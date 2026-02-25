from pipelex.core.concepts.exceptions import ConceptCodeError, ConceptStringError
from pipelex.core.qualified_ref import QualifiedRef, QualifiedRefError
from pipelex.tools.misc.string_utils import is_pascal_case


def is_concept_code_valid(concept_code: str) -> bool:
    return is_pascal_case(concept_code)


def validate_concept_code(concept_code: str) -> None:
    if not is_concept_code_valid(concept_code=concept_code):
        msg = f"Concept code '{concept_code}' is not a valid concept code. It should be in PascalCase."
        raise ConceptCodeError(msg)


def is_concept_ref_valid(concept_ref: str) -> bool:
    """Check if a concept reference (domain.ConceptCode) is valid.

    Supports hierarchical domains: "legal.contracts.NonCompeteClause" is valid.
    Supports cross-package refs: "alias->domain.ConceptCode" is valid.
    """
    if QualifiedRef.has_cross_package_prefix(concept_ref):
        _, remainder = QualifiedRef.split_cross_package_ref(concept_ref)
        return is_concept_ref_valid(concept_ref=remainder)
    try:
        ref = QualifiedRef.parse_concept_ref(concept_ref)
    except QualifiedRefError:
        return False
    return ref.is_qualified


def validate_concept_ref(concept_ref: str) -> None:
    if not is_concept_ref_valid(concept_ref=concept_ref):
        msg = (
            f"Concept string '{concept_ref}' is not a valid concept string. It must be in the format 'domain.ConceptCode': "
            " - domain: a valid domain code (snake_case, possibly hierarchical like legal.contracts), "
            " - ConceptCode: a valid concept code (PascalCase)"
        )
        raise ConceptStringError(msg)


def is_concept_ref_or_code_valid(concept_ref_or_code: str) -> bool:
    """Check if a concept reference or bare code is valid.

    Supports hierarchical domains: "legal.contracts.NonCompeteClause" is valid.
    Bare codes must be PascalCase: "NonCompeteClause" is valid.
    Supports cross-package refs: "alias->domain.ConceptCode" is valid.
    """
    if not concept_ref_or_code:
        return False
    if QualifiedRef.has_cross_package_prefix(concept_ref_or_code):
        _, remainder = QualifiedRef.split_cross_package_ref(concept_ref_or_code)
        return is_concept_ref_or_code_valid(concept_ref_or_code=remainder)
    if "." in concept_ref_or_code:
        return is_concept_ref_valid(concept_ref=concept_ref_or_code)
    return is_concept_code_valid(concept_code=concept_ref_or_code)


def validate_concept_ref_or_code(concept_ref_or_code: str) -> None:
    if not is_concept_ref_or_code_valid(concept_ref_or_code=concept_ref_or_code):
        msg = f"Concept string or code '{concept_ref_or_code}' is not a valid concept string or code."
        raise ConceptStringError(msg)
