from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.pipes.exceptions import PipeBlueprintError
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.tools.misc.string_utils import is_snake_case
from pipelex.types import StrEnum


class AllowedPipeCategories(StrEnum):
    PIPE_OPERATOR = "PipeOperator"
    PIPE_CONTROLLER = "PipeController"

    @classmethod
    def value_list(cls) -> list[str]:
        return list(cls)

    @property
    def is_controller(self) -> bool:
        match self:
            case AllowedPipeCategories.PIPE_CONTROLLER:
                return True
            case AllowedPipeCategories.PIPE_OPERATOR:
                return False

    @classmethod
    def is_controller_by_str(cls, category_str: str) -> bool:
        try:
            category = cls(category_str)
            return category.is_controller
        except ValueError:
            return False


class AllowedPipeTypes(StrEnum):
    # Pipe Operators
    PIPE_FUNC = "PipeFunc"
    PIPE_IMG_GEN = "PipeImgGen"
    PIPE_COMPOSE = "PipeCompose"
    PIPE_LLM = "PipeLLM"
    PIPE_EXTRACT = "PipeExtract"
    # Pipe Controller
    PIPE_BATCH = "PipeBatch"
    PIPE_CONDITION = "PipeCondition"
    PIPE_PARALLEL = "PipeParallel"
    PIPE_SEQUENCE = "PipeSequence"

    @classmethod
    def value_list(cls) -> list[str]:
        return list(cls)

    @property
    def category(self) -> AllowedPipeCategories:
        match self:
            case AllowedPipeTypes.PIPE_FUNC:
                return AllowedPipeCategories.PIPE_OPERATOR
            case AllowedPipeTypes.PIPE_IMG_GEN:
                return AllowedPipeCategories.PIPE_OPERATOR
            case AllowedPipeTypes.PIPE_COMPOSE:
                return AllowedPipeCategories.PIPE_OPERATOR
            case AllowedPipeTypes.PIPE_LLM:
                return AllowedPipeCategories.PIPE_OPERATOR
            case AllowedPipeTypes.PIPE_EXTRACT:
                return AllowedPipeCategories.PIPE_OPERATOR
            case AllowedPipeTypes.PIPE_BATCH:
                return AllowedPipeCategories.PIPE_CONTROLLER
            case AllowedPipeTypes.PIPE_CONDITION:
                return AllowedPipeCategories.PIPE_CONTROLLER
            case AllowedPipeTypes.PIPE_PARALLEL:
                return AllowedPipeCategories.PIPE_CONTROLLER
            case AllowedPipeTypes.PIPE_SEQUENCE:
                return AllowedPipeCategories.PIPE_CONTROLLER


class PipeBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str | None = None
    pipe_category: Any = Field(exclude=True)  # Technical field for Union discrimination, not user-facing
    type: Any  # TODO: Find a better way to handle this.
    description: str | None = None
    inputs: dict[str, str] | None = None
    output: str

    @property
    def pipe_dependencies(self) -> set[str]:
        """Return the set of pipe codes that this pipe depends on.

        This is overridden by PipeController subclasses to return their dependencies.
        PipeOperators have no dependencies, so return an empty set.

        Returns:
            Set of pipe codes this pipe depends on
        """
        return set()

    @property
    def ordered_pipe_dependencies(self) -> list[str] | None:
        """Return ordered dependencies if order matters (e.g., for PipeSequence steps).

        This is overridden by controllers where dependency order is significant,
        such as PipeSequence where steps should be processed in order.

        Returns:
            Ordered list of pipe codes if order matters, None otherwise
        """
        return None

    @field_validator("type", mode="after")
    @classmethod
    def validate_pipe_type(cls, value: Any) -> Any:
        """Validate that the pipe type is one of the allowed values."""
        if value not in AllowedPipeTypes.value_list():
            msg = f"Invalid pipe type '{value}'. Must be one of: {AllowedPipeTypes.value_list()}"
            raise PipeBlueprintError(msg)
        return value

    @field_validator("pipe_category", mode="after")
    @classmethod
    def validate_pipe_category(cls, value: Any) -> Any:
        """Validate that the pipe category is one of the allowed values."""
        if value not in AllowedPipeCategories.value_list():
            msg = f"Invalid pipe category '{value}'. Must be one of: {AllowedPipeCategories.value_list()}"
            raise PipeBlueprintError(msg)
        return value

    @field_validator("output", mode="before")
    @classmethod
    def validate_output(cls, output: str) -> str:
        # Strip multiplicity brackets before validating
        output_parse_result = parse_concept_with_multiplicity(output)
        ConceptBlueprint.validate_concept_string_or_code(concept_string_or_code=output_parse_result.concept)
        return output  # Return with brackets intact

    @classmethod
    def validate_pipe_code_syntax(cls, pipe_code: str) -> str:
        if not is_snake_case(pipe_code):
            msg = f"Invalid pipe code syntax '{pipe_code}'. Must be in snake_case."
            raise PipeBlueprintError(msg)
        return pipe_code
