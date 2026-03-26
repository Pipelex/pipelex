from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError
from typing_extensions import override

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.pipe_job import PipeJob

with workflow.unsafe.imports_passed_through():
    from kajson.composite_class_registry import CompositeClassRegistry
    from kajson.kajson_manager import KajsonManager
    from temporalio import workflow

    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.hub import get_library_manager, set_current_library, teardown_current_library
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.temporal.log_temporal import workflow_log
    from pipelex.temporal.tprl.temporal_error import TemporalError
    from pipelex.temporal.tprl.workflow_caller import WorkflowClass
    from pipelex.temporal.tprl_pipe.hydration import hydrate_working_memory


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

        try:
            if library_crate is not None:
                # 1. Create scoped ClassRegistry (local overlay on global)
                global_registry = KajsonManager.get_class_registry()
                scoped_registry = CompositeClassRegistry(parent=global_registry)
                KajsonManager.set_scoped_class_registry(scoped_registry)

                # 2. Load crate (registers dynamic classes into scoped registry)
                library_manager = get_library_manager()
                wf_library_id = f"wf_{workflow.info().workflow_id}"
                library_manager.open_library(library_id=wf_library_id)
                set_current_library(library_id=wf_library_id)
                library_manager.load_from_crate(library_id=wf_library_id, crate=library_crate)

                # 3. Hydrate WorkingMemory (now that dynamic classes are registered)
                if workflow_arg.working_memory_raw is not None:
                    workflow_arg.working_memory = hydrate_working_memory(workflow_arg.working_memory_raw)
                    workflow_arg.working_memory_raw = None

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
            if wf_library_id is not None:
                get_library_manager().teardown(library_id=wf_library_id)
                teardown_current_library()
            if library_crate is not None:
                KajsonManager.set_scoped_class_registry(None)

        workflow_log.debug("Workflow complete")
        return pipe_output
