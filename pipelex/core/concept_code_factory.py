from typing import Optional

from pipelex.core.concept import Concept
from pipelex.core.concept_native import NativeConcept
from pipelex.exceptions import ConceptFactoryError


class ConceptCodeFactory:
    @classmethod
    def make_concept_code(cls, domain: str, code: str) -> str:
        if "." in code:
            return code
        return f"{domain}.{code}"

    @classmethod
    def make_concept_code_from_str(cls, concept_str: str, fallback_domain: Optional[str] = None) -> str:
        if Concept.concept_str_contains_domain(concept_str=concept_str):
            return concept_str
        elif concept_str in NativeConcept.names():
            native_concept = NativeConcept(concept_str)
            return native_concept.code
        elif fallback_domain:
            return cls.make_concept_code(domain=fallback_domain, code=concept_str)
        else:
            raise ConceptFactoryError(f"Concept '{concept_str}' does not contain a domain and no fallback domain was provided")
