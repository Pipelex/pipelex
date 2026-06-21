# Move Temporal config out of core (fix the core→`temporalio` type-check coupling)

**Status:** **Phases 1, 2 & 3 DONE + verified green + COMMITTED (not pushed).** Core (Plugins-3) commit `eaa671d10` on `refactor/Plugins-3` (worktree `_plugins`); pipelex-temporal commit `187e846` on `refactor/own-temporal-config`. Phase 3 (re-merge into `feature/mistralai-2x-bump`, worktree `_workflows`) landed as merge `a34ca9a7e` + follow-up `8da150c43` (stale-test removal); the relocated test is pipelex-temporal `877c85b`. **Priority:** ship-blocker for the plugin-system effort — it falsifies the effort's headline invariant ("core names no integration — not by import, not by string — anywhere").

> **As-built summary (see the "As-built" section at the bottom for detail).** The `temporalio` type-coupling is gone from core: `config_temporal.py` deleted, no `temporal` field on `PipelexConfig`, core `make agent-check` (pyright + mypy) clean, `make tb` / `make agent-test` green, `make gep` + `make check-config-sync` green. `pipelex-temporal` now owns the rich config (`config_temporal.py` + `temporal.toml` + `load_temporal_config` + `temporal_hub` cache) and gates on the generic core `plugins.boot_orchestrator` selector; its `make agent-check` + `make agent-test` are green against the editable new core. Both CLIs smoke clean (`--temporal/--no-temporal` → `--orchestrator`).

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
- **Exact `--orchestrator` vocabulary** for force-in-process (`direct` vs `none`) — settled: the flag takes any plugin name; `--orchestrator temporal` boots Temporal, omitting it (or any non-boot-orchestrator name) runs in-process. No sentinel keyword is reserved.
- **Whether other (inference) plugin config should also leave `PipelexConfig`** — user explicitly scoped this pass to Temporal only.

## As-built (Phases 1 & 2 complete, uncommitted)

### What landed

**`pipelex-temporal` now owns the rich Temporal config** (new files):

- `pipelex_temporal/config_temporal.py` — the 760-line schema, relocated from core. The `temporalio.common.RetryPolicy` type-import now sits where `temporalio` is a real dependency. `is_enabled` dropped from the `Temporal` model (the gate moved to core).
- `pipelex_temporal/temporal.toml` — the packaged default (the old core `[temporal]` block, prefix-stripped to root tables, `is_enabled` removed). Shipped in the wheel; loaded as the base layer.
- `pipelex_temporal/temporal_config_loader.py` — `load_temporal_config()`: packaged default deep-merged with an optional `.pipelex/temporal.toml` override (project→global via `config_manager.resolve_config_file`). Mirrors `backends.toml` / `routing_profiles.toml`.
- `pipelex_temporal/temporal_activation.py` — `is_temporal_boot_active()` + `TEMPORAL_PLUGIN_NAME = "temporal"`. The runtime gate (`config.plugins.boot_orchestrator == "temporal"`), replacing the old `config.temporal.is_enabled` guard.
- `temporal_hub` caches the loaded `Temporal` (lazy-load + `set_temporal_config` for tests, cleared by `reset()`). All ~130 runtime `get_config().temporal.X` reads → `get_temporal_config().X`. Exceptions `TemporalConfigError` / `WorkerTaskQueueUnknownError` moved into `pipelex_temporal/exceptions.py`.
- Plugin gate flipped to `registrar.config.plugins.boot_orchestrator == self.name`; `worker_cli` / `worker_cmd` / `setup_namespace_cmd` / `codec_server_cli` boot with `Pipelex.make(boot_orchestrator=TEMPORAL_PLUGIN_NAME)`. The old `worker_cli` `is_enabled` force-on block is gone (redundant under the explicit boot gate).

**Core (`pipelex`) shed everything Temporal-config**:

- `PluginsConfig += boot_orchestrator: str | None = None` (generic gate; absent from `pipelex.toml`, set programmatically).
- Deleted `pipelex/system/configuration/config_temporal.py` **and** `pipelex/system/configuration/exceptions.py` (its only importer was `config_temporal`); removed `temporal: Temporal` from `PipelexConfig`.
- CLI: `--temporal/--no-temporal` (`bool|None`) → `--orchestrator` (`str|None`); `temporal_enabled` → `boot_orchestrator` through `cli_factory` → `Pipelex.make`/`setup`; the `pipelex.py` override sets `config.plugins.boot_orchestrator`.
- Removed every `[temporal]` block from `pipelex/pipelex.toml`, `.pipelex/pipelex.toml`, `.pipelex/pipelex_override.toml`, `pipelex/kit/configs/pipelex.toml`; `tracing_config.temporal_dynamodb` stays. `make check-config-sync` green.
- `make gep` regenerated: removed the 2 relocated core exceptions **and** 9 pre-existing stale `pipelex-temporal` flow-error pages (left over from the Phase-5 externalization) — core's error catalog now names no Temporal error.

### Deviations from the written plan (deliberate)

- **Phase 1 did more than "repoint imports."** Repointing only the schema *imports* to the local module while still reading `get_config().temporal` would create nominal-type conflicts (core `WorkerScope` vs local `WorkerScope`). So Phase 1 also rewired all rich reads to `get_temporal_config()` (local). The gate/guards stayed on core `is_enabled` through Phase 1 (faithful copy keeps `is_enabled` in the local schema); `is_enabled` was dropped in Phase 2 with the gate flip. Checkpoint 1 (pipelex-temporal green, core untouched) held.
- **Phase 2 = core cut-over (Step B) + pipelex-temporal gate flip (Step C), landed together.** Core green on its own; the editable pin means pipelex-temporal's gate flip had to land with it. Both verified green together at Checkpoint 2.

### Local-environment migration (one-off, done)

The config loader also merges the **global** `~/.pipelex/pipelex.toml`, which was seeded from an old kit and still carried `[temporal]` → `extra="forbid"` boot failure. Backed up to `~/.pipelex/pipelex.toml.pre-temporal-cut.bak` and removed the stale block. CI is unaffected (fresh global is kit-seeded from the now-clean kit). **Any developer/deployment upgrading past this change must drop `[temporal]` from their `~/.pipelex/pipelex.toml`** (breaking change, no back-compat per repo policy).

### Headline invariant — verified

Core has **no** `from temporalio... import` anywhere and **no** `temporal` config field. Remaining `temporal` mentions are all out of scope: the intentional `sys.modules.get("temporalio.activity")` *sniff* in `reporting_manager` (a string lookup that explicitly avoids importing — the crash-free-without-temporalio pattern), the execution-mode enum's `requires_pipelex_temporal` mode vocabulary, prose comments/docstrings, and the deferred `temporal_dynamodb` tracing axis. None is a type-check coupling.

### Gates (all green)

- core: `make agent-check` (pyright 0 / mypy 0 / keyword-only / plxt), `make tb`, `make agent-test` (exit 0), `make gep`, `make check-config-sync`; `pipelex run pipe --help` / `validate pipe --help` show `--orchestrator`.
- pipelex-temporal: `make agent-check` (pyright 0 / mypy 0), `make agent-test` (unit + integration time-skipping) against editable new core; `pipelex-temporal --help` smokes.

### Committed (not pushed)

- Core: `eaa671d10` on `refactor/Plugins-3` (`_plugins`) — the doc update lands in the immediate follow-up commit.
- pipelex-temporal: `187e846` on `refactor/own-temporal-config` (branched off `main`).

### Phase 3 — as-built (DONE)

Re-merged `refactor/Plugins-3` → `feature/mistralai-2x-bump` (worktree `_workflows`), merge commit `a34ca9a7e`. As predicted, the **only** content conflict was `CHANGELOG.md`, resolved by union (`[Unreleased]` mistralai 2.x on top, then `[v0.35.0]`, then `[v0.34.0]`). `pyproject.toml` auto-merged cleanly and correctly: `mistralai>=2.4.4` (mistralai side) survives, no `temporal` extra and no `temporalio` anywhere (Plugins-3 side). `uv sync --all-extras` then dropped the stale `temporalio` from the venv with **zero** errors — the exact clean sync that previously surfaced the 13-pyright-error defect now passes, proving the fix holds. Gates green on the merged base: `make tb`, `make agent-check` (pyright 0 / mypy clean across 2075 files / keyword-only / plxt), `make agent-test` (all passed).

**Discovered + fixed latent red (test-relocation gap).** The first `make agent-test` run failed one test: `tests/unit/pipelex/system/test_non_retryable_baseline_pins.py` read `config["temporal"]["worker_config"]["retry_policy_config"]["non_retryable_error_types"]` from core's `pipelex.toml` → `KeyError: 'temporal'`. Root cause: the Phase 5 externalization deleted most temporal tests from core and re-homed them in `pipelex-temporal`, but **this one was mistakenly renamed** (`tests/unit/pipelex/temporal/` → `tests/unit/pipelex/system/`) and left pointing at the now-absent core `[temporal]` block. It was a **pre-existing red on `refactor/Plugins-3` itself** (the baseline now lives at the root `[worker_config.retry_policy_config]` table in `pipelex-temporal/temporal.toml`), not introduced by the merge — the Checkpoint-2 "core `make agent-test` exit 0" claim missed it. Fix preserves the protection rather than dropping it (the guard covers the retry-forever family this project has been bitten by): the stale core copy is **deleted** (`8da150c43`), and a corrected test is **relocated to `pipelex-temporal`** (`877c85b`) — it imports the core class names (`DryRunMockBuildError` / `DryRunObjectFidelityError`), reads the packaged `temporal.toml` directly (env-independent, not via `load_temporal_config()` whose deep-merge would let a user override mask the baseline), and asserts the string linkage holds. pipelex-temporal `make agent-check` + the test are green.

Next: the original task — make `pipelex-mistralai-workflows` a discoverable `pipelex.plugins` entry-point plugin — proceeds against this corrected base.
- **Docs follow-up (deferred).** Updated `docs/under-the-hood/orchestrator-plugins.md` (gate + module paths). Still stale and not touched this pass: `docs/under-the-hood/pipe-routing-and-execution.md` and `docs/distributed-execution/task-routing.md` still show `temporal.is_enabled` and `[temporal.worker_config.*]` / `[temporal.queue_options.*]` TOML examples. Those config tables now live at **root** in `pipelex-temporal`'s `temporal.toml` (no `[temporal.]` prefix), so the examples need rewriting — and the distributed-execution config docs arguably belong in the `pipelex-temporal` repo now. Left as a separate docs pass (involves a relocation decision).
