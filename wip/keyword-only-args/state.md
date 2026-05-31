# Keyword-only arguments — cold-start state

Status: Checkpoint A VERIFIED — guard built; `make agent-check` clean (pyright 0 errors / mypy 1932 files ok); full `make agent-test` green (exit 0); rule strictness + gate placement confirmed with the user; `convention.md` corrected to match the enforced rule. Ready to start Wave 1. Nothing committed yet — see Current position.

This is the running cold-start log for the keyword-only-arguments refactor. Read this file plus [`../../TODOS.md`](../../TODOS.md) and you have everything needed to resume with zero lost context. The convention itself lives in [`convention.md`](convention.md).

## Guard

The guard is the `check-keyword-only` dev CLI command. It walks every `.py` under `pipelex/` (excluding `__pycache__` and `tests/`), parses each with `ast`, evaluates the carve-outs then the keyword-only rule per def, compares the found violations against the committed baseline, and fails (exit 1) only on NEW violations not present in the baseline.

- Command: `.venv/bin/pipelex-dev check-keyword-only` (flags: `--report` for the full inventory grouped by package, `--regen-baseline` to rewrite the baseline with all current violations, `--quiet` / `-q` for the single-line Make mode).
- Makefile target: `make check-keyword-only` (alias `make cko`), which runs `$(VENV_PIPELEX_DEV) check-keyword-only --quiet`.
- Wired into the `check:` aggregate (Makefile around line 1156, in the `check-* ` cluster) and listed in `.PHONY`.
- Source: `pipelex/cli/dev_cli/commands/check_keyword_only_cmd.py`.
- Registration: `pipelex/cli/dev_cli/_dev_cli.py` (import, the `list_commands` entry, and the `@app.command("check-keyword-only")` Typer wrapper).
- Tests: `tests/unit/pipelex/cli/dev/test_check_keyword_only_cmd.py`.
- Baseline: `wip/keyword-only-args/violations-baseline.txt` — newline-delimited `relpath::qualified_name` keys, no line numbers, sorted lexicographically. Strictly shrinks as waves land; the guard warns about and prunes (via `--regen-baseline`) stale entries that no longer violate; remove the file entirely once the tree is fully compliant.
- Inventory: `wip/keyword-only-args/inventory.json` — machine-readable `total` + `per_package_counts` + `violations_by_package`.

The guard currently passes against its own baseline (all current violations known-debt; zero NEW violations). The guard's own command module is fully compliant with the convention.

## Per-package violation inventory (baseline)

These are tracked data captured at Checkpoint A from the `--regen-baseline` run, mirrored from `inventory.json` (`per_package_counts`). Total: 812.

| Package | Violations |
| --- | --- |
| `tools` | 131 |
| `cogt` | 132 |
| `cli` | 109 |
| `core` | 108 |
| `plugins` | 50 |
| `system` | 44 |
| `temporal` | 40 |
| `pipe_operators` | 40 |
| `graph` | 39 |
| `libraries` | 24 |
| `builder` | 21 |
| `pipe_run` | 21 |
| `pipeline` | 12 |
| `kit` | 8 |
| `reporting` | 7 |
| `pipe_controllers` | 6 |
| `tracing` | 6 |
| `<root>` (`pipelex.py`, `hub.py`, `config.py`, `types.py`, `urls.py`, `base_exceptions.py`, `exceptions.py`) | 4 |
| `language` | 4 |
| `errors` | 3 |
| `observer` | 2 |
| `test_extras` | 1 |

These are the burn-down targets ordered into waves in [`README.md`](README.md). The wave order is risk-based (leaf packages first, framework/public surface last), not violation-count order — so a high-count leaf like `tools/` lands in Wave 1 while a smaller but framework-sensitive package like `cli/` waits for Wave 5.

## Decisions log

- Override handling — skip any def carrying `@override`. We deliberately did NOT introduce a `@kw_exempt` decorator and did NOT attempt base-aware / import-resolving detection. Rationale: `pyproject.toml` sets `reportImplicitOverride = true`, so any method overriding a nominal base MUST carry `@override` or `make agent-check` (pyright) fails before this guard runs — making `@override` a complete, self-maintaining signal. `reportIncompatibleMethodOverride = error` means an overriding method cannot freely re-shape its signature, so the convention is applied at the base/Protocol definition and impls inherit it; skipping `@override` impls is consistent with that. The rare Protocol-implementor-without-`@override` is covered by the `# kw-only: ignore` escape hatch. Matched structurally: `ast.Name` with `id == "override"` OR `ast.Attribute` with `attr == "override"` (covers both `override` and `typing_extensions.override` without import resolution). The pyright invariant lives at `pyproject.toml` line 176.
- Symmetric-tuple allowlist — exempt the WHOLE function only for genuine ordered tuples under a recognized convention, keyed by EXACT qualified name AND file path (both must match), no pattern guessing. The list is intentionally short and conservative. Entries: `pipelex.system.environment.set_env` (`set_env(key, value)`), `pipelex.kit.single_file_agent_rules.unified_diff` (`unified_diff(before, after, path)`), `pipelex.tools.misc.diff.diff_files` (`diff_files(path1, path2)`), `pipelex.tools.misc.diff.diff_dirs` (`diff_dirs(dir1, dir2)`). Deliberately EXCLUDED: `has_diff_dirs`, `copy_file`, `sync_toml_values` — each has a genuine ordered leading pair but also trailing options; a whole-function exemption would let those options go positional too. They stay off the allowlist and are flagged as violations, resolved per-function at burn-down (see the Exception-2 open question below). Erring toward keyword-only is the safe default; adding to the allowlist is a deliberate, justified act.
- Carve-out decorators (def never inspected when any matches) — dunder/operator names matching `^__[A-Za-z0-9_]+__$` full-match on the NAME node only (so `____` cannot match and name-mangled half-dunders like `__private` remain subject to the rule); pydantic `field_validator` / `model_validator` / `field_serializer` / `model_serializer` / `validator` / `root_validator` (call-form or bare, matched on the unqualified decorator name); framework entrypoints — Typer/click `*.command` / `*.callback` (matched on the attribute suffix, since the receiver varies: `app` / `graph_app` / `show_app` / `kit_app` / `build_app`), Temporal `activity.defn` / `workflow.run` / `workflow.signal` / `workflow.query` / `workflow.update` (matched on the trailing two attribute segments, scanned across the WHOLE decorator stack so a custom decorator stacked below `@activity.defn` does not hide it), and `pytest.fixture`; and `@override` (see above). The escape hatch `# kw-only: ignore` on the def line suppresses exactly one violation.
- Typer call-style entrypoint detection (closes the decorator-blind gap) — some Typer commands are registered via `app.command(name=...)(fn)` against functions in separate modules that carry NO decorator. The guard treats a def as a framework entrypoint when any parameter's `Annotated[...]` metadata contains a call to `typer.Argument(...)` or `typer.Option(...)`, without resorting to a broad path-based exclusion of CLI modules.
- The rule itself — after dropping a leading `self`/`cls` and the single allowed subject parameter, a def is a VIOLATION iff one or more positional-or-keyword params remain (i.e. two or more non-self/cls positional-or-keyword params total and no bare `*` already separating them). Keyword-only params (already past a bare `*`), `*args`, and `**kwargs` do not count as violations. Single-param / subject-only defs are compliant under Exception 1.
- Rule strictness (confirmed with user) — STRICT: only the subject may be positional; every other parameter must be keyword-only, so `def f(a, b)` and `def truncate(text, max_length=80)` are violations. The subject exception is a *permission* (the Swift `_` readability case), never a requirement — making the subject keyword-only too (`def f(*, a, b)`) is always compliant and often preferable. The guard already enforces this; `convention.md` was corrected to match (it had drifted to a looser "one trailing positional is fine" reading that contradicted both the code and the 812 baseline).
- Gate placement (confirmed with user) — `check-keyword-only` runs in BOTH `make agent-check` (fast everyday gate) and `make check` (heavy gate + CI), so a new violation is caught in the tight edit loop, not only at `make check`.

## Current position

Checkpoint A is VERIFIED and snapshotted in `TODOS.md`. Next: Phase 2 / Wave 1 burn-down (`tools/` → root modules → `reporting/` → `observer/` → `tracing/`). Nothing has been committed yet — the Phase-1 guard, the doc fixes, the Makefile + `_dev_cli.py` changes, and the `wip/keyword-only-args/` track sit unstaged on branch `refactor/Function-calling-1`. Commit Phase 1 (and decide whether it is its own PR or the base of the Wave-1 PR) before or as part of starting Wave 1.

Open question carried into burn-down (Exception 2): the symmetric allowlist is whole-function, so it cannot express "leading directional pair positional, trailing options keyword". Under the strict rule, `copy_file(source_path, target_path, *, overwrite=True)` is still a violation (`target_path` is a second positional). Resolve per-function when its package is migrated: either reshape to `copy_file(source_path, *, target_path, overwrite=True)`, or extend the allowlist with a per-entry leading-positional-count so a genuine pair stays positional while `*` still forces the options keyword. Affects `copy_file`, `has_diff_dirs`, `sync_toml_values` (and any future directional-pair-plus-options helper).

## Resume commands

Run from the repo worktree root (`/Users/lchoquel/repos/Pipelex/_calls`), using the project virtualenv.

```bash
# 1. Verify Checkpoint A: lint + full suite must pass (do this FIRST).
make agent-check
make agent-test

# 2. Confirm the guard is green against its baseline (single-line Make mode).
make check-keyword-only            # alias: make cko

# 3. Inspect the full inventory grouped by package (drives the wave burn-down).
.venv/bin/pipelex-dev check-keyword-only --report

# 4. After migrating a package: delete its now-fixed keys from the baseline,
#    then regenerate to prune any remaining stale entries and re-verify.
.venv/bin/pipelex-dev check-keyword-only --regen-baseline
make check-keyword-only

# 5. Run the guard's own unit tests.
.venv/bin/pytest -q tests/unit/pipelex/cli/dev/test_check_keyword_only_cmd.py
```
