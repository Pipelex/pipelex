import re
from typing import TYPE_CHECKING

from pipelex.base_exceptions import PipelexError
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.exceptions import ConceptStringError
from pipelex.core.concepts.validation import validate_concept_string_or_code
from pipelex.core.pipes.inputs.input_requirements import InputRequirement, InputRequirements
from pipelex.hub import get_required_concept

if TYPE_CHECKING:
    from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity


class InputRequirementsFactoryError(PipelexError):
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
    ) -> InputRequirements:
        input_requirements_dict: dict[str, InputRequirement] = {}
        for var_name, requirement_str in blueprint.items():
            input_requirement = InputRequirementsFactory.make_from_string(
                domain=domain,
                requirement_str=requirement_str,
            )
            input_requirements_dict[var_name] = input_requirement
        return InputRequirements(root=input_requirements_dict)

    @classmethod
    def make_from_string(
        cls,
        domain: str,
        requirement_str: str,
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

        Returns:
            InputRequirement with the parsed concept and multiplicity

        Raises:
            InputRequirementsFactorySyInputRequirementsFactoryErrorntaxError: If the requirement string format is invalid
        """
        # Pattern to match concept string and optional multiplicity brackets
        # Group 1: concept string (everything before brackets)
        # Group 2: content inside brackets (empty string for [], digits for [5])
        pattern = r"^(.+?)(?:\[(\d*)\])?$"
        match = re.match(pattern, requirement_str)

        if not match:
            msg = f"Invalid input requirement string: {requirement_str}"
            raise InputRequirementsFactoryError(msg)

        concept_string_or_code = match.group(1)
        multiplicity_str = match.group(2)

        # Validate and resolve concept string with domain
        try:
            validate_concept_string_or_code(concept_string_or_code=concept_string_or_code)
        except ConceptStringError as exc:
            msg = f"Invalid concept string '{concept_string_or_code}' when trying to make an 'InputRequirement' from string: {exc}"
            raise InputRequirementsFactoryError(msg) from exc

        concept_string_with_domain = ConceptFactory.make_concept_string_with_domain_from_concept_string_or_code(
            domain=domain,
            concept_sring_or_code=concept_string_or_code,
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
