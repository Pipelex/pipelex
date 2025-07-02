from typing import Callable, Dict, List, Set, Tuple

from pydantic import Field, RootModel, field_validator
from typing_extensions import Self

from pipelex import log
from pipelex.core.concept_code_factory import ConceptCodeFactory
from pipelex.exceptions import PipeInputNotFoundError

PipeInputSpecRoot = Dict[str, str]


class PipeInputSpec(RootModel[PipeInputSpecRoot]):
    """
    A PipeInputSpec is a dictionary of variable names and their corresponding concept codes.
    It's meant to hold the required input variables declared by a pipe.
    """

    root: PipeInputSpecRoot = Field(default_factory=dict)

    @field_validator("root", mode="wrap")
    @classmethod
    def validate_concept_codes(cls, input_value: Dict[str, str], handler: Callable[[Dict[str, str]], Dict[str, str]]) -> Dict[str, str]:
        # First let Pydantic handle the basic type validation
        validated_dict: Dict[str, str] = handler(input_value)

        # Now we can transform and validate the keys and values
        transformed_dict: Dict[str, str] = {}
        for required_input, concept_str in validated_dict.items():
            # in case of sub-attribute, the variable name is the object name, before the 1st dot
            transformed_key: str = required_input.split(".", 1)[0]
            if transformed_key != required_input:
                log.verbose(f"Sub-attribute {required_input} detected, using {transformed_key} as variable name")

            # Validate concept_code
            concept_code = ConceptCodeFactory.make_concept_code_from_str(concept_str=concept_str)

            if transformed_key in transformed_dict and transformed_dict[transformed_key] != concept_code:
                log.verbose(
                    f"Variable {transformed_key} already exists with a different concept code: {transformed_dict[transformed_key]} -> {concept_str}"
                )
            transformed_dict[transformed_key] = concept_code

        return transformed_dict

    def set_default_domain(self, domain: str):
        for input_name, input_concept_code in self.root.items():
            if "." not in input_concept_code:
                self.root[input_name] = f"{domain}.{input_concept_code}"

    def get_required_concept_code(self, variable_name: str) -> str:
        concept_code = self.root.get(variable_name)
        if not concept_code:
            raise PipeInputNotFoundError(f"Variable '{variable_name}' not found in input spec")
        return concept_code

    def add_requirement(self, variable_name: str, concept_code: str):
        self.root[variable_name] = concept_code

    @classmethod
    def make_empty(cls) -> Self:
        return cls(root={})

    @classmethod
    def make_from_dict(cls, input_dict: Dict[str, str]) -> Self:
        return cls(root=input_dict)

    @property
    def items(self) -> List[Tuple[str, str]]:
        return list(self.root.items())

    @property
    def concepts(self) -> Set[str]:
        return set(self.root.values())

    @property
    def variables(self) -> List[str]:
        return list(self.root.keys())

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
