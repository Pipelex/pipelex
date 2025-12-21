from pipelex.base_exceptions import PipelexError
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.exceptions import ConceptFactoryError
from pipelex.core.pipes.exceptions import PipeVariableMultiplicityError
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.hub import get_required_concept


class StuffSpecFactoryError(PipelexError):
    pass


class StuffSpecFactory:
    @classmethod
    def make_from_blueprint(
        cls,
        domain_code: str,
        output_string: str,
    ) -> StuffSpec:
        """Parse an output string and return a StuffSpec with concept and multiplicity.

        Args:
            domain_code: The domain code to use for resolving concept codes without domain prefix
            output_string: String in the format "ConceptCode" or "domain.ConceptCode"
                          with optional "[multiplicity]" (e.g., "Text", "Text[]", "Text[3]")

        Returns:
            StuffSpec with the parsed concept and multiplicity

        Raises:
            StuffSpecFactoryError: If the output string format is invalid
        """
        # Parse output to extract concept and multiplicity
        try:
            parse_result = parse_concept_with_multiplicity(output_string)
        except PipeVariableMultiplicityError as exc:
            msg = f"Error parsing output string '{output_string}': {exc}"
            raise StuffSpecFactoryError(msg) from exc

        # Resolve concept with domain
        try:
            domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_ref_or_code(
                domain_code=domain_code,
                concept_ref_or_code=parse_result.concept,
            )
        except ConceptFactoryError as exc:
            msg = f"Error resolving concept from output string '{output_string}': {exc}"
            raise StuffSpecFactoryError(msg) from exc

        concept = get_required_concept(
            concept_ref=ConceptFactory.make_concept_ref_with_domain(
                domain_code=domain_and_code.domain_code,
                concept_code=domain_and_code.concept_code,
            ),
        )

        return StuffSpec(concept=concept, multiplicity=parse_result.multiplicity)
