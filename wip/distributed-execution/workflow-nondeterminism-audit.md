# Workflow Nondeterminism Audit — worker-local inputs leaking into the command stream

**Status: H1 and M1 fixed; remaining findings are diagnosis only.** Multi-agent audit of all code reachable inline from `@workflow.defn` bodies, run on top of the PR #984 fix (commit `db669ea62`, which gated `act_flush_trace_events` on the payload's `trace_context` instead of worker-local `tracing_config.is_enabled`). Every finding below was adversarially verified against the actual code; refuted candidates are listed at the end so they don't get re-chased.

**The breach definition used throughout:** any input read in code executing inline on the workflow thread (the `@workflow.run` body and everything it calls outside `@activity.defn` functions) that is not derived from the workflow payload or workflow APIs (`workflow.now()`, `workflow.uuid4()`, history), and that influences the command stream — whether/which/how many activities or child workflows get scheduled, their order, arguments, timeouts, retry policies, or task queues. Config reads inside activity bodies or at submission time are fine.

**Key calibration from verification (matters for prioritization):** Temporal's replay checker compares command *sequence, types, and IDs* — **not input payloads**. So worker-local inputs that flip *whether a command is emitted* cause the TMPRL1100 silent-hang class; inputs that only change *command arguments* (activity args, timeouts, retry policies, task queues of not-yet-scheduled commands) cause silent skew, not hangs. Both are breaches; only the first class reproduces the PR #984 symptom.

## Inline/activity boundary (map facts)

Everything from `WfPipeRouter.run` → `pipe.run_pipe` → controller/operator `_live_run_*` paths (Jinja prompt rendering, model-deck resolution, class-registry lookups, PipeFunc user functions) executes inline on the workflow thread. The activity boundary is exactly the `workflow.execute_activity(...)` calls inside `ContentGeneratorInWorkflow.make_*`. Controller pipes (`PipeSequence`/`PipeParallel`/`PipeCondition`/`PipeBatch`) dispatch every sub-pipe as a child `WfPipeRouter` via `hub.get_pipe_router()` → `TemporalPipeRouter`; operator pipes are *not* turned into activities wholesale — each runs inline inside its own child workflow and only its inference/templating/extract/img/search leaves cross to activities. `TemporalPipeRun` and `WorkflowExecutorFactory` are submitter-only (no in-workflow branch). The dry-run path (`run_mode=DRY`, `ContentGeneratorDry`) is reachable inline — `run_mode` comes from the payload and nothing on the Temporal dispatch path gates DRY out.

---

## HIGH — can reproduce the TMPRL1100 silent hang (command-count divergence)

These two finish what PR #984 started: scheduling around the flush activity and library teardown in `wf_pipe_router.py` is still not a pure function of payload + history.

### H1. Flush activity gated on a buffer that activities populate cross-thread — empty on replay — **FIXED**

> **Fixed:** `WfPipeRouter` now schedules `act_flush_trace_events` unconditionally whenever the payload carries a `trace_context` (the activity no-ops on an empty list), and `ReportingManager._emit_usage_event` routes any emission coming from inside a Temporal activity (`activity.in_activity()`) to the per-process runner fallback — co-located activities never write into the workflow's in-sandbox buffer. Guarded by `tests/integration/pipelex/temporal/test_wf_pipe_router_costs_only_flush_nondeterminism.py`.

`pipelex/reporting/reporting_manager.py:176` + `pipelex/temporal/tprl_pipe/wf_pipe_router.py:221`

`WfPipeRouter` registers its `BufferingEventLog` in the process-global `ReportingManager._event_log_contexts` keyed by `wf_{workflow_id}`. The single Worker registers workflows and activities in one process, so co-located **activity** completions (`report_inference_job`) hit the fast path and mutate the workflow's buffer from the activity thread. In costs-only mode (`emit_usage_events=True, emit_graph_events=False` — a first-class payload option, see `pipeline_run_setup.py`) the tracer gets `event_log=None`, so those activity-side emissions are the *only* buffer content. Live execution drains a non-empty buffer and schedules `act_flush_trace_events`; on replay, activity results come from history without executing, the recreated buffer stays empty, and the `if buffered_events:` gate emits no flush command. A `ScheduleActivityTask` present in history but absent on replay → TMPRL1100 **from a routine sticky-cache eviction on the same worker** — no config skew or fleet heterogeneity needed. Symmetrically, routing activities to a different queue/worker, or `is_reporting_enabled=false` on the replaying worker (a `ReportingNoOp` never populates the buffer), flips the same command. Graph+usage mode is safe for the boolean (inline tracer emissions re-fire deterministically on replay) — only costs-only mode flips command emission.

**Fix:** gate the flush dispatch purely on the payload (`trace_context` presence / emit flags) and let the activity no-op on an empty event list; stop routing activity-side usage events through the workflow's in-sandbox buffer (co-located activities should use the same runner-fallback per-process event log they use when remote).

### H2. Eviction skips library teardown → leaked fingerprint poisons same-worker replay

`pipelex/temporal/tprl_pipe/wf_pipe_router.py:96` (setup) and `:241` (teardown)

Worker-local cleanup (`get_library_manager().teardown(wf_library_id)`) sits in the `finally` block *after* the awaited flush activity. Eviction-time interruptions (`_WorkflowBeingEvictedError` — a `BaseException` subclass raised by `_assert_not_read_only` when the workflow is being deleted; also `CancelledError` paths) bypass the `except Exception` at line 229 and abort the `finally` before teardown runs, leaking `_libraries` and `_loaded_fingerprints` in the worker-local `LibraryManager` singleton, keyed by the *deterministic* `wf_{workflow_id}`. On same-worker sticky replay: `open_library` returns the stale library, `set_class_registry` installs a **fresh** registry seeded only from the global one, and `load_from_crate` is fingerprint-skipped (`library_manager.py:388-393`) — so the crate's dynamic classes are never registered into the new registry. `hydrate_working_memory` then raises `PipeJobError` inline where history recorded successful pipe execution → the workflow takes the error path instead of re-emitting recorded commands → command-stream divergence. Triggers are routine: cache eviction under load + tracing-on payload + same-worker replay. The common variant self-heals on the next task retry (that replay's synchronous `finally` tears the leak down), but the persistent-hang variant exists with dynamic-class activity results on a single-worker queue.

**Fix:** scope the fingerprint dedup to the registry instance (clear `_loaded_fingerprints` when `set_class_registry` swaps the registry), or have `WfPipeRouter` force-teardown any pre-existing library under its deterministic id before opening; additionally move worker-local cleanup before the awaited flush activity or into an eviction-safe guard.

---

## MEDIUM — command-stream breaches (which/how many commands, or known-residual divergence)

### M1. The known residual: best-effort tracing-setup `except Exception` — **FIXED**

> **Fixed:** `GraphTracerManager.open_tracer` is now collision-proof (pop-and-replace of a stale tracer key with a WARNING, instead of raising), and the best-effort `except Exception` around tracing setup in `WfPipeRouter` was removed entirely — the setup block is pure in-memory state, so any failure is a real bug that surfaces deterministically (and re-fires identically on replay).

`pipelex/temporal/tprl_pipe/wf_pipe_router.py:160`

The catch-all around tracing setup nulls `event_log` on any worker-local failure, so the flush command at line 223 is never emitted while history contains it. Reachable with identical config on both workers: `GraphTracerManager.open_tracer` raises `ValueError` on a stale tracer key leaked by a prior interrupted execution (`graph_tracer_manager.py:133-135`, process-lifetime singleton keyed by `workflow_id`). Verification narrowed severity: fresh/restarted workers have empty singletons so routine churn does *not* trigger it — a leak requires a stuck eviction or `disable_safe_eviction` plus a same-`workflow_id` rerun on the poisoned worker. Aggravator: on *success* the block rewrites `workflow_arg.job_metadata` with `wf_trace_context`, which rides inside every child-workflow `PipeJob` and every content-generation activity argument — so setup success/failure also diverges the arguments of all subsequent commands. **Fix:** payload-pure flush gating (H1's fix) plus make `open_tracer` collision-proof (pop-and-replace instead of raise).

### M2. `PipeBatch` fan-out chunking from worker config

`pipelex/pipe_controllers/batch/pipe_batch.py:141` — `get_config().pipelex.pipeline_execution_config.max_concurrency` bounds `gather_bounded` over branches that each `workflow.execute_child_workflow`. The chunk size controls how many `StartChildWorkflowExecution` commands are emitted per workflow task and their grouping; a config edit rolled out while a batch workflow is in flight diverges replay (TMPRL1100) on any batch spanning multiple workflow tasks. **Fix:** carry `max_concurrency` in `pipe_run_params` (payload), stamped from config at the submission boundary.

### M3. Dry-run mock fan-out length from worker config

`pipelex/cogt/content_generation/content_generator_dry.py:94` (also `nb_extract_pages` at lines 233/262, `nb_list_items` again at 305, image params) — `dry_run_config.nb_list_items` sets the *length* of mock lists built inline; a downstream `PipeBatch` fans out one child workflow per item, so the recorded command count equals a worker-local config value. DRY runs reach Temporal: `dry_run_pipeline()` dispatches via `TemporalPipeRun` under a Temporal-enabled hub with no DRY gate on the path (PR #976 only localized the BundleValidator sweep). **Fix:** move dry-run synthesis into the activity (aligned with the dry-run-as-temporal-activity direction) or carry the dry-run params in the payload.

### M4. `PipeCondition` pipe resolution on the no-crate path

`pipelex/pipe_controllers/condition/pipe_condition.py:254` — the expression evaluation is deterministic from `WorkingMemory`, but the resolved pipe object selects *which* child workflow gets scheduled (and is embedded in its `PipeJob` argument). On the crate-backed path resolution is payload-pure (per-workflow library rebuilt from the crate); the **no-crate** path is real and supported (`PipeJob.library_crate` is `Optional`; `worker_cli.py` boot-loads a `worker_base` library), and there library drift between workers changes the child command or replaces it with an inline PipeNotFound error path. **Fix:** require crate-derived resolution for Temporal dispatch, or carry the resolved sub-pipe selection in the payload.

### M5. `PipeFunc` runs arbitrary user code inline; sync branch is broken outright

`pipelex/pipe_operators/func/pipe_func.py:183,189` — `PipeFunc` has no temporal-aware dispatch: the worker-local module-level `func_registry` read and the user function both execute inline on the workflow thread. Registry presence (function registered on one worker but not another — `LibraryCrate` carries blueprints, not functions) flips fail-vs-complete command paths. The coroutine branch runs unconstrained user async code inline, where nondeterministic success-vs-failure flips the command stream and user `asyncio` calls emit nondeterministically-parameterized timer commands. **Bonus functional bug found during verification:** the sync branch's `asyncio.to_thread` raises `NotImplementedError` under Temporal's workflow event loop (no `run_in_executor`) — sync PipeFunc functions cannot work inside workflows at all today; it fails deterministically, but it fails. **Fix:** execute PipeFunc user functions inside a dedicated activity (`act_run_func`) when in Temporal mode.

---

## MEDIUM/LOW — command-argument drift (silent skew, not hangs)

Temporal does not compare input payloads on replay, so these cannot TMPRL1100 — but recorded vs re-emitted command attributes diverge, and any not-yet-completed activity rescheduled after a config edit runs with different routing/args/policies than history recorded.

| Site | Worker-local input | What drifts | Fix |
|---|---|---|---|
| `tprl_content_generation/content_generator_in_workflow.py:113` (same pattern in every `make_*`: 154, 195, 265, 311, 350, 391, 429, 458, 491, 525) | `get_config().temporal.worker_config.resolve_dispatch` + `temporal.queue_options` at command-emission time | task_queue, all four timeouts, full RetryPolicy of every `ScheduleActivityTask` | move-to-payload: resolve `DispatchOptions` at the submission boundary and carry the per-activity dispatch bundle in `PipeJob`. Note `wf_pipe_run.py` already states and follows this exact principle for its child dispatch — the content generator violates it |
| `pipe_operators/llm/pipe_llm.py:196` (same pattern: `pipe_structure.py:125`, img-gen/extract operators) | worker-local model deck singleton (`get_model_deck()`; deck/config files, not in the crate) | resolved handle is both the activity arg (`LLMAssignment.llm_setting`) **and** the `routing_key` for `resolve_dispatch` → task-queue selection via `by_handle` | move-to-payload |
| `pipe_operators/llm/pipe_llm.py:219` | `pipelex.prompting_config` **plus mutation of `self.llm_prompt_spec` on the library-resident shared pipe object** (the `not templating_style` guard makes the first run on a worker win — sticky, order-dependent) | inline Jinja rendering → the LLM activity's prompt argument | move-to-payload for the style; separately, stop mutating library-resident pipe objects per-run |
| `pipe_operators/llm/pipe_llm.py:275` + `pipe_operators/structure/pipe_structure.py:132` | `cogt.llm_config` structure-prompt flag + template text | whether/how the structure-schema section is rendered into the activity-arg prompt | move-into-activity |
| `tprl_content_generation/content_generator_in_workflow.py:256` (and 302) | `cogt.img_gen_config` defaults | baked into `ImgGenAssignment` activity argument | move-into-activity |
| `tprl_content_generation/content_generator_in_workflow.py:385` (and 452) | `cogt.extract_config.default_page_views_dpi` (the default path always has `page_views_dpi=None`, so the read is always live) | `RenderPageViewsAssignment` activity argument | move-into-activity |
| `tprl/observability.py:104` | `temporal.search_attributes` (enabled flag + attribute subset) | `search_attributes` on `StartChildWorkflowExecution` (called from `wf_pipe_run.py:63` and `temporal_pipe_router.py:88`; the helper's docstring claims purity from `pipe_job` — the config read breaks that claim) | move-to-payload |
| `pipe_operators/compose/pipe_compose.py:317` | `pipeline_execution_config.is_mock_inputs` | raise vs mock-and-continue in the dry-run construct-mode except path — diverges the remaining command stream (low: needs a `StructuredContentComposerValueError` first) | move-to-payload |

### Randomness / clock cluster

Root cause: `pipelex/core/stuffs/stuff_factory.py:44` — `make_stuff_code()` is `shortuuid.uuid()[:5]`, and every operator's output stuff is minted inline on the workflow thread. The codes reach command arguments two ways: working memory serialized into child `PipeJob` args (`pipe_batch.py:138` branch codes → `final_stuff_code` on each branch's `PipeRunParams`; `sub_pipe.py:119` synthetic batch stuff; `pipe_batch.py:218` aggregate output), and the IOSpec digest inside trace events passed literally as the `act_flush_trace_events` argument. Adjacent instances:

- `pipelex/core/pipes/pipe_abstract.py:627` — `PipelineFactory.make_pipe_run_id()` is plain `uuid.uuid4()` per pipe run, stamped into the `child_metadata` that rides in every activity and child-workflow argument. Note the *child workflow id* was already fixed with `workflow.uuid4` (`temporal_pipe_router.py:72`) — the run id needs the same treatment.
- `pipelex/core/pipes/pipe_abstract.py:650` — OTel span creation inline: worker-local telemetry singleton decides span-vs-None and the SDK's random span-id generator feeds `child_metadata.otel_context` (low).
- `pipelex/graph/graph_tracer.py:250` — `datetime.now(timezone.utc)` timestamps in every trace event → flush activity argument (low; timestamps never gate emission).

**Fix shape for the whole cluster:** an injectable replay-safe id/clock provider that returns `workflow.uuid4()` / `workflow.now()` when inside a Temporal workflow, plain `shortuuid`/`uuid4`/`datetime.now` outside.

---

## LOW — test workflows (`test_extras/`, flaky-test risk only)

- `wf_test_child_pipe.py:43` — mutates the worker-global hub pipe library inline with hardcoded pipe codes; `add_new_pipe` raises on duplicates, so any replay or second run on the same worker fails inline before recorded commands. One verifier found these two workflows are currently **orphaned** (registered in `PIPELEX_TEMPORAL_TEST_WORKFLOWS` but not exercised by any test), which caps urgency.
- `wf_test_child_pipe.py:48` (and the other test workflows) — `JobMetadata` constructed inline, so `started_at`'s `default_factory=datetime.now` (`pipeline/job_metadata.py:91`) fires on the workflow thread and rides into every activity argument. The root is the naive `default_factory` itself — already tracked as a P0.2 follow-on in [README.md](README.md).
- `wf_test_content_generator_child.py:63,71` — worker-local model-deck alias resolution (`$testing-text` / `$testing-structured`) inline; a worker missing the alias raises before any downstream activity is scheduled.

---

## Refuted candidates (verified non-breaches — don't re-chase)

- **`temporal_error.py:198` config read of non-retryable name lists** — reachable workflow-side via `from_app_error`, but only sets log severity and the `non_retryable` flag on an unconditionally-raised error; no command divergence.
- **Kajson global `ClassRegistry` accumulation (`wf_pipe_router.py:89`)** — the only writes to the global registry happen at deterministic worker boot; per-workflow registries are seeded fresh.
- **`conditional_worker.py` INTERNAL branch (shortuuid + instance state)** — unreachable inside workflow bodies; the hub router that workflow-thread code resolves is always built EXTERNAL.
- **`wf_pipe_router.py:241` teardown raising on missing library** — `open_library` is idempotent and runs at line 96 on every replay before teardown can be reached.
- **`SubPipe` hub pipe lookup (`sub_pipe.py:45`)** — payload-derived on every supported crate-backed dispatch (the genuine gap is the `PipeCondition` no-crate path, M4).
- **`pipe_run_params_factory.py:19` `pipe_stack_limit` fallback** — production params are fully payload-derived; only the orphaned test workflows hit the config fallback.
- **`pipe_compose.py:292` dry generator selection** — the chosen generator is never invoked on any `PipeCompose` path.
- **`submitter_hydration.py:58` `uuid4`** — names a worker-local scoped library only; never reaches a command.
- **`pipe_abstract.py:474` `datetime.now` in `_run_pipe_traced`** — timestamps land only in trace-event activity args, never gate emission (subsumed by the clock-cluster note above).

---

## Suggested fix order

1. ~~**H1 + M1 together**~~ — **DONE**: `act_flush_trace_events` scheduling is a pure function of `trace_context` (always scheduled when present; activity no-ops on empty events), `open_tracer` is collision-proof, and activity-side usage events never route through the in-sandbox buffer. This finishes PR #984.
2. **H2** — fingerprint-cache scoping / force-teardown on `open_library`, plus eviction-safe cleanup ordering in the `finally`.
3. **Dispatch options to payload** — resolve `DispatchOptions` at the submission boundary and carry them in `PipeJob` (`ContentGeneratorInWorkflow` then reads only the payload), closing M2's sibling and the biggest argument-drift surface in one move.
4. **Replay-safe id/clock provider** for the randomness cluster.
5. **M3/M4/M5** individually as the dry-run-as-activity and PipeFunc-as-activity work lands.
