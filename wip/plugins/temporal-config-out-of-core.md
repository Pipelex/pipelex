# Move Temporal config out of core (fix the core→`temporalio` type-check coupling)

**Status:** planned, not started. **Branch:** `refactor/Plugins-3` (core, worktree `_plugins`) + `main` (worktree-less sibling `pipelex-temporal`). **Priority:** ship-blocker for the plugin-system effort — it falsifies the effort's headline invariant ("core names no integration — not by import, not by string — anywhere").

## The defect

`pipelex/system/configuration/config_temporal.py` lives in **core** but type-imports `from temporalio.common import RetryPolicy` (under `TYPE_CHECKING`, with a runtime `RetryPolicy = Any` placeholder). Core declares **no** `temporalio` dependency anywhere — not runtime, not an extra, not `dev`. So a clean type-check cannot resolve the import:

```
config_temporal.py:15 - error: Import "temporalio.common" could not be resolved (reportMissingImports)
… 13 pyright errors total, + the equivalent mypy import-not-found
```

It only ever passed because both the `_plugins` and `_workflows` venvs carried a **stale** `temporalio 1.24.0` left over from before the Phase 5 Temporal externalization. `make li` (lock + `uv sync --all-extras`) removes it and `make check` fails identically in `_plugins` itself. The merge of `refactor/Plugins-3` into `feature/mistralai-2x-bump` surfaced it because that merge correctly **drops the `temporal` extra** (public-repo rule), and the subsequent clean sync removed `temporalio`.

### Root cause

The plan's **D7** ("Temporal config stays typed in core") plus **Step 0b** (which *relocated* the Temporal config schema *into* core to break the `configs.py → pipelex.temporal` import cycle). That broke the cycle by importing Temporal's whole schema into core instead of inverting the dependency. Now that Temporal is an external plugin (`pipelex-temporal`), its config schema has no business in core.

### Rejected alternative

Adding `temporalio` to core's `dev` extra so the type-only import resolves: re-couples core's dev/CI environment to a SDK we just externalized and leaves the schema in core. Perpetuates exactly the coupling this effort exists to remove. Rejected.

## Decision (locked with the user)

**Move the Temporal config out of core entirely**, mirroring how `backends.toml` / `routing_profiles.toml` already work (separate `.pipelex/` TOML, resolved via `config_manager.resolve_config_file(...)`, parsed by their own subsystem at setup — *not* fields on `PipelexConfig`).

**Activation gate = generic core gate** (chosen over keeping a `--temporal` flag or dropping the flag): replace the temporal-specific `--temporal/--no-temporal` + `temporal_enabled` + `config.temporal.is_enabled` plumbing with a backend-agnostic selector. Core names **no** orchestrator; the plugin matches on its own name.

## Target architecture

The key property: the rich Temporal schema (the one with the `temporalio` import) **never loads in core or in `register`**. It loads only inside the boot thunks and `orchestrator.run` — all in `pipelex-temporal`, at runtime, where `temporalio` is a real dependency.

- **Generic gate in core config:** `PluginsConfig` gains `boot_orchestrator: str | None` (Optional → `= None` in the class def per repo rule; absent from `pipelex.toml`). It means "boot *this process* under the orchestrator plugin of this name" (`None`/any non-matching name = in-process default). This is plugin-system wiring, legitimately core's concern (core owns the orchestrator registry + boot slots) and carries no integration name.
- **`register` gates generically:** the Temporal plugin's `register` claims the boot slots iff `registrar.config.plugins.boot_orchestrator == self.name`. No temporal config read, no I/O, no `temporalio`. The TEMPORAL_* orchestrators are still added unconditionally (they need no config).
- **Rich config self-loads in the plugin:** `pipelex-temporal` ships its own default `temporal.toml`, reads user overrides from `.pipelex/temporal.toml` (layered project/global via `config_manager.resolve_config_file("temporal.toml")`), deep-merges, and parses into its `Temporal` schema — inside the boot thunks (apply-point, I/O fine) and `orchestrator.run` (runtime). The `temporalio` type-import travels with the schema into `pipelex-temporal`.
- **CLI:** `--temporal/--no-temporal` → `--orchestrator TEXT`; `temporal_enabled: bool | None` → `boot_orchestrator: str | None` through `cli_factory` → `Pipelex.setup()`. The override site (`pipelex.py:206-207`) sets `config.plugins.boot_orchestrator` instead of mutating `config.temporal.is_enabled`. `--orchestrator temporal` claims temporal's slots; `--orchestrator direct` (or anything ≠ a boot-orchestrator plugin name) → no claim → in-process. No sentinel needed: the gate is a name match.

## Core footprint (small)

- `configs.py:14` import of `Temporal` + `configs.py:257` `temporal: Temporal` field → removed.
- `pipelex.py:206-207` — the only core code reading `config.temporal` (the override) → rewired to `boot_orchestrator`.
- `--temporal/--no-temporal` flags threaded through: `cli/cli_factory.py`, `cli/commands/validate/{pipe,bundle,method}_cmd.py` + `_validate_core.py`, `cli/commands/run/bundle_cmd.py`, `pipelex.py` setup signatures.
- `[temporal]` TOML blocks in `pipelex/pipelex.toml`, `.pipelex/pipelex.toml`, `.pipelex/pipelex_override.toml`, **and** the kit templates under `pipelex/kit/configs/` (they seed `~/.pipelex`; `make check-config-sync` enforces `.pipelex ↔ kit` parity, so both sides move together). `tracing_config.temporal_dynamodb` is the separate tracing axis and **stays**.
- `config_temporal.py` (the 760-line schema) + the two exceptions it owns (`TemporalConfigError`, `WorkerTaskQueueUnknownError` in `pipelex/system/configuration/exceptions.py`) → moved to `pipelex-temporal`. `pipelex-temporal` already consumes the schema from core (its `temporal_connect`/`temporal_tasks`/`task_manager`/`temporal_task_manager`/`temporal_manager`/`namespace_check` import `pipelex.system.configuration.config_temporal`), so those imports become local.

## Plan (phased, cross-repo)

### Phase 1 — `pipelex-temporal` owns its config (additive, no core change yet)

- Add `config_temporal.py` to `pipelex_temporal/` (copy from core; the `temporalio` type-import now sits where `temporalio` is a real dep). Move `TemporalConfigError` + `WorkerTaskQueueUnknownError` into `pipelex_temporal`'s own `exceptions.py`.
- Add `pipelex_temporal/temporal.toml` = the default config (the relocated `[temporal]` block), shipped in the wheel.
- Add a config loader (`load_temporal_config() -> Temporal`) using `config_manager.resolve_config_file("temporal.toml")` + the packaged defaults, deep-merged.
- Repoint `pipelex-temporal`'s internal imports to its own `config_temporal` module.
- Keep the plugin reading core config for the gate *temporarily* (still `is_enabled`) so this phase stays green standalone.

🛑 **Checkpoint 1** — pipelex-temporal `make agent-check` + `make agent-test` green with its own schema (core still has its copy + field; nothing broken).

### Phase 2 — core sheds Temporal config + the generic gate (the breaking, atomic change)

- `PluginsConfig` += `boot_orchestrator: str | None = None`.
- Remove `temporal: Temporal` field + the `config_temporal` import from `configs.py`.
- Delete core `config_temporal.py` + the two exceptions from `pipelex/system/configuration/exceptions.py`.
- Remove every `[temporal]` block from core TOMLs (base + `.pipelex/*` + kit configs); keep `tracing_config.temporal_dynamodb`. Run `make check-config-sync`.
- Rewire CLI: `--temporal/--no-temporal` → `--orchestrator`; `temporal_enabled` → `boot_orchestrator` through `cli_factory` + `Pipelex.setup()`; the `pipelex.py` override site sets `config.plugins.boot_orchestrator`.
- Update the Temporal plugin `register` gate → `registrar.config.plugins.boot_orchestrator == self.name`; boot thunks + orchestrators self-load the rich config via the Phase-1 loader.
- Regenerate error pages (`make gep`) — the two relocated exceptions leave core's error catalog.

🛑 **Checkpoint 2** — **core `make check` pyright/mypy CLEAN (the `temporalio` import is gone from core), `make tb` green, `make agent-test` green**; `pipelex-temporal` `make agent-check` + `make agent-test` green (editable core). This is the gate that proves the defect fixed.

### Phase 3 — re-merge + re-sync

- Re-merge `refactor/Plugins-3` → `feature/mistralai-2x-bump` (worktree `_workflows`); the only expected conflict is `CHANGELOG.md` (union, `[Unreleased]` on top). `uv sync --all-extras` in `_workflows`. `make tb` + `make agent-check` + `make agent-test`.
- Then resume the original task (make `pipelex-mistralai-workflows` a discoverable `pipelex.plugins` entry-point plugin) against the corrected base.

## Risks / watch-items

- **`extra="forbid"` is unforgiving:** a single missed `[temporal]` key in any loaded TOML hard-fails boot. The TOML sweep (base + `.pipelex/*` + kit + tests) must be exhaustive; `make tb` is the fast catch.
- **Cross-repo ordering:** `pipelex-temporal` must have its own schema (Phase 1) before core deletes its copy (Phase 2), or the editable `pipelex-temporal` build breaks. Verify both green together under the editable pin before committing either.
- **Tests in core that assert `--temporal` / `config.temporal`:** update to `--orchestrator` / `boot_orchestrator`. Tests that reference the Temporal *schema* should already live in `pipelex-temporal`.

## Deferred (out of scope, follow-ups)

- **Tracing naming axis:** `TracingBackend.TEMPORAL_DYNAMODB`, `TemporalDynamoDBTracingConfig`, `tracing_config.temporal_dynamodb` are string/naming couplings (no `temporalio` import, don't break the build). Whether a fully-externalized Temporal should still have core's tracing system name a `temporal_dynamodb` backend is a separate question — leave for later.
- **Exact `--orchestrator` vocabulary** for force-in-process (`direct` vs `none`) — settle during Phase 2; the gate is a name-match either way.
- **Whether other (inference) plugin config should also leave `PipelexConfig`** — user explicitly scoped this pass to Temporal only.
