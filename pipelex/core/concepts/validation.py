from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.concepts.exceptions import ConceptCodeError, ConceptRefineError, ConceptStringError
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.domains.exceptions import DomainCodeError
from pipelex.core.domains.validation import is_domain_code_valid, validate_domain_code
from pipelex.tools.misc.string_utils import is_pascal_case


def is_concept_code_valid(concept_code: str) -> bool:
    return is_pascal_case(concept_code)


def validate_concept_code(concept_code: str) -> None:
    if not is_concept_code_valid(concept_code=concept_code):
        msg = f"Concept code '{concept_code}' is not a valid concept code. It should be in PascalCase."
        raise ConceptCodeError(msg)


def is_concept_string_or_code_valid(concept_string_or_code: str) -> bool:
    if concept_string_or_code.count(".") > 1:
        return False

    if concept_string_or_code.count(".") == 1:
        domain, concept_code = concept_string_or_code.split(".")
        try:
            validate_concept_code(concept_code=concept_code)
            validate_domain_code(code=domain)
            return True
        except (ConceptCodeError, DomainCodeError):
            return False
    else:
        return is_concept_code_valid(concept_code=concept_string_or_code)


def validate_concept_string_or_code(concept_string_or_code: str) -> None:
    if not is_concept_string_or_code_valid(concept_string_or_code=concept_string_or_code):
        msg = f"Concept string or code '{concept_string_or_code}' is not a valid concept string or code."
        raise ConceptStringError(msg)


def validate_concept_string(concept_string: str) -> None:
    if not is_concept_string_valid(concept_string=concept_string):
        msg = (
            f"Concept string '{concept_string}' is not a valid concept string. It must be in the format 'domain.ConceptCode': "
            " - domain: a valid domain code (snake_case), "
            " - ConceptCode: a valid concept code (PascalCase)"
        )
        raise ConceptStringError(msg)


def is_concept_string_valid(concept_string: str) -> bool:
    if "." not in concept_string or concept_string.count(".") > 1:
        return False
    domain, concept_code = concept_string.split(".", 1)

    # Validate domain
    if not is_domain_code_valid(code=domain):
        return False

    # Validate concept code
    if not is_concept_code_valid(concept_code=concept_code):
        return False

    # Validate that if the concept code is among the native concepts, the domain MUST be native.
    if concept_code in NativeConceptCode.values_list():
        if not SpecialDomain.is_native(domain=domain):
            return False
    # Validate that if the domain is native, the concept code is a native concept
    if SpecialDomain.is_native(domain=domain):
        if concept_code not in NativeConceptCode.values_list():
            return False
    return True


def is_refine_valid(refine: str) -> bool:
    return NativeConceptCode.get_validated_native_concept_string(concept_string_or_code=refine) is not None


def validate_refine(refine: str) -> None:
    if not is_refine_valid(refine=refine):
        msg = (
            f"Refine '{refine}' is not a valid refine. It must be referencing a native concept. "
            "More about native concepts here: "
            "https://docs.pipelex.com/pages/build-reliable-ai-workflows-with-pipelex/define_your_concepts/#native-concepts-and-their-structures"
        )
        raise ConceptRefineError(msg)
