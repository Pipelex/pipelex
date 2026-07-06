# Master plan — Provider plugins: storage & secrets

Status: **Storage vertical DONE. Secrets vertical Phase 3 CODE DONE + gates green — Checkpoint 3 clean-room review IN FLIGHT.** Branch: `feature/More-plugins-2` (worktree `/Users/lchoquel/repos/Pipelex/_plugins`). **Nothing pushed** (no upstream). This file is the **conductor**; the granular per-seam procedures live in linked docs and should not be duplicated here.

Commits on the branch (newest substantive first; run `git log` for the exact tip — later `docs(plugins)` bookkeeping commits may sit on top):

- `8a0b32668` — feat: secrets provider → config-selected plugin seam (**Phase 3 — the Checkpoint-3 review target**)
- `3940eb7a2` — docs: Phase 2 checkpoint bookkeeping — storage vertical done
- `37a3b72f1` — fix: Phase-2 review triage (doc tense + stronger gcp secret-wiring assert)
- `f08193e81` — test: storage-provider seam tests + docs (**Phase 2**)
- `977c73811` — docs: this plan + Phase 1 checkpoint bookkeeping
- `58961848a` — fix: contract.py v3 comment (Checkpoint-1 review triage)
- `8268ff08f` — feat: storage provider → config-selected plugin seam (**Phase 1 code**)
- `04434f785` — branch base (release v0.37.0 merge). Whole-branch diff for the final Checkpoint 5 = `git diff 04434f785..HEAD`.

**Cold-start (resume here):** The **storage vertical is complete** and **secrets Phase 3 code is committed** (`8a0b32668`) with all gates green (`agent-check`, `tb`, full `agent-test`) and manual smokes passing (`pipelex plugins list` shows `secrets`; default `method="env"`→`EnvSecretsProvider`; unknown token→`UnknownSecretsMethodError`). **The Checkpoint-3 clean-room Sonnet `/code-review` was fanned out on `8a0b32668` but its outcome is NOT yet recorded below — resume by checking that review's findings and triaging them, THEN move to Phase 4** (Secrets tests + docs). Key Phase-3 as-built deviations (esp. the W-A boot-placement refinement) are under "Phase 3 — as-built" below. `PLUGIN_API_VERSION` is already 3 — **no second bump**.

> ⚠️ **Phase-4 heads-up (learned in Phase 2):** the s3/gcp "MissingDependencyError when *selected*" phrasing in the plan is imprecise — the SDK guard is deferred to *use*, not *selection*. Expect the secrets detail doc to carry the same imprecision for SDK-backed secrets providers (Vault/AWS) and treat it the same way (pin *import-light registration*, not a select-time raise). See "Phase 2 — as-built".

**Environment notes for the next session (avoid rediscovering these):**

- **Targeted tests for the storage seam:** `.venv/bin/pytest -n auto -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" -o log_level=WARNING --tb=short -q tests/unit/pipelex/plugins/ tests/unit/pipelex/tools/storage/ tests/integration/pipelex/tools/storage/` (Phase 2 also needs `tests/integration/pipelex/plugins/` for the external-plugin harness). But Checkpoint 2 requires the **full** `make agent-test`.
- **This machine's global `~/.pipelex/pipelex.toml` sets `storage_config.method = "s3"`**, so a plain `Pipelex.make(needs_inference=False)` boot smoke test yields an `S3StorageProvider`, *not* `local` (base + repo `.pipelex/` both say `local`; the global override wins). To smoke a specific method faithfully, pass `config_overrides={"pipelex": {"storage_config": {"method": "local"}}}` in a fresh interpreter. This is a machine/global-config condition, **not** a bug in the seam — don't chase it.
- **Empirically confirmed** (so Phase 2 boot tests can rely on it): `StorageProviderConfig.method: str = Field(strict=False)` coerces a `StrEnum` input to a plain `str`, accepts an external token (e.g. `"azure"`) at parse, and `StrEnum` registry keys resolve against a plain-str `config.method` in dict lookup.

> Replaces the retired cookbook hello-plugin tracker (complete; recoverable in git history).

## What & why (cold-start summary)

Promote the two dependency-injection seams that pass all plugin criteria — **storage provider** and **secrets provider** — to formal `pipelex.plugins` entry-point plugins, so third parties can ship `pipelex-storage-<backend>` / `pipelex-secrets-<backend>` packages selected at deploy time. Chosen after a full boot-audit of DI seams; everything else is already a plugin, a boot-orchestrator-owned hub slot, or a population/config point that should stay one.

**Read these three before starting** (they hold the detailed steps this master plan sequences):

- `wip/plugins/README.md` — the track's shared decisions + boot-audit rationale + the new mechanism.
- `wip/plugins/storage-provider-plugin.md` — storage detail (defines the shared mechanism). **Lands first.**
- `wip/plugins/secrets-provider-plugin.md` — secrets detail (reuses the mechanism; **Decision W already RESOLVED = W-A**).

**The new mechanism (both seams share it):** a *keyed registry + config-selected singleton*. Plugins register N provider factories keyed by an open method token (mirroring `OrchestrationMode`); at boot, core reads one config field (`storage_config.method` / `secrets_config.method`), looks the token up in the registry, and calls the factory to produce the one provider set on the hub. Deliberately **not** a `HubSlot` (those are orchestrator-coupled).

## Locked decisions (do not re-litigate)

- **DX-1 — one API bump.** `PLUGIN_API_VERSION` 2→3, done once on this branch. Both seams land before any release, so external plugins (`pipelex-temporal`, `pipelex-mistralai-workflows`) re-declare `targets_api=3` exactly once. Discovery uses strict-equality, so any menu addition is a breaking bump.
- **DX-2 — unconditional builtins.** `StoragePlugin` and `SecretsPlugin` join `CORE_UNCONDITIONAL_PLUGIN_NAMES` — required infra can't be disabled into a broken boot.
- **DX-3 — external-provider config surface is a follow-up**, not built here (fixed typed sub-configs only in Phase scope).
- **D1 / S1 — open method token.** `method` config fields accept an open `str`, validated at registry lookup (unknown → `UnknownStorageMethodError` / `UnknownSecretsMethodError`), not at parse.
- **W-A (secrets boot ordering) — RESOLVED, refined in Phase 3.** The `# needed for gateway check` comment was stale; the gateway path is secrets-free, so the hardcoded `EnvSecretsProvider()` is gone and secrets is now config-selected from the registry. **Placement deviation (deliberate, see "Phase 3 — as-built"):** the plan's literal W-A said move the `build_registrar` call *above the gateway block* (after line 209 / before old 212). Phase 3 instead placed it *after* the gateway service/terms-check block and *just before the telemetry factory* (secrets' true first consumer). Both satisfy W-A's only hard constraint (secrets resolved before telemetry); the after-the-gate placement additionally preserves precondition-gate-first semantics (an unaccepted-terms / first-run boot fails fast before any discovery work) — a contract two `__new__`-based gateway-terms unit tests encode, which the above-the-gate placement broke.

## Sequencing

Storage vertical (Phases 1–2) → Secrets vertical (Phases 3–4) → Release gating (Phase 5). One coherent commit per phase; a mandatory checkpoint after each.

---

## ⛔ Checkpoint protocol (MANDATORY at every checkpoint — do not skip, do not merge phases)

At each `CHECKPOINT`, the agent **must stop** and do all three, in order:

1. **Verify progress.** Run the gates for the phase and paste real results:
   - Always: `make agent-check` (pyright/ruff/mypy/plxt/keyword-only) + `make tb` (boot sequence — critical whenever config/registry wiring changed).
   - Test phases (2, 4) and the final phase: full `make agent-test`. Intermediate phases may scope to the phase's tests but must still pass `agent-check` + `tb`.
   - If a gate fails: fix before proceeding; a checkpoint is not cleared with a red gate.

2. **Commit, then update this file for cold start.** Commit the phase as one commit. Then edit `TODOS.md` (and/or the linked wip doc) so a brand-new session could resume with no lost context: tick the phase's checkboxes, record the **commit SHA**, any decisions taken or deviations from the linked plan, the current state of the code, and the exact next action. Treat this as a handoff you won't be present to explain.

3. **Fan-out a Sonnet-5 `/code-review` sub-agent — with NO inherited context.** Spawn a **fresh** sub-agent (never a fork) whose entire input is a *pointer to the phase's changes* — the commit SHA / `git diff <base>..HEAD` / the working-tree file list — and nothing else. Do **not** hand it the plan, the rationale, the decisions, or your conclusions; a clean-room review is the point (we want clean solid software, not over-engineering). Spawn template:

   ```
   Agent(
     subagent_type: "general-purpose",   # fresh context — NOT "fork"
     model: "sonnet",                     # Sonnet-5
     description: "code-review phase N",
     prompt: "Run the /code-review skill on the changes in commit <SHA> "
             "(inspect via `git diff <SHA>^..<SHA>` in /Users/lchoquel/repos/Pipelex/_plugins). "
             "Review ONLY those changes. You have no prior context and should assume none. "
             "Focus: correctness bugs, and over-engineering / unnecessary abstraction / "
             "speculative generality. Report findings ranked most-severe first; "
             "if nothing substantive, say so plainly."
   )
   ```

   Then **triage** the findings: apply genuine bug/simplification fixes in a follow-up commit; capture design-tradeoff findings (not silent bugs) as a deferred note under `wip/plugins/` rather than reflexively applying the convenient fix. Record the triage outcome in this file. Only then move to the next phase.

---

## Phase 1 — Storage: mechanism + builtin plugin + boot wiring
*(Detail: `wip/plugins/storage-provider-plugin.md` Phases 1–3. Delivers a working config-selected storage plugin.)*

- [x] `PLUGIN_API_VERSION` 2→3 in `pipelex/plugins/contract.py` (the one batched bump — DX-1).
- [x] Registrar (`pipelex/plugins/registrar.py`): `storage_providers` dict field + `add_storage_provider(*, method, factory)` via the `_add` helper; `StorageProviderFactoryFn` alias.
- [x] New `pipelex/plugins/storage_provider_registry.py`: `StorageProviderRegistry` (mirror `OrchestratorRegistry`: `get_optional`/`get_required`/`has`/`methods`).
- [x] New `UnknownStorageMethodError` in `pipelex/plugins/exceptions.py`.
- [x] Hub (`pipelex/hub.py`): `set_/get_storage_provider_registry` + module accessor.
- [x] New `pipelex/plugins/storage/storage_plugin.py`: `StoragePlugin` (`name="storage"`) + module-level factory closures (`_make_local/_in_memory/_s3/_gcp_storage_provider`) holding the exact bodies moved from the deleted `make_storage_provider_from_config` `match` arms (keep `lazy_validate()`; keep GCP's `get_secrets_provider()` read — legal at the boot apply-point).
- [x] `pipelex/plugins/builtins.py`: register `StoragePlugin()`; add `"storage"` to `CORE_UNCONDITIONAL_PLUGIN_NAMES`.
- [x] Boot (`pipelex.py`): build + `set_storage_provider_registry(...)` alongside the other registries; replace the `make_storage_provider_from_config` block with registry selection (explicit param > `registry.get_required(method=config.method)(config)`).
- [x] Delete `pipelex/tools/storage/storage_provider_factory.py` (grep for other importers first — and re-home them).
- [x] D1: relax `StorageProviderConfig.method` to open `str`.

### Phase 1 — as-built (deviations & decisions, for cold start)

- **Boot ordering (resolved a plan ambiguity).** The old factory ran at `pipelex.py:307-310`, *before* `build_registrar` (~393), but the registry only exists after `build_registrar`. So storage selection **moved down** to sit right beside the other registry constructions (after the 4 `set_*_registry` calls): build `StorageProviderRegistry(plugin_registrar.storage_providers)` → `set_storage_provider_registry` → `if storage_provider is None: select via registry` → `set_storage_provider`. Verified safe: no `get_storage_provider()` consumer runs during `setup()` before that point (all consumers are run-time), and secrets is on the hub (line 306) so the GCP factory's secret read works. This is byte-equivalent to the old factory and forward-compatible with the Phase 3 W-A move (which relocates only the `build_registrar` *call*, not the storage registry construction).
- **`DuplicateStorageProviderError` added** (not in the plan checklist but required by the `_add` `on_duplicate` contract; mirrors `DuplicateOrchestratorError`).
- **D1 blast radius.** `method: StorageMethod` → `method: str = Field(strict=False)` forced a `case _` in `storage_path` + `uri_format` (and the model-validator) because `reportMatchNotExhaustive` fires on open `str`. Empirically confirmed the field coerces a `StrEnum` input to a plain `str` and accepts an external token (e.g. `"azure"`) at parse. Same `case _` added to the two test-side matches (`test_storage_config.py`, `generator_fixtures.py`).
- **Test re-homing.** `test_storage_provider_factory.py` **deleted** (its SUT is gone; Phase 2 adds the registry + parametrized-boot seam tests that supersede it). `generator_fixtures.py` now selects through `get_storage_provider_registry().get_required(...)`. `test_storage_provider_config.py`'s strict-coercion test rewritten to the D1 open-token behavior (`method == "local"` as plain str; `"azure"` accepted at parse).
- **Built-in tokens** registered as the `StorageMethod` enum values (`StrEnum` keys are interchangeable with their plain-str form in dict lookup, so boot's plain-str `config.method` resolves them).

### ⛔ CHECKPOINT 1 — run the protocol above (verify → commit + update → clean-room /code-review → triage)
- [x] Gates green: `make agent-check` (ruff/plxt/pyright/mypy/keyword-only all pass), `make tb` (9 passed), `pipelex plugins list` shows `storage` (builtin, API 3, 4 contributions), boot `method="local"`→`LocalStorageProvider` / `method="in_memory"`→`InMemoryStorageProvider`, unknown token → `UnknownStorageMethodError`. Targeted `tests/unit/pipelex/plugins/ tests/unit+integration/.../tools/storage/` = 1036 passed; re-homed fixture consumers = 4 passed.
- [x] Commit SHA recorded here: `8268ff08f`
- [x] Cold-start state updated in this file.
- [x] Sonnet-5 clean-room `/code-review` fanned out on `8268ff08f`; findings triaged. **Outcome:** review verified correctness (byte-identical factory bodies, safe `StorageMethod→str` D1 relaxation, correct boot ordering, keyword-only compliant, no bare `except`). 3 findings:
  1. *contract.py v3 comment implied secrets registry already exists* → **FIXED** in follow-up `58961848a` (reworded to "pre-reserved / lands in a follow-up").
  2. *storage-selection path has no direct automated test after deleting the factory test* → **deferred to Phase 2 as already planned** (Phase 2 checklist adds registry hit/miss + duplicate + parametrized-boot). Manually smoke-verified this phase.
  3. *`StorageProviderRegistry.get_optional`/`has` have no caller* → **kept (no change).** Confirmed by grep that all sibling read-views (orchestrator/bundle_validator/model_lister) expose the identical shape; `has` is family-wide unused and `get_optional` used by exactly one. It's an established, plan-mandated registry-family convention, not speculative surface — trimming would make storage the odd one out.
  Reviewer also noted a benign boot-ordering nuance: a bad storage config now fails *after* `models_manager.setup()` rather than immediately after secrets (necessary consequence of needing the registrar built first; behavior otherwise byte-equivalent).

---

## Phase 2 — Storage: tests + docs
*(Detail: `wip/plugins/storage-provider-plugin.md` Phases 4–5.)*

- [x] Unit: `StorageProviderRegistry` hit/miss (`UnknownStorageMethodError`) + duplicate-registration fail-loud via `_add`. → `test_storage_provider_registry.py`.
- [x] Built-in factories: each built-in `method` yields the right provider (registry selection); gcp reads its credentials from the hub secrets provider. → `test_storage_plugin.py`. *(Reframed from "parametrized boot" to direct factory-selection — see as-built; the boot-select line is covered end-to-end by the integration test.)*
- [x] Integration: an external test plugin registering a fake `method` (entry-point discovered) is selectable via config, and lands on the hub. → `test_storage_external_plugin.py`.
- [x] Import-light registration pinned: s3/gcp factories register without importing their SDK. → `test_import_light_boot.py` (added `google.cloud.storage` to BLOCKED + assert `storage_providers`).
- [x] New `docs/under-the-hood/storage-provider-plugins.md` (mirrors `orchestrator-plugins.md`); mkdocs nav (both blocks); cross-links from `inference-backend-plugins.md` Related. *(No "the plugin seams are …" enumeration exists to update — grep-verified.)*
- [x] CHANGELOG `[Unreleased]`: "breaking" `PLUGIN_API_VERSION` 2→3; storage is now a plugin seam. *(Added a fresh `[Unreleased]` — none existed, branch base was v0.37.0.)*

### Phase 2 — as-built (deviations & decisions, for cold start)

- **The s3/gcp SDK guard is deferred to *use*, not *selection* (plan text was imprecise).** The plan/detail-doc said "s3/gcp arms raise `MissingDependencyError` only when *selected* with the SDK absent." Not so: `S3StorageProvider.__init__` / `GcpStorageProvider.__init__` only store fields; the `find_spec` guard lives in `_get_session` / `_get_bucket`, invoked inside the I/O methods. So *selecting* (constructing) s3/gcp NEVER raises `MissingDependencyError` even with the SDK absent — the error is deferred to first load/store. The correct invariant Phase 2 pins is therefore **import-light registration** (the s3/gcp factories register without importing their SDK), done by extending `test_import_light_boot.py`. The `MissingDependencyError`-on-use path is already covered by the dedicated `test_{s3,gcp}_storage_provider.py`, so it is not re-tested in the seam tests (avoids redundancy). Both aioboto3 and google-cloud-storage happen to be installed in this dev venv, so an in-process "SDK absent" test would need to mock `find_spec` anyway.
- **Phase-1 latent breakage found + fixed (Phase-1 escapee).** `tests/integration/pipelex/system/test_hub_slot_injection_precedence.py` booted with an empty fake registrar and no explicit `storage_provider`; Phase 1's new selection path (`get_required(method=config.method)`) now rejects that with `UnknownStorageMethodError`. Checkpoint 1 only ran the plugins/storage dirs, not `system/`, so it escaped — the full `make agent-test` at Checkpoint 2 caught it. Fixed by injecting a dependency-free `InMemoryStorageProvider()` in the four boots (this suite tests hub slots, not storage). Grep-verified it was the *only* test with the empty-registrar-boot pattern (`test_plugin_discovery` / `test_import_light_boot` call `build_registrar` directly, never `Pipelex.make`, so they're unaffected).
- **Test layout** (one TestClass per module): registry read-view + duplicate (`test_storage_provider_registry.py`, mirrors `test_bundle_validator_registry.py`); built-in factories + gcp secret-wiring (`test_storage_plugin.py`); integration discovery→selection→hub (`test_storage_external_plugin.py`). Config helpers reused from `tests/unit/pipelex/tools/storage/test_storage_provider_config.py` (`make_{local,in_memory,s3,gcp}_config`) — local construction touches no filesystem (no tmp_path needed).
- **Integration harness** = `mocker.patch("pipelex.plugins.discovery._external_entry_points", return_value=[SimpleNamespace(name=..., load=lambda: FakePluginClass)])` (discovery instantiates a callable/class), keep the real `BUILTIN_PLUGINS`, boot `Pipelex.make(needs_inference=False, config_overrides={"pipelex": {"storage_config": {"method": "test_mem"}}})`, assert `get_storage_provider()` is the fake + registry `.has(method="test_mem")`. An external method token loads fine (the config validator's `case _: pass`). Per-module autouse `reset_pipelex_config_fixture` (teardown-first) overrides the global module fixture (mirror of the two existing `system/` boot-test modules). This is also the harness template for the Phase 4 secrets external-plugin test.
- **GCP secret-wiring assertion (Phase-2 review triage).** The first cut only asserted the secret was *requested*; the clean-room reviewer flagged it didn't assert the *value* flowed. Strengthened via `mocker.patch(..., wraps=GcpStorageProvider)` + `assert_called_once_with(credentials_file_path=fake_secrets.credentials_path, …)` — the repo-idiomatic way (`reportPrivateUsage`/`SLF001` both hard-block a `provider._credentials_file_path` read, so no private access / suppressions).

### ⛔ CHECKPOINT 2 — CLEARED
- [x] Gates green: `make agent-check` (ruff/plxt/pyright 0 errors/mypy/keyword-only), `make tb` (9 passed), **full `make agent-test` (exit 0, "All tests passed")**. Targeted storage-seam + at-risk boot test also green in isolation.
- [x] Commit SHAs: `f08193e81` (Phase 2 code/tests/docs/changelog) + `37a3b72f1` (review triage).
- [x] Cold-start state updated in this file.
- [x] Sonnet clean-room `/code-review` fanned out on `f08193e81`; findings triaged. **Outcome:** 2 findings, **both genuine and applied** in `37a3b72f1`. (1) *High — doc/code contradiction:* the new page reasserted "the same mechanism backs the secrets provider seam" as present tense, but secrets is not yet registry-selected (and commit `58961848a` had just retracted the same claim in `contract.py`) → reworded to planned/future. (2) *Medium — test gap:* the gcp test checked the secret was requested but not that its value reached the provider → added the wraps-ctor `assert_called_once_with` above. Reviewer otherwise verified: no correctness bugs, no over-engineering, mocks faithful to the real contracts, no tautological assertions, no redundancy across the three new files, all doc snippets match source, MkDocs/pytest conventions respected.

---

## Phase 3 — Secrets: mechanism + config + builtin plugin + boot wiring (W-A)
*(Detail: `wip/plugins/secrets-provider-plugin.md` Phases 1–3. W-A is locked — this is a build instruction, not an investigation.)*

- [x] Registrar: `secrets_providers` dict + `add_secrets_provider(*, method, factory)` via `_add`; `SecretsProviderFactoryFn` alias. *(API already at 3 from Phase 1 — no second bump.)*
- [x] New `pipelex/plugins/secrets_provider_registry.py`: `SecretsProviderRegistry`.
- [x] New `UnknownSecretsMethodError` in `pipelex/plugins/exceptions.py`. *(Also added `DuplicateSecretsProviderError` — required by the `_add` `on_duplicate` contract, mirroring storage.)*
- [x] Hub: `set_/get_secrets_provider_registry` + module accessor.
- [x] New config `SecretsProviderConfig` (`pipelex/tools/secrets/secrets_config.py`), `method: str = Field(strict=False)`, **no class default**. Placed as sibling of `storage_config` under `pipelex.*` (single flat model, no `SecretsConfig` subclass needed — secrets has no is_fetch/is_upload analogue).
- [x] `pipelex/pipelex.toml`: added `[pipelex.secrets_config] method = "env"`; wired `secrets_config: SecretsProviderConfig` into the `Pipelex` config model. Same real-valued block added to `.pipelex/pipelex.toml` override. `make tb` green.
- [x] New `pipelex/plugins/secrets/secrets_plugin.py`: `SecretsPlugin` + `_make_env_secrets_provider(config)` → `EnvSecretsProvider()` (unused `config` param carries `# noqa: ARG001`, the plugins-dir convention for a callback-signature-conforming factory).
- [x] `builtins.py`: registered `SecretsPlugin()` in `BUILTIN_PLUGINS`; added `"secrets"` to `CORE_UNCONDITIONAL_PLUGIN_NAMES`.
- [x] **W-A boot edit** (`pipelex.py`): `build_registrar` + boot-orchestrator gate + secrets registry/selection now sit **just before the telemetry factory** (not above the gateway block — see as-built). Downstream registry constructions still reference the same `plugin_registrar`.
- [x] **Deleted** the stale `# needed for gateway check` + hardcoded `EnvSecretsProvider()`; replaced with registry selection (explicit `setup(secrets_provider=...)` still wins). Dropped the now-unused `EnvSecretsProvider` import from `pipelex.py`.

### Phase 3 — as-built (deviations & decisions, for cold start)

- **W-A boot placement refined — after the precondition gate, not above the gateway block (the one real deviation).** The plan's literal W-A said move `build_registrar(config=get_config())` up to *before the gateway service block* (after line 209 / old line 212). Doing exactly that broke two unit tests — `tests/unit/pipelex/system/pipelex_service/test_gateway_terms_check.py::{test_first_run_raises_inference_setup_required, test_needs_inference_true_raises_when_terms_not_accepted}`. Those tests exercise the gateway terms/first-run gate in isolation via `Pipelex.__new__(Pipelex)` (skipping `__init__`, so no config/hub is set) and rely on `setup()` reaching the terms-check `raise` **before** touching `get_config()` / `self.pipelex_hub`. Moving `build_registrar(config=get_config())` above the gate made `setup()` call `get_config()` first → `RuntimeError: Config instance is not set`. **Resolution:** placed the whole plugin-discovery + boot-orchestrator gate + secrets-registry/selection block **after** the gateway service/terms-check block and **immediately before the telemetry factory** — telemetry (`make_telemetry_manager`) is the *true first consumer* of `secrets_provider`, which is W-A's only hard constraint. This is strictly better than the plan's literal placement: the terms/first-run precondition gate fails fast before any discovery work, and no `__new__` test needed changing for the gate. (The boot-orchestrator gate also moved to this spot — still far earlier than its original post-`models_manager.setup` position, so fail-fast is preserved.)
- **`DuplicateSecretsProviderError` added** (not in the plan checklist) — required by the `_add` `on_duplicate` contract; mirrors `DuplicateStorageProviderError` / `DuplicateOrchestratorError`.
- **`SecretsProviderConfig` is a single flat model**, not a base+subclass like storage's `StorageProviderConfig`/`StorageConfig`. Storage's subclass exists only to add `is_fetch_remote_content_enabled`/`is_upload_local_content_enabled`; secrets has no such extra fields, so a lone `SecretsProviderConfig(ConfigModel)` with just `method` is the clean-solid shape (no speculative base).
- **Phase-1 escapee proactively found + fixed (same class as storage's).** `test_hub_slot_injection_precedence.py` boots a fake **empty** registrar (patched into `build_registrar`) and passed an explicit `storage_provider` but no `secrets_provider`; the new secrets selection path (`get_required(method="env")`) rejects the empty registry with `UnknownSecretsMethodError`. Fixed by injecting `EnvSecretsProvider()` in the four boots (+ docstring updated). Grep-verified this was the only `Pipelex.make` boot with a mocked empty/partial registrar (the plugins-dir tests call `build_registrar` directly; `test_storage_external_plugin` keeps the real `BUILTIN_PLUGINS`, so its `env` secrets provider is present). Caught here via the full `make agent-test` rather than escaping to a later checkpoint.
- **The env factory ignores config.** `_make_env_secrets_provider(config)` returns a bare `EnvSecretsProvider()`; the `config` param exists only to conform to `SecretsProviderFactoryFn = Callable[[SecretsProviderConfig], ...]` (an SDK-backed external provider would read its own settings from it). Marked `# noqa: ARG001`, the established plugins-dir convention (see linkup/bedrock/azure_rest workers).

### ⛔ CHECKPOINT 3 — review in flight
- [x] Gates green: `make agent-check` (ruff/plxt/pyright 0 errors/mypy/keyword-only), `make tb` (9 passed), **full `make agent-test` (exit 0, "All tests passed")**. Manual smokes: `pipelex plugins list` shows `secrets` (builtin, API 3, `secrets provider env`); default `method="env"`→`EnvSecretsProvider`; unknown token→`UnknownSecretsMethodError`.
- [x] Commit SHA recorded here: `8a0b32668`
- [x] Cold-start state updated in this file.
- [ ] Sonnet-5 clean-room `/code-review` **fanned out on `8a0b32668`** (fresh general-purpose agent, no context, pointed only at the commit; instructed to scrutinize the boot-order move). **Outcome: PENDING — triage on resume.**

---

## Phase 4 — Secrets: tests + docs
*(Detail: `wip/plugins/secrets-provider-plugin.md` Phases 4–5.)*

- [ ] Unit: `SecretsProviderRegistry` hit/miss (`UnknownSecretsMethodError`) + duplicate fail-loud.
- [ ] Boot: default config yields `EnvSecretsProvider` on the hub; explicit `setup(secrets_provider=...)` overrides.
- [ ] Integration: external test plugin registering a fake secrets `method` is selectable via config.
- [ ] Ordering guard: a boot with a non-env secrets method has secrets on the hub before storage's GCP arm reads it (assert boot order).
- [ ] New `docs/under-the-hood/secrets-provider-plugins.md` (emphasize the lazy optional-dep closure for SDK-backed providers like Vault/AWS); mkdocs nav; update seam enumerations.
- [ ] CHANGELOG `[Unreleased]`: secrets is now a plugin seam.

### ⛔ CHECKPOINT 4 — run the protocol above
- [ ] Full `make agent-test` green (+ `agent-check`).
- [ ] Commit SHA recorded here: `__________`
- [ ] Cold-start state updated.
- [ ] Sonnet-5 clean-room `/code-review` on the commit; findings triaged. Outcome: `__________`

---

## Phase 5 — Release gating & cross-repo (documentation in this branch; execution is release-gated)

- [ ] Record in the CHANGELOG / release notes: `pipelex-temporal` and `pipelex-mistralai-workflows` must bump `targets_api` to 3 when the pipelex version carrying this lands (they register no provider; the bump is the only change). Do NOT touch those repos here.
- [ ] Confirm the whole branch is one clean sequence of per-phase commits; open the PR to the intended base.

### ⛔ CHECKPOINT 5 (final) — run the protocol above, whole-branch scope
- [ ] Full `make agent-test` + `make agent-check` + `make tb` all green on the final tip.
- [ ] Final Sonnet-5 clean-room `/code-review` over the **whole-branch diff** (`git diff <branch-base>..HEAD`) — a last over-engineering sweep across both seams together. Findings triaged. Outcome: `__________`
- [ ] This file updated to DONE with all SHAs; deferred follow-ups (DX-3 external config passthrough, first real external provider, cookbook example) captured under `wip/plugins/`.

---

## Deferred follow-ups (not in this plan — see wip docs)

- DX-3 external-provider config passthrough (storage D3 / secrets S4).
- First real external provider (e.g. Vault / AWS Secrets Manager) as proof-of-seam — likely a private package if hosted-platform-targeted.
- Cookbook `pipelex-storage-hello` external-plugin example, mirroring the hello-inference-plugin track.
