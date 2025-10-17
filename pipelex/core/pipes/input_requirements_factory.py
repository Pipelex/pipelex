import re
from typing import TYPE_CHECKING

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.input_requirements import InputRequirement, InputRequirements
from pipelex.exceptions import PipelexException
from pipelex.hub import get_required_concept

if TYPE_CHECKING:
    from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity


class InputRequirementsFactorySyntaxError(PipelexException):
    pass


class InputRequirementsFactory:
    @classmethod
    def make_empty(cls) -> InputRequirements:
        return InputRequirements(root={})

    @classmethod
    def make_from_blueprint(
        cls,
        domain: str,
        blueprint: dict[str, str],
        concept_codes_from_the_same_domain: list[str] | None = None,
    ) -> InputRequirements:
        input_requirements_dict: dict[str, InputRequirement] = {}
        for var_name, requirement_str in blueprint.items():
            input_requirement = InputRequirementsFactory.make_from_string(
                domain=domain,
                requirement_str=requirement_str,
                concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
            )
            input_requirements_dict[var_name] = input_requirement
        return InputRequirements(root=input_requirements_dict)

    @classmethod
    def make_from_string(
        cls,
        domain: str,
        requirement_str: str,
        concept_codes_from_the_same_domain: list[str] | None = None,
    ) -> InputRequirement:
        """Parse an input requirement string and return an InputRequirement.

        Interprets multiplicity from a string in the form:
        - "domain.ConceptCode[5]" -> multiplicity = 5 (int)
        - "domain.ConceptCode[]" -> multiplicity = True
        - "domain.ConceptCode" -> multiplicity = None (single item, default)
        - "ConceptCode[5]" -> multiplicity = 5 (resolved with domain)

        Args:
            domain: The domain to use for resolving concept codes without domain prefix
            requirement_str: String in the format "domain.ConceptCode" or "ConceptCode" with optional "[multiplicity]"
            concept_codes_from_the_same_domain: List of concept codes from the same domain for resolution

        Returns:
            InputRequirement with the parsed concept and multiplicity

        Raises:
            InputRequirementsFactorySyntaxError: If the requirement string format is invalid
        """
        # Pattern to match concept string and optional multiplicity brackets
        # Group 1: concept string (everything before brackets)
        # Group 2: content inside brackets (empty string for [], digits for [5])
        pattern = r"^(.+?)(?:\[(\d*)\])?$"
        match = re.match(pattern, requirement_str)

        if not match:
            msg = f"Invalid input requirement string: {requirement_str}"
            raise InputRequirementsFactorySyntaxError(msg)

        concept_string_or_code = match.group(1)
        multiplicity_str = match.group(2)

        # Validate and resolve concept string with domain
        ConceptBlueprint.validate_concept_string_or_code(concept_string_or_code=concept_string_or_code)
        concept_string_with_domain = ConceptFactory.make_concept_string_with_domain_from_concept_string_or_code(
            domain=domain,
            concept_sring_or_code=concept_string_or_code,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )

        # Determine multiplicity
        multiplicity: VariableMultiplicity | None = None
        if multiplicity_str is not None:  # Brackets were present
            if multiplicity_str == "":  # Empty brackets []
                multiplicity = True
            else:  # Number in brackets [5]
                multiplicity = int(multiplicity_str)
        # else: No brackets, multiplicity stays None

        concept = get_required_concept(concept_string=concept_string_with_domain)
        return InputRequirement(concept=concept, multiplicity=multiplicity)
