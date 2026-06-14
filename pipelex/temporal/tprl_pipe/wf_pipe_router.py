from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError, FailureError
from typing_extensions import override

with workflow.unsafe.imports_passed_through():
    from kajson.class_registry import ClassRegistry
    from kajson.kajson_manager import KajsonManager

    from pipelex.base_exceptions import PipelexError, iter_cause_chain
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.graph.graph_tracer_manager import GraphTracerManager
    from pipelex.hub import clear_current_library, get_library_manager, get_report_delegate, set_current_library
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.runtime_bridge.primitives.hydration import hydrate_working_memory
    from pipelex.temporal.log_temporal import WorkflowLog
    from pipelex.temporal.tprl.temporal_error import TemporalError
    from pipelex.temporal.tprl.workflow_caller import WorkflowClass
    from pipelex.temporal.tprl_pipe.act_flush_trace_events import FlushTraceEventsArg, act_flush_trace_events
    from pipelex.tracing.buffering_event_log import BufferingEventLog


def _carries_temporal_failure(exc: BaseException) -> bool:
    """True when ``exc`` or any error in its ``__cause__`` chain is a Temporal ``FailureError``.

    This is the hinge of the inline fail-safe: ``True`` ⇒ leave ``exc`` untouched,
    ``False`` ⇒ convert it with ``from_message_exception``. Carrying a Temporal
    ``FailureError`` *is* the definition of "already a terminal Temporal failure",
    so it is the predicate, not a proxy for a narrower type.

    The reachable case it protects: a controller pipe (e.g. ``PipeSequence``) runs a
    sub-pipe as a child workflow; the sub-pipe fails; ``TemporalPipeRouter`` wraps the
    ``ChildWorkflowError`` as ``WorkflowExecutionError`` (``temporal_pipe_router.py``),
    which escapes the parent's ``pipe.run_pipe`` into the ``except PipelexError`` below.
    That ``WorkflowExecutionError`` carries no report of its own — the rich leaf
    classification lives deeper, in the child's ``ApplicationError.details``, reachable
    only by ``recover_error_report``'s ``__cause__`` walk at the submitter (which
    normalizes ``ChildWorkflowError.cause`` into the chain). A worker-side
    ``from_message_exception`` here would flatten it, because ``to_error_report``'s
    enrichment stops at the non-``PipelexError`` ``ChildWorkflowError``. So we propagate.

    Invariant this relies on: disciplined ``raise … from`` usage. The one way it can
    misattribute is "recover-then-rechain" — pipe code that handles a side failure and
    then raises a *fresh, unrelated* error ``from`` the one it already recovered. The
    fresh error would then carry that side ``FailureError`` and propagate untouched,
    surfacing the side failure's classification instead of its own. Don't do that: a
    fresh error must only be chained ``from`` the error that actually caused it.

    Walks via ``iter_cause_chain`` (single cyclic-guard). See
    ``docs/under-the-hood/error-model.md`` "Workflow-Level Fail-Safe Floor" for the
    design narrative.
    """
    return any(isinstance(node, FailureError) for node in iter_cause_chain(exc))


@workflow.defn(name="wf_pipe_router")
class WfPipeRouter(WorkflowClass[PipeJob, PipeOutput]):
    @override
    @workflow.run
    async def run(
        self,
        workflow_arg: PipeJob,
    ) -> PipeOutput:
        # Bound once per invocation: every record below carries this run's
        # request_id (None when the run carries no inbound API request id).
        workflow_log = WorkflowLog(request_id=workflow_arg.job_metadata.request_id)
        workflow_log.debug("Workflow start")

        pipe = workflow_arg.pipe
        workflow_log.verbose(f"Routing {pipe.__class__.__name__} pipe '{workflow_arg.pipe.code}': {pipe.description}")

        # Run-scoped identity for ALL per-run worker-local state (library id, tracer key,
        # event-log context key) and for event/node-id stamps: run_id is replay-stable but
        # unique per run, so a reused workflow id (workflow-level retry_policy, Temporal
        # reset, resubmission of the same pipeline_run_id) can never collide with a live
        # successor run's state on the same worker.
        wf_run_id = workflow.info().run_id

        # Set up per-workflow library if a library crate is present
        library_crate = workflow_arg.library_crate
        wf_library_id: str | None = None

        # Per-workflow tracing state (declared before try for finally block access).
        # schedule_flush is the payload-pure flush gate, computed in the tracing setup
        # block below (see the determinism comments there and in the finally).
        event_log = None
        wf_tracer_key: str | None = None
        schedule_flush: bool = False
        trace_context = workflow_arg.job_metadata.trace_context

        pipe_output: PipeOutput | None = None

        try:
            if library_crate is not None:
                # 1. Create per-workflow ClassRegistry pre-seeded from global
                global_registry = KajsonManager.get_class_registry()
                workflow_registry = ClassRegistry()
                workflow_registry.register_classes_dict(global_registry.get_classes_dict())

                # 2. Open library and attach registry to it. The library id is keyed by run_id —
                # replay-stable (a replay of this run sees the same run_id) but unique per run.
                # Keying by workflow_id would collide across runs: workflow ids are reused by
                # workflow-level retry_policy, Temporal reset, and resubmission of the same
                # pipeline_run_id (make_workflow_id is deterministic), so a closed predecessor
                # run's late eviction cleanup could tear down a live successor run's library.
                # With run_id keying, a pre-existing library under this id can only be THIS run's
                # own leftover — an evicted/interrupted execution whose finally never ran (H2):
                # reusing it would fingerprint-skip the crate load below against the fresh
                # registry, so the crate's dynamic classes never land in it and inline hydration
                # fails where history recorded success. open_fresh_library tears any such
                # leftover down — pure in-memory, no commands emitted, so it is replay-safe.
                library_manager = get_library_manager()
                wf_library_id = f"wf_{wf_run_id}"
                wf_library = library_manager.open_fresh_library(library_id=wf_library_id)
                wf_library.set_class_registry(workflow_registry)
                set_current_library(library_id=wf_library_id)

                # 3. Load crate (registers dynamic classes into workflow_registry via hub.get_class_registry())
                library_manager.load_from_crate(library_id=wf_library_id, crate=library_crate)

                # 4. Hydrate WorkingMemory if needed
                if workflow_arg.working_memory_raw is not None:
                    workflow_arg.working_memory = hydrate_working_memory(workflow_arg.working_memory_raw)
                    workflow_arg.working_memory_raw = None

            # Set up per-workflow graph tracing if enabled.
            pipeline_run_id = workflow_arg.job_metadata.pipeline_run_id

            # Determinism: whether tracing is set up — and therefore whether the finally
            # block schedules act_flush_trace_events — must be a pure function of the
            # workflow payload, never of worker-local state (which can differ between
            # the worker that recorded the history and the one replaying it, causing a
            # [TMPRL1100] nondeterminism error). The presence of trace_context IS the
            # submitter's decision; the worker-local tracing_config.is_enabled check
            # lives in the flush activity, where reading local config is legal. No
            # best-effort guard around this block: every step is pure in-memory state
            # (no I/O, no config reads) and open_tracer is collision-proof against
            # tracer keys leaked by a prior interrupted execution, so a failure here
            # is a real bug that must surface — and being inline-deterministic, it
            # re-fires identically on replay.
            if trace_context is not None:
                # Use BufferingEventLog inside workflows (no I/O allowed).
                # Events are flushed to the real backend via act_flush_trace_events.
                event_log = BufferingEventLog()
                wf_tracer_key = wf_run_id
                # Payload-pure flush gate: the buffer is populated exclusively by inline
                # (workflow-thread) emissions, and since the unified dry run moved leaf
                # mocking inside the activities, the only inline source left is graph
                # events from the tracer when emit_graph_events is on. Every usage
                # emission — LIVE, DRY, or mock-usage — happens activity-side via the
                # per-process runner fallback, so with graph events off the buffer is
                # deterministically empty and the flush round-trip is skipped. The gate
                # input rides in the payload, so the decision replays identically.
                schedule_flush = trace_context.emit_graph_events
                wf_trace_context = GraphTracerManager.get_or_create_instance().open_tracer(
                    graph_id=trace_context.graph_id,
                    data_inclusion=trace_context.data_inclusion,
                    # D5: only feed the event log to the tracer when graph events are wanted. In
                    # costs-only mode the tracer still mints node ids but emits no graph events;
                    # usage events flow via the report delegate's set_event_log below.
                    event_log=event_log if trace_context.emit_graph_events else None,
                    workflow_id=wf_run_id,
                    pipeline_run_id=pipeline_run_id,
                    tracer_key=wf_tracer_key,
                    # Threaded in so the returned context is born with the correct flags (no emit-flag
                    # footgun in the model_copy below).
                    emit_graph_events=trace_context.emit_graph_events,
                    emit_usage_events=trace_context.emit_usage_events,
                )
                # Update job_metadata with the per-workflow trace_context (carries tracer_key + emit
                # flags), but preserve parent_node_id from the incoming context so CONTAINS edges link
                # back to the parent workflow's controller node.
                wf_trace_context = wf_trace_context.model_copy(
                    update={"parent_node_id": trace_context.parent_node_id},
                )
                workflow_arg.job_metadata = workflow_arg.job_metadata.model_copy(
                    update={"trace_context": wf_trace_context},
                )
                # Configure the report delegate for usage event emission — only when cost reporting
                # is on. In graph-only mode no usage context is registered, so usage events are
                # suppressed (the runner fallback also gates on emit_usage_events). Only emissions
                # from the workflow thread itself would land in this buffer — and since the unified
                # dry run moved leaf mocking inside the activities, no such inline source currently
                # exists: ReportingManager routes activity-side emissions to its per-process
                # fallback even when the activity runs co-located, so the buffer content stays a
                # deterministic function of inline execution and re-fires identically on replay.
                if trace_context.emit_usage_events:
                    get_report_delegate().set_event_log(
                        context_key=wf_tracer_key,
                        event_log=event_log,
                        workflow_id=wf_run_id,
                        pipeline_run_id=pipeline_run_id,
                    )

            working_memory = workflow_arg.get_working_memory()
            pipe_output = await pipe.run_pipe(
                job_metadata=workflow_arg.job_metadata,
                working_memory=working_memory,
                output_name=workflow_arg.output_name,
                pipe_run_params=workflow_arg.pipe_run_params,
                library_crate=library_crate,
            )
        except ActivityError as exc:
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        except PipelexError as exc:
            # Inline fail-safe floor: a domain error raised inline in workflow code (never via an
            # activity) is neither an ActivityError nor an ApplicationError, so without this clause
            # it escapes as a non-terminal workflow-task failure and retries indefinitely — a silent
            # hang (see docs/under-the-hood/error-model.md "Workflow-Level Fail-Safe Floor"). Convert
            # a genuine inline error to a terminal, classified TemporalError; leave one that already
            # carries a Temporal failure untouched for the submitter to recover. The propagate-vs-
            # convert decision and the invariant it relies on live in _carries_temporal_failure.
            # Scoped to PipelexError: transient Temporal/infra errors keep Temporal's task-retry.
            # force_non_retryable: an inline error must fail terminally, not trigger a blunt whole-
            # workflow retry that re-runs completed inline work — retry belongs at the activity
            # boundary. It also keeps this workflow-side conversion config-free (deterministic).
            if _carries_temporal_failure(exc):
                raise
            raise TemporalError.from_message_exception(exc=exc, force_non_retryable=True) from exc
        finally:
            # ALL worker-local cleanup in this finally is synchronous and runs before the
            # awaited flush activity at the end. Eviction safety (H2): the flush await is a
            # suspension point where a BaseException can be raised (_WorkflowBeingEvictedError
            # on sticky-cache eviction) — it escapes the `except Exception` around the flush
            # and aborts the rest of this finally block. Worker-local cleanup (tracer,
            # event-log context, per-workflow library + crate fingerprint) must therefore run
            # BEFORE that await, so an eviction can no longer leak state keyed by the
            # deterministic wf_{run_id} into the worker-local singletons and poison a
            # same-worker replay. (Workflow cancellation is NOT such an interruption: at an
            # activity await the SDK surfaces it as an ActivityError — an Exception — which
            # the best-effort except around the flush swallows.)

            # Close per-workflow graph tracer (collects in-memory graph spec). In costs-only
            # mode close_tracer returns None by contract (teardown skips the spec build), so
            # the graph_spec gate alone keeps costs-only outputs spec-free.
            if wf_tracer_key is not None:
                try:
                    graph_spec = GraphTracerManager.get_or_create_instance().close_tracer(wf_tracer_key)
                    if graph_spec is not None and pipe_output is not None:
                        pipe_output.graph_spec = graph_spec
                except Exception as tracer_exc:  # noqa: BLE001
                    # Best-effort: tracer close in the finally block must never fail the workflow — log and continue.
                    workflow_log.warning(f"Failed to close per-workflow tracer: {tracer_exc}")
                # Clear stale event log state from the report delegate, under the SAME key
                # set_event_log registered it with (clear_event_log is a no-op pop when no
                # context was registered, e.g. graph-only mode).
                get_report_delegate().clear_event_log(context_key=wf_tracer_key)

            if wf_library_id is not None:
                try:
                    get_library_manager().teardown(library_id=wf_library_id)
                except Exception as teardown_exc:  # noqa: BLE001
                    # Best-effort: library teardown in the finally block must never fail the
                    # workflow or skip the remaining worker-local cleanup below — log and
                    # continue. LibraryManager forgets the entry pop-first even when the
                    # library's own teardown raises, so no poisoned state remains.
                    workflow_log.warning(f"Failed to tear down per-workflow library: {teardown_exc}")
                finally:
                    clear_current_library()

            if event_log is not None:
                buffered_events = event_log.drain()
                event_log.close()

                # The awaited flush comes LAST: an interruption here can only skip the flush
                # itself, never the worker-local cleanup above — and on replay the buffer is
                # rebuilt deterministically from inline execution, so the flush re-fires with
                # the same content.
                #
                # Determinism (H1): the schedule is a pure function of the payload — the
                # event_log sentinel (trace_context presence) and schedule_flush
                # (emit_graph_events, a payload field). It must NOT be gated on the buffer
                # CONTENT: anything written into the buffer from outside the workflow
                # thread would not be re-written on replay (activities do not re-execute),
                # so a content-gated schedule recorded in history could vanish from the
                # replayed command stream after a routine sticky-cache eviction
                # ([TMPRL1100]). The payload-pure schedule_flush gate only skips
                # graph-events-off runs, where the buffer is deterministically empty (see
                # the tracing setup block). The activity no-ops on an empty list either way.
                if schedule_flush:
                    try:
                        await workflow.execute_activity(
                            act_flush_trace_events,
                            arg=FlushTraceEventsArg(events=buffered_events),
                            start_to_close_timeout=timedelta(seconds=30),
                            retry_policy=RetryPolicy(maximum_attempts=3),
                        )
                    except Exception as flush_exc:  # noqa: BLE001
                        # Best-effort: trace-event flush in the finally block must never fail the workflow — log and continue.
                        workflow_log.warning(f"Failed to flush trace events: {flush_exc}")
                elif buffered_events:
                    # Tripwire, not a guard: with graph events off the buffer is deterministically
                    # empty by the invariant above, so this branch is unreachable today. If a
                    # future inline emission path breaks that invariant, these events would be
                    # silently discarded — turn that into a log line instead.
                    workflow_log.warning(f"Discarding {len(buffered_events)} buffered trace events: flush skipped by the graph-events-off gate")

        # Dehydrate PipeOutput for Temporal transit: serialize WorkingMemory to
        # raw dict so the parent's data converter can deserialize without needing
        # dynamic concept classes in its ClassRegistry.
        assert pipe_output is not None
        pipe_output = pipe_output.prepare_for_temporal(library_crate=library_crate)

        workflow_log.debug("Workflow complete")
        return pipe_output
