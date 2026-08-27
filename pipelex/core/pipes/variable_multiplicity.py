from __future__ import annotations

import re

from mthds.protocol.pipe_io_contracts import PresenceMarker
from pydantic import BaseModel, Field

from pipelex.core.pipes.exceptions import PipeVariableMultiplicityError

__all__ = [
    "MULTIPLICITY_PATTERN",
    "MultiplicityParseResult",
    "PresenceMarker",
    "VariableMultiplicity",
    "VariableMultiplicityResolution",
    "fixed_item_count",
    "format_concept_with_multiplicity",
    "is_force_presence",
    "is_multiple_multiplicity",
    "is_multiplicity_compatible",
    "make_variable_multiplicity",
    "parse_concept_with_multiplicity",
    "presence_from_symbol",
    "presence_symbol",
]

VariableMultiplicity = bool | int

# The io-ref suffix grammar: an optional multiplicity suffix ("[]" or "[N]") followed by an
# optional presence marker ("?" optional / "!" force). Order is fixed: multiplicity then presence.
# Group 1: concept ref or code; group 2: bracket content (None / "" / digits); group 3: presence
# marker symbol (None / "?" / "!").
MULTIPLICITY_PATTERN = r"^([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)(?:\[(\d*)\])?([?!])?$"


def presence_from_symbol(*, symbol: str | None) -> PresenceMarker:
    """The presence marker an io-ref suffix symbol denotes: nothing is `plain`, `?` optional, `!` force.

    The symbol grammar is this engine's parser, not the standard's wire vocabulary, so it lives here
    beside `MULTIPLICITY_PATTERN` rather than on the enum the standard declares.
    """
    match symbol:
        case None | "":
            return PresenceMarker.PLAIN
        case "?":
            return PresenceMarker.OPTIONAL
        case "!":
            return PresenceMarker.FORCE
        case _:
            msg = f"Invalid presence marker symbol: '{symbol}'. Expected '?', '!', or nothing."
            raise PipeVariableMultiplicityError(msg)


def presence_symbol(*, presence: PresenceMarker) -> str:
    """The io-ref suffix symbol a presence marker renders as — the inverse of `presence_from_symbol`."""
    match presence:
        case PresenceMarker.PLAIN:
            return ""
        case PresenceMarker.OPTIONAL:
            return "?"
        case PresenceMarker.FORCE:
            return "!"


def is_force_presence(*, presence: PresenceMarker | None) -> bool:
    """Whether a marker is the force assertion (`!`), an unstated marker included as not forced.

    The standard's enum answers `is_optional` and `is_plain`, the two questions a wire consumer asks.
    The force assertion is the authored claim this engine's lints and blueprint checks read, so the
    third question is answered here.
    """
    return presence is PresenceMarker.FORCE


class VariableMultiplicityResolution(BaseModel):
    """Result of resolving output multiplicity settings between base and override values."""

    resolved_multiplicity: VariableMultiplicity | None = Field(description="The final multiplicity value to use after resolution")
    is_multiple_outputs_enabled: bool = Field(description="Whether multiple values should be expected/generated")
    specific_output_count: int | None = Field(default=None, description="Exact number of items to expect/generate, if specified")


def make_variable_multiplicity(*, nb_items: int | None, multiple_items: bool | None) -> VariableMultiplicity | None:
    """This function takes two mutually exclusive parameters that control how many items a variable can have
    and converts them into a single VariableMultiplicity type.

    Args:
        nb_items: Specific number of outputs to generate. If provided and truthy,
                  takes precedence over multiple_output.
        multiple_items: Boolean flag indicating whether to generate multiple outputs.
                        If True, lets the LLM decide how many outputs to generate.

    Examples:
        >>> make_variable_multiplicity(nb_items=3, multiple_items=None)
        3
        >>> make_variable_multiplicity(nb_items=None, multiple_items=True)
        True
        >>> make_variable_multiplicity(nb_items=None, multiple_items=False)
        None
        >>> make_variable_multiplicity(nb_items=0, multiple_items=True)
        True

    """
    variable_multiplicity: VariableMultiplicity | None
    if nb_items:
        variable_multiplicity = nb_items
    elif multiple_items:
        variable_multiplicity = True
    else:
        variable_multiplicity = None
    return variable_multiplicity


def is_multiple_multiplicity(*, multiplicity: VariableMultiplicity | None) -> bool:
    """Whether a multiplicity denotes a list of items.

    True for a variable-length list (`[]`) and for a fixed count above one (`[N]`, N > 1).
    A fixed count of exactly one (`[1]`) stays single: no list framing.
    """
    if multiplicity is None:
        return False
    if isinstance(multiplicity, bool):
        return multiplicity
    return multiplicity > 1


def fixed_item_count(*, multiplicity: VariableMultiplicity | None) -> int | None:
    """The exact item count when the multiplicity is a fixed count above one, else None.

    Both a variable-length list (`True`) and a single item (`None` or `[1]`) report None —
    only a genuine fixed-length list carries a count. The bool check must come first:
    `True` is an `int` in Python and would otherwise read as a count of 1.
    """
    if multiplicity is None or isinstance(multiplicity, bool):
        return None
    return multiplicity if multiplicity > 1 else None


class MultiplicityParseResult(BaseModel):
    concept_ref_or_code: str
    multiplicity: int | bool | None
    presence: PresenceMarker = PresenceMarker.PLAIN


def parse_concept_with_multiplicity(concept_ref_or_code: str) -> MultiplicityParseResult:
    """Parse a concept specification string to extract concept, multiplicity, and presence.

    Supported formats:
    - "ConceptName" -> (ConceptName, None, plain)
    - "ConceptName[]" -> (ConceptName, True, plain)
    - "ConceptName[5]" -> (ConceptName, 5, plain)
    - "ConceptName?" -> (ConceptName, None, optional)
    - "ConceptName!" -> (ConceptName, None, force)
    - "domain.ConceptName" and any of the suffixes above on a qualified ref

    The parser accepts multiplicity + presence combinations ("ConceptName[]?") so that callers with
    context (blueprint input vs output validation) can reject them with a precise, typed error; the
    D1 v1 rule that markers are mutually exclusive with multiplicity is NOT enforced here.

    Args:
        concept_ref_or_code: Concept specification string with optional multiplicity brackets
            and optional presence marker (order fixed: multiplicity then presence)

    Returns:
        MultiplicityParseResult with concept (without suffixes), multiplicity, and presence

    Raises:
        PipeVariableMultiplicityError: If the concept specification has invalid syntax
            or if multiplicity is zero or negative (a pipe must produce at least one output)
    """
    match = re.match(MULTIPLICITY_PATTERN, concept_ref_or_code)

    if not match:
        msg = (
            f"Invalid concept specification syntax: '{concept_ref_or_code}'. "
            f"Expected format: 'ConceptName' or 'domain.ConceptName' with an optional multiplicity "
            f"suffix ('[]' or '[N]') and/or an optional presence marker ('?' or '!') after it, "
            f"where concept and domain names must start with a letter or underscore."
        )
        raise PipeVariableMultiplicityError(msg)

    extracted_concept = match.group(1)
    bracket_content = match.group(2)
    marker_symbol = match.group(3)

    multiplicity: int | bool | None
    if bracket_content is None:
        # No brackets - single item
        multiplicity = None
    elif bracket_content == "":
        # Empty brackets [] - variable list
        multiplicity = True
    else:
        # Number in brackets [N] - fixed count
        multiplicity = int(bracket_content)
        if multiplicity <= 0:
            msg = f"Invalid multiplicity value in '{concept_ref_or_code}': multiplicity must be at least 1. A pipe must produce at least one output."
            raise PipeVariableMultiplicityError(msg)

    return MultiplicityParseResult(
        concept_ref_or_code=extracted_concept,
        multiplicity=multiplicity,
        presence=presence_from_symbol(symbol=marker_symbol),
    )


def is_multiplicity_compatible(*, source_multiplicity: VariableMultiplicity | None, target_multiplicity: VariableMultiplicity | None) -> bool:
    """Check if a source multiplicity is compatible with a target multiplicity.

    This is used to validate that a pipe's output multiplicity can fulfill a required output multiplicity.
    For example, when validating a PipeSequence, the last step's output multiplicity (source) must be
    compatible with the sequence's declared output multiplicity (target).

    Compatibility rules:
    - If target is None (single item), source must also be None
    - If target is True (variable list), source can be True OR any positive integer
      (a fixed count is compatible with a variable-length expectation)
    - If target is an integer N (fixed count), source must be exactly N

    Args:
        source_multiplicity: The actual multiplicity provided (e.g., from a sub-pipe's output)
        target_multiplicity: The required/expected multiplicity (e.g., declared on a sequence)

    Returns:
        True if source_multiplicity can fulfill target_multiplicity, False otherwise

    Examples:
        >>> is_multiplicity_compatible(source_multiplicity=None, target_multiplicity=None)
        True
        >>> is_multiplicity_compatible(source_multiplicity=True, target_multiplicity=True)
        True
        >>> is_multiplicity_compatible(source_multiplicity=3, target_multiplicity=True)  # Fixed count fulfills variable expectation
        True
        >>> is_multiplicity_compatible(source_multiplicity=True, target_multiplicity=3)  # Variable cannot fulfill fixed expectation
        False
        >>> is_multiplicity_compatible(source_multiplicity=3, target_multiplicity=3)
        True
        >>> is_multiplicity_compatible(source_multiplicity=3, target_multiplicity=5)  # Different fixed counts are incompatible
        False
        >>> is_multiplicity_compatible(source_multiplicity=None, target_multiplicity=True)  # Single cannot fulfill list expectation
        False
    """
    # Case 1: Target expects single item (None)
    if target_multiplicity is None:
        return source_multiplicity is None

    # Case 2: Target expects variable-length list (True)
    if target_multiplicity is True:
        # Accept True (variable) or any integer (fixed count)
        # Both represent "multiple items", just with different specificity
        # Note: We must explicitly check for bool first because bool is a subclass of int in Python
        # isinstance(False, int) returns True, which would incorrectly match False as a valid multiplicity
        return source_multiplicity is True or (isinstance(source_multiplicity, int) and not isinstance(source_multiplicity, bool))

    # Case 3: Target expects fixed count (integer)
    # Source must match exactly, but must not be a boolean
    # Note: We must explicitly check for bool first because bool is a subclass of int in Python
    # True == 1 evaluates to True, which would incorrectly match True (variable list) as compatible with 1 (fixed count)
    if isinstance(source_multiplicity, bool):
        return False
    return source_multiplicity == target_multiplicity


def format_concept_with_multiplicity(
    concept_code_or_string: str,
    *,
    multiplicity: VariableMultiplicity | None,
    presence: PresenceMarker = PresenceMarker.PLAIN,
) -> str:
    """Format a concept code or string with multiplicity and presence notation.

    This is the reverse operation of parse_concept_with_multiplicity.

    Args:
        concept_code_or_string: The concept code or string (e.g., "ConceptName" or "domain.ConceptName")
        multiplicity: The multiplicity value:
            - None: single item (no brackets)
            - True: variable-length list (empty brackets [])
            - int: fixed-length list (brackets with number [N])
        presence: The presence marker, rendered after the multiplicity suffix ("" / "?" / "!")

    Returns:
        Formatted concept specification string with multiplicity and presence notation

    Examples:
        >>> format_concept_with_multiplicity("Text", multiplicity=None)
        "Text"
        >>> format_concept_with_multiplicity("Text", multiplicity=True)
        "Text[]"
        >>> format_concept_with_multiplicity("Text", multiplicity=3)
        "Text[3]"
        >>> format_concept_with_multiplicity("Text", multiplicity=None, presence=PresenceMarker.OPTIONAL)
        "Text?"
        >>> format_concept_with_multiplicity("domain.Text", multiplicity=None, presence=PresenceMarker.FORCE)
        "domain.Text!"
    """
    multiplicity_suffix: str
    if multiplicity is None:
        # Single item - no brackets
        multiplicity_suffix = ""
    elif multiplicity is True:
        # Variable-length list - empty brackets
        multiplicity_suffix = "[]"
    else:
        # Fixed-length list - brackets with number
        multiplicity_suffix = f"[{multiplicity}]"
    return f"{concept_code_or_string}{multiplicity_suffix}{presence_symbol(presence=presence)}"
