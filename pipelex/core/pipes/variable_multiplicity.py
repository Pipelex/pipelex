from __future__ import annotations

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
