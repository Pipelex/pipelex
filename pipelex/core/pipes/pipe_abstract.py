import traceback
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, final

from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, Span, SpanContext, SpanKind, Status, StatusCode, TraceFlags
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pipelex import log
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError, PipeValidationErrorType
from pipelex.core.pipes.inputs.exceptions import PipeRunInputsError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_blueprint import PipeCategory, PipeType
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.validation import is_variable_satisfied_by_inputs
from pipelex.graph.graph_tracer_manager import GraphTracerManager, IOSpec, NodeKind
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata, OtelContext
from pipelex.pipeline.pipeline_factory import PipelineFactory
from pipelex.system.telemetry.otel_constants import (
    LangfuseSpanAttr,
    OTelConstants,
    PipelexSpanAttr,
    SpanCategory,
    SpanOutcome,
)
from pipelex.system.telemetry.otel_factory import OtelFactory
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.misc.package_utils import get_package_version
from pipelex.tools.misc.string_utils import is_snake_case
from pipelex.types import Self

if TYPE_CHECKING:
    from pipelex.graph.graph_context import GraphContext

PipeAbstractType = type["PipeAbstract"]


class PipeAbstract(ABC, BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    pipe_category: Any  # Any so that subclasses can put a Literal
    type: Any  # Any so that subclasses can put a Literal
    code: str
    domain_code: str
    description: str
    inputs: InputStuffSpecs = Field(default_factory=InputStuffSpecs)
    output: StuffSpec

    @property
    def pipe_type(self) -> str:
        return self.__class__.__name__

    @property
    def is_controller(self) -> bool:
        return PipeCategory.is_controller_by_str(self.pipe_category)

    @property
    def concept_dependencies(self) -> list[Concept]:
        """Return all unique concept dependencies (output + inputs) without duplicates."""
        seen_concept_refs: set[str] = set()
        unique_concepts: list[Concept] = []

        # Add output concept first
        unique_concepts.append(self.output.concept)
        seen_concept_refs.add(self.output.concept.concept_ref)

        # Add input concepts (avoiding duplicates)
        for concept in self.inputs.concepts:
            if concept.concept_ref not in seen_concept_refs:
                unique_concepts.append(concept)
                seen_concept_refs.add(concept.concept_ref)

        return unique_concepts

    @field_validator("code", mode="before")
    @classmethod
    def validate_pipe_code_syntax(cls, code: str) -> str:
        if not is_snake_case(code):
            msg = f"Invalid pipe code syntax '{code}'. Must be in snake_case."
            raise ValueError(msg)
        return code

    @field_validator("type", mode="after")
    @classmethod
    def validate_pipe_type(cls, value: Any) -> Any:
        if value not in PipeType.value_list():
            msg = f"Invalid pipe type '{value}' for pipe '{cls.code}'. Must be one of: {PipeType.value_list()}"
            raise ValueError(msg)
        return value

    @field_validator("pipe_category", mode="after")
    @classmethod
    def validate_pipe_category(cls, value: Any) -> Any:
        if value not in PipeCategory.value_list():
            msg = f"Invalid pipe category '{value}' for pipe '{cls.code}'. Must be one of: {PipeCategory.value_list()}"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def validate_pipe_category_based_on_type(self) -> Self:
        try:
            pipe_type = PipeType(self.type)
        except ValueError as exc:
            # If type is invalid, it should have been caught by the field validator
            # but we handle it gracefully here
            msg = f"Invalid pipe type '{self.type}' for pipe '{self.code}'. Must be one of: {PipeType.value_list()}"
            raise ValueError(msg) from exc

        if self.pipe_category != pipe_type.category:
            msg = (
                f"Inconsistency detected in pipe '{self.code}': pipe_category '{self.pipe_category}' "
                f"does not match the expected category '{pipe_type.category}' for type '{self.type}'"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def validate_pipe(self) -> Self:
        self.generic_validate_inputs_static()
        self.generic_validate_output_static()
        return self

    @final
    def validate_with_libraries(self):
        self.generic_validate_inputs_with_library()
        self.generic_validate_output_with_library()

    @final
    def generic_validate_inputs_static(self):
        self.validate_inputs_static()

    @final
    def generic_validate_output_static(self):
        self.validate_output_static()

    @final
    def generic_validate_inputs_with_library(self):
        # First validate required variables are in the inputs (using prefix-based matching)
        input_names = set(self.inputs.variables)
        for required_variable_path in self.required_variables():
            if not is_variable_satisfied_by_inputs(required_variable_path, input_names):
                msg = f"Required variable '{required_variable_path}' is not in the inputs of pipe '{self.code}'. Current inputs: {self.inputs}"
                raise PipeValidationError(
                    message=msg,
                    error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE,
                    domain_code=self.domain_code,
                    pipe_code=self.code,
                    variable_names=[required_variable_path],
                )

        # Then validate that all inputs are actually needed and match requirements exactly
        the_needed_inputs = self.needed_inputs()

        # Check all required variables are in the inputs and match the required StuffSpec
        for named_stuff_spec in the_needed_inputs.named_stuff_specs:
            var_name = named_stuff_spec.variable_name

            if var_name not in self.inputs.variables:
                msg = f"Required variable '{var_name}' is not in the inputs of pipe '{self.code}'. Current inputs: {self.inputs}"
                raise PipeValidationError(
                    message=msg,
                    error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE,
                    domain_code=self.domain_code,
                    pipe_code=self.code,
                    variable_names=[var_name],
                )

            # TODO: add this to the PipeController validation. (This might need to refactor a little bit how we can override the validation)
            if self.is_controller:
                # Compare the essential parts of StuffSpec (concept code + multiplicity)
                # Skip validation if the needed stuff_spec is Dynamic or Anything (flexible output types)
                declared_stuff_spec = self.inputs.root[var_name]
                needed_stuff_spec = the_needed_inputs.root[named_stuff_spec.requirement_expression or var_name]

                # Allow mismatch if the needed stuff_spec is a flexible type (Dynamic or Anything)
                if (
                    needed_stuff_spec.concept.code not in {NativeConceptCode.DYNAMIC, NativeConceptCode.ANYTHING}
                    and declared_stuff_spec != needed_stuff_spec
                ):
                    # Identify the specific mismatched field(s)
                    mismatch_details: list[str] = []
                    if declared_stuff_spec.concept != needed_stuff_spec.concept:
                        mismatch_details.append(f"concept: declared='{declared_stuff_spec.concept}' vs required='{needed_stuff_spec.concept}'")
                    if declared_stuff_spec.multiplicity != needed_stuff_spec.multiplicity:
                        mismatch_details.append(
                            f"multiplicity: declared='{declared_stuff_spec.multiplicity}' vs required='{needed_stuff_spec.multiplicity}'"
                        )

                    mismatch_summary = ", ".join(mismatch_details)
                    msg = (
                        f"In the pipe '{self.code}', the input variable '{var_name}' has a stuff spec mismatch.\n"
                        f"Mismatched field(s): {mismatch_summary}\n"
                        f"Declared: {declared_stuff_spec}\n"
                        f"Required: {needed_stuff_spec}"
                    )
                    raise PipeValidationError(
                        message=msg,
                        error_type=PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH,
                        domain_code=self.domain_code,
                        pipe_code=self.code,
                        variable_names=[var_name],
                    )

        # Check that all declared inputs are actually needed
        for input_name in self.inputs.variables:
            if input_name not in the_needed_inputs.required_names:
                msg = f"Extraneous input '{input_name}' found in the inputs of pipe {self.code}"
                raise PipeValidationError(
                    message=msg,
                    error_type=PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
                    domain_code=self.domain_code,
                    pipe_code=self.code,
                    variable_names=[input_name],
                )

        self.validate_inputs_with_library()

    @final
    def generic_validate_output_with_library(self):
        self.validate_output_with_library()

    @abstractmethod
    def validate_inputs_with_library(self):
        pass

    @abstractmethod
    def validate_inputs_static(self):
        pass

    @abstractmethod
    def validate_output_with_library(self):
        pass

    @abstractmethod
    def validate_output_static(self):
        pass

    @final
    async def validate_before_run(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ):
        # Check that all the needed inputs are actually in the working memory
        missing_input_names: list[str] = []

        for named_stuff_spec in self.needed_inputs().named_stuff_specs:
            if not working_memory.get_optional_stuff(named_stuff_spec.variable_name):
                missing_input_names.append(named_stuff_spec.variable_name)

        if missing_input_names:
            msg = f"Dry run of {self.type} '{self.code}': missing required inputs: {', '.join(missing_input_names)}"
            raise PipeRunInputsError(
                message=msg,
                run_mode=pipe_run_params.run_mode,
                pipe_code=self.code,
                missing_inputs=missing_input_names,
            )

        # Specific pipe validation function
        await self._validate_before_run(
            job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name
        )

    @abstractmethod
    async def _validate_before_run(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ):
        pass

    @final
    async def validate_after_run(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ):
        await self._validate_after_run(
            job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name
        )

    @abstractmethod
    async def _validate_after_run(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ):
        pass

    @abstractmethod
    def required_variables(self) -> set[str]:
        """Return the variables that are required for the pipe to run.
        The required variables are only the list:
        # 1 - The inputs of dependency pipes
        # 2 - The variables in the pipe definition
            - PipeConditon : Variables in the expression
            - PipeBatch: Variables in the batch_params
            - PipeLLM : Variables in the prompt
        """

    @abstractmethod
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        """Return the stuff specs that are needed for the pipe to run.

        Args:
            visited_pipes: Set of pipe codes currently being processed to prevent infinite recursion.
                          If None, starts recursion detection with an empty set.

        Returns:
            InputStuffSpecs containing all needed inputs for this pipe

        """

    def _format_pipe_run_info(self, pipe_run_params: PipeRunParams) -> str:
        indent_level = len(pipe_run_params.pipe_stack) - 1
        indent = "   " * indent_level
        if indent_level > 0:
            indent = f"{indent}[yellow]↳[/yellow] "
        pipe_type_label = f"[white]{self.pipe_type}:[/white]"
        if pipe_run_params.run_mode.is_dry:
            pipe_type_label = f"[dim]Dry run:[/dim] {pipe_type_label}"
        pipe_code_label = f"[red]{self.code}[/red]"
        concept_code_label = f"[bold green]{self.output.concept.code}[/bold green]"
        arrow = "[yellow]→[/yellow]"
        return f"{indent}{pipe_type_label} {pipe_code_label} {arrow} {concept_code_label}"

    @final
    async def run_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        pipe_run_params.push_pipe_to_stack(pipe_code=self.code)

        # Handle graph tracing if enabled
        graph_node_id: str | None = None
        child_graph_context: GraphContext | None = None
        tracer_manager = None

        parent_graph_context = job_metadata.graph_context
        if parent_graph_context is not None:
            tracer_manager = GraphTracerManager.get_instance()
            if tracer_manager is not None:
                started_at = datetime.now(timezone.utc)
                node_kind = NodeKind.CONTROLLER if self.is_controller else NodeKind.OPERATOR

                # Capture input specs from working memory for data flow tracking
                input_specs: list[IOSpec] = []
                for var_name in self.needed_inputs().required_names:
                    stuff = working_memory.get_optional_stuff(var_name)
                    if stuff is not None:
                        input_spec = IOSpec(
                            name=var_name,
                            concept=stuff.concept.code,
                            content_type=stuff.content.content_type,
                            digest=stuff.stuff_code,
                            data=stuff.content.smart_dump() if parent_graph_context.data_inclusion.stuff_json_content else None,
                            data_text=stuff.content.rendered_pretty_text() if parent_graph_context.data_inclusion.stuff_text_content else None,
                            data_html=stuff.content.rendered_pretty_html() if parent_graph_context.data_inclusion.stuff_html_content else None,
                        )
                        input_specs.append(input_spec)

                graph_node_id, child_graph_context = tracer_manager.on_pipe_start(
                    graph_context=parent_graph_context,
                    pipe_code=self.code,
                    pipe_type=self.type,
                    node_kind=node_kind,
                    started_at=started_at,
                    input_specs=input_specs or None,
                )
                # Update job metadata with child graph context for nested pipes
                if child_graph_context is not None:
                    job_metadata = job_metadata.copy_with_update(
                        otel_context=job_metadata.otel_context,
                        graph_context=child_graph_context,
                    )

        try:
            match pipe_run_params.run_mode:
                case PipeRunMode.LIVE:
                    pipe_output = await self.live_run_pipe(
                        job_metadata=job_metadata,
                        working_memory=working_memory,
                        pipe_run_params=pipe_run_params,
                        output_name=output_name,
                    )
                case PipeRunMode.DRY:
                    pipe_output = await self.dry_run_pipe(
                        job_metadata=job_metadata,
                        working_memory=working_memory,
                        pipe_run_params=pipe_run_params,
                        output_name=output_name,
                    )
        except Exception as exc:
            # Record graph tracing error
            if tracer_manager is not None and parent_graph_context is not None:
                error_stack: str | None = None
                if parent_graph_context.data_inclusion.error_stack_traces:
                    error_stack = traceback.format_exc()
                tracer_manager.on_pipe_end_error(
                    graph_id=parent_graph_context.graph_id,
                    node_id=graph_node_id,
                    ended_at=datetime.now(timezone.utc),
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    error_stack=error_stack,
                )
            raise

        # Record graph tracing success
        if tracer_manager is not None and parent_graph_context is not None:
            # Capture output spec for data flow tracking
            # Note: main_stuff may not exist for pipes like PipeParallel with add_each_output=true
            main_stuff = pipe_output.working_memory.get_optional_main_stuff()
            output_spec: IOSpec | None = None
            if main_stuff is not None:
                output_spec = IOSpec(
                    name=output_name or main_stuff.stuff_name or "main_stuff",
                    concept=main_stuff.concept.code,
                    content_type=main_stuff.content.content_type,
                    digest=main_stuff.stuff_code,
                    data=main_stuff.content.smart_dump() if parent_graph_context.data_inclusion.stuff_json_content else None,
                    data_text=main_stuff.content.rendered_pretty_text() if parent_graph_context.data_inclusion.stuff_text_content else None,
                    data_html=main_stuff.content.rendered_pretty_html() if parent_graph_context.data_inclusion.stuff_html_content else None,
                )

            tracer_manager.on_pipe_end_success(
                graph_id=parent_graph_context.graph_id,
                node_id=graph_node_id,
                ended_at=datetime.now(timezone.utc),
                output_spec=output_spec,
            )

        pipe_run_params.pop_pipe_from_stack(pipe_code=self.code)
        return pipe_output

    @final
    async def live_run_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        log.info(self._format_pipe_run_info(pipe_run_params=pipe_run_params))

        # Handle telemetry ------------------------------------------------------------

        # Generate pipe_run_id (business ID, always set)
        this_pipe_run_id = PipelineFactory.make_pipe_run_id()

        # Derive OtelContext if telemetry is enabled (not dry mode and tracer available)
        # The trace_id comes from parent's otel_context (already computed at pipeline start)
        this_otel_context: OtelContext | None = None
        span: Span | None = None
        is_root_span: bool = False

        parent_otel_context = job_metadata.otel_context
        if not pipe_run_params.run_mode.is_dry and parent_otel_context is not None:
            # Start OTel span first
            span, is_root_span = self._start_pipe_span(
                parent_otel_context=parent_otel_context,
                pipeline_run_id=job_metadata.pipeline_run_id,
                working_memory=working_memory,
            )
            # Get the actual span_id from OTel (OTel generates its own span_id)
            if span:
                span_context = span.get_span_context()
                this_otel_context = OtelContext(
                    trace_id=parent_otel_context.trace_id,
                    trace_name=parent_otel_context.trace_name,
                    trace_name_redacted=parent_otel_context.trace_name_redacted,
                    span_id=span_context.span_id,
                )

        # Create child metadata with updated pipe_code and pipe_run_id
        # This passes down a modified copy rather than mutating the original
        # otel_context is passed separately because it must always be set explicitly
        # (even when None in dry mode) to avoid inheriting stale parent context
        child_metadata = job_metadata.copy_with_update(
            otel_context=this_otel_context,
            pipe_code=self.code,
            pipe_run_id=this_pipe_run_id,
        )

        # Run pipe ------------------------------------------------------------

        try:
            pipe_output = await self._live_run_pipe(
                job_metadata=child_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name
            )
        except Exception as exc:
            self._end_pipe_span_error(span, error=exc, is_root_span=is_root_span)
            raise

        # Handle telemetry ------------------------------------------------------------

        self._end_pipe_span_success(span=span, pipe_output=pipe_output, is_root_span=is_root_span)

        return pipe_output

    @final
    async def dry_run_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        log.verbose(f"Dry run of {self.type}: '{self.code}'")
        assert pipe_run_params.run_mode.is_dry, f"Dry run of {self.type} '{self.code}' called with run_mode = {pipe_run_params.run_mode}"
        await self.validate_before_run(
            job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name
        )
        pipe_output = await self._dry_run_pipe(
            job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name
        )
        await self.validate_after_run(
            job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name
        )
        return pipe_output

    @abstractmethod
    async def _live_run_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        pass

    @abstractmethod
    async def _dry_run_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        pass

    def _start_pipe_span(
        self,
        parent_otel_context: OtelContext,
        pipeline_run_id: str,
        working_memory: WorkingMemory,
    ) -> tuple[Span | None, bool]:
        """Start an OTel span for this pipe execution.

        Always includes full (non-redacted) pipe codes and content in span attributes.
        Redaction is handled by individual exporters based on their TelemetryRedactionConfig.

        Args:
            parent_otel_context: The parent's OTel context.
            pipeline_run_id: The pipeline run ID for span attributes.
            working_memory: The working memory containing input stuffs for telemetry capture.

        Returns:
            A tuple of (span, is_root_span) where span is the started span or None if tracer
            is unavailable, and is_root_span indicates if this is the trace root span.
        """
        tracer = TelemetryManagerAbstract.get_instance_tracer()
        if tracer is None:
            log.verbose(f"[OTel] No tracer available for pipe '{self.code}'")
            return None, False

        # Always use full pipe code - redaction is handled by exporters
        span_name = f"{self.pipe_type}: {self.code}"

        # For root spans: parent_otel_context.span_id is OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID (1)
        # This ensures OTel uses our trace_id (INVALID_SPAN_ID=0 makes context invalid).
        # The exporter filters out this virtual parent when setting $ai_parent_id.
        # For child spans: parent_otel_context.span_id is the actual parent's span_id
        parent_span_id = parent_otel_context.span_id
        is_root_span = parent_span_id == OTelConstants.OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID

        # Build all span attributes upfront with FULL (non-redacted) values
        # PostHog exporters will apply redaction based on their TelemetryRedactionConfig
        # Langfuse gets full data - users who configure Langfuse control their own data exposure
        span_attributes: dict[str, str] = {
            # Pipelex-specific attributes (always full values, exporters redact as needed)
            PipelexSpanAttr.TRACE_NAME: parent_otel_context.trace_name,
            PipelexSpanAttr.TRACE_NAME_REDACTED: parent_otel_context.trace_name_redacted,
            PipelexSpanAttr.SPAN_CATEGORY: SpanCategory.PIPE,
            PipelexSpanAttr.PIPELINE_RUN_ID: pipeline_run_id,
            PipelexSpanAttr.PIPE_CATEGORY: self.pipe_category,
            PipelexSpanAttr.PIPE_TYPE: self.pipe_type,
            PipelexSpanAttr.PIPE_CODE: self.code,  # Full pipe code, exporter handles redaction
        }

        # Langfuse-specific attributes: always send full data
        if TelemetryManagerAbstract.get_langfuse_enabled():
            span_attributes.update(
                {
                    LangfuseSpanAttr.TRACE_NAME: parent_otel_context.trace_name,
                    LangfuseSpanAttr.RELEASE: get_package_version(),
                    LangfuseSpanAttr.OBSERVATION_TYPE: SpanCategory.PIPE,
                    LangfuseSpanAttr.OBSERVATION_PIPE_CATEGORY: self.pipe_category,
                    LangfuseSpanAttr.OBSERVATION_PIPE_TYPE: self.pipe_type,
                    LangfuseSpanAttr.OBSERVATION_PIPE_CODE: self.code,
                    LangfuseSpanAttr.OBSERVATION_PIPELINE_RUN_ID: pipeline_run_id,
                }
            )
            if self.description:
                span_attributes[LangfuseSpanAttr.OBSERVATION_DESCRIPTION] = self.description

            # Capture full input content for Langfuse
            needed_input_names = set(self.needed_inputs().required_names)
            inputs_json = OtelFactory.make_inputs_json(
                working_memory=working_memory,
                needed_input_names=needed_input_names,
                max_length=None,  # No truncation for Langfuse
            )
            span_attributes[LangfuseSpanAttr.OBSERVATION_INPUT] = inputs_json

            # For root span, also set trace-level input and metadata
            if is_root_span:
                span_attributes[LangfuseSpanAttr.TRACE_INPUT] = inputs_json
                # Set trace-level metadata (filterable in Langfuse UI)
                span_attributes[LangfuseSpanAttr.TRACE_PIPE_CODE] = self.code
                span_attributes[LangfuseSpanAttr.TRACE_PIPE_TYPE] = self.pipe_type
                span_attributes[LangfuseSpanAttr.TRACE_PIPE_CATEGORY] = self.pipe_category
                span_attributes[LangfuseSpanAttr.TRACE_PIPELINE_RUN_ID] = pipeline_run_id
                if self.description:
                    span_attributes[LangfuseSpanAttr.TRACE_DESCRIPTION] = self.description

        parent_span_context = SpanContext(
            trace_id=parent_otel_context.trace_id,
            span_id=parent_span_id,
            is_remote=True,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        )
        parent_ctx = trace.set_span_in_context(NonRecordingSpan(parent_span_context))

        # Start span with attributes - OTel generates the span_id, we capture it after
        span = tracer.start_span(
            name=span_name,
            kind=SpanKind.INTERNAL,
            context=parent_ctx,
            attributes=span_attributes,
        )

        # Debug logging
        span_ctx = span.get_span_context()
        log.verbose(
            f"[OTel] PIPE SPAN STARTED:\n"
            f"  pipe_code='{self.code}'\n"
            f"  pipeline_run_id='{pipeline_run_id}'\n"
            f"  trace_id={span_ctx.trace_id:032x}\n"
            f"  span_id={span_ctx.span_id:016x}\n"
            f"  parent_span_id={parent_span_id:016x}\n"
            f"  is_root_span={is_root_span}"
        )

        return span, is_root_span

    def _end_pipe_span_success(self, span: Span | None, pipe_output: PipeOutput, is_root_span: bool) -> None:
        """End the pipe's OTel span with success status. Safe to call if span is None.

        Args:
            span: The OTel span to end, or None if telemetry is disabled.
            pipe_output: The pipe output containing the result for telemetry capture.
            is_root_span: Whether this is the root span of the trace.
        """
        if span is None:
            return

        span_ctx = span.get_span_context()
        log.verbose(f"[OTel] PIPE SPAN ENDING:\n  pipe_code='{self.code}'\n  trace_id={span_ctx.trace_id:032x}\n  span_id={span_ctx.span_id:016x}")

        # Always capture full output content for Langfuse
        if TelemetryManagerAbstract.get_langfuse_enabled():
            output_json = OtelFactory.make_output_json(
                pipe_output=pipe_output,
                max_length=None,  # No truncation for Langfuse
            )
            span.set_attribute(LangfuseSpanAttr.OBSERVATION_OUTPUT, output_json)

            # For root span, also set trace-level output
            if is_root_span:
                span.set_attribute(LangfuseSpanAttr.TRACE_OUTPUT, output_json)

        span.set_attribute(PipelexSpanAttr.OUTCOME, SpanOutcome.SUCCESS)
        span.set_status(Status(StatusCode.OK))
        if TelemetryManagerAbstract.get_langfuse_enabled():
            span.set_attribute(LangfuseSpanAttr.OBSERVATION_OUTCOME, SpanOutcome.SUCCESS)
            if is_root_span:
                span.set_attribute(LangfuseSpanAttr.TRACE_OUTCOME, SpanOutcome.SUCCESS)
        span.end()

    def _end_pipe_span_error(self, span: Span | None, error: Exception, is_root_span: bool = False) -> None:
        """End the pipe's OTel span with error status. Safe to call if span is None.

        Args:
            span: The OTel span to end, or None if telemetry is disabled.
            error: The exception that caused the error.
            is_root_span: Whether this is the root span of the trace.
        """
        if span is None:
            return

        span_ctx = span.get_span_context()
        log.verbose(
            f"[OTel] PIPE SPAN ENDING WITH ERROR:\n  pipe_code='{self.code}'\n  trace_id={span_ctx.trace_id:032x}\n  span_id={span_ctx.span_id:016x}"
        )

        span.set_attribute(PipelexSpanAttr.OUTCOME, SpanOutcome.FAILURE)
        span.record_exception(error)
        span.set_status(Status(StatusCode.ERROR, str(error)))
        if TelemetryManagerAbstract.get_langfuse_enabled():
            span.set_attribute(LangfuseSpanAttr.OBSERVATION_OUTCOME, SpanOutcome.FAILURE)
            if is_root_span:
                span.set_attribute(LangfuseSpanAttr.TRACE_OUTCOME, SpanOutcome.FAILURE)
        span.end()
