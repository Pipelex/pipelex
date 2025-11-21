from pipelex.core.concepts.exceptions import ConceptCodeError, ConceptStringError
from pipelex.core.domains.validation import is_domain_code_valid
from pipelex.tools.misc.string_utils import is_pascal_case


def is_concept_code_valid(concept_code: str) -> bool:
    return is_pascal_case(concept_code)


def validate_concept_code(concept_code: str) -> None:
    if not is_concept_code_valid(concept_code=concept_code):
        msg = f"Concept code '{concept_code}' is not a valid concept code. It should be in PascalCase."
        raise ConceptCodeError(msg)


def is_concept_string_valid(concept_string: str) -> bool:
    domain, concept_code = concept_string.split(".", 1)

    # Validate domain
    if not is_domain_code_valid(code=domain):
        return False

    # Validate concept code
    return is_concept_code_valid(concept_code=concept_code)


def validate_concept_string(concept_string: str) -> None:
    if not is_concept_string_valid(concept_string=concept_string):
        msg = (
            f"Concept string '{concept_string}' is not a valid concept string. It must be in the format 'domain.ConceptCode': "
            " - domain: a valid domain code (snake_case), "
            " - ConceptCode: a valid concept code (PascalCase)"
        )
        raise ConceptStringError(msg)


def is_concept_string_or_code_valid(concept_string_or_code: str) -> bool:
    if concept_string_or_code.count(".") > 1:
        return False

    if concept_string_or_code.count(".") == 1:
        return is_concept_string_valid(concept_string=concept_string_or_code)
    else:
        return is_concept_code_valid(concept_code=concept_string_or_code)


def validate_concept_string_or_code(concept_string_or_code: str) -> None:
    if not is_concept_string_or_code_valid(concept_string_or_code=concept_string_or_code):
        msg = f"Concept string or code '{concept_string_or_code}' is not a valid concept string or code."
        raise ConceptStringError(msg)
