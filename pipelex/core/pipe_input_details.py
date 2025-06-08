from typing import Any, Callable, Dict, List, Set, Tuple, Type, TypeVar

from pydantic import BaseModel, Field, RootModel, field_validator

from pipelex import log
from pipelex.exceptions import PipeInputSpecError

PipeInputDetailsRoot = Dict[str, str]


class PipeInputDetails(RootModel[PipeInputDetailsRoot]):
    root: PipeInputDetailsRoot = Field(default_factory=dict)

    @field_validator("root", mode="wrap")
    @classmethod
    def validate_concept_codes(cls, input_value: Dict[str, str], handler: Callable[[Dict[str, str]], Dict[str, str]]) -> Dict[str, str]:
        # First let Pydantic handle the basic type validation
        validated_dict: Dict[str, str] = handler(input_value)

        # Now we can transform and validate the keys and values
        transformed_dict: Dict[str, str] = {}
        for key, value in validated_dict.items():
            # in case of sub-attribute, the variable name is the object name, before the 1st dot
            transformed_key: str = key.split(".", 1)[0]
            if transformed_key != key:
                log.warning(f"Sub-attribute {key} detected, using {transformed_key} as variable name")

            # Validate value
            if not value:
                raise PipeInputSpecError(f"Invalid concept code: {value}")
            if value.count(".") > 1:
                raise PipeInputSpecError(f"Concept code {value} contains more than one dot")

            if transformed_key in transformed_dict and transformed_dict[transformed_key] != value:
                log.warning(
                    f"Variable {transformed_key} already exists with a different concept code: {transformed_dict[transformed_key]} -> {value}"
                )
            transformed_dict[transformed_key] = value

        return transformed_dict

    def set_default_domain(self, domain: str):
        for input_name, input_concept_code in self.root.items():
            if "." not in input_concept_code:
                self.root[input_name] = f"{domain}.{input_concept_code}"

    def get(self, variable_name: str) -> str:
        return self.root[variable_name]

    def add_requirement(self, variable_name: str, concept_code: str):
        self.root[variable_name] = concept_code

    @property
    def items(self) -> List[Tuple[str, str]]:
        return list(self.root.items())

    @property
    def concepts(self) -> Set[str]:
        return set(self.root.values())

    # @property
    # def variables(self) -> List[str]:
    #     return list(self.root.keys())

    @property
    def required_names(self) -> List[str]:
        the_required_names: List[str] = []
        for requirement_expression in self.root.keys():
            required_variable_name = requirement_expression.split(".", 1)[0]
            the_required_names.append(required_variable_name)
        return the_required_names

    @property
    def detailed_requirements(self) -> List[Tuple[str, str, str]]:
        the_requirements: List[Tuple[str, str, str]] = []
        for requirement_expression, concept_code in self.root.items():
            required_variable_name = requirement_expression.split(".", 1)[0]
            the_requirements.append((required_variable_name, requirement_expression, concept_code))
        return the_requirements
