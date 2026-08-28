import re
from abc import ABC
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Self, cast, final

from pydantic import BaseModel, ConfigDict, Field, SerializerFunctionWrapHandler, field_validator, model_serializer, model_validator

from pipelex.core.concepts.exceptions import ConceptStringError
from pipelex.core.concepts.validation import validate_concept_ref_or_code
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.pipes.variable_multiplicity import (
    MULTIPLICITY_PATTERN,
    PipeVariableMultiplicityError,
    is_force_presence,
    is_multiple_multiplicity,
    multiplicity_from_bracket_content,
    parse_concept_with_multiplicity,
    presence_from_symbol,
    presence_symbol,
)
from pipelex.pipe_machinery.validation import validate_input_name
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
# consulted). Single source of truth for the blueprint and spec (authoring) layers — the spec layer
# reuses it augmented with its structural `pipe_code` field (see `SIGNATURE_ONLY_SPEC_KEYS`).
SIGNATURE_ONLY_KEYS: frozenset[str] = frozenset({"description", "inputs", "output", "signature_for", "source"})

# The contract keys advertised to authors in the typeless-signature teaching message, in display order.
# Deliberately NOT derived from `SIGNATURE_ONLY_KEYS` / `SIGNATURE_ONLY_SPEC_KEYS`: those admit internal
# keys never written by an author (`source`, and the spec layer's structural `pipe_code`) that must not
# leak into a user-facing message. Kept here so the message can never drift from the advertisable set.
_ADVERTISABLE_SIGNATURE_KEYS: tuple[str, ...] = ("description", "inputs", "output", "signature_for")


def explicit_signature_tag_migration_message(pipe_code: Any) -> str:
    """The migration error for a section that still writes the retired `type = "PipeSignature"` tag.

    Starts with ``Pipe `<code>``` so the validation-error categorizer recovers the pipe code from the
    message (the error is raised on the aggregate `pipe` field, which carries no pipe code in its
    pydantic `loc`). Single source of truth for the blueprint and spec layers and the single-pipe
    authoring path (`parse_pipe_spec`).
    """
    return (
        f'Pipe `{pipe_code}` sets `type = "PipeSignature"`, which is no longer a pipe type. '
        "Delete the `type` line — a pipe with no `type` and no implementation is a signature (contract only)."
    )


def normalize_typeless_signature_section(*, pipe_code: Any, pipe_section: Any, allowed_keys: frozenset[str] = SIGNATURE_ONLY_KEYS) -> Any:
    """Inject the internal `PipeSignature` tag on a typeless contract-only section, reject a typeless
    section that declares more than the contract, and reject a section that still writes the retired
    explicit `type = "PipeSignature"` tag. Non-dict values (already-built pipe instances) and sections
    that name a concrete `type` pass through unchanged.

    Shared by the blueprint (`PipelexBundleBlueprint`) and spec (`PipelexBundleSpec`) `pipe`
    before-validators so both teaching messages — whose exact wording the validation-error categorizer
    keys off (`_MISSING_PIPE_TYPE_MARKER` / `_EXPLICIT_SIGNATURE_TAG_MARKER` in
    `validation_error_categorizer.py`) — have a single source of truth. `allowed_keys` differs per
    layer: the spec section additionally carries the structural `pipe_code` field, so it passes
    `SIGNATURE_ONLY_SPEC_KEYS`.

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
    stray_keys = [key for key in typed_section if key not in allowed_keys]
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
    for the three layers (`PipeBlueprint`, `PipeAbstract`, `PipeSpec`) that gate `type`.
    """
    return [*PipeType.value_list(), PIPE_SIGNATURE_TYPE_TAG]


class InputSlotBlueprint(BaseModel):
    """The expanded input-slot form: `name = { concept = "…", hints = { … } }` (spec: intent-hints.md).

    `concept` carries the full slot grammar of the string form (ref, optional multiplicity, optional
    presence marker). The form is deliberately closed (`extra="forbid"` implements the spec's
    "unknown slot-table keys MUST be rejected") so future per-slot semantic keys land here without a
    second syntax. A slot table carrying no hints collapses to its plain string at parse time (see
    `PipeBlueprint.collapse_hint_free_slot_tables`), so a slot value that IS a table carries
    non-empty hints — hint-free bundles produce byte-identical blueprints to the string form.
    """

    model_config = ConfigDict(extra="forbid")

    concept: str
    hints: dict[str, str] | None = None

    @field_validator("hints", mode="after")
    @classmethod
    def normalize_empty_hints(cls, hints: dict[str, str] | None) -> dict[str, str] | None:
        # Sorted here so every serialization is canonical (spec: hints entries emitted sorted by
        # key); hint key order is not semantic, unlike structure-field order.
        return dict(sorted(hints.items())) if hints else None

    @model_serializer(mode="wrap")
    def serialize_without_absent_hints(self, handler: SerializerFunctionWrapHandler):
        """Absent hints are an absent member — never `null` (spec rule). Unreachable for a
        hint-free slot in practice (the parse-time collapse leaves it a plain string), kept so any
        directly-constructed instance still serializes canonically.

        The return is deliberately unannotated — see `ConceptBlueprint.serialize_without_absent_hints`:
        an annotation here becomes the model's serialization JSON Schema and erases its shape.
        """
        dumped: dict[str, Any] = handler(self)
        if dumped.get("hints") is None:
            dumped.pop("hints", None)
        return dumped


def slot_concept_spec(slot_value: "str | InputSlotBlueprint") -> str:
    """The concept spec string of an input-slot value (markers included), whichever arm authored it."""
    return slot_value if isinstance(slot_value, str) else slot_value.concept


class PipeBlueprint(ABC, BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str | None = None
    pipe_category: Any = Field(exclude=True)  # Technical field for Union discrimination, not user-facing
    type: Any  # TODO: Find a better way to handle this.
    description: str
    inputs: Mapping[str, str | InputSlotBlueprint] | None = None
    """`Mapping` (not `dict`) deliberately: value-covariant, so the dominant hint-free callers keep
    passing plain `dict[str, str]` without a cast. Values are strings except for slots authored in
    the expanded form WITH hints (see the collapse rule below)."""
    output: str

    @field_validator("inputs", mode="after")
    @classmethod
    def collapse_hint_free_slot_tables(cls, inputs: Mapping[str, str | InputSlotBlueprint] | None) -> Mapping[str, str | InputSlotBlueprint] | None:
        """Parse-time collapse rule: `x = { concept = "S" }` and `x = { concept = "S", hints = {} }`
        are the same slot as `x = "S"` and become that string (the spec says they hash identically).
        Invariant bought downstream: a slot value that is a table carries non-empty hints.
        """
        if not inputs:
            return inputs
        return {name: value.concept if isinstance(value, InputSlotBlueprint) and not value.hints else value for name, value in inputs.items()}

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
                validate_input_name(input_name)

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
                if bracket_content and int(bracket_content) <= 0:
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
