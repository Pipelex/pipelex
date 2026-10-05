import json
from typing import Any

from pydantic import Field, RootModel

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.pipes.inputs.exceptions import InputStuffSpecNotFoundError
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import PresenceMarker, VariableMultiplicity
from pipelex.core.stuffs.stuff_content import StuffContent


class NamedStuffSpec(StuffSpec):
    variable_name: str


class TypedNamedStuffSpec(NamedStuffSpec):
    structure_class: type[StuffContent]

    @classmethod
    def make_from_named(
        cls,
        named: NamedStuffSpec,
        *,
        structure_class: type[StuffContent],
    ) -> "TypedNamedStuffSpec":
        return cls(**named.model_dump(), structure_class=structure_class)


PipeInputsRoot = dict[str, StuffSpec]


class InputStuffSpecs(RootModel[PipeInputsRoot]):
    root: PipeInputsRoot = Field(default_factory=dict)

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

    def add_stuff_spec(
        self,
        *,
        variable_name: str,
        concept: Concept,
        multiplicity: VariableMultiplicity | None = None,
        presence: PresenceMarker = PresenceMarker.PLAIN,
    ):
        self.root[variable_name] = StuffSpec(concept=concept, multiplicity=multiplicity, presence=presence)

    @property
    def items(self) -> list[tuple[str, StuffSpec]]:
        return list(self.root.items())

    def get_single_stuff_spec(self) -> StuffSpec:
        if len(self.root) != 1:
            msg = f"Expected 1 input, but got {len(self.root)}"
            raise ValueError(msg)
        return next(iter(self.root.values()))

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
    def declared_names(self) -> list[str]:
        """Every declared input name, regardless of presence marker."""
        return list(self.root)

    @property
    def required_names(self) -> list[str]:
        """Declared input names whose value is required at run time: plain and forced (`!`)
        inputs. Optional (`?`) inputs are declared but may legitimately be absent.
        """
        return [input_name for input_name, stuff_spec in self.root.items() if not stuff_spec.presence.is_optional]

    @property
    def named_stuff_specs(self) -> list[NamedStuffSpec]:
        return [
            NamedStuffSpec(
                variable_name=input_name,
                concept=stuff_spec.concept,
                multiplicity=stuff_spec.multiplicity,
                presence=stuff_spec.presence,
            )
            for input_name, stuff_spec in self.root.items()
        ]

    @property
    def is_empty(self) -> bool:
        return not bool(self.root)

    def format_for_display(self, *, indent: int = 6) -> str:
        """Format input stuff specs as a human-readable multi-line string.

        Args:
            indent: Number of spaces to indent each input line

        Returns:
            A multi-line string with one input per line, e.g.:
                  - cv: cv_screening.CV
                  - scorecard: cv_screening.Scorecard
        """
        if not self.root:
            return "(none)"
        prefix = " " * indent
        lines = [f"{prefix}- {var_name}: {stuff_spec.to_bundle_representation()}" for var_name, stuff_spec in self.root.items()]
        return "\n" + "\n".join(lines)

    def build_inputs_template(self, *, concept_provider: ConceptProviderAbstract) -> dict[str, Any]:
        """Build the inputs template dict: variable name -> example stuff representation.

        Args:
            concept_provider: Resolves each declared concept's structure class.

        Returns:
            Dictionary mapping each input variable to its generated example value
        """
        template: dict[str, Any] = {}
        for var_name, stuff_spec in self.root.items():
            template[var_name] = stuff_spec.render_stuff_spec(concept_provider=concept_provider, output_format=ConceptRepresentationFormat.JSON)
        return template

    def render_inputs(self, *, concept_provider: ConceptProviderAbstract, indent: int = 2) -> str:
        """Render a JSON representation for all stuff specs as a formatted string.

        Args:
            concept_provider: Resolves each declared concept's structure class.
            indent: Number of spaces for indentation (default: 2)

        Returns:
            Formatted JSON string with all inputs
        """
        return json.dumps(self.build_inputs_template(concept_provider=concept_provider), indent=indent, ensure_ascii=False)
