from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError
from typing_extensions import override

with workflow.unsafe.imports_passed_through():
    from pipelex.config import get_config
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.graph.graph_tracer_manager import GraphTracerManager
    from pipelex.hub import get_report_delegate
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.reporting.reporting_manager import ReportingManager
    from pipelex.temporal.log_temporal import workflow_log
    from pipelex.temporal.tprl.temporal_error import TemporalError
    from pipelex.temporal.tprl.workflow_caller import WorkflowClass
    from pipelex.temporal.tprl.workflow_library_setup import setup_workflow_library, teardown_workflow_library
    from pipelex.temporal.tprl_pipe.hydration import hydrate_working_memory
    from pipelex.tracing.ndjson_event_log import NdjsonEventLog


@workflow.defn(name="wf_pipe_router")
class WfPipeRouter(WorkflowClass[PipeJob, PipeOutput]):
    @override
    @workflow.run
    async def run(
        self,
        workflow_arg: PipeJob,
    ) -> PipeOutput:
        workflow_log.debug("Workflow start")

        pipe = workflow_arg.pipe
        workflow_log.verbose(f"Routing {pipe.__class__.__name__} pipe '{workflow_arg.pipe.code}': {pipe.description}")

        # Set up per-workflow library if a library crate is present
        library_crate = workflow_arg.library_crate
        wf_library_id: str | None = None

        # Per-workflow tracing state (declared before try for finally block access)
        event_log: NdjsonEventLog | None = None
        wf_graph_tracer_manager: GraphTracerManager | None = None
        wf_tracer_key: str | None = None
        graph_context = workflow_arg.job_metadata.graph_context

        try:
            if library_crate is not None:
                wf_library_id = setup_workflow_library(
                    library_crate=library_crate,
                    workflow_id=workflow.info().workflow_id,
                )

                # Hydrate WorkingMemory (now that dynamic classes are registered)
                if workflow_arg.working_memory_raw is not None:
                    workflow_arg.working_memory = hydrate_working_memory(workflow_arg.working_memory_raw)
                    workflow_arg.working_memory_raw = None

            # Set up per-workflow graph tracing if enabled
            pipeline_run_id = workflow_arg.job_metadata.pipeline_run_id
            wf_workflow_id = workflow.info().workflow_id

            tracing_config = get_config().pipelex.tracing_config
            if tracing_config.is_enabled and graph_context is not None:
                try:
                    event_log = NdjsonEventLog(traces_dir=tracing_config.traces_dir)
                    wf_graph_tracer_manager = GraphTracerManager.get_or_create_instance()
                    wf_tracer_key = wf_workflow_id
                    wf_graph_context = wf_graph_tracer_manager.open_tracer(
                        graph_id=graph_context.graph_id,
                        data_inclusion=graph_context.data_inclusion,
                        event_log=event_log,
                        workflow_id=wf_workflow_id,
                        pipeline_run_id=pipeline_run_id,
                        tracer_key=wf_tracer_key,
                    )
                    # Update job_metadata with the per-workflow graph_context (carries tracer_key),
                    # but preserve parent_node_id from the incoming context so CONTAINS edges
                    # link back to the parent workflow's controller node.
                    wf_graph_context = wf_graph_context.model_copy(
                        update={"parent_node_id": graph_context.parent_node_id},
                    )
                    workflow_arg.job_metadata = workflow_arg.job_metadata.model_copy(
                        update={"graph_context": wf_graph_context},
                    )
                    # Configure ReportingManager for usage event emission
                    report_delegate = get_report_delegate()
                    if isinstance(report_delegate, ReportingManager):
                        report_delegate.set_event_log(
                            context_key=wf_workflow_id,
                            event_log=event_log,
                            workflow_id=wf_workflow_id,
                            pipeline_run_id=pipeline_run_id,
                        )
                except Exception as exc:
                    workflow_log.warning(f"Failed to set up per-workflow tracing, continuing without: {exc}")
                    # Clean up partially initialized resources before nulling (the finally block
                    # won't be able to clean up after we null these references)
                    if wf_graph_tracer_manager is not None and wf_tracer_key is not None:
                        try:
                            wf_graph_tracer_manager.close_tracer(wf_tracer_key)
                        except Exception as tracer_exc:
                            workflow_log.warning(f"Failed to close partially initialized tracer: {tracer_exc}")
                    if event_log is not None:
                        try:
                            event_log.close()
                        except Exception:  # noqa: S110
                            pass
                    report_delegate = get_report_delegate()
                    if isinstance(report_delegate, ReportingManager):
                        report_delegate.clear_event_log(context_key=wf_workflow_id)
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
            # Close per-workflow graph tracer (flushes events to NDJSON)
            if wf_graph_tracer_manager is not None and wf_tracer_key is not None:
                try:
                    wf_graph_tracer_manager.close_tracer(wf_tracer_key)
                except Exception as tracer_exc:
                    workflow_log.warning(f"Failed to close per-workflow tracer: {tracer_exc}")
            if event_log is not None:
                try:
                    event_log.close()
                except Exception:  # noqa: S110
                    pass
                # Clear stale event log state from ReportingManager
                # wf_tracer_key is always set when event_log is not None (both assigned in same block)
                if wf_tracer_key is not None:
                    report_delegate = get_report_delegate()
                    if isinstance(report_delegate, ReportingManager):
                        report_delegate.clear_event_log(context_key=wf_tracer_key)

            if wf_library_id is not None:
                teardown_workflow_library(wf_library_id=wf_library_id)

        # Dehydrate PipeOutput for Temporal transit: serialize WorkingMemory to
        # raw dict so the parent's data converter can deserialize without needing
        # dynamic concept classes in its ClassRegistry.
        if library_crate is not None:
            pipe_output = pipe_output.prepare_for_temporal()

        workflow_log.debug("Workflow complete")
        return pipe_output
