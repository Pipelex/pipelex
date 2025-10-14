from typing import Any, Literal

from pydantic import Field, field_validator

from pipelex import log
from pipelex.builder.concept.concept_spec import ConceptSpec
from pipelex.core.pipes.exceptions import PipeBlueprintError
from pipelex.core.pipes.input_requirement_blueprint import InputRequirementBlueprint
from pipelex.core.pipes.pipe_blueprint import AllowedPipeCategories, AllowedPipeTypes, PipeBlueprint
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.tools.misc.string_utils import is_snake_case, normalize_to_ascii


class PipeSignature(StructuredContent):
    """PipeSignature is a contract for a pipe.
    It defines the inputs, outputs, and the purpose of the pipe.
    It doesn't go into the details of how it does it.
    """

    code: str = Field(description="Pipe code identifying the pipe. Must be snake_case.")
    type: AllowedPipeTypes = Field(description="Pipe type.")
    pipe_category: Literal["PipeSignature"] = "PipeSignature"
    description: str = Field(description="What the pipe does")
    inputs: dict[str, str] = Field(
        description="Pipe inputs: keys are the input variable_names in snake_case, values are the ConceptCodes in PascalCase."
    )
    result: str = Field(
        description="variable_name for the result of the pipe. Must be snake_case. It could be referenced as input in a following pipe."
    )
    output: str = Field(description="Just the output ConceptCode in PascalCase")
    pipe_dependencies: list[str] = Field(description="List of pipe codes that this pipe depends on. This is for the PipeControllers")


class PipeSpec(StructuredContent):
    """Spec defining a pipe: an executable component with a clear contract defined by its inputs and output.
    There are two categories of pipes: controllers and operators.
    Controllers are used to control the flow of the pipeline, and operators are used to perform specific tasks.
    """

    pipe_code: str = Field(description="Pipe code. Must be snake_case.")
    type: Any = Field(description=f"Pipe type. It is defined with type `Any` but validated at runtime and it must be one of: {AllowedPipeTypes}")
    pipe_category: Any = Field(
        description=f"Pipe category. It is defined with type `Any` but validated at runtime and it must be one of: {AllowedPipeCategories}"
    )
    description: str | None = Field(description="Natural language description of what the pipe does.")
    inputs: dict[str, str] = Field(
        description=("Input concept specifications. The keys are input names in snake_case. Each value must be a ConceptCode in PascalCase"),
    )
    output: str = Field(description="Output concept code in PascalCase format!! Very important")

    @field_validator("pipe_code", mode="before")
    @classmethod
    def validate_pipe_code(cls, value: str) -> str:
        return cls.validate_pipe_code_syntax(value)

    @field_validator("type", mode="after")
    @classmethod
    def validate_pipe_type(cls, value: Any) -> Any:
        if value not in AllowedPipeTypes.value_list():
            msg = f"Invalid pipe type '{value}'. Must be one of: {AllowedPipeTypes.value_list()}"
            raise PipeBlueprintError(msg)
        return value

    @field_validator("output", mode="after")
    @classmethod
    def validate_concept_string_or_code(cls, output: str) -> str:
        ConceptSpec.validate_concept_string_or_code(concept_string_or_code=output)
        return output

    @field_validator("inputs", mode="after")
    @classmethod
    def validate_inputs(cls, inputs: dict[str, str] | None) -> dict[str, str] | None:
        if inputs is None:
            return None
        for input_name, concept_code in inputs.items():
            if not is_snake_case(input_name):
                msg = f"Invalid input name syntax '{input_name}'. Must be in snake_case."
                raise PipeBlueprintError(msg)
            ConceptSpec.validate_concept_string_or_code(concept_string_or_code=concept_code)
        return inputs

    @classmethod
    def validate_pipe_code_syntax(cls, pipe_code: str) -> str:
        # First, normalize Unicode to ASCII to prevent homograph attacks
        normalized_pipe_code = normalize_to_ascii(pipe_code)

        if normalized_pipe_code != pipe_code:
            log.warning(f"Pipe code '{pipe_code}' contained non-ASCII characters, normalized to '{normalized_pipe_code}'")

        if not is_snake_case(normalized_pipe_code):
            msg = f"Invalid pipe code syntax '{normalized_pipe_code}'. Must be in snake_case."
            raise PipeBlueprintError(msg)
        return normalized_pipe_code

    def to_blueprint(self) -> PipeBlueprint:
        converted_inputs: dict[str, str | InputRequirementBlueprint] | None
        if not self.inputs:
            converted_inputs = None
        else:
            converted_inputs = {}
            for input_name, concept_code in self.inputs.items():
                converted_inputs[input_name] = InputRequirementBlueprint(concept=concept_code)

        return PipeBlueprint(
            description=self.description,
            inputs=converted_inputs,
            output=self.output,
            type=self.type,
            pipe_category=self.pipe_category,
        )
