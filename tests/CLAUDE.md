# Targeted Test Guide

Instead of running the full suite (`make agent-test`) every time, run only the tests relevant to what you changed.

## Command template

```bash
.venv/bin/pytest -n auto \
  -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" \
  -o log_level=WARNING --tb=short -q \
  <paths>
```

Replace `<paths>` with the test directories from the mapping below. Concatenate paths when multiple source areas are touched.

## Source-to-test mapping

| Changed source | Test paths to run |
|---|---|
| `pipelex/builder/` | `tests/unit/pipelex/builder/ tests/integration/pipelex/builder/` |
| `pipelex/cli/` | `tests/unit/pipelex/cli/ tests/integration/pipelex/cli/ tests/e2e/pipelex/cli/` |
| `pipelex/codegen/` | `tests/unit/pipelex/codegen/ tests/integration/pipelex/codegen/` |
| `pipelex/cogt/` | `tests/unit/pipelex/cogt/ tests/integration/pipelex/cogt/` |
| `pipelex/core/` | `tests/unit/pipelex/core/ tests/integration/pipelex/core/ tests/integration/pipelex/pipes/` |
| `pipelex/graph/` | `tests/unit/pipelex/graph/ tests/e2e/pipelex/graph/` |
| `pipelex/kit/` | `tests/unit/pipelex/kit/ tests/integration/pipelex/kit/` |
| `pipelex/language/` | `tests/unit/pipelex/language/ tests/integration/pipelex/language/` |
| `pipelex/libraries/` | `tests/unit/pipelex/libraries/ tests/integration/pipelex/libraries/` |
| `pipelex/mthds_parsing/` | `tests/unit/pipelex/mthds_parsing/ tests/integration/pipelex/language/` |
| `pipelex/pipe_controllers/` | `tests/unit/pipelex/pipe_controllers/ tests/integration/pipelex/pipes/` |
| `pipelex/pipe_machinery/` | `tests/unit/pipelex/pipe_machinery/ tests/integration/pipelex/pipe_machinery/` |
| `pipelex/pipe_operators/` | `tests/unit/pipelex/pipe_operators/ tests/integration/pipelex/pipes/` |
| `pipelex/pipe_run/` | `tests/unit/pipelex/pipe_run/ tests/integration/pipelex/pipes/` |
| `pipelex/pipe_signature/` | `tests/unit/pipelex/pipe_signature/ tests/integration/pipelex/pipe_signature/` |
| `pipelex/pipeline/` | `tests/integration/pipelex/pipeline/` |
| `pipelex/plugins/` | `tests/unit/pipelex/plugins/ tests/integration/pipelex/plugins/` |
| `pipelex/providers/` | `tests/unit/pipelex/providers/ tests/integration/pipelex/providers/` |
| `pipelex/system/` | `tests/unit/pipelex/system/ tests/integration/pipelex/system/` |
| `pipelex/tools/` | `tests/unit/pipelex/tools/ tests/integration/pipelex/tools/` |

Note: `pipe_controllers/`, `pipe_operators/`, and `pipe_run/` share integration tests at `tests/integration/pipelex/pipes/` -- deduplicate the path when multiple of these areas are touched.

## Cross-cutting triggers

Add these to any targeted run when applicable:

- **Config TOML changes** (`pipelex/pipelex.toml`, `pipelex/kit/configs/`): also run `make tb` (boot test)
- **`.mthds` file changes**: also add `tests/unit/pipelex/builder/ tests/integration/pipelex/builder/ tests/integration/pipelex/pipes/`
- **Test fixtures changed** (`tests/data/`, `tests/cases/`): also run tests that import from those fixtures

## When to run full `make agent-test`

Fall back to the full suite when:

- Changes span 3+ source areas from the mapping above
- Changes touch `pyproject.toml`, `tests/conftest.py`, or `tests/helpers/`
- Changes touch root-level modules: `pipelex/__init__.py`, `pipelex/runtime_hub.py`, `pipelex/interpreter_hub.py`
- Changes touch `pipelex/system/configuration/` (config loading affects everything)
- Refactors touching base exceptions or shared base classes
- Preparing a release, a push, or a commit intended for remote (e.g. `/release`, `/commit-push`, `/ship`, or when the context makes it obvious the work is about to land)

## Quick reference

| Command | When to use |
|---|---|
| `make tb` | Config/TOML-only changes (boot sanity check) |
| `make agent-check` | Always run after code changes (linting, formatting, type checking) |
| `make agent-test` | Full suite fallback for broad changes |
