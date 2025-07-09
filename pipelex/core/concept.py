import re
from typing import List, Tuple

from kajson.kajson_manager import KajsonManager
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self

from pipelex import log
from pipelex.core.concept_native import NativeConcept
from pipelex.core.domain import SpecialDomain
from pipelex.core.stuff_content import StuffContent
from pipelex.exceptions import ConceptCodeError, ConceptDomainError, ConceptError, StructureClassError
from pipelex.tools.misc.string_utils import pascal_case_to_sentence


class Concept(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    code: str
    domain: str
    structure_class_name: str
    definition: str
    refines: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_code_domain(self) -> Self:
        if not Concept.concept_str_contains_domain(self.code):
            raise ConceptCodeError(f"Code must contain a dot (.) for concept with code '{self.code}' and domain '{self.domain}'")

        domain, code = Concept.extract_domain_and_concept_from_str(concept_str=self.code)
        if domain != self.domain:
            raise ConceptDomainError(
                f"Left part of code must match the domain field for concept with "
                f"code '{self.code}' and domain '{self.domain}': {domain} != {self.domain}"
            )

        self.validate_domain_syntax(domain, self.code, self.domain)
        self.validate_concept_code_syntax(code, self.code, self.domain)

        return self

    @classmethod
    def validate_domain_syntax(cls, domain: str, code: str, domain_field: str) -> None:
        if not re.match(r"^[a-z][a-z0-9_]*$", domain):
            raise ConceptDomainError(
                f"Domain must be snake_case (lowercase letters, numbers, and underscores only) "
                f"for concept with code '{code}' and domain '{domain_field}': {domain}"
            )

    @classmethod
    def validate_concept_code_syntax(cls, code: str, concept_code: str, domain_field: str) -> None:
        if not re.match(r"^[A-Z][a-zA-Z0-9]*$", code):
            raise ConceptCodeError(
                f"Code must be PascalCase (letters and numbers only, starting with uppercase) "
                f"for concept with code '{concept_code}' and domain '{domain_field}': {code}"
            )

    @field_validator("refines")
    @classmethod
    def validate_refines(cls, value: List[str]) -> List[str]:
        validated_refines: List[str] = []

        for refine_code in value:
            # Handle NativeConcept values directly without importing ConceptCodeFactory to avoid circular import
            if not cls.concept_str_contains_domain(refine_code):
                # Check if it's a valid NativeConcept name
                if refine_code in NativeConcept.names():
                    native_concept = NativeConcept(refine_code)
                    full_code = native_concept.code
                    validated_refines.append(full_code)
                    continue
                else:
                    raise ConceptCodeError(f"Each refine code must contain a single dot (.), got: {refine_code}")
            else:
                # Already has domain, validate it directly
                full_code = refine_code
                validated_refines.append(full_code)

            # Validate the domain and concept syntax for the full code
            domain, code = cls.extract_domain_and_concept_from_str(concept_str=full_code)
            cls.validate_concept_code_syntax(code=code, concept_code=full_code, domain_field=domain)
            cls.validate_domain_syntax(domain=domain, code=full_code, domain_field=domain)

        return validated_refines

    @field_validator("structure_class_name")
    @classmethod
    def validate_structure_class_name(cls, value: str) -> str:
        if not cls.is_valid_structure_class(structure_class_name=value):
            raise StructureClassError(f"Could not validate concept because structure_class_name '{value}' is not in class registry. ")
        return value

    @classmethod
    def is_valid_structure_class(cls, structure_class_name: str) -> bool:
        # we get_class_registry directly from KajsonManager instead of pipelex hub to avoid circular import
        if KajsonManager.get_class_registry().has_subclass(name=structure_class_name, base_class=StuffContent):
            return True
        else:
            # we get_class_registry directly from KajsonManager instead of pipelex hub to avoid circular import
            if KajsonManager.get_class_registry().has_class(name=structure_class_name):
                log.warning(f"Concept class '{structure_class_name}' is registered but it's not a subclass of StuffContent")
            return False

    @classmethod
    def extract_domain_and_concept_from_str(cls, concept_str: str) -> Tuple[str, str]:
        if "." in concept_str:
            domain_code, concept_code = concept_str.split(".")
            return domain_code, concept_code
        raise ConceptError(f"Could not extract domain and concept from concept code '{concept_str}'")

    @classmethod
    def extract_concept_name_from_str(cls, concept_str: str) -> str:
        _, concept = cls.extract_domain_and_concept_from_str(concept_str=concept_str)
        return concept

    @classmethod
    def extract_domain_from_str(cls, concept_str: str) -> str:
        domain, _ = cls.extract_domain_and_concept_from_str(concept_str=concept_str)
        return domain

    @classmethod
    def concept_str_contains_domain(cls, concept_str: str) -> bool:
        """Check if the concept code contains a domain and is in the form <domain>.<concept_code>"""
        return "." in concept_str and len(concept_str.split(".")) == 2

    @classmethod
    def sentence_from_concept_code(cls, concept_code: str) -> str:
        return pascal_case_to_sentence(name=concept_code)

    @property
    def node_name(self) -> str:
        return self.code

    @classmethod
    def is_native_concept(cls, concept_str: str) -> bool:
        if Concept.concept_str_contains_domain(concept_str=concept_str):
            domain = Concept.extract_domain_from_str(concept_str=concept_str)
            return domain == SpecialDomain.NATIVE.value
        else:
            return concept_str in NativeConcept.names()
