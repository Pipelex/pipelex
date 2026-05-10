# TODO: Collapse `tprl_content_generation/` Workflow Layer

> **Required reading before Phase 1:** `wip/temporal-primitives/collapse-content-generation-workflow-layer-v2.md` — the architectural analysis (current `WfMake*` shapes in §0, full file-level inventory in §1, behavioral diff incl. retry / task_queue / dry-mode in §2, the asymmetric `inference_task_queue` rule, and the `make_extract_pages` pre-existing divergence). This file is the executable plan; v2 is the *why*. Do not start Phase 1 without reading v2 first — the phases below assume that context.
>
> **Branch:** `refactor/Temporal-primitives` (start work here; ship via PR to `main`).

## Goal

Replace `WfMake*` child-workflow dispatch with direct `workflow.execute_activity(act_*, …)` calls inside `WfPipeRouter`. Deletes seven workflow types, two near-duplicate generator implementations (`ContentGeneratorTop` + `ContentGeneratorChild`) and their factories, and a small assignment-types models file. Adds one new in-workflow generator. Net: history-event reduction ≈12 → 3 per content-generation call; per-LLM-call durability preserved; deletion is concentrated and mechanical.

## Status

- [ ] **Phase 0 — Pre-flight audit** (uniqueness invariants for `activity_id`)
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

## Decisions

- **Generator class name:** `ContentGeneratorInWorkflow`. The `InWorkflow` suffix flags the load-bearing constraint at every import site — this class only works when called from inside a workflow's `run()` (because each method calls `workflow.execute_activity(…)`, which hard-fails outside a workflow context).
- **`activity_id=` for observability:** Thread `wfid` into `activity_id=` at every `workflow.execute_activity(…)` call. Preserves the Temporal Web UI per-step breadcrumb that ops use to triage failures. Uniqueness strategy depends on the Phase 0 audit outcome — see Phase 0 for the two branches.
- **Activity-id uniqueness strategy:** *To be filled in by Phase 0.* Either (i) "default-`wfid`-is-unique-per-workflow" (rely on today's invariant — at most one call per `ContentGeneratorProtocol` method per `WfPipeRouter` execution), or (ii) "per-method counter" (suffix `wfid` with an instance-level counter to disambiguate repeated calls). Phase 0 records the choice here.

---

## Phase 0 — Pre-flight audit

The `activity_id=wfid` strategy depends on activity-ids being unique within each workflow execution. `ContentGeneratorChild` defaults `wfid` to method-specific constants — `"craft-text"`, `"craft-object-direct"`, `"craft-object-list-direct"`, `"craft-image"`, `"jinja2-text"`, `"render-page-views"`, `"extract"` (`content_generator_child.py:95, 137, 178, 248, 294, 331, 372, 411`). Today these collide-by-design with each other within a single workflow because `make_child_workflow_id` prepends the parent's globally-unique `workflow_id`. After collapse, activity-ids only get the workflow's own scope — no parent prefix to fall back on. So we need to confirm the per-workflow invariant or add a counter.

**Cost of skipping:** a duplicate-`activity_id` runtime error on the second call. Cost of doing the audit: ~30 minutes.

- [ ] Grep operator call sites for `ContentGeneratorProtocol` method calls:
    ```bash
    grep -rn "content_generator\.\(make_llm_text\|make_object\|make_object_list\|make_single_image\|make_image_list\|make_templated_text\|make_render_page_views\|make_extract_pages\)" pipelex/pipe_operators/ pipelex/pipe_controllers/ pipelex/temporal/test_extras/
    ```
- [ ] For each match, inspect surrounding control flow. Flag any:
    - calls inside a `for` / `while` loop (would repeat with same default `wfid`)
    - the same method called more than once per `_live_run_operator_pipe` invocation (or per test-workflow `run()`)
    - calls without an explicit `wfid=` argument that share a `WfPipeRouter` execution with another call to the same method
- [ ] Specifically confirm:
    - [ ] `PipeLLM._live_run_operator_pipe` calls at most one of `make_llm_text` / `make_object` / `make_object_list` per execution (today's branching at `pipe_llm.py:265, 374, 392` is mutually exclusive — verify still true).
    - [ ] `PipeImgGen` calls `make_single_image` / `make_image_list` at most once per execution.
    - [ ] `PipeExtract` calls `make_extract_pages` at most once per execution.
    - [ ] `PipeCompose` and `structured_content_composer` consume `content_generator` — confirm their loop structure if any.
    - [ ] `WfTestContentGeneratorChild` (`pipelex/temporal/test_extras/wf_test_content_generator_child.py`) calls each method at most once with the default `wfid`. Distinct method-defaults (`"craft-text"` vs `"craft-object-direct"` etc.) keep the test workflow safe — confirm no method is invoked twice without a distinct `wfid=`.
- [ ] Record the result in **Decisions** above:
    - **(i) Findings clean — invariant holds:** proceed with the simple `activity_id=wfid` strategy. Add a code comment in the new generator stating "callers must pass distinct `wfid` values when invoking the same method twice within a single workflow execution; default values disambiguate by method but not by call-count."
    - **(ii) Findings show repeated calls:** the new generator adds an instance-level per-method counter. Build the activity-id as `f"{wfid}-{count}"` where `count` increments on every call. (This is replay-stable: Temporal replays workflow code deterministically, so the counter walks the same values on replay. Document this property.)
- [ ] Note: `make_extract_pages` post-Phase-4 dispatches TWO activities (`act_extract_gen_extract_pages` + optionally `act_render_page_views`). These have different `act_*` names but share the same wrapper method. Plan their `activity_id`s explicitly: e.g. `f"{wfid}-extract"` and `f"{wfid}-render-page-views"`, or pass `wfid=` for the first and `wfid=f"{wfid}-pageviews"` for the second.

**Verification:** no code changes. This phase produces an entry in **Decisions** and unblocks Phase 1.

---

## Phase 1 — Build new in-workflow content generator

Add the new generator next to the existing files. No wiring yet — just code.

- [ ] Create `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py`.
- [ ] Define class `ContentGeneratorInWorkflow` implementing `ContentGeneratorProtocol` with the nine current methods:
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
- [ ] Thread `wfid` into `activity_id=` at every `workflow.execute_activity(…)` site, applying the strategy decided in Phase 0:
    - **Strategy (i):** `activity_id=wfid` when `wfid is not None`; omit when `None`.
    - **Strategy (ii):** instance-level `dict[str, int]` counter keyed by method name; activity_id is `f"{wfid}-{counter[method]}"`; increment after use.
- [ ] Wrap each method body in `try/except ActivityError` to translate `ApplicationError → TemporalError.from_app_error(...)`, mirroring `wf_make_llm_text.py:32-35`.
- [ ] Keep the `@update_job_metadata` decorator on each method (matches `ContentGeneratorChild`).
- [ ] Add an inline comment at the LLM-text site stating the asymmetric routing rule (`task_queue=inference_task_queue` here only; other activities run on the workflow's own queue).
- [ ] Create a factory module `content_generator_in_workflow_factory.py` with a `make_content_generator_in_workflow(...)` classmethod that takes `generated_content_factory` and returns the instance. (Don't plumb `task_queue` / `workflow_execution_timeout` etc. — those are read from config inside each method.)
- [ ] Add a unit test that mocks `workflow.execute_activity` and asserts:
    - `task_queue=` kwarg per method (LLM-text only sets it; the other eight don't)
    - `activity_id=` kwarg threading per method
    - (if Strategy (ii)) repeated calls to the same method produce distinct activity_ids

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

This validates the round-trips through the new generator. The feature flag is still OFF in `pipelex.py`, but the test workflow constructs the new generator unconditionally — so this test path now exercises the new code regardless of flag state.

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
- [ ] Use distinct `activity_id`s per Phase 0's strategy (the two activities share a wrapper method).
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
- [ ] Sanity-check a manual run of a Temporal pipeline (any `library_crate/` bundle) and inspect the Temporal UI: confirm activities appear directly under `WfPipeRouter` with no intervening `WfMake*` child workflow, and that `activity_id` values are meaningful.

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

Open questions / decisions for next session:
- [ ] Is the deploy ready (drain-before-deploy enforced)? See Phase 8.

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
| 0 | (no code changes — record finding in Decisions) |
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
- **`activity_id` collisions** under repeated calls — see Phase 0. The default `wfid` values are method-specific constants; they do NOT disambiguate repeated calls to the same method. If Phase 0 found this risk in any operator, Strategy (ii) (counter) is mandatory.
- **`model_validate(obj.model_dump(mode="json", serialize_as_any=True))` round-trips** for `make_object` / `make_object_list`. Required because the activity boundary returns a generic `BaseModel`. Don't drop these.
- **Page-views augmentation** in `make_extract_pages` (Phase 4). Mirror the direct generator's branching exactly: don't double-emit when `should_include_page_views` is false; handle both `document_uri` (multi-page render) and `image_uri` (single-image) inputs; assert length match.
