from __future__ import annotations

from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from mthds.protocol.exceptions import PipelineRequestError
from mthds.protocol.models import ModelCategory as MthdsModelCategory
from mthds.protocol.models import ModelDeck as MthdsModelDeck
from mthds.protocol.models import ModelInfo as MthdsModelInfo
from mthds.protocol.models import ValidationReport, VersionInfo
from mthds.protocol.protocol import MTHDSProtocol
from pydantic import Field, ValidationError
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.builder.operations.models_ops import ModelCategory, list_models
from pipelex.config import get_config
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.hub import (
    clear_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    get_pipe_run,
    get_pipeline_manager,
    get_report_delegate,
    get_telemetry_manager,
    set_current_library,
)
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipeline.exceptions import PipeExecutionError, PipelineExecutionError
from pipelex.pipeline.pipeline_response import PipelexRunResultExecute, PipelexRunResultStart, RunState
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.system.telemetry.events import EventName, EventProperty, Outcome
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

if TYPE_CHECKING:
    import asyncio

    from mthds.protocol.pipe_output import VariableMultiplicity
    from mthds.protocol.pipeline_inputs import PipelineInputs
    from mthds.protocol.working_memory import WorkingMemoryAbstract

    from pipelex.core.memory.working_memory import WorkingMemory
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.pipe_run.pipe_run_mode import PipeRunMode
    from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol
    from pipelex.system.configuration.configs import PipelineExecutionConfig

# The MTHDS Protocol version this runtime implements (mthds-protocol.openapi.yaml).
MTHDS_PROTOCOL_VERSION = "0.6.0"


class PipelexValidationReport(ValidationReport):
    """Pipelex's validation artifacts — this implementation's extensions on the
    protocol's `ValidationReport` (which declares no body fields).
    """

    blueprint: Any = None
    graph_spec: Any = None
    pipe_structures: Any = None
    pending_signatures: list[str] = Field(default_factory=list)
    is_runnable: bool = True


class PipelexModelDeck(MthdsModelDeck):
    """Pipelex's model deck — the protocol base plus this implementation's
    routing metadata (aliases, waterfalls).
    """

    aliases: dict[str, str] = Field(default_factory=dict)
    waterfalls: dict[str, list[str]] = Field(default_factory=dict)


class PipelexVersionInfo(VersionInfo):
    """Pipelex's version handshake — the protocol base plus this
    implementation's identification.
    """

    implementation: str
    implementation_version: str
    runtime_version: str | None = None


class PipelexMTHDSProtocol(MTHDSProtocol["PipeOutput"]):
    """Pipelex implementation of the mthds MTHDSProtocol.

    Adapts pipelex pipeline execution to the mthds protocol interface.
    Pipelex-specific configuration (library directories, run mode, etc.)
    is provided at construction time.
    """

    def __init__(
        self,
        *,
        library_id: str | None = None,
        library_dirs: list[str] | None = None,
        bundle_uris: list[str] | None = None,
        pipe_run_mode: PipeRunMode | None = None,
        is_mock_usage: bool = False,
        search_domain_codes: list[str] | None = None,
        user_id: str | None = None,
        execution_config: PipelineExecutionConfig | None = None,
        pipe_run: PipeRunProtocol | None = None,
    ):
        self.library_id = library_id
        self.library_dirs = library_dirs
        self.bundle_uris = bundle_uris
        self.pipe_run_mode = pipe_run_mode
        self.is_mock_usage = is_mock_usage
        self.search_domain_codes = search_domain_codes
        self.user_id = user_id
        self.execution_config = execution_config
        self._pipe_run = pipe_run
        self._running_tasks: dict[str, asyncio.Task[PipeOutput]] = {}

    @override
    async def execute(
        self,
        pipe_code: str | None = None,
        mthds_contents: list[str] | None = None,
        inputs: PipelineInputs | WorkingMemoryAbstract[Any] | None = None,
        output_name: str | None = None,
        output_multiplicity: VariableMultiplicity | None = None,
        dynamic_output_concept_ref: str | None = None,
        extra: dict[str, Any] | None = None,
        delivery_assignment: DeliveryAssignment | None = None,
    ) -> PipelexRunResultExecute:
        """Execute a pipeline and wait for its completion.

        This method executes a pipe and returns its output. Unlike ``start``,
        this method waits for the pipe execution to complete before returning.

        Pipelex-specific configuration (library directories, run mode, etc.) is provided
        at construction time via the ``PipelexMTHDSProtocol`` constructor.

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
        dynamic_output_concept_ref:
            Override the dynamic output concept ref.
        extra:
            Rejected — the local runtime defines no extension args. Extension
            args are server-specific; pass them to the server that defines them.
        delivery_assignment:
            Internal delivery hook used by the API layer (in-process, not a
            wire extension).

        Returns:
        -------
        PipelexRunResultExecute
            The pipeline execution response wrapping the pipe output, including
            pipeline run ID, timestamps, and pipeline state. If ``generate_graph``
            was True, the execution graph is available in the pipe output's
            ``graph_spec``.

        """
        if extra:
            msg = f"The local runtime defines no extension args; got {sorted(extra)}."
            raise PipelineRequestError(msg)

        created_at = datetime.now(timezone.utc).isoformat()

        # Use provided config or get default
        execution_config = self.execution_config or get_config().pipelex.pipeline_execution_config

        # Cast inputs: the protocol accepts WorkingMemoryAbstract but pipelex expects WorkingMemory
        pipelex_inputs: PipelineInputs | WorkingMemory | None = cast("PipelineInputs | WorkingMemory | None", inputs)

        properties: dict[EventProperty, Any]
        # These variables are set in pipeline_run_setup and needed in finally/except blocks
        pipeline_run_id: str | None = None
        library_id_resolved: str | None = None
        pipe_job: PipeJob | None = None
        # Capture the caller's outer current-library before pipeline_run_setup overwrites it with the
        # run library, so the finally can restore it instead of clobbering it (mirrors pipeline_run_setup's
        # own error-path restore).
        prev_library_id = get_current_library_id_or_none()
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
                dynamic_output_concept_ref=dynamic_output_concept_ref,
                pipe_run_mode=self.pipe_run_mode,
                is_mock_usage=self.is_mock_usage,
                search_domain_codes=self.search_domain_codes,
                user_id=self.user_id,
            )
            effective_pipe_run = self._pipe_run or get_pipe_run()
            pipe_output = await effective_pipe_run.run(pipe_job, delivery_assignment=delivery_assignment)
        except PipeRouterError as exc:
            # PipeRouterError can only be raised by get_pipe_run().run(), so pipe_job is guaranteed to exist
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
                # The live pipe_stack has fully unwound by now; PipeRouterError carries the
                # snapshot taken where the failure occurred.
                pipe_stack=exc.pipe_stack,
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
            # Close the tracer if it was opened (cleanup only — the PipeRun is responsible for capturing
            # the graph spec on pipe_output). The tracer is opened whenever graph OR cost reporting is on
            # (costs-only mode opens it with event_log=None), so the close gate must match that condition.
            if (execution_config.is_generate_graph or execution_config.is_generate_usage) and pipeline_run_id is not None:
                tracer_manager = GraphTracerManager.get_instance()
                if tracer_manager is not None:
                    tracer_manager.close_tracer(pipeline_run_id)

            # Clear event log state from the report delegate (direct execution path)
            if pipeline_run_id is not None:
                get_report_delegate().clear_event_log(context_key=pipeline_run_id)

            # Free the per-run registry entry so a later run can resubmit the same explicit
            # pipeline_run_id (serial resubmission is a supported scenario; only genuinely
            # concurrent same-id runs should collide in add_new_pipeline). Must come after
            # close_tracer: while the entry is registered, the collision raise shields the live
            # direct-mode tracer (keyed by the caller-suppliable pipeline_run_id) from
            # open_tracer's stale-key pop-and-replace healing. The pop is tolerant — when
            # pipeline_run_setup failed it already removed its own registration (and
            # pipeline_run_id is None here anyway).
            if pipeline_run_id is not None:
                get_pipeline_manager().remove_pipeline(pipeline_run_id=pipeline_run_id)

            # Only teardown library if it was successfully created
            if library_id_resolved is not None:
                # Restore the caller's outer current-library FIRST so the guarantee survives a teardown
                # raise, then tear the run library down — mirroring pipeline_run_setup's error-path
                # restore. set_current_library cannot take None, so route the "no outer was set" case
                # through clear_current_library. The `!= library_id_resolved` guard handles the collision
                # where the caller's outer current-library IS this run's library: "restoring" it would
                # leave the ContextVar pointing at the library we tear down next, so clear instead.
                if prev_library_id is not None and prev_library_id != library_id_resolved:
                    set_current_library(library_id=prev_library_id)
                else:
                    clear_current_library()
                get_library_manager().teardown(library_id=library_id_resolved)

        assert pipe_job is not None  # for type checker, success path requires a resolved job
        properties = {
            EventProperty.PIPELINE_RUN_ID: pipeline_run_id,
            EventProperty.PIPE_TYPE: pipe_job.pipe.pipe_type,
            EventProperty.PIPELINE_OUTCOME: Outcome.SUCCESS,
        }
        get_telemetry_manager().track_event(event_name=EventName.PIPELINE_COMPLETE, properties=properties)

        finished_at = datetime.now(timezone.utc).isoformat()
        return PipelexRunResultExecute.from_pipe_output(
            pipe_output=pipe_output,
            pipeline_run_id=pipe_output.pipeline_run_id,
            created_at=created_at,
            state=RunState.COMPLETED,
            finished_at=finished_at,
        )

    @override
    async def start(
        self,
        pipe_code: str | None = None,
        mthds_contents: list[str] | None = None,
        inputs: PipelineInputs | WorkingMemoryAbstract[Any] | None = None,
        output_name: str | None = None,
        output_multiplicity: VariableMultiplicity | None = None,
        dynamic_output_concept_ref: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> PipelexRunResultStart:
        """Start a method asynchronously — not implemented by the local runtime.

        Asynchronous execution is owned by the API layer (pipelex-api overrides
        this with Temporal dispatch) and the hosted platform; locally, use
        `execute`.
        """
        _ = (
            pipe_code,
            mthds_contents,
            inputs,
            output_name,
            output_multiplicity,
            dynamic_output_concept_ref,
            extra,
        )
        msg = "start is not implemented by the local runtime. Use execute, or run against an MTHDS API runner."
        raise NotImplementedError(msg)

    @override
    async def validate(
        self,
        mthds_contents: list[str],
        allow_signatures: bool = False,
    ) -> ValidationReport:
        """Parse, validate, and dry-run MTHDS bundles — protocol `validate`.

        Wraps `validate_bundle` and maps its result onto the protocol's
        `ValidationReport`: the parsed blueprint(s) and per-pipe structures are
        reported; `graph_spec` stays None (the dry run validates the graph
        without materializing a spec artifact). The runnability verdict is
        reported as `pending_signatures` (qualified refs of pipes still
        declared as `PipeSignature` in the assembled library) plus
        `is_runnable = not pending_signatures` — the same convention as the
        agent-CLI / builder validate envelopes. It only matters on the lenient
        `allow_signatures=True` path: in strict mode an unsatisfied signature
        makes `validate_bundle` raise instead.

        Args:
            mthds_contents: MTHDS contents to load (always a list, even for one file).
            allow_signatures: Tolerate unimplemented pipe signatures (strict by default).

        Returns:
            ValidationReport with the structural artifacts of a valid bundle.

        Raises:
            PipelexError: When the bundle is invalid (parse, static validation, or dry-run failure).
        """
        library_dirs = [Path(library_dir) for library_dir in self.library_dirs] if self.library_dirs else None
        # `validate_bundle` deliberately leaves its validation library OPEN and
        # current on success (the CLI surfaces consume it before process exit).
        # This protocol wrapper is a long-lived entry point, so restore the
        # caller's current-library and tear the validation library down on the
        # way out — on failure `validate_bundle` already did both, making the
        # cleanup below a no-op.
        prev_library_id = get_current_library_id_or_none()
        try:
            result = await validate_bundle(
                mthds_contents=mthds_contents,
                library_dirs=library_dirs,
                allow_signatures=allow_signatures,
            )
        finally:
            validation_library_id = get_current_library_id_or_none()
            if validation_library_id is not None and validation_library_id != prev_library_id:
                if prev_library_id is not None:
                    set_current_library(library_id=prev_library_id)
                else:
                    clear_current_library()
                get_library_manager().teardown(library_id=validation_library_id)
        blueprints_dump: list[dict[str, Any]] = [blueprint.model_dump(mode="json") for blueprint in result.blueprints]
        pipe_structures: dict[str, Any] = {pipe.code: pipe.model_dump(mode="json") for pipe in result.pipes}
        return PipelexValidationReport(
            blueprint=blueprints_dump[0] if len(blueprints_dump) == 1 else blueprints_dump,
            graph_spec=None,
            pipe_structures=pipe_structures,
            pending_signatures=result.pending_signatures,
            is_runnable=not result.pending_signatures,
        )

    @override
    async def models(self, category: MthdsModelCategory | None = None) -> MthdsModelDeck:
        """The model deck this runtime can route to — protocol `models`.

        Wraps the builder's `list_models` and shapes its per-category payload
        into the protocol `ModelDeck`.

        Args:
            category: Optional deck filter (`llm`, `extract`, `img_gen`, `search`).

        Returns:
            ModelDeck with presets, aliases, and routing waterfalls.
        """
        categories = [ModelCategory(category)] if category is not None else None
        deck_raw = list_models(categories=categories)
        models: list[MthdsModelInfo] = []
        aliases: dict[str, str] = {}
        waterfalls: dict[str, list[str]] = {}
        presets_by_category: dict[str, list[dict[str, Any]]] = deck_raw["presets"]
        aliases_by_category: dict[str, dict[str, str]] = deck_raw["aliases"]
        waterfalls_by_category: dict[str, dict[str, list[str]]] = deck_raw["waterfalls"]
        for category_key, category_presets in presets_by_category.items():
            for preset in category_presets:
                models.append(MthdsModelInfo(name=preset["name"], type=MthdsModelCategory(category_key)))
        for category_aliases in aliases_by_category.values():
            aliases.update(category_aliases)
        for category_waterfalls in waterfalls_by_category.values():
            waterfalls.update(category_waterfalls)
        return PipelexModelDeck(models=models, aliases=aliases, waterfalls=waterfalls)

    @override
    async def version(self) -> VersionInfo:
        """Protocol + runner versions — protocol `version`.

        Returns:
            VersionInfo with the installed pipelex version as the runner
            version, plus pipelex's identification extensions.
        """
        pipelex_version: str
        try:
            pipelex_version = metadata.version("pipelex")
        except metadata.PackageNotFoundError:
            # Source checkout on PYTHONPATH without an installed distribution —
            # the runtime still works, so version() must not fail.
            pipelex_version = "unknown"
        return PipelexVersionInfo(
            protocol_version=MTHDS_PROTOCOL_VERSION,
            runner_version=pipelex_version,
            implementation="pipelex",
            implementation_version=pipelex_version,
            runtime_version=pipelex_version,
        )
