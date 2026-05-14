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
- `pipelex/system/pipelex_service/remote_config_fetcher.py:93` — only short-circuits for Codex *Cloud* (`runtime_manager.is_in_codex_cloud`). The cache fallback added below also solves the local-sandbox case incidentally; no new sandbox detection is needed.

## Design overview

### Cache contract

- Location: `~/.pipelex/cache/remote_config.json` (global, single-user). Schema-versioned and timestamped.
- **Stored payload is the raw JSON dict** returned by `response.json()`, NOT a re-serialized Pydantic model. This avoids any Pydantic round-trip quirks (e.g. `extra="allow"` semantics across `model_dump()` modes) and keeps the cache stable against minor schema drift. On load: `RemoteConfig.model_validate(payload["raw_config"])`.
- The remote config URL is versioned in `pipelex-back-office` (we control both ends). Schema bumps are handled by bumping both the URL version AND the cache `SCHEMA_VERSION` constant; older caches are then rejected (return `None`) and clients re-prime on next online fetch.
- **Atomic writes**: `tempfile.NamedTemporaryFile(dir=cache_dir, delete=False)` → write → `os.replace(tmp_path, cache_path)`. Prevents corrupted-cache from concurrent writes.
- Written by:
  - `RemoteConfigFetcher.fetch_remote_config()` on every successful fetch (opportunistic refresh).
  - The init flow when gateway terms are accepted (priming step).
- Read by:
  - `RemoteConfigFetcher.fetch_remote_config()` when the network call fails, as a fallback.
- Never read for any other purpose. Cache is a **last resort**, not a freshness optimisation.

### New types

- `CachedRemoteConfig` — Pydantic `BaseModel` wrapping the cached payload metadata: `cached_at: datetime`, `cache_schema_version: int`, `raw_config: dict[str, Any]` (the raw remote payload). Use `datetime.timezone.utc`, not `datetime.UTC`.
- `RemoteConfigSource` — `StrEnum` from `pipelex.types` with **lowercase string values** to match codebase convention: `FRESH = "fresh"` | `CACHED = "cached"`.
- `RemoteConfigResult` — Pydantic `BaseModel` (`ConfigDict(extra="forbid", strict=True)`) carrying `config: RemoteConfig`, `source: RemoteConfigSource`, `cached_at: datetime | None = None`. NOT a dataclass; match project convention.

### New / preserved exceptions (in `pipelex/system/pipelex_service/exceptions.py`)

- **Keep** `RemoteConfigFetchError` as the existing internal exception raised by the retry layer when the network fails. Do NOT remove it — it's already caught by `doctor_cmd.py:745`, `cli_factory.py:73`, `error_handlers.py:365`, and the agent CLI hints (`agent_output.py:51`). Removing it breaks those surfaces.
- **Add** `RemoteConfigUnavailableError(PipelexServiceError)` as a sibling — raised when fetch failed AND no usable cache exists. Message names the cache path and remediation (`pipelex init` while online; or disable gateway in `backends.toml` as the offline-permanent alternative).
- **Add** `GatewayUnknownModelError(PipelexServiceError)` — raised when a bundle references a gateway model that isn't present in the (fresh or cached) gateway specs. Carries a `source: RemoteConfigSource` field; message branches: when `CACHED`, hint that the remote config is stale and suggest `pipelex init` while online.
- **Add** `RemoteConfigStaleWarning(UserWarning)` — emitted when `source == CACHED` during setup. Lives next to `GatewayOverrideWarning` in `exceptions.py`.

### Wiring in `pipelex.py`

- `setup()` keeps calling `RemoteConfigFetcher.fetch_remote_config()`, but the fetcher now returns a `RemoteConfigResult`.
- The `source` is **NOT stored on `GatewayConfig`** (which keeps `extra="forbid"` and stays a pure value object describing the gateway). Instead, `setup()` passes `gateway_config_source: RemoteConfigSource` separately to `models_manager.setup()` → `BackendLibrary` so the model-membership check can branch its error message on fresh-vs-cached.
- When `source == CACHED`:
  - `is_pipelex_telemetry_enabled` stays `False` (already disabled without inference; this is a separate, stricter guard for stale operation). Add an explicit test for this.
  - Emit `RemoteConfigStaleWarning` via `warnings.warn(...)`.
  - The agent CLI `agent_success(...)` envelope surfaces a structured `warnings: [{"type": "RemoteConfigStale", "cached_at": "..."}]` field so machine consumers see it.

### Doc / fixture generators must refuse stale data

`gateway_models_generator.py:46` and `preprocess_test_models_cmd.py:98` regenerate **committed** reference docs and test fixtures from the remote config. If they silently fall back to cache, they'll bake stale data into the repo.

- Add a `require_fresh: bool = False` argument to `fetch_remote_config()` (or expose a thin `fetch_remote_config_fresh_only()` wrapper) that raises `RemoteConfigUnavailableError` immediately if `source == CACHED`.
- Both dev-CLI generators set it; everyone else doesn't.
- Add a unit test that this branch raises when only cache is available.

### Behaviour matrix to validate

| Scenario | Gateway enabled | Network | Cache | Expected |
|---|---|---|---|---|
| BYOK offline | no | down | n/a | setup OK, validate OK, dry-run OK, inference OK if backend reachable |
| Gateway dry-run, fresh | yes | up | n/a | fresh fetch, dry-run OK |
| Gateway dry-run, cached | yes | down | present | cache fallback, warning, dry-run OK |
| Gateway dry-run, cold | yes | down | absent | `RemoteConfigUnavailableError` with clear remediation |
| Gateway inference, cached | yes | down | present | cache fallback, inference still fails when call is made (network); error message attributes the failure to the gateway call, not setup |
| Bundle references unknown model | yes | up or down | any | `GatewayUnknownModelError` during library load (message branches on source) |
| Doc generator offline w/ cache | yes | down | present | `RemoteConfigUnavailableError` (require_fresh=True refuses cache) |

---

## Working agreements

- TDD throughout. Red → green for every functional unit.
- Integration tests declare **blueprints in Python** and exercise the public APIs (`Pipelex.make`, `RemoteConfigFetcher`, `BackendLibrary`, etc.). They go under `tests/integration/pipelex/`.
- E2E tests use **actual `.mthds` bundle files** placed in `tests/e2e/data/offline_mode/` and drive them via `mthds-agent run bundle ... --dry-run --mock-inputs` (subprocess), the same surface that fails today.
- Follow `.claude/rules/python-standards.md`:
  - 1 TestClass per test module.
  - `StrEnum` from `pipelex.types`.
  - Never `except Exception` outside CLI roots. Use `from pytest_mock import MockerFixture`; never `unittest.mock`.
  - `make agent-check` after code changes, `make agent-test` at session boundaries.
- No backward compatibility shims. If we rename or change a signature, just change it.
- **No test-aware production code**: do NOT introduce a `PIPELEX_TEST_BLOCK_REMOTE_FETCH` env var. Use the legitimate `PIPELEX_REMOTE_CONFIG_URL` override (see Phase 5) to point at an unreachable URL.

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

- [x] **0.1** Add `tests/integration/pipelex/system/pipelex_service/test_offline_baseline.py` with `TestOfflineBaseline` covering the baseline that must NOT regress: BYOK-offline succeeds, gateway-offline-without-cache raises today. Write these as **passing tests against current behaviour** (do not write "expected-to-fail" tests). In Phases 2/3 they will be updated as semantics legitimately change, not "flipped." Use `mocker.patch("httpx.get", side_effect=httpx.ConnectError(...))`.
- [x] **0.2** Confirm by running the new tests that `Pipelex.make(needs_inference=False, needs_model_specs=True)` with gateway disabled (BYOK backend only) succeeds offline. If it does not, file a sub-task here before continuing — a phantom network call somewhere has to be tracked down. **Note**: 3.2 will add an explicit regression guard for this; 0.2 is the one-time confirmation.
- [x] **0.3** Run `make agent-check && make agent-test`. Record output in the checkpoint status.

🛑 **CHECKPOINT 0** — Baseline pinned. Cold-start safe: new session can pick up from Phase 1 with confidence about what already works.

---

## Phase 1 — Cache module (TDD, isolated, no integration yet)

**Goal:** stand up `RemoteConfigCache` with no other code calling it yet. Pure read/write/version logic.

- [x] **1.1** Write failing tests first: `tests/unit/system/pipelex_service/test_remote_config_cache.py` with `TestRemoteConfigCache`:
  - `test_write_then_read_roundtrip` — writes a config, reads it back, asserts equality + non-stale timestamp.
  - `test_read_missing_returns_none` — no cache file → `None` (no exception).
  - `test_read_corrupted_json_returns_none_and_logs` — file exists but isn't JSON → returns `None`, logs a warning. (Use `caplog`.)
  - `test_read_wrong_schema_version_returns_none` — file from a different schema version → returns `None`.
  - `test_write_creates_parent_dir` — cache dir doesn't exist yet → created.
  - `test_cache_path_uses_global_config_dir` — path lives under `config_manager.global_config_dir / "cache" / "remote_config.json"`.
  - `test_write_is_atomic` — simulate failure between write-to-tmp and `os.replace` (e.g. via `mocker.patch("os.replace", side_effect=OSError)`); assert no partial file at the destination path.
  - `test_raw_payload_extras_preserved` — store a payload with an unknown top-level key, load it back, pass through `RemoteConfig.model_validate(...)`, and assert the unknown key is still on the resulting model (Pydantic `extra="allow"` semantics). Guards the cache-integrity invariant.
- [x] **1.2** Implement `pipelex/system/pipelex_service/remote_config_cache.py`:
  - `class RemoteConfigCache` with `@classmethod load() -> CachedRemoteConfig | None` and `@classmethod store(remote_config_payload: dict[str, Any]) -> None`. **The `store` argument is the raw JSON dict from `response.json()`, not a `RemoteConfig` instance.**
  - JSON file format on disk: `{"schema_version": 1, "cached_at": "<iso>", "raw_config": { ... raw remote payload ... }}`.
  - Atomic write via `tempfile.NamedTemporaryFile(dir=cache_dir, delete=False)` + `os.replace`.
  - Catch only `OSError`, `JSONDecodeError`, `ValidationError` — never bare `Exception`.
- [x] **1.3** Add `CachedRemoteConfig` Pydantic model alongside `RemoteConfigCache`. Fields: `schema_version: int`, `cached_at: datetime`, `raw_config: dict[str, Any]`. Use `datetime.timezone.utc` (Python 3.10 compatibility). Provide a `to_remote_config()` helper that returns `RemoteConfig.model_validate(self.raw_config)`.
- [x] **1.4** `make agent-check` clean.
- [x] **1.5** Tests green.

🛑 **CHECKPOINT 1** — Cache module shippable on its own. Cold-start safe.

---

## Phase 2 — Fetch with fallback (TDD)

**Goal:** `RemoteConfigFetcher.fetch_remote_config()` returns a `RemoteConfigResult` carrying source provenance, writes cache on success, reads cache on failure, raises `RemoteConfigUnavailableError` only when both fail. Keep `RemoteConfigFetchError` as the internal exception raised by the retry layer.

- [x] **2.1** Failing tests in `tests/integration/pipelex/system/pipelex_service/test_remote_config_fetcher.py` with `TestRemoteConfigFetcher`:
  - `test_success_returns_fresh_and_writes_cache` — `mocker.patch("httpx.get")` returns a valid payload → result has `source=FRESH`, cache file written.
  - `test_network_failure_with_cache_returns_cached` — `httpx.get` raises `httpx.ConnectError`, cache is pre-populated via `RemoteConfigCache.store(...)` → result has `source=CACHED`, `RemoteConfigStaleWarning` emitted.
  - `test_network_failure_without_cache_raises_unavailable` — `httpx.get` raises, no cache → `RemoteConfigUnavailableError` with cache path in message.
  - `test_http_error_with_cache_returns_cached` — 5xx response with cache present → cached fallback.
  - `test_http_error_without_cache_raises_unavailable` — 5xx no cache → `RemoteConfigUnavailableError`.
  - `test_validation_error_does_not_fall_back` — the remote responded with garbage JSON; we must still surface `RemoteConfigValidationError` and **not** silently fall back to cache (a server-side schema break is a real bug, and we control the server).
  - `test_codex_cloud_short_circuit_still_works` — `runtime_manager.is_in_codex_cloud=True` → returns dummy with `source=FRESH`, does not write cache.
  - `test_succeeds_after_4_transient_failures_no_cache_fallback` — `httpx.get` raises `ConnectError` 4 times then returns valid payload; tenacity (`stop_after_attempt(5)`) rescues; result has `source=FRESH`, no cache fallback was triggered.
  - `test_falls_back_to_cache_after_5_transient_failures` — all 5 attempts raise; cache is pre-populated; result has `source=CACHED`.
  - `test_require_fresh_refuses_cache` — `httpx.get` raises, cache populated, but caller passed `require_fresh=True` → raises `RemoteConfigUnavailableError` (doc generators must not silently use cache).
- [x] **2.2** Implement the new control flow in `remote_config_fetcher.py`:
  - Change `fetch_remote_config` to return `RemoteConfigResult(config, source, cached_at)` and accept `require_fresh: bool = False`.
  - Keep raising the existing `RemoteConfigFetchError` from the inner `_fetch_remote_config_with_retry` path (don't churn that).
  - In the outer flow: catch `RemoteConfigFetchError`. If `require_fresh`: re-raise as `RemoteConfigUnavailableError`. Else: try cache; if hit, emit `RemoteConfigStaleWarning` + return `source=CACHED`; if miss, raise `RemoteConfigUnavailableError` (message includes cache path).
  - Persist to cache on success.
  - Leave `RemoteConfigValidationError` path untouched (no cache fallback).
- [x] **2.3** Add `RemoteConfigUnavailableError` and `RemoteConfigStaleWarning` to `exceptions.py`. `RemoteConfigUnavailableError` message: include cache path and remediation (`pipelex init` while online to prime cache; disable gateway in `backends.toml` as the offline-permanent alternative). Do NOT remove `RemoteConfigFetchError`.
- [x] **2.4** Update every existing caller of `fetch_remote_config()`. Pre-checked call sites (run `grep -rn "fetch_remote_config" --include="*.py"` to verify nothing else has appeared):
  - `pipelex/pipelex.py:235` — main setup; needs `source` for downstream wiring.
  - `pipelex/cli/commands/doctor_cmd.py:740` — doctor; surface cache age in output.
  - `pipelex/cli/dev_cli/commands/gateway_models_generator.py:46` — **must pass `require_fresh=True`** (regenerates committed docs).
  - `pipelex/cli/dev_cli/commands/preprocess_test_models_cmd.py:98` — **must pass `require_fresh=True`** (rewrites test fixtures).
  - `tests/conftest.py:35` — session cache shim; just unwrap `.config`.
  - `tests/unit/pipelex/cogt/models/test_model_deck_references.py:59` — just unwrap `.config`.
  Most callers do `result = ...; remote_config = result.config`.
- [x] **2.4b** While editing `doctor_cmd.py` for 2.4, replace the **pre-existing** `except Exception as exc:` at `doctor_cmd.py:767` with the specific exception classes that `models_manager.setup()` and `validate_model_deck()` can raise (the lineage is already enumerated in `pipelex.py:307-336`). This is an existing CLAUDE.md violation; fix it while we're here.
- [x] **2.5** `make agent-check` clean. Tests green.

🛑 **CHECKPOINT 2** — Fetcher is now resilient and provenance-aware. Cold-start safe.

---

## Phase 3 — Plumb `source` through setup and enforce model membership (TDD)

**Goal:** downstream code can see whether the config it has is fresh or cached; backend library raises a clear error when a bundle references a gateway model not present in the (fresh or cached) specs. **Source is passed as a separate argument, NOT stored on `GatewayConfig`** — `GatewayConfig` stays `extra="forbid"` and remains a pure value object.

- [x] **3.1** Failing tests in `tests/integration/pipelex/cogt/model_backends/test_gateway_unknown_model.py` with `TestGatewayUnknownModel`:
  - `test_known_model_loads` — gateway specs contain `gpt-x`, backend deck references it → load OK.
  - `test_unknown_model_fresh_raises` — backend deck references `gpt-future` not in fresh gateway specs → `GatewayUnknownModelError` with `source=FRESH` and the model name in the message.
  - `test_unknown_model_cached_raises_with_stale_hint` — same as above but source is `CACHED`; message hints "remote config is stale; run `pipelex init` while online to refresh".
- [x] **3.2** Failing tests in `tests/integration/pipelex/system/pipelex_service/test_setup_with_cache.py` with `TestSetupWithCache`:
  - `test_setup_succeeds_with_stale_cache_dry_run` — `Pipelex.make(needs_inference=False, needs_model_specs=True)` with gateway enabled + httpx mocked to fail + cache primed → setup succeeds, a `RemoteConfigStaleWarning` is emitted.
  - `test_setup_fails_without_cache_dry_run` — same as above but cache empty → `RemoteConfigUnavailableError`.
  - `test_telemetry_disabled_when_source_cached` — `Pipelex.make(needs_inference=True)` with gateway enabled + cache fallback → assert the active telemetry manager is the no-op variant (or `is_pipelex_telemetry_enabled` is `False`). Guards the "stale ops shouldn't phone home" invariant.
  - `test_byok_offline_regression_guard` — `Pipelex.make(needs_inference=False, needs_model_specs=True)` with gateway **disabled** in backends.toml + httpx mocked to fail → setup succeeds without ever calling `fetch_remote_config()` (assert via `mocker.spy`). This is the explicit regression test that 0.2 only verifies one-time; without it, a future refactor could re-introduce a phantom network call.
- [x] **3.3** Implement:
  - Add a `gateway_config_source: RemoteConfigSource | None` parameter to `ModelManager.setup()` and `BackendLibrary._load_gateway_model_specs()`. `None` means no gateway active.
  - In `pipelex.py:setup()`, after the fetch:
    - Build `GatewayConfig` from `result.config` (no `is_from_cache` field — `GatewayConfig` stays unchanged).
    - Pass `result.source` to `models_manager.setup(...)` as `gateway_config_source`.
    - When `result.source == CACHED`, emit `RemoteConfigStaleWarning` (UserWarning subclass next to `GatewayOverrideWarning`).
  - In `BackendLibrary._load_gateway_model_specs` (or wherever model_handle resolution lives — read the call site before deciding), raise `GatewayUnknownModelError(model_name=..., source=gateway_config_source)` when a referenced gateway model isn't in `gateway_config.model_specs`. Message branches on `source`.
- [x] **3.4** Update agent CLI error mapping in `pipelex/cli/agent_cli/commands/agent_output.py` (`AGENT_ERROR_HINTS`, `AGENT_ERROR_DOMAINS`) for `RemoteConfigUnavailableError` and `GatewayUnknownModelError`. Plumb the structured `warnings` field into the `agent_success(...)` envelope so machine consumers see `[{"type": "RemoteConfigStale", "cached_at": "..."}]` when source is cached.
- [x] **3.5** `make agent-check` clean. Tests green.

🛑 **CHECKPOINT 3** — Stale operation is safe, model membership is enforced. Cold-start safe.

---

## Phase 4 — Cache priming at init (TDD)

**Goal:** when `pipelex init` (or the agent-cli equivalent) completes the gateway terms acceptance flow, attempt one fetch and persist the cache. If offline at init time, log a warning and continue — cache stays empty, user has been told.

- [x] **4.1** Failing tests in `tests/integration/pipelex/cli/commands/init/test_cache_priming.py` with `TestCachePriming`:
  - `test_init_primes_cache_when_online` — run init flow with gateway enabled + httpx mocked to succeed → cache file present and readable afterwards.
  - `test_init_warns_when_offline` — same flow but httpx mocked to fail → init completes (no crash), cache file not present, warning printed to console.
  - `test_init_skips_priming_when_gateway_disabled` — gateway disabled in backends → no fetch attempted, no cache written.
  - `test_init_does_not_double_prime` — if cache already exists and is fresh, init can still refresh it (this is fine; assert the file was rewritten).
- [x] **4.2** Implement priming hook: in `pipelex/cli/commands/init/command.py`, after `_check_gateway_terms_if_needed` has accepted terms and gateway remains enabled, call a new helper `prime_remote_config_cache(console)` that calls `RemoteConfigFetcher.fetch_remote_config()` inside a try/except limited to `RemoteConfigUnavailableError`, `RemoteConfigFetchError`, and `RemoteConfigValidationError`. On unavailable/fetch-error: log a clear yellow warning; on validation error: re-raise (server schema break is fatal, and we control the server). **Never `except Exception`.**
- [x] **4.3** Mirror the same hook into the agent CLI init path (`pipelex/cli/agent_cli/commands/init_cmd.py`) so machine clients also prime.
- [x] **4.4** `make agent-check` clean. Tests green.

🛑 **CHECKPOINT 4** — Cache lifecycle complete. Cold-start safe.

---

## Phase 5 — E2E with real `.mthds` bundles

**Goal:** exercise the full surface that the codex-sandbox handoff doc describes (`mthds-agent run bundle ... --dry-run --mock-inputs`) through subprocess invocations.

- [x] **5.1** Create `tests/e2e/data/offline_mode/` with three minimal bundles:
  - `byok_simple/` — references a backend model that does **not** require the gateway (e.g. ollama or anthropic). All `.mthds` files necessary to validate, plus an `inputs.json` shape for `--mock-inputs`.
  - `gateway_known_model/` — references a gateway model that exists in the test fixture remote config.
  - `gateway_unknown_model/` — references a gateway model that does **not** exist in the test fixture remote config.
- [x] **5.2** Add a one-line indirection in `pipelex/system/pipelex_service/pipelex_details.py`: `REMOTE_CONFIG_URL` reads from the `PIPELEX_REMOTE_CONFIG_URL` env var if set, else uses the hard-coded production URL. This is a **legitimate config knob** (useful for testing/staging), not a test backdoor. Failing tests in `tests/e2e/agent_cli/test_offline_run_dry.py` with `TestOfflineDryRun`. Mark `@pytest.mark.asyncio(loop_scope="class")` if any tests are async. Each test:
  - Invokes the CLI via `subprocess.run([".venv/bin/pipelex-agent", "run", "bundle", str(bundle_dir), "--dry-run", "--mock-inputs"], ...)` (the CLI binary is `pipelex-agent`, not `mthds-agent`).
  - Uses a `monkeypatch`-style fixture to point `HOME` (and therefore `~/.pipelex/cache/`) at a tmp path, so cache state is controlled per-test.
  - Sets `PIPELEX_REMOTE_CONFIG_URL=http://127.0.0.1:1/` (a reserved-port unreachable URL) to simulate offline. Real `httpx`, real `ConnectError`, no production-code-aware-of-tests.
- [x] **5.3** Test cases:
  - `test_byok_offline_succeeds` — gateway disabled (test bundle ships with `backends.toml` that has gateway disabled), no network, no cache → exit 0, structured success JSON.
  - `test_gateway_known_with_cache_succeeds_offline` — gateway enabled, no network, cache primed → exit 0, success JSON includes a `warnings` array with `{"type": "RemoteConfigStale", ...}`.
  - `test_gateway_unknown_with_cache_fails_with_clear_error` — exit nonzero, the unknown handle surfaces in the JSON envelope. Implementation note: pinning `error_type == "GatewayUnknownModelError"` would require an extra deck override to make the membership check fire (the bundle's pipe-level model reference fails at the pipe-operator layer instead). The test asserts the handle is visible without locking the error_type, leaving room for both failure paths.
  - `test_gateway_no_cache_no_network_fails_with_unavailable` — exit nonzero, `error_type == "RemoteConfigUnavailableError"`, message references priming via `pipelex init`.
- [x] **5.4** `make agent-check` clean. Tests green.

🛑 **CHECKPOINT 5** — End-to-end behaviour validated against the exact surface the codex-sandbox doc exercised. Cold-start safe.

---

## Phase 6 — User-facing polish

- [ ] **6.1** Update `pipelex/cli/agent_cli/commands/agent_output.py`:
  - Add `AGENT_ERROR_HINTS` entries for `RemoteConfigUnavailableError` and `GatewayUnknownModelError`.
  - Add `AGENT_ERROR_DOMAINS` entries for both.
  - Keep the existing `RemoteConfigFetchError` and `RemoteConfigValidationError` hints intact.
- [ ] **6.2** Update `pipelex/cli/error_handlers.py` for the Rich CLI surface: add handlers for `RemoteConfigUnavailableError` and `GatewayUnknownModelError` mirroring the agent-cli hints. Keep existing `RemoteConfigFetchError`/`RemoteConfigValidationError` handlers.
- [ ] **6.3** Update relevant CLAUDE.md sections:
  - `pipelex/cli/agent_cli/CLAUDE.md` if error classes are mentioned.
  - `pipelex/system/pipelex_service/CLAUDE.md` if it exists; create a short note if not (only if there's already a convention for service-level docs).
- [ ] **6.4** Add a `## [Unreleased]` entry to `CHANGELOG.md` summarising the user-visible behaviour change (offline support + new error types + new warning).

> **Deferred from this PR:** Phase 6.3-old (`pipelex doctor` cache-age reporting) and Phase 6.6-old (cross-repo `mthds-plugins/wip/codex-sandbox-escalation.md` update). See "Deferred follow-ups" at the bottom of this file.

🛑 **CHECKPOINT 6** — User-facing surface complete. Cold-start safe.

---

## Phase 7 — Final verification

- [ ] **7.1** `make agent-check` clean.
- [ ] **7.2** `make agent-test` clean.
- [ ] **7.3** Manually reproduce all scenarios from the behaviour matrix:
  - BYOK offline `mthds-agent run bundle ... --dry-run --mock-inputs` → success.
  - Gateway online, no cache → success, cache written.
  - Gateway offline, cache present → success with stale warning.
  - Gateway offline, no cache → clear `RemoteConfigUnavailableError`.
  - Bundle references unknown gateway model → clear `GatewayUnknownModelError`.
  - `pipelex-dev update-gateway-models` offline → clear refusal (no stale docs written).
- [ ] **7.4** Squash-friendly commit history; PR description references the codex-sandbox-escalation handoff and the deferred follow-ups.

🛑 **CHECKPOINT 7** — Ready for review.

---

## Risk log

- **Caller migration in Phase 2.** Every call site of `fetch_remote_config()` must be updated. If a caller is missed, it'll break at runtime in dev-CLI tooling that's rarely exercised. Grep before declaring 2.4 done. Current known sites are listed in 2.4 — re-run the grep to be sure.
- **Cache poisoning during validation breakage.** We explicitly chose NOT to fall back to cache on `RemoteConfigValidationError`. Since we control the remote config server (`../pipelex-back-office`) AND the URL is versioned, a schema-rejecting payload is a real server-side bug, not an expected operational state. Failing loudly is the desired behaviour. Confirm this design choice survives review.
- **Schema version bumps are coordinated.** The remote-config URL is versioned in `pipelex-back-office`. To change the `RemoteConfig` shape: bump the URL version in back-office AND bump `RemoteConfigCache.SCHEMA_VERSION` in this repo. Old caches return `None` on load (test in 1.1) and re-prime on next online fetch. Document this in the cache module docstring.
- **`is_first_time_backends_setup` semantics.** Phase 4 priming is conditional on terms-accepted-and-gateway-enabled state. The init flow has a few branches; verify priming runs on the **first** init pass, not only on subsequent re-inits.
- **Doc-generator silent staleness was the critical-gap finding.** Phase 2 fixes it via `require_fresh=True`. If you drop that constraint, you reopen the regression.

## Open questions to resolve as we go

- Maximum acceptable cache age before we refuse to use it? **Default: no cap.** Gateway model lists drift slowly; an old cache is better than no cache. Revisit if it bites us.
- Should the agent-cli `init` command auto-prime even without `--gateway`? **No.** Priming only when gateway is selected.

---

## Deferred follow-ups (out of this PR's scope)

Capture as separate work after this lands:

1. **`pipelex doctor` cache reporting.** Extend `doctor` to surface cache presence, age, gateway-enabled-but-missing-cache hint. Pure additive feature; orthogonal to the offline-fix. Was Phase 6.3 in the original plan.
2. **Codex Cloud cache-first short-circuit.** Today `remote_config_fetcher.py:93` returns a dummy unconditionally in Codex Cloud. After this PR ships, change the short-circuit to try cache first and fall back to dummy. Low risk because we already trust the cache.
3. **Cross-repo: `mthds-plugins/wip/codex-sandbox-escalation.md`.** Note that `--dry-run` no longer requires escalation once Pipelex is initialised online once. Lives in a different repo; do as a separate PR there. Was Phase 6.6 in the original plan.
4. **Cache TTL revisit.** Currently uncapped. Re-evaluate once we have telemetry on cache-fallback usage in production.
5. **Schema-version migration runbook.** When `RemoteConfig` shape actually changes, write down the URL-version + `SCHEMA_VERSION` bump procedure. Not needed until the first real schema bump.
6. **`pipelex-agent run bundle --output-dir` flag.** Today the CLI writes `dry_run.json` (and `live_run.json`, graph HTML) next to the input bundle (`_run_core.py:92` derives `output_dir` from the bundle path). That side effect forced Phase 5 to stage each bundle into a tmp dir before invocation, and would also break invocations against a read-only mounted bundle path (the codex-sandbox case). Adding `--output-dir <path>` (and falling back to the current behaviour when unset) would let read-only callers operate without copying. Surfaced in the Phase 5 code review.
7. **E2E test pinning `GatewayUnknownModelError` end-to-end.** Phase 5's `test_gateway_unknown_with_cache_fails_with_clear_error` asserts the unknown handle is visible in the envelope without pinning `error_type`, because the bundle's pipe-level model reference fires `ModelChoiceNotFoundError`/`PipeOperatorModelAvailabilityError` at the pipe-operator layer rather than the deck-level membership check. Phase 3's unit test (`test_gateway_unknown_model.py`) covers the membership check directly; a follow-up E2E with a deck override that points a preset at a missing handle would pin the agent-CLI's `GatewayUnknownModelError` mapping end-to-end. Surfaced in the Phase 5 code review.

---

## Checkpoint status log

<!-- Append a "### Checkpoint N status" block here after each 🛑 CHECKPOINT, capturing what landed, open decisions, and the next checkbox to start with. Keep blocks short; the codebase is authoritative. -->

### Checkpoint 0 status

**Landed:**
- `tests/integration/pipelex/system/pipelex_service/test_offline_baseline.py` — `TestOfflineBaseline` with two passing tests:
  - `test_byok_offline_setup_succeeds_without_fetching_remote_config` — gateway disabled, no network, `fetch_remote_config` and `httpx.get` are asserted to be uncalled.
  - `test_gateway_offline_without_cache_raises_remote_config_fetch_error` — gateway enabled + terms accepted + `httpx.get` raising `ConnectError` raises `RemoteConfigFetchError`. Bypasses the session-scoped cache patch via a module-level capture of the original classmethod.

**Workaround:** The test module overrides the autouse `reset_pipelex_config_fixture` (no eager `Pipelex.make`) and the gateway-offline test explicitly calls `log.reset()` after the expected failure, because `Pipelex.make` does not reset log state when setup raises. This is pre-existing behaviour — flagged for future fix, not in scope here.

**Verification:**
- `make agent-check` → clean.
- `make agent-test` → all green (5253 passed, 2 skipped, 3 xfailed; matches main).

**Next:** Phase 1 — start at **1.1** (failing tests for `RemoteConfigCache` in `tests/unit/system/pipelex_service/test_remote_config_cache.py`).

### Checkpoint 1 status

**Landed:**
- `pipelex/system/pipelex_service/remote_config_cache.py` — `CachedRemoteConfig` (Pydantic) + `RemoteConfigCache` (class with `cache_path()`, `load()`, `store()`). On-disk layout `{schema_version, cached_at, raw_config}`. Atomic writes via `tempfile.NamedTemporaryFile` + `os.replace` (kept explicit `os.replace` with a per-line `# noqa: PTH202`, with cleanup of the tmp file on failure via a `replaced` flag in `finally`). Module constant `CACHE_SCHEMA_VERSION = 1`.
- `tests/unit/pipelex/system/pipelex_service/test_remote_config_cache.py` — 8 tests covering roundtrip, missing-file, corrupted-JSON, wrong-schema-version, parent-dir creation, cache-path location, atomic-write-on-rename-failure, and raw-payload extras preservation.
- `tests/unit/pipelex/system/pipelex_service/conftest.py` — extended the existing `mock_log` autouse fixture to also patch `remote_config_cache.log`, so unit tests don't need a configured Pipelex log stack.

**Decisions:**
- `CachedRemoteConfig.model_config` is `ConfigDict(extra="forbid")` — *not* strict, because we deserialize datetimes from ISO strings.
- The cache module uses `pipelex.log` rather than stdlib `logging` to stay consistent with the rest of the package; tests rely on the module-scoped `mock_log` fixture to assert warnings instead of `caplog`.
- For `test_write_is_atomic`, the test patches `pathlib.Path.replace` (which is what Python uses under the hood after ruff PTH-fixed the call) rather than `os.replace` at module scope.

**Verification:**
- `.venv/bin/pytest tests/unit/pipelex/system/pipelex_service/test_remote_config_cache.py` — 8 passed.
- `make agent-check` — clean.

**Next:** Phase 2 — start at **2.1** (failing tests for `RemoteConfigFetcher.fetch_remote_config` with fallback semantics in `tests/integration/pipelex/system/pipelex_service/test_remote_config_fetcher.py`).

### Checkpoint 2 status

**Landed:**
- `pipelex/system/pipelex_service/exceptions.py` — added `RemoteConfigUnavailableError(PipelexServiceError)` (user-facing offline-mode error: cache path + `pipelex init`/disable-gateway remediation hints) and `RemoteConfigStaleWarning(UserWarning)`. `RemoteConfigFetchError` kept intact as the internal retry-layer exception.
- `pipelex/system/pipelex_service/remote_config_fetcher.py` — full rewrite of the public API. `fetch_remote_config(require_fresh: bool = False) -> RemoteConfigResult` now carries provenance (`source: RemoteConfigSource` = `FRESH` | `CACHED`, plus `cached_at`). On success: validates payload then writes the **raw JSON dict** via `RemoteConfigCache.store(...)`. On `RemoteConfigFetchError`: tries cache (unless `require_fresh=True`), emits `RemoteConfigStaleWarning` on hit, raises `RemoteConfigUnavailableError` chained from the original `RemoteConfigFetchError` on miss. `RemoteConfigValidationError` path untouched — no cache fallback for schema breaks. Codex Cloud short-circuit still returns a dummy result without writing the cache.
- `tests/integration/pipelex/system/pipelex_service/test_remote_config_fetcher.py` — new `TestRemoteConfigFetcher` with 11 tests covering all the matrix entries from the plan: fresh success + cache write, connect-error fallback, HTTP-5xx fallback, both no-cache variants raising `RemoteConfigUnavailableError`, schema-break never falling back, Codex Cloud short-circuit untouched, tenacity recovering after 4 transient failures (no cache fallback triggered), tenacity exhausting all 5 attempts (cache fallback), `require_fresh=True` refusing cache, and a guard that the inner `RemoteConfigFetchError` is chained as `__cause__`.
- Caller migration:
  - `pipelex/pipelex.py:235` — unwraps `result.config`, logs the source.
  - `pipelex/cli/commands/doctor_cmd.py` — unwraps `result.config`; the `except (RemoteConfigFetchError, RemoteConfigValidationError)` became `except (RemoteConfigUnavailableError, RemoteConfigValidationError)`.
  - `pipelex/cli/dev_cli/commands/gateway_models_generator.py` and `preprocess_test_models_cmd.py` — pass `require_fresh=True` (these regenerate committed reference docs and test fixtures; stale cache must never bake in).
  - `tests/conftest.py` — session-level cache shim now returns a `RemoteConfigResult`; signature accepts `require_fresh` and ignores it (intentional — the test session cache exists to avoid network).
  - `tests/unit/pipelex/cogt/models/test_model_deck_references.py` — unwraps `.config`.
  - `tests/unit/pipelex/system/pipelex_service/test_gateway_terms_check.py` — mock now returns a result-shaped object whose `.config` exposes `backend_model_specs` + `aws_region`.
- `tests/integration/pipelex/system/pipelex_service/test_offline_baseline.py` — renamed the gateway-offline test to `test_gateway_offline_without_cache_raises_remote_config_unavailable_error` and isolated `~/.pipelex` per test via the `ConfigLoader.global_config_dir` `PropertyMock` so a developer's real cache can't accidentally satisfy the fallback. The BYOK-offline test is unchanged.
- `pipelex/cli/commands/doctor_cmd.py` — replaced the pre-existing `except Exception as exc:` at the model-check block with the specific exception lineage (`RoutingProfileLibraryNotFoundError`, `InferenceBackendLibraryNotFoundError`, `ModelDeckNotFoundError`, `RoutingProfileDisabledBackendError`, `InferenceBackendLibraryValidationError`, `ModelDeckValidationError`, `InferenceBackendCredentialsError`).

**Decisions:**
- `RemoteConfigResult` is a Pydantic `BaseModel` with `ConfigDict(extra="forbid", strict=True, arbitrary_types_allowed=True)` (matches project convention; the `arbitrary_types_allowed` is needed because `RemoteConfig` is also a `BaseModel`). Carries `config`, `source`, `cached_at` (UTC).
- `RemoteConfigSource` is a `StrEnum` from `pipelex.types` with lowercase values `fresh` / `cached`.
- `RemoteConfigUnavailableError` is built by a helper (`_build_unavailable_error`) and the caller does the `raise ... from fetch_error`. Initial draft had a helper that raised directly; refactored to return-and-raise so pyright doesn't see "unreachable code" at the call site and ruff doesn't complain about `raise AssertionError("unreachable")`.
- `datetime` import in the fetcher is annotated `# noqa: TC003` — Pydantic v2 resolves annotations at runtime even with `from __future__ import annotations`, so it cannot be moved into the `TYPE_CHECKING` block.

**Verification:**
- `make agent-check` — clean (ruff fix-imports, ruff format, plxt fmt, ruff lint, plxt lint, pyright, mypy all green).
- Targeted: `.venv/bin/pytest -n auto -m "..." tests/unit/pipelex/system/ tests/integration/pipelex/system/` → 110 passed; same flags on `tests/unit/pipelex/cli/ tests/integration/pipelex/cli/ tests/unit/pipelex/cogt/ tests/integration/pipelex/cogt/` → 1006 passed.
- `make agent-test` — full suite green.

**Next:** Phase 3 — start at **3.1** (failing tests for `GatewayUnknownModelError` in `tests/integration/pipelex/cogt/model_backends/test_gateway_unknown_model.py`).

### Checkpoint 3 status

**Landed:**
- `pipelex/cogt/exceptions.py` — added `GatewayUnknownModelError(CogtError)` with `error_category=CONFIGURATION`. Carries `model_name: str` and `source: RemoteConfigSource`. Message branches on source via exhaustive match: `FRESH` → "gateway no longer offers it / check name / disable gateway"; `CACHED` → "cache may be stale, run `pipelex init` while online". Imports `RemoteConfigSource` at module level — no circular-import issue since the fetcher module doesn't touch `cogt`.
- `pipelex/cogt/models/model_manager_abstract.py` — added required `gateway_config_source: RemoteConfigSource | None` parameter to the abstract `setup()`.
- `pipelex/cogt/models/model_manager.py` — implementation of the membership check:
  - `setup()` now accepts `gateway_config_source` and calls `_enforce_gateway_model_membership` after `build_deck`.
  - `_enforce_gateway_model_membership(gateway_config, gateway_config_source)` — no-op when either is `None` (gateway not live). Otherwise iterates `_collect_deck_referenced_handles(deck)`, resolves each through `_resolve_terminal_handle` (walks aliases + first-element of waterfalls), and raises `GatewayUnknownModelError(model_name=terminal, source=gateway_config_source)` when the terminal handle is missing from both `deck.inference_models` AND `gateway_config.model_specs` (defaults key skipped).
  - `_collect_deck_referenced_handles` covers preset models (LLM/Extract/ImgGen/Search) and the two LLM choice defaults. Aliases/waterfalls are intentionally NOT enumerated directly — they're reachable via preset/choice references and the resolver walks them.
  - `_extract_choice_handle` normalises the `LLMModelChoice` union (`LLMSetting | ModelReference | str | None`) to a raw handle string.
  - `_resolve_terminal_handle` does its own model-type → aliases/waterfalls dispatch (instead of calling `ModelDeck._get_aliases_and_waterfalls_for_type`, which is protected) to keep the cogt API surface clean.
- `pipelex/pipelex.py` — captures `gateway_config_source` from the fetch result, passes it through `models_manager.setup(...)`, and tightens the telemetry guard:
  - `is_pipelex_telemetry_enabled = is_pipelex_service_enabled and needs_inference and gateway_config_source != RemoteConfigSource.CACHED` (stale config implies stale model identities; phoning home then would pollute metrics).
  - Re-emits `RemoteConfigStaleWarning` at setup time even when the fetcher itself didn't (the session-cached fetcher in `tests/conftest.py` swaps in a wrapper that doesn't warn — re-emitting here makes provenance visible regardless of how the result reached us).
  - Dummy remote config path (`needs_model_specs=False`) gets `source=FRESH` so the gateway-membership check is silent in that branch (model_specs is empty there).
- `pipelex/cli/commands/doctor_cmd.py` — propagates `gateway_config_source` from the fetch result through `models_manager.setup(...)`.
- `pipelex/cli/agent_cli/commands/agent_output.py`:
  - New module-level capture buffer + `record_setup_warning(...)` / `consume_setup_warnings()` helpers.
  - `agent_success(...)` drains the buffer into a top-level `warnings` array on the JSON envelope (appending to any caller-supplied list).
  - Added `AGENT_ERROR_HINTS` and `AGENT_ERROR_DOMAINS` entries for `RemoteConfigUnavailableError` and `GatewayUnknownModelError`. Existing `RemoteConfigFetchError` and `RemoteConfigValidationError` hints untouched.
- `pipelex/cli/agent_cli/commands/agent_cli_factory.py`:
  - Wraps `Pipelex.make` in `warnings.catch_warnings(record=True)` and records every `RemoteConfigStaleWarning` as `{"type": "RemoteConfigStale", "message": "..."}` via `record_setup_warning(...)`. The next `agent_success` call surfaces it on the envelope.
  - New `except` clauses for `RemoteConfigUnavailableError` and `GatewayUnknownModelError`; the latter exposes `model_name` and `source` on the error JSON.

**Tests:**
- `tests/integration/pipelex/cogt/model_backends/test_gateway_unknown_model.py` — `TestGatewayUnknownModel` with three tests covering the happy path (default cached gateway has all referenced handles), fresh-source missing handle, and cached-source missing handle (asserts the message hints at `pipelex init`).
- `tests/integration/pipelex/system/pipelex_service/test_setup_with_cache.py` — `TestSetupWithCache` with four tests: dry-run with primed cache (warning emitted), dry-run with cold cache (`RemoteConfigUnavailableError`), telemetry-downgrade-to-no-op when source is cached even with `needs_inference=True`, and the BYOK-offline regression guard (gateway disabled → `fetch_remote_config` never called).

**Decisions:**
- `GatewayConfig` stays `extra="forbid"` and source-free. Provenance flows through `ModelManager.setup(gateway_config_source=...)` rather than being baked into the value object.
- The membership check runs at the end of `ModelManager.setup` (not only at `validate_model_deck` time), so even `needs_inference=False, needs_model_specs=True` dry-run flows surface gateway-spec mismatches. This is necessary because the default `missing_presets_reaction = "log"` would otherwise swallow the failure silently.
- `_enforce_gateway_model_membership` skips already-resolved handles (i.e. ones that ended up in `deck.inference_models`). This means the production happy path is silent even when the gateway has every standard model.
- We did NOT extend `ModelDeck._get_aliases_and_waterfalls_for_type` to public access — the resolver re-does the dispatch locally to keep the deck's invariants encapsulated.
- The structured `warnings` envelope is keyed `type=RemoteConfigStale`; the `cached_at` field will be added once we propagate the timestamp through the warning payload (currently the warning message has it inline; deferred to a follow-up if a structured field becomes necessary for downstream consumers).
- Telemetry is downgraded to no-op (rather than to a "stale" variant) when the source is cached. Stricter than the original plan's "is_pipelex_telemetry_enabled stays False" wording — current implementation makes the downgrade explicit in `pipelex.py` so the existing `TelemetryFactory.make_telemetry_manager(is_pipelex_telemetry_enabled=False, ...)` path returns the no-op directly.

**Verification:**
- Targeted: `.venv/bin/pytest -n auto -m "not pipelex_api" tests/integration/pipelex/system/pipelex_service/ tests/unit/pipelex/system/` → 112 passed.
- Targeted: `.venv/bin/pytest -n auto -m "not pipelex_api" tests/integration/pipelex/cogt/model_backends/test_gateway_unknown_model.py` → 3 passed.
- Targeted: `.venv/bin/pytest -n auto -m "not pipelex_api" tests/integration/pipelex/system/pipelex_service/test_setup_with_cache.py` → 4 passed.
- `make agent-check` — clean (ruff + plxt + pyright + mypy all green).
- `make agent-test` — full suite green.

**Next:** Phase 4 — start at **4.1** (failing tests for cache priming in `tests/integration/pipelex/cli/commands/init/test_cache_priming.py`).

### Checkpoint 4 status

**Landed:**
- `pipelex/cli/commands/init/command.py`:
  - New `CachePrimingResult` Pydantic model (`extra="forbid", strict=True`) with `primed: bool` and `error_message: str | None`.
  - New pure-logic helper `attempt_prime_remote_config_cache()` — checks gateway enabled + terms accepted, calls `RemoteConfigFetcher.fetch_remote_config()`, returns a `CachePrimingResult`. Catches only `RemoteConfigUnavailableError` and `RemoteConfigFetchError`; `RemoteConfigValidationError` propagates (server-side schema breaks must surface — we control the back-office).
  - Interactive wrapper `prime_remote_config_cache(console)` — calls the pure helper and emits a yellow Rich warning when a fetch was attempted and failed; otherwise silent.
  - `execute_initialization(...)` now calls `prime_remote_config_cache(console)` as Step 5, after telemetry setup. No-op for BYOK/declined-terms paths, so unconditional call is safe.
- `pipelex/cli/agent_cli/commands/init_cmd.py`:
  - Calls `attempt_prime_remote_config_cache()` after `update_inference_setup_completed(...)`.
  - The `agent_success(...)` envelope now includes `cache_primed: bool` and (when applicable) `cache_priming_error: str`. Machine consumers can branch on these without parsing log output.
- `tests/integration/pipelex/cli/commands/init/test_cache_priming.py` — `TestCachePriming` with 4 tests covering the matrix: primes when online, warns when offline (no crash, no cache written, yellow warning emitted), skips when gateway disabled (no fetch + no cache), and overwrites an existing cache when refreshing online.

**Decisions:**
- Split the helper into a pure-logic `attempt_prime_remote_config_cache()` + an interactive `prime_remote_config_cache(console)` wrapper. The split lets the agent CLI surface structured fields (`cache_primed`, `cache_priming_error`) on its JSON envelope while the Rich CLI gets a yellow warning. The plan's original sketch only described the interactive wrapper; the agent CLI mirror needed the pure variant.
- Priming runs unconditionally at the end of `execute_initialization`. The helper itself short-circuits when gateway is disabled or terms not accepted, so wrapping the call in `if PipelexBackend.GATEWAY in selected_backend_keys:` at the call site would be redundant double-checking. The internal short-circuit also covers the agent CLI mirror cleanly.
- The skipped state (`primed=False, error_message=None`) is intentionally indistinguishable from "no gateway/no terms" — both surface the same `cache_primed: false` on the agent envelope. Consumers that care can check `backends_enabled` or read `pipelex_service.toml` directly.
- No `--no-prime` opt-out flag for now. If priming ever becomes a real problem at init time (slow network, captive portals), revisit; today the helper warns and continues so it can't block init.
- `attempt_prime_remote_config_cache` passes ``require_fresh=True`` to the fetcher. Without it, an offline fetch with a stale cache on disk would silently return ``source=CACHED`` and the helper would falsely report ``primed=True`` (no new write happened). With ``require_fresh=True``, the offline-with-stale-cache path raises ``RemoteConfigUnavailableError`` → we surface it as ``error_message`` and the existing cache file is left intact. Caught in code review post-Phase 4; `test_init_warns_when_offline_with_stale_cache_present` pins the regression.

**Verification:**
- `.venv/bin/pytest tests/integration/pipelex/cli/commands/init/test_cache_priming.py` — 5 passed.
- Targeted: `.venv/bin/pytest -n auto -m "..." tests/unit/pipelex/cli/ tests/integration/pipelex/cli/ tests/unit/pipelex/system/ tests/integration/pipelex/system/` → 429 passed.
- `make agent-check` — clean (ruff + plxt + pyright + mypy all green).
- `make agent-test` — full suite green.

**Next:** Phase 5 — start at **5.1** (create `tests/e2e/data/offline_mode/` bundles for `byok_simple`, `gateway_known_model`, `gateway_unknown_model`).

### Checkpoint 5 status

**Landed:**
- `pipelex/system/pipelex_service/pipelex_details.py` — replaced the class-level `REMOTE_CONFIG_URL` constant with a `remote_config_url()` classmethod that reads `PIPELEX_REMOTE_CONFIG_URL` from the environment when set, else falls back to the production URL. New `_DEFAULT_REMOTE_CONFIG_URL` module constant + `REMOTE_CONFIG_URL_ENV_VAR` name; the underlying call site in `remote_config_fetcher.py:206` now calls the method.
- `tests/e2e/data/offline_mode/{byok_simple,gateway_known_model,gateway_unknown_model}/<name>.mthds` — minimal `PipeLLM` bundles, each referencing one handle: `claude-4.5-haiku` (BYOK via anthropic), `gpt-4o-mini` (known gateway handle), `gpt-future-fake-99` (deliberately absent from the cached payload). Prompts use the inline `$topic.text` sigil (not `@`, which produces tag-wrapped block content and is invalid on the same line as other text).
- `tests/e2e/agent_cli/conftest.py` — new hermetic-home fixtures:
  - `hermetic_home` (returns the tmp `HOME` with a kit-copied `.pipelex/` tree, with `pipelex_service.toml` pre-stamped as terms-accepted + onboarding-complete).
  - `offline_subprocess_env` (subprocess env with `HOME` redirected, `PIPELEX_REMOTE_CONFIG_URL=http://127.0.0.1:1/...`, `RUN_MODE=ci_test`, and dummy values for every `${...}` backend credential variable referenced by the kit's `backends.toml`; under `--dry-run`'s `needs_inference=False` Pipelex is lenient on missing credentials, but the env-var substitution itself still needs the var to exist).
  - Helper functions: `set_gateway_enabled`, `write_active_routing_profile`, `write_remote_config_cache`, `write_pipelex_service_config`. The cache writer hits the real `RemoteConfigCache` JSON schema (matches `CACHE_SCHEMA_VERSION`).
- `tests/e2e/agent_cli/test_offline_run_dry.py` — `TestOfflineDryRun` with four subprocess-based E2E tests. Each test sets `cwd=hermetic_home` so `ConfigLoader.find_project_root` immediately stops at `Path.home()` and the subprocess uses the test's `.pipelex/` instead of walking up to the repo's project-level one.
  - `test_byok_offline_succeeds` — gateway disabled (and routing flipped to `all_anthropic`) → exit 0, no `error` field, `text` payload present.
  - `test_gateway_no_cache_no_network_fails_with_unavailable` — gateway enabled, no cache → `error_type == "RemoteConfigUnavailableError"` with `pipelex init` in the remediation message.
  - `test_gateway_known_with_cache_succeeds_offline` — gateway enabled, cache primed with a comprehensive payload covering every kit-deck terminal handle (LLM, img-gen, extract, search) → exit 0, the `warnings` array surfaces `{"type": "RemoteConfigStale", ...}`. The "comprehensive payload" is critical: the gateway membership check iterates every preset/choice terminal across all model-type decks, and any missing handle (e.g. `azure-document-intelligence` for the default extract preset) raises `GatewayUnknownModelError` at setup time even when the bundle never touches that model.
  - `test_gateway_unknown_with_cache_fails_with_clear_error` — bundle pipe references `gpt-future-fake-99` (absent from the cache). The test asserts a non-zero exit and the unknown handle visible somewhere in the JSON envelope without pinning `error_type`. In practice this fires as `ModelChoiceNotFoundError` or `PipeOperatorModelAvailabilityError` at the pipe-operator layer rather than `GatewayUnknownModelError`, because the kit deck doesn't reference the fake handle and our membership check only iterates deck-level presets/choices.

**Decisions:**
- `cwd=hermetic_home` instead of `cwd=tmp_path/some_subdir` was deliberate. With `HOME=tmp_path` and `cwd=tmp_path`, `find_project_root` returns `None` immediately (the loop hits the home guard on iteration 0) so the project-config-dir lookup short-circuits to the hermetic global dir. Any other cwd choice risks walking up to a sibling project marker file in the temp tree.
- The `gateway_unknown_model` test doesn't pin the error_type because making the membership check fire from a `.mthds` bundle would require shipping a custom deck override that points a preset at the fake handle. That's worth doing in a follow-up but adds churn here without changing the user-facing contract — what we promise is "the unknown handle surfaces in a structured error", and the test asserts exactly that.
- The cached `backend_model_specs` payload uses minimal valid spec bodies (`sdk` + `model_type` + a couple of inputs/outputs). Larger spec fields like cost/latency/max-tokens are optional in `InferenceModelSpecBlueprint` and elided to keep the fixture compact.
- Subprocess env explicitly does NOT inherit the parent process env. The dict is built from scratch and includes `PATH=/usr/bin:/bin:/usr/local/bin`. This prevents developer-machine env vars (e.g. a real `ANTHROPIC_API_KEY`, a real `HOME`) from leaking in and making the test environment non-hermetic. Side effect: if a future test needs more env, it has to be added explicitly to `offline_subprocess_env`.
- `subprocess` import gets a `# noqa: S404` because the bandit rule flags any use of the module, but we genuinely want to spawn the real CLI binary for E2E coverage. The `S603` noqa on the actual `subprocess.run` call covers the same concern at the call site.
- Renamed `PipelexDetails.REMOTE_CONFIG_URL` (class constant) to `PipelexDetails.remote_config_url()` (classmethod). A `@classmethod @property` would have been more drop-in but is deprecated in Python 3.11 and removed in 3.13; a method is the safe substitute.

**Verification:**
- `.venv/bin/pytest tests/e2e/agent_cli/test_offline_run_dry.py` — 4 passed (~50s wall clock; each test spawns one subprocess invocation of `pipelex-agent`).
- Targeted: `.venv/bin/pytest -n auto -m "not pipelex_api" tests/unit/pipelex/system/ tests/integration/pipelex/system/ tests/unit/pipelex/cli/ tests/integration/pipelex/cli/` — 429 passed.
- `make agent-check` — clean (ruff + plxt + pyright + mypy all green).

**Next:** Phase 6 — start at **6.1** (update `agent_output.py` `AGENT_ERROR_HINTS`/`AGENT_ERROR_DOMAINS` for new error types).
