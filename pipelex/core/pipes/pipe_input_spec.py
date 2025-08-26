from typing import Callable, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel, Field, RootModel, field_validator

from pipelex import log
from pipelex.core.concepts.concept import Concept
from pipelex.core.pipes.pipe_run_params import PipeOutputMultiplicity
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.exceptions import PipeInputNotFoundError


class InputRequirement(BaseModel):
    concept: Concept
    multiplicity: Optional[PipeOutputMultiplicity] = None


class NamedInputRequirement(InputRequirement):
    variable_name: str
    requirement_expression: Optional[str] = None


class TypedNamedInputRequirement(NamedInputRequirement):
    structure_class: Type[StuffContent]

    @classmethod
    def make_from_named(
        cls,
        named: NamedInputRequirement,
        structure_class: Type[StuffContent],
    ) -> "TypedNamedInputRequirement":
        return cls(**named.model_dump(), structure_class=structure_class)


PipeInputSpecRoot = Dict[str, InputRequirement]


class PipeInputSpec(RootModel[PipeInputSpecRoot]):
    """
    A PipeInputSpec is a dictionary of variable names and their corresponding concept codes.
    It's meant to hold the required input variables declared by a pipe.
    """

    root: PipeInputSpecRoot = Field(default_factory=dict)

    @field_validator("root", mode="wrap")
    @classmethod
    def validate_concept_codes(
        cls,
        input_value: Dict[str, InputRequirement],
        handler: Callable[[Dict[str, InputRequirement]], Dict[str, InputRequirement]],
    ) -> Dict[str, InputRequirement]:
        # First let Pydantic handle the basic type validation
        validated_dict: Dict[str, InputRequirement] = handler(input_value)

        # Now we can transform and validate the keys and values
        transformed_dict: Dict[str, InputRequirement] = {}
        for required_input, requirement in validated_dict.items():
            # in case of sub-attribute, the variable name is the object name, before the 1st dot
            transformed_key: str = required_input.split(".", 1)[0]
            if transformed_key != required_input:
                log.verbose(f"Sub-attribute {required_input} detected, using {transformed_key} as variable name")

            if transformed_key in transformed_dict and transformed_dict[transformed_key] != requirement:
                log.verbose(
                    f"Variable {transformed_key} already exists with a different concept code: {transformed_dict[transformed_key]} -> {requirement}"
                )
            transformed_dict[transformed_key] = InputRequirement(concept=requirement.concept, multiplicity=requirement.multiplicity)

        return transformed_dict

    def set_default_domain(self, domain: str):
        for input_name, requirement in self.root.items():
            input_concept_code = requirement.concept.code
            if "." not in input_concept_code:
                requirement.concept.code = f"{domain}.{input_concept_code}"
                self.root[input_name] = requirement

    def get_required_input_requirement(self, variable_name: str) -> InputRequirement:
        requirement = self.root.get(variable_name)
        if not requirement:
            raise PipeInputNotFoundError(f"Variable '{variable_name}' not found in input spec")
        return requirement

    def add_requirement(self, variable_name: str, concept: Concept, multiplicity: Optional[PipeOutputMultiplicity] = None):
        self.root[variable_name] = InputRequirement(concept=concept, multiplicity=multiplicity)

    @property
    def items(self) -> List[Tuple[str, InputRequirement]]:
        return list(self.root.items())

    @property
    def concepts(self) -> List[Concept]:
        all_concepts: List[Concept] = []
        for requirement in self.root.values():
            if requirement.concept.concept_string not in [c.concept_string for c in all_concepts]:
                all_concepts.append(requirement.concept)
        return all_concepts

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
    def named_input_requirements(self) -> List[NamedInputRequirement]:
        the_requirements: List[NamedInputRequirement] = []
        for requirement_expression, requirement in self.root.items():
            required_variable_name = requirement_expression.split(".", 1)[0]
            # TODO: refactor this with a proper class like InputRequirement
            the_requirements.append(
                NamedInputRequirement(
                    variable_name=required_variable_name,
                    requirement_expression=requirement_expression,
                    concept=requirement.concept,
                    multiplicity=requirement.multiplicity,
                )
            )
        return the_requirements
