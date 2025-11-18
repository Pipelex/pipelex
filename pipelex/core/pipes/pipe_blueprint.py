import re
from abc import ABC
from typing import Any, final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pipelex.core.concepts.exceptions import ConceptStringError
from pipelex.core.concepts.validation import validate_concept_string_or_code
from pipelex.core.pipes.exceptions import PipeBlueprintValueError
from pipelex.core.pipes.validation import validate_input_name
from pipelex.core.pipes.variable_multiplicity import MUTLIPLICITY_PATTERN, parse_concept_with_multiplicity
from pipelex.types import Self, StrEnum


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


class PipeBlueprint(ABC, BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str | None = None
    pipe_category: Any = Field(exclude=True)  # Technical field for Union discrimination, not user-facing
    type: Any  # TODO: Find a better way to handle this.
    description: str | None = None
    inputs: dict[str, str] | None = None
    output: str

    @property
    def nb_inputs(self) -> int:
        return len(self.inputs) if self.inputs else 0

    @property
    def input_names(self) -> list[str]:
        return list(self.inputs.keys()) if self.inputs else []

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
            raise ValueError(msg)
        return value

    @field_validator("pipe_category", mode="after")
    @classmethod
    def validate_pipe_category(cls, value: Any) -> Any:
        """Validate that the pipe category is one of the allowed values."""
        if value not in AllowedPipeCategories.value_list():
            msg = f"Invalid pipe category '{value}'. Must be one of: {AllowedPipeCategories.value_list()}"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def validate_inputs_blueprint(self) -> Self:
        self.validate_inputs()
        self.validate_output()
        return self

    def _validate_inputs(self):
        pass

    def _validate_output(self):
        pass

    @final
    def validate_inputs(self):
        if self.inputs is None:
            return

        # Pattern allows: ConceptName, domain.ConceptName, ConceptName[], ConceptName[N]
        multiplicity_pattern = MUTLIPLICITY_PATTERN

        for input_name, concept_spec in self.inputs.items():
            validate_input_name(input_name)

            # Validate the concept spec format with optional multiplicity brackets
            match = re.match(multiplicity_pattern, concept_spec)
            if not match:
                msg = (
                    f"Invalid input syntax for '{input_name}': '{concept_spec}'. "
                    f"Expected format: 'ConceptName', 'ConceptName[]', or 'ConceptName[N]' where N is an integer."
                )
                raise ValueError(msg)

            # Extract the concept part (without multiplicity) and validate it
            concept_string_or_code = match.group(1)
            validate_concept_string_or_code(concept_string_or_code=concept_string_or_code)

        # Check that every input_name is unique
        input_names = list(self.inputs.keys())
        if len(input_names) != len(set(input_names)):
            duplicates = [name for name in input_names if input_names.count(name) > 1]
            msg = f"Duplicate input names found: {duplicates}. Input names must be unique."
            raise ValueError(msg)

        self._validate_inputs()

    @final
    def validate_output(self):
        # Strip multiplicity brackets before validating
        output_parse_result = parse_concept_with_multiplicity(self.output)
        try:
            validate_concept_string_or_code(concept_string_or_code=output_parse_result.concept)
        except ConceptStringError as exc:
            msg = f"Invalid concept string '{output_parse_result.concept}' when trying to validate the output of a pipe blueprint: {exc}"
            raise ValueError(msg) from exc

        self._validate_output()
