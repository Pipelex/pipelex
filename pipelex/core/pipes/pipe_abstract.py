from abc import ABC, abstractmethod
from typing import Any, final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pipelex import log
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError, PipeValidationErrorType
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_blueprint import PipeCategory, PipeType
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.pipe_telemetry_context import PipeTelemetryContext
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.utils import monitor_pipe_stack
from pipelex.pipe_run.exceptions import PipeRunError
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

PipeAbstractType = type["PipeAbstract"]


class PipeAbstract(ABC, BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    pipe_category: Any  # Any so that subclasses can put a Literal
    type: Any  # Any so that subclasses can put a Literal
    code: str
    domain_code: str
    description: str | None = None
    inputs: InputStuffSpecs = Field(default_factory=InputStuffSpecs)
    output: StuffSpec

    @property
    def pipe_type(self) -> str:
        return self.__class__.__name__

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
        # First validate required variables are in the inputs
        for required_variable_name in self.required_variables():
            if required_variable_name not in self.inputs.variables:
                msg = f"Required variable '{required_variable_name}' is not in the inputs of pipe '{self.code}'. Current inputs: {self.inputs}"
                raise PipeValidationError(
                    message=msg,
                    error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE,
                    domain_code=self.domain_code,
                    pipe_code=self.code,
                    variable_names=[required_variable_name],
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
            if PipeCategory.is_controller_by_str(self.pipe_category):
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
            raise PipeRunError(
                message=msg,
                run_mode=pipe_run_params.run_mode,
                pipe_code=self.code,
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
        match pipe_run_params.run_mode:
            case PipeRunMode.LIVE:
                pass
            case PipeRunMode.DRY:
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
        monitor_pipe_stack(pipe_run_params=pipe_run_params)
        pipe_run_id = PipelineFactory.make_pipe_run_id()

        match pipe_run_params.run_mode:
            case PipeRunMode.LIVE:
                pipe_output = await self.live_run_pipe(
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    pipe_run_params=pipe_run_params,
                    output_name=output_name,
                    pipe_run_id=pipe_run_id,
                )
            case PipeRunMode.DRY:
                pipe_output = await self.dry_run_pipe(
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    pipe_run_params=pipe_run_params,
                    output_name=output_name,
                    pipe_run_id=pipe_run_id,
                )

        pipe_run_params.pop_pipe_from_stack(pipe_code=self.code)
        return pipe_output

    @final
    async def live_run_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        pipe_run_id: str,
        output_name: str | None = None,
    ) -> PipeOutput:
        log.info(self._format_pipe_run_info(pipe_run_params=pipe_run_params))

        with PipeTelemetryContext(
            pipe_code=self.code,
            pipe_type=self.pipe_type,
            pipe_category=self.pipe_category,
            description=self.description,
            parent_otel_context=job_metadata.otel_context if not pipe_run_params.run_mode.is_dry else None,
            pipeline_run_id=job_metadata.pipeline_run_id,
            working_memory=working_memory,
            needed_inputs=self.needed_inputs(),
        ) as span_ctx:
            # Create child metadata with updated 'pipe_code' and 'pipe_run_id'
            # This passes down a modified copy rather than mutating the original
            # otel_context is passed separately because it must always be set explicitly
            # (even when None in run_mode=DRY) to avoid inheriting stale parent context
            child_metadata = job_metadata.copy_with_update(
                updated_metadata=JobMetadata(
                    pipe_code=self.code,
                    pipe_run_id=pipe_run_id,
                ),
                otel_context=span_ctx.otel_context,
            )

            return await self._live_run_pipe(
                job_metadata=child_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name
            )

    @final
    async def dry_run_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        pipe_run_id: str,
        output_name: str | None = None,
    ) -> PipeOutput:
        log.verbose(f"Dry run of {self.type}: '{self.code}', pipe_run_id={pipe_run_id}")

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
