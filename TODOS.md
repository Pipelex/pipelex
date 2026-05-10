# TODO: Collapse `tprl_content_generation/` Workflow Layer

> **Required reading before Phase 1:** `wip/temporal-primitives/collapse-content-generation-workflow-layer-v2.md` — the architectural analysis (current `WfMake*` shapes in §0, full file-level inventory in §1, behavioral diff incl. retry / task_queue / dry-mode in §2, the asymmetric `inference_task_queue` rule, and the `make_extract_pages` pre-existing divergence). This file is the executable plan; v2 is the *why*. Do not start Phase 1 without reading v2 first — the phases below assume that context.
>
> **Branch:** `refactor/Temporal-primitives` (start work here; ship via PR to `main`).

## Goal

Replace `WfMake*` child-workflow dispatch with direct `workflow.execute_activity(act_*, …)` calls inside `WfPipeRouter`. Deletes seven workflow types, two near-duplicate generator implementations (`ContentGeneratorTop` + `ContentGeneratorChild`) and their factories, and a small assignment-types models file. Adds one new in-workflow generator. Net: history-event reduction ≈12 → 3 per content-generation call; per-LLM-call durability preserved; deletion is concentrated and mechanical.

## Status

- [x] **Phase 0 — Pre-flight audit** (uniqueness invariants for `activity_id`)
- [x] **Phase 1 — Build new generator** (no wiring)
- [x] **Phase 2 — Wire behind feature flag** (default old)
- [x] **Phase 3 — Re-point `WfTestContentGeneratorChild`**
- [x] **Phase 4 — Fix `make_extract_pages` page-views asymmetry**
- [x] ✅ **Checkpoint A** — new generator validated end-to-end, ready to flip
- [x] **Phase 5 — Flip default to new generator**
- [x] **Phase 6 — Delete old surface** (one commit)
- [ ] **Phase 7 — Update docstrings and docs**
- [ ] ✅ **Checkpoint B** — old surface gone, codebase in target state
- [ ] **Phase 8 — Final verification**

Each phase ends with `make agent-check && make agent-test` (or, during local dev, the `tests/integration/pipelex/temporal/` subset). If a phase reveals a hidden divergence, stop and update this doc + the v2 analysis before proceeding.

---

## Decisions

- **Generator class name:** `ContentGeneratorInWorkflow`. The `InWorkflow` suffix flags the load-bearing constraint at every import site — this class only works when called from inside a workflow's `run()` (because each method calls `workflow.execute_activity(…)`, which hard-fails outside a workflow context).
- **`activity_id=` for observability:** Thread `wfid` into `activity_id=` at every `workflow.execute_activity(…)` call. Preserves the Temporal Web UI per-step breadcrumb that ops use to triage failures. Uniqueness strategy depends on the Phase 0 audit outcome — see Phase 0 for the two branches.
- **Activity-id uniqueness strategy:** **Strategy (i) — "default-`wfid`-is-unique-per-workflow"**, with three mitigations recorded in Phase 0. Today's invariant is "at most one call per `ContentGeneratorProtocol` method per `WfPipeRouter` execution"; the audit (see Phase 0 below) confirms it. Phase 1 must:
    1. Use distinct method-default `wfid`s, FIXING the pre-existing duplicate where both `make_single_image` and `make_image_list` default to `"craft-image"` — split into `"craft-image-single"` and `"craft-image-list"` so the strategy is robust if a future site ever calls both within one execution.
    2. Inside `make_extract_pages` (which post-Phase-4 dispatches TWO activities), explicitly construct distinct activity_ids for the inner calls (e.g. `f"{wfid}-extract-pages"` for `act_extract_gen_extract_pages` and `f"{wfid}-render-page-views"` for the conditional `act_render_page_views`). Do not rely on the inbound single `wfid` for both.
    3. **Runtime-check the invariant**, don't just comment it. The generator carries `self._seen_activity_ids: dict[str, set[str]]` keyed by `workflow.info().workflow_id` (NOT a flat `set[str]` — the generator is set once on the hub and reused across many workflow runs, so a flat set produces cross-run false positives). The check is gated by `workflow.unsafe.is_replaying()` and short-circuits during replay, otherwise a cache-eviction replay on the same worker process would raise spurious "duplicate activity_id" errors against the populated set from the original execution. Each `make_*` method adds its computed `activity_id` to the per-workflow set and raises `ContentGenerationError` on duplicate insert. The audit proves no current call site triggers this, so the check is a regression guard, not a runtime cost. (Follow-up: the dict has no eviction; see Follow-up TODOs for the cleanup hook.)

  Strategy (ii) (per-method counter) was considered and rejected — adds complexity to solve a problem we don't have today, and would be replay-stable but harder to read in the Temporal UI.

---

## Phase 0 — Pre-flight audit

The `activity_id=wfid` strategy depends on activity-ids being unique within each workflow execution. `ContentGeneratorChild` defaults `wfid` to method-specific constants — `"craft-text"`, `"craft-object-direct"`, `"craft-object-list-direct"`, `"craft-image"`, `"jinja2-text"`, `"render-page-views"`, `"extract"` (`content_generator_child.py:95, 137, 178, 248, 294, 331, 372, 411`). Today these collide-by-design with each other within a single workflow because `make_child_workflow_id` prepends the parent's globally-unique `workflow_id`. After collapse, activity-ids only get the workflow's own scope — no parent prefix to fall back on. So we need to confirm the per-workflow invariant or add a counter.

**Cost of skipping:** a duplicate-`activity_id` runtime error on the second call. Cost of doing the audit: ~30 minutes.

- [x] Grep operator call sites for `ContentGeneratorProtocol` method calls:
    ```bash
    grep -rn "content_generator\.\(make_llm_text\|make_object\|make_object_list\|make_single_image\|make_image_list\|make_templated_text\|make_render_page_views\|make_extract_pages\)" pipelex/pipe_operators/ pipelex/pipe_controllers/ pipelex/temporal/test_extras/
    ```
    Result — six operator-side matches (no `pipe_controllers/` matches), plus six in `wf_test_content_generator_child.py`:
    - `pipe_operators/llm/pipe_llm.py:265` — `make_llm_text`
    - `pipe_operators/llm/pipe_llm.py:374` — `make_object_list`
    - `pipe_operators/llm/pipe_llm.py:392` — `make_object`
    - `pipe_operators/extract/pipe_extract.py:158` — `make_extract_pages`
    - `pipe_operators/img_gen/pipe_img_gen.py:237` — `make_image_list`
    - `pipe_operators/img_gen/pipe_img_gen.py:254` — `make_single_image`
    - `temporal/test_extras/wf_test_content_generator_child.py:64, 72, 80, 88, 98, 105` — one call per method (six methods)
- [x] For each match, inspect surrounding control flow. Findings: no call site is inside a `for`/`while` loop; no method is invoked more than once per `_live_run_operator_pipe`; the only shared default is `"craft-image"` between `make_single_image` and `make_image_list` (mitigation in Decisions).
- [x] Specifically confirm:
    - [x] `PipeLLM._live_run_operator_pipe` calls at most one of `make_llm_text` / `make_object` / `make_object_list` per execution. **Confirmed.** `pipe_llm.py:253-317`: the outer `if (text concept and not multiple) … else …` branch goes to `make_llm_text` xor `_llm_gen_object_stuff_content`; inside `_llm_gen_object_stuff_content` (`pipe_llm.py:354-402`), the `if is_multiple_output / else` branch goes to `make_object_list` xor `make_object`. The three methods are mutually exclusive within one execution.
    - [x] `PipeImgGen` calls `make_single_image` / `make_image_list` at most once per execution. **Confirmed.** `pipe_img_gen.py:236-260`: `if nb_images > 1 → make_image_list; else → make_single_image`. Mutually exclusive.
    - [x] `PipeExtract` calls `make_extract_pages` at most once per execution. **Confirmed.** `pipe_extract.py:158` is the sole, unconditional call inside `_live_run_operator_pipe`.
    - [x] `PipeCompose` and `structured_content_composer` consume `content_generator`. **Confirmed pure plumbing — no protocol-method invocation.** `pipe_compose.py` accepts `content_generator` and passes it down to `StructuredContentComposer` (line 255) and recursively to nested composers (`structured_content_composer.py:691`), but neither calls any `make_*` method on it. `_resolve_template`-style flows call `render_template(...)` directly (`structured_content_composer.py:660-665`), bypassing `make_templated_text`. So `make_templated_text` and `make_render_page_views` have NO operator-side call sites today.
    - [x] `WfTestContentGeneratorChild` calls each method at most once with the default `wfid`. **Confirmed.** Six calls (`wf_test_content_generator_child.py:64, 72, 80, 88, 98, 105`) cover six methods, each once. Method-specific defaults are pairwise distinct (`"craft-text"`, `"craft-object-direct"`, `"craft-object-list-direct"`, `"craft-image"`, `"jinja2-text"`, `"extract"`) — safe for this test workflow.
- [x] Record the result in **Decisions** above. **Strategy (i) chosen** — see Decisions section.
- [x] Note: `make_extract_pages` post-Phase-4 dispatches TWO activities (`act_extract_gen_extract_pages` + optionally `act_render_page_views`). These have different `act_*` names but share the same wrapper method. Plan their `activity_id`s explicitly: e.g. `f"{wfid}-extract"` and `f"{wfid}-render-page-views"`, or pass `wfid=` for the first and `wfid=f"{wfid}-pageviews"` for the second. **Recorded as Decisions item (2).**

**Audit result summary:**

| Method | Operator site(s) | Branch | Per-execution count | Default `wfid` |
|---|---|---|---|---|
| `make_llm_text` | `pipe_llm.py:265` | text-concept and not multiple | ≤1 | `"craft-text"` |
| `make_object` | `pipe_llm.py:392` | `not is_multiple_output` (object branch) | ≤1 | `"craft-object-direct"` |
| `make_object_list` | `pipe_llm.py:374` | `is_multiple_output` (object branch) | ≤1 | `"craft-object-list-direct"` |
| `make_single_image` | `pipe_img_gen.py:254` | `nb_images == 1` | ≤1 | `"craft-image"` ⚠ |
| `make_image_list` | `pipe_img_gen.py:237` | `nb_images > 1` | ≤1 | `"craft-image"` ⚠ |
| `make_extract_pages` | `pipe_extract.py:158` | unconditional | exactly 1 | `"extract"` |
| `make_templated_text` | (none in operators — only test workflow) | — | — | `"jinja2-text"` |
| `make_render_page_views` | (none in operators — only invoked internally from `make_extract_pages`) | — | — | `"render-page-views"` |

⚠ Pre-existing duplicate default `"craft-image"` shared by `make_single_image` and `make_image_list`. They never run together today (mutually exclusive in `PipeImgGen`; `WfTestContentGeneratorChild` only calls `make_single_image`). Phase 1 must split them into `"craft-image-single"` / `"craft-image-list"` — see Decisions.

**Conclusion:** Today's per-workflow uniqueness invariant **holds** for Strategy (i). Strategy (i) is adopted, with the mitigations documented in Decisions (distinct method-default `wfid`s including the `craft-image` split, distinct activity_ids inside `make_extract_pages`, and a runtime uniqueness check in the new generator).

**Verification:** no code changes. This phase produces an entry in **Decisions** and unblocks Phase 1.

---

## Phase 1 — Build new in-workflow content generator ✅

Add the new generator next to the existing files. No wiring yet — just code.

- [x] Create `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py`.
- [x] Define class `ContentGeneratorInWorkflow` implementing `ContentGeneratorProtocol` with all current methods.
- [x] At every `workflow.execute_activity(…)` site, pass `start_to_close_timeout=worker_config.workflow_execution_timeout` and `retry_policy=worker_config.retry_policy`.
- [x] Thread `wfid` into `activity_id=` per **Strategy (i)**.
- [x] Runtime uniqueness check from Decisions item (3) — keyed by `workflow.info().workflow_id` (the generator instance is shared across workflow runs via the hub, so the per-instance set in the original plan was insufficient; scoped by workflow_id instead).
- [x] Wrap each method body in `try/except ActivityError` to translate `ApplicationError → TemporalError.from_app_error(...)`. Did NOT carry over `except PipelexError → TemporalError.from_message_exception(...)` clause.
- [x] Keep the `@update_job_metadata` decorator on each method.
- [x] Inline comment at the LLM-text site stating the asymmetric routing rule.
- [x] Create factory module `content_generator_in_workflow_factory.py`.
- [x] Unit tests at `tests/unit/pipelex/temporal/test_content_generator_in_workflow.py` covering: positive task_queue assertion for `make_llm_text`, negative task_queue absence for non-LLM methods, activity_id threading per method, distinct default ids for image methods (`craft-image-single` / `craft-image-list`), single-vs-two-activity branching in `make_extract_pages`, the runtime duplicate check, replay-safety of the duplicate check, and `ActivityError → TemporalError` translation (both the `ApplicationError`-cause and other-cause branches).

**Verification:** `make agent-check` passes; targeted unit tests green.

---

## Phase 2 — Wire behind a temporary feature flag ✅

- [x] In `pipelex/pipelex.py`, env-flag-gated branch on `os.environ.get("PIPELEX_USE_IN_WORKFLOW_CONTENT_GENERATOR")` (renamed in Phase 5 to `PIPELEX_USE_LEGACY_CONTENT_GENERATOR` when the polarity flipped). Default OFF (legacy was the default at Phase 2).
- [x] Did NOT add to `pipelex.toml`. Transient.
- [x] Mirrored env-flag branch in `tests/integration/pipelex/temporal/conftest.py` and `test_payload_codec_pipeline.py`.
- [x] Validated locally with flag ON: targeted Temporal subsets pass — `library_crate/`, `tracing/` (incl. `test_split_worker_usage.py` that exercises the asymmetric `inference_task_queue` routing), `content_generation/`, `workflows/`.
- [x] Validated with flag OFF: same subsets pass identically (baseline preserved).

**Verification:** `make agent-check` passes; targeted Temporal subsets pass with both flag values.

---

## Phase 3 — Re-point `WfTestContentGeneratorChild` ✅

- [x] Updated `pipelex/temporal/test_extras/wf_test_content_generator_child.py` to import and construct via `ContentGeneratorInWorkflowFactory`.
- [x] `is_dry_run` branch still picks `ContentGeneratorDry`.
- [x] `tests/integration/pipelex/temporal/content_generation/test_tprl_content_generator_child.py` passes.

The test workflow now exercises the new code unconditionally regardless of flag state.

**Verification:** `make agent-check` passes; content_generation targeted subset green.

---

## Phase 4 — Fix `make_extract_pages` page-views asymmetry ✅

Implemented inline within Phase 1 since `make_extract_pages` is a Phase 1 method.

- [x] Signature follows `ContentGeneratorProtocol` (non-None params).
- [x] Dispatches `act_extract_gen_extract_pages` first.
- [x] If `should_include_page_views` is true:
    - [x] `document_uri` → dispatch `act_render_page_views`.
    - [x] `image_uri` → build single-element `[ImageContent(url=extract_input.image_uri)]` inline.
- [x] Length-match validation; raises `ContentGenerationError` on mismatch.
- [x] Attaches via `pop(0)` loop.
- [x] No double-emit when false.
- [x] Distinct `activity_id`s: `f"{base_id}-pages"` and `f"{base_id}-render-page-views"`.
- [x] Unit tests cover all branches (no-page-views, image_uri, document_uri+document branch).
- [x] Real-PDF integration coverage added (post Phase 6):
    - New test fixture workflow `pipelex/temporal/test_extras/wf_test_content_generator_pdf_page_views.py` (`WfTestContentGeneratorPdfPageViews`) registered in `TEMPORAL_TEST_WORKFLOWS`.
    - New test class `tests/integration/pipelex/temporal/content_generation/test_tprl_content_generator_pdf_page_views.py:TestTprlContentGeneratorPdfPageViews` exercises the `document_uri` + `should_include_page_views=True` branch end-to-end through real Temporal: `act_extract_gen_extract_pages` for OCR + `act_render_page_views` for pypdfium2 rendering, with the in-workflow page_view attachment loop asserted page-by-page. Marked `@extract @inference @dry_runnable @temporal`.
    - Uses local 2-page `tests/data/documents/Job-Offer.pdf` (added as `PipeTestCases.JOB_OFFER_PDF_LOCAL` in `tests/integration/pipelex/temporal/test_data.py`) — multi-page catches `pop(0)` ordering bugs that a 1-page PDF would not.

**Verification:** `make agent-check` passes; unit tests verify all branches.

---

## ✅ Checkpoint A — Ready to flip (REACHED)

State at this checkpoint:
- New generator (`ContentGeneratorInWorkflow`) implemented in `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py`, factory in `content_generator_in_workflow_factory.py`, unit tests in `tests/unit/pipelex/temporal/test_content_generator_in_workflow.py`.
- Wired behind env-flag `PIPELEX_USE_IN_WORKFLOW_CONTENT_GENERATOR` (Phase 5 renamed to `PIPELEX_USE_LEGACY_CONTENT_GENERATOR`) in `pipelex.py` and both Temporal conftests (`tests/integration/pipelex/temporal/conftest.py` and `test_payload_codec_pipeline.py`); default OFF at Checkpoint A.
- `pipelex/temporal/test_extras/wf_test_content_generator_child.py` re-pointed to construct the new generator unconditionally (this is a test fixture workflow; the env flag does not gate it).
- `make_extract_pages` page-views asymmetry fixed; both single-image (`image_uri`) and multi-page (`document_uri`) branches covered by unit tests.
- `ContentGeneratorChild` and `ContentGeneratorTop` still exist; production traffic still goes through `ContentGeneratorChild` (flag OFF).

Validated locally — targeted Temporal subsets pass with both flag values: `library_crate/`, `tracing/` (incl. `test_split_worker_usage.py`, which is the only test exercising the asymmetric `inference_task_queue` routing rule and so the load-bearing test for that rule under the new code path), `content_generation/`, `workflows/`.

Notable design fix applied during Phase 1 (after a silent-failure-hunter review): the runtime activity-id uniqueness check is keyed by `workflow.info().workflow_id` (dict of sets) rather than a flat instance-level set, AND short-circuits during replay via `workflow.unsafe.is_replaying()`. The original plan's flat set would have produced cross-run false positives; without the replay guard, cache-eviction replays on the same worker process would have raised spurious duplicates against the populated set from the original execution. See Decisions item (3) and the file's docstring/comments.

Code review feedback applied (silent-failure-hunter + code-reviewer agents):
- C1 (replay false positives) — fixed via `is_replaying()` guard.
- S5 (no test coverage on the catch blocks) — added two tests for `ActivityError → TemporalError` translation (`ApplicationError`-cause path and other-cause re-raise path).
- Findings deferred (mirror legacy behavior or low-value vs. blast-radius): orphan storage on partial `make_extract_pages` failure (S2), `nb_items` parameter being silently ignored (S3, pre-existing across all generators), code duplication between standalone `make_render_page_views` and the inline dispatch in `make_extract_pages` (S4), choice of `log` vs `workflow_log` in catch blocks (S6, replicates legacy `wf_make_images.py` pattern).
- Findings filed as Follow-up TODOs: `_seen_activity_ids` unbounded growth.

Working-tree state (uncommitted):
- 8 changed files (3 added, 5 modified). Run `git status` to see them. Nothing has been committed yet — Checkpoint A is the natural commit boundary; recommended to commit before Phase 5 so the flip can be reverted cheaply.

Open questions / decisions for next session:
- [ ] Land Checkpoint A as a standalone commit before Phase 5 (strongly recommended).

---

## Phase 5 — Flip the feature flag default ✅

- [x] In `pipelex/pipelex.py`, flipped the env-flag default. Renamed the variable to `PIPELEX_USE_LEGACY_CONTENT_GENERATOR` so the polarity is self-documenting: unset → new in-workflow generator (default); set → legacy `ContentGeneratorChild` escape hatch.
- [x] Mirrored the rename + flipped polarity in `tests/integration/pipelex/temporal/conftest.py` and `tests/integration/pipelex/temporal/test_payload_codec_pipeline.py`.
- [x] `make agent-check` passes (ruff/pyright/mypy clean).
- [x] `make agent-test` passes (full suite).
- [x] Targeted `tests/integration/pipelex/temporal/content_generation/` (9 tests) and `tests/integration/pipelex/temporal/tracing/` (36 tests, including `test_split_worker_usage.py` which is the load-bearing test for the asymmetric `inference_task_queue` routing rule) pass under the new default.
- [ ] Optional: run against a real Temporal server (`.venv/bin/pytest tests/integration/pipelex/temporal/ --temporal-server local`) — not run this session (requires local Temporal server).
- [ ] Optional: manual UI inspection of a `library_crate/` pipeline run — requires human inspection.

**Note for Phase 6:** the env var was renamed from `PIPELEX_USE_IN_WORKFLOW_CONTENT_GENERATOR` to `PIPELEX_USE_LEGACY_CONTENT_GENERATOR`. Phase 6 must grep/delete the new name.

---

## Phase 6 — Delete the old surface (one commit) ✅

Per the project's "no backward compatibility" rule, deleted in a single commit:

**Files deleted under `pipelex/temporal/tprl_content_generation/`:**

- [x] `wf_make_llm_text.py`
- [x] `wf_make_object.py`
- [x] `wf_make_images.py`
- [x] `wf_make_jinja2_text.py`
- [x] `wf_make_extract.py`
- [x] `wf_render_page_views.py`
- [x] `content_generator_top.py`
- [x] `content_generator_top_factory.py`
- [x] `content_generator_child.py`
- [x] `content_generator_child_factory.py`
- [x] `content_generator_models.py`

**Test files deleted:**

- [x] `tests/integration/pipelex/temporal/content_generation/test_tprl_content_generator_top.py`
- [x] `tests/integration/pipelex/temporal/content_generation/test_tprl_make_content_generator.py`
- [x] `tests/integration/pipelex/temporal/workflows/test_wf_gen_text.py` (already commented-out)
- [x] `tests/integration/pipelex/temporal/workflows/test_wf_jinja2.py` (already commented-out)

**Edits:**

- [x] `pipelex/temporal/tasks.py` — dropped the `WfMake*` / `WfRenderPageViews` import lines; the `crafting` `TaskPack` now has `workflow_list=[]`. Activity list unchanged.
- [x] `pipelex/pipelex.py` — removed the feature-flag branch (`PIPELEX_USE_LEGACY_CONTENT_GENERATOR` and the surrounding `if/else`); when `temporal.is_enabled` is true, `ContentGeneratorInWorkflowFactory.make_content_generator_in_workflow(...)` is now constructed unconditionally. Dropped the `os` import (no longer used).
- [x] `tests/integration/pipelex/temporal/conftest.py` — dropped the env-flag branch and inline `import os`; conftest now imports `ContentGeneratorInWorkflowFactory` at the top of the function and constructs it unconditionally.
- [x] `tests/integration/pipelex/temporal/test_payload_codec_pipeline.py` — same pattern as the parent conftest.
- [x] `tests/integration/pipelex/temporal/content_generation/conftest.py` — removed the `ContentGeneratorChild` / `ContentGeneratorChildFactory` / `ContentGeneratorTopFactory` imports along with the `top_crafter` and `child_crafter` fixtures and their now-unused supporting imports (`AsyncGenerator`, `pytest_asyncio`, `TemporalClient`, `ContentGeneratorDry`, `ContentGeneratorProtocol`, `GeneratedContentFactory`, `PipeRunMode`, `TemporalWorkerEnvironment`).
- [x] `test_tprl_content_generator_child.py` — no edit needed; only imports the surviving `WfTestContentGeneratorChild` test fixture workflow.
- [x] **Bonus:** removed the now-stale code comment in `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py:211` that referenced the deleted `ContentGeneratorChild`.

**Verification:**

- [x] `make cleanderived` (regenerated `_generated_model_sets.py` afterwards via `pipelex-dev preprocess-test-models --generate-fixtures --profile ci`, otherwise pyright fails on the missing-import).
- [x] `make agent-check` — ruff + plxt + pyright + mypy clean.
- [x] `make agent-test` — full suite passes.
- [x] `make tb` — boot test passes.

**Notes / known follow-ups handed to Phase 7:**

- Three stale references to `WfMakeLLMText` survive in `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py` (lines 3, 63, 80). These are docstrings/comments; Phase 7 explicitly owns this rewrite together with `tracing/helpers.py` and `docs/under-the-hood/`.
- The `WfTestContentGeneratorChild` test fixture workflow (in `pipelex/temporal/test_extras/`) is intentionally kept — it was re-pointed in Phase 3 to use the new in-workflow generator and is the only thing Phase 6 leaves with "Child" in the name.

---

## Phase 7 — Update docstrings and docs

- [ ] `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py` — rewrite the module docstring and surrounding fixture comments to describe the direct-activity-call topology (no more `WfMakeLLMText` child workflow; the activity is now dispatched from `ContentGeneratorInWorkflow.make_llm_text` inside `WfPipeRouter`).
- [ ] `tests/integration/pipelex/temporal/tracing/helpers.py` — update the comments around `make_split_workers` and `_runner_isolated_act_llm_gen_text` for the same topology change.
- [ ] `docs/under-the-hood/pipe-routing-and-execution.md` — update the pipe-routing table and any inline references to `WfMake*` to reflect direct activity dispatch from `WfPipeRouter`.
- [ ] Search the rest of the docs for `WfMake` references and update or remove:
    ```bash
    grep -rn "WfMake\|wf_make_" docs/
    ```
- [ ] Update CHANGELOG under `[Unreleased]`: brief note that `tprl_content_generation/` workflow layer was collapsed; durability semantics unchanged; per-step naming preserved as `activity_id` (instead of as a child workflow id).

**Verification:** `make agent-check`. Docs-only changes don't need a full test run, but rerun `make agent-test` if any docs are imported by tests (they aren't, currently).

---

## ✅ Checkpoint B — Codebase in target state

State at this checkpoint:
- `tprl_content_generation/` contains only the seven `act_*.py` activity files and the new `content_generator_in_workflow.py` (+ its factory).
- `pipelex.py` always wires the new generator when `temporal.is_enabled`.
- All `WfMake*` references gone from code, tests, and docs.
- Page-views augmentation works in Temporal mode.
- All Temporal integration tests pass.

---

## Phase 8 — Final verification

- [ ] `make agent-check && make agent-test` — full suite green.
- [ ] `.venv/bin/pytest tests/integration/pipelex/temporal/ --temporal-server local` — against a real Temporal server.
- [ ] Manual smoke: run a multi-step `PipeSequence` end-to-end and confirm via Temporal UI that activities appear directly under `WfPipeRouter`.
- [ ] Replay-history check: confirm no test fixtures depend on old `WfMake*` history.
    - [ ] `grep -rn "WfMake\|wf_make_\|WfRenderPageViews\|wf_render_page_views" tests/` returns nothing in the resulting tree.
    - [ ] No binary or JSON replay fixture references the old workflow types: `find tests/ \( -name "*.bin" -o -name "*history*" -o -name "*replay*" \) -type f`. Inspect any hits — if pickled `WorkflowEvent` data exists, attempt replay against the new tree to confirm break.
    - [ ] If no replay fixtures exist (expected per v2 §6 "Replay-history compatibility: none"), record that finding explicitly.

> Deploy/ship operations are out of scope for this plan — handled separately when the branch is ready to land.

---

## Verification matrix (quick reference)

| After phase | Command |
|---|---|
| 0 | (no code changes — record finding in Decisions) |
| 1 | `make agent-check` |
| 2 | `make agent-check && make agent-test` (flag OFF and ON locally) |
| 3 | `make agent-check && make agent-test` |
| 4 | `make agent-check && make agent-test` |
| 5 | `make agent-test`; `--temporal-server local`; manual UI inspection |
| 6 | `make cleanderived && make agent-check && make agent-test && make tb` |
| 7 | `make agent-check` |
| 8 | full suite + real-server suite + manual smoke + replay-history check |

---

## Where bugs are likely to hide (from v2 §6)

- **Asymmetric `task_queue=worker_config.inference_task_queue` rule.** Easy to forget at the LLM-text site or to over-apply elsewhere. Covered by the unit test added in Phase 1 — including the negative assertion that non-LLM-text methods must NOT pass `task_queue=`. Mis-routing image-gen to the inference queue would break split-worker production where the runner doesn't register the image-gen activity.
- **`activity_id` collisions** under repeated calls — see Phase 0. The default `wfid` values are method-specific constants; they do NOT disambiguate repeated calls to the same method. The Phase 1 runtime check (`dict[workflow_id, set[str]]` on the singleton generator, gated by `workflow.unsafe.is_replaying()`) converts this from a documented invariant to a checked one and is replay-safe (cache-eviction replays do not raise spurious duplicates).
- **`model_validate(obj.model_dump(mode="json", serialize_as_any=True))` round-trips** for `make_object` / `make_object_list`. Required because the activity boundary returns a generic `BaseModel`. Don't drop these. **Use `mode="json"` on BOTH** — `ContentGeneratorChild.make_object_list:189` omits it today (pre-existing asymmetry vs. `make_object:148`).
- **Page-views augmentation** in `make_extract_pages` (Phase 4). Mirror the direct generator's branching exactly: don't double-emit when `should_include_page_views` is false; handle both `document_uri` (multi-page render) and `image_uri` (single-image) inputs; assert length match. Both branches are covered by unit tests; the `document_uri` branch additionally has a real-PDF end-to-end integration test (`TestTprlContentGeneratorPdfPageViews`).
- **Test infrastructure bypass.** Both `tests/integration/pipelex/temporal/conftest.py` and `test_payload_codec_pipeline.py` explicitly call `pipelex_hub.set_content_generator(...)` after `Pipelex.make()`, so the env-flag branch in `pipelex.py` is bypassed in tests. Phase 2 must mirror the env flag in both conftests; Phase 6 must update both as part of cleanup.

---

## Follow-up TODOs (out of scope for this PR)

- **Watch task-queue saturation post-deploy.** Today, a `PipeSequence` of N inference calls schedules N child workflows, decoupling activity scheduling across child task lists. Post-collapse, all N activities run through the parent's task list (or `inference_task_queue` for LLM-text). For deep pipelines (N > 50), single-queue QPS could spike. After the first production deploy after this lands, watch `ScheduleToStartLatency` on the parent worker queue and on `inference_task_queue`. If it rises, investigate batching or per-pipe queue assignment. Not blocking; upside (history-event reduction) dominates.
- **Drop `make_render_page_views` from `ContentGeneratorProtocol`** if no operator caller emerges within one release cycle. Today it's only invoked internally from `make_extract_pages`; post-Phase-4 the same is true. The Protocol method becomes dead code from the operator side. Inline its behavior into `make_extract_pages` and remove from the Protocol + every implementation. Estimated savings: ~50 lines across four files.
- **Fix `ContentGenerator.make_extract_pages` Protocol-violating signature.** `content_generator.py:259-267` declares `extract_job_params: ExtractJobParams | None = None` and `extract_job_config: ExtractJobConfig | None = None`, while the Protocol requires non-None. Tighten the signature to match the Protocol; default-construct at the operator boundary instead. Pre-existing divergence; project's "flag and fix" rule applies, but bundling into this refactor would expand the diff for marginal gain.
- **Bound `_seen_activity_ids` growth in `ContentGeneratorInWorkflow`.** The dict is keyed by `workflow.info().workflow_id`, gated by `workflow.unsafe.is_replaying()` to be replay-safe, but never evicts entries. A long-running worker accumulates one entry per processed workflow id over its lifetime. Add eviction on workflow completion via a context manager hook, or move the set into workflow-local state (e.g., a contextvar set at the start of `WfPipeRouter.run` and cleared in `finally`). Cheap follow-up; not blocking Checkpoint A.
- **Update v2 doc claim.** `wip/temporal-primitives/collapse-content-generation-workflow-layer-v2.md` §5 step 3 says image-gen path in `wf_test_content_generator_child.py:87-92` is commented out. It is not — the path is live. Doc-only fix.
