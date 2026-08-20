"""The closed registry of ``error_type`` values a bundle-validation diagnostic can carry.

Every ``ValidationErrorItem`` — the per-error wire item behind the agent CLI's
``validation_errors[]`` array and the API's ``/validate`` verdict — names the fault it reports
in an ``error_type`` field. This module is where that vocabulary is defined, in full, and
:data:`VALIDATION_ERROR_TYPES` is the enumeration of it: a consumer that wants to know which
faults the language surface can report reads this registry rather than collecting strings from
whatever diagnostics it happens to have seen.

The registry is a **union of the enums the runtime already raises**, never a second list beside
them. ``PipeValidationErrorType`` and ``PipeFactoryErrorType`` are the two vocabularies the
validation stages produce, and :class:`ValidationResidualErrorType` names the one residual
channel that has no stage enum of its own. Deriving the registry from them is what stops it
from drifting: a member added to any of the three is in the registry the moment it is declared,
with nothing here to remember to update.

**Two spellings live in one vocabulary, deliberately.** The stage enums are snake_case codes
(``missing_input_variable``), while the dry-run residual is ``DryRunError`` — the name of the
exception that produced it, because that residual is raised as an error object rather than
classified into a code. Normalizing the residual would be a wire break across every consumer
that pins it, and it buys nothing: a reader consuming this registry gets the closed set either
way, and the corpus tag vocabulary already normalizes registry codes to snake_case on the way
in (``DryRunError`` → ``error.dry_run_error``, exactly as ``YesNo`` → ``native.yes_no``).

This module is deliberately low-level — stdlib only, and no ``pipelex`` imports at all — for the
same reason ``pipelex.suggested_fix`` is: ``pipelex.base_exceptions``, where
``ValidationErrorItem`` lives, types its ``error_type`` field against :data:`ValidationErrorType`
and must be able to import it without an import cycle. The stage enums live here rather than
beside the exceptions that raise them precisely so that typing is possible; the exception classes
in ``pipelex.core.pipes.exceptions`` import them back.
"""

from enum import StrEnum
from typing import TypeAlias


class PipeValidationErrorType(StrEnum):
    """Types of pipe validation errors.

    These error types are raised during pipe validation from Pipe/Concept classes.
    """

    MISSING_INPUT_VARIABLE = "missing_input_variable"
    EXTRANEOUS_INPUT_VARIABLE = "extraneous_input_variable"
    INPUT_STUFF_SPEC_MISMATCH = "input_stuff_spec_mismatch"
    INADEQUATE_OUTPUT_CONCEPT = "inadequate_output_concept"
    INADEQUATE_OUTPUT_MULTIPLICITY = "inadequate_output_multiplicity"

    CIRCULAR_DEPENDENCY_ERROR = "circular_dependency_error"

    LLM_OUTPUT_CANNOT_BE_IMAGE = "llm_output_cannot_be_image"
    INVALID_PIPE_CODE_SYNTAX = "invalid_pipe_code_syntax"
    UNKNOWN_PIPE_TYPE = "unknown_pipe_type"
    # A `[pipe.x]` section declared no `type` yet carries fields beyond the signature contract
    # (`description`, `inputs`, `output`). The author is describing an implementation without naming
    # its type — the counterpart to UNKNOWN_PIPE_TYPE (a declared-but-invalid type).
    MISSING_PIPE_TYPE = "missing_pipe_type"
    BATCH_ITEM_NAME_COLLISION = "batch_item_name_collision"

    # Presence-marker grammar misuse, detected at blueprint parse time: a presence marker
    # (`?` or `!`) combined with a multiplicity suffix, or `!` on an output (D1, D4 of the
    # optionals design).
    OPTIONAL_MARKER_INVALID = "optional_marker_invalid"

    # Static absence-taint violations (D6/D7/D11 of the optionals design): a maybe-absent slot
    # escaping through a non-optional controller boundary; a `continue`-reachable PipeCondition
    # without a `?` output; an unguarded template reference to a declared-optional input; a
    # required structure field fed by a maybe-absent PipeParallel branch.
    OPTIONAL_NOT_HANDLED = "optional_not_handled"
    OPTIONAL_OUTPUT_REQUIRED = "optional_output_required"
    OPTIONAL_INPUT_UNGUARDED = "optional_input_unguarded"
    OPTIONAL_BRANCH_REQUIRED_FIELD = "optional_branch_required_field"

    # Advisory-only (rides the validation report's `warnings` array, never raised as an error):
    # a `!` (force) input whose slot is guaranteed present in every analyzed flow — the
    # assertion can never fire.
    OPTIONAL_FORCE_REDUNDANT = "optional_force_redundant"

    # Blueprint parse-time concept error: a bundle declares a concept whose code collides with a
    # native Pipelex concept (`Text`, `Number`, …). Structurally suppressible — set only at the
    # single `validate_concept_keys` raise site — so the fix planner keys on it safely.
    NATIVE_CONCEPT_REDECLARATION = "native_concept_redeclaration"

    # Wiring / reference-resolution failures, detected when validating a pipe's contract against the
    # merged library (a referenced concept or dependency pipe does not resolve).
    UNRESOLVED_CONCEPT = "unresolved_concept"
    UNRESOLVED_PIPE_DEPENDENCY = "unresolved_pipe_dependency"

    # Generic fallback for unexpected validation errors
    UNKNOWN_VALIDATION_ERROR = "unknown_validation_error"

    @property
    def is_controller_input_drift(self) -> bool:
        """True for the input-drift trio the fix planner can act on when enriched."""
        match self:
            case (
                PipeValidationErrorType.MISSING_INPUT_VARIABLE
                | PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE
                | PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH
            ):
                return True
            case (
                PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT
                | PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY
                | PipeValidationErrorType.CIRCULAR_DEPENDENCY_ERROR
                | PipeValidationErrorType.LLM_OUTPUT_CANNOT_BE_IMAGE
                | PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX
                | PipeValidationErrorType.UNKNOWN_PIPE_TYPE
                | PipeValidationErrorType.MISSING_PIPE_TYPE
                | PipeValidationErrorType.BATCH_ITEM_NAME_COLLISION
                | PipeValidationErrorType.OPTIONAL_MARKER_INVALID
                | PipeValidationErrorType.OPTIONAL_NOT_HANDLED
                | PipeValidationErrorType.OPTIONAL_OUTPUT_REQUIRED
                | PipeValidationErrorType.OPTIONAL_INPUT_UNGUARDED
                | PipeValidationErrorType.OPTIONAL_BRANCH_REQUIRED_FIELD
                | PipeValidationErrorType.OPTIONAL_FORCE_REDUNDANT
                | PipeValidationErrorType.NATIVE_CONCEPT_REDECLARATION
                | PipeValidationErrorType.UNRESOLVED_CONCEPT
                | PipeValidationErrorType.UNRESOLVED_PIPE_DEPENDENCY
                | PipeValidationErrorType.UNKNOWN_VALIDATION_ERROR
            ):
                return False

    @property
    def is_inadequate_output(self) -> bool:
        """True for the output-mismatch pair the fix planner can act on when enriched."""
        match self:
            case PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT | PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY:
                return True
            case (
                PipeValidationErrorType.MISSING_INPUT_VARIABLE
                | PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE
                | PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH
                | PipeValidationErrorType.CIRCULAR_DEPENDENCY_ERROR
                | PipeValidationErrorType.LLM_OUTPUT_CANNOT_BE_IMAGE
                | PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX
                | PipeValidationErrorType.UNKNOWN_PIPE_TYPE
                | PipeValidationErrorType.MISSING_PIPE_TYPE
                | PipeValidationErrorType.BATCH_ITEM_NAME_COLLISION
                | PipeValidationErrorType.OPTIONAL_MARKER_INVALID
                | PipeValidationErrorType.OPTIONAL_NOT_HANDLED
                | PipeValidationErrorType.OPTIONAL_OUTPUT_REQUIRED
                | PipeValidationErrorType.OPTIONAL_INPUT_UNGUARDED
                | PipeValidationErrorType.OPTIONAL_BRANCH_REQUIRED_FIELD
                | PipeValidationErrorType.OPTIONAL_FORCE_REDUNDANT
                | PipeValidationErrorType.NATIVE_CONCEPT_REDECLARATION
                | PipeValidationErrorType.UNRESOLVED_CONCEPT
                | PipeValidationErrorType.UNRESOLVED_PIPE_DEPENDENCY
                | PipeValidationErrorType.UNKNOWN_VALIDATION_ERROR
            ):
                return False

    @property
    def is_inadequate_output_multiplicity(self) -> bool:
        """True only for the multiplicity-mismatch case.

        The required/provided concept-ref suffix appended by the error categorizer is suppressed
        for this case: a multiplicity mismatch has the same concept on both sides by definition
        (the concept-compatibility check passed just before it fired), so the suffix would print
        two identical refs and its list-repr brackets would masquerade as `[]` multiplicity syntax.
        """
        match self:
            case PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY:
                return True
            case (
                PipeValidationErrorType.MISSING_INPUT_VARIABLE
                | PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE
                | PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH
                | PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT
                | PipeValidationErrorType.CIRCULAR_DEPENDENCY_ERROR
                | PipeValidationErrorType.LLM_OUTPUT_CANNOT_BE_IMAGE
                | PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX
                | PipeValidationErrorType.UNKNOWN_PIPE_TYPE
                | PipeValidationErrorType.MISSING_PIPE_TYPE
                | PipeValidationErrorType.BATCH_ITEM_NAME_COLLISION
                | PipeValidationErrorType.OPTIONAL_MARKER_INVALID
                | PipeValidationErrorType.OPTIONAL_NOT_HANDLED
                | PipeValidationErrorType.OPTIONAL_OUTPUT_REQUIRED
                | PipeValidationErrorType.OPTIONAL_INPUT_UNGUARDED
                | PipeValidationErrorType.OPTIONAL_BRANCH_REQUIRED_FIELD
                | PipeValidationErrorType.OPTIONAL_FORCE_REDUNDANT
                | PipeValidationErrorType.NATIVE_CONCEPT_REDECLARATION
                | PipeValidationErrorType.UNRESOLVED_CONCEPT
                | PipeValidationErrorType.UNRESOLVED_PIPE_DEPENDENCY
                | PipeValidationErrorType.UNKNOWN_VALIDATION_ERROR
            ):
                return False

    @property
    def is_native_concept_redeclaration(self) -> bool:
        """True for the blueprint-channel native-concept redeclaration the fix planner strips."""
        match self:
            case PipeValidationErrorType.NATIVE_CONCEPT_REDECLARATION:
                return True
            case (
                PipeValidationErrorType.MISSING_INPUT_VARIABLE
                | PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE
                | PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH
                | PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT
                | PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY
                | PipeValidationErrorType.CIRCULAR_DEPENDENCY_ERROR
                | PipeValidationErrorType.LLM_OUTPUT_CANNOT_BE_IMAGE
                | PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX
                | PipeValidationErrorType.UNKNOWN_PIPE_TYPE
                | PipeValidationErrorType.MISSING_PIPE_TYPE
                | PipeValidationErrorType.BATCH_ITEM_NAME_COLLISION
                | PipeValidationErrorType.OPTIONAL_MARKER_INVALID
                | PipeValidationErrorType.OPTIONAL_NOT_HANDLED
                | PipeValidationErrorType.OPTIONAL_OUTPUT_REQUIRED
                | PipeValidationErrorType.OPTIONAL_INPUT_UNGUARDED
                | PipeValidationErrorType.OPTIONAL_BRANCH_REQUIRED_FIELD
                | PipeValidationErrorType.OPTIONAL_FORCE_REDUNDANT
                | PipeValidationErrorType.UNRESOLVED_CONCEPT
                | PipeValidationErrorType.UNRESOLVED_PIPE_DEPENDENCY
                | PipeValidationErrorType.UNKNOWN_VALIDATION_ERROR
            ):
                return False

    @property
    def is_invalid_pipe_code_syntax(self) -> bool:
        """True for the invalid-pipe-code-syntax error the fix planner strips when it is enriched.

        Gates entry to ``strip-namespace``; the planner still requires the ``stripped_pipe_code``
        enrichment, so un-strippable syntax errors (malformed codes, cross-package dotted refs)
        fall through as ``None`` even though they share this ``error_type``.
        """
        match self:
            case PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX:
                return True
            case (
                PipeValidationErrorType.MISSING_INPUT_VARIABLE
                | PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE
                | PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH
                | PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT
                | PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY
                | PipeValidationErrorType.CIRCULAR_DEPENDENCY_ERROR
                | PipeValidationErrorType.LLM_OUTPUT_CANNOT_BE_IMAGE
                | PipeValidationErrorType.UNKNOWN_PIPE_TYPE
                | PipeValidationErrorType.MISSING_PIPE_TYPE
                | PipeValidationErrorType.BATCH_ITEM_NAME_COLLISION
                | PipeValidationErrorType.OPTIONAL_MARKER_INVALID
                | PipeValidationErrorType.OPTIONAL_NOT_HANDLED
                | PipeValidationErrorType.OPTIONAL_OUTPUT_REQUIRED
                | PipeValidationErrorType.OPTIONAL_INPUT_UNGUARDED
                | PipeValidationErrorType.OPTIONAL_BRANCH_REQUIRED_FIELD
                | PipeValidationErrorType.OPTIONAL_FORCE_REDUNDANT
                | PipeValidationErrorType.NATIVE_CONCEPT_REDECLARATION
                | PipeValidationErrorType.UNRESOLVED_CONCEPT
                | PipeValidationErrorType.UNRESOLVED_PIPE_DEPENDENCY
                | PipeValidationErrorType.UNKNOWN_VALIDATION_ERROR
            ):
                return False


class PipeFactoryErrorType(StrEnum):
    """Types of pipe factory errors.

    These error types are raised during pipe creation from blueprints.
    """

    UNKNOWN_CONCEPT = "unknown_concept"

    # Generic fallback for unexpected factory errors
    UNKNOWN_FACTORY_ERROR = "unknown_factory_error"


class ValidationResidualErrorType(StrEnum):
    """The ``error_type`` of a validation residual — a failure with no stage-level error data.

    A residual is what the wire projection emits when a bundle failed but no categorized
    validation stage produced structured data to report. There is exactly one residual that names
    itself: a dry-run failure surfaces a single message from a raised ``DryRunError`` / ``PipeRunError``,
    so the item is tagged with that exception's own class name.

    The other residual — the parse-level one, for a bundle that could not be turned into a
    blueprint at all (a TOML-syntax error, an empty blueprint, an elaborator failure) — carries no
    ``error_type`` and therefore no member here. That is not an omission: it fires for several
    distinct underlying errors, and inventing one code for all of them would tell a consumer it
    knows which fault occurred when it does not. Its message is the authoritative diagnostic.
    """

    DRY_RUN_ERROR = "DryRunError"


ValidationErrorType: TypeAlias = PipeValidationErrorType | PipeFactoryErrorType | ValidationResidualErrorType
"""The type of a bundle-validation diagnostic's ``error_type``.

``ValidationErrorItem.error_type`` is typed against this alias, which is what makes the registry
*closed* rather than merely documented: a value outside these three enums cannot be constructed
onto the wire, so the enumeration below and the values a consumer actually observes cannot
disagree.
"""

VALIDATION_ERROR_TYPES: tuple[ValidationErrorType, ...] = (
    *PipeValidationErrorType,
    *PipeFactoryErrorType,
    *ValidationResidualErrorType,
)
"""Every ``error_type`` a bundle-validation diagnostic can carry, in a deterministic order.

Ordered by contributing enum, then by declaration order within it — so a generated artifact keyed
on this registry (the MTHDS Test Corpus tag vocabulary is the first) is stable across runs and a
new member shows up as one added line rather than a reshuffle.

The three enums are value-disjoint, and that is a property worth stating rather than assuming:
were two of them to share a wire value, ``error_type`` would stop identifying the fault and the
alias above would resolve it to whichever enum pydantic tried first. It is gated by
``tests/unit/pipelex/errors/test_validation_error_types.py``.

Membership says a value is *reachable on the wire*, never that it is a useful coverage target.
The advisory-only member rides the validation report's ``warnings`` array and never an invalid
verdict; the two ``unknown_*`` fallbacks fire on states no author can ask for. A consumer that
needs to exercise each fault — the corpus's ``error.*`` axis — excludes those in its own
generator, with a stated reason per exclusion, rather than pruning them from the runtime truth here.
"""
