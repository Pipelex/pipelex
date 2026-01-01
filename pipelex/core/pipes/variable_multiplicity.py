from __future__ import annotations

import re

from pydantic import BaseModel, Field

from pipelex.core.pipes.exceptions import PipeVariableMultiplicityError

VariableMultiplicity = bool | int

MUTLIPLICITY_PATTERN = r"^([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)(?:\[(\d*)\])?$"


class VariableMultiplicityResolution(BaseModel):
    """Result of resolving output multiplicity settings between base and override values."""

    resolved_multiplicity: VariableMultiplicity | None = Field(description="The final multiplicity value to use after resolution")
    is_multiple_outputs_enabled: bool = Field(description="Whether multiple values should be expected/generated")
    specific_output_count: int | None = Field(default=None, description="Exact number of items to expect/generate, if specified")


def make_variable_multiplicity(nb_items: int | None, multiple_items: bool | None) -> VariableMultiplicity | None:
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


class MultiplicityParseResult:
    """Result of parsing a concept string with multiplicity notation."""

    def __init__(self, concept: str, multiplicity: int | bool | None):
        self.concept: str = concept
        self.multiplicity: int | bool | None = multiplicity


def parse_concept_with_multiplicity(concept_ref: str) -> MultiplicityParseResult:
    """Parse a concept specification string to extract concept and multiplicity.

    Supported formats:
    - "ConceptName" -> (ConceptName, None)
    - "ConceptName[]" -> (ConceptName, True)
    - "ConceptName[5]" -> (ConceptName, 5)
    - "domain.ConceptName" -> (domain.ConceptName, None)
    - "domain.ConceptName[]" -> (domain.ConceptName, True)
    - "domain.ConceptName[5]" -> (domain.ConceptName, 5)

    Args:
        concept_ref: Concept specification string with optional multiplicity brackets

    Returns:
        MultiplicityParseResult with concept (without brackets) and multiplicity value

    Raises:
        PipeVariableMultiplicityError: If the concept specification has invalid syntax
            or if multiplicity is zero or negative (a pipe must produce at least one output)
    """
    # Use strict pattern to validate identifier syntax
    # Concept must start with letter/underscore, optional domain prefix, optional brackets
    pattern = r"^([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)(?:\[(\d*)\])?$"
    match = re.match(pattern, concept_ref)

    if not match:
        msg = (
            f"Invalid concept specification syntax: '{concept_ref}'. "
            f"Expected format: 'ConceptName', 'ConceptName[]', 'ConceptName[N]', "
            f"'domain.ConceptName', 'domain.ConceptName[]', or 'domain.ConceptName[N]' "
            f"where concept and domain names must start with a letter or underscore."
        )
        raise PipeVariableMultiplicityError(msg)

    concept = match.group(1)
    bracket_content = match.group(2)

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
            msg = f"Invalid multiplicity value in '{concept_ref}': multiplicity must be at least 1. A pipe must produce at least one output."
            raise PipeVariableMultiplicityError(msg)

    return MultiplicityParseResult(concept=concept, multiplicity=multiplicity)


def is_multiplicity_compatible(source_multiplicity: VariableMultiplicity | None, target_multiplicity: VariableMultiplicity | None) -> bool:
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
        >>> is_multiplicity_compatible(None, None)
        True
        >>> is_multiplicity_compatible(True, True)
        True
        >>> is_multiplicity_compatible(3, True)  # Fixed count fulfills variable expectation
        True
        >>> is_multiplicity_compatible(True, 3)  # Variable cannot fulfill fixed expectation
        False
        >>> is_multiplicity_compatible(3, 3)
        True
        >>> is_multiplicity_compatible(3, 5)  # Different fixed counts are incompatible
        False
        >>> is_multiplicity_compatible(None, True)  # Single cannot fulfill list expectation
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


def format_concept_with_multiplicity(concept_code_or_string: str, multiplicity: VariableMultiplicity | None) -> str:
    """Format a concept code or string with multiplicity notation.

    This is the reverse operation of parse_concept_with_multiplicity.

    Args:
        concept_code_or_string: The concept code or string (e.g., "ConceptName" or "domain.ConceptName")
        multiplicity: The multiplicity value:
            - None: single item (no brackets)
            - True: variable-length list (empty brackets [])
            - int: fixed-length list (brackets with number [N])

    Returns:
        Formatted concept specification string with multiplicity notation

    Examples:
        >>> format_concept_with_multiplicity("Text", None)
        "Text"
        >>> format_concept_with_multiplicity("Text", True)
        "Text[]"
        >>> format_concept_with_multiplicity("Text", 3)
        "Text[3]"
        >>> format_concept_with_multiplicity("domain.Text", None)
        "domain.Text"
        >>> format_concept_with_multiplicity("domain.Text", True)
        "domain.Text[]"
        >>> format_concept_with_multiplicity("domain.Text", 5)
        "domain.Text[5]"
    """
    if multiplicity is None:
        # Single item - no brackets
        return concept_code_or_string
    elif multiplicity is True:
        # Variable-length list - empty brackets
        return f"{concept_code_or_string}[]"
    else:
        # Fixed-length list - brackets with number
        return f"{concept_code_or_string}[{multiplicity}]"
