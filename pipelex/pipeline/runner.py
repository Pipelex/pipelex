from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

from mthds.client.pipeline import PipelineState
from mthds.client.protocol import RunnerProtocol
from pydantic import ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.config import get_config
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.hub import (
    get_library_manager,
    get_pipe_router,
    get_report_delegate,
    get_telemetry_manager,
    teardown_current_library,
)
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipeline.exceptions import PipeExecutionError, PipelineExecutionError
from pipelex.pipeline.pipeline_response import PipelexPipelineExecuteResponse
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.system.telemetry.events import EventName, EventProperty, Outcome
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

if TYPE_CHECKING:
    import asyncio

    from mthds.client.pipeline import PipelineStartResponse
    from mthds.models.pipe_output import VariableMultiplicity
    from mthds.models.pipeline_inputs import PipelineInputs
    from mthds.models.working_memory import WorkingMemoryAbstract

    from pipelex.core.memory.working_memory import WorkingMemory
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.pipe_run.pipe_run_mode import PipeRunMode
    from pipelex.system.configuration.configs import PipelineExecutionConfig


class PipelexRunner(RunnerProtocol["PipeOutput"]):
    """Pipelex implementation of the mthds RunnerProtocol.

    Adapts pipelex pipeline execution to the mthds protocol interface.
    Pipelex-specific configuration (library directories, run mode, etc.)
    is provided at construction time.
    """

    def __init__(
        self,
        library_id: str | None = None,
        library_dirs: list[str] | None = None,
        bundle_uris: list[str] | None = None,
        pipe_run_mode: PipeRunMode | None = None,
        search_domain_codes: list[str] | None = None,
        user_id: str | None = None,
        execution_config: PipelineExecutionConfig | None = None,
    ):
        self.library_id = library_id
        self.library_dirs = library_dirs
        self.bundle_uris = bundle_uris
        self.pipe_run_mode = pipe_run_mode
        self.search_domain_codes = search_domain_codes
        self.user_id = user_id
        self.execution_config = execution_config
        self._running_tasks: dict[str, asyncio.Task[PipeOutput]] = {}

    @override
    async def execute_pipeline(
        self,
        pipe_code: str | None = None,
        mthds_contents: list[str] | None = None,
        inputs: PipelineInputs | WorkingMemoryAbstract[Any] | None = None,
        output_name: str | None = None,
        output_multiplicity: VariableMultiplicity | None = None,
        dynamic_output_concept_code: str | None = None,
    ) -> PipelexPipelineExecuteResponse:
        """Execute a pipeline and wait for its completion.

        This method executes a pipe and returns its output. Unlike ``start_pipeline``,
        this method waits for the pipe execution to complete before returning.

        Pipelex-specific configuration (library directories, run mode, etc.) is provided
        at construction time via the ``PipelexRunner`` constructor.

        Parameters
        ----------
        pipe_code:
            Code identifying the pipe to execute. Required when ``mthds_contents`` is not
            provided. When both ``mthds_contents`` and ``pipe_code`` are provided, the
            specified pipe from the MTHDS contents will be executed (overriding any
            ``main_pipe`` defined in the contents).
        mthds_contents:
            List of MTHDS bundle contents as strings. The pipe to execute is determined by
            ``pipe_code`` (if provided) or the ``main_pipe`` property in the content.
            Can be combined with ``library_dirs`` to load additional definitions.
        inputs:
            Inputs passed to the pipeline. Can be either a ``PipelineInputs`` dictionary
            or a ``WorkingMemory`` instance.
        output_name:
            Name of the output slot to write to.
        output_multiplicity:
            Output multiplicity specification.
        dynamic_output_concept_code:
            Override the dynamic output concept code.

        Returns:
        -------
        PipelexPipelineExecuteResponse
            The pipeline execution response wrapping the pipe output, including
            pipeline run ID, timestamps, and pipeline state. If ``generate_graph``
            was True, the execution graph is available in the pipe output's
            ``graph_spec``.

        """
        created_at = datetime.now(timezone.utc).isoformat()

        # Use provided config or get default
        execution_config = self.execution_config or get_config().pipelex.pipeline_execution_config

        # Cast inputs: the protocol accepts WorkingMemoryAbstract but pipelex expects WorkingMemory
        pipelex_inputs: PipelineInputs | WorkingMemory | None = cast("PipelineInputs | WorkingMemory | None", inputs)

        properties: dict[EventProperty, Any]
        graph_spec_result = None
        # These variables are set in pipeline_run_setup and needed in finally/except blocks
        pipeline_run_id: str | None = None
        library_id_resolved: str | None = None
        pipe_job: PipeJob | None = None
        try:
            pipe_job, pipeline_run_id, library_id_resolved = await pipeline_run_setup(
                execution_config=execution_config,
                library_id=self.library_id,
                library_dirs=self.library_dirs,
                pipe_code=pipe_code,
                mthds_contents=mthds_contents,
                bundle_uris=self.bundle_uris,
                inputs=pipelex_inputs,
                output_name=output_name,
                output_multiplicity=output_multiplicity,
                dynamic_output_concept_code=dynamic_output_concept_code,
                pipe_run_mode=self.pipe_run_mode,
                search_domain_codes=self.search_domain_codes,
                user_id=self.user_id,
            )
            pipe_output = await get_pipe_router().run(pipe_job)
        except PipeRouterError as exc:
            # PipeRouterError can only be raised by get_pipe_router().run(), so pipe_job is guaranteed to exist
            assert pipe_job is not None  # for type checker
            properties = {
                EventProperty.PIPELINE_RUN_ID: pipeline_run_id,
                EventProperty.PIPE_TYPE: pipe_job.pipe.pipe_type,
                EventProperty.PIPELINE_OUTCOME: Outcome.FAILURE,
            }
            get_telemetry_manager().track_event(event_name=EventName.PIPELINE_COMPLETE, properties=properties)
            raise PipelineExecutionError(
                message=exc.message,
                run_mode=pipe_job.pipe_run_params.run_mode,
                pipe_code=pipe_job.pipe.code,
                output_name=pipe_job.output_name,
                pipe_stack=pipe_job.pipe_run_params.pipe_stack,
            ) from exc
        except PipelexError as exc:
            # Catch other Pipelex errors that bypass the router's PipeRunError handling
            # (e.g., PipeRunInputsError raised directly from pipe_abstract.py)
            # If pipe_job is None, the error occurred during pipeline_run_setup before pipe_job was created
            if pipe_job is None:
                raise
            properties = {
                EventProperty.PIPELINE_RUN_ID: pipeline_run_id,
                EventProperty.PIPE_TYPE: pipe_job.pipe.pipe_type,
                EventProperty.PIPELINE_OUTCOME: Outcome.FAILURE,
            }
            get_telemetry_manager().track_event(event_name=EventName.PIPELINE_COMPLETE, properties=properties)
            raise PipelineExecutionError(
                message=exc.message,
                run_mode=pipe_job.pipe_run_params.run_mode,
                pipe_code=pipe_job.pipe.code,
                output_name=pipe_job.output_name,
                pipe_stack=pipe_job.pipe_run_params.pipe_stack,
            ) from exc
        except ValidationError as exc:
            formatted_error = format_pydantic_validation_error(exc)
            model_name = exc.title
            msg = f"Input validation failed for '{model_name}': {formatted_error}"
            raise PipeExecutionError(message=msg) from exc
        finally:
            # Close graph tracer if it was opened (capture graph even on failure)
            # pipeline_run_id may be None if pipeline_run_setup failed early
            if execution_config.is_generate_graph and pipeline_run_id is not None:
                tracer_manager = GraphTracerManager.get_instance()
                if tracer_manager is not None:
                    graph_spec_result = tracer_manager.close_tracer(pipeline_run_id)

                # In Temporal mode with tracing enabled, assemble from events instead
                tracing_config = get_config().pipelex.tracing_config
                if tracing_config.is_enabled and get_config().temporal.is_enabled:
                    try:
                        from pipelex.graph.graphspec import PipelineRef  # noqa: PLC0415
                        from pipelex.reporting.reporting_manager import ReportingManager  # noqa: PLC0415
                        from pipelex.tracing.graphspec_assembler import GraphSpecAssembler  # noqa: PLC0415
                        from pipelex.tracing.ndjson_event_log import NdjsonEventLog  # noqa: PLC0415
                        from pipelex.tracing.usage_aggregator import UsageAggregator  # noqa: PLC0415

                        assembly_event_log = NdjsonEventLog(traces_dir=tracing_config.traces_dir)
                        try:
                            events = assembly_event_log.read_events(pipeline_run_id)
                            if events:
                                assembled_domain: str | None = None
                                assembled_main_pipe: str | None = None
                                if pipe_job is not None:
                                    assembled_domain = pipe_job.pipe.domain_code
                                    assembled_main_pipe = pipe_job.pipe.code
                                graph_spec_result = GraphSpecAssembler.assemble(
                                    events=events,
                                    graph_id=pipeline_run_id,
                                    pipeline_ref=PipelineRef(
                                        domain=assembled_domain,
                                        main_pipe=assembled_main_pipe,
                                    ),
                                )
                                # Aggregate usage from events so generate_report() includes cross-worker costs
                                usage_data = UsageAggregator.aggregate(events)
                                if usage_data:
                                    report_delegate = get_report_delegate()
                                    if isinstance(report_delegate, ReportingManager):
                                        report_delegate.inject_tokens_usages(
                                            pipeline_run_id=pipeline_run_id,
                                            tokens_usages=usage_data,
                                        )
                        finally:
                            assembly_event_log.close()
                    except Exception as exc:
                        log.warning(f"Failed to assemble graph from events, using in-memory graph: {exc}")

            # Clear event log state from ReportingManager (direct execution path)
            if pipeline_run_id is not None:
                from pipelex.reporting.reporting_manager import ReportingManager  # noqa: PLC0415

                report_delegate = get_report_delegate()
                if isinstance(report_delegate, ReportingManager):
                    report_delegate.clear_event_log(context_key=pipeline_run_id)

            # Only teardown library if it was successfully created
            if library_id_resolved is not None:
                get_library_manager().teardown(library_id=library_id_resolved)
                teardown_current_library()

        # Assign graph spec to output (only reached on success, when pipe_output is bound)
        if graph_spec_result is not None:
            pipe_output.graph_spec = graph_spec_result

        assert pipe_job is not None  # for type checker, success path requires a resolved job
        properties = {
            EventProperty.PIPELINE_RUN_ID: pipeline_run_id,
            EventProperty.PIPE_TYPE: pipe_job.pipe.pipe_type,
            EventProperty.PIPELINE_OUTCOME: Outcome.SUCCESS,
        }
        get_telemetry_manager().track_event(event_name=EventName.PIPELINE_COMPLETE, properties=properties)

        finished_at = datetime.now(timezone.utc).isoformat()
        return PipelexPipelineExecuteResponse.from_pipe_output(
            pipe_output=pipe_output,
            pipeline_run_id=pipe_output.pipeline_run_id,
            created_at=created_at,
            pipeline_state=PipelineState.COMPLETED,
            finished_at=finished_at,
        )

    @override
    async def start_pipeline(
        self,
        pipe_code: str | None = None,
        mthds_contents: list[str] | None = None,
        inputs: PipelineInputs | WorkingMemoryAbstract[Any] | None = None,
        output_name: str | None = None,
        output_multiplicity: VariableMultiplicity | None = None,
        dynamic_output_concept_code: str | None = None,
    ) -> PipelineStartResponse[PipeOutput]:
        raise NotImplementedError
