from typing import Any, Dict, Optional, Union

from pydantic import Field, field_validator

from pipelex.core.pipes.exceptions import PipeBlueprintError
from pipelex.core.pipes.pipe_blueprint import AllowedPipeTypes
from pipelex.core.stuffs.stuff_content import StructuredContent
from pipelex.libraries.pipelines.builder.concept.concept import ConceptBlueprint, ConceptSpec
from pipelex.libraries.pipelines.builder.pipe.inputs import InputRequirementBlueprint
from pipelex.tools.misc.string_utils import is_snake_case


class PipeSignature(StructuredContent):
    code: str = Field(description="Pipe code. Must be snake_case.")
    type: AllowedPipeTypes = Field(description="Pipe type.")
    definition: str = Field(description="What the pipe does")
    inputs: Dict[str, ConceptSpec] = Field(description="Pipe inputs: key is the concept code in pascal Case.")
    output: ConceptSpec = Field(description="Concept as output")


class PipeBlueprint(StructuredContent):
    """Blueprint defining a pipe component in the Pipelex framework.

    Pipes are the fundamental processing units in Pipelex workflows. They transform
    input concepts into output concepts through various operations like LLM processing,
    image generation, OCR, or custom functions.

    Attributes:
        type: The pipe type (PipeFunc, PipeLLM, PipeImgGen, PipeOcr, PipeBatch,
              PipeCondition, PipeParallel, PipeSequence). Uses Any type to avoid
              type override conflicts but validated at runtime.
        definition: Natural language description of what the pipe does.
        inputs: Input concept specifications. Can be either:
               - A string (concept string/code in PascalCase)
               - An InputRequirementBlueprint with additional constraints
               Dictionary keys are input names, values are concept specifications.
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
    definition: Optional[str] = Field(description="Natural language description of what the pipe does.")
    inputs: Optional[Dict[str, Union[str, InputRequirementBlueprint]]] = Field(
        description=(
            "Input concept specifications. Can be either: "
            "- A string (concept string/code in PascalCase) "
            "- An InputRequirementBlueprint with additional constraints "
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
