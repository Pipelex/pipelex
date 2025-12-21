import re
from abc import ABC
from typing import Any, final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pipelex.core.concepts.exceptions import ConceptStringError
from pipelex.core.concepts.validation import validate_concept_ref_or_code
from pipelex.core.pipes.validation import validate_input_name
from pipelex.core.pipes.variable_multiplicity import MUTLIPLICITY_PATTERN, PipeVariableMultiplicityError, parse_concept_with_multiplicity
from pipelex.types import Self, StrEnum


class PipeCategory(StrEnum):
    PIPE_OPERATOR = "PipeOperator"
    PIPE_CONTROLLER = "PipeController"

    @classmethod
    def value_list(cls) -> list[str]:
        return list(cls)

    @property
    def is_controller(self) -> bool:
        match self:
            case PipeCategory.PIPE_CONTROLLER:
                return True
            case PipeCategory.PIPE_OPERATOR:
                return False

    @classmethod
    def is_controller_by_str(cls, category_str: str) -> bool:
        try:
            category = cls(category_str)
            return category.is_controller
        except ValueError:
            return False


class PipeType(StrEnum):
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
    def category(self) -> PipeCategory:
        match self:
            case PipeType.PIPE_FUNC:
                return PipeCategory.PIPE_OPERATOR
            case PipeType.PIPE_IMG_GEN:
                return PipeCategory.PIPE_OPERATOR
            case PipeType.PIPE_COMPOSE:
                return PipeCategory.PIPE_OPERATOR
            case PipeType.PIPE_LLM:
                return PipeCategory.PIPE_OPERATOR
            case PipeType.PIPE_EXTRACT:
                return PipeCategory.PIPE_OPERATOR
            case PipeType.PIPE_BATCH:
                return PipeCategory.PIPE_CONTROLLER
            case PipeType.PIPE_CONDITION:
                return PipeCategory.PIPE_CONTROLLER
            case PipeType.PIPE_PARALLEL:
                return PipeCategory.PIPE_CONTROLLER
            case PipeType.PIPE_SEQUENCE:
                return PipeCategory.PIPE_CONTROLLER


class PipeBlueprint(ABC, BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str | None = None
    pipe_category: Any = Field(exclude=True)  # Technical field for Union discrimination, not user-facing
    type: Any  # TODO: Find a better way to handle this.
    description: str
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
        if value not in PipeType.value_list():
            msg = f"Invalid pipe type '{value}'. Must be one of: {PipeType.value_list()}"
            raise ValueError(msg)
        return value

    @field_validator("pipe_category", mode="after")
    @classmethod
    def validate_pipe_category(cls, value: Any) -> Any:
        if value not in PipeCategory.value_list():
            msg = f"Invalid pipe category '{value}'. Must be one of: {PipeCategory.value_list()}"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def validate_pipe_category_based_on_type(self) -> Self:
        try:
            pipe_type = PipeType(self.type)
        except ValueError as exc:
            # If type is invalid, it should have been caught by the field validator
            # but we handle it gracefully here
            msg = f"Invalid pipe type '{self.type}'. Must be one of: {PipeType.value_list()}"
            raise ValueError(msg) from exc

        if self.pipe_category != pipe_type.category:
            msg = (
                f"Inconsistency detected: pipe_category '{self.pipe_category}' does not match the "
                f"expected category '{pipe_type.category}' for type '{self.type}'"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def validate_inputs_blueprint(self) -> Self:
        self.generic_validate_inputs()
        self.generic_validate_output()
        return self

    def validate_inputs(self):
        pass

    def validate_output(self):
        pass

    @final
    def generic_validate_inputs(self):
        if self.inputs:
            for input_name, concept_spec in self.inputs.items():
                validate_input_name(input_name)

                # Validate the concept spec format with optional multiplicity brackets
                # Pattern allows: ConceptName, domain.ConceptName, ConceptName[], ConceptName[N]
                match = re.match(MUTLIPLICITY_PATTERN, concept_spec)
                if not match:
                    msg = (
                        f"Invalid input syntax for '{input_name}': '{concept_spec}'. "
                        f"Expected format: 'ConceptName', 'ConceptName[]', or 'ConceptName[N]' where N is an integer."
                    )
                    raise ValueError(msg)

                # Extract the concept part (without multiplicity) and validate it
                concept_ref_or_code = match.group(1)
                try:
                    validate_concept_ref_or_code(concept_ref_or_code=concept_ref_or_code)
                except ConceptStringError as exc:
                    msg = f"Invalid concept string or code '{concept_ref_or_code}' when trying to validate the input of a pipe blueprint: {exc}"
                    raise ValueError(msg) from exc

        self.validate_inputs()

    @final
    def generic_validate_output(self):
        # Strip multiplicity brackets before validating
        try:
            output_parse_result = parse_concept_with_multiplicity(self.output)
        except PipeVariableMultiplicityError as exc:
            msg = f"Invalid concept specification syntax: '{self.output}'. {exc}"
            raise ValueError(msg) from exc
        try:
            validate_concept_ref_or_code(concept_ref_or_code=output_parse_result.concept)
        except ConceptStringError as exc:
            msg = f"Invalid concept string '{output_parse_result.concept}' when trying to validate the output of a pipe blueprint: {exc}"
            raise ValueError(msg) from exc

        self.validate_output()
