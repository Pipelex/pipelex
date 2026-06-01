> **ARCHIVED — validates the abandoned `fix/dry-run` branch, NOT the current code.**
> The commands and results below were run against commit `7a01854f` on `fix/dry-run`, which was never merged into the live branch. They do not reflect the current tree. Kept as a reference for what the consolidation's verification looked like. See `archive/fix-dry-run-implementation.md` for context.

# G. Validation — Commands, Results, Known Flakes

## Commands run during implementation

| Command | Result | Notes |
|---|---|---|
| `make agent-check` | ✅ Clean | `ruff` (fix-unused-imports, format, lint), `plxt` (TOML/MTHDS), `pyright`, `mypy`. Two minor ruff lints surfaced during iteration (`PLR1714` → set membership) and were fixed. |
| `make tb` | ✅ Pass | Boot/config-load test. Required because `DryRunConfig.allowed_to_fail_pipes` was removed and `pipelex.toml` was edited. Confirms config still parses. |
| `make agent-test` (full suite) | ✅ Pass (with one pre-existing unrelated failure and the usual xdist flakes) | See "Known issues" below. |
| `.venv/bin/pytest tests/integration/pipelex/pipeline/test_validate_bundle_dry_run.py -v` | ✅ Pass | The MUST-add regression test from plan §8. |
| `.venv/bin/pytest -n auto tests/integration/pipelex/temporal/` | ✅ 99 passed, 4 xpassed | Temporal tests pass cleanly when re-run; the xpasses are documented xdist races in `test_wf_cv_batch_screening.py` and `test_wf_pipe_batch.py`. |
| `.venv/bin/pytest tests/integration/pipelex/pipes/controller/pipe_sequence/test_pipe_sequence_list_output_bug.py tests/integration/pipelex/pipeline/ tests/integration/pipelex/temporal/library_crate/ -v` | ✅ 55 passed, 24 deselected, 4 xpassed | Targeted run for the touched validator + dry-run paths. |

## Known issues (not caused by this refactor)

1. **`tests/integration/pipelex/plugins/test_openai.py::TestOpenAI::test_openai_list_available_models[plugin_for_openai0]`** — fails with `openai.AuthenticationError: 401`. Pre-existing local-env issue (invalid API key in test env); unrelated to this branch.
2. **Temporal collection-time errors under `-n auto`** — `make agent-test` once surfaced ~70 errors across `tests/integration/pipelex/temporal/...`. Re-running the same test files in isolation or with targeted `-n auto` paths produces all-pass. Documented xdist flakiness; not caused by the refactor (does not touch Temporal worker code).

## What to re-run if you touch...

Mirrors `tests/CLAUDE.md`'s source-to-test mapping for the areas this PR touches.

| If you change... | Run |
|---|---|
| `pipelex/pipe_run/` (any remaining file) | `tests/unit/pipelex/pipe_run/ tests/integration/pipelex/pipes/` |
| `pipelex/pipeline/runner.py` or `pipeline_run_setup.py` | `tests/integration/pipelex/pipeline/` plus the validator suite |
| `pipelex/pipeline/validate_bundle.py` (helpers or `validate_bundle`) | `tests/integration/pipelex/pipeline/test_validate_bundle_dry_run.py` and any validator-suite caller |
| `pipelex/core/memory/working_memory_factory.py::convert_input_specs_to_typed` | `tests/unit/pipelex/core/` plus `tests/integration/pipelex/temporal/library_crate/conftest.py`-driven tests |
| Validator callsites (CLI, agent CLI, builder) | `tests/unit/pipelex/cli/ tests/integration/pipelex/cli/ tests/integration/pipelex/builder/` |
| `pipelex/pipelex.toml` or `system/configuration/configs.py` | `make tb` (boot test) — config must still parse |

Refactor touches 5+ source areas (`pipe_run/`, `pipeline/`, `core/memory/`, `graph/`, `builder/`, `cli/`), so per `tests/CLAUDE.md` `make agent-test` is the right fallback for pre-merge confidence.

## Pre-merge checklist

- [x] `make agent-check` clean
- [x] `make tb` boot test passes
- [x] Regression test (`test_validate_bundle_dry_run.py`) passes
- [x] `make agent-test` passes (modulo the unrelated openai 401 and xdist flakes)
- [x] No remaining imports of the deleted modules (`grep -r "from pipelex.pipe_run.dry_run" --include='*.py'` returns nothing)
- [x] `allowed_to_fail_pipes` removed from both `configs.py` and `pipelex.toml`
- [x] `ValidateBundleResult.dry_run_failures` (not `dry_run_result`) used by all downstream consumers

## Verifying parity gate did not regress

If `pipelex-api-deploy` or `pipelex-worker` add boot-time library/extension preloads, re-run the parity check from `E-parity-gate.md` — specifically confirm both `Pipelex.make()` invocations register the same set of `StructuredContent` subclasses by the end of `setup()`. If they diverge, the "DRY → always local" routing in `PipelexRunner._resolve_pipe_run()` becomes unsafe and would need to be revisited.
