# Analysis: Collapsing the `tprl_content_generation/` Workflow Layer

This is the narrower scope hinted at in `wip/operators-as-activities-analysis.md`'s recommendation: keep `PipeOperators` running inside `WfPipeRouter` as today, but delete the `WfMake*` / `WfRenderPageViews` workflow wrappers and have the per-workflow `ContentGenerator` call `workflow.execute_activity(act_*, …)` directly instead of `execute_child_workflow(WfMake*, …)`.

The proposed shape:

```
WfPipeRun (top, unchanged)
  └─ WfPipeRouter (orchestrator, unchanged)
      └─ [PipeController iterates sub-pipes]
           ├─ WfPipeRouter (child sub-pipe, unchanged)
           │    └─ [PipeOperator's ContentGenerator]
           │         └─ workflow.execute_activity(act_llm_gen_text, …)   ← direct activity call
```

versus today's:

```
WfPipeRouter
  └─ [PipeOperator's ContentGenerator]
       └─ execute_child_workflow(WfMakeLLMText)
            └─ workflow.start_activity(act_llm_gen_text, …)
```

---

## 1. Concrete file-level inventory

### Delete

All under `pipelex/temporal/tprl_content_generation/`:

- `wf_make_llm_text.py` — `WfMakeLLMText` (`pipelex/temporal/tprl_content_generation/wf_make_llm_text.py:14-37`); a single `start_activity(act_llm_gen_text, …, task_queue=worker_config.inference_task_queue)` wrapped in `ActivityError → TemporalError` translation.
- `wf_make_object.py` — four workflow defs (`WfMakeObject`, `WfMakeObjectList`, `WfMakeTextThenObject`, `WfMakeTextThenObjectList`, `pipelex/temporal/tprl_content_generation/wf_make_object.py:24-169`). The two `…ThenObject…` variants invoke two activities in sequence and assemble the second `LLMAssignment` between them.
- `wf_make_images.py` — `WfMakeImages` (`pipelex/temporal/tprl_content_generation/wf_make_images.py:16-40`).
- `wf_make_jinja2_text.py` — `WfMakeJinja2Text` (`pipelex/temporal/tprl_content_generation/wf_make_jinja2_text.py:18-40`).
- `wf_make_extract.py` — `WfMakeExtract` (`pipelex/temporal/tprl_content_generation/wf_make_extract.py:16-40`).
- `wf_render_page_views.py` — `WfRenderPageViews` (`pipelex/temporal/tprl_content_generation/wf_render_page_views.py:16-40`).
- `content_generator_top.py` — `ContentGeneratorTop` (`pipelex/temporal/tprl_content_generation/content_generator_top.py:53-447`). This class is only used in tests (see §4 *Tests*); it dispatches `WfMake*` as top-level workflows from the submitter side. Once the `WfMake*` types are gone there is no top-level workflow to dispatch and the class becomes meaningless.
- `content_generator_top_factory.py` — its only producer (`pipelex/temporal/tprl_content_generation/content_generator_top_factory.py:12-35`).
- `content_generator_child.py` — `ContentGeneratorChild` (`pipelex/temporal/tprl_content_generation/content_generator_child.py:74-532`). Each method dispatches a `WfMake*` via `WorkflowExecutorFactory[…].execute_child_workflow(…)`. Becomes redundant once we call activities directly.
- `content_generator_child_factory.py` — its only producer (`pipelex/temporal/tprl_content_generation/content_generator_child_factory.py:10-34`).
- `content_generator_models.py` — `AssignmentType` / `ResultType` unions, only consumed by `ContentGeneratorTop`/`ContentGeneratorChild` (`pipelex/temporal/tprl_content_generation/content_generator_models.py:8-20`).

### Probably delete (after a usage review)

- `pipelex/temporal/tprl/conditional_worker.py` — `with_conditional_worker` (`pipelex/temporal/tprl/conditional_worker.py:14-41`). The decorator is currently applied in three places:
    1. Each `ContentGeneratorTop` method (`pipelex/temporal/tprl_content_generation/content_generator_top.py:59` and the eight other methods at lines 90, 124, 169, 203, 278, 317, 352, 383, 418).
    2. `TemporalPipeRouter._run_pipe_job` (`pipelex/temporal/tprl_pipe/temporal_pipe_router.py:47`).
    3. `TemporalPipeRun.run` and `.start` (`pipelex/temporal/tprl_pipe/temporal_pipe_run.py:42, 72`).

  After the refactor, (1) is gone with `ContentGeneratorTop`. (2) and (3) remain — they exist so that, when running the pipelex test suite with `worker_environment=INTERNAL`, the test process spins up an in-process worker on a per-call task queue and tears it down (`pipelex/temporal/tprl/conditional_worker.py:23-37`). That capability is still used by the temporal test fixtures regardless of the content-generation layer, so the decorator file itself should stay; only the imports from `content_generator_top.py` / `content_generator_child.py` go away.

- The `WorkflowExecutor.execute_child_workflow` / `start_child_workflow` methods on `pipelex/temporal/tprl/workflow_caller.py:150-216` are used today only by `ContentGeneratorChild`'s `WorkflowExecutorFactory[…].create_executor().execute_child_workflow(…)` calls (`pipelex/temporal/tprl_content_generation/content_generator_child.py:99-105` and the parallel calls in each of its other methods) and indirectly by `TemporalPipeRouter` for `WfPipeRouter` child dispatch (`pipelex/temporal/tprl_pipe/temporal_pipe_router.py:62-67`). After the refactor (2) keeps using them. Don't delete the methods, but they're free to slim if `TemporalPipeRouter` is rewritten to call `workflow.execute_child_workflow` directly.

### Modify

- `pipelex/temporal/tasks.py` — drop the `WfMake*` / `WfRenderPageViews` entries from the `crafting` `TaskPack`'s `workflow_list` (`pipelex/temporal/tasks.py:30-51`). The `activity_list` is unchanged: `act_llm_gen_text`, `act_llm_gen_object`, `act_llm_gen_object_list`, `act_img_gen_images`, `act_jinja2_gen_text`, `act_extract_gen_extract_pages`, `act_render_page_views` all stay registered on the `crafting` pack.

- `pipelex/pipelex.py:338-351` — the runtime branch that builds a `ContentGeneratorChild` when `temporal.is_enabled` (`pipelex/pipelex.py:341-347`) needs to construct *something else*. The natural choice: a new `ContentGeneratorTemporalActivities` (subclass of `ContentGeneratorProtocol`) that, inside each method, picks between (a) calling the activity via `workflow.execute_activity(…)` when `is_in_temporal_workflow()` is true, and (b) doing nothing reasonable when called outside a workflow — because today, `ContentGeneratorChild` is *only* meaningful when called from within `WfPipeRouter`. (See §2 *Direct-mode* for why this branch is essentially never hit at top level.)

  A simpler alternative that matches today's contract more tightly: register the regular non-Temporal `ContentGenerator` (`pipelex/cogt/content_generation/content_generator.py:41-405`) in the hub even when `temporal.is_enabled`, and have a thin adapter that overrides only the methods that *must* hop through an activity for durability. With Pipelex's "activity worker may be a different process from the workflow worker" deployment topology (the `router` / `runner` worker scopes in `pipelex/pipelex.toml:535-567`), every LLM / extract / image / page-view / jinja2 method needs the activity hop — direct-call would run inference inside the workflow process, which breaks the split-worker setup. So in practice the new generator overrides every method.

- `pipelex/temporal/test_extras/wf_test_content_generator_child.py` — `WfTestContentGeneratorChild` constructs a `ContentGeneratorChildFactory.make_content_generator_child(…)` inside the workflow body (`pipelex/temporal/test_extras/wf_test_content_generator_child.py:62-65`). Replace that with construction of the new in-workflow content generator. The test workflow itself — and its registration in `pipelex/temporal/test_extras/temporal_test_tasks.py:1-10` — stay.

- Tests under `tests/integration/pipelex/temporal/content_generation/`:
    - `conftest.py` (`tests/integration/pipelex/temporal/content_generation/conftest.py:46-73`) — both fixtures `top_crafter` and `child_crafter` go away. Replace with a single fixture that builds the new in-workflow `ContentGenerator` (or skip the layer entirely and test the activities directly).
    - `test_tprl_content_generator_top.py` (the whole file, `tests/integration/pipelex/temporal/content_generation/test_tprl_content_generator_top.py:57-232`) — the cleanest move is delete: this file tests `ContentGeneratorTop` end-to-end, and that whole class is being removed. The same test scenarios are covered, in-workflow, by `WfTestContentGeneratorChild` in `test_tprl_content_generator_child.py` / `test_wf_child_crafter.py`.
    - `test_tprl_content_generator_child.py` (`tests/integration/pipelex/temporal/content_generation/test_tprl_content_generator_child.py:18-33`) — keep, but re-point `WfTestContentGeneratorChild` at the new in-workflow generator.
    - `test_tprl_make_content_generator.py` — references `ContentGeneratorTopFactory` (`tests/integration/pipelex/temporal/content_generation/test_tprl_make_content_generator.py:5-11`); deleted alongside the factory.

- `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py` — its `configure_inference_task_queue` fixture overrides `worker_config.inference_task_queue` (`tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py:77-89`) so that `WfMakeLLMText.start_activity(…, task_queue=worker_config.inference_task_queue, …)` (`pipelex/temporal/tprl_content_generation/wf_make_llm_text.py:30`) routes to the runner queue. After the refactor, the same `task_queue=worker_config.inference_task_queue` argument has to be passed at the new in-workflow `workflow.execute_activity(act_llm_gen_text, …)` call site. The test still works as written, but the *site we override* moves; documentation strings in `test_split_worker_usage.py` and `tracing/helpers.py:179-231` will be out of date and need a pass.

- `tests/integration/pipelex/temporal/workflows/test_wf_child_crafter.py` (`tests/integration/pipelex/temporal/workflows/test_wf_child_crafter.py:17-32`) — runs `WfTestContentGeneratorChild` and depends on `TEMPORAL_TEST_WORKFLOWS`/`TEMPORAL_TEST_ACTIVITIES`. Keep, contingent on the rewrite of `WfTestContentGeneratorChild`.

- `tests/integration/pipelex/temporal/workflows/test_wf_gen_text.py` and `test_wf_jinja2.py` — already commented-out historical tests that referenced `WfMakeLLMText` / `WfMakeJinja2Text`. Delete the files outright.

### Stays unchanged

- All seven inference activities — `act_llm_gen_text`, `act_llm_gen_object`, `act_llm_gen_object_list` (`pipelex/temporal/tprl_content_generation/act_llm_generate.py:9-25`), `act_img_gen_images` (`pipelex/temporal/tprl_content_generation/act_img_gen_generate.py:11-30`), `act_jinja2_gen_text` (`pipelex/temporal/tprl_content_generation/act_jinja2_generate.py:8-12`), `act_extract_gen_extract_pages` (`pipelex/temporal/tprl_content_generation/act_extract_generate.py:11-25`), `act_render_page_views` (`pipelex/temporal/tprl_content_generation/act_render_page_views.py:13-39`).
- The `ContentGeneratorProtocol` interface (`pipelex/cogt/content_generation/content_generator_protocol.py:46-159`) and the direct-mode `ContentGenerator` (`pipelex/cogt/content_generation/content_generator.py`) — both untouched.
- `WfPipeRun`, `WfPipeRouter`, `TemporalPipeRouter`, `TemporalPipeRun`, all `act_*` activities under `tprl_pipe/`, and the entire `tprl/` directory of helpers.
- The pipe operators themselves: `pipelex/pipe_operators/llm/pipe_llm.py`, `pipe_img_gen.py`, `pipe_extract.py`, `pipe_compose.py`, `structured_content_composer.py`. They consume `get_content_generator()` (`pipelex/pipe_operators/llm/pipe_llm.py:191`, `pipe_img_gen.py:147`, `pipe_extract.py:128`, `pipe_compose.py:152, 297`, `structured_content_composer.py:61`) and don't care which implementation is registered.

---

## 2. Behavioral diff

### Temporal history shape per LLM call

Today, a single `make_llm_text` from inside `WfPipeRouter` produces this scheduling chain in the parent's history (the events with corresponding `Started`/`Completed`/`Failed` siblings are listed compactly):

- `StartChildWorkflowExecutionInitiated` → `ChildWorkflowExecutionStarted` (for `WfMakeLLMText`)
- `ChildWorkflowExecutionCompleted` (or `Failed`)

…and the `WfMakeLLMText` child's *own* history adds:

- `WorkflowExecutionStarted`
- `WorkflowTaskScheduled` / `WorkflowTaskStarted` / `WorkflowTaskCompleted`
- `ActivityTaskScheduled` (`act_llm_gen_text`) → `ActivityTaskStarted` → `ActivityTaskCompleted` / `Failed`
- `WorkflowTaskScheduled` / `WorkflowTaskStarted` / `WorkflowTaskCompleted`
- `WorkflowExecutionCompleted`

So per LLM call: roughly **two `Initiated`/`Started`/`Completed` triplets in the parent + a full child workflow history of about a dozen events**, plus a separate child workflow execution to track.

After the collapse, the same call inside the parent is just:

- `ActivityTaskScheduled` → `ActivityTaskStarted` → `ActivityTaskCompleted` / `Failed`

…three events, in the parent's history, no child workflow. For a `make_text_then_object` (today: one `WfMakeTextThenObject` child wrapping two `act_llm_gen_*` activities — `pipelex/temporal/tprl_content_generation/wf_make_object.py:87-111`), the saving is the same: lose the child-workflow framing events, keep the two activity invocations.

A long `PipeSequence` of N LLM steps therefore goes from "N child-workflow scheduling pairs in parent + N small child histories" to "N activity scheduling pairs in parent". This is the bulk of the history-event reduction motivating the wider refactor — and unlike the wholesale "operators-as-activities" alternative, it does not cost any per-LLM-call durability, because the activity boundary is still there.

### Worker registration

`pipelex/temporal/tasks.py:30-51`: `crafting` `TaskPack`'s `workflow_list` shrinks from nine workflow types to zero (or to whatever auxiliary workflows we want to keep there — currently nothing). The `activity_list` (the seven `act_*` functions) is unchanged. `pipe` `TaskPack` is unchanged.

The `worker_scopes` config in `pipelex/pipelex.toml:535-567` ("full", "router", "runner") is by reference: it requires the `crafting` and `pipe` packs by *name*, so the scope definitions don't need to change. The bare `router` scope (which sets `disable_all_activities=true`) currently registers nine fewer workflows; the runner scope (which sets `disable_all_workflows=true`) is unaffected.

### Retry semantics

Today, each `WfMake*` workflow constructs its `start_activity(…)` call with `retry_policy=worker_config.retry_policy` (`pipelex/temporal/tprl_content_generation/wf_make_llm_text.py:25-31`, and the parallel sites in the other `wf_make_*` files). That's a single global default — the per-workflow retry knob in `WorkflowExecutorFactory.create_executor(…)` (`pipelex/temporal/tprl/workflow_caller.py:219-248`) lets a *caller* override the policy at workflow-dispatch time, but `ContentGeneratorChild` doesn't pass anything custom (`pipelex/temporal/tprl_content_generation/content_generator_child_factory.py:29` plumbs the config default through). So in practice, every content-gen activity already runs under the same `worker_config.retry_policy_config`.

After the collapse, the new in-workflow `ContentGenerator` should pass `retry_policy=get_config().temporal.worker_config.retry_policy` at every `workflow.execute_activity(…)` call site. This preserves identical semantics. Any future "per-content-generation-kind retry policy" feature would now plug in at the activity invocation in the new generator rather than on a per-workflow basis — practically the same surface, just relocated.

The non-retryable error list in `pipelex/pipelex.toml:494-501` (`ExtractHandleNotFoundError`, `FileNotFoundError`, `ImgGenHandleNotFoundError`, `LLMHandleNotFoundError`, `ModelNotFoundError`, `ValidationError`) survives untouched — it's part of `worker_config.retry_policy`.

### Per-call timeouts and task-queue routing

The current `WfMake*` workflows pin both `start_to_close_timeout=worker_config.workflow_execution_timeout` and (in the LLM-text case only, `pipelex/temporal/tprl_content_generation/wf_make_llm_text.py:30`) `task_queue=worker_config.inference_task_queue`. The other `wf_make_*` files do **not** route to `inference_task_queue`; their activities run on the workflow's own task queue. So today's de-facto routing rule is:

- LLM-text completions → `inference_task_queue` (when set)
- Object-mode LLM, image gen, extract, render-page-views, templating → workflow's own queue

After the collapse, the new in-workflow `ContentGenerator` re-applies the same rule at each call site: pass `task_queue=worker_config.inference_task_queue` only on the `act_llm_gen_text` invocation. This preserves the split-worker test in `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py:77-89`. It does not change the production deployment topology.

The `WfMake*` workflows' own `workflow_execution_timeout` argument (passed at child dispatch from `ContentGeneratorChild`'s `execute_child_workflow(…)`, ultimately `pipelex/temporal/tprl/workflow_caller.py:167`) disappears. The activity-level `start_to_close_timeout` already plays an equivalent role: it bounds how long an LLM call may run. Today's "child workflow execution timeout" was always larger than or equal to its single activity's `start_to_close_timeout` — both came from the same `worker_config.workflow_execution_timeout` (`pipelex/temporal/tprl_content_generation/wf_make_llm_text.py:28`), so collapsing to just the activity timeout is a no-op for happy-path execution and slightly tighter on the failure path (no separate workflow timeout to wait through).

### Direct-mode (non-Temporal) execution

In `pipelex/pipelex.py:338-351`, when `temporal.is_enabled` is false, `ContentGenerator` (the direct, non-Temporal one) is registered. That branch is unchanged; non-Temporal flows keep their current behavior end-to-end.

The `ContentGeneratorChild` branch (`pipelex/pipelex.py:341-347`) is reached when `temporal.is_enabled` is true. In production, `get_content_generator()` is called from inside `WfPipeRouter` (via the operator's `pipe_llm.py` / `pipe_img_gen.py` / etc.), so the registered child generator is always invoked from a workflow context. There is no production code path that calls `ContentGeneratorChild`'s methods at top-level outside of a workflow — `ContentGeneratorChild.make_llm_text` (`pipelex/temporal/tprl_content_generation/content_generator_child.py:80-116`) calls `WorkflowExecutorFactory[…].create_executor().execute_child_workflow(WfMakeLLMText, …)`, which uses `workflow.execute_child_workflow` from the `temporalio.workflow` module (`pipelex/temporal/tprl/workflow_caller.py:161`); that call hard-fails outside a workflow. So the *existing* contract is "this generator only works inside a workflow."

After the collapse, the new in-workflow generator's contract is the same: each method calls `workflow.execute_activity(…)`, which also hard-fails outside a workflow. Direct-mode is unaffected because direct-mode never gets this generator wired in.

### Dry-run path

In dry mode, `ContentGeneratorDry` is registered at `pipelex/pipelex.py:339-340`. `temporal.is_enabled` is gated *after* the dry check, so dry-mode does not depend on the temporal generator. The collapse does not touch this. `WfTestContentGeneratorChild` in `pipelex/temporal/test_extras/wf_test_content_generator_child.py:53-66` switches between `ContentGeneratorDry` and (post-refactor) the new in-workflow generator based on its `is_dry_run` arg — same shape as today.

### Routing of nested controller calls

`TemporalPipeRouter._run_pipe_job` (`pipelex/temporal/tprl_pipe/temporal_pipe_router.py:46-91`) is unchanged. `PipeController` sub-pipes still dispatch as `WfPipeRouter` child workflows, exactly as today. The collapse only affects what happens *inside* the leaf `WfPipeRouter` when its pipe is a `PipeOperator`.

---

## 3. Pros vs. current code

- **History-event reduction.** Concretely measurable: each LLM/img/extract/jinja2 call inside a `WfPipeRouter` drops from "child workflow + activity" (≈15 events including child-workflow framing) to "activity only" (3 events). On a deep `PipeSequence` this is the dominant factor in approaching the 10K-event soft limit. The wholesale alternative documented in `wip/operators-as-activities-analysis.md` got the same reduction at the cost of per-LLM-call durability; this narrower refactor gets the reduction without that cost, because the activity is preserved.
- **One fewer indirection in the Temporal UI.** Today, finding the actual LLM call requires drilling into `WfPipeRouter` → `WfMakeLLMText` → `act_llm_gen_text` (three workflow-execution levels in `pipelex/temporal/tprl_pipe/wf_pipe_router.py:127` → `pipelex/temporal/tprl_content_generation/content_generator_child.py:99-105` → `pipelex/temporal/tprl_content_generation/wf_make_llm_text.py:25-31`). After: `WfPipeRouter` → `act_llm_gen_text`. The activity is one level below the controller it belongs to, which matches the actual semantics.
- **Less code to maintain.** Two near-duplicate generator implementations (`ContentGeneratorTop` + `ContentGeneratorChild`) — the only real difference between them is `execute_workflow` versus `execute_child_workflow` — collapse into one in-workflow generator. Their factories and the `AssignmentType`/`ResultType` plumbing in `content_generator_models.py` are gone.
- **No new abstractions required.** Activities, the `act_*` functions, the registration in `tasks.py`'s `crafting` pack — all already exist and stay in place. The refactor is largely deletion.
- **`make_text_then_object` becomes more honest.** Today, `WfMakeTextThenObject` (`pipelex/temporal/tprl_content_generation/wf_make_object.py:76-120`) wraps two activities in a child workflow whose only job is to glue them together with an `LLMAssignmentFactory.make_llm_assignment(preliminary_text=…)` call between them (`wf_make_object.py:96-104`). After collapsing, that same Python glue runs in the parent `WfPipeRouter` (between two `workflow.execute_activity` calls) — fewer hops, same logic.
- **Eliminates the "where does retry / timeout / task_queue config live?" dual-source-of-truth problem.** Today some of those knobs are on the `WfMake*` workflow's `start_activity(…)` call (`wf_make_llm_text.py:25-31`), some are on the `ContentGeneratorChild` factory plumbing (`content_generator_child_factory.py:13-34`), and the test override in `test_split_worker_usage.py:77-89` mutates `worker_config.inference_task_queue` and *trusts* `WfMakeLLMText` to read it on every child-workflow invocation. After collapsing, all those knobs apply at the single `workflow.execute_activity(…)` call site.

---

## 4. Cons / risks vs. current code

- **Loss of distinct workflow IDs per content-generation call in the Temporal UI.** Today, `ContentGeneratorChild.make_llm_text` builds a `child_workflow_id` from the parent's id + `wfid` (`pipelex/temporal/tprl_content_generation/content_generator_child.py:57-71, 102-106`), and the same is true for every other method. Operators and tests pass `wfid=` to give a Temporal-UI-visible name to a specific content-generation step. After the collapse, the activity has no comparable "ID" surface — only `activity_id`, which is auto-assigned by the SDK and not user-controllable. Effect on observability: per-step naming is lost in the Temporal UI; you'd need to rely on activity logs, the `act_*` function name, and the `JobMetadata.content_generation_job_id` field that `update_job_metadata` already stamps on the `JobMetadata` (`pipelex/cogt/content_generation/content_generator_protocol.py:26-43`). This is the most concrete observability regression.
- **Loss of the per-content-generation `workflow_execution_timeout`.** Today each `WfMake*` carries its own `execution_timeout` (today derived from `worker_config.workflow_execution_timeout`, but a future per-call override is on the table). After the collapse there is only the activity's `start_to_close_timeout`. In practice this is the same value today (see §2 *Per-call timeouts*), so no regression today — but you've lost a future axis of independent control.
- **`with_conditional_worker` removal from the content-gen path.** This is the decorator at `pipelex/temporal/tprl/conditional_worker.py:14-41` that, in `INTERNAL` worker mode, spins up a per-call worker on a UUID-suffixed task queue (`conditional_worker.py:25-37`). Today every method on `ContentGeneratorTop` is wrapped with it. The decorator is *only* relevant for top-level dispatch (it spins up a *workflow* worker; activities can ride on whatever worker is already up). Post-refactor, `ContentGeneratorTop` is gone, so the wrap on those methods disappears for free; the decorator file remains because `TemporalPipeRouter` and `TemporalPipeRun` still use it. Net: fewer call sites, no behavioral change for the test suite that uses `INTERNAL` mode against `WfPipeRouter` / `WfPipeRun`.
- **Determinism implications.** This is the biggest "subtle bug" risk. Today the `wf_make_*` workflow body is a thin layer (typically just `start_activity` + error translation), all calls run inside `WfPipeRouter`'s sandbox already, and the `ContentGenerator` adapter for child workflows lives in `content_generator_child.py` outside the sandboxed import path. After the refactor, the new in-workflow generator's *whole* method body — including any helper utility it calls — runs inside `WfPipeRouter`'s sandbox.

  Looking at `ContentGeneratorChild` today, its method bodies already do (a) construct `LLMAssignment` / `ObjectAssignment` / `TemplatingAssignment` / `ImgGenAssignment` / `ExtractAssignment` / `RenderPageViewsAssignment` Pydantic models, (b) call `LLMPromptTemplate.make_for_structuring_from_preliminary_text()` for the `…ThenObject…` path, (c) re-validate the returned object via `object_class.model_validate(obj.model_dump(serialize_as_any=True))` (`content_generator_child.py:157, 207, 248-299`), and (d) build child workflow IDs via `make_child_workflow_id(…)` (`content_generator_child.py:57-71`). All of those already run inside `WfPipeRouter`'s sandboxed workflow code today (they're imported through the `with workflow.unsafe.imports_passed_through():` block in `wf_pipe_router.py:8-22` indirectly, since `pipe.run_pipe(…)` reaches operator code that calls `get_content_generator()` and dispatches).

  So there is *no new* determinism surface introduced by collapsing — the same code already runs inside the workflow today. The only new line is `workflow.execute_activity(…)` replacing `WorkflowExecutorFactory[…].create_executor().execute_child_workflow(…)`. Both are deterministic Temporal SDK calls. The risk is therefore mostly one of *reorganization* — making sure the new generator doesn't accidentally pull in a non-passing-through import on top of what's already there. A boot test (`make tb`) and the existing `library_crate` integration suite catch this kind of regression cheaply.
- **Default activity worker.** Today, `WfMakeLLMText` is the only call with `task_queue=worker_config.inference_task_queue` (`wf_make_llm_text.py:30`). The other `wf_make_*` files don't pass `task_queue`, so their activities run on the *workflow's* task queue (`wf_make_object.py:38-40, 64-66, 88-92, 106-111, 134-139, 153-158`; `wf_make_images.py:27-32`; `wf_make_jinja2_text.py:29-34`; `wf_make_extract.py:27-32`; `wf_render_page_views.py:27-32`). After the refactor, the new in-workflow generator must replicate this choice exactly. Easy to mis-handle if a reviewer thinks "we should route everything to inference_task_queue" — it'd break the `crafting` pack registration on the runner workers (which today register the LLM activity on the inference queue and the others on the default queue).

  Mitigation: write the new generator with a comment at the LLM-text site explicitly stating the asymmetric routing rule, and add a unit test that asserts the call-site `task_queue` parameter for each method.
- **Tests that depend on the current workflow topology.** The biggest cluster:
    - `test_tprl_content_generator_top.py` (deletes wholesale).
    - `test_tprl_make_content_generator.py` (deletes wholesale).
    - `test_tprl_content_generator_child.py` (small touch — re-points).
    - `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py` (test logic still works; docstrings need updating to reflect that the `inference_task_queue` override now applies at the activity-call site rather than at `WfMakeLLMText.start_activity`).
    - `tests/integration/pipelex/temporal/workflows/test_wf_gen_text.py` and `test_wf_jinja2.py` — already commented-out historical tests that referenced `WfMakeLLMText` / `WfMakeJinja2Text`. Delete the files outright.
    - The `library_crate/` test suite (`tests/integration/pipelex/temporal/library_crate/`) tests `WfPipeRouter`-level behavior and does not directly reference the `WfMake*` classes — should pass unchanged.
    - The `tracing/` suite primarily exercises `WfPipeRouter` and its `act_flush_trace_events` activity; its dependence on `WfMake*` is only indirect (through the inference activity dispatch). Should pass unchanged after the LLM-call site is correctly task-queue-routed.

  Replay tests, if any, that pickle a `WfMake*` history will break — none in the current tree.
- **Pre-existing behavioral divergence to be aware of (flag-and-fix candidate).** `ContentGenerator.make_extract_pages` (the direct-mode one, `pipelex/cogt/content_generation/content_generator.py:386-405`) augments its return with `make_render_page_views(…)` when `extract_job_params.should_include_page_views` is true. The Temporal-mode `ContentGeneratorChild.make_extract_pages` (`pipelex/temporal/tprl_content_generation/content_generator_child.py:497-532`) does not — it just dispatches `WfMakeExtract` and returns the page contents as-is, missing the page-view augmentation. The collapse is a good moment to fix that asymmetry: the new in-workflow generator can mirror `ContentGenerator.make_extract_pages`'s control flow exactly, dispatching `act_extract_gen_extract_pages` and (when needed) `act_render_page_views` as two separate activity calls. Today's `WfMakeExtract` cannot do that because it's a single-activity wrapper. This flag-and-fix is in scope per the project's "flag and fix existing bugs" principle.

---

## 5. Refactoring plan

The ordering below preserves direct-mode parity at every step (direct-mode never depends on the temporal content-generation classes) and keeps Temporal mode green at every checkpoint. Each numbered step ends with `make agent-check && make agent-test` (or, during local dev, the `tests/integration/pipelex/temporal/` subset).

1. **Add the new in-workflow content generator class.** Create `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py`. Implement `ContentGeneratorInWorkflow` (or pick a better name) with the same `ContentGeneratorProtocol` surface and method-by-method bodies that call `workflow.execute_activity(act_*, arg=..., start_to_close_timeout=worker_config.workflow_execution_timeout, retry_policy=worker_config.retry_policy [, task_queue=worker_config.inference_task_queue for LLM-text only])`. Wrap with the `ActivityError → TemporalError.from_app_error(…)` translation that today lives in each `wf_make_*` (`wf_make_llm_text.py:32-35` and parallels). Add a factory that returns the instance (no kwargs needed beyond the `GeneratedContentFactory`).

   At this step, nothing is wired yet. Run `make agent-check`.

2. **Wire the new generator behind a feature flag.** Add a temporary boolean in `pipelex/pipelex.py`'s ContentGenerator selection (`pipelex.py:338-351`) — e.g., environment-flag-gated — that picks the new generator instead of `ContentGeneratorChild` when `temporal.is_enabled`. Default: still `ContentGeneratorChild`. This is a *transient* flag; do not add it to `pipelex.toml`. Run `tests/integration/pipelex/temporal/library_crate/` and `tracing/` with the flag flipped on; assert that the suites pass. The flag isolates risk.

3. **Re-point `WfTestContentGeneratorChild`.** Update `pipelex/temporal/test_extras/wf_test_content_generator_child.py:62-65` to construct the new in-workflow generator (rather than `ContentGeneratorChild`). This validates one full `make_llm_text` / `make_object_direct` / `make_text_then_object` / `make_object_list_direct` / `make_text_then_object_list` / `make_templated_text` / `make_extract_pages` round-trip via `test_wf_child_crafter.py:17-32` and `test_tprl_content_generator_child.py:18-33`. The test workflow itself is the harness for the new code path.

4. **Migrate the `make_extract_pages` page-views augmentation.** While the new generator is being written, mirror `ContentGenerator.make_extract_pages`'s `should_include_page_views` branch by calling `act_render_page_views` inline after `act_extract_gen_extract_pages` returns. This fixes the pre-existing divergence noted in §4.

5. **Flip the default.** Once §3 is green, swap the feature flag default so the new generator is the production path. Run `make agent-test`.

6. **Delete `ContentGeneratorChild`, `ContentGeneratorTop`, factories, and the `wf_make_*` workflow files.** All in one commit, per the project's "no backward compatibility" rule:
    - Files listed under §1 *Delete*.
    - Imports in `pipelex/temporal/tasks.py:30-51` (drop the `WfMake*` and `WfRenderPageViews` from `crafting.workflow_list`).
    - The feature flag added in step 2.
    - `tests/integration/pipelex/temporal/content_generation/test_tprl_content_generator_top.py` (whole file).
    - `tests/integration/pipelex/temporal/content_generation/test_tprl_make_content_generator.py` (whole file).
    - `tests/integration/pipelex/temporal/workflows/test_wf_gen_text.py` and `test_wf_jinja2.py` (whole files — already commented-out historical tests).
    - The `top_crafter` and `child_crafter` fixtures in `tests/integration/pipelex/temporal/content_generation/conftest.py:46-73`.

7. **Update docstrings.** `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py:60-68, 77-89` and `tracing/helpers.py:179-231` reference `WfMakeLLMText` by name. Rewrite the docstrings to describe the new direct-activity-call topology. The test logic does not change.

8. **No `patched()` calls needed if the deploy is hard-cut.** Per project rule: there is no backward-compat transition. The constraint is that no in-flight Pipelex workflows may be running during the deploy. If that constraint cannot be enforced operationally — i.e. there are persistent long-running pipelines in production — then `workflow.patched("collapse-content-generation-layer")` would be needed at *every* `ContentGenerator.make_*` call in the new generator, with a fallback path that dispatches the legacy `WfMake*`. Recommendation: enforce the drain-before-deploy constraint and skip `patched()`.

---

## 6. Size estimate

- **Files deleted:** the `wf_make_*.py` set (six files) plus `wf_render_page_views.py`, `content_generator_top.py`, `content_generator_top_factory.py`, `content_generator_child.py`, `content_generator_child_factory.py`, `content_generator_models.py`. Plus four test files (`test_tprl_content_generator_top.py`, `test_tprl_make_content_generator.py`, `test_wf_gen_text.py`, `test_wf_jinja2.py`).
- **Files created:** one (`content_generator_in_workflow.py`).
- **Files modified:** `pipelex/temporal/tasks.py`, `pipelex/pipelex.py`, `pipelex/temporal/test_extras/wf_test_content_generator_child.py`, `tests/integration/pipelex/temporal/content_generation/conftest.py`, `tests/integration/pipelex/temporal/content_generation/test_tprl_content_generator_child.py`, `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py` (docstring only), `tests/integration/pipelex/temporal/tracing/helpers.py` (docstring only).
- **Effort:** small. Most of the work is mechanical — the `ContentGeneratorChild.make_*` method bodies are already in the right shape; the change at each call site is replacing a `WorkflowExecutorFactory[…].execute_child_workflow(WfMakeXxx, …)` with `workflow.execute_activity(act_xxx, …)` and folding the `wf_make_*.py` argument-assembly inline (mostly trivial — see `wf_make_object.py:87-104` for the only nontrivial case, the `…ThenObject…` glue between two activities). Budget: a focused day for code, plus a day for the test-fixture migration and flipping the feature flag.
- **Where bugs are likely to hide:**
    - The asymmetric `task_queue=worker_config.inference_task_queue` rule — easy to forget on the LLM-text site or to over-apply to other sites. Add an explicit unit test that mocks `workflow.execute_activity` and asserts the `task_queue=` kwarg per method.
    - The `make_text_then_object` / `…_list` glue between two activities. The current `wf_make_object.py:96-104` does an `await workflow_arg.llm_assignment_factory_to_object.make_llm_assignment(preliminary_text=preliminary_text)` *between* the two activities; that line currently runs inside the child-workflow sandbox. After the refactor it runs inside `WfPipeRouter`'s sandbox instead. `LLMAssignmentFactory.make_llm_assignment` is async — verify it doesn't internally do anything sandbox-forbidden (network I/O, time access, random). Quick code read suggests it just constructs a Pydantic model from the prompt template; safe.
    - The `model_validate(obj.model_dump(serialize_as_any=True))` round-trips at `content_generator_child.py:157, 207, 248-299`. These are needed because the activity boundary returns a generic `BaseModel` (`act_llm_gen_object` is typed `-> BaseModel` at `act_llm_generate.py:16`). The new generator must keep these round-trips at the same place; otherwise structured-output validation regresses. The temporal data converter handles `BaseModel` inheritance via `kajson` already (`pipelex/temporal/temporal_data_converter.py`), but `model_validate` against the *concrete* class is what guarantees the output type expected by callers.
    - The page-views augmentation in `make_extract_pages` (today missing, fixed during the refactor). Make sure the new branch doesn't double-emit when `should_include_page_views` is false.
- **Replay-history compatibility:** none. Any workflow that's mid-flight at deploy time and references `WfMakeLLMText` etc. in its history will fail to replay. Drain or fail-fast all in-flight Pipelex workflows before deploy.

---

## 7. Recommendation

**Yes, do this — and do it before the wholesale operators-as-activities refactor (if that ever happens).**

The wholesale alternative (`wip/operators-as-activities-analysis.md`) explicitly recommends this narrower change as the most-of-the-benefit, fraction-of-the-risk subset. The analysis here confirms that:

- The history-event reduction is real (≈12 events per LLM call → 3) and is the dominant practical motivation for either refactor.
- Per-LLM-call durability — the biggest concern about the wholesale alternative — is **fully preserved**, because the activity boundary is unchanged.
- The `LibraryCrate` / `ClassRegistry` / `WorkingMemory` transit machinery — which is where most of the bug-finding effort would go in the wholesale alternative — is **completely untouched** here. That's the determinism work this scope explicitly avoids.
- The deletion is mostly mechanical and concentrated in one directory (`pipelex/temporal/tprl_content_generation/`).

**Ordering vs. other open work.** This refactor is best done when the temporal integration tests are otherwise green and stable, since the move flips which generator is registered into the hub. It is *not* worth coupling with a release: do it on a dev branch, run the full temporal suite + the `library_crate` and `tracing` subdirectories, and only land it once those pass. If a release or a Temporal-related feature is in flight (e.g. payload codec work, `ClassRegistry` propagation work), defer this until after the in-flight feature lands and stabilizes — the refactor is purely subtractive and gains nothing by being interleaved.

**Open question to surface during implementation, not before:** the "loss of distinct workflow IDs per content-generation call in the Temporal UI" cost in §4. If the UI breadcrumbs are heavily used by ops today, consider before §6 whether to invest in setting `activity_id=` explicitly via the SDK's `activity.start_activity(...)` overrides to reproduce the `wfid`-based naming, or whether logs + `JobMetadata.content_generation_job_id` are sufficient. The decision can be made independently of the rest of the refactor.
