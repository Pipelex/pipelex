from collections.abc import Callable

from pydantic import BaseModel, Field, RootModel, field_validator

from pipelex import log
from pipelex.core.concepts.concept import Concept
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.exceptions import PipeInputNotFoundError
from pipelex.pipe_run.pipe_run_params import PipeOutputMultiplicity


class InputRequirement(BaseModel):
    concept: Concept
    multiplicity: PipeOutputMultiplicity | None = None


class NamedInputRequirement(InputRequirement):
    variable_name: str
    requirement_expression: str | None = None


class TypedNamedInputRequirement(NamedInputRequirement):
    structure_class: type[StuffContent]

    @classmethod
    def make_from_named(
        cls,
        named: NamedInputRequirement,
        structure_class: type[StuffContent],
    ) -> "TypedNamedInputRequirement":
        return cls(**named.model_dump(), structure_class=structure_class)


InputRequirementsRoot = dict[str, InputRequirement]


class InputRequirements(RootModel[InputRequirementsRoot]):
    root: InputRequirementsRoot = Field(default_factory=dict)

    @field_validator("root", mode="wrap")
    @classmethod
    def validate_concept_codes(
        cls,
        input_value: dict[str, InputRequirement],
        handler: Callable[[dict[str, InputRequirement]], dict[str, InputRequirement]],
    ) -> dict[str, InputRequirement]:
        # First let Pydantic handle the basic type validation
        validated_dict: dict[str, InputRequirement] = handler(input_value)

        # Now we can transform and validate the keys and values
        transformed_dict: dict[str, InputRequirement] = {}
        for required_input, requirement in validated_dict.items():
            # in case of sub-attribute, the variable name is the object name, before the 1st dot
            transformed_key: str = required_input.split(".", 1)[0]
            if transformed_key != required_input:
                log.verbose(f"Sub-attribute {required_input} detected, using {transformed_key} as variable name")

            if transformed_key in transformed_dict and transformed_dict[transformed_key] != requirement:
                log.verbose(
                    f"Variable {transformed_key} already exists with a different concept code: {transformed_dict[transformed_key]} -> {requirement}",
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
            msg = f"Variable '{variable_name}' not found in input spec"
            raise PipeInputNotFoundError(msg)
        return requirement

    def add_requirement(self, variable_name: str, concept: Concept, multiplicity: PipeOutputMultiplicity | None = None):
        self.root[variable_name] = InputRequirement(concept=concept, multiplicity=multiplicity)

    @property
    def items(self) -> list[tuple[str, InputRequirement]]:
        return list(self.root.items())

    @property
    def concepts(self) -> list[Concept]:
        all_concepts: list[Concept] = []
        for requirement in self.root.values():
            if requirement.concept.concept_string not in [c.concept_string for c in all_concepts]:
                all_concepts.append(requirement.concept)
        return all_concepts

    @property
    def variables(self) -> list[str]:
        return list(self.root.keys())

    @property
    def required_names(self) -> list[str]:
        the_required_names: list[str] = []
        for requirement_expression in self.root:
            required_variable_name = requirement_expression.split(".", 1)[0]
            the_required_names.append(required_variable_name)
        return the_required_names

    @property
    def named_input_requirements(self) -> list[NamedInputRequirement]:
        the_requirements: list[NamedInputRequirement] = []
        for requirement_expression, requirement in self.root.items():
            required_variable_name = requirement_expression.split(".", 1)[0]
            # TODO: refactor this with a proper class like InputRequirement
            the_requirements.append(
                NamedInputRequirement(
                    variable_name=required_variable_name,
                    requirement_expression=requirement_expression,
                    concept=requirement.concept,
                    multiplicity=requirement.multiplicity,
                ),
            )
        return the_requirements

    @property
    def nb_inputs(self) -> int:
        return len(self.root)
