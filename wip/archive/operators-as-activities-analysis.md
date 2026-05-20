# Analysis: PipeOperators as Workflows vs. as Activities

## Current architecture (as observed)

**Two layers of workflows wrap every pipe execution:**

1. `WfPipeRun` (top-level) — orchestrates pipe execution + post-run side effects (graph assembly, delivery webhook)
2. `WfPipeRouter` (child workflow) — sets up per-workflow `LibraryCrate` / `ClassRegistry`, opens a graph tracer, hydrates `WorkingMemory`, delegates to `pipe.run_pipe(...)`, then dehydrates

**Inside `WfPipeRouter`, the actual pipe code runs:**

- A **PipeController** (`PipeSequence`, `PipeParallel`, `PipeBatch`, `PipeCondition`) iterates its sub-pipes. Each `SubPipe.run_pipe()` calls `get_pipe_router().run(...)` → which re-enters `TemporalPipeRouter._run_pipe_job` → which dispatches **another `WfPipeRouter` child workflow** (`pipelex/temporal/tprl_pipe/temporal_pipe_router.py:55-67`). So a sequence of N steps produces N additional child workflows below the parent router.
- A **PipeOperator** (`PipeLLM`, `PipeImgGen`, `PipeExtract`, etc.) runs in-process inside the same `WfPipeRouter` workflow execution, calling the `ContentGeneratorTop` protocol — which then dispatches **another workflow** per content-generation call (`WfMakeLLMText`, `WfMakeImages`, `WfMakeJinja2Text`, `WfMakeExtract`, …) which itself calls a single activity (`act_llm_gen_text`, etc.).

So the topology is roughly:

```
WfPipeRun (top)
  └─ WfPipeRouter (parent pipe)
      └─ [Controller iterates]
           ├─ WfPipeRouter (child sub-pipe 1)
           │    └─ [Operator's ContentGenerator]
           │         └─ WfMakeLLMText (workflow)
           │              └─ act_llm_gen_text (activity)
           ├─ WfPipeRouter (child sub-pipe 2)
           │    └─ ...
```

Pipe code (PipeLLM, PipeSequence, etc.) is **plain Python** and runs *inside* a workflow. The Temporal-ness is achieved by the `ContentGenerator` and `PipeRouter` protocols re-implemented as workflow-dispatching adapters.

---

## Alternative: PipeOperators as Activities

The proposed shape would be:

```
WfPipeRun (top)
  └─ WfPipeRouter (orchestrator)
      └─ [iterates sub-pipes]
           ├─ act_run_pipe_llm(pipe_llm_def, working_memory)   ← activity
           ├─ act_run_pipe_extract(...)                          ← activity
           ├─ act_run_pipe_img_gen(...)                          ← activity
           └─ child WfPipeRouter for nested controllers
```

Operators become a single activity that internally does prompt assembly + LLM call + structuring + output stuff building. Controllers stay as workflows because they need durable orchestration of multiple steps.

---

## Pros of the alternative (operators-as-activities)

1. **Smaller history footprint.** Today every PipeLLM produces a child `WfPipeRouter` + a `WfMake…` workflow + an activity = 3 workflow executions and ~15+ history events for a single LLM call. As an activity it's ~2 events (`ActivityScheduled` / `ActivityCompleted`). For long sequences, this matters: you can hit the 50 MB / 10K-event soft limit much faster with the current shape.

2. **Less workflow code = less determinism risk.** Today operator code (PipeLLM with prompt templating, structuring choices, output stuff assembly, `pretty_print_stuff`) runs *inside* `WfPipeRouter`. Anything in `pipe_operators/llm/helpers.py`, `pretty_print_stuff`, `_register_execution_data`, and the tracing manager calls runs in workflow context and is subject to sandbox + replay rules. Pushing all of that behind an activity boundary frees that code from determinism constraints — including third-party libs you might want to use later (json libs, jinja2 internals, etc.).

3. **Cheaper retries.** Today if an LLM call fails transiently, Temporal retries the **innermost activity** (`act_llm_gen_text`) — that part is already fine. But if the operator's *post-processing* (e.g. structuring validation) fails, you have a workflow failure that requires patching/versioning. As an activity, the whole operator is one retryable unit.

4. **Simpler mental model.** "Workflows orchestrate, activities do work" is the canonical Temporal pattern. PipeLLM is non-deterministic work (it calls an LLM). Modeling it as an activity matches the framework's grain.

5. **Fewer wrapper classes.** You can collapse the entire `tprl_content_generation/` package — `WfMakeLLMText`, `WfMakeObject`, `WfMakeImages`, `WfMakeJinja2Text`, `WfMakeExtract`, `WfRenderPageViews`, `ContentGeneratorTop`, `ContentGeneratorChild`, plus the dual `top`/`child` factory split — into a flat set of activities. The `with_conditional_worker` decorator and the WorkflowExecutor abstraction become unnecessary at the operator level.

6. **Better observability for "the actual unit of LLM work."** In the Temporal UI today, an LLM call is buried 4 levels deep. As an activity, it's a single line item with input/output/timing.

7. **Activity-level resource controls.** Temporal lets you configure per-activity concurrency, task queues (you already route `act_llm_gen_text` to `inference_task_queue`), and rate limiting. If operators are activities, you get this naturally for the *whole* operator, not just the inference call. Useful when a backend has its own rate limits beyond raw LLM tokens.

---

## Cons of the alternative

1. **You lose intra-operator durability.** Today, if the worker crashes mid-PipeLLM (after the LLM responded but before structuring completed), the `act_llm_gen_text` result is durably persisted; on resume, only the structuring is re-attempted. As one activity, the entire PipeLLM re-runs from scratch — you re-pay for the LLM call. This is the **biggest single trade-off**, and it's worse for `make_text_then_object` (two LLM calls) which today benefits from each call being durable independently.

2. **Operator code must be activity-safe in different ways.** Activities have their own constraints: payload-size limits on inputs/outputs, must be idempotent for retries (today retries are scoped to the inference call which is naturally idempotent — moving up means the *whole operator* including stuff-id generation, graph trace events, etc. needs to be safe-to-retry).

3. **Per-step controllability disappears.** Right now `WfMakeLLMText` is its own workflow with its own `workflow_execution_timeout`, `retry_policy`, and `task_queue`. Different content-generation kinds can have different policies. As activities, you still get per-activity policies — *but* the operator-level retry policy is now coarser (the LLM call and the structuring are one retryable unit even though they have different failure modes).

4. **PipeBatch fan-out semantics.** PipeBatch today expands into N parallel sub-pipes via `get_pipe_router().run(...)`, each becoming a child workflow. Each child gets its own retry budget and durable checkpoint. If you push operators into activities, batches of operators become a fan-out of activities (fine), but batches of *controllers* still need workflows. You'll end up with two dispatch paths inside a controller (activity for operators, child workflow for controllers) — slightly more complex than the current uniform "everything is a workflow" rule, even if the runtime is faster.

5. **Tracing/library state.** `WfPipeRouter` currently sets up per-workflow `LibraryCrate`, `ClassRegistry`, `BufferingEventLog`, and tracer key, and tears them down in `finally`. Some of this state currently lives in workflow-local variables. If the operator is an activity, the activity will run on a worker that may not have this state set up — you'd have to either (a) pass the crate to every activity (large payloads, repeated through history), or (b) keep the controller workflow's setup and rely on the worker to pick up the right context per activity invocation (which is awkward because activities aren't co-located with the workflow worker by default — you specifically use `inference_task_queue` to route the inference call to inference workers).

6. **`PipeJob` payload in every activity.** Today the dehydrated `WorkingMemory` flows through `WfPipeRouter` as a workflow input; from there, only small `LLMAssignment`-type payloads cross the activity boundary. If operators are activities, the full `WorkingMemory` (or its relevant subset) crosses the activity boundary on each call — and goes into history once (workflow → activity input → activity output → workflow). For a long sequence, the same `WorkingMemory` may cross many activity boundaries. You'd want to invest in S3-backed payloads or `WorkingMemory` deltas to avoid history bloat. This partially negates pro #1.

7. **Image/file payloads.** `wf_make_images.py` exists explicitly because image generation produces large binary payloads — there's already logic to store images at the activity level rather than in workflow history. Pushing operators up to activity-grain doesn't immediately break that, but you'd have to be careful that operator inputs/outputs continue to use references (URIs/IDs), not raw bytes.

8. **Loss of fine-grained progress for the user.** In Temporal UI / event history, you can see *exactly* what each PipeLLM did (template rendering activity vs. LLM activity vs. object structuring activity, in the current `wf_make_text_then_object`). As one activity, you lose that granularity and replace it with logs/heartbeats inside the activity. For debugging production LLM pipelines, the current granularity is actually valuable.

9. **Dry-run / direct-mode parity.** Pipelex pipes also run outside Temporal (direct mode). The operator's current "I just call a Python protocol method" works identically in direct mode. As an activity, the operator's `_live_run_operator_pipe` and the activity definition would diverge — you'd need a layer that calls them both from the same Python entry point. Not impossible (you already have `with_conditional_worker`), but it's added surface area on a code path that's currently uniform.

---

## Refactoring effort

If you wanted to move operators to activities, here's the rough shape of the work:

### Mandatory, high-effort

1. **Define one activity per operator type** (or one generic `act_run_operator(pipe_def, working_memory)`). Decide the granularity:
   - Per-type (`act_run_pipe_llm`, `act_run_pipe_img_gen`, `act_run_pipe_extract`, `act_run_pipe_func`, `act_run_pipe_search`, `act_run_pipe_compose`) — better typing, more activity registrations.
   - One generic activity dispatching on `pipe.type` — simpler registration, weaker typing.

2. **Refactor `ContentGeneratorTop` / `ContentGeneratorChild`.** Today they exist *because* operators run inside workflows and need to dispatch via `execute_workflow` / `execute_child_workflow`. Once operators are activities, the `ContentGenerator` adapter pattern can be deleted: the activity body just calls the direct (non-Temporal) `ContentGenerator`. This deletes most of `tprl_content_generation/` (`wf_make_*.py`, `content_generator_top.py`, `content_generator_child*.py`). Keep the inference activities (`act_llm_generate.py`, etc.) but they're now *internal helpers* the operator activity calls directly — or just inline them.

3. **WorkingMemory transit.** Each operator activity needs `WorkingMemory` as input and a `PipeOutput` (containing updated `WorkingMemory`) as output. This is the same dehydrate/rehydrate dance you already do at workflow boundaries — generalize `prepare_for_temporal()` / `rehydrate_pipe_output_with_crate()` to also work at activity boundaries. Probably need a "delta" form (only what changed) to avoid re-emitting the full memory on each step. **This is the trickiest piece** because of `kajson`'s class-registry-aware deserialization — activities running on inference workers need access to the `LibraryCrate`'s dynamic classes.

4. **LibraryCrate propagation to activities.** The crate currently flows into `WfPipeRouter` and is loaded into a per-workflow `ClassRegistry`. For activity execution, the activity worker must have the crate available — either pass it on every activity invocation (expensive, repeated in history) or maintain per-activity-worker session caches keyed by `pipeline_run_id`. The cleanest path is probably the latter: a "load crate" activity that primes the worker, then operator activities reference it by pipeline-run ID. Cache eviction and cross-worker concurrency need thought.

5. **`PipeRouter` rewrite.** `TemporalPipeRouter._run_pipe_job` currently dispatches `WfPipeRouter` for *any* pipe. It would need to:
   - For controllers → still dispatch `WfPipeRouter` (or new controller-specific workflows).
   - For operators → if called from inside a workflow, dispatch the operator activity; if called from outside (direct call), spin up a `WfPipeRouter` to wrap it. The "outside Temporal entirely" path stays the same.

6. **PipeController bodies.** Today `PipeSequence._live_run_controller_pipe` does `await sub_pipe.run_pipe(...)` which routes through `get_pipe_router()`. That router is currently a `TemporalPipeRouter` when running under Temporal, so each sub-pipe becomes a child workflow. After the refactor, the router needs to know whether the sub-pipe is operator-or-controller and pick activity vs. child workflow. This is a small change but it touches every controller.

7. **Tracing/observability integration.** The `BufferingEventLog` flush currently happens at the end of `WfPipeRouter` via `act_flush_trace_events`. If operators are activities, you need a way to capture trace events emitted *inside* the operator activity and surface them back to the parent workflow's buffering log — likely return them as part of the activity output and let the workflow append them.

8. **Replay/versioning story.** You have running Pipelex workflows in production (presumably). Changing the workflow shape is a non-trivial versioning event. You'd need either (a) a hard cut-over with all in-flight workflows drained first, or (b) Temporal's `patched()` API at every controller's dispatch site to keep both shapes alive during transition. With your "no backward compatibility" rule, hard cut-over is the natural choice — but only if you can guarantee no in-flight Pipelex workflows during the deploy.

### Optional / nice-to-have

9. **Collapse `WfPipeRun` and `WfPipeRouter`.** Once operators no longer need a workflow boundary, the two-level workflow split (`WfPipeRun` for delivery, `WfPipeRouter` for actual run) might be simplifiable to a single workflow per top-level pipe call.

10. **Per-operator task queues.** With operators as activities you can route each operator type to a different worker pool (e.g. `extract` to a heavy-CPU pool, `llm` to a thin async pool). You partially do this today via `inference_task_queue` for the innermost activity.

### Test/infra impact

11. The `temporal-test-crate` and `temporal-e2e-validate` test suites encode assumptions about the current workflow topology (cross-process serialization, deferred hydration, ClassRegistry scoping). These tests would need substantial rewrites — particularly the LibraryCrate / ClassRegistry isolation tests, since the propagation model changes.

12. Replay tests against existing histories will all break — either delete them or keep around a "legacy replay" suite during transition.

**Rough size estimate:** Medium-large refactor. The file changes are concentrated (~15-25 files), but the ClassRegistry / WorkingMemory transit logic at activity boundaries is genuinely subtle and is where most of the bug-finding effort would go. Budget on the order of 2–3 weeks of focused work plus another week or two on the test rewrite, assuming direct-mode parity is preserved throughout.

---

## Recommendation

**The current architecture is more "Temporal-canonical" only at first glance.** "Workflows orchestrate, activities do work" is the rule, and PipeLLM *is* work — so on paper it should be an activity. But the current shape buys something real: **per-call durability for LLM completions**, which is the most expensive thing a Pipelex pipe does. Losing that to retry whole operators would be a meaningful regression on cost and latency under failure.

The strongest case for refactoring isn't "operators should be activities" wholesale — it's **collapsing the `tprl_content_generation/` workflow layer**. That layer adds ~6 workflow types that wrap a single activity each. Eliminating those workflow wrappers (calling the activity directly from `PipeLLM.run` running inside `WfPipeRouter`) gets most of the history/footprint benefit without losing per-LLM-call durability. The inference call stays a durable activity; only the redundant workflow shell around it goes away.

If pursuing that narrower change first, the scope is much smaller — basically delete `wf_make_*.py` and `content_generator_top.py` / `content_generator_child*.py`, and have `ContentGenerator` (in operator code) directly call `workflow.execute_activity(act_llm_gen_text, ...)` when running inside a workflow.
