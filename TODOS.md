# Master plan — Provider plugins: storage & secrets

Status: **Phase 1 DONE + Checkpoint 1 CLEARED.** Branch: `feature/More-plugins-2` (worktree `/Users/lchoquel/repos/Pipelex/_plugins`). **Nothing pushed** (no upstream). This file is the **conductor**; the granular per-seam procedures live in linked docs and should not be duplicated here.

Commits on the branch (tip → base):

- `977c73811` — docs: this plan + Phase 1 checkpoint bookkeeping ← **current HEAD**
- `58961848a` — fix: contract.py v3 comment (Checkpoint-1 review triage)
- `8268ff08f` — feat: storage provider → config-selected plugin seam (**Phase 1 code — the review target**)
- `04434f785` — branch base (release v0.37.0 merge). Whole-branch diff for the final Checkpoint 5 = `git diff 04434f785..HEAD`.

**Cold-start (resume here):** Storage seam (storage plan Phases 1–3) is landed + reviewed. **Next action = Phase 2** (storage tests + docs): unit `StorageProviderRegistry` hit/miss (`UnknownStorageMethodError`) + duplicate fail-loud via `_add`; parametrized boot per built-in `method` (s3/gcp `MissingDependencyError` only when *selected* with SDK absent); an external test-plugin integration test (entry-point discovered, selectable via config — mirror the inference external-plugin harness); new `docs/under-the-hood/storage-provider-plugins.md` + mkdocs nav; CHANGELOG `[Unreleased]` (breaking `PLUGIN_API_VERSION` 2→3). Checkpoint 2 gate = **full `make agent-test`** (test phase). The secrets vertical (Phases 3–4) and the W-A `build_registrar` boot move are untouched. Key as-built deviations are under "Phase 1 — as-built" below.

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
- **W-A (secrets boot ordering) — RESOLVED.** The `# needed for gateway check` comment at `pipelex.py:211` is stale; the gateway path is secrets-free. Move the pure `build_registrar(config=get_config())` call up (after line 209, before 212), select secrets from the registry there, delete the hardcoded `EnvSecretsProvider()`. Zero ordering risk. See secrets doc § The wrinkle.

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

- [ ] Unit: `StorageProviderRegistry` hit/miss (`UnknownStorageMethodError`) + duplicate-registration fail-loud via `_add`.
- [ ] Boot (parametrized): each built-in `method` yields the right provider on the hub; s3/gcp arms raise `MissingDependencyError` only when *selected* with the SDK absent, never at registration.
- [ ] Integration: an external test plugin registering a fake `method` (entry-point discovered) is selectable via config — mirror the inference external-plugin test harness.
- [ ] New `docs/under-the-hood/storage-provider-plugins.md` (mirror `orchestrator-plugins.md` structure); mkdocs nav; update any "the plugin seams are …" enumerations.
- [ ] CHANGELOG `[Unreleased]`: "breaking" `PLUGIN_API_VERSION` 2→3; storage is now a plugin seam.

### ⛔ CHECKPOINT 2 — run the protocol above
- [ ] Full `make agent-test` green (+ `agent-check`).
- [ ] Commit SHA recorded here: `__________`
- [ ] Cold-start state updated.
- [ ] Sonnet-5 clean-room `/code-review` on the commit; findings triaged. Outcome: `__________`

---

## Phase 3 — Secrets: mechanism + config + builtin plugin + boot wiring (W-A)
*(Detail: `wip/plugins/secrets-provider-plugin.md` Phases 1–3. W-A is locked — this is a build instruction, not an investigation.)*

- [ ] Registrar: `secrets_providers` dict + `add_secrets_provider(*, method, factory)` via `_add`; `SecretsProviderFactoryFn` alias. *(API already at 3 from Phase 1 — no second bump.)*
- [ ] New `pipelex/plugins/secrets_provider_registry.py`: `SecretsProviderRegistry`.
- [ ] New `UnknownSecretsMethodError` in `pipelex/plugins/exceptions.py`.
- [ ] Hub: `set_/get_secrets_provider_registry` + module accessor.
- [ ] New config `SecretsProviderConfig` (`pipelex/tools/secrets/secrets_config.py`), `method: str = Field(strict=False)`, **no class default** (default lives in TOML). Confirm placement with config owner (sibling of `storage_config` under `pipelex.*`).
- [ ] `pipelex/pipelex.toml`: add `[pipelex.secrets_config]` with `method = "env"`; wire `secrets_config` into the owning config model. Add the same real-valued block to `.pipelex/pipelex.toml` override (never commented out). Run `make tb` after.
- [ ] New `pipelex/plugins/secrets/secrets_plugin.py`: `SecretsPlugin` + `_make_env_secrets_provider(config)` → `EnvSecretsProvider()`.
- [ ] `builtins.py`: register `SecretsPlugin()`; add `"secrets"` to `CORE_UNCONDITIONAL_PLUGIN_NAMES`.
- [ ] **W-A boot edit** (`pipelex.py`): move `build_registrar(config=get_config())` (393-394) up to after line 209 / before 212; keep downstream registry constructions referencing `self._plugin_registrar`; optionally move the `boot_orchestrator` gate (401-403) up for fail-fast. Build + `set_secrets_provider_registry(...)` there.
- [ ] **Delete lines 211-212** (stale `# needed for gateway check` + hardcoded `EnvSecretsProvider()`); replace with registry selection (explicit `setup(secrets_provider=...)` param still wins). Drop the now-unused `EnvSecretsProvider` import from `pipelex.py`.

### ⛔ CHECKPOINT 3 — run the protocol above
- [ ] Gates green (`agent-check` + `tb`; `pipelex plugins list` shows `secrets`; a run with default `method="env"`; `get_secret(...)` still resolves env vars).
- [ ] Commit SHA recorded here: `__________`
- [ ] Cold-start state updated.
- [ ] Sonnet-5 clean-room `/code-review` on the commit; findings triaged (pay attention to the boot-order move — a reviewer with no context is the right check on it). Outcome: `__________`

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
