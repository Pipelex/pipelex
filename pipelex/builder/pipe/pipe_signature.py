from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from pipelex.core.pipes.exceptions import PipeBlueprintError
from pipelex.core.pipes.pipe_blueprint import AllowedPipeCategories, AllowedPipeTypes
from pipelex.core.stuffs.structured_content import StructuredContent


class PipeSignature(StructuredContent):
    """PipeSignature is a contract for a pipe.

    It defines the inputs, outputs, and the purpose of the pipe without implementation details.

    Multiplicity Notation:
        Use bracket notation to specify how many items are produced, but only for the outputs:
        - No brackets: single item (default)
        - []: variable-length list
        - [N]: exactly N items (where N is a positive integer)

    Examples:
        - output = "Text[]" - produces multiple text items
        - output = "Image[3]" - produces exactly 3 images
    """

    code: str = Field(description="Pipe code identifying the pipe. Must be snake_case.")
    type: AllowedPipeTypes | str = Field(description="Pipe type.")
    pipe_category: SkipJsonSchema[AllowedPipeCategories] = Field(description="Pipe category set according to its type.")
    description: str = Field(description="What the pipe does")
    inputs: dict[str, str] = Field(
        description="Pipe inputs: keys are the input variable_names in snake_case, values are the ConceptCodes in PascalCase."
    )
    result: str = Field(
        description="variable_name for the result of the pipe. Must be snake_case. It could be referenced as input in a following pipe."
    )
    output: str = Field(description="The output ConceptCode in PascalCase, possibly with multiplicity brackets")
    pipe_dependencies: list[str] = Field(description="List of pipe codes that this pipe depends on. This is for the PipeControllers")

    @model_validator(mode="before")
    @classmethod
    def set_pipe_category(cls, values: dict[str, Any]) -> dict[str, Any]:
        try:
            type_str = values["type"]
        except TypeError as exc:
            msg = f"Invalid type for '{values}': could not get subscript, required for 'type'"
            raise PipeBlueprintError(msg) from exc
        # we need to convert the type string to the AllowedPipeTypes enum because it arrives as a str implictly converted to enum but not yet
        the_type = AllowedPipeTypes(type_str)
        values["pipe_category"] = the_type.category
        return values

    @field_validator("type", mode="before")
    @classmethod
    def validate_type(cls, type_value: str) -> AllowedPipeTypes:
        return AllowedPipeTypes(type_value)
