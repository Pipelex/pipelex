# Option A — drop the CLI-command seam; Temporal ops as the `pipelex-temporal` console script (as-built)

> ✅ **IMPLEMENTED.** Committed on `refactor/Plugins-2` as `989c9beed` ("Refactor CLI command handling and introduce standalone pipelex-temporal console script"). All gates green: `make agent-check` (pyright 0 / mypy 0 over 2240 files / keyword-only), `make tb`, `make agent-test` ("All tests passed."), `pytest tests/integration/pipelex/temporal/` (156 passed, 4 xpassed = the Phase-3 baseline xdist markers), plus both `--help` smokes. This is the faithful as-built record — the basis Phases 4–5 build on.
>
> **What it did:** removed the plugin CLI-command-contribution seam (the former decision **D3**) entirely. The two Temporal operational commands — `worker` and `setup-namespace` — now ship as a standalone `pipelex-temporal` console script (`[project.scripts]` → `pipelex.temporal.temporal_cli:app`), not harvested `pipelex` subcommands. This resolved the whole [critical finding](phase-3-critical-cli-harvest-fragility.md) by **removing the surface**, not hardening it: `pipelex --help` no longer loads config or scans entry points, and no plugin can shadow a core command or brick the recovery commands. The inference-backend / orchestrator / boot-slot seams are **untouched**.
>
> Read [TODOS.md cold-start primer](../../TODOS.md#cold-start-primer-read-this-first-if-youre-new-to-the-session) for the plugin-seam vocabulary (registrar, `build_registrar`, `BUILTIN_PLUGINS`, slot-claims, D1–D7).

## Why this, in one screen

The seam treats "CLI command" as just another contribution type alongside "inference backend" and "orchestrator." It isn't — and that mismatch is the whole bug. The other contributions are consumed **lazily, at point-of-use, inside a booted Pipelex** (a backend when a model needs a worker; an orchestrator at execution time; a slot-claim at boot). The seam's **fail-loud** invariant is correct there. CLI commands are consumed **eagerly, at module-import of `pipelex/cli/_cli.py`, before anything boots, on every `pipelex` invocation including `--help`**. On that path fail-loud is a liability: one broken/colliding installed plugin (or an unreadable config) bricks every command — including `doctor`/`plugins`/`init`, the very commands you'd use to disable the bad plugin. The four facets in the critical doc and the "double discovery / import-time cost" item in [`phase-3-review-deferred.md`](phase-3-review-deferred.md) are all symptoms of this one decision.

The consumer that justified the seam is tiny and operational: `add_cli_command` has exactly **one** caller (the Temporal plugin), contributing exactly **two** commands — `worker` (start a long-running worker daemon) and `setup-temporal-namespace` (one-time namespace bootstrap). Neither is how a pipeline *runs* on Temporal — distributed execution goes through the orchestrator registry via `execution_mode`, which is untouched by any of this. Operational daemons are the textbook use case for a **console script** (`[project.scripts]`), which pip materializes into its own executable — no host-CLI harvest, no import-time discovery, no fragility. Pipelex already ships three (`pipelex`, `pipelex-agent`, `pipelex-dev`). And it is exactly where Phase 5 wants to land: when Temporal externalizes to `pipelex-temporal`, that dist owns its own `pipelex-temporal` console script natively, with no custom machinery to move.

**Net effect of this change:** deletes the harvest, all four facets, the double-discovery, and the per-invocation config-load + entry-point-scan on `--help`. Strictly less code, strictly less fragility, strictly better Phase-5 alignment. The only real cost is one user-facing rename (`pipelex worker` → `pipelex-temporal worker`) and a one-line Dockerfile change in the `pipelex-worker` repo (gated on the release — see the cross-repo stage).

## The design (as built)

A single grouped Temporal CLI exposed as a console script:

- New console script in `pyproject.toml`: `pipelex-temporal = "pipelex.temporal.temporal_cli:app"`.
- New module `pipelex/temporal/temporal_cli.py`: a `typer.Typer()` app registering two subcommands — `worker` and `setup-namespace`.
- The two command callables **move** from `pipelex/cli/commands/` to `pipelex/temporal/` (they are Temporal-owned and must travel together in Phase 5; absolute imports keep working from the new location):
  - `pipelex/cli/commands/worker_cmd.py` → `pipelex/temporal/worker_cmd.py` (`worker_cmd`)
  - `pipelex/cli/commands/setup_temporal_namespace_cmd.py` → `pipelex/temporal/setup_namespace_cmd.py` (`setup_namespace_cmd`)
- Resulting invocations: `pipelex-temporal worker [--no-sandbox --task-queue … --scope … --profile …]` and `pipelex-temporal setup-namespace [--dry-run --server …]`.

Both command callables are already import-light at module top (temporalio is pulled lazily inside their bodies), so importing `temporal_cli.py` when you run `pipelex-temporal` is import-light, and — crucially — `pipelex/cli/_cli.py` no longer references them at all, so `pipelex --help` cannot touch Temporal. The import-light *boot* guard is unaffected and still applies to boot.

**Design choices (as built):**

- *Grouped script vs two flat scripts.* Grouped `pipelex-temporal` (chosen) over flat `pipelex-worker` + `pipelex-setup-temporal-namespace`. Grouped maps 1:1 to the Phase-5 dist and avoids colliding with the `pipelex-worker` *repo/dist* name.
- *Move the command modules vs leave them in `pipelex/cli/commands/`.* Move (chosen) — Phase-5-aligned, "solid over quick." Cost is mechanical: update import + mock paths in one test (`test_setup_temporal_namespace_cmd.py`).
- *Subcommand name `setup-namespace` vs `setup-temporal-namespace`.* `setup-namespace` (chosen) — "temporal" is redundant under a `pipelex-temporal` group, and every embedding string changes anyway.

## Out of scope — do NOT unwind these

The valuable coupling inversion stays exactly as shipped. **Touch none of it:**

- The four inference-family `match` → `InferenceBackendRegistry` lookups (Phases 1–2).
- The bridge `match` → `OrchestratorRegistry.get_optional(mode=…)` dispatch (Phase 3).
- The `temporal.is_enabled` boot-slot claims + LIFO teardown via `_resolve_hub_slot` (Phase 3).
- `build_registrar`, `BUILTIN_PLUGINS`, the `pipelex.plugins` entry-point group for **runtime** contributions, `pipelex plugins list`, the denylist.

This change removes only the **CLI-command** contribution path. Everything else the seam does is consumed at boot/use where fail-loud is correct.

## Implementation steps (all done — retained as the record of what changed)

### Step 1 — Stand up the new Temporal CLI surface

1. Create `pipelex/temporal/temporal_cli.py`: `app = typer.Typer()`; register `worker_cmd` as `worker` and `setup_namespace_cmd` as `setup-namespace` (use `app.command(name="worker")(worker_cmd)` / `app.command(name="setup-namespace")(setup_namespace_cmd)`, or `@app.command` wrappers — match the existing Typer idiom in the repo). Keep it import-light at module top.
2. Move `pipelex/cli/commands/worker_cmd.py` → `pipelex/temporal/worker_cmd.py` and `pipelex/cli/commands/setup_temporal_namespace_cmd.py` → `pipelex/temporal/setup_namespace_cmd.py` (rename the callable `setup_temporal_namespace_cmd` → `setup_namespace_cmd`). Their internal imports (`pipelex.cli.cli_factory`, `pipelex.cli.error_handlers`, `pipelex.config`, `pipelex.pipelex`) are absolute and unaffected.
3. Add to `pyproject.toml` `[project.scripts]`: `pipelex-temporal = "pipelex.temporal.temporal_cli:app"`.

### Step 2 — Remove the seam

4. `pipelex/cli/_cli.py`: delete `_config_for_cli_harvest()`, `_register_discovered_cli_commands()`, and the module-level `_PLUGIN_COMMAND_NAMES = …`. Change `PipelexCLI.list_commands` to `return list(_CORE_COMMAND_ORDER)`. Update the `_CORE_COMMAND_ORDER` comment block (drop the "plugin-contributed commands are appended after" paragraph). Let `make fix-unused-imports` + `make agent-check` strip the now-dead imports (expected: `importlib`, `ValidationError`, `build_registrar`, `config_manager`, `PipelexConfig`, `TomlError`, possibly `log`).
5. `pipelex/plugins/registrar.py`: remove `add_cli_command`, the `CliCommand` NamedTuple, the `self.cli_commands` field (and its mention in the class docstring), and the `"cli command {name}"` contribution line. `plugins_cmd.py` renders `discoveries[].contributions` generically, so no change needed there — those lines simply stop appearing.
6. `pipelex/temporal/temporal_plugin.py`: remove the two `registrar.add_cli_command(...)` calls and the comment above them about declaring commands by `import_path`. Update the module + class docstrings (the bullet that says the plugin "contributes the … `worker` / `setup-temporal-namespace` CLI commands"). The plugin now contributes only orchestrators (always) and slot-claims/teardown (when `is_enabled`).

### Step 3 — Update in-code user-facing strings

7. `pipelex/temporal/tprl/namespace_check.py`: `PIPELEX_SETUP_CLI_COMMAND` → `"pipelex-temporal setup-namespace"`; update the two docstring mentions (~`:19`, `:165`).
8. `pipelex/temporal/exceptions.py` (~`:90`): docstring mention of `pipelex setup-temporal-namespace` → new invocation.
9. The two moved command modules' own docstrings + `Examples:` blocks: `pipelex worker …` → `pipelex-temporal worker …`; `pipelex setup-temporal-namespace …` → `pipelex-temporal setup-namespace …`.

### Step 4 — Tests

10. **Delete** `tests/unit/pipelex/cli/test_plugin_cli_command_harvest.py` — its entire subject (the harvest + `_config_for_cli_harvest`) is gone. Optionally replace with a ~5-line smoke test asserting `pipelex.temporal.temporal_cli.app` exposes `worker` + `setup-namespace` (`[c.name for c in app.registered_commands]`).
11. **Update** `tests/unit/pipelex/cli/test_setup_temporal_namespace_cmd.py`: import path `from pipelex.temporal.setup_namespace_cmd import setup_namespace_cmd` and all `mocker.patch("pipelex.temporal.setup_namespace_cmd.…")` targets; update the callable name if renamed.
12. Confirm the import-light boot guard test (the subprocess that blocks `temporalio`) still passes — it pins boot, not the harvest, so it should be untouched. Grep showed `test_plugin_cli_command_harvest.py` is the *only* harvest-coupled test.

### Step 5 — Docs

13. Mechanical prefix swap in **current** user docs (`pipelex worker` → `pipelex-temporal worker`; `pipelex setup-temporal-namespace` → `pipelex-temporal setup-namespace`; flags `--scope/--profile/--task-queue/--dry-run/--server` unchanged): `docs/distributed-execution/workers.md`, `docs/distributed-execution/temporal/index.md`, `docs/distributed-execution/cluster-setup.md`, `docs/features/distributed-execution.md`, `docs/running-locally-on-temporal.md`. **Do NOT touch** `docs/history/**`, `wip/history/**`, `docs/plans/**` (archival).
14. **Rewrite** `docs/under-the-hood/orchestrator-plugins.md`'s "CLI-by-import-path" section: the orchestrator SPI no longer harvests CLI commands; a plugin that wants an operational command ships its own console script (`[project.scripts]`). **Fold in the deferred-doc fix** here too: the line (~`:116`) claiming the Temporal plugin is "discovered via an entry point pipelex declares on itself" is factually wrong — it is in `BUILTIN_PLUGINS`, and `pyproject.toml` declares no `pipelex.plugins` self-entry-point. State the builtin-list mechanism + the real Phase-5 delta. (`docs/under-the-hood/inference-backend-plugins.md` does **not** mention the CLI seam — leave it.)
15. Sanity-check (almost certainly clean): no `docs/specs/**` or `conformance/**` command-surface entry references these invocations (verified — the grep found none), so no `make check-spec-links` concern. Re-verify after editing.

### Step 6 — Tracker bookkeeping

16. `TODOS.md`: mark **D3 superseded** by this doc (one line in the locked-decisions list + the CLI seam row of the cold-start primer). Note the CLI-command contribution path was removed; runtime contributions (backends/orchestrators) and `plugins list` are unchanged.
17. `phase-3-critical-cli-harvest-fragility.md`: add a top banner — **RESOLVED by removal**, pointing here.
18. `phase-3-review-deferred.md`: mark the "Double discovery + import-time cost" Low item **resolved** (the import-time harvest is gone); mark the "SPI doc factually wrong" Medium item resolved (folded into step 14).

### ✅ CHECKPOINT — verify gate (PASSED)

- ✅ `make agent-check` clean (pyright 0 / mypy 0 over 2240 files / ruff+plxt / keyword-only).
- ✅ `make tb` green — 5 passed (registrar shape changed — boot/config sanity).
- ✅ `make agent-test` green ("All tests passed.", exit 0).
- ✅ `.venv/bin/pytest tests/integration/pipelex/temporal/` — **156 passed, 4 xpassed** (the §14.5 Temporal gate; the 4 xpassed are the pre-existing xdist class-registration flakiness markers, matching the Phase-3 baseline exactly).
- ✅ Manual smoke: `.venv/bin/pipelex --help` lists core commands only — no `worker`/`setup-temporal-namespace`, no config load / entry-point scan; `.venv/bin/pipelex-temporal --help` lists `worker` + `setup-namespace`.
- ✅ Committed on `refactor/Plugins-2` as `989c9beed` (one-commit-per-checkpoint delivery model).

> **Note on the env:** materializing the new console script needs `uv sync --all-extras` (it regenerates `[project.scripts]` wrappers into `.venv/bin/`). That sync also brings the venv up to the already-committed `uv.lock` (it had drifted behind on `cryptography`/`mthds`); `uv.lock` itself is unchanged. Separately, `make cleanderived` deletes the gitignored generated fixture `tests/integration/pipelex/fixtures/_generated_model_sets.py` — regenerate it with `make regenerate-test-models-quiet` (alias `rtm`) before `make agent-check`, or pyright fails on the missing import.

## Cross-repo follow-up — GATED on the release that ships the script

This is the one downstream cost, and it is **release-gated** — do **not** push it ahead of the pipelex release that carries `pipelex-temporal`. Blast radius is exactly one repo (`pipelex-api-hosted`, `sandbox`, `pipelex-api` were checked and do **not** invoke the worker):

- `pipelex-worker/Dockerfile` (~`:25`): `CMD ["pipelex", "worker", "--no-sandbox"]` → `CMD ["pipelex-temporal", "worker", "--no-sandbox"]`.
- `pipelex-worker/Makefile` (~`:125`): `pipelex worker --no-sandbox --task-queue test` → `pipelex-temporal worker …`.

**Rule:** whoever bumps `pipelex-worker`'s `pipelex` pin to the release containing this change must flip these two lines in the **same** commit. Until that bump, the old pinned pipelex still has `pipelex worker`, so nothing breaks. This session is **pipelex-only** — capture the above as a standing follow-up (this section is that record; mirror it into the Phase-5 downstream-pin step in `TODOS.md` so it isn't lost).

## Open cleanups (investigate, note — do NOT expand scope)

- **`ensure_global_if_missing` / `load_base_config_dict`.** ⚠️ **Investigated — confirmed sole caller, FLAGGED for a follow-up (not removed here).** `_config_for_cli_harvest` (now deleted) was the **only** caller of both `config_manager.load_config(ensure_global_if_missing=False)` and `config_manager.load_base_config_dict()` (verified by grep across `pipelex/` + `tests/`). After this change: `load_base_config_dict()` has **zero** callers (dead method), and every `load_config` caller uses the default `ensure_global_if_missing=True` so the `False` branch (`config_loader.py:~260`) is dead. Both are in `pipelex/system/configuration/config_loader.py` (`load_base_config_dict` ~`:195`, the param ~`:205`/`:242`/`:260`). Left in place deliberately — removing the param means reshaping `load_config`'s signature + collapsing the branch, a config-loader edit out of scope for "drop the CLI seam." Neither breaks a gate (ruff/pyright don't flag unused public methods). **Follow-up:** delete `load_base_config_dict()` and simplify `load_config` to always-ensure-global.
- **Legacy `pipelex/temporal/worker_cli.py`.** A second, heavier worker entrypoint (`python -m pipelex.temporal.worker_cli`, the `configure` command) that imports `temporalio` at module top and duplicates worker-start logic. Out of scope here; note it as a unification candidate (it could become a thin alias of, or be folded into, the new `temporal_cli.py`). Don't fix unless trivial.

## Pointers

- Seam removal: `pipelex/cli/_cli.py` (harvest), `pipelex/plugins/registrar.py` (`add_cli_command`/`CliCommand`), `pipelex/temporal/temporal_plugin.py` (the two calls).
- Command callables to move: `pipelex/cli/commands/worker_cmd.py`, `pipelex/cli/commands/setup_temporal_namespace_cmd.py`.
- Strings: `pipelex/temporal/tprl/namespace_check.py` (`PIPELEX_SETUP_CLI_COMMAND`), `pipelex/temporal/exceptions.py`.
- Decision lineage: supersedes **D3** in [TODOS.md](../../TODOS.md); resolves [phase-3-critical-cli-harvest-fragility.md](phase-3-critical-cli-harvest-fragility.md) and two items in [phase-3-review-deferred.md](phase-3-review-deferred.md).
