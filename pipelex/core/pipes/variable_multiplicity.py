from __future__ import annotations

import re

from pydantic import BaseModel, Field

VariableMultiplicity = bool | int


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


def parse_concept_with_multiplicity(concept_spec: str) -> MultiplicityParseResult:
    """Parse a concept specification string to extract concept and multiplicity.

    Supported formats:
    - "ConceptName" -> (ConceptName, None)
    - "ConceptName[]" -> (ConceptName, True)
    - "ConceptName[5]" -> (ConceptName, 5)
    - "domain.ConceptName" -> (domain.ConceptName, None)
    - "domain.ConceptName[]" -> (domain.ConceptName, True)
    - "domain.ConceptName[5]" -> (domain.ConceptName, 5)

    Args:
        concept_spec: Concept specification string with optional multiplicity brackets

    Returns:
        MultiplicityParseResult with concept (without brackets) and multiplicity value

    Raises:
        ValueError: If the concept specification has invalid syntax
    """
    # Use strict pattern to validate identifier syntax
    # Concept must start with letter/underscore, optional domain prefix, optional brackets
    pattern = r"^([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)(?:\[(\d*)\])?$"
    match = re.match(pattern, concept_spec)

    if not match:
        msg = (
            f"Invalid concept specification syntax: '{concept_spec}'. "
            f"Expected format: 'ConceptName', 'ConceptName[]', 'ConceptName[N]', "
            f"'domain.ConceptName', 'domain.ConceptName[]', or 'domain.ConceptName[N]' "
            f"where concept and domain names must start with a letter or underscore."
        )
        raise ValueError(msg)

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

    return MultiplicityParseResult(concept=concept, multiplicity=multiplicity)
