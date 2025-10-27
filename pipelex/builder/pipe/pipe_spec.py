import re
from typing import Any

from pydantic import Field, field_validator
from typing_extensions import override

from pipelex import log, pretty_print
from pipelex.builder.concept.concept_spec import ConceptSpec
from pipelex.core.pipes.exceptions import PipeBlueprintError
from pipelex.core.pipes.pipe_blueprint import AllowedPipeCategories, AllowedPipeTypes, PipeBlueprint
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.tools.misc.json_utils import remove_none_values_from_dict
from pipelex.tools.misc.string_utils import is_snake_case, normalize_to_ascii


class PipeSpec(StructuredContent):
    """Spec defining a pipe: an executable component with a clear contract defined by its inputs and output.

    Pipes are the building blocks of a Pipelex pipeline. There are two categories:
    - Controllers: Manage execution flow (PipeSequence, PipeParallel, PipeCondition, PipeBatch)
    - Operators: Perform specific tasks (PipeLLM, PipeImgGen, PipeExtract, PipeFunc, PipeCompose)

    Multiplicity Notation:
        Both inputs and outputs use bracket notation to specify item counts:
        - No brackets: single item (default)
        - []: variable-length list (e.g., "Text[]")
        - [N]: exactly N items (e.g., "Image[3]" for 3 images)

    Examples:
        inputs = {"document": "PDF", "queries": "Text[]"}  # single PDF, multiple texts
        output = "Article[]"  # produces a list of articles
        output = "Image[5]"  # produces exactly 5 images
    """

    pipe_code: str = Field(description="Unique pipe identifier. Must be snake_case.")
    type: Any = Field(
        description=(
            f"Pipe type. Validated at runtime, must be one of: {AllowedPipeTypes}. "
            "Examples: PipeLLM, PipeImgGen, PipeExtract, PipeSequence, PipeParallel."
        )
    )
    pipe_category: Any = Field(
        description=(f"Pipe category. Validated at runtime, must be one of: {AllowedPipeCategories}. Either 'PipeController' or 'PipeOperator'.")
    )
    description: str | None = Field(description="Natural language description of the pipe's purpose and functionality.")
    inputs: dict[str, str] = Field(
        description=(
            "Input specifications mapping variable names to concept codes with optional multiplicity. "
            "Keys: input names in snake_case. "
            "Values: ConceptCodes in PascalCase with optional brackets. "
            "Examples: 'Text' (single), 'Text[]' (variable list), 'Image[2]' (exactly 2 images), 'domain.Concept[]' (domain-qualified list)."
        )
    )
    output: str = Field(
        description=(
            "Output concept code in PascalCase with optional multiplicity brackets. "
            "Examples: 'Text' (single text), 'Article[]' (list of articles), 'Image[3]' (exactly 3 images). "
            "IMPORTANT: Always use PascalCase for the concept name."
        )
    )

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
    def validate_output(cls, output: str) -> str:
        # Extract concept without multiplicity for validation
        parse_result = parse_concept_with_multiplicity(output)
        ConceptSpec.validate_concept_string_or_code(concept_string_or_code=parse_result.concept)
        return output  # Return original with brackets intact

    @field_validator("inputs", mode="after")
    @classmethod
    def validate_inputs(cls, inputs: dict[str, str] | None) -> dict[str, str] | None:
        if inputs is None:
            return None

        # Pattern allows: ConceptName, domain.ConceptName, ConceptName[], ConceptName[N]
        multiplicity_pattern = r"^([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)(?:\[(\d*)\])?$"

        for input_name, concept_spec in inputs.items():
            if not is_snake_case(input_name):
                msg = f"Invalid input name syntax '{input_name}'. Must be in snake_case."
                raise PipeBlueprintError(msg)

            # Validate the concept spec format with optional multiplicity brackets
            match = re.match(multiplicity_pattern, concept_spec)
            if not match:
                msg = (
                    f"Invalid input syntax for '{input_name}': '{concept_spec}'. "
                    f"Expected format: 'ConceptName', 'ConceptName[]', or 'ConceptName[N]' where N is an integer."
                )
                raise PipeBlueprintError(msg)

            # Extract the concept part (without multiplicity) and validate it
            concept_string_or_code = match.group(1)
            ConceptSpec.validate_concept_string_or_code(concept_string_or_code=concept_string_or_code)

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
        return PipeBlueprint(
            description=self.description,
            inputs=self.inputs if self.inputs else None,
            output=self.output,
            type=self.type,
            pipe_category=self.pipe_category,
        )

    @override
    def pretty_print_content(self, title: str | None = None, number: int | None = None) -> None:
        the_dict: dict[str, Any] = self.smart_dump()
        the_dict = remove_none_values_from_dict(data=the_dict)
        if number:
            title = f"Pipe #{number}: {self.pipe_code}"
        else:
            title = f"Pipe: {self.pipe_code}"
        title += f" • {self.type}"
        subtitle = self.description
        the_dict.pop("pipe_code")
        the_dict.pop("description")
        the_dict.pop("type")
        the_dict.pop("pipe_category")
        pretty_print(the_dict, title=title, subtitle=subtitle)
