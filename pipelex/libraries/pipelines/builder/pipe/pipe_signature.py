from typing import Any

from pydantic import Field, field_validator

from pipelex.core.pipes.exceptions import PipeBlueprintError
from pipelex.core.pipes.pipe_blueprint import AllowedPipeCategories, AllowedPipeTypes, PipeBlueprint
from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.core.stuffs.stuff_content import StructuredContent
from pipelex.libraries.pipelines.builder.concept.concept_spec import ConceptBlueprint, ConceptSpecDraft
from pipelex.libraries.pipelines.builder.pipe.inputs_spec import InputRequirementSpec
from pipelex.tools.misc.string_utils import is_snake_case


class PipeSignature(StructuredContent):
    code: str = Field(description="Pipe code. Must be snake_case.")
    type: AllowedPipeTypes = Field(description="Pipe type.")
    category: AllowedPipeCategories = Field(description="Pipe category.")
    definition: str = Field(description="What the pipe does")
    inputs: dict[str, ConceptSpecDraft] = Field(description="Pipe inputs: key is the concept code in pascal Case.")
    result: str = Field(description="The name of the result of the pipe. Must be snake_case. It will be used in the inputs of the next pipes.")
    output: ConceptSpecDraft = Field(description="Concept as output")
    important_features: dict[str, Any] | None = Field(
        default=None,
        description="Important features specific to this pipe type "
        "(e.g., referenced pipe codes for controllers, specific configuration for operators)",
    )


class PipeSpec(StructuredContent):
    """Spec defining a pipe component in the Pipelex framework.

    Pipes are the fundamental processing units in Pipelex workflows. They transform
    input concepts into output concepts through various operations like LLM processing,
    image generation, OCR, or custom functions.

    Attributes:
        type: The pipe type (PipeFunc, PipeLLM, PipeImgGen, PipeOcr, PipeBatch,
              PipeCondition, PipeParallel, PipeSequence). Uses Any type to avoid
              type override conflicts but validated at runtime.
        category: The pipe category (PipeOperator, PipeController). Uses Any type to avoid
              category override conflicts but validated at runtime.
              The pipe controllers are PipeSequence, PipeParallel, PipeCondition, PipeBatch.
              The pipe operators are PipeFunc, PipeLLM, PipeImgGen, PipeOcr, PipeJinja2.
        definition: Natural language description of what the pipe does.
        inputs: Input concept specifications. should be an InputRequirementBlueprint
               Dictionary keys are input names in snake_case, values are concept specifications in PascalCase.
        output: Output concept code in PascalCase format.

    Validation Rules:
        1. Pipe type: Must be one of the AllowedPipeTypes enum values.
        2. Output concept: Must be valid concept string or code in PascalCase.
        3. Input concepts: When provided, must use PascalCase for concept references.
        4. Pipe codes: When validating pipe codes, must be in snake_case format.

    """

    type: Any = Field(description=f"Pipe type. Must be one of: {AllowedPipeTypes}")
    category: Any = Field(description=f"Pipe category. Must be one of: {AllowedPipeCategories}")
    definition: str | None = Field(description="Natural language description of what the pipe does.")
    inputs: dict[str, str | InputRequirementSpec] | None = Field(
        description=(
            "Input concept specifications. Can be either: "
            "InputRequirementSpec with additional constraints"
            "Dictionary keys are input names, values are concept specifications. If Its the concept itself, use the concept code in PascalCase."
        ),
    )
    output: str = Field(description="Output concept code in PascalCase format!! Very important")

    @field_validator("type", mode="after")
    @staticmethod
    def validate_pipe_type(value: Any) -> Any:
        if value not in AllowedPipeTypes.value_list():
            msg = f"Invalid pipe type '{value}'. Must be one of: {AllowedPipeTypes.value_list()}"
            raise PipeBlueprintError(msg)
        return value

    @field_validator("output", mode="before")
    @staticmethod
    def validate_concept_string_or_code(output: str) -> str:
        ConceptBlueprint.validate_concept_string_or_code(concept_string_or_code=output)
        return output

    @classmethod
    def validate_pipe_code_syntax(cls, pipe_code: str) -> str:
        if not is_snake_case(pipe_code):
            msg = f"Invalid pipe code syntax '{pipe_code}'. Must be in snake_case."
            raise PipeBlueprintError(msg)
        return pipe_code

    def to_blueprint(self) -> PipeBlueprint:
        converted_inputs: dict[str, str | InputRequirementBlueprint] | None = None
        if self.inputs is not None:
            converted_inputs = {}
            for input_name, input_spec in self.inputs.items():
                if isinstance(input_spec, InputRequirementSpec):
                    converted_inputs[input_name] = input_spec.to_blueprint()
                else:
                    converted_inputs[input_name] = InputRequirementBlueprint(concept=input_spec)

        return PipeBlueprint(
            definition=self.definition,
            inputs=converted_inputs,
            output=self.output,
            type=self.type,
            category=self.category,
        )
