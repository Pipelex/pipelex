# Analysis: Collapsing the `tprl_content_generation/` Workflow Layer (v2)

> **What changed since v1.** The "text-then-object" structuring path was removed end-to-end (commit `16b775b8`): `WfMakeTextThenObject` / `WfMakeTextThenObjectList` are gone, `LLMAssignmentFactory` and `TextThenObjectAssignment` are gone, `make_text_then_object` / `make_text_then_object_list` are gone from `ContentGeneratorProtocol` and all four implementations, `make_object_direct` was renamed to `make_object`, and `make_object_list_direct` was renamed to `make_object_list`. The `StructuringMethod.PRELIMINARY_TEXT` enum value still exists but `PipeLLM` raises `NotImplementedError` if it's selected.
>
> **Net effect on this refactor.** The single nontrivial case in the v1 plan — the two-activity glue inside `WfMakeTextThenObject` — is gone. Every surviving `WfMake*` workflow is now a structurally identical single-activity wrapper. The collapse is now pure boilerplate deletion.

---

## 0. The shape of what's left

After the text-then-object removal, the seven surviving workflow types in `pipelex/temporal/tprl_content_generation/` are all the same shape:

```python
@workflow.defn(name="wf_…")
class WfMakeXxx(WorkflowClass[XxxAssignment, ResultType]):
    @workflow.run
    async def run(self, workflow_arg: XxxAssignment) -> ResultType:
        worker_config = get_config().temporal.worker_config
        try:
            result = await workflow.start_activity(
                activity=act_xxx,
                arg=workflow_arg,
                start_to_close_timeout=worker_config.workflow_execution_timeout,
                retry_policy=worker_config.retry_policy,
                # task_queue=worker_config.inference_task_queue  ← LLM-text only
            )
        except ActivityError as exc:
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        return result
```

Concretely, with line refs to the current code:

| Workflow | File | Activity | Special routing |
|---|---|---|---|
| `WfMakeLLMText` | `wf_make_llm_text.py:14-37` | `act_llm_gen_text` | `task_queue=inference_task_queue` |
| `WfMakeObject` | `wf_make_object.py:19-42` | `act_llm_gen_object` | — |
| `WfMakeObjectList` | `wf_make_object.py:45-68` | `act_llm_gen_object_list` | — |
| `WfMakeImages` | `wf_make_images.py:16-40` | `act_img_gen_images` | — |
| `WfMakeJinja2Text` | `wf_make_jinja2_text.py:18-40` | `act_jinja2_gen_text` | — |
| `WfMakeExtract` | `wf_make_extract.py:16-40` | `act_extract_gen_extract_pages` | — |
| `WfRenderPageViews` | `wf_render_page_views.py:16-40` | `act_render_page_views` | — |

There is no remaining workflow body that does anything between activities. Every workflow is `1 activity = 1 result`.

---

## 1. Concrete file-level inventory

### Delete

All under `pipelex/temporal/tprl_content_generation/`:

- `wf_make_llm_text.py` — `WfMakeLLMText`.
- `wf_make_object.py` — `WfMakeObject`, `WfMakeObjectList` (down from four classes in v1; `WfMakeTextThenObject*` already gone).
- `wf_make_images.py` — `WfMakeImages`.
- `wf_make_jinja2_text.py` — `WfMakeJinja2Text`.
- `wf_make_extract.py` — `WfMakeExtract`.
- `wf_render_page_views.py` — `WfRenderPageViews`.
- `content_generator_top.py` — `ContentGeneratorTop` (`content_generator_top.py:44-347`). Used only in tests; dispatches `WfMake*` from the submitter side and is meaningless once those workflows are gone.
- `content_generator_top_factory.py` — its only producer.
- `content_generator_child.py` — `ContentGeneratorChild` (`content_generator_child.py:65-422`). Each method dispatches a `WfMake*` via `WorkflowExecutorFactory[…].execute_child_workflow(…)`.
- `content_generator_child_factory.py` — its only producer.
- `content_generator_models.py` — `AssignmentType` / `ResultType` unions, only consumed by the two generators above.

### Stays unchanged

- All seven inference activities — `act_llm_gen_text`, `act_llm_gen_object`, `act_llm_gen_object_list`, `act_img_gen_images`, `act_jinja2_gen_text`, `act_extract_gen_extract_pages`, `act_render_page_views`. The activity bodies have not changed.
- The `ContentGeneratorProtocol` interface (`pipelex/cogt/content_generation/content_generator_protocol.py:45-135`) and the direct-mode `ContentGenerator` (`pipelex/cogt/content_generation/content_generator.py:37-301`) — both untouched. The protocol surface is now nine methods (it had eleven before the text-then-object removal).
- `WfPipeRun`, `WfPipeRouter`, `TemporalPipeRouter`, `TemporalPipeRun`, all `act_*` activities under `tprl_pipe/`, and the `tprl/` directory of helpers.
- The pipe operators: `pipelex/pipe_operators/llm/pipe_llm.py`, `pipe_img_gen.py`, `pipe_extract.py`, `pipe_compose.py`, `structured_content_composer.py`. After the text-then-object removal, `PipeLLM._llm_gen_object_stuff_content` (`pipe_llm.py:354-405`) is now a clean 2-way split (single vs list); it consumes `make_object` / `make_object_list` / `make_llm_text` from whichever generator is registered.
- `with_conditional_worker` (`pipelex/temporal/tprl/conditional_worker.py:14-41`). The decorator is still used by `TemporalPipeRouter._run_pipe_job` (`temporal_pipe_router.py:47`) and `TemporalPipeRun.run` / `.start` (`temporal_pipe_run.py:42, 72`) for `INTERNAL` worker mode in the test suite. It just stops being applied to `ContentGeneratorTop` (which is being deleted). The file itself stays.
- `WorkflowExecutor.execute_child_workflow` / `start_child_workflow` (`pipelex/temporal/tprl/workflow_caller.py:150-216`). After the refactor they are still used by `TemporalPipeRouter` for `WfPipeRouter` child dispatch (`temporal_pipe_router.py:62-67`).

### Modify

- `pipelex/temporal/tasks.py:30-49` — drop the seven `WfMake*` / `WfRenderPageViews` entries from the `crafting` `TaskPack`'s `workflow_list`. The `activity_list` (the seven `act_*` functions) is unchanged; the `pipe` `TaskPack` is unchanged.

- `pipelex/pipelex.py:338-351` — the runtime branch that builds a `ContentGeneratorChild` when `temporal.is_enabled` (`pipelex.py:341-347`) needs to construct a new in-workflow generator instead. See §2 *Direct-mode* for why every method must hop through an activity rather than calling the direct `ContentGenerator` inline (the split-worker deployment requires it).

- `pipelex/temporal/test_extras/wf_test_content_generator_child.py:43-114` — `WfTestContentGeneratorChild` constructs a `ContentGeneratorChildFactory.make_content_generator_child(…)` inside the workflow body (`wf_test_content_generator_child.py:53-55`). Replace with construction of the new in-workflow generator. The test workflow itself — and its registration in `pipelex/temporal/test_extras/temporal_test_tasks.py:5` — stay.

- Tests under `tests/integration/pipelex/temporal/content_generation/`:
    - `conftest.py:46-73` — both fixtures `top_crafter` and `child_crafter` go away. The `top_crafter` fixture wires `ContentGeneratorTopFactory.make_content_generator_top(…)` for tests in the (deleted) top suite; the `child_crafter` fixture wires `ContentGeneratorChildFactory.make_content_generator_child(…)` directly (it works today because the construction itself is async-safe outside a workflow — only the *call sites* hard-fail outside a workflow). Both can be replaced with a single fixture that builds the new in-workflow generator if any direct-construction tests are kept; otherwise just delete both.
    - `test_tprl_content_generator_top.py` (whole file, `test_tprl_content_generator_top.py:45-185`) — delete. This file tests `ContentGeneratorTop` end-to-end (seven methods including `make_object`, `make_object_list`, image, jinja2, extract, error-path); the same scenarios are covered in-workflow by `WfTestContentGeneratorChild` (`test_extras/wf_test_content_generator_child.py:43-114`) via `test_tprl_content_generator_child.py` and `test_wf_child_crafter.py`. Note: there is also `test_tprl_make_llm_text_with_error` at `:144-184` which validates that bad `LLMSetting.model` fails through the `WorkflowFailureError` envelope — keep an equivalent assertion in the new in-workflow test (or in a small unit test that mocks `workflow.execute_activity` to raise `ActivityError(ApplicationError(...))`).
    - `test_tprl_content_generator_child.py` (`test_tprl_content_generator_child.py:18-33`) — keep; `WfTestContentGeneratorChild` is re-pointed in step 3.
    - `test_tprl_make_content_generator.py:9-20` — references both `ContentGeneratorTopFactory` and `ContentGeneratorChildFactory`; deleted alongside the factories.

- `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py:77-89` — the `configure_inference_task_queue` fixture mutates `worker_config.inference_task_queue` so that `WfMakeLLMText.start_activity(…, task_queue=worker_config.inference_task_queue, …)` (`wf_make_llm_text.py:30`) routes to the runner queue. After the refactor, the same `task_queue=worker_config.inference_task_queue` argument is read at the new in-workflow `workflow.execute_activity(act_llm_gen_text, …)` call site. The test logic is unchanged. The docstring and the comment at `test_split_worker_usage.py:1-9, 60-68, 78-83` reference `WfMakeLLMText` by name and need a small rewrite.

- `tests/integration/pipelex/temporal/tracing/helpers.py:179-231` — references `WfMakeLLMText` in docstrings; rewrite to describe the direct-activity-call topology.

- `tests/integration/pipelex/temporal/workflows/test_wf_gen_text.py` and `test_wf_jinja2.py` — already commented-out historical tests that referenced `WfMakeLLMText` / `WfMakeJinja2Text` (`test_wf_gen_text.py:1-60` is entirely commented). Delete the files outright.

- `tests/integration/pipelex/temporal/workflows/test_wf_child_crafter.py:17-32` — runs `WfTestContentGeneratorChild`; keep, contingent on the rewrite of `WfTestContentGeneratorChild`.

- `docs/under-the-hood/pipe-routing-and-execution.md:232` and any nearby table entries that reference `wf_make_object` / `wf_make_llm_text` etc. as workflow types — update to describe direct activity dispatch.

---

## 2. Behavioral diff

### Temporal history shape per content-generation call

Today, a single `make_llm_text` from inside `WfPipeRouter` produces this scheduling chain in the parent's history:

- `StartChildWorkflowExecutionInitiated` → `ChildWorkflowExecutionStarted` (for `WfMakeLLMText`)
- `ChildWorkflowExecutionCompleted` (or `Failed`)

…and the `WfMakeLLMText` child's own history adds `WorkflowExecutionStarted` + workflow-task framing + `ActivityTaskScheduled` → `ActivityTaskStarted` → `ActivityTaskCompleted` (or `Failed`) + workflow-task framing + `WorkflowExecutionCompleted` — about a dozen events for a single LLM call.

After the collapse, the same call inside the parent is just:

- `ActivityTaskScheduled` → `ActivityTaskStarted` → `ActivityTaskCompleted` (or `Failed`)

…three events, in the parent's history, no child workflow.

A long `PipeSequence` of N LLM steps therefore goes from "N child-workflow scheduling pairs in parent + N small child histories" to "N activity scheduling pairs in parent". Per-LLM-call durability is preserved — the activity boundary is unchanged.

> **What v1 said about `make_text_then_object` no longer applies.** v1 noted that the same reduction applied to two-activity workflows (`WfMakeTextThenObject*`) — those don't exist anymore. There is no surviving multi-activity workflow in `tprl_content_generation/`.

### Worker registration

`pipelex/temporal/tasks.py:30-49`: `crafting` `TaskPack`'s `workflow_list` shrinks from seven workflow types to zero. The `activity_list` is unchanged. `pipe` `TaskPack` is unchanged.

The `worker_scopes` config in `pipelex/pipelex.toml` ("full", "router", "runner") is by reference: it requires the `crafting` and `pipe` packs by *name*, so the scope definitions don't need to change. The bare `router` scope (`disable_all_activities=true`) registers seven fewer workflows; the `runner` scope (`disable_all_workflows=true`) is unaffected.

### Retry semantics

Every `WfMake*` constructs its `start_activity(…)` with `retry_policy=worker_config.retry_policy` (`wf_make_llm_text.py:29`, identical at every parallel site). That's a single global default; the per-workflow retry knob in `WorkflowExecutorFactory.create_executor(…)` (`workflow_caller.py:219-248`) is plumbed through but `ContentGeneratorChildFactory` only passes the config default (`content_generator_child_factory.py:29`). So in practice every content-gen activity already runs under the same `worker_config.retry_policy_config`.

After the collapse, the new in-workflow generator passes `retry_policy=get_config().temporal.worker_config.retry_policy` at every `workflow.execute_activity(…)` call site. Identical semantics. The non-retryable error list in `pipelex/pipelex.toml` survives untouched — it's part of `worker_config.retry_policy`.

### Per-call timeouts and task-queue routing

The current `WfMake*` workflows pin both `start_to_close_timeout=worker_config.workflow_execution_timeout` and (LLM-text only, `wf_make_llm_text.py:30`) `task_queue=worker_config.inference_task_queue`. Today's de-facto routing rule is:

- LLM-text completions → `inference_task_queue` (when set)
- Object-mode LLM, image gen, extract, render-page-views, templating → workflow's own queue

After the collapse, the new in-workflow generator re-applies the same rule at each call site: `task_queue=worker_config.inference_task_queue` only on `act_llm_gen_text`. This preserves `test_split_worker_usage.py:77-89`. Production deployment topology is unchanged.

The `WfMake*` workflows' `workflow_execution_timeout` argument (passed at child dispatch from `ContentGeneratorChild` via `WorkflowExecutor.execute_child_workflow`, `workflow_caller.py:167`) disappears. The activity-level `start_to_close_timeout` already plays the equivalent role; both come from `worker_config.workflow_execution_timeout`, so collapsing to just the activity timeout is a no-op for happy-path execution and slightly tighter on the failure path.

### Direct-mode (non-Temporal) execution

`pipelex/pipelex.py:338-351`: when `temporal.is_enabled` is false, the direct, non-Temporal `ContentGenerator` is registered. Unchanged.

The `ContentGeneratorChild` branch (`pipelex.py:341-347`) is reached when `temporal.is_enabled` is true. In production, `get_content_generator()` is called from inside `WfPipeRouter` (via the operator's `pipe_llm.py` etc.), so the registered child generator is always invoked from a workflow context. There is no production code path that calls `ContentGeneratorChild`'s methods at top-level outside of a workflow — its method bodies use `workflow.execute_child_workflow`, which hard-fails outside a workflow. So the *existing* contract is "this generator only works inside a workflow."

After the collapse, the new in-workflow generator's contract is the same: each method calls `workflow.execute_activity(…)`, which also hard-fails outside a workflow. Direct-mode is unaffected because direct-mode never gets this generator wired in.

### Dry-run path

In dry mode, `ContentGeneratorDry` is registered at `pipelex.py:339-340`. `temporal.is_enabled` is gated *after* the dry check, so dry-mode does not depend on the temporal generator. The collapse does not touch this. `WfTestContentGeneratorChild` (`wf_test_content_generator_child.py:46-55`) switches between `ContentGeneratorDry` and (post-refactor) the new in-workflow generator based on its `is_dry_run` arg — same shape as today.

### Routing of nested controller calls

`TemporalPipeRouter._run_pipe_job` (`temporal_pipe_router.py:46-91`) is unchanged. `PipeController` sub-pipes still dispatch as `WfPipeRouter` child workflows. The collapse only affects what happens *inside* the leaf `WfPipeRouter` when its pipe is a `PipeOperator`.

---

## 3. Pros vs. current code

- **History-event reduction.** Each LLM/img/extract/jinja2/render call inside a `WfPipeRouter` drops from "child workflow + activity" (≈12 events including child-workflow framing) to "activity only" (3 events). On a deep `PipeSequence` this is the dominant factor in approaching the 10K-event soft limit. Per-LLM-call durability is preserved because the activity boundary is unchanged.

- **One fewer indirection in the Temporal UI.** Today: `WfPipeRouter` → `WfMakeLLMText` → `act_llm_gen_text` (three execution levels). After: `WfPipeRouter` → `act_llm_gen_text`. The activity is one level below the controller it belongs to, which matches the actual semantics.

- **Less code to maintain.** Two near-duplicate generator implementations (`ContentGeneratorTop` + `ContentGeneratorChild`, ≈770 lines combined) — the only real difference is `execute_workflow` versus `execute_child_workflow` — collapse into one in-workflow generator (estimated ≈300 lines, one method per activity).

- **No new abstractions required.** The activities, the `act_*` functions, the `crafting` pack registration — all already exist and stay in place. The refactor is largely deletion.

- **Eliminates a dual-source-of-truth for retry / timeout / task_queue config.** Today some knobs are on the `WfMake*` workflow's `start_activity(…)` (`wf_make_llm_text.py:25-31`), some are on `ContentGeneratorChildFactory` plumbing (`content_generator_child_factory.py:13-34`), and `test_split_worker_usage.py:77-89` mutates `worker_config.inference_task_queue` and *trusts* `WfMakeLLMText` to read it on every child-workflow invocation. After collapsing, all those knobs apply at the single `workflow.execute_activity(…)` call site.

- **Workflows are now structurally identical.** This is the main difference vs. v1's pros list. With `WfMakeTextThenObject*` gone, every surviving `WfMake*` is the same template (see §0). Deleting seven copies of the same five-line wrapper is a strict simplification — no logic is being relocated, just moved one frame up the stack.

---

## 4. Cons / risks vs. current code

- **Loss of distinct workflow IDs per content-generation call in the Temporal UI.** `ContentGeneratorChild.make_llm_text` builds `child_workflow_id` from the parent's id + `wfid` (`content_generator_child.py:48-62, 95`). Operators and tests pass `wfid=` to give a Temporal-UI-visible name to a specific content-generation step. After the collapse, the activity has no comparable user-controllable "ID" surface — only `activity_id`, auto-assigned by the SDK. Per-step naming is lost in the Temporal UI; observability falls back to activity logs, the `act_*` function name, and the `JobMetadata.content_generation_job_id` field that `update_job_metadata` already stamps (`content_generator_protocol.py:25-42`). This is the most concrete observability regression.

- **Loss of the per-content-generation `workflow_execution_timeout`.** Each `WfMake*` carries its own `execution_timeout` today (derived from `worker_config.workflow_execution_timeout`, but a future per-call override is on the table). After the collapse there is only the activity's `start_to_close_timeout`. In practice this is the same value, so no regression today — but you've lost a future axis of independent control.

- **Determinism implications — smaller surface than v1 estimated.** Today the `wf_make_*` workflow body is a thin layer (just `start_activity` + error translation). All calls run inside `WfPipeRouter`'s sandbox already, since `pipe.run_pipe(…)` reaches operator code that calls `get_content_generator()` and dispatches via `ContentGeneratorChild`'s methods. The construction of `LLMAssignment` / `ObjectAssignment` / `TemplatingAssignment` / `ImgGenAssignment` / `ExtractAssignment` / `RenderPageViewsAssignment` Pydantic models, plus `ObjectAssignment.make_for_class(...)`, plus the `model_validate(obj.model_dump(serialize_as_any=True))` re-validation at `content_generator_child.py:148, 189`, plus `make_child_workflow_id(…)` — all already run inside `WfPipeRouter`'s sandboxed code today. The new line is just `workflow.execute_activity(…)` replacing `WorkflowExecutorFactory[…].create_executor().execute_child_workflow(…)`. Both are deterministic Temporal SDK calls.

  **Why this is smaller than v1.** v1 flagged `LLMAssignmentFactory.make_llm_assignment(preliminary_text=…)` running between two activities inside the workflow sandbox as the riskiest piece of glue. That code is gone. There is no longer any inter-activity glue that needs to run inside the new in-workflow generator. The whole determinism-risk paragraph reduces to "make sure no new non-passing-through import sneaks in" — which `make tb` and the `library_crate` integration suite catch cheaply.

- **Default activity worker / asymmetric task_queue routing.** Today, only `WfMakeLLMText` passes `task_queue=worker_config.inference_task_queue` (`wf_make_llm_text.py:30`). The other six wrappers don't pass `task_queue`, so their activities run on the workflow's task queue. The new generator must replicate this exactly. Easy to mis-handle if a reviewer thinks "we should route everything to inference_task_queue" — that would break the `crafting` pack registration on the runner workers (which today register the LLM activity on the inference queue and the others on the default queue).

  *Mitigation:* a comment at the LLM-text site explicitly stating the asymmetric routing rule, plus a small unit test that mocks `workflow.execute_activity` and asserts the `task_queue=` kwarg per method.

- **Pre-existing behavioral divergence to flag-and-fix.** `ContentGenerator.make_extract_pages` (`content_generator.py:259-300`) augments its return with `make_render_page_views(…)` when `extract_job_params.should_include_page_views` is true (or sets a single-image page view when `extract_input.image_uri` is set). The Temporal-mode `ContentGeneratorChild.make_extract_pages` (`content_generator_child.py:386-422`) does not — it just dispatches `WfMakeExtract` and returns the page contents as-is, missing both augmentations. The collapse is the right moment to fix this asymmetry: the new in-workflow generator can mirror `ContentGenerator.make_extract_pages` exactly, dispatching `act_extract_gen_extract_pages` and (when needed) `act_render_page_views` as two separate activity calls, then attaching page views to the page contents in-workflow. This is in scope per the project's "flag and fix existing bugs" principle.

- **Tests that depend on the current workflow topology.** Same cluster as v1, slightly smaller now:
    - `test_tprl_content_generator_top.py` (delete wholesale).
    - `test_tprl_make_content_generator.py` (delete wholesale).
    - `test_tprl_content_generator_child.py` (small touch — re-points).
    - `test_split_worker_usage.py` (test logic unchanged; docstrings stale).
    - `test_wf_gen_text.py` and `test_wf_jinja2.py` (already commented-out — delete the files).
    - `library_crate/` and `tracing/` suites — pass unchanged after the LLM-text site is correctly task-queue-routed.

  Replay tests, if any, that pickle a `WfMake*` history will break — none in the current tree.

- **`with_conditional_worker` removal from the content-gen path.** This decorator (`pipelex/temporal/tprl/conditional_worker.py:14-41`) wraps every method on `ContentGeneratorTop` today. Post-refactor, `ContentGeneratorTop` is gone, so the wrap on those methods disappears. The decorator file remains because `TemporalPipeRouter` and `TemporalPipeRun` still use it. Net: fewer call sites, no behavioral change for the `INTERNAL`-mode test fixtures that drive `WfPipeRouter` / `WfPipeRun`.

---

## 5. Refactoring plan

The ordering preserves direct-mode parity at every step (direct-mode never depends on the temporal content-generation classes) and keeps Temporal mode green at every checkpoint. Each numbered step ends with `make agent-check && make agent-test` (or, during local dev, the `tests/integration/pipelex/temporal/` subset).

1. **Add the new in-workflow content generator.** Create `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py`. Implement `ContentGeneratorInWorkflow` (or pick a better name) with the same `ContentGeneratorProtocol` surface — nine methods now that text-then-object is gone — and method bodies that call `workflow.execute_activity(act_*, arg=..., start_to_close_timeout=worker_config.workflow_execution_timeout, retry_policy=worker_config.retry_policy [, task_queue=worker_config.inference_task_queue for LLM-text only])`. Wrap with `try/except ActivityError` to translate `ApplicationError → TemporalError.from_app_error(...)`, mirroring what each `wf_make_*.py` does today (`wf_make_llm_text.py:32-35` and parallels). Add a factory.

   No wiring yet. Run `make agent-check`.

2. **Wire the new generator behind a temporary feature flag.** Add a transient boolean in `pipelex/pipelex.py:338-351` (env-flag-gated, *not* in `pipelex.toml`) that picks the new generator instead of `ContentGeneratorChild` when `temporal.is_enabled`. Default: still `ContentGeneratorChild`. Flip the flag locally and run `tests/integration/pipelex/temporal/library_crate/` and `tracing/`; assert green.

3. **Re-point `WfTestContentGeneratorChild`.** Update `pipelex/temporal/test_extras/wf_test_content_generator_child.py:53-55` to construct the new in-workflow generator. This validates a full `make_llm_text` / `make_object` / `make_object_list` / `make_templated_text` / `make_extract_pages` round-trip via `test_wf_child_crafter.py:17-32` and `test_tprl_content_generator_child.py:18-33`. (Image-gen path is currently commented out at `wf_test_content_generator_child.py:87-92`; consider re-enabling it now that the page-views augmentation is being addressed in step 4 — an in-workflow `make_single_image` exercise here would cover img-gen via the new generator.)

4. **Migrate the `make_extract_pages` page-views augmentation.** While writing the new generator, mirror `ContentGenerator.make_extract_pages`'s `should_include_page_views` branch: dispatch `act_extract_gen_extract_pages`, then if `extract_input.document_uri` is set and `should_include_page_views` is true call `act_render_page_views` as a second activity, else if `extract_input.image_uri` is set construct a single-image page-view list inline. Attach to `page_contents` in-workflow. Fixes the pre-existing divergence noted in §4.

5. **Flip the default.** Once §3 is green, swap the feature flag default so the new generator is the production path. Run `make agent-test`.

6. **Delete the old surface.** All in one commit, per the project's "no backward compatibility" rule:
    - Files listed under §1 *Delete*.
    - Imports in `pipelex/temporal/tasks.py` (drop `WfMake*` and `WfRenderPageViews` from `crafting.workflow_list`; drop the `wf_make_*` import lines).
    - The feature flag added in step 2.
    - `tests/integration/pipelex/temporal/content_generation/test_tprl_content_generator_top.py` (whole file).
    - `tests/integration/pipelex/temporal/content_generation/test_tprl_make_content_generator.py` (whole file).
    - `tests/integration/pipelex/temporal/workflows/test_wf_gen_text.py` and `test_wf_jinja2.py` (whole files — already commented-out).
    - The `top_crafter` and `child_crafter` fixtures + their imports in `conftest.py:18-20, 46-73`.

7. **Update docstrings and docs.**
    - `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py:1-9, 60-68, 78-83` references `WfMakeLLMText` by name; rewrite for the direct-activity-call topology.
    - `tests/integration/pipelex/temporal/tracing/helpers.py:179-231` — same.
    - `docs/under-the-hood/pipe-routing-and-execution.md:232` — update the "workflow → activity" table to describe direct activity dispatch.

8. **No `patched()` calls if the deploy is hard-cut.** Per project rule, there is no backward-compat transition. The constraint is that no in-flight Pipelex workflows may be running during the deploy. If that constraint cannot be enforced operationally, `workflow.patched("collapse-content-generation-layer")` would be needed at every `make_*` call site in the new generator, with a fallback that dispatches the legacy `WfMake*`. Recommendation: enforce drain-before-deploy and skip `patched()`.

---

## 6. Size estimate

- **Files deleted:** seven workflow files (`wf_make_llm_text.py`, `wf_make_object.py`, `wf_make_images.py`, `wf_make_jinja2_text.py`, `wf_make_extract.py`, `wf_render_page_views.py`), four generator/factory files (`content_generator_top.py`, `content_generator_top_factory.py`, `content_generator_child.py`, `content_generator_child_factory.py`), one models file (`content_generator_models.py`), and four test files (`test_tprl_content_generator_top.py`, `test_tprl_make_content_generator.py`, `test_wf_gen_text.py`, `test_wf_jinja2.py`).
- **Files created:** one (`content_generator_in_workflow.py`).
- **Files modified:** `pipelex/temporal/tasks.py`, `pipelex/pipelex.py`, `pipelex/temporal/test_extras/wf_test_content_generator_child.py`, `tests/integration/pipelex/temporal/content_generation/conftest.py`, `tests/integration/pipelex/temporal/content_generation/test_tprl_content_generator_child.py`, `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py` (docstring/comments only), `tests/integration/pipelex/temporal/tracing/helpers.py` (docstring only), `docs/under-the-hood/pipe-routing-and-execution.md` (table only).
- **Effort:** smaller than v1 estimated. The change at each call site is replacing a `WorkflowExecutorFactory[…].execute_child_workflow(WfMakeXxx, …)` with `workflow.execute_activity(act_xxx, …)`. There is no longer any inter-activity glue to relocate. Budget: a focused half-day for code, plus a half-day for the test-fixture migration and feature-flag flip.
- **Where bugs are likely to hide:**
    - The asymmetric `task_queue=worker_config.inference_task_queue` rule — easy to forget on the LLM-text site or to over-apply elsewhere. Add an explicit unit test that mocks `workflow.execute_activity` and asserts the `task_queue=` kwarg per method.
    - The `model_validate(obj.model_dump(mode="json", serialize_as_any=True))` round-trips at `content_generator_child.py:148, 189`. These are needed because the activity boundary returns a generic `BaseModel` (`act_llm_gen_object` is typed `-> BaseModel` at `act_llm_generate.py:16`). The new generator must keep these round-trips at the same place; otherwise structured-output validation regresses. The temporal data converter handles `BaseModel` inheritance via `kajson` already (`pipelex/temporal/temporal_data_converter.py`), but `model_validate` against the *concrete* class is what guarantees the output type expected by callers.
    - The page-views augmentation in `make_extract_pages` (today missing in Temporal mode, fixed during the refactor). Mirror the direct generator's branching exactly: don't double-emit when `should_include_page_views` is false; handle both `document_uri` (multi-page render) and `image_uri` (single-image) inputs.
- **Replay-history compatibility:** none. Any workflow mid-flight at deploy time that references `WfMakeLLMText` etc. in its history will fail to replay. Drain or fail-fast all in-flight Pipelex workflows before deploy.

---

## 7. Recommendation

**Yes — and the case is strictly stronger than in v1.**

The text-then-object removal eliminated the only nontrivial workflow in `tprl_content_generation/`. The remaining seven `WfMake*` are now structurally identical thin wrappers (§0). The collapse becomes pure boilerplate deletion:

- **History-event reduction is unchanged:** ≈12 → 3 events per content-generation call.
- **Per-LLM-call durability is preserved:** the activity boundary is unchanged.
- **The single subtle-glue risk v1 flagged is gone.** v1's §6 "where bugs are likely to hide" listed `LLMAssignmentFactory.make_llm_assignment(preliminary_text=…)` running between two activities inside the workflow sandbox as the highest-risk piece. There is no longer any inter-activity glue.
- **The deletion is concentrated and mechanical.** Eleven files in one directory plus four test files; one new generator file with nine method bodies that each look almost identical.

**Open question for implementation, not before:** the "loss of distinct workflow IDs per content-generation call in the Temporal UI" cost in §4. If ops rely on those IDs as breadcrumbs today, decide between (a) setting `activity_id=` explicitly via the SDK overrides to reproduce the `wfid`-based naming, or (b) accepting logs + `JobMetadata.content_generation_job_id` as sufficient. Independent of the rest of the refactor.

**Ordering vs. other open work.** Do this on a dev branch when the temporal integration tests are otherwise green. It's not worth coupling with a release. If a Temporal-related feature is in flight (payload codec, `ClassRegistry` propagation), defer until after — the refactor is purely subtractive and gains nothing by being interleaved.

---

## 8. What changed vs. v1 (summary)

| Aspect | v1 | v2 |
|---|---|---|
| Workflows to delete | 9 (incl. `WfMakeTextThenObject`, `WfMakeTextThenObjectList`) | 7 |
| Protocol methods to migrate | 11 | 9 |
| Non-trivial workflow body | `WfMakeTextThenObject*` (two activities + `LLMAssignmentFactory` glue) | None |
| `ObjectAssignment` factory wired through `LLMAssignmentFactory.make_llm_assignment_for_class(...)` | Yes | Replaced by direct `ObjectAssignment.make_for_class(...)` calls (already done) |
| Determinism-risk surface in §4 | "Verify `LLMAssignmentFactory.make_llm_assignment` is sandbox-safe" | Empty (no inter-activity glue) |
| Effort estimate | "focused day for code + day for tests" | "half-day for code + half-day for tests" |
| Other items (history reduction, retry, task-queue, `make_extract_pages` divergence, observability) | Same | Same |
