import re
from typing import TYPE_CHECKING

from pipelex.base_exceptions import PipelexError
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.exceptions import ConceptStringError
from pipelex.core.concepts.validation import validate_concept_ref_or_code
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs, PipeInputsRoot
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.hub import get_required_concept

if TYPE_CHECKING:
    from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity


class InputStuffSpecsFactoryError(PipelexError):
    pass


class InputStuffSpecsFactory:
    @classmethod
    def make_empty(cls) -> InputStuffSpecs:
        return InputStuffSpecs(root={})

    @classmethod
    def make_from_blueprint(
        cls,
        domain_code: str,
        blueprint: dict[str, str],
    ) -> InputStuffSpecs:
        stuff_specs: PipeInputsRoot = {}
        for var_name, stuff_spec_str in blueprint.items():
            stuff_spec = InputStuffSpecsFactory.make_from_string(
                domain_code=domain_code,
                stuff_spec_str=stuff_spec_str,
            )
            stuff_specs[var_name] = stuff_spec
        return InputStuffSpecs(root=stuff_specs)

    @classmethod
    def make_from_string(
        cls,
        domain_code: str,
        stuff_spec_str: str,
    ) -> StuffSpec:
        """Parse an input requirement string and return an StuffSpec.

        Interprets multiplicity from a string in the form:
        - "domain.ConceptCode[5]" -> multiplicity = 5 (int)
        - "domain.ConceptCode[]" -> multiplicity = True
        - "domain.ConceptCode" -> multiplicity = None (single item, default)
        - "ConceptCode[5]" -> multiplicity = 5 (resolved with domain)

        Args:
            domain_code: The domain code to use for resolving concept codes without domain prefix
            stuff_spec_str: String in the format "domain.ConceptCode" or "ConceptCode" with optional "[multiplicity]"

        Returns:
            StuffSpec with the parsed concept and multiplicity

        Raises:
            InputStuffSpecsFactoryError: If the stuff spec string format is invalid
        """
        # Pattern to match concept string and optional multiplicity brackets
        # Group 1: concept string (everything before brackets)
        # Group 2: content inside brackets (empty string for [], digits for [5])
        pattern = r"^(.+?)(?:\[(\d*)\])?$"
        match = re.match(pattern, stuff_spec_str)

        if not match:
            msg = f"Invalid input stuff spec string: {stuff_spec_str}"
            raise InputStuffSpecsFactoryError(msg)

        concept_ref_or_code = match.group(1)
        multiplicity_str = match.group(2)

        # Validate and resolve concept string with domain
        try:
            validate_concept_ref_or_code(concept_ref_or_code=concept_ref_or_code)
        except ConceptStringError as exc:
            msg = f"Invalid concept string '{concept_ref_or_code}' when trying to make an 'StuffSpec' from string: {exc}"
            raise InputStuffSpecsFactoryError(msg) from exc

        concept_ref_with_domain = ConceptFactory.make_concept_ref_with_domain_from_concept_ref_or_code(
            domain_code=domain_code,
            concept_sring_or_code=concept_ref_or_code,
        )

        # Determine multiplicity
        multiplicity: VariableMultiplicity | None = None

        if multiplicity_str is not None:  # Brackets were present
            if multiplicity_str == "":  # Empty brackets []
                multiplicity = True
            else:  # Number in brackets [5]
                multiplicity = int(multiplicity_str)
        # else: No brackets, multiplicity stays None

        concept = get_required_concept(concept_ref=concept_ref_with_domain)
        return StuffSpec(concept=concept, multiplicity=multiplicity)
