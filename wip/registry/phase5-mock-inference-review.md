    # Phase 5 (`--mock-inference`) — review findings + verify/solve plan

Multi-angle code review of the Phase 5 staged changes (the `--mock-inference` flag + the shared `cogt/content_generation/dry_mock.py` leaf mocks). **No correctness bug was found** by any finder angle — the change is well-tested and the TODOS/docstrings already pre-empt most review questions. What follows is the punch-list that did survive: one real-money safety hazard, one documented runtime-crash risk, and some cleanup. Each item has a **verify** step (reproduce / pin with a failing test first) and a **solve** step.

**Status:** F1 **DONE** (cheap hard guard landed, extended to web search beyond the review's original img-gen/extract scope). F2 and the rest remain a *deliberate, already-documented* deferral (TODOS §7 + [`../dry-run-refactor/followup-leaf-run-mode-mock.md`](../dry-run-refactor/followup-leaf-run-mode-mock.md)); reproduced here with a concrete remediation so the decision is explicit rather than lost. F3–F5 are mechanical and can land whenever.

## Triage

| # | Finding | Type | Recommended action |
|---|---------|------|--------------------|
| F1 | `--mock-inference` on an img-gen / extract / **search** pipe silently calls the real provider and spends | Safety / altitude (documented) | ✅ **DONE** — cheap hard guard landed (raise at those leaves); full leaf mock stays B2 |
| F2 | Object mock built from the schema-reconstructed class can fail re-validation against the original class | Correctness, plausible (documented) | Wrap the failure in a clear typed error now; full fidelity is B2 |
| F3 | The `--mock-inference`/`--dry-run` + `--mock-inputs`/`--dry-run` guards are copy-pasted across the run subcommands | Cleanup | Extract one shared flag-combination validator |
| F4 | `mock_llm_gen_object_list` omits the first-item `pipe_code="mock_main"` coordination of the dry path | Divergence, likely-irrelevant | Document why it's intentionally omitted (don't mirror) |
| F5 | `build_mock_object` is unused by `ContentGeneratorDry.make_object`; the two object mocks duplicate `schema→report→build` | Cleanup | Optional dedup |

---

## F1 — Silent provider spend on img-gen / extract pipes  ⚠️ highest impact

**What.** `JobMetadata.is_mock_inference` is honored *only* at the LLM leaf. An img-gen or extract pipe run with `--mock-inference` takes the normal LIVE dispatch and hits the **real** provider — it is billed — while the flag's help text promises "fakes AI calls … no actual inference calls". The failure is silent: the user gets a real result and a real bill from a flag whose entire purpose is "no spend".

**Evidence.**

- `pipelex/cogt/content_generation/llm_generate.py:14,29,50` — the `is_mock_inference` early-returns exist on the three LLM leaves only.
- `pipelex/cogt/content_generation/img_gen_generate.py:10,23` (`img_gen_single_image`, `img_gen_image_list`) and `pipelex/cogt/content_generation/extract_generate.py:9` (`extract_gen_pages`) — no `is_mock_inference` branch; they dispatch to the real worker regardless.
- `TODOS.md` §7 and the followup doc already record this as a deliberate Phase 5 scope cut, with the noted mitigation: *"make the img-gen/extract leaf raise under `is_mock_inference` rather than silently spend."*

**Verify.**

1. Write a failing integration test (sibling to `tests/integration/pipelex/pipeline/test_mock_inference_direct.py`): a minimal `PipeImgGen` (and a `PipeExtract`) bundle run with `is_mock_inference=True`, asserting the run **raises the guard error** and the img-gen / extract worker getter is never called. Today it would instead reach the real worker — so first assert "worker not called" to watch it fail (proves the spend path), then flip the assertion to "raises".

**Solve (recommended: the cheap hard guard now).**

- Add a typed error — `MockInferenceUnsupportedError(PipelexError)` in `pipelex/cogt/content_generation/exceptions.py` (that module already hosts `PipelexError` subclasses, so the docs generator + `type_uri` test pick it up automatically).
- At the top of `img_gen_single_image` / `img_gen_image_list` (`img_gen_generate.py`) and `extract_gen_pages` (`extract_generate.py`), `if <assignment>.job_metadata.is_mock_inference: raise MockInferenceUnsupportedError(msg)` with a message that names the leaf and points at `--dry-run` for full no-spend coverage. This is the same single-flag read the LLM leaf already does — right depth, not a special case.
- Templating (`templating_generate.py:5`) is pure Jinja with no provider call, so it needs no guard; do not add one.

**Decision.** This is a documented tradeoff, so it needs a sign-off rather than a reflexive patch. The lean is **fix now**: a flag sold as "no spend" that can silently spend is the kind of footgun that should fail loud, and the guard is a few lines per leaf that the eventual B2 full-mock simply replaces. The alternative — leave it deferred and rely on the docs — is only defensible because Phase 6 Tier 8b uses LLM-only bundles; the moment anyone points `--mock-inference` at an img-gen pipe, real money moves.

**As built (cheap hard guard).**

- New typed error `MockInferenceUnsupportedError(PipelexError)` in `pipelex/cogt/content_generation/exceptions.py` — `error_domain = INPUT` (caller picked an unsupported flag/pipe combination they can fix), `_authors_caller_facing_message = True` (the message is pure guidance, no secrets). A `for_operation(operation)` classmethod owns the wording so all call sites share one message and can't drift. Docs page `docs/errors/mock-inference-unsupported-error.md` regenerated; error-class-location + `type_uri` uniqueness tests stay green.
- Guards (raise before any provider call when `job_metadata.is_mock_inference`): `img_gen_single_image` / `img_gen_image_list` (`img_gen_generate.py`), `extract_gen_pages` (`extract_generate.py`), and — beyond the review's original scope — `PipeSearch._live_run_operator_pipe` (`pipe_operators/search/pipe_search.py`). Search has no `cogt/content_generation` leaf, so its spend happens in the operator's live path; the guard lives there. Templating stays unguarded (pure Jinja, no provider call).
- Tests: leaf-direct unit tests `test_img_gen_generate_mock_guard.py` / `test_extract_generate_mock_guard.py` (flag on → raises + worker getter untouched; flag off → real worker path runs), and an operator-through-router integration test `test_pipe_search_mock_inference_guard.py` (raises through the real router; `SearchWorkerFactory.make_search_worker` never called — `MockInferenceUnsupportedError` is a plain `PipelexError`, so `PipeOperator._live_run_pipe` does not re-wrap it).
- The eventual B1 leaf mock (`run_mode=DRY`, followup-leaf) simply replaces each guard with a real synthetic-output branch.

---

## F2 — Object mock can fail re-validation against the original class  (plausible, documented)

**What.** `mock_llm_gen_object` / `mock_llm_gen_object_list` build the instance from the **schema-reconstructed** class (`SchemaToModelFactory.make_from_json_schema`), because the leaf carries only the JSON schema. `ContentGenerator.make_object` then re-validates that data against the **original** class. polyfactory fills the reconstructed class with random data; if the JSON-schema round-trip dropped a format / pattern constraint (encoded via `json_schema_extra`), the random value can satisfy the reconstructed class but be **rejected** by the original → `ValidationError` mid-run. This is *new* relative to both the dry path (which builds the original class directly) and the live path (the LLM is steered by the prompt toward valid data).

**Evidence.**

- `pipelex/cogt/content_generation/dry_mock.py:163,185` — both object mocks build via `SchemaToModelFactory.make_from_json_schema` then `build_mock_object`.
- `pipelex/cogt/content_generation/content_generator.py:85,108` — re-validation `object_class.model_validate(raw_obj.model_dump(serialize_as_any=True))`.
- The `mock_llm_gen_object` docstring itself flags the gap; the followup doc §8 owns the durable fix.
- The DIRECT integration test only covers `Topic` (a plain `name: text`), which survives the round-trip — so the failing case is uncovered.

**Verify.**

1. Add a unit/integration case with an output concept whose structure has a constrained field (a `pattern` / format hint via `json_schema_extra`) and run it under `--mock-inference`; confirm whether `make_object` raises `ValidationError`. This both proves the gap is reachable and becomes the regression test for whatever fix lands.

**Solve.**

- **Now (cheap):** catch the `ValidationError` at the `make_object` / `make_object_list` re-validation boundary *only on a mock-inference run* and re-raise as a typed error that names the object class and explains the known schema-round-trip fidelity gap (so a confusing pydantic stacktrace becomes an actionable message). Do not broaden the catch beyond the mock path.
- **Full fix (B2):** thread the original class to the leaf (or have the leaf build against the original class when running in-process), per `followup-leaf-run-mode-mock.md` §8. Out of scope for this branch.

**Decision.** Deferred design limitation — keep it deferred, but upgrade the failure mode from "opaque pydantic crash" to "clear typed error" now, since that is a few lines and makes the documented gap self-explaining when someone hits it.

---

## F3 — Run-subcommand flag-combination guards are copy-pasted  (cleanup)

**What.** Each of the `pipe` / `method` / `bundle` run subcommands carries the same two hand-written guard blocks: `--mock-inputs requires --dry-run` and (new in Phase 5) `--mock-inference cannot be combined with --dry-run`. Same comment, same `typer.secho(..., err=True)`, same `raise typer.Exit(1)`, repeated per command.

**Evidence.**

- `pipelex/cli/commands/run/bundle_cmd.py:115` and `:128`, `method_cmd.py:117` and `:130`, `pipe_cmd.py:121` and `:134`.

**Verify.**

1. The existing `tests/unit/pipelex/cli/test_mock_inference_cli_guard.py` (rejects the `--mock-inference --dry-run` combo on every subcommand) plus the `--mock-inputs requires --dry-run` coverage are the regression net — they must stay green after the refactor with no change to their assertions.

**Solve.**

- Add one helper, e.g. `validate_run_flag_combination(*, dry_run, mock_inference, mock_inputs) -> None` in `pipelex/cli/commands/run/_run_core.py`, that raises `typer.Exit(1)` with the right message for each illegal combination, and call it once at the top of each subcommand in place of the inlined blocks. One owner of "which run-flag combinations are legal", three call sites that can no longer drift.

**Decision.** Mechanical, low-risk; land whenever F1/F2 are touched.

---

## F4 — `mock_llm_gen_object_list` omits the `pipe_code="mock_main"` first-item coordination  (likely-irrelevant divergence)

**What.** The dry `ContentGeneratorDry.make_object_list` sets `item.pipe_code = "mock_main"` on the first list item to satisfy `BundleHeaderSpec.main_pipe` (`examples=["mock_main"]`) during bundle dry-validation. The extracted `mock_llm_gen_object_list` does not.

**Evidence.**

- `pipelex/cogt/content_generation/content_generator_dry.py:102-105` (the dry coordination) vs `pipelex/cogt/content_generation/dry_mock.py:185` (the mock, no coordination).
- The `mock_main` convention is a dry-validation artifact, also present at `core/memory/working_memory_factory.py:242` and `pipe_controllers/batch/pipe_batch.py:283`.

**Verify.**

1. Confirm the negative: bundle dry-validation runs under `run_mode=DRY` (which swaps in `ContentGeneratorDry`, never the leaf mock), so a LIVE `--mock-inference` run cannot reach the `BundleHeaderSpec.main_pipe` check. Grep the callers of the leaf mock to confirm there is no LIVE path that asserts `pipe_code == "mock_main"`.

**Solve.**

- Do **not** mirror the assignment (it would be cargo-culting a dry-only artifact into a LIVE path). Instead add a one-line comment at `dry_mock.py:185` stating the omission is intentional because `--mock-inference` is LIVE and never drives bundle dry-validation. If the verify step surprises us and a real path exists, mirror the assignment instead.

**Decision.** Lowest priority; comment-only unless verification finds a reachable path.

---

## F5 — Minor reuse  (optional cleanup)

**What.** `build_mock_object` (`dry_mock.py`) is the new shared "build one polyfactory instance" helper, but `ContentGeneratorDry.make_object` (`content_generator_dry.py:74`) still inlines `DryRunFactory.make_dry_run_factory(object_class).build()`. Separately, `mock_llm_gen_object` and `mock_llm_gen_object_list` repeat the `make_from_json_schema → report_mock_inference_llm_job → build_mock_object` sequence.

**Solve.**

- Point `ContentGeneratorDry.make_object` at `build_mock_object`.
- Extract a small `_mock_object_from_schema(object_assignment)` in `dry_mock.py` that does the schema reconstruction + reporting, used by both object mocks.

**Decision.** Cosmetic; fold in only if F1/F2 already have the file open. Note these helpers collapse further in B2, so don't over-invest.

---

## Suggested sequencing

1. **F1 + F3 together** (they touch the guard/leaf surface and share new tests). F1 is the only item with user-visible money impact — do it first, behind the sign-off.
2. **F2** — add the typed-error wrap + the constrained-field regression test.
3. **F4 / F5** — comment + optional dedup, opportunistic.

## Verification gate (before wrapping)

- `make agent-check` (ruff/plxt, pyright, mypy) clean.
- `make agent-test` green, including the new F1 guard test and the F2 constrained-field test.
- The Temporal arm (`tests/integration/pipelex/temporal/tracing/test_mock_inference_temporal.py`) is `gha_disabled`; if F1/F2 touch the activity-side leaf path, re-verify it locally/serially with `--temporal-server none` as the as-built note describes.
- New error classes (F1, optionally F2) appear under `docs/errors/` after `make generate-error-pages`, and the error-class-location test stays green.
