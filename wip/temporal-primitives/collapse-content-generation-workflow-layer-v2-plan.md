# Plan: Collapse `tprl_content_generation/` Workflow Layer

> Companion to `collapse-content-generation-workflow-layer-v2.md` (the analysis). This file is the executable, checkbox-tracked plan. Update it as work lands.

## Goal

Replace `WfMake*` child-workflow dispatch with direct `workflow.execute_activity(act_*, …)` calls inside `WfPipeRouter`. Deletes seven workflow types, two near-duplicate generator implementations (`ContentGeneratorTop` + `ContentGeneratorChild`) and their factories, and a small assignment-types models file. Adds one new in-workflow generator. Net: history-event reduction ≈12 → 3 per content-generation call; per-LLM-call durability preserved; deletion is concentrated and mechanical.

## Status

- [ ] **Phase 1 — Build new generator** (no wiring)
- [ ] **Phase 2 — Wire behind feature flag** (default old)
- [ ] **Phase 3 — Re-point `WfTestContentGeneratorChild`**
- [ ] **Phase 4 — Fix `make_extract_pages` page-views asymmetry**
- [ ] ✅ **Checkpoint A** — new generator validated end-to-end, ready to flip
- [ ] **Phase 5 — Flip default to new generator**
- [ ] **Phase 6 — Delete old surface** (one commit)
- [ ] **Phase 7 — Update docstrings and docs**
- [ ] ✅ **Checkpoint B** — old surface gone, codebase in target state
- [ ] **Phase 8 — Final verification and ship**

Each phase ends with `make agent-check && make agent-test` (or, during local dev, the `tests/integration/pipelex/temporal/` subset). If a phase reveals a hidden divergence, stop and update this doc + the v2 analysis before proceeding.

---

## Open decisions to resolve before starting

- [ ] **Generator class name.** v2 suggested `ContentGeneratorInWorkflow`. Confirm or pick a better name (alternatives: `ContentGeneratorActivities`, `ContentGeneratorTemporal`).
- [ ] **`activity_id=` for observability.** Today, child workflows get a Temporal-UI-visible name from the parent's `wfid`. After collapse, only `activity_id` remains (auto-assigned). Decision: (a) reproduce the per-step naming by passing `activity_id=` from the `wfid` arg, or (b) accept logs + `JobMetadata.content_generation_job_id` as sufficient. If (a), thread `wfid` into every `workflow.execute_activity(…)` call in Phase 1.

---

## Phase 1 — Build new in-workflow content generator

Add the new generator next to the existing files. No wiring yet — just code.

- [ ] Create `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py`.
- [ ] Define the class (resolved name from open decisions) implementing `ContentGeneratorProtocol` with the nine current methods:
    - [ ] `make_llm_text` → `act_llm_gen_text`, with `task_queue=worker_config.inference_task_queue`
    - [ ] `make_object` → `act_llm_gen_object`, plus `model_validate(obj.model_dump(mode="json", serialize_as_any=True))` round-trip
    - [ ] `make_object_list` → `act_llm_gen_object_list`, plus per-item `model_validate(...)` round-trip
    - [ ] `make_image_content` → unchanged from `ContentGeneratorChild` (no activity hop; uses `_generated_content_factory`)
    - [ ] `make_page_contents` → unchanged from `ContentGeneratorChild` (no activity hop)
    - [ ] `make_single_image` → `act_img_gen_images` with `nb_images=1`, then assert `len == 1`
    - [ ] `make_image_list` → `act_img_gen_images` with `nb_images=nb_images`
    - [ ] `make_templated_text` → `act_jinja2_gen_text`
    - [ ] `make_render_page_views` → `act_render_page_views`
    - [ ] `make_extract_pages` → see Phase 4 (sequenced two-activity path)
- [ ] At every `workflow.execute_activity(…)` site, pass `start_to_close_timeout=worker_config.workflow_execution_timeout` and `retry_policy=worker_config.retry_policy`.
- [ ] Wrap each method body in `try/except ActivityError` to translate `ApplicationError → TemporalError.from_app_error(...)`, mirroring `wf_make_llm_text.py:32-35`.
- [ ] Keep the `@update_job_metadata` decorator on each method (matches `ContentGeneratorChild`).
- [ ] Add an inline comment at the LLM-text site stating the asymmetric routing rule (`task_queue=inference_task_queue` here only; other activities run on the workflow's own queue).
- [ ] Create a factory module `content_generator_in_workflow_factory.py` with a `make_content_generator_in_workflow(...)` classmethod that takes `generated_content_factory` and returns the instance. (Don't plumb `task_queue` / `workflow_execution_timeout` etc. — those are read from config inside each method.)
- [ ] Add a unit test that mocks `workflow.execute_activity` and asserts the `task_queue=` kwarg per method (LLM-text only sets it; the other eight don't).

**Verification:** `make agent-check`. Nothing is wired yet — full test suite must still pass against the existing `ContentGeneratorChild` path.

---

## Phase 2 — Wire behind a temporary feature flag

- [ ] In `pipelex/pipelex.py:338-351`, add an env-flag-gated branch (e.g. `os.environ.get("PIPELEX_USE_IN_WORKFLOW_CONTENT_GENERATOR")`) that picks the new generator when `temporal.is_enabled` is true. Default OFF — `ContentGeneratorChild` remains the production path.
    - [ ] Do NOT add this flag to `pipelex.toml`. It's transient.
- [ ] Run locally with the flag ON:
    - [ ] `tests/integration/pipelex/temporal/library_crate/`
    - [ ] `tests/integration/pipelex/temporal/tracing/`
    - [ ] `tests/integration/pipelex/temporal/content_generation/test_tprl_content_generator_child.py`
- [ ] Run with the flag OFF (default): full Temporal subset must pass identically to main.

**Verification:** `make agent-check && make agent-test` (full suite, default flag OFF).

---

## Phase 3 — Re-point `WfTestContentGeneratorChild`

- [ ] Update `pipelex/temporal/test_extras/wf_test_content_generator_child.py:53-55` to construct the new in-workflow generator via the Phase 1 factory instead of `ContentGeneratorChildFactory.make_content_generator_child(...)`.
- [ ] Confirm `is_dry_run` branch still picks `ContentGeneratorDry` (lines 49-50).
- [ ] Run:
    - [ ] `.venv/bin/pytest tests/integration/pipelex/temporal/content_generation/test_tprl_content_generator_child.py`
    - [ ] `.venv/bin/pytest tests/integration/pipelex/temporal/workflows/test_wf_child_crafter.py`

This validates `make_llm_text` / `make_object` / `make_object_list` / `make_templated_text` / `make_extract_pages` round-trips through the new generator. The feature flag is still OFF in `pipelex.py`, but the test workflow constructs the new generator unconditionally — so this test path now exercises the new code regardless of flag state.

**Verification:** `make agent-check && make agent-test`.

---

## Phase 4 — Fix `make_extract_pages` page-views asymmetry

`ContentGenerator.make_extract_pages` (`content_generator.py:259-300`) augments page contents with page views when `extract_job_params.should_include_page_views` is true. `ContentGeneratorChild.make_extract_pages` (`content_generator_child.py:386-422`) does not — pre-existing bug.

- [ ] In the new generator's `make_extract_pages`, dispatch `act_extract_gen_extract_pages` first.
- [ ] If `extract_job_params.should_include_page_views` is true:
    - [ ] If `extract_input.document_uri` is set → dispatch `act_render_page_views` and use its return as `page_view_contents`.
    - [ ] Else if `extract_input.image_uri` is set → build a single-element `[ImageContent(url=extract_input.image_uri)]` inline.
- [ ] Validate `len(page_view_contents) == len(page_contents)`; raise on mismatch (matches direct generator at `content_generator.py:294-296`).
- [ ] Attach via `for page_content in page_contents: page_content.page_view = page_view_contents.pop(0)`.
- [ ] Don't double-emit when `should_include_page_views` is false.
- [ ] Add an integration test (or extend `WfTestContentGeneratorChild`) that exercises the augmentation path with a `document_uri` input.

**Verification:** `make agent-check && make agent-test`.

---

## ✅ Checkpoint A — Ready to flip

State at this checkpoint:
- New generator implemented, factory in place, unit-tested.
- Wired behind a feature flag (default OFF).
- `WfTestContentGeneratorChild` re-pointed; integration tests pass against the new generator.
- `make_extract_pages` page-views asymmetry fixed.
- `ContentGeneratorChild` and `ContentGeneratorTop` still exist; production traffic still goes through `ContentGeneratorChild`.

Open questions / decisions for next session:
- [ ] Confirm that `tests/integration/pipelex/temporal/library_crate/` and `tracing/` pass with the flag flipped on, on a freshly-built worker process.
- [ ] Verify `test_split_worker_usage.py:77-89`'s `inference_task_queue` override still routes correctly (test logic unchanged; the read site moves from `WfMakeLLMText.start_activity` to the new `workflow.execute_activity` site).
- [ ] Decide whether to land Checkpoint A as a standalone commit before Phase 5 (recommended: yes, so the flip can be reverted cheaply if a hidden integration breaks).

---

## Phase 5 — Flip the feature flag default

- [ ] In `pipelex/pipelex.py`, swap the env-flag default so the new generator is the production path when `temporal.is_enabled` is true.
- [ ] Run `make agent-test` (full suite).
- [ ] Run the local Temporal-server suite if available: `.venv/bin/pytest tests/integration/pipelex/temporal/ --temporal-server local`.
- [ ] Sanity-check a manual run of a Temporal pipeline (any `library_crate/` bundle) and inspect the Temporal UI: confirm activities appear directly under `WfPipeRouter` with no intervening `WfMake*` child workflow.

**Verification:** `make agent-check && make agent-test`. If anything regresses, flip the flag back OFF and diagnose; do not proceed to Phase 6.

---

## Phase 6 — Delete the old surface (one commit)

Per the project's "no backward compatibility" rule, delete in a single commit:

**Files deleted under `pipelex/temporal/tprl_content_generation/`:**

- [ ] `wf_make_llm_text.py`
- [ ] `wf_make_object.py`
- [ ] `wf_make_images.py`
- [ ] `wf_make_jinja2_text.py`
- [ ] `wf_make_extract.py`
- [ ] `wf_render_page_views.py`
- [ ] `content_generator_top.py`
- [ ] `content_generator_top_factory.py`
- [ ] `content_generator_child.py`
- [ ] `content_generator_child_factory.py`
- [ ] `content_generator_models.py`

**Test files deleted:**

- [ ] `tests/integration/pipelex/temporal/content_generation/test_tprl_content_generator_top.py`
- [ ] `tests/integration/pipelex/temporal/content_generation/test_tprl_make_content_generator.py`
- [ ] `tests/integration/pipelex/temporal/workflows/test_wf_gen_text.py` (already commented-out)
- [ ] `tests/integration/pipelex/temporal/workflows/test_wf_jinja2.py` (already commented-out)

**Edits:**

- [ ] `pipelex/temporal/tasks.py:1-49` — drop the seven `WfMake*` import lines and remove them from the `crafting.workflow_list`. Activity list unchanged.
- [ ] `pipelex/pipelex.py:338-351` — remove the feature-flag branch added in Phase 2; the new generator is now unconditional under `temporal.is_enabled`.
- [ ] `tests/integration/pipelex/temporal/content_generation/conftest.py:18-20, 46-73` — delete the imports of `ContentGeneratorChild` / `ContentGeneratorChildFactory` / `ContentGeneratorTopFactory` and the `top_crafter` and `child_crafter` fixtures.
- [ ] If `test_tprl_content_generator_child.py` referenced any deleted import, update accordingly.

**Verification:**

- [ ] `make cleanderived` (linters / pytest collection get confused by deleted files otherwise).
- [ ] `make agent-check`.
- [ ] `make agent-test`.
- [ ] `make tb` (boot test — config and registration sanity).

---

## Phase 7 — Update docstrings and docs

- [ ] `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py:1-9, 60-68, 78-83` — rewrite to describe the direct-activity-call topology (no more `WfMakeLLMText`).
- [ ] `tests/integration/pipelex/temporal/tracing/helpers.py:179-231` — same.
- [ ] `docs/under-the-hood/pipe-routing-and-execution.md:232` and surrounding table — update to reflect direct activity dispatch from `WfPipeRouter`.
- [ ] Search the rest of the docs for `WfMake` references and update or remove:
    ```bash
    grep -rn "WfMake\|wf_make_" docs/
    ```
- [ ] Update CHANGELOG under `[Unreleased]`: brief note that `tprl_content_generation/` workflow layer was collapsed; durability semantics unchanged; observability note about per-call workflow IDs no longer appearing in Temporal UI.

**Verification:** `make agent-check`. Docs-only changes don't need a full test run, but rerun `make agent-test` if any docs are imported by tests (they aren't, currently).

---

## ✅ Checkpoint B — Codebase in target state

State at this checkpoint:
- `tprl_content_generation/` contains only the seven `act_*.py` activity files and the new `content_generator_in_workflow.py` (+ its factory).
- `pipelex.py` always wires the new generator when `temporal.is_enabled`.
- All `WfMake*` references gone from code, tests, and docs.
- Page-views augmentation works in Temporal mode.
- All Temporal integration tests pass.

Open questions / decisions for next session:
- [ ] Is the deploy ready (drain-before-deploy enforced)? See Phase 8.
- [ ] Did the `activity_id=` decision land — and if not, file a follow-up issue?

---

## Phase 8 — Final verification and ship

**Pre-ship verification:**

- [ ] `make agent-check && make agent-test` — full suite green.
- [ ] `.venv/bin/pytest tests/integration/pipelex/temporal/ --temporal-server local` — against a real Temporal server.
- [ ] Manual smoke: run a multi-step `PipeSequence` end-to-end and confirm via Temporal UI that activities appear directly under `WfPipeRouter`.
- [ ] Replay-history check: confirm no test fixtures pickle old `WfMake*` history. (Spot-check: `grep -rn "WfMake" tests/` should return nothing in the resulting tree.)

**Deploy operations:**

- [ ] **Drain-before-deploy.** No in-flight Pipelex workflows may be running during the deploy. Any history that references a deleted `WfMake*` workflow type will fail to replay. Confirm with ops that the drain is enforced.
- [ ] If drain cannot be enforced, STOP and add `workflow.patched("collapse-content-generation-layer")` at every `make_*` site in the new generator with a fallback to the legacy `WfMake*` dispatch. (Recommendation: enforce the drain instead.)

**Ship:**

- [ ] Commit per phase boundary (Phases 1, 2, 3, 4, 5, 6, 7 each as separate commits where reasonable; Phase 6 is intentionally one commit).
- [ ] Use `/release` for the version bump and CHANGELOG finalization.

---

## Verification matrix (quick reference)

| After phase | Command |
|---|---|
| 1 | `make agent-check` |
| 2 | `make agent-check && make agent-test` (flag OFF and ON locally) |
| 3 | `make agent-check && make agent-test` |
| 4 | `make agent-check && make agent-test` |
| 5 | `make agent-test`; `--temporal-server local`; manual UI inspection |
| 6 | `make cleanderived && make agent-check && make agent-test && make tb` |
| 7 | `make agent-check` |
| 8 | full suite + real-server suite + manual smoke + drain confirmation |

---

## Where bugs are likely to hide (from v2 §6)

- **Asymmetric `task_queue=worker_config.inference_task_queue` rule.** Easy to forget at the LLM-text site or to over-apply elsewhere. Covered by the unit test added in Phase 1.
- **`model_validate(obj.model_dump(mode="json", serialize_as_any=True))` round-trips** for `make_object` / `make_object_list`. Required because the activity boundary returns a generic `BaseModel`. Don't drop these.
- **Page-views augmentation** in `make_extract_pages` (Phase 4). Mirror the direct generator's branching exactly: don't double-emit when `should_include_page_views` is false; handle both `document_uri` (multi-page render) and `image_uri` (single-image) inputs; assert length match.
