# Plan — Unified dry run (retire `is_mock_inference`; add internal `is_mock_usage` flag)

> **Status: COMPLETE (2026-06-10) — all phases done, `make agent-check` + full `make agent-test` green.** Implements [`design-unified-dry-run.md`](./design-unified-dry-run.md) (design agreed with the user). Baseline: `feature/Mock-activities` as-built (Part B complete + Part C validation activity merged in).

## Plan-time decisions (resolving design §5)

The design deferred these to plan time; resolved here, taking the design's proposed options:

- **`is_mock_usage=True` + `run_mode=LIVE` is a validation error** — a pydantic model-validator on `CogtRunParams` rejects it (fail loud, per the design's proposal). The CLI never produces the combination (the hidden flag requires `--dry-run`), so the validator only fires on a buggy embedder call.
- **E2E trigger = hidden CLI flag `--mock-usage`** (typer `hidden=True` on `run pipe` / `run bundle` / `run method`, requires `--dry-run`). Present for the `temporal-e2e-validate` Mode-2 scripts, absent from `--help` and docs.
- **`MockInferenceObjectFidelityError` → renamed `DryRunObjectFidelityError`** — mock-built objects are now DRY-only, the old name is a lie; no backward compat per project principles. Error pages regenerated.
- **Sentinel naming**: two sentinels stay — `dry_run` (zero-token) unchanged; `mock_inference` → `mock_usage`. No fold into a single sentinel: tests filter usage events by sentinel name, and two names keep the two reporting payloads grep-able.
- **Non-LLM leaves do NOT emit synthetic usage under `is_mock_usage=True`** (minimal design — matches what the cost-assembly tests assert).
- **`CogtRunParams.is_mock_built` property deleted** (not kept as alias): mock-built is now exactly `run_mode.is_dry`; keeping a second name for one predicate is the disease this refactor cures. Fidelity-guard call sites read `run_mode.is_dry`.
- **PipeCompose dry arm: untouched** (explicitly parked by the user).

## Phases

### Phase 1 — Carrier + factory + entry points

- [x] `CogtRunParams`: `is_mock_inference` → `is_mock_usage` with new semantics docstring; add model-validator rejecting `is_mock_usage=True` with `run_mode.is_live`; delete `is_mock_built` property. Frozen/extra-forbid/required-run_mode unchanged.
- [x] `PipeRunParamsFactory.make_run_params`: param re-keyed `is_mock_inference` → `is_mock_usage`; forced-DRY path simplified (single warning; no swallow arm — `is_mock_usage` rides DRY fine).
- [x] Entry-point threading re-keyed: `PipelexRunner.__init__` / `execute_pipeline`, `pipeline_run_setup`, `prepare_pipe_job` (`execution_seams.py`). Docstrings rewritten for the sub-flag semantics.
- [x] Fidelity guard call sites (`content_generator.py` ×3, `content_generator_in_workflow.py` ×3) re-keyed from `is_mock_built` to `run_mode.is_dry`.

### Phase 2 — Leaves

- [x] `llm_generate.py`: dual branch collapses to one `if run_mode.is_dry` per leaf; dry helpers select report func on `is_mock_usage`.
- [x] `dry_mock.py`: delete `mock_llm_gen_text` / `mock_llm_gen_object` / `mock_llm_gen_object_list` / `_mock_text` and the `MOCK INFERENCE` marker; rename `report_mock_inference_llm_job` → `report_mock_usage_llm_job`, `MOCK_INFERENCE_MODEL_NAME/ID` → `MOCK_USAGE_*` (= `"mock_usage"`), `MOCK_INFERENCE_NB_TOKENS_BY_CATEGORY` → `MOCK_USAGE_NB_TOKENS_BY_CATEGORY`; dry helpers pick report func via a shared `_dry_report_func(cogt_run_params)`; `stamp_mock_main_coordination` docstring sheds the mock-inference caveat (the dry object-list leaf stamps regardless of `is_mock_usage`); module docstring rewritten for the one-mode world.
- [x] Delete the `MockInferenceUnsupportedError` guards: `img_gen_generate.py` (×2), `extract_generate.py`, `search_generate.py` (`_guard_no_mock_inference`).

### Phase 3 — Errors + config lists

- [x] Delete `MockInferenceUnsupportedError` from `cogt/content_generation/exceptions.py`; remove it from `non_retryable_error_types` in all three toml copies (`pipelex/pipelex.toml`, `pipelex/kit/configs/pipelex.toml`, `.pipelex/pipelex.toml`).
- [x] Rename `MockInferenceObjectFidelityError` → `DryRunObjectFidelityError`; message/docstring re-scoped to DRY-only.
- [x] Regenerate error pages (`make gep`): `mock-inference-unsupported-error.md` removed, fidelity page renamed.

### ⛔ CHECKPOINT 1 — core re-key compiles and unit tests pass — **CLEARED 2026-06-10** (targeted cogt/cli/pipe_run/temporal unit + cogt integration runs green)

### Phase 4 — CLI

- [x] Remove `--mock-inference` from `pipe_cmd.py` / `bundle_cmd.py` / `method_cmd.py`; add hidden `--mock-usage` (typer `hidden=True`).
- [x] `validate_run_flag_combination`: mutual-exclusion arm replaced by "`--mock-usage` requires `--dry-run`"; `--mock-inputs` rule unchanged.
- [x] `_run_core.py`: `mock_inference` params → `mock_usage`, threaded to `PipelexRunner(is_mock_usage=...)`.

### Phase 5 — Tests (TDD where behavior is new: validator + CLI flag rule written red-first)

- [x] `test_cogt_run_params_carrier.py`: re-key; add the LIVE+`is_mock_usage` rejection test (red first).
- [x] `test_run_flag_combination.py`: new `--mock-usage`-requires-`--dry-run` arm (red first); exclusion arm dropped.
- [x] Merge `test_llm_generate_mock_branch.py` into `test_llm_generate_dry_branch.py` parameterized over `is_mock_usage` (zero-token suppressed vs non-zero rendered payloads asserted); delete the mock-branch file.
- [x] Delete guard tests: `test_extract_generate_mock_guard.py`, `test_img_gen_generate_mock_guard.py`, `test_pipe_search_mock_inference_guard.py`, `test_mock_inference_cli_guard.py` (folded into flag-combination tests).
- [x] Re-key + rename: `test_mock_inference_temporal.py` → `test_mock_usage_temporal.py` (wire survival on the carrier, DRY + `is_mock_usage`), `test_mock_inference_direct.py` → `test_mock_usage_direct.py`, `test_mock_inference_object_fidelity.py` → `test_dry_run_object_fidelity.py`, `test_content_generator_in_workflow_object_fidelity.py` (error rename).
- [x] Fidelity tests (D6 arms): re-key from two triggers to DRY-only; `test_leaf_dry_object_mocks.py` stamp test now asserts stamping regardless of `is_mock_usage`.
- [x] Keyless-boot tests: drop the swallow-warning arm.
- [x] `test_dry_mock.py`, `test_traceback_flag_run_core.py`, tracing `test_data.py`/`helpers.py`: mechanical re-keys.

### ⛔ CHECKPOINT 2 — full suite green (`make agent-check` + `make agent-test`) — **CLEARED 2026-06-10** (0 lint/type errors, full suite passed)

### Phase 6 — Skill + docs + changelog

- [x] `temporal-e2e-validate` skill: Tier 8b arms re-pointed to `--dry-run --mock-usage` (still asserting non-zero aggregated values); Tier 17 prose drops the "distinct from `--mock-inference`" contrast and states the sub-flag; SKILL.md description + routing battery + scope manifests updated.
- [x] `docs/building-methods/pipes/run-modes-and-backends.md`: matrix collapses to one mode axis × two backends; mock inference disappears as a user-facing concept.
- [x] Purge `--mock-inference` from `docs/features/validation-dry-run.md`, `docs/under-the-hood/dry-run-mock-generation.md`, `docs/building-methods/pipes/executing-pipelines.md`; error pages already regenerated in Phase 3.
- [x] CHANGELOG `[Unreleased]`: breaking — `--mock-inference` removed; `CogtRunParams.is_mock_inference` → internal `is_mock_usage` DRY sub-flag.
- [x] wip docs: this plan's checkboxes updated; `wip/registry/deferred-followups.md` "fate of is_mock_inference" item closed; `README.md` updated.

### Phase 7 — Final verification

- [x] `make agent-check` + `make agent-test` green; commit.

## Cross-repo note (design §3.7)

`pipelex-api` carries `is_mock_inference` on its public runner API params (fed from `_run_core` → runner). That change rides a pipelex version bump like any other public-surface change — grep `mock_inference` in `pipelex-api/` when bumping the pin there; NOT part of this branch.
