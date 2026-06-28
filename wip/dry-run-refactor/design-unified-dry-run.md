# Design — Unified dry run (retire `is_mock_inference` as a mode; add internal `is_mock_usage` flag)

> **Status: IMPLEMENTED (2026-06-10) — see [`plan-unified-dry-run.md`](./plan-unified-dry-run.md) for the plan and as-built record.** Design agreed with the user (2026-06-10). This design **supersedes eng-review decision D8** of [`followup-leaf-run-mode-mock.md`](./followup-leaf-run-mode-mock.md) ("is_mock_inference KEPT as thin reportable-mock"): the *mode* is retired; the *capability* (non-zero synthetic usage) survives as a secondary flag on dry run. It also resolves the "fate of `is_mock_inference`" item tracked in [`../history/registry/deferred-followups.md`](../history/registry/deferred-followups.md).
>
> **Baseline:** the as-built state of `feature/Mock-activities` (PR #983, Part B complete through Checkpoint E) + the Part C validation activity (`feature/Dry-run-as-temporal-activity`). Read [`followup-leaf-run-mode-mock.md`](./followup-leaf-run-mode-mock.md) and [`followup-temporal-validation-activity.md`](./followup-temporal-validation-activity.md) for how that baseline works.

## 1. How we got here (why two modes exist today)

- **The old dry run** predated the leaf-mock work: `--dry-run` swapped in `ContentGeneratorDry` *pre-dispatch*, so a dry run never entered Temporal activities. That mode is dead — Part B deleted `ContentGeneratorDry` and moved the mock to the cogt leaf.
- **`--mock-inference`** was added as an interim trigger (registry branch, `fix/For-API-update` Phase 5) because tests needed a *dispatching* fake: a LIVE run whose LLM leaves fake the call with non-zero synthetic usage, so the cross-worker cost-report assembly could be validated cheaply. At the time it was the only non-live mode that reached the activities.
- **Part B (this branch) unified the foundation**: `run_mode` now rides `CogtRunParams` on every assignment, every inference leaf branches at the leaf, and `--dry-run` on Temporal genuinely dispatches and mocks inside activities (Tier 17). Result: **two modes that both dispatch and both mock at the leaf**, separated only by usage reporting, leaf coverage (mock-inference is LLM-only), and a few pipe-tier dry behaviors. Two names for nearly one thing — actively confusing, as the run-modes doc work surfaced.

## 2. The design

### 2.1 One non-live mode: **dry run**

There is exactly one non-live run mode for pipeline runs: `run_mode=DRY` (`--dry-run`). Its defining contract is **no effects**:

- no AI provider calls, no API cost, no API keys needed;
- no storage IO (mocks built above the `*_and_store` step — unchanged D10);
- no user-code execution: `PipeFunc` does not execute the user's Python; `PipeCompose` keeps its dry arm (exact compose-dry details deliberately deferred — see §5);
- zero-token synthetic usage, cost report suppressed — *by default* (see §2.3).

The name is "dry run" (not "mock inference") precisely because the contract is broader than inference mocking: it is the no-effects mode.

### 2.2 Dry run is orthogonal to backend (unchanged)

Part B's deliverable holds as-is:

- **DRY × direct**: leaves mock inline in-process.
- **DRY × Temporal**: the run dispatches the *real* workflow/activity tree (child workflows, `act_*_gen_*` on workers) and the leaf mocks inside each activity. This is the mode that exercises the distribution machinery (dispatch, serialization, routing, cross-worker graph tracing) at zero cost with zero credentials.
- **The validation sweep** (`validate_bundle` / `act_dry_validate`) is *not* a third mode: it is dry run with the backend pinned in-process by the existing ContextVar scopes (`scoped_pipe_router`, `scoped_content_generator`, `scoped_event_log`), batched over all pipes, with mock inputs always on and the graph traced in memory. Unchanged by this design.

### 2.3 `is_mock_usage` — a secondary, internal flag on dry run

`CogtRunParams.is_mock_inference` is replaced by `CogtRunParams.is_mock_usage: bool = False`, with new semantics:

- It is a **sub-flag of DRY**, not a mode: it only has meaning when `run_mode=DRY`. Setting it with `run_mode=LIVE` is a contract violation (proposed: model-validator rejection — fail loud; confirm at plan time).
- `is_mock_usage=False` (default): leaves report **zero-token** synthetic jobs → `AggregatedCosts.has_reportable_usage` is False → cost report suppressed. Exactly today's dry-run reporting.
- `is_mock_usage=True`: leaves report **non-zero** synthetic usage (the deterministic sentinel counts, e.g. INPUT 100 / OUTPUT 50, `unit_costs={}` so cost is $0) → the cost report **renders**. This is what cross-worker cost-report assembly tests consume — they assert on non-zero aggregated values, not just on report presence.
- **Internal only — no public CLI flag.** Exposed through the Python surface (`PipelexRunner` / `execute_pipeline` / `PipeRunParamsFactory.make_run_params`) for tests and embedders. No documented CLI option; CLI users get `--dry-run` and nothing else.
- **Tests must still trigger it end-to-end**, including the `temporal-e2e-validate` skill's Mode-2 (3-process, CLI-driven) tiers, with non-zero values asserted. Since Mode 2 drives the real CLI, the design proposes a **hidden CLI option** (typer `hidden=True`, e.g. `--mock-usage`, requires `--dry-run`) as the test trigger: present for scripts, absent from `--help` and docs. Alternative if hidden flags are unwanted: a tiny Python submitter under `temporal/test_extras`. Decide at plan time; the hidden flag is the lowest-friction proposal.

### 2.4 Leaf coverage becomes uniform

Mock-inference's LLM-only restriction dies with the mode. Dry run already mocks **every** leaf (LLM text/object/list, img-gen, extract, render-page-views, search, templating). Consequently:

- `MockInferenceUnsupportedError` and its fail-loud guards at the img/extract/search leaves are **deleted** — their entire reason was mock-inference's partial coverage. With `is_mock_usage` riding on DRY, a "reportable" run covers every operator a dry run covers.
- Non-LLM leaves keep their current dry behavior (synthetic outputs, no usage reporting). Whether `is_mock_usage=True` should ALSO emit synthetic usage for non-LLM leaves (img-gen/extract jobs have their own usage records in live runs) is left to plan time; the minimal design keeps reportable synthetic usage LLM-only, matching what the cost-assembly tests actually assert today.

## 3. Delta inventory — what changes relative to the as-built baseline

### 3.1 Carrier and factory

- `CogtRunParams`: `is_mock_inference` → `is_mock_usage` (semantics per §2.3; frozen/extra-forbid/required-run_mode unchanged). The `is_mock_built` property collapses — mock-built is now simply `run_mode.is_dry`; keep or inline it (the fidelity guards key off it).
- `PipeRunParamsFactory.make_run_params`: parameter re-keyed; stays the single writer. The boot forced-DRY path simplifies — the "forced-DRY swallows an explicit `--mock-inference`" warning disappears (there is nothing to swallow anymore).
- `PipelexRunner` / `execute_pipeline` / `prepare_pipe_job`: `is_mock_inference` param → `is_mock_usage`.

### 3.2 Leaves (`pipelex/cogt/content_generation/`)

- Each LLM leaf's **dual branch collapses to one**: `if cogt_run_params.run_mode.is_dry → dry helper`; the dry helper selects its report func on `is_mock_usage` (zero-token `report_dry_llm_job` vs non-zero `report_mock_usage_llm_job`, renamed from `report_mock_inference_llm_job`). The object/list variants are already parameterized via `_leaf_gen_object(report_func=...)`; the text variant adopts the same shape.
- **Delete** `mock_llm_gen_text` / `mock_llm_gen_object` / `mock_llm_gen_object_list` / `_mock_text` and the `MOCK INFERENCE` marker string. One marker family remains (`DRY RUN: …`). Tests grepping the mock marker must re-key.
- Sentinel identifiers: `dry_run` model name stays for zero-token; `mock_inference` model name/id → `mock_usage` (or fold to a single sentinel with two token payloads — plan-time detail; tests that count/filter by sentinel follow).
- `stamp_mock_main_coordination`: the "mock-inference deliberately does NOT stamp" arm dies with the mode; the dry object-list leaf stamps regardless of `is_mock_usage` (harmless — the stamp only matters to bundle dry-validation, and its docstring sheds the mock-inference caveat).
- `dry_mock.py` module docstring rewritten for the one-mode world.

### 3.3 Errors

- `MockInferenceUnsupportedError`: **deleted** (guards at img/extract/search leaves removed). Error page removed on regeneration.
- `MockInferenceObjectFidelityError`: fires on mock-built objects, which is now DRY-only — **rename candidate** (e.g. `DryRunObjectFidelityError`); message/remedy text already generalized in B1. Decide at plan time; regenerate error pages either way.
- `DryRunMockBuildError`: unchanged.

### 3.4 CLI

- `--mock-inference` removed from `run pipe` / `run bundle` / `run method`.
- `validate_run_flag_combination` loses the mutual-exclusion arm; only "`--mock-inputs` requires `--dry-run`" remains (plus, if the hidden-flag proposal is taken, "`--mock-usage` requires `--dry-run`").

### 3.5 Tests

- Leaf unit tests: dual-arm (dry vs mock) tests merge into dry tests parameterized over `is_mock_usage`; reporting assertions cover both token payloads (zero suppressed / non-zero rendered).
- `test_mock_inference_temporal.py` (wire-survival of the flag): re-key to `is_mock_usage` on the carrier.
- Fidelity tests (D6 arms): re-key from `is_mock_built`'s two triggers to DRY-only.
- Keyless-boot tests: drop the swallow-warning arm.
- **`temporal-e2e-validate` skill**: Tier 8b (the `--mock-inference` cost-assembly arms — cross-worker usage aggregated into one rendered submitter report) re-points to the dry-run + `is_mock_usage` trigger (hidden flag or submitter script per §2.3) and keeps asserting **non-zero** aggregated values. Tier 17 prose drops the "distinct from `--mock-inference`" contrast and instead states the `is_mock_usage` sub-flag. Routing battery / scope manifests mentioning `--mock-inference` updated.

### 3.6 Docs

- `docs/building-methods/pipes/run-modes-and-backends.md`: the 3×2 matrix collapses to **one mode axis** (live / dry) × two backends, plus the validation-sweep section; mock inference disappears as a user-facing concept (the internal flag is deliberately undocumented, or mentioned only as an internal testing affordance).
- `docs/under-the-hood/dry-run-mock-generation.md`, `docs/features/validation-dry-run.md`, `docs/features/cost-tracking.md`, `docs/tools/cli/run.md`: purge `--mock-inference`.
- Error pages regenerated (`make gep`).
- CHANGELOG entry under `[Unreleased]` (breaking: `--mock-inference` removed; no deprecation period per our principles).

### 3.7 Non-concerns

- **Wire/backward compatibility: none.** The Temporal integration has never shipped to prod; the `CogtRunParams` field rename needs no migration shims.
- **`pipelex-api` / platform repos**: grep for `mock_inference` at plan time; the public runner API params carry `is_mock_inference` today via `_run_core` → runner — the public surface change must ride a pipelex version bump like any other.

## 4. What does NOT change

- The leaf-mock foundation: `CogtRunParams` carrier (frozen, single-writer, stamped on every assignment, serializes across the activity boundary), the `dry_*` helpers, schema-built object mocks (`SchemaToModelFactory` + `DryRunFactory`), `DryRunMockBuildError`, the fidelity re-validation.
- Backend orthogonality and Tier 17's meaning (DRY-on-Temporal dispatches and mocks inside activities).
- The validation sweep and `act_dry_validate` (Part C) — shape, scopes, contracts all untouched.
- The forced-DRY keyless boot (`Pipelex.make(needs_inference=False)` → every run forced DRY) — it only loses the swallow-warning edge case.
- `--dry-run` and `--mock-inputs` CLI surface.

## 5. Deliberately deferred to plan time

- **PipeCompose dry-arm specifics** — the user explicitly parked this ("we'll see about those details later"). Current behavior (construct-mode `PipeComposeError` fallback, direct template rendering) stands until then.
- The exact e2e trigger mechanism for `is_mock_usage` (hidden CLI flag vs test submitter script) — §2.3 proposal: hidden flag.
- Whether `is_mock_usage=True` + `run_mode=LIVE` is a validation error (proposed) or silently ignored.
- `MockInferenceObjectFidelityError` rename.
- Sentinel-model naming consolidation (§3.2).
- Whether non-LLM leaves emit synthetic usage under `is_mock_usage=True` (§2.4 — minimal design says no).
