# Offline Mode & Remote Config Cache — Implementation Plan

> Branch: `fix/Offline-mode`
> Working dir: `/Users/lchoquel/repos/Pipelex/_off` (worktree of `pipelex/`)

## Objectives (verbatim from user)

1. **Fully support offline mode when gateway is disabled** — no remote config fetch is ever attempted; setup completes without network.
2. **Support dry-run mode when gateway is enabled but the remote config is temporarily unavailable**, even when the bundle references gateway models. Implies a cache that must be **primed at the time Pipelex first creates its local or global config**, and refreshed on every successful subsequent fetch.
3. **Fail if requested gateway models don't exist** according to the fresh remote config (when available) or the cached one (when that's all we have). No silent fallbacks.

## Non-objectives

- We are not removing the remote fetch. We are adding resilience.
- We are not granting offline inference *runs* through the gateway (the gateway itself still needs network at call time). We're talking about *setup* and *dry-run* working offline. Real inference calls fail as they always have when the network is down.
- We are not bundling a baked-in snapshot in the package.

## Failure point (already diagnosed)

- `pipelex/pipelex.py:202` — `effective_needs_model_specs = needs_model_specs if needs_model_specs is not None else needs_inference`. When the agent CLI passes `needs_model_specs=True` explicitly (it does for `validate`, `inputs`, and `run --dry-run`), this is `True` regardless of `needs_inference`.
- `pipelex/pipelex.py:235` — unconditionally calls `RemoteConfigFetcher.fetch_remote_config()` when `is_pipelex_service_enabled and effective_needs_model_specs`. Raises `RemoteConfigFetchError` on any network failure.
- `pipelex/system/pipelex_service/remote_config_fetcher.py:93` — only short-circuits for Codex *Cloud* (`runtime_manager.is_in_codex_cloud`), not for local Codex sandboxes or general offline cases.

## Design overview

### Cache contract

- Location: `~/.pipelex/cache/remote_config.json` (global, single-user). Schema-versioned and timestamped.
- Written by:
  - `RemoteConfigFetcher.fetch_remote_config()` on every successful fetch (opportunistic refresh).
  - The init flow when gateway terms are accepted (priming step).
- Read by:
  - `RemoteConfigFetcher.fetch_remote_config()` when the network call fails, as a fallback.
- Never read for any other purpose. Cache is a **last resort**, not a freshness optimisation.

### New types

- `CachedRemoteConfig` — wraps `RemoteConfig` with `cached_at: datetime`, `cache_schema_version: int`.
- `RemoteConfigSource` (StrEnum from `pipelex.types`): `FRESH` | `CACHED`.
- `RemoteConfigResult` — small dataclass-like model returning `(config, source)`.

### New exceptions (in `pipelex/system/pipelex_service/exceptions.py`)

- `RemoteConfigUnavailableError(PipelexServiceError)` — raised when fetch failed AND no usable cache exists. Replaces the user-facing `RemoteConfigFetchError` at the call site in `pipelex.py`. Message names the cache path and remediation (`pipelex init` while online).
- `GatewayCachedModelUnknownError(PipelexServiceError)` — raised when a bundle references a gateway model that isn't present in the (fresh or cached) gateway specs.

### Wiring in `pipelex.py`

- `setup()` keeps calling `RemoteConfigFetcher.fetch_remote_config()`, but the fetcher now returns a `RemoteConfigResult` with a `source` discriminator.
- When `source == CACHED`, telemetry stays disabled (we already disable it without inference; this is a separate, stricter guard for stale operation) and the resulting `GatewayConfig` carries an `is_from_cache: bool` flag so downstream code can refuse to call out where stale data isn't acceptable.

### Behaviour matrix to validate

| Scenario | Gateway enabled | Network | Cache | Expected |
|---|---|---|---|---|
| BYOK offline | no | down | n/a | setup OK, validate OK, dry-run OK, inference OK if backend reachable |
| Gateway dry-run, fresh | yes | up | n/a | fresh fetch, dry-run OK |
| Gateway dry-run, cached | yes | down | present | cache fallback, warning, dry-run OK |
| Gateway dry-run, cold | yes | down | absent | `RemoteConfigUnavailableError` with clear remediation |
| Gateway inference, cached | yes | down | present | cache fallback, inference still fails when call is made (network); error message attributes the failure to the gateway call, not setup |
| Bundle references unknown model | yes | up or down | any | `GatewayCachedModelUnknownError` during library load |

---

## Working agreements

- TDD throughout. Red → green for every functional unit.
- Integration tests declare **blueprints in Python** and exercise the public APIs (`Pipelex.make`, `RemoteConfigFetcher`, `BackendLibrary`, etc.). They go under `tests/integration/pipelex/`.
- E2E tests use **actual `.mthds` bundle files** placed in `tests/e2e/data/offline_mode/` and drive them via `mthds-agent run bundle ... --dry-run --mock-inputs` (subprocess), the same surface that fails today.
- Follow `.claude/rules/python-standards.md`:
  - 1 TestClass per test module.
  - `StrEnum` from `pipelex.types`.
  - Never `except Exception` outside CLI roots.
  - `pytest-mock` only; never `unittest.mock`.
  - `make agent-check` after code changes, `make agent-test` at session boundaries.
- No backward compatibility shims. If we rename or change a signature, just change it.

## Cold-start handoff protocol

After every `🛑 CHECKPOINT` line:

1. Re-read this `TODOS.md` and mark just-completed checkboxes.
2. Append a `### Checkpoint N status` subsection at the bottom of this file capturing:
   - What landed (paths of new/modified files).
   - Open decisions / unknowns.
   - The exact next checkbox to start with.
3. Run `make agent-check && make agent-test`. Note pass/fail in the checkpoint status.
4. Stop. A new session takes over from the status block.

---

## Phase 0 — Lock down current behaviour (no production code changes)

- [ ] **0.1** Add `tests/integration/pipelex/system/pipelex_service/test_offline_baseline.py` with `TestOfflineBaseline` covering current behaviour (BYOK-offline already works; gateway-offline currently raises). These tests fail-forward will be flipped in later phases — for now they pin existing semantics so we notice unintended regressions. Use `mocker.patch("httpx.get", side_effect=httpx.ConnectError(...))`.
- [ ] **0.2** Confirm by running the new tests that `Pipelex.make(needs_inference=False, needs_model_specs=True)` with gateway disabled (BYOK backend only) succeeds offline. If it does not, file a sub-task here before continuing — a phantom network call somewhere has to be tracked down.
- [ ] **0.3** Run `make agent-check && make agent-test`. Record output in the checkpoint status.

🛑 **CHECKPOINT 0** — Baseline pinned. Cold-start safe: new session can pick up from Phase 1 with confidence about what already works.

---

## Phase 1 — Cache module (TDD, isolated, no integration yet)

**Goal:** stand up `RemoteConfigCache` with no other code calling it yet. Pure read/write/version logic.

- [ ] **1.1** Write failing tests first: `tests/unit/system/pipelex_service/test_remote_config_cache.py` with `TestRemoteConfigCache`:
  - `test_write_then_read_roundtrip` — writes a config, reads it back, asserts equality + non-stale timestamp.
  - `test_read_missing_returns_none` — no cache file → `None` (no exception).
  - `test_read_corrupted_json_returns_none_and_logs` — file exists but isn't JSON → returns `None`, logs a warning. (Use `caplog`.)
  - `test_read_wrong_schema_version_returns_none` — file from a different schema version → returns `None`.
  - `test_write_creates_parent_dir` — cache dir doesn't exist yet → created.
  - `test_cache_path_uses_global_config_dir` — path lives under `config_manager.global_config_dir / "cache" / "remote_config.json"`.
- [ ] **1.2** Implement `pipelex/system/pipelex_service/remote_config_cache.py`:
  - `class RemoteConfigCache` with `@classmethod load() -> CachedRemoteConfig | None` and `@classmethod store(remote_config: RemoteConfig) -> None`.
  - JSON format: `{"schema_version": 1, "cached_at": "<iso>", "config": {...}}`.
  - Catch only `OSError`, `JSONDecodeError`, `ValidationError` — never bare `Exception`.
- [ ] **1.3** Add `CachedRemoteConfig` model to `remote_config.py` (or a sibling module — your call). Use `datetime.timezone.utc` (not `datetime.UTC`, Python 3.10 compatibility).
- [ ] **1.4** `make agent-check` clean.
- [ ] **1.5** Tests green.

🛑 **CHECKPOINT 1** — Cache module shippable on its own. Cold-start safe.

---

## Phase 2 — Fetch with fallback (TDD)

**Goal:** `RemoteConfigFetcher.fetch_remote_config()` returns a `RemoteConfigResult` carrying source provenance, writes cache on success, reads cache on failure, raises `RemoteConfigUnavailableError` only when both fail.

- [ ] **2.1** Failing tests in `tests/integration/pipelex/system/pipelex_service/test_remote_config_fetcher.py` with `TestRemoteConfigFetcher`:
  - `test_success_returns_fresh_and_writes_cache` — `mocker.patch("httpx.get")` returns a valid payload → result has `source=FRESH`, cache file written.
  - `test_network_failure_with_cache_returns_cached` — `httpx.get` raises `httpx.ConnectError`, cache is pre-populated via `RemoteConfigCache.store(...)` → result has `source=CACHED`, warning logged.
  - `test_network_failure_without_cache_raises_unavailable` — `httpx.get` raises, no cache → `RemoteConfigUnavailableError` with cache path in message.
  - `test_http_error_with_cache_returns_cached` — 5xx response with cache present → cached fallback.
  - `test_http_error_without_cache_raises_unavailable` — 5xx no cache → `RemoteConfigUnavailableError`.
  - `test_validation_error_does_not_fall_back` — the remote responded with garbage JSON; we must still surface `RemoteConfigValidationError` and **not** silently fall back to cache (a server-side schema break is a real bug).
  - `test_codex_cloud_short_circuit_still_works` — `runtime_manager.is_in_codex_cloud=True` → returns dummy with `source=FRESH`, does not write cache.
- [ ] **2.2** Implement the new control flow in `remote_config_fetcher.py`:
  - Rename / extend `fetch_remote_config` to return `RemoteConfigResult(config, source)`.
  - Persist to cache on success.
  - On `httpx.TimeoutException | httpx.RequestError | httpx.HTTPStatusError`: try cache; if hit, log warning + return CACHED; if miss, raise `RemoteConfigUnavailableError` (message includes cache path).
  - Leave `RemoteConfigValidationError` path untouched (no cache fallback).
- [ ] **2.3** Add `RemoteConfigUnavailableError` to `exceptions.py` with rich remediation text (mention `pipelex init` while online to prime cache, and disabling gateway in `backends.toml` as the offline-permanent alternative).
- [ ] **2.4** Update every existing caller of `fetch_remote_config()` to handle the new return shape (they are listed at `grep -n "fetch_remote_config" pipelex/**/*.py`). Most callers can do `result = ...; remote_config = result.config`.
- [ ] **2.5** `make agent-check` clean. Tests green.

🛑 **CHECKPOINT 2** — Fetcher is now resilient and provenance-aware. Cold-start safe.

---

## Phase 3 — Wire `is_from_cache` through `GatewayConfig` and enforce model membership (TDD)

**Goal:** downstream code can see whether the config it has is fresh or cached; backend library raises a clear error when a bundle references a gateway model not present in the (fresh or cached) specs.

- [ ] **3.1** Failing tests in `tests/integration/pipelex/cogt/model_backends/test_gateway_unknown_model.py` with `TestGatewayUnknownModel`:
  - `test_known_model_loads` — gateway specs contain `gpt-x`, backend deck references it → load OK.
  - `test_unknown_model_fresh_raises` — backend deck references `gpt-future` not in fresh gateway specs → `GatewayCachedModelUnknownError` (or a renamed variant — see 3.3 below) with the model name and source (`FRESH` vs `CACHED`) in the message.
  - `test_unknown_model_cached_raises_with_stale_hint` — same as above but source is `CACHED`; message hints "remote config is stale; run `pipelex init` while online to refresh".
- [ ] **3.2** Failing tests in `tests/integration/pipelex/system/pipelex_service/test_setup_with_cache.py` with `TestSetupWithCache`:
  - `test_setup_succeeds_with_stale_cache_dry_run` — `Pipelex.make(needs_inference=False, needs_model_specs=True)` with gateway enabled + httpx mocked to fail + cache primed → setup succeeds, a `RemoteConfigStaleWarning` is logged.
  - `test_setup_fails_without_cache_dry_run` — same as above but cache empty → `RemoteConfigUnavailableError`.
- [ ] **3.3** Implement:
  - Add `is_from_cache: bool = False` field to `GatewayConfig`.
  - In `pipelex.py:setup()`, propagate `result.source` into the `GatewayConfig` and log a `RemoteConfigStaleWarning` (new `UserWarning` subclass next to `GatewayOverrideWarning`) when stale.
  - In `BackendLibrary._load_gateway_model_specs` (or wherever model_handle resolution lives — read the call site before deciding), raise `GatewayCachedModelUnknownError` when a referenced gateway model isn't in `gateway_config.model_specs`. Message branches on `is_from_cache`.
  - Decide: keep the name `GatewayCachedModelUnknownError` or rename to `GatewayUnknownModelError` since it also fires on fresh data. **Recommendation: `GatewayUnknownModelError` with a `source` field.** Pick one and stay consistent.
- [ ] **3.4** Update agent CLI error mapping in `pipelex/cli/agent_cli/commands/agent_cli_factory.py` and `agent_output.py` (`AGENT_ERROR_HINTS`, `AGENT_ERROR_DOMAINS`) for the two new errors.
- [ ] **3.5** `make agent-check` clean. Tests green.

🛑 **CHECKPOINT 3** — Stale operation is safe, model membership is enforced. Cold-start safe.

---

## Phase 4 — Cache priming at init (TDD)

**Goal:** when `pipelex init` (or the agent-cli equivalent) completes the gateway terms acceptance flow, attempt one fetch and persist the cache. If offline at init time, log a warning and continue — cache stays empty, user has been told.

- [ ] **4.1** Failing tests in `tests/integration/pipelex/cli/commands/init/test_cache_priming.py` with `TestCachePriming`:
  - `test_init_primes_cache_when_online` — run init flow with gateway enabled + httpx mocked to succeed → cache file present and readable afterwards.
  - `test_init_warns_when_offline` — same flow but httpx mocked to fail → init completes (no crash), cache file not present, warning printed to console.
  - `test_init_skips_priming_when_gateway_disabled` — gateway disabled in backends → no fetch attempted, no cache written.
  - `test_init_does_not_double_prime` — if cache already exists and is fresh, init can still refresh it (this is fine; assert the file was rewritten).
- [ ] **4.2** Implement priming hook: in `pipelex/cli/commands/init/command.py`, after `_check_gateway_terms_if_needed` has accepted terms and gateway remains enabled, call a new helper `prime_remote_config_cache(console)` that calls `RemoteConfigFetcher.fetch_remote_config()` inside a try/except limited to `RemoteConfigUnavailableError` and `RemoteConfigValidationError`. On unavailable: log a clear yellow warning; on validation error: re-raise (server schema break is fatal).
- [ ] **4.3** Mirror the same hook into the agent CLI init path (`pipelex/cli/agent_cli/commands/init_cmd.py`) so machine clients also prime.
- [ ] **4.4** `make agent-check` clean. Tests green.

🛑 **CHECKPOINT 4** — Cache lifecycle complete. Cold-start safe.

---

## Phase 5 — E2E with real `.mthds` bundles

**Goal:** exercise the full surface that the codex-sandbox handoff doc describes (`mthds-agent run bundle ... --dry-run --mock-inputs`) through subprocess invocations.

- [ ] **5.1** Create `tests/e2e/data/offline_mode/` with three minimal bundles:
  - `byok_simple/` — references a backend model that does **not** require the gateway (e.g. ollama or anthropic). All `.mthds` files necessary to validate, plus an `inputs.json` shape for `--mock-inputs`.
  - `gateway_known_model/` — references a gateway model that exists in the test fixture remote config.
  - `gateway_unknown_model/` — references a gateway model that does **not** exist in the test fixture remote config.
- [ ] **5.2** Failing tests in `tests/e2e/agent_cli/test_offline_run_dry.py` with `TestOfflineDryRun`. Apply `@pytest.mark.gha_disabled` only if the network-blocking approach we choose requires it; otherwise leave unmarked. Mark `@pytest.mark.asyncio(loop_scope="class")` if any tests are async. Each test:
  - Invokes the CLI via `subprocess.run([".venv/bin/mthds-agent", "run", "bundle", str(bundle_dir), "--dry-run", "--mock-inputs"], ...)`.
  - Uses a `monkeypatch`-style fixture to point `HOME` (and therefore `~/.pipelex/cache/`) at a tmp path, so cache state is controlled per-test.
  - Uses an HTTP-blocking layer (recommend: a `conftest.py` fixture that sets a `PIPELEX_TEST_BLOCK_REMOTE_FETCH=1` env var which the fetcher checks early and raises a synthetic `httpx.ConnectError`). This avoids fragile real-network blocking.
- [ ] **5.3** Test cases:
  - `test_byok_offline_succeeds` — gateway disabled (test bundle ships with `backends.toml` that has gateway disabled), no network, no cache → exit 0, structured success JSON.
  - `test_gateway_known_with_cache_succeeds_offline` — gateway enabled, no network, cache primed → exit 0, success JSON includes a `warnings` field naming the stale source.
  - `test_gateway_unknown_with_cache_fails_with_clear_error` — exit nonzero, `error_type == "GatewayUnknownModelError"`, model name surfaced, `source == "CACHED"` somewhere in payload.
  - `test_gateway_no_cache_no_network_fails_with_unavailable` — exit nonzero, `error_type == "RemoteConfigUnavailableError"`, message references priming via `pipelex init`.
- [ ] **5.4** `make agent-check` clean. Tests green.

🛑 **CHECKPOINT 5** — End-to-end behaviour validated against the exact surface the codex-sandbox doc exercised. Cold-start safe.

---

## Phase 6 — User-facing polish

- [ ] **6.1** Update `pipelex/cli/agent_cli/commands/agent_output.py`:
  - Add `AGENT_ERROR_HINTS` entries for `RemoteConfigUnavailableError` and `GatewayUnknownModelError`.
  - Add `AGENT_ERROR_DOMAINS` entries for both.
- [ ] **6.2** Update `pipelex/cli/error_handlers.py` for the Rich CLI surface (mirror the agent-cli hints).
- [ ] **6.3** Extend `pipelex doctor` to report cache presence, cache age, and whether gateway is enabled but cache is missing.
- [ ] **6.4** Update relevant CLAUDE.md sections:
  - `pipelex/cli/agent_cli/CLAUDE.md` if error classes are mentioned.
  - `pipelex/system/pipelex_service/CLAUDE.md` if it exists; create a short note if not (only if there's already a convention for service-level docs).
- [ ] **6.5** Add a `## [Unreleased]` entry to `CHANGELOG.md` summarising the user-visible behaviour change (offline support + new error types).
- [ ] **6.6** Update the codex sandbox handoff doc at `../mthds-plugins/wip/codex-sandbox-escalation.md` to note that `--dry-run` no longer requires escalation once Pipelex is initialised online once. (Heads-up: that file is in the `mthds-plugins/` repo, not this worktree — coordinate before editing.)

🛑 **CHECKPOINT 6** — User-facing surface complete. Cold-start safe.

---

## Phase 7 — Final verification

- [ ] **7.1** `make agent-check` clean.
- [ ] **7.2** `make agent-test` clean.
- [ ] **7.3** Manually reproduce all four scenarios from the behaviour matrix:
  - BYOK offline `mthds-agent run bundle ... --dry-run --mock-inputs` → success.
  - Gateway online, no cache → success, cache written.
  - Gateway offline, cache present → success with stale warning.
  - Gateway offline, no cache → clear `RemoteConfigUnavailableError`.
  - Bundle references unknown gateway model → clear `GatewayUnknownModelError`.
- [ ] **7.4** Squash-friendly commit history; PR description references the codex-sandbox-escalation handoff.

🛑 **CHECKPOINT 7** — Ready for review.

---

## Risk log

- **Caller migration in Phase 2.** Every call site of `fetch_remote_config()` must be updated. If a caller is missed, it'll break at runtime in dev-CLI tooling that's rarely exercised. Grep before declaring 2.4 done.
- **Cache poisoning during validation breakage.** We explicitly chose NOT to fall back to cache on `RemoteConfigValidationError`. If we ship a backend that emits a remote config our pydantic model rejects, all clients fail loudly — which is the desired behaviour. Confirm this design choice survives review.
- **`is_first_time_backends_setup` semantics.** Phase 4 priming is conditional on terms-accepted-and-gateway-enabled state. The init flow has a few branches; verify priming runs on the **first** init pass, not only on subsequent re-inits.
- **Schema version bumping.** If we ever change `RemoteConfig`'s shape, bump `RemoteConfigCache.SCHEMA_VERSION` so stale caches don't pretend to be valid.

## Open questions to resolve as we go

- Should `pipelex doctor` actively try to refresh a stale cache, or just report on it? **Default: report only**, to keep `doctor` side-effect-free. Decide explicitly in Phase 6.3.
- Maximum acceptable cache age before we refuse to use it? **Default: no cap.** Gateway model lists drift slowly; an old cache is better than no cache. Revisit if it bites us.
- Should the agent-cli `init` command auto-prime even without `--gateway`? **No.** Priming only when gateway is selected.

---

## Checkpoint status log

<!-- Append a "### Checkpoint N status" block here after each 🛑 CHECKPOINT, capturing what landed, open decisions, and the next checkbox to start with. Keep blocks short; the codebase is authoritative. -->
