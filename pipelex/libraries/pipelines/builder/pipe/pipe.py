from typing import Any, Dict, Optional, Union

from pydantic import Field, field_validator

from pipelex.core.pipes.exceptions import PipeBlueprintError
from pipelex.core.pipes.pipe_blueprint import AllowedPipeCategories, AllowedPipeTypes
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint as PipeBlueprintCore
from pipelex.core.stuffs.stuff_content import StructuredContent
from pipelex.libraries.pipelines.builder.concept.concept import ConceptBlueprint, ConceptSpec
from pipelex.libraries.pipelines.builder.pipe.inputs import InputRequirementBlueprint
from pipelex.core.pipes.pipe_input_spec_blueprint import InputRequirementBlueprint as InputRequirementBlueprintCore
from pipelex.tools.misc.string_utils import is_snake_case


class PipeSignature(StructuredContent):
    code: str = Field(description="Pipe code. Must be snake_case.")
    type: AllowedPipeTypes = Field(description="Pipe type.")
    category: AllowedPipeCategories = Field(description="Pipe category.")
    definition: str = Field(description="What the pipe does")
    inputs: Dict[str, ConceptSpec] = Field(description="Pipe inputs: key is the concept code in pascal Case.")
    result: str = Field(description="The name of the result of the pipe. Must be snake_case. It will be used in the inputs of the next pipes.")
    output: ConceptSpec = Field(description="Concept as output")
    important_features: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Important features specific to this pipe type "
        "(e.g., referenced pipe codes for controllers, specific configuration for operators)",
    )


class PipeBlueprint(StructuredContent):
    """Blueprint defining a pipe component in the Pipelex framework.

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
        output_concept_string_or_concept_code: Output concept code in PascalCase format.
                                              Aliased as 'output' in serialization.

    Validation Rules:
        1. Pipe type: Must be one of the AllowedPipeTypes enum values.
        2. Output concept: Must be valid concept string or code in PascalCase.
        3. Input concepts: When provided, must use PascalCase for concept references.
        4. Pipe codes: When validating pipe codes, must be in snake_case format.

    Raises:
        PipeBlueprintError: When validation rules are violated.
    """

    type: Any = Field(description=f"Pipe type. Must be one of: {[AllowedPipeTypes.value for AllowedPipeTypes in AllowedPipeTypes]}")
    category: Any = Field(
        description=f"Pipe category. Must be one of: {[AllowedPipeCategories.value for AllowedPipeCategories in AllowedPipeCategories]}"
    )
    definition: Optional[str] = Field(description="Natural language description of what the pipe does.")
    inputs: Optional[Dict[str, Union[str, InputRequirementBlueprint]]] = Field(
        description=(
            "Input concept specifications. Can be either: "
            "InputRequirementBlueprint with additional constraints"
            "Dictionary keys are input names, values are concept specifications."
        )
    )
    output_concept_string_or_concept_code: str = Field(
        alias="output", description="Output concept code in PascalCase format. (is output_concept_string_or_concept_code)"
    )

    @field_validator("type", mode="after")
    def validate_pipe_type(cls, value: Any) -> Any:
        """Validate that the pipe type is one of the allowed values."""
        allowed_types = [_type.value for _type in AllowedPipeTypes]
        if value not in allowed_types:
            raise PipeBlueprintError(f"Invalid pipe type '{value}'. Must be one of: {allowed_types}")
        return value

    @field_validator("output_concept_string_or_concept_code", mode="before")
    def validate_concept_string_or_concept_code(cls, output: str) -> str:
        ConceptBlueprint.validate_concept_string_or_concept_code(concept_string_or_concept_code=output)
        return output

    @classmethod
    def validate_pipe_code_syntax(cls, pipe_code: str) -> str:
        if not is_snake_case(pipe_code):
            raise PipeBlueprintError(f"Invalid pipe code syntax '{pipe_code}'. Must be in snake_case.")
        return pipe_code

    def to_core_blueprint(self, pipe_code: str, domain: str) -> PipeBlueprintCore:
        """Convert this PipeBlueprint to the core PipeBlueprint."""
        # Convert inputs
        converted_inputs: Optional[Dict[str, Union[str, InputRequirementBlueprintCore]]] = {}
        if self.inputs:
            for input_name, input_spec in self.inputs.items():
                if isinstance(input_spec, InputRequirementBlueprint):
                    converted_inputs[input_name] = input_spec.to_core_input_requirement(domain)
                else:
                    converted_inputs[input_name] = InputRequirementBlueprintCore(concept=input_spec)


        return PipeBlueprintCore(
            definition=self.definition,
            inputs=converted_inputs,
            output=self.output_concept_string_or_concept_code,
            type=self.type,
            category=self.category,
        )
