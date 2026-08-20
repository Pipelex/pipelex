import traceback
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, NamedTuple, Self, final

import shortuuid
from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, Span, SpanContext, SpanKind, Status, StatusCode, TraceFlags
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pipelex import log
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME, WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.pipes.inputs.exceptions import OptionalValueAbsentError, PipeRunInputsError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs, NamedStuffSpec
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import PresenceMarker
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.graph.graph_tracer_manager import GraphTracerManager, IOSpec, NodeKind
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_machinery.pipe_blueprint import PipeCategory, PipeType, valid_pipe_type_tags
from pipelex.pipe_machinery.validation import is_variable_satisfied_by_inputs
from pipelex.pipe_run.pipe_run_params import PipeRunParams, output_multiplicity_to_apply
from pipelex.pipe_signature.exceptions import PipeSignatureNotExecutableError
from pipelex.pipeline.pipeline_factory import PipelineFactory
from pipelex.system.job_metadata import JobMetadata, OtelContext
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.registries.class_registry_access import get_class_registry
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
from pipelex.validation_error_types import PipeValidationErrorType

if TYPE_CHECKING:
    from pipelex.system.trace_context import TraceContext

PipeAbstractType = type["PipeAbstract"]


class AbsentInput(NamedTuple):
    """One needed input that is absent from working memory, with its ledger record when one exists."""

    named_stuff_spec: NamedStuffSpec
    absence_record: AbsenceRecord


class CompanionSlot(NamedTuple):
    """One extra slot a pipe would have written into working memory besides its main output
    (e.g. an `add_each_output` parallel's branch result slots). When the pipe is lifted, each
    companion slot must be resolved too — a recorded absence for a singular slot, an empty
    list for a plural one (D4) — or downstream consumers would hit a hard neither-value-nor-record miss.
    """

    slot_name: str
    concept: Concept
    is_plural: bool
    producing_pipe_code: str


class InputPresenceScan(NamedTuple):
    """The runtime trichotomy (D3) applied to a pipe's needed inputs against working memory.

    - ``missing_names``: absent with NO absence record and not optional — never produced, a hard error.
    - ``forced_absent``: `!` inputs fed a recorded absence — typed failure with provenance.
    - ``liftable``: plain inputs fed a recorded absence — the pipe is lifted (skipped).

    Absent optional (`?`) inputs appear nowhere: the pipe runs and handles absence itself.
    """

    missing_names: list[str]
    forced_absent: list[AbsentInput]
    liftable: list[AbsentInput]


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
    def pipe_ref(self) -> str:
        """Domain-qualified pipe reference, e.g. 'scoring.compute_score'."""
        return f"{self.domain_code}.{self.code}"

    @property
    def pipe_type(self) -> str:
        return self.__class__.__name__

    @property
    def is_controller(self) -> bool:
        return PipeCategory.is_controller_by_str(self.pipe_category)

    @property
    def is_signature(self) -> bool:
        # Identity by class, not by enum field: the base is never a signature; `PipeSignature`
        # overrides this to True. (`pipe_category` no longer encodes signature-ness.)
        return False

    def pipe_dependencies(self) -> set[str]:
        """Return the set of pipe codes that this pipe depends on.

        Operators and signatures have no sub-pipe dependencies by default. Controllers
        override this to return the codes of pipes they orchestrate.
        """
        return set()

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

    def _register_execution_data(self, *, job_metadata: JobMetadata, execution_data: dict[str, Any]) -> None:
        """Register execution metadata with the graph tracer.

        Called by pipe subclasses during execution to capture runtime-resolved data
        (rendered prompts, resolved models, etc.) for the GraphSpec.
        """
        trace_context = job_metadata.trace_context
        if trace_context is None:
            return
        tracer_manager = GraphTracerManager.get_instance()
        if tracer_manager is None or trace_context.parent_node_id is None:
            return
        tracer_manager.register_execution_data(
            lookup_key=trace_context.lookup_key,
            node_id=trace_context.parent_node_id,
            execution_data=execution_data,
        )

    def _make_pipe_data_for_registry(self, *, library_crate: LibraryCrate | None) -> dict[str, Any]:
        """Serialize this pipe for the graph registry, including declaration source when known."""
        pipe_data = self.model_dump(mode="json", serialize_as_any=True)
        if library_crate is not None:
            source = library_crate.source_map.get(self.pipe_ref)
            if source:
                pipe_data["source"] = source
        return pipe_data

    def _make_single_concept_data_for_registry(self, concept: Concept, *, library_crate: LibraryCrate | None) -> dict[str, Any]:
        """Serialize a single concept for the graph registry, including its JSON Schema."""
        concept_dict = concept.model_dump(mode="json", serialize_as_any=True)
        if library_crate is not None:
            source = library_crate.source_map.get(concept.concept_ref)
            if source:
                concept_dict["source"] = source
        # Reads the active class registry directly rather than asking a concept provider. Importing
        # either hub here is a pyright `reportImportCycles` failure via runtime_hub ->
        # orchestrator_registry -> pipe_job -> here; those edges are TYPE_CHECKING-only, so there is no
        # runtime cycle, but pyright counts them and reports at `interpreter_hub.py`, out of reach of a
        # line-level ignore. Deferring the import does not help either. `class_registry_access` sits
        # below both hubs for exactly this. The lenient `get_class` (no StuffContent bound) is
        # deliberate: the schema is optional decoration on a graph-registry entry, so an unresolvable
        # class yields `None` rather than failing the run.
        structure_class = get_class_registry().get_class(name=concept.structure_class_name)
        try:
            concept_dict["json_schema"] = structure_class.model_json_schema() if structure_class is not None else None
        except (TypeError, ValueError):
            concept_dict["json_schema"] = None
        return concept_dict

    def _make_concept_data_for_registry(self, *, library_crate: LibraryCrate | None) -> list[dict[str, Any]]:
        """Serialize all unique concepts from this pipe for the graph registry."""
        return [self._make_single_concept_data_for_registry(concept, library_crate=library_crate) for concept in self.concept_dependencies]

    @field_validator("code", mode="before")
    @classmethod
    def validate_pipe_code_syntax(cls, code: str) -> str:
        # Strip namespace prefix if present (e.g., "domain.my_pipe" → "my_pipe").
        # The builder LLM sometimes generates dotted pipe codes; the namespace
        # comes from the bundle's domain field, not from the pipe code itself.
        if "." in code:
            bare_code = code.rsplit(".", maxsplit=1)[1]
            log.warning(f"Runtime pipe code '{code}' contains a namespace prefix, stripped to '{bare_code}'")
            code = bare_code
        if not is_snake_case(code):
            msg = f"Invalid pipe code syntax '{code}'. Must be in snake_case."
            raise ValueError(msg)
        return code

    @field_validator("type", mode="after")
    @classmethod
    def validate_pipe_type(cls, value: Any) -> Any:
        allowed = valid_pipe_type_tags()
        if value not in allowed:
            msg = f"Invalid pipe type '{value}'. Must be one of: {allowed}"
            raise ValueError(msg)
        return value

    @field_validator("pipe_category", mode="after")
    @classmethod
    def validate_pipe_category(cls, value: Any) -> Any:
        # A signature carries `pipe_category = None` (no executable category); every executable pipe
        # pins a `Literal["PipeOperator"|"PipeController"]`, so `None` unambiguously means "signature".
        if value is not None and value not in PipeCategory.value_list():
            msg = f"Invalid pipe category '{value}'. Must be one of: {PipeCategory.value_list()}"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def validate_pipe_category_based_on_type(self) -> Self:
        if self.is_signature:
            # Signatures sit outside the executable taxonomy: `type` is the signature tag (not a
            # `PipeType`) and `pipe_category` is None, so the type↔category consistency check below
            # (which coerces `PipeType(self.type)`) does not apply.
            return self
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

    def _expected_inputs_for_fix(self, needed_inputs: InputStuffSpecs) -> dict[str, str] | None:
        """Render the full needed-inputs mapping a fix would write, or ``None`` for operators.

        Controller-gated: only a controller's ``needed_inputs()`` is a trustworthy ground truth
        for its declared ``inputs`` table (operators re-emit their own declaration). The
        author's declared representation is preserved (keeping their presence marker — presence
        is deliberately not part of the drift contract) whenever the validator would accept it:
        either its concept + multiplicity already match the needed spec, or the needed spec is a
        flexible type (``Dynamic``/``Anything``), which the validator accepts against any concrete
        declaration. This mirrors the flexible-type carve-out in ``generic_validate_inputs_with_library``
        so a co-occurring drift on another input never rewrites a valid concrete declaration back
        to ``Dynamic``/``Anything``. Refs are derived from the needed spec only for variables being
        added or whose concept/multiplicity genuinely changes against a non-flexible need.
        """
        if not self.is_controller:
            return None
        expected_inputs: dict[str, str] = {}
        for named_stuff_spec in needed_inputs.named_stuff_specs:
            var_name = named_stuff_spec.variable_name
            declared_stuff_spec = self.inputs.root.get(var_name)
            if declared_stuff_spec is not None and (
                named_stuff_spec.concept.code in {NativeConceptCode.DYNAMIC, NativeConceptCode.ANYTHING}
                or (declared_stuff_spec.concept == named_stuff_spec.concept and declared_stuff_spec.multiplicity == named_stuff_spec.multiplicity)
            ):
                spec_to_render: StuffSpec = declared_stuff_spec
            else:
                spec_to_render = named_stuff_spec
            expected_inputs[var_name] = spec_to_render.to_bundle_representation(relative_to_domain=self.domain_code)
        return expected_inputs

    def _declared_inputs_for_fix(self) -> dict[str, str] | None:
        """Render the currently declared inputs the same way, or ``None`` for operators.

        Carried alongside ``expected_inputs`` so the fix planner (pure, no file access) can
        emit a minimal diff against the declaration instead of a table rewrite.
        """
        if not self.is_controller:
            return None
        return {
            var_name: declared_stuff_spec.to_bundle_representation(relative_to_domain=self.domain_code)
            for var_name, declared_stuff_spec in self.inputs.root.items()
        }

    @final
    def generic_validate_inputs_with_library(self):
        # First validate required variables are in the inputs (using prefix-based matching)
        input_names = set(self.inputs.variables)
        for required_variable_path in self.required_variables():
            if not is_variable_satisfied_by_inputs(required_variable_path, input_names=input_names):
                msg = (
                    f"Required variable '{required_variable_path}' is not in the inputs of pipe '{self.code}'. "
                    f"Current inputs: {self.inputs.format_for_display()}"
                )
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
                msg = f"Required variable '{var_name}' is not in the inputs of pipe '{self.code}'. Current inputs: {self.inputs.format_for_display()}"
                raise PipeValidationError(
                    message=msg,
                    error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE,
                    domain_code=self.domain_code,
                    pipe_code=self.code,
                    variable_names=[var_name],
                    expected_inputs=self._expected_inputs_for_fix(the_needed_inputs),
                    declared_inputs=self._declared_inputs_for_fix(),
                )

            # TODO: add this to the PipeController validation. (This might need to refactor a little bit how we can override the validation)
            if self.is_controller:
                # Compare the essential parts of StuffSpec (concept code + multiplicity)
                # Skip validation if the needed stuff_spec is Dynamic or Anything (flexible output types)
                declared_stuff_spec = self.inputs.root[var_name]
                needed_stuff_spec = the_needed_inputs.root[named_stuff_spec.requirement_expression or var_name]

                # Allow mismatch if the needed stuff_spec is a flexible type (Dynamic or Anything).
                # Presence markers are deliberately NOT compared: a controller's boundary marker may
                # legitimately differ from a child's need (e.g. a sequence declares `X?` while a step
                # needs `X` plain — that is exactly the lift-skip case, D3). Only concept and
                # multiplicity define the spec contract here.
                if needed_stuff_spec.concept.code not in {NativeConceptCode.DYNAMIC, NativeConceptCode.ANYTHING} and (
                    declared_stuff_spec.concept != needed_stuff_spec.concept or declared_stuff_spec.multiplicity != needed_stuff_spec.multiplicity
                ):
                    # Render both specs the way an author would write them in this pipe's domain
                    # (bare `Number` / `Text[]`, qualified only for foreign domains) — never the
                    # Python repr of the Concept/StuffSpec objects.
                    declared_ref = declared_stuff_spec.to_bundle_representation(relative_to_domain=self.domain_code)
                    required_ref = needed_stuff_spec.to_bundle_representation(relative_to_domain=self.domain_code)
                    msg = (
                        f"In pipe '{self.code}', input '{var_name}' is declared as '{declared_ref}' "
                        f"but its step needs '{required_ref}'. Update the input to '{required_ref}'."
                    )
                    raise PipeValidationError(
                        message=msg,
                        error_type=PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH,
                        domain_code=self.domain_code,
                        pipe_code=self.code,
                        variable_names=[var_name],
                        expected_inputs=self._expected_inputs_for_fix(the_needed_inputs),
                        declared_inputs=self._declared_inputs_for_fix(),
                    )

        # Check that all declared inputs are actually needed
        for input_name in self.inputs.variables:
            if input_name not in the_needed_inputs.declared_names:
                msg = f"Extraneous input '{input_name}' found in the inputs of pipe {self.code}"
                raise PipeValidationError(
                    message=msg,
                    error_type=PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
                    domain_code=self.domain_code,
                    pipe_code=self.code,
                    variable_names=[input_name],
                    expected_inputs=self._expected_inputs_for_fix(the_needed_inputs),
                    declared_inputs=self._declared_inputs_for_fix(),
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

    def _scan_input_presence(self, *, working_memory: WorkingMemory) -> InputPresenceScan:
        """Apply the runtime trichotomy (D3) to this pipe's needed inputs.

        The presence marker is read from this pipe's OWN input declaration when it exists —
        that is the boundary contract (D5: boundaries explicit). A controller's aggregated
        ``needed_inputs()`` carries the children's markers, and e.g. a sequence declaring
        ``X?`` over a step that needs ``X`` plain must run (its steps lift), not lift wholesale.
        """
        missing_names: list[str] = []
        forced_absent: list[AbsentInput] = []
        liftable: list[AbsentInput] = []
        for named_stuff_spec in self.needed_inputs().named_stuff_specs:
            if working_memory.get_optional_stuff(named_stuff_spec.variable_name):
                continue
            absence_record = working_memory.get_optional_absence(named_stuff_spec.variable_name)
            declared_stuff_spec = self.inputs.root.get(named_stuff_spec.variable_name)
            presence = declared_stuff_spec.presence if declared_stuff_spec else named_stuff_spec.presence
            match presence:
                case PresenceMarker.OPTIONAL:
                    continue
                case PresenceMarker.FORCE:
                    if absence_record:
                        forced_absent.append(AbsentInput(named_stuff_spec=named_stuff_spec, absence_record=absence_record))
                    else:
                        missing_names.append(named_stuff_spec.variable_name)
                case PresenceMarker.PLAIN:
                    if absence_record:
                        liftable.append(AbsentInput(named_stuff_spec=named_stuff_spec, absence_record=absence_record))
                    else:
                        missing_names.append(named_stuff_spec.variable_name)
        return InputPresenceScan(missing_names=missing_names, forced_absent=forced_absent, liftable=liftable)

    @final
    async def validate_before_run(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> InputPresenceScan:
        # A PipeSignature has no implementation: reject live execution before the input
        # checks below, so callers get the actionable error, not a misleading "missing inputs".
        if self.is_signature and pipe_run_params.run_mode.is_live:
            raise PipeSignatureNotExecutableError(pipe_ref=self.pipe_ref)

        # The runtime trichotomy (D3): a recorded absence on a `!` input is a typed failure with
        # provenance; absent with no record (and not optional) is a hard miss — the bug case.
        presence_scan = self._scan_input_presence(working_memory=working_memory)

        if presence_scan.forced_absent:
            forced = presence_scan.forced_absent[0]
            raise OptionalValueAbsentError.make(
                run_mode=pipe_run_params.run_mode,
                pipe_code=self.code,
                variable_name=forced.named_stuff_spec.variable_name,
                concept_ref=forced.named_stuff_spec.concept.concept_ref,
                absence_record=forced.absence_record,
            )

        if presence_scan.missing_names:
            run_label = "Dry run" if pipe_run_params.run_mode.is_dry else "Live run"
            msg = f"{run_label} of {self.type} '{self.code}': missing required inputs: {', '.join(presence_scan.missing_names)}."
            optional_input_names = [
                named_stuff_spec.variable_name for named_stuff_spec in self.needed_inputs().named_stuff_specs if named_stuff_spec.presence.is_optional
            ]
            if optional_input_names:
                msg += f" These optional inputs may be omitted: {', '.join(optional_input_names)}."
            raise PipeRunInputsError(
                message=msg,
                run_mode=pipe_run_params.run_mode,
                pipe_code=self.code,
                missing_inputs=presence_scan.missing_names,
            )

        # The pipe is about to be lifted (skipped): per-pipe validation and resource checks are
        # moot — they would inspect inputs the pipe will never consume.
        if presence_scan.liftable:
            return presence_scan

        # Validate external resources (URLs, file paths) referenced by input contents.
        # Skipped in dry-run mode because inputs are mock-generated with fake URLs.
        if not pipe_run_params.run_mode.is_dry:
            for named_stuff_spec in self.needed_inputs().named_stuff_specs:
                variable_name = named_stuff_spec.variable_name
                stuff = working_memory.get_optional_stuff(variable_name)
                if stuff is not None:
                    try:
                        stuff.content.validate_resources()
                    except ValueError as exc:
                        msg = f"Input '{variable_name}' of pipe '{self.code}' references an invalid resource: {exc}"
                        raise PipeRunInputsError(
                            message=msg,
                            run_mode=pipe_run_params.run_mode,
                            pipe_code=self.code,
                            variable_name=variable_name,
                        ) from exc

        # Specific pipe validation function
        await self._validate_before_run(
            job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name
        )
        return presence_scan

    @abstractmethod
    async def _validate_before_run(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ):
        pass

    @final
    async def validate_after_run(
        self,
        *,
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
        *,
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
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
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
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: LibraryCrate | None = None,
    ) -> PipeOutput:
        # Push the pipe's frame onto the stack, run it, and always pop it — even on failure —
        # so a failed pipe never leaves a stale frame behind on the shared pipe_stack, where it
        # could accumulate entries and trip PipeStackOverflowError. Required cleanup belongs in a
        # `finally` block.
        pipe_run_params.push_pipe_to_stack(pipe_code=self.code)
        try:
            return await self._run_pipe_traced(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
                output_name=output_name,
                library_crate=library_crate,
            )
        finally:
            pipe_run_params.pop_pipe_from_stack(pipe_code=self.code)

    @final
    async def _run_pipe_traced(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: LibraryCrate | None = None,
    ) -> PipeOutput:
        """Run the pipe with graph tracing — the inner body of `run_pipe()`.

        Split out so `run_pipe()` stays a thin push / `try`-`finally` / pop wrapper that
        keeps the pipe's `pipe_stack` frame balanced on every exit path.
        """
        # Handle graph tracing if enabled
        graph_node_id: str | None = None
        child_trace_context: TraceContext | None = None
        tracer_manager = None

        parent_trace_context = job_metadata.trace_context
        if parent_trace_context is not None:
            tracer_manager = GraphTracerManager.get_instance()
            if tracer_manager is not None:
                started_at = datetime.now(UTC)
                node_kind = NodeKind.CONTROLLER if self.is_controller else NodeKind.OPERATOR

                # Capture input specs from working memory for data flow tracking
                input_specs: list[IOSpec] = []
                for var_name in self.needed_inputs().declared_names:
                    stuff = working_memory.get_optional_stuff(var_name)
                    if stuff is not None:
                        # E1: gate the expensive payload serialization on emit_graph_events too — in
                        # costs-only mode the GraphSpec is never assembled, so these dumps would be built
                        # then discarded. The lightweight IOSpec (name/concept/content_type/digest) is kept
                        # so node ids and usage-event correlation are unaffected.
                        include_graph_data = parent_trace_context.emit_graph_events
                        input_spec = IOSpec(
                            name=var_name,
                            concept=stuff.concept.code,
                            content_type=stuff.content.content_type,
                            digest=stuff.stuff_code,
                            data=stuff.content.smart_dump()
                            if (include_graph_data and parent_trace_context.data_inclusion.stuff_json_content)
                            else None,
                            data_text=stuff.content.rendered_pretty_text()
                            if (include_graph_data and parent_trace_context.data_inclusion.stuff_text_content)
                            else None,
                            data_html=stuff.content.rendered_pretty_html()
                            if (include_graph_data and parent_trace_context.data_inclusion.stuff_html_content)
                            else None,
                        )
                        input_specs.append(input_spec)

                # Serialize pipe and concept data for registries if enabled (E1: also gated on
                # emit_graph_events — the registries only feed the GraphSpec).
                pipe_data: dict[str, Any] | None = None
                concept_data: list[dict[str, Any]] | None = None
                if parent_trace_context.emit_graph_events and parent_trace_context.data_inclusion.pipe_and_concept_registry:
                    pipe_data = self._make_pipe_data_for_registry(library_crate=library_crate)
                    concept_data = self._make_concept_data_for_registry(library_crate=library_crate)

                graph_node_id, child_trace_context = tracer_manager.on_pipe_start(
                    trace_context=parent_trace_context,
                    pipe_code=self.code,
                    pipe_type=self.type,
                    node_kind=node_kind,
                    started_at=started_at,
                    input_specs=input_specs or None,
                    pipe_data=pipe_data,
                    concept_data=concept_data,
                    description=self.description,
                    domain_code=self.domain_code,
                )
                # Update job metadata with child trace context for nested pipes
                if child_trace_context is not None:
                    job_metadata = job_metadata.copy_with_update(
                        otel_context=job_metadata.otel_context,
                        trace_context=child_trace_context,
                    )
        try:
            presence_scan = await self.validate_before_run(
                job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name
            )
            if presence_scan.liftable:
                # Implicit lifting (D3): a plain input fed a recorded absence skips the pipe;
                # its output is recorded absent with provenance chaining to the input's record.
                pipe_output = self._make_lifted_output(
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    liftable=presence_scan.liftable,
                    pipe_run_params=pipe_run_params,
                    output_name=output_name,
                )
            else:
                match pipe_run_params.run_mode:
                    case PipeRunMode.LIVE:
                        pipe_output = await self.live_run_pipe(
                            job_metadata=job_metadata,
                            working_memory=working_memory,
                            pipe_run_params=pipe_run_params,
                            output_name=output_name,
                            library_crate=library_crate,
                        )
                    case PipeRunMode.DRY:
                        pipe_output = await self.dry_run_pipe(
                            job_metadata=job_metadata,
                            working_memory=working_memory,
                            pipe_run_params=pipe_run_params,
                            output_name=output_name,
                            library_crate=library_crate,
                        )
                await self.validate_after_run(
                    job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name
                )
        except Exception as exc:
            # Broad catch is intentional: graph tracing must record EVERY failure mode,
            # including unexpected ones — an untraced failure is an observability hole.
            # This observes-and-re-raises (no swallow, no convert), so no bug is hidden.
            # Can't be a `finally`: the success/error paths record different things and
            # the error path needs the exception object.
            # Record graph tracing error
            if tracer_manager is not None and parent_trace_context is not None:
                error_stack: str | None = None
                if parent_trace_context.data_inclusion.error_stack_traces:
                    error_stack = traceback.format_exc()
                tracer_manager.on_pipe_end_error(
                    lookup_key=parent_trace_context.lookup_key,
                    node_id=graph_node_id,
                    ended_at=datetime.now(UTC),
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    error_stack=error_stack,
                )
            raise

        # Record graph tracing completion — a lifted (skipped) pipe ends its node in the distinct
        # `skipped` state with the skip reason; every other completion is a success.
        if tracer_manager is not None and parent_trace_context is not None:
            # Capture output spec for data flow tracking — a completed pipe run always resolves its
            # declared output: a value or a recorded absence. An absent output has no payload to
            # capture. A LIFTED pipe with a PLURAL output still wrote a real empty-list Stuff (D4)
            # that downstream pipes consume, so its spec must register in the producer map exactly
            # like a produced value — otherwise the consumers' DATA edges silently drop.
            main_resolved = pipe_output.working_memory.resolve_main_stuff()
            output_spec: IOSpec | None = None
            output_concept_data: dict[str, Any] | None = None
            if isinstance(main_resolved, Stuff):
                main_stuff = main_resolved
                # E1: same gating as the input block — skip the discarded payload dumps in costs-only mode.
                include_graph_data = parent_trace_context.emit_graph_events
                output_spec = IOSpec(
                    name=output_name or main_stuff.stuff_name or "main_stuff",
                    concept=main_stuff.concept.code,
                    content_type=main_stuff.content.content_type,
                    digest=main_stuff.stuff_code,
                    data=main_stuff.content.smart_dump() if (include_graph_data and parent_trace_context.data_inclusion.stuff_json_content) else None,
                    data_text=main_stuff.content.rendered_pretty_text()
                    if (include_graph_data and parent_trace_context.data_inclusion.stuff_text_content)
                    else None,
                    data_html=main_stuff.content.rendered_pretty_html()
                    if (include_graph_data and parent_trace_context.data_inclusion.stuff_html_content)
                    else None,
                    # The optional-edge marker (D8): a data edge fed by this output reports that the
                    # value may be absent in other runs.
                    extra={"optional": True} if self.output.presence.is_optional else {},
                )

                # Serialize output concept for registry if enabled (E1: also gated on emit_graph_events).
                if parent_trace_context.emit_graph_events and parent_trace_context.data_inclusion.pipe_and_concept_registry:
                    output_concept_data = self._make_single_concept_data_for_registry(main_stuff.concept, library_crate=library_crate)

            if presence_scan.liftable:
                tracer_manager.on_pipe_end_skipped(
                    lookup_key=parent_trace_context.lookup_key,
                    node_id=graph_node_id,
                    ended_at=datetime.now(UTC),
                    skip_reason=self._make_skip_reason(liftable=presence_scan.liftable),
                    output_spec=output_spec,
                    output_concept_data=output_concept_data,
                )
                # Plural companion slots also wrote real empty-list Stuffs on the lift — register
                # them as this node's outputs so their downstream DATA edges resolve too.
                # (graph_node_id is set whenever tracing recorded the start; guard for the type.)
                if graph_node_id is not None:
                    for companion_slot in self.lifted_companion_slots():
                        if not companion_slot.is_plural:
                            continue
                        companion_stuff = pipe_output.working_memory.get_optional_stuff(companion_slot.slot_name)
                        if companion_stuff is None:
                            continue
                        tracer_manager.register_controller_output(
                            lookup_key=parent_trace_context.lookup_key,
                            node_id=graph_node_id,
                            output_spec=IOSpec(
                                name=companion_slot.slot_name,
                                concept=companion_stuff.concept.code,
                                content_type=companion_stuff.content.content_type,
                                digest=companion_stuff.stuff_code,
                            ),
                        )
            else:
                tracer_manager.on_pipe_end_success(
                    lookup_key=parent_trace_context.lookup_key,
                    node_id=graph_node_id,
                    ended_at=datetime.now(UTC),
                    output_spec=output_spec,
                    output_concept_data=output_concept_data,
                )

        return pipe_output

    def lifted_companion_slots(self) -> list[CompanionSlot]:
        """Extra slots this pipe would have written besides its main output, to resolve when it
        is lifted. Default: none; an `add_each_output` PipeParallel reports its branch slots.
        """
        return []

    @classmethod
    def _make_skip_reason(cls, *, liftable: list[AbsentInput]) -> str:
        """The one skip-reason wording, shared by the absence record and the graph node."""
        return f"skipped because input '{liftable[0].named_stuff_spec.variable_name}' is absent"

    def _make_lifted_output(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        liftable: list[AbsentInput],
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        """Skip this pipe (implicit lifting, D3) and record its output as absent with provenance.

        A plural output does not go absent: it normalizes to an empty list (D4) — `[]`-emptiness
        is the absence story for plurals — with a ledger note kept for observability; taint stops.
        Plurality is resolved like the run path resolves it (declared multiplicity + the
        invocation-level override), matching what the static taint pass promised downstream.
        Companion slots the pipe would also have written (`lifted_companion_slots`) are resolved
        the same way, so no downstream consumer meets a neither-value-nor-record hard miss.
        """
        lifted_input = liftable[0]
        absent_names = ", ".join(absent.named_stuff_spec.variable_name for absent in liftable)
        output_slot_name = output_name or MAIN_STUFF_NAME
        log.info(f"Skipping {self.type} '{self.code}': absent input(s): {absent_names}")

        skip_reason = self._make_skip_reason(liftable=liftable)
        skip_record = AbsenceRecord(
            variable_name=output_slot_name,
            kind=AbsenceKind.SKIPPED,
            reason=skip_reason,
            producing_pipe=self.code,
            upstream=lifted_input.absence_record,
        )
        multiplicity_resolution = output_multiplicity_to_apply(
            base_multiplicity=self.output.multiplicity,
            override_multiplicity=pipe_run_params.output_multiplicity,
        )
        if multiplicity_resolution.is_multiple_outputs_enabled:
            empty_list_stuff = Stuff(
                concept=self.output.concept,
                content=ListContent[StuffContent](items=[]),
                stuff_name=output_slot_name,
                stuff_code=shortuuid.uuid()[:5],
            )
            working_memory.set_new_main_stuff(empty_list_stuff, name=output_name)
            # Observability note only — the empty list is the value consumers see.
            working_memory.record_absence(skip_record)
        else:
            working_memory.record_new_main_absence(skip_record)

        for companion_slot in self.lifted_companion_slots():
            companion_record = AbsenceRecord(
                variable_name=companion_slot.slot_name,
                kind=AbsenceKind.SKIPPED,
                reason=skip_reason,
                producing_pipe=companion_slot.producing_pipe_code,
                upstream=lifted_input.absence_record,
            )
            if companion_slot.is_plural:
                empty_companion_stuff = Stuff(
                    concept=companion_slot.concept,
                    content=ListContent[StuffContent](items=[]),
                    stuff_name=companion_slot.slot_name,
                    stuff_code=shortuuid.uuid()[:5],
                )
                working_memory.set_stuff(name=companion_slot.slot_name, stuff=empty_companion_stuff)
                working_memory.record_absence(companion_record)
            else:
                working_memory.record_resolved_absence(companion_record)

        return PipeOutput(working_memory=working_memory, pipeline_run_id=job_metadata.run_metadata.pipeline_run_id)

    @final
    async def live_run_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: LibraryCrate | None = None,
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
                pipeline_run_id=job_metadata.run_metadata.pipeline_run_id,
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
                job_metadata=child_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
                output_name=output_name,
                library_crate=library_crate,
            )
        except Exception as exc:
            # Broad catch is intentional: the OTel span must be closed with ERROR status
            # on any failure. Observes-and-re-raises — see note on the catch in _run_pipe_traced.
            self._end_pipe_span_error(span, error=exc, is_root_span=is_root_span)
            raise

        # Handle telemetry ------------------------------------------------------------

        self._end_pipe_span_success(span=span, pipe_output=pipe_output, is_root_span=is_root_span)

        return pipe_output

    @final
    async def dry_run_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: LibraryCrate | None = None,
    ) -> PipeOutput:
        log.verbose(f"Dry run of {self.type}: '{self.code}'")
        assert pipe_run_params.run_mode.is_dry, f"Dry run of {self.type} '{self.code}' called with run_mode = {pipe_run_params.run_mode}"
        # Stamp the running pipe onto the metadata handed down, exactly as `live_run_pipe` does.
        # Without it a dry run's `job_metadata.pipe_code` stays whatever the caller passed — usually
        # unset — so everything downstream that identifies a step by it (leaf-activity labelling in a
        # distributed backend, log correlation) sees an anonymous step in DRY and a named one in LIVE.
        # Telemetry stays live-only on purpose: `pipe_run_id` and `otel_context` belong to a real run.
        # `otel_context=None` matches what `live_run_pipe` itself computes in dry mode, and clearing
        # it explicitly is the point of that parameter being required — inheriting the parent's would
        # attach a dry step to a live span.
        child_metadata = job_metadata.copy_with_update(otel_context=None, pipe_code=self.code)
        return await self._dry_run_pipe(
            job_metadata=child_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
            library_crate=library_crate,
        )

    @abstractmethod
    async def _live_run_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: LibraryCrate | None = None,
    ) -> PipeOutput:
        pass

    @abstractmethod
    async def _dry_run_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: LibraryCrate | None = None,
    ) -> PipeOutput:
        pass

    def _start_pipe_span(
        self,
        *,
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
            needed_input_names = set(self.needed_inputs().declared_names)
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

    def _end_pipe_span_success(self, span: Span | None, *, pipe_output: PipeOutput, is_root_span: bool) -> None:
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

    def _end_pipe_span_error(self, span: Span | None, *, error: Exception, is_root_span: bool = False) -> None:
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
