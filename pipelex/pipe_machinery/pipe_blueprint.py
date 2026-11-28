import re
from abc import ABC
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Self, cast, final

from pydantic import BaseModel, ConfigDict, Field, SerializerFunctionWrapHandler, field_validator, model_serializer, model_validator

from pipelex.core.concepts.choice_options import ChoiceOptionValue, choice_values, parse_choices
from pipelex.core.concepts.contract_fact_blueprint import ContractFactsBlueprint, drop_absent_members, raise_first_finding
from pipelex.core.concepts.exceptions import ConceptStringError, ContractFactInvalidError
from pipelex.core.concepts.native.concept_native import NativeConceptCode, is_file_valued_native
from pipelex.core.concepts.validation import validate_concept_ref_or_code
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.pipes.variable_multiplicity import (
    MULTIPLICITY_PATTERN,
    PipeVariableMultiplicityError,
    fixed_count_from_digits,
    is_force_presence,
    is_multiple_multiplicity,
    multiplicity_from_bracket_content,
    parse_concept_with_multiplicity,
    presence_from_symbol,
    presence_symbol,
)
from pipelex.language.contract_facts import (
    CONTRACT_FACT_KEY_NAMES,
    TEXT_CONSTRAINT_KEYS,
    ContractFactKey,
    ContractFactReason,
    contradiction_findings,
)
from pipelex.pipe_machinery.validation import check_variables_are_declared, validate_input_names
from pipelex.tools.jinja2.exceptions import Jinja2TemplateSyntaxError
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.string_utils import get_root_from_dotted_path
from pipelex.validation_error_types import PipeValidationErrorType

# A signature is NOT an executable pipe kind: it is deliberately absent from `PipeType` and
# `PipeCategory`. This is the one extra `type` tag the parse-time allowlists admit beyond the
# executable kinds (a signature blueprint carries `type = "PipeSignature"`, `pipe_category = None`).
PIPE_SIGNATURE_TYPE_TAG = "PipeSignature"

# The exact set of keys a *typeless* `[pipe.x]` section may declare and still be a signature
# (contract only). A section with no `type` whose keys are a subset of this set is normalized to a
# `PipeSignature`; any other key present means the author is describing an implementation, which must
# name its `type` — that is a hard error (see `normalize_typeless_signature_section` below). `source`
# is a non-user blueprint field, admitted defensively so this set matches `PipeSignatureBlueprint`'s
# writable contract; it is unreachable via the stray-key path today (a section carrying `source` was
# dumped from a blueprint, so it also carries `type`, which short-circuits before this set is
# consulted).
SIGNATURE_ONLY_KEYS: frozenset[str] = frozenset({"description", "inputs", "output", "signature_for", "source"})

# The contract keys advertised to authors in the typeless-signature teaching message, in display order.
# Deliberately NOT derived from `SIGNATURE_ONLY_KEYS`: it admits `source`, an internal key never written
# by an author, which must not leak into a user-facing message. Kept here so the message can never drift from the advertisable set.
_ADVERTISABLE_SIGNATURE_KEYS: tuple[str, ...] = ("description", "inputs", "output", "signature_for")


def explicit_signature_tag_migration_message(pipe_code: Any) -> str:
    """The migration error for a section that still writes the retired `type = "PipeSignature"` tag.

    Starts with ``Pipe `<code>``` so the validation-error categorizer recovers the pipe code from the
    message (the error is raised on the aggregate `pipe` field, which carries no pipe code in its
    pydantic `loc`).
    """
    return (
        f'Pipe `{pipe_code}` sets `type = "PipeSignature"`, which is no longer a pipe type. '
        "Delete the `type` line — a pipe with no `type` and no implementation is a signature (contract only)."
    )


def normalize_typeless_signature_section(*, pipe_code: Any, pipe_section: Any) -> Any:
    """Inject the internal `PipeSignature` tag on a typeless contract-only section, reject a typeless
    section that declares more than the contract, and reject a section that still writes the retired
    explicit `type = "PipeSignature"` tag. Non-dict values (already-built pipe instances) and sections
    that name a concrete `type` pass through unchanged.

    Called by the `pipe` before-validator of `PipelexBundleBlueprint`. The exact wording of both
    teaching messages is what the validation-error categorizer keys off (`_MISSING_PIPE_TYPE_MARKER` /
    `_EXPLICIT_SIGNATURE_TAG_MARKER` in `validation_error_categorizer.py`).

    The injected tag never re-enters this function: it is returned in a fresh dict that downstream
    validation consumes directly, and `PipeSignatureBlueprint` excludes `type` from its serialization,
    so an internal dump→revalidate round-trip yields a typeless section (re-injected here), not the
    tag. The tag therefore appears in a raw section only when a user wrote it — which is what we reject.
    """
    if not isinstance(pipe_section, dict):
        return pipe_section
    typed_section = cast("dict[str, Any]", pipe_section)
    if "type" in typed_section:
        if typed_section["type"] == PIPE_SIGNATURE_TYPE_TAG:
            raise ValueError(explicit_signature_tag_migration_message(pipe_code))
        return typed_section
    stray_keys = [key for key in typed_section if key not in SIGNATURE_ONLY_KEYS]
    if stray_keys:
        stray = ", ".join(f"`{key}`" for key in stray_keys)
        allowed = ", ".join(f"`{key}`" for key in _ADVERTISABLE_SIGNATURE_KEYS)
        msg = (
            f"Pipe `{pipe_code}` has no `type` but declares {stray}. "
            f"A pipe with no `type` may declare only {allowed} — that is a "
            "signature (contract only). To implement it, add the appropriate `type` (`PipeLLM`, `PipeImgGen`, …). "
            f"To keep it a contract, remove {stray}."
        )
        raise ValueError(msg)
    return {**typed_section, "type": PIPE_SIGNATURE_TYPE_TAG}


class PipeCategory(StrEnum):
    PIPE_OPERATOR = "PipeOperator"
    PIPE_CONTROLLER = "PipeController"

    @classmethod
    def value_list(cls) -> list[str]:
        return list(cls)

    @property
    def is_controller(self) -> bool:
        match self:
            case PipeCategory.PIPE_CONTROLLER:
                return True
            case PipeCategory.PIPE_OPERATOR:
                return False

    @classmethod
    def is_controller_by_str(cls, category_str: str) -> bool:
        try:
            category = cls(category_str)
            return category.is_controller
        except ValueError:
            return False


class PipeType(StrEnum):
    # Pipe Operators
    PIPE_FUNC = "PipeFunc"
    PIPE_IMG_GEN = "PipeImgGen"
    PIPE_COMPOSE = "PipeCompose"
    PIPE_LLM = "PipeLLM"
    PIPE_EXTRACT = "PipeExtract"
    PIPE_SEARCH = "PipeSearch"
    PIPE_STRUCTURE = "PipeStructure"
    PIPE_DOC_GEN = "PipeDocGen"
    PIPE_JUDGE = "PipeJudge"
    # Pipe Controller
    PIPE_BATCH = "PipeBatch"
    PIPE_CONDITION = "PipeCondition"
    PIPE_PARALLEL = "PipeParallel"
    PIPE_SEQUENCE = "PipeSequence"

    @classmethod
    def value_list(cls) -> list[str]:
        return list(cls)

    @property
    def category(self) -> PipeCategory:
        match self:
            case PipeType.PIPE_FUNC:
                return PipeCategory.PIPE_OPERATOR
            case PipeType.PIPE_IMG_GEN:
                return PipeCategory.PIPE_OPERATOR
            case PipeType.PIPE_COMPOSE:
                return PipeCategory.PIPE_OPERATOR
            case PipeType.PIPE_LLM:
                return PipeCategory.PIPE_OPERATOR
            case PipeType.PIPE_EXTRACT:
                return PipeCategory.PIPE_OPERATOR
            case PipeType.PIPE_SEARCH:
                return PipeCategory.PIPE_OPERATOR
            case PipeType.PIPE_STRUCTURE:
                return PipeCategory.PIPE_OPERATOR
            case PipeType.PIPE_DOC_GEN:
                return PipeCategory.PIPE_OPERATOR
            case PipeType.PIPE_JUDGE:
                return PipeCategory.PIPE_OPERATOR
            case PipeType.PIPE_BATCH:
                return PipeCategory.PIPE_CONTROLLER
            case PipeType.PIPE_CONDITION:
                return PipeCategory.PIPE_CONTROLLER
            case PipeType.PIPE_PARALLEL:
                return PipeCategory.PIPE_CONTROLLER
            case PipeType.PIPE_SEQUENCE:
                return PipeCategory.PIPE_CONTROLLER


def valid_pipe_type_tags() -> list[str]:
    """Every legal `type` string a pipe blueprint may carry: the executable `PipeType` kinds plus the
    signature tag. A signature is not an executable kind (see `PIPE_SIGNATURE_TYPE_TAG`), so it is not a
    `PipeType` member — but the tag is the INTERNAL discriminator the before-validator injects for a
    typeless section, so the injected value must pass the `type` field validator and therefore belongs
    in this allowlist. It is never written by users: an explicit `type = "PipeSignature"` is rejected
    upstream in the before-validator (`normalize_typeless_signature_section`). Single source of truth
    for the two layers (`PipeBlueprint`, `PipeAbstract`) that gate `type`.
    """
    return [*PipeType.value_list(), PIPE_SIGNATURE_TYPE_TAG]


class InputSlotBlueprint(ContractFactsBlueprint):
    """The expanded input-slot form: `name = { concept = "…", description = "…", hints = { … }, … }` (spec: mthds-format.md,
    "Input slot declarations").

    `concept` carries the full slot grammar of the string form (ref, optional multiplicity, optional presence marker). Beside
    it, a slot may say what it is for in this pipe (`description`), carry intent hints, and, on a slot holding a plain value,
    the contract facts (`ContractFactsBlueprint`) and `choices` a structure field takes, which apply to each item of a plural
    slot. The form is deliberately closed (`extra="forbid"` implements the spec's "unknown slot-table keys MUST be
    rejected"). A slot table carrying none of these collapses to its plain string at parse time (see
    `PipeBlueprint.collapse_plain_slot_tables`), so such bundles produce byte-identical blueprints to the string form.

    What this blueprint judges alone: a description that is empty, `aggregate` (never on a slot), a text constraint or
    `examples` beside `choices`, and facts that contradict each other. Whether a fact or `choices` applies to the slot's value
    class depends on its concept, which a slot cannot resolve alone, so it is judged once the library's concepts are known
    (`pipelex.libraries.contract_fact_sites`).
    """

    model_config = ConfigDict(extra="forbid")

    concept: str
    description: str | None = None
    """What the slot is for in this pipe, which a consumer presenting the slot shows in place of its concept's description."""
    hints: dict[str, str] | None = None
    choices: list[ChoiceOptionValue] | None = None
    """The options a text-valued slot's text must be one of, each a string or an option table carrying words for people."""

    @field_validator("hints", mode="after")
    @classmethod
    def normalize_empty_hints(cls, hints: dict[str, str] | None) -> dict[str, str] | None:
        # Sorted here so every serialization is canonical (spec: hints entries emitted sorted by
        # key); hint key order is not semantic, unlike structure-field order.
        return dict(sorted(hints.items())) if hints else None

    @field_validator("description", mode="after")
    @classmethod
    def refuse_empty_description(cls, description: str | None) -> str | None:
        if description is not None and not description:
            msg = "An input slot's description must not be empty"
            raise ValueError(msg)
        return description

    @field_validator("choices", mode="before")
    @classmethod
    def read_choice_options(cls, choices: Any) -> Any:
        """Read the options into normal form, refusing a malformed option table (`parse_choices`)."""
        return parse_choices(raw=choices)

    @model_validator(mode="after")
    def refuse_facts_the_slot_alone_refuses(self) -> Self:
        """Refuse what a slot refuses whatever its concept: `aggregate`, a text constraint or `examples` beside `choices`,
        and facts that contradict each other. A concept holds any number, never only integers.
        """
        facts = self.contract_facts
        if self.aggregate is not None:
            msg = "'aggregate' is not allowed on an input slot, which holds one value, never a column of records"
            raise ContractFactInvalidError(msg, fact=ContractFactKey.AGGREGATE, reason=ContractFactReason.INAPPLICABLE)
        if self.choices:
            for key_name in facts:
                key = ContractFactKey(key_name)
                if key in TEXT_CONSTRAINT_KEYS or key is ContractFactKey.EXAMPLES:
                    msg = f"'{key}' is not allowed beside 'choices': the options list every value"
                    raise ContractFactInvalidError(msg, fact=key, reason=ContractFactReason.INAPPLICABLE)
        raise_first_finding(findings=contradiction_findings(facts=facts, is_integer=False))
        return self

    @property
    def carries_meaning(self) -> bool:
        """Whether the slot carries anything beyond its concept: hints, a description, a contract fact or `choices`."""
        return bool(self.hints) or self.description is not None or bool(self.contract_facts) or self.choices is not None

    @property
    def choice_values(self) -> list[str] | None:
        """The values the slot's options declare, in declared order, or `None` for a slot with no `choices`."""
        return choice_values(options=self.choices) if self.choices is not None else None

    @model_serializer(mode="wrap")
    def serialize_without_absent_members(self, handler: SerializerFunctionWrapHandler):
        """Absent members are absent — never `null` (spec rule): hints, description, choices and every contract fact.

        The return is deliberately unannotated — see `ConceptBlueprint.serialize_without_absent_hints`:
        an annotation here becomes the model's serialization JSON Schema and erases its shape.
        """
        dumped: dict[str, Any] = handler(self)
        return drop_absent_members(dumped=dumped, keys=("hints", "description", "choices", *CONTRACT_FACT_KEY_NAMES))


def slot_concept_spec(slot_value: "str | InputSlotBlueprint") -> str:
    """The concept spec string of an input-slot value (markers included), whichever arm authored it."""
    return slot_value if isinstance(slot_value, str) else slot_value.concept


class PipeBlueprint(ABC, BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str | None = None
    """Not an authoring field. The library manager clears it just before the pipe is built, so whatever a bundle's text
    writes here is never read: a step finds a file its bundle names in the bundle's method tree, which the library
    manager hands the factory (see `LibraryCrate.tree_bundles` and `building_pipe_of`)."""
    pipe_category: Any = Field(exclude=True)  # Technical field for Union discrimination, not user-facing
    type: Any  # TODO: Find a better way to handle this.
    description: str
    inputs: Mapping[str, str | InputSlotBlueprint] | None = None
    """`Mapping` (not `dict`) deliberately: value-covariant, so the dominant hint-free callers keep
    passing plain `dict[str, str]` without a cast. Values are strings except for slots authored in
    the expanded form WITH hints (see the collapse rule below)."""
    output: str
    activity: str | None = None
    """What the pipe is doing, in the present tense, for a person watching a run (spec: mthds-format.md, "What a Run
    Shows"). Plain text, never a template. A contract-only signature does not carry it."""
    output_filename: str | None = None
    """A Jinja2 template naming the file an operator with a file-valued output writes (spec: "Naming Produced Files"). It
    reads the pipe's inputs, so it counts as reading them; a controller writes no file and refuses it. Naming the file is
    the runtime's when the pipe produces its output."""

    @model_serializer(mode="wrap")
    def serialize_without_absent_presentation(self, handler: SerializerFunctionWrapHandler):
        """An absent `activity` or `output_filename` is an absent member, never `null`, so a library that authors neither
        keeps its fingerprint. The return is deliberately unannotated — see `ConceptBlueprint.serialize_without_absent_hints`.
        """
        dumped: dict[str, Any] = handler(self)
        return drop_absent_members(dumped=dumped, keys=("activity", "output_filename"))

    @field_validator("activity", mode="before")
    @classmethod
    def validate_activity(cls, activity: Any) -> Any:
        if activity is None or not isinstance(activity, str):
            return activity
        if not activity.strip():
            msg = "A pipe's activity must not be empty"
            raise ValueError(msg)
        if "\n" in activity or "\r" in activity:
            msg = "A pipe's activity must hold no line break: it is a short phrase for a person watching a run"
            raise ValueError(msg)
        return activity

    @model_validator(mode="after")
    def validate_output_filename_site(self) -> Self:
        """Refuse `output_filename` where no file is written: on a controller, and on an operator whose output names a native
        concept that is not file-valued. An output naming a declared concept is judged once the library's concepts are known
        (`pipelex.libraries.contract_fact_sites`). Every variable it reads must be a declared input.
        """
        if self.output_filename is None:
            return self
        if self.is_signature or (self.pipe_category is not None and PipeCategory(self.pipe_category).is_controller):
            msg = "`output_filename` is not allowed on a controller, which writes no file of its own: set it on the operator that produces the file"
            raise ValueError(msg)
        output_ref = parse_concept_with_multiplicity(self.output).concept_ref_or_code
        if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=output_ref) and not is_file_valued_native(native_ref=output_ref):
            msg = (
                "`output_filename` is allowed only on an operator whose output is file-valued (an Image or a Document), "
                f"and this output is '{self.output}'"
            )
            raise ValueError(msg)
        check_variables_are_declared(
            declared_inputs=set(self.input_names), variable_paths=self.output_filename_variable_paths(), reader="output_filename"
        )
        return self

    def output_filename_variable_paths(self) -> set[str]:
        """The dotted variable paths `output_filename` reads, internal names (starting with an underscore) excluded.

        It is plain Jinja2: the `$` and `@` shorthands are not expanded in it, so a file name may hold either as itself.

        Raises:
            ValueError: When the template does not parse.
        """
        if self.output_filename is None:
            return set()
        try:
            check_jinja2_parsing(template_source=self.output_filename, template_category=TemplateCategory.BASIC)
        except Jinja2TemplateSyntaxError as exc:
            msg = f"Could not parse the output_filename template: {exc}"
            raise ValueError(msg) from exc
        full_paths = detect_jinja2_required_variables(template_category=TemplateCategory.BASIC, template_source=self.output_filename)
        return {path for path in full_paths if not get_root_from_dotted_path(path).startswith("_")}

    def reader_with_output_filename(self, *, reader: str) -> str:
        """The fields that read an operator's inputs, as a message names them, `output_filename` included when it is set."""
        return f"{reader} or output_filename" if self.output_filename is not None else reader

    @field_validator("inputs", mode="after")
    @classmethod
    def collapse_plain_slot_tables(cls, inputs: Mapping[str, str | InputSlotBlueprint] | None) -> Mapping[str, str | InputSlotBlueprint] | None:
        """Parse-time collapse rule: `x = { concept = "S" }` and `x = { concept = "S", hints = {} }`
        are the same slot as `x = "S"` and become that string (the spec says they hash identically).
        Invariant bought downstream: a slot value that is a table carries hints, a description, a
        contract fact or `choices` (`InputSlotBlueprint.carries_meaning`).
        """
        if not inputs:
            return inputs
        return {
            name: value.concept if isinstance(value, InputSlotBlueprint) and not value.carries_meaning else value for name, value in inputs.items()
        }

    @property
    def nb_inputs(self) -> int:
        return len(self.inputs) if self.inputs else 0

    @property
    def input_names(self) -> list[str]:
        return list(self.inputs.keys()) if self.inputs else []

    @property
    def inputs_concept_specs(self) -> dict[str, str] | None:
        """Slot name -> concept spec string (markers included), whichever arm authored each slot.

        The projection for consumers that read the slot grammar and nothing else — template
        analyzers, contract matching, the runtime spec factory. Hints-aware consumers (crate
        qualification, the input-form deriver) read `inputs` itself.
        """
        if self.inputs is None:
            return None
        return {name: slot_concept_spec(value) for name, value in self.inputs.items()}

    @property
    def is_signature(self) -> bool:
        # Identity by class, not by enum field: the base is never a signature; `PipeSignatureBlueprint`
        # overrides this to True. (`pipe_category` no longer encodes signature-ness.)
        return False

    @property
    def pipe_dependencies(self) -> set[str]:
        """Return the set of pipe codes that this pipe depends on.

        This is overridden by PipeController subclasses to return their dependencies.
        PipeOperators have no dependencies, so return an empty set.

        Returns:
            Set of pipe codes this pipe depends on
        """
        return set()

    @property
    def named_file_references(self) -> set[str]:
        """The files of its method tree this pipe names, as it writes them, relative to its bundle.

        Overridden by a pipe that reads a file of its tree, such as a `PipeDocGen` step's `template_file`. A bundle
        submitted as content strings brings exactly these files with it.
        """
        return set()

    @property
    def ordered_pipe_dependencies(self) -> list[str] | None:
        """Return ordered dependencies if order matters (e.g., for PipeSequence steps).

        This is overridden by controllers where dependency order is significant,
        such as PipeSequence where steps should be processed in order.

        Returns:
            Ordered list of pipe codes if order matters, None otherwise
        """
        return None

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
            msg = f"Invalid pipe type '{self.type}'. Must be one of: {PipeType.value_list()}"
            raise ValueError(msg) from exc

        if self.pipe_category != pipe_type.category:
            msg = (
                f"Inconsistency detected: pipe_category '{self.pipe_category}' does not match the "
                f"expected category '{pipe_type.category}' for type '{self.type}'"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def validate_inputs_blueprint(self) -> Self:
        self.generic_validate_inputs()
        self.generic_validate_output()
        return self

    def validate_inputs(self):
        pass

    def validate_output(self):
        pass

    @final
    def generic_validate_inputs(self):
        if self.inputs:
            for input_name, slot_value in self.inputs.items():
                # One grammar, two spellings: the expanded slot form's `concept` value is validated
                # with the same ref+multiplicity+presence grammar as the plain string form.
                concept_spec = slot_concept_spec(slot_value)

                # Validate the concept spec format: optional multiplicity brackets then optional
                # presence marker. Pattern allows: ConceptName, domain.ConceptName, ConceptName[],
                # ConceptName[N], ConceptName?, ConceptName!
                match = re.match(MULTIPLICITY_PATTERN, concept_spec)
                if not match:
                    msg = (
                        f"Invalid input syntax for '{input_name}': '{concept_spec}'. "
                        f"Expected format: 'ConceptName', 'ConceptName[]', 'ConceptName[N]' where N is an integer, "
                        f"with an optional presence marker '?' or '!' on singular forms (e.g. 'ConceptName?')."
                    )
                    raise ValueError(msg)

                bracket_content = match.group(2)
                # A count written with more digits than any runtime allows is refused on the string, naming the input,
                # before it is converted; whether it passes the maximum in force is the load's check.
                if bracket_content and fixed_count_from_digits(digits=bracket_content, slot=f"the input '{input_name}'") <= 0:
                    msg = f"Invalid input '{input_name}': '{concept_spec}'. Multiplicity must be at least 1."
                    raise ValueError(msg)

                # D1/D4: presence markers are mutually exclusive with multiplicity — a plural slot's
                # "nothing" is the empty list, so there is nothing for `?` or `!` to say. A `[1]` slot
                # is not plural: it is the single form with its count written out, so it takes a marker
                # exactly as a bare ref does. Reading the projection rather than the bracket text is
                # what keeps this in step with the output half, which parses before it decides.
                presence = presence_from_symbol(symbol=match.group(3))
                multiplicity = multiplicity_from_bracket_content(bracket_content=bracket_content)
                if not presence.is_plain and is_multiple_multiplicity(multiplicity=multiplicity):
                    msg = (
                        f"Invalid input '{input_name}': '{concept_spec}'. "
                        f"The presence marker '{presence_symbol(presence=presence)}' cannot be combined with multiplicity: "
                        f"a plural slot is never absent — when nothing is found, it is the empty list."
                    )
                    raise PipeValidationError(
                        message=msg,
                        error_type=PipeValidationErrorType.OPTIONAL_MARKER_INVALID,
                        variable_names=[input_name],
                    )

                # Extract the concept part (without markers) and validate it
                concept_ref_or_code = match.group(1)
                try:
                    validate_concept_ref_or_code(concept_ref_or_code=concept_ref_or_code)
                except ConceptStringError as exc:
                    msg = f"Invalid concept string or code '{concept_ref_or_code}' when trying to validate the input of a pipe blueprint: {exc}"
                    raise ValueError(msg) from exc

            # One check for every pipe, operator, controller or signature alike: an input name is a plain
            # snake_case name, never a dotted path into a field (`invalid_input_name`). It runs once every spec
            # is known to be valid, because whether deleting a redundant dotted key is safe depends on the
            # markers the specs carry.
            validate_input_names(input_specs={input_name: slot_concept_spec(slot_value) for input_name, slot_value in self.inputs.items()})

        self.validate_inputs()

    @final
    def generic_validate_output(self):
        # Strip multiplicity brackets and presence marker before validating
        try:
            output_parse_result = parse_concept_with_multiplicity(self.output)
        except PipeVariableMultiplicityError as exc:
            msg = f"Invalid concept specification syntax: '{self.output}'. {exc}"
            raise ValueError(msg) from exc

        # D1: `!` is a use-site assertion — it is meaningless on outputs (a producer doesn't unwrap).
        if is_force_presence(presence=output_parse_result.presence):
            msg = (
                f"Invalid output: '{self.output}'. The force marker '!' is not allowed on outputs — "
                f"it is a use-site assertion for inputs. To declare that this pipe may produce no value, use '?'."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.OPTIONAL_MARKER_INVALID,
            )
        # D4: `?` is mutually exclusive with multiplicity — an absent plural normalizes to the empty list.
        if output_parse_result.presence.is_optional and output_parse_result.multiplicity is not None:
            msg = (
                f"Invalid output: '{self.output}'. The optional marker '?' cannot be combined with multiplicity: "
                f"a plural slot is never absent — when nothing is found, it is the empty list."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.OPTIONAL_MARKER_INVALID,
            )

        try:
            validate_concept_ref_or_code(concept_ref_or_code=output_parse_result.concept_ref_or_code)
        except ConceptStringError as exc:
            msg = f"Invalid concept string '{output_parse_result.concept_ref_or_code}' when trying to validate the output of a pipe blueprint: {exc}"
            raise ValueError(msg) from exc

        self.validate_output()
