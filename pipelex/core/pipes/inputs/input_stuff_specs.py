import json
from collections.abc import Callable
from typing import Any

from pydantic import Field, RootModel, field_validator

from pipelex import log
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.pipes.inputs.exceptions import InputStuffSpecNotFoundError
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.misc.string_utils import get_root_from_dotted_path


class NamedStuffSpec(StuffSpec):
    variable_name: str
    requirement_expression: str | None = None


class TypedNamedStuffSpec(NamedStuffSpec):
    structure_class: type[StuffContent]

    @classmethod
    def make_from_named(
        cls,
        named: NamedStuffSpec,
        structure_class: type[StuffContent],
    ) -> "TypedNamedStuffSpec":
        return cls(**named.model_dump(), structure_class=structure_class)


PipeInputsRoot = dict[str, StuffSpec]


class InputStuffSpecs(RootModel[PipeInputsRoot]):
    root: PipeInputsRoot = Field(default_factory=dict)

    @field_validator("root", mode="wrap")
    @classmethod
    def validate_concept_codes(
        cls,
        input_value: PipeInputsRoot,
        handler: Callable[[PipeInputsRoot], PipeInputsRoot],
    ) -> PipeInputsRoot:
        # First let Pydantic handle the basic type validation
        stuff_specs: PipeInputsRoot = handler(input_value)

        # Now we can transform and validate the keys and values
        transformed_dict: PipeInputsRoot = {}
        for input_name, stuff_spec in stuff_specs.items():
            # in case of sub-attribute, the variable name is the object name, before the 1st dot
            transformed_key: str = get_root_from_dotted_path(input_name)
            if transformed_key != input_name:
                log.verbose(f"Sub-attribute {input_name} detected, using {transformed_key} as variable name")

            if transformed_key in transformed_dict and transformed_dict[transformed_key] != stuff_spec:
                log.verbose(
                    f"Variable {transformed_key} already exists with a different concept code: {transformed_dict[transformed_key]} -> {stuff_spec}",
                )
            transformed_dict[transformed_key] = StuffSpec(concept=stuff_spec.concept, multiplicity=stuff_spec.multiplicity)

        return transformed_dict

    def set_default_domain(self, domain_code: str):
        for input_name, stuff_spec in self.root.items():
            input_concept_code = stuff_spec.concept.code
            if "." not in input_concept_code:
                stuff_spec.concept.code = f"{domain_code}.{input_concept_code}"
                self.root[input_name] = stuff_spec

    def get_required_stuff_spec(self, variable_name: str) -> StuffSpec:
        stuff_spec = self.root.get(variable_name)
        if not stuff_spec:
            msg = f"Variable '{variable_name}' not found the input stuff specs"
            raise InputStuffSpecNotFoundError(msg)
        return stuff_spec

    def is_variable_existing(self, variable_name: str) -> bool:
        return variable_name in self.root

    def add_stuff_spec(self, variable_name: str, concept: Concept, multiplicity: VariableMultiplicity | None = None):
        self.root[variable_name] = StuffSpec(concept=concept, multiplicity=multiplicity)

    @property
    def items(self) -> list[tuple[str, StuffSpec]]:
        return list(self.root.items())

    @property
    def concepts(self) -> list[Concept]:
        all_concepts: list[Concept] = []
        for stuff_spec in self.root.values():
            if stuff_spec.concept.concept_ref not in [c.concept_ref for c in all_concepts]:
                all_concepts.append(stuff_spec.concept)
        return all_concepts

    @property
    def variables(self) -> list[str]:
        return list(self.root.keys())

    @property
    def required_names(self) -> list[str]:
        the_required_names: list[str] = []
        for requirement_expression in self.root:
            required_variable_name = get_root_from_dotted_path(requirement_expression)
            the_required_names.append(required_variable_name)
        return the_required_names

    @property
    def named_stuff_specs(self) -> list[NamedStuffSpec]:
        the_named_stuff_spec: list[NamedStuffSpec] = []
        for requirement_expression, stuff_spec in self.root.items():
            required_variable_name = get_root_from_dotted_path(requirement_expression)
            the_named_stuff_spec.append(
                NamedStuffSpec(
                    variable_name=required_variable_name,
                    requirement_expression=requirement_expression,
                    concept=stuff_spec.concept,
                    multiplicity=stuff_spec.multiplicity,
                ),
            )
        return the_named_stuff_spec

    @property
    def is_empty(self) -> bool:
        return not bool(self.root)

    def generate_json_representation(self) -> dict[str, Any]:
        """Generate a JSON representation for all inputs.

        Returns:
            Dictionary with JSON representations for each input
        """
        json_inputs: dict[str, Any] = {}
        for var_name, stuff_spec in self.root.items():
            json_value, _ = stuff_spec.concept.generate_input_representation(
                output_format=ConceptRepresentationFormat.JSON,
                is_multiple=stuff_spec.is_multiple(),
            )
            json_inputs[var_name] = json_value

        return json_inputs

    def generate_json_string(self, indent: int = 2) -> str:
        """Generate a JSON representation for all inputs as a formatted string.

        Args:
            indent: Number of spaces for indentation (default: 2)

        Returns:
            Formatted JSON string
        """
        json_inputs = self.generate_json_representation()
        return json.dumps(json_inputs, indent=indent, ensure_ascii=False)
