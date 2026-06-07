from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError
from typing_extensions import override

with workflow.unsafe.imports_passed_through():
    from kajson.class_registry import ClassRegistry
    from kajson.kajson_manager import KajsonManager

    from pipelex.config import get_config
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.graph.graph_tracer_manager import GraphTracerManager
    from pipelex.hub import clear_current_library, get_library_manager, get_report_delegate, set_current_library
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.temporal.log_temporal import WorkflowLog
    from pipelex.temporal.tprl.temporal_error import TemporalError
    from pipelex.temporal.tprl.workflow_caller import WorkflowClass
    from pipelex.temporal.tprl_pipe.act_flush_trace_events import FlushTraceEventsArg, act_flush_trace_events
    from pipelex.temporal.tprl_pipe.hydration import hydrate_working_memory
    from pipelex.tracing.buffering_event_log import BufferingEventLog


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

        # Set up per-workflow library if a library crate is present
        library_crate = workflow_arg.library_crate
        wf_library_id: str | None = None

        # Per-workflow tracing state (declared before try for finally block access)
        event_log = None
        wf_graph_tracer_manager: GraphTracerManager | None = None
        wf_tracer_key: str | None = None
        trace_context = workflow_arg.job_metadata.trace_context

        pipe_output: PipeOutput | None = None

        try:
            if library_crate is not None:
                # 1. Create per-workflow ClassRegistry pre-seeded from global
                global_registry = KajsonManager.get_class_registry()
                workflow_registry = ClassRegistry()
                workflow_registry.register_classes_dict(global_registry.get_classes_dict())

                # 2. Open library and attach registry to it
                library_manager = get_library_manager()
                wf_library_id = f"wf_{workflow.info().workflow_id}"
                _wf_library_id, wf_library = library_manager.open_library(library_id=wf_library_id)
                wf_library.set_class_registry(workflow_registry)
                set_current_library(library_id=wf_library_id)

                # 3. Load crate (registers dynamic classes into workflow_registry via hub.get_class_registry())
                library_manager.load_from_crate(library_id=wf_library_id, crate=library_crate)

                # 4. Hydrate WorkingMemory if needed
                if workflow_arg.working_memory_raw is not None:
                    workflow_arg.working_memory = hydrate_working_memory(workflow_arg.working_memory_raw)
                    workflow_arg.working_memory_raw = None

            # Set up per-workflow graph tracing if enabled
            pipeline_run_id = workflow_arg.job_metadata.pipeline_run_id
            wf_workflow_id = workflow.info().workflow_id

            tracing_config = get_config().pipelex.tracing_config
            if tracing_config.is_enabled and trace_context is not None:
                try:
                    # Use BufferingEventLog inside workflows (no I/O allowed).
                    # Events are flushed to the real backend via act_flush_trace_events.
                    event_log = BufferingEventLog()
                    wf_graph_tracer_manager = GraphTracerManager.get_or_create_instance()
                    wf_tracer_key = wf_workflow_id
                    wf_trace_context = wf_graph_tracer_manager.open_tracer(
                        graph_id=trace_context.graph_id,
                        data_inclusion=trace_context.data_inclusion,
                        # D5: only feed the event log to the tracer when graph events are wanted. In
                        # costs-only mode the tracer still mints node ids but emits no graph events;
                        # usage events flow via the report delegate's set_event_log below.
                        event_log=event_log if trace_context.emit_graph_events else None,
                        workflow_id=wf_workflow_id,
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
                    # suppressed (the runner fallback also gates on emit_usage_events).
                    if trace_context.emit_usage_events:
                        get_report_delegate().set_event_log(
                            context_key=wf_workflow_id,
                            event_log=event_log,
                            workflow_id=wf_workflow_id,
                            pipeline_run_id=pipeline_run_id,
                        )
                except Exception as exc:  # noqa: BLE001
                    # Best-effort: per-workflow tracing setup must never fail the workflow — log and continue without it.
                    workflow_log.warning(f"Failed to set up per-workflow tracing, continuing without: {exc}")
                    # Clean up partially initialized resources before nulling (the finally block
                    # won't be able to clean up after we null these references)
                    if wf_graph_tracer_manager is not None and wf_tracer_key is not None:
                        try:
                            wf_graph_tracer_manager.close_tracer(wf_tracer_key)
                        except Exception as tracer_exc:  # noqa: BLE001
                            # Best-effort cleanup: closing a partially-initialized tracer must not mask the setup failure.
                            workflow_log.warning(f"Failed to close partially initialized tracer: {tracer_exc}")
                    if event_log is not None:
                        event_log.close()
                    get_report_delegate().clear_event_log(context_key=wf_workflow_id)
                    event_log = None
                    wf_graph_tracer_manager = None

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
        finally:
            # Close per-workflow graph tracer (collects in-memory graph spec). F1: only assign the spec
            # when graph events were requested — in costs-only mode close_tracer returns None (teardown
            # skips the spec build), and this guard keeps the contract explicit even if that changes.
            if wf_graph_tracer_manager is not None and wf_tracer_key is not None:
                try:
                    graph_spec = wf_graph_tracer_manager.close_tracer(wf_tracer_key)
                    if graph_spec is not None and pipe_output is not None and trace_context is not None and trace_context.emit_graph_events:
                        pipe_output.graph_spec = graph_spec
                except Exception as tracer_exc:  # noqa: BLE001
                    # Best-effort: tracer close in the finally block must never fail the workflow — log and continue.
                    workflow_log.warning(f"Failed to close per-workflow tracer: {tracer_exc}")

            # Flush trace events and clean up event log
            if event_log is not None:
                # Drain buffered events and flush to the real backend via activity
                buffered_events = event_log.drain()
                if buffered_events:
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

                event_log.close()

                # Clear stale event log state from the report delegate
                if wf_tracer_key is not None:
                    get_report_delegate().clear_event_log(context_key=wf_tracer_key)

            if wf_library_id is not None:
                try:
                    get_library_manager().teardown(library_id=wf_library_id)
                finally:
                    clear_current_library()

        # Dehydrate PipeOutput for Temporal transit: serialize WorkingMemory to
        # raw dict so the parent's data converter can deserialize without needing
        # dynamic concept classes in its ClassRegistry.
        assert pipe_output is not None
        pipe_output = pipe_output.prepare_for_temporal(library_crate=library_crate)

        workflow_log.debug("Workflow complete")
        return pipe_output
