import re
from typing import List, Tuple

from kajson.class_registry import class_registry
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self

from pipelex import log
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

        domain, code = Concept.extract_domain_and_concept_from_definition(concept_code=self.code)
        if domain != self.domain:
            raise ConceptDomainError(
                f"Left part of code must match the domain field for concept with \
                    code '{self.code}' and domain '{self.domain}': {domain} != {self.domain}"
            )

        self.validate_domain_syntax(domain, self.code, self.domain)
        self.validate_concept_code_syntax(code, self.code, self.domain)

        return self

    @classmethod
    def validate_domain_syntax(cls, domain: str, code: str, domain_field: str) -> None:
        if not re.match(r"^[a-z][a-z0-9_]*$", domain):
            raise ConceptDomainError(
                f"Domain must be snake_case (lowercase letters, numbers, and underscores only) \
                    for concept with code '{code}' and domain '{domain_field}': {domain}"
            )

    @classmethod
    def validate_concept_code_syntax(cls, code: str, concept_code: str, domain_field: str) -> None:
        if not re.match(r"^[A-Z][a-zA-Z0-9]*$", code):
            raise ConceptCodeError(
                f"Code must be PascalCase (letters and numbers only, starting with uppercase) \
                    for concept with code '{concept_code}' and domain '{domain_field}': {code}"
            )

    @field_validator("refines")
    @classmethod
    def validate_refines(cls, value: List[str]) -> List[str]:
        for code in value:
            if not cls.concept_str_contains_domain(code):
                raise ConceptCodeError(f"Each inherited code must contain a dot (.), got: {code}")

            domain, code = Concept.extract_domain_and_concept_from_definition(concept_code=code)
            cls.validate_concept_code_syntax(code=code, concept_code=code, domain_field=code)
            cls.validate_domain_syntax(domain=domain, code=code, domain_field=code)
        return value

    @field_validator("structure_class_name")
    @classmethod
    def validate_structure_class_name(cls, value: str) -> str:
        if not cls.is_valid_structure_class(structure_class_name=value):
            raise StructureClassError(f"Could not validate concept because structure_class_name '{value}' is not in class registry. ")
        return value

    @classmethod
    def is_valid_structure_class(cls, structure_class_name: str) -> bool:
        if class_registry.has_subclass(name=structure_class_name, base_class=StuffContent):
            return True
        else:
            if class_registry.has_class(name=structure_class_name):
                log.warning(f"Concept class '{structure_class_name}' is registered but it's not a subclass of StuffContent")
            return False

    @classmethod
    def extract_domain_and_concept_from_definition(cls, concept_code: str) -> Tuple[str, str]:
        if "." in concept_code:
            domain, concept = concept_code.split(".")
            return domain, concept
        raise ConceptError(f"No extraction of domain and concept from concept code '{concept_code}'")

    @classmethod
    def extract_concept_name_from_str(cls, concept_str: str) -> str:
        _, concept = cls.extract_domain_and_concept_from_definition(concept_code=concept_str)
        return concept

    @classmethod
    def extract_domain_from_str(cls, concept_str: str) -> str:
        domain, _ = cls.extract_domain_and_concept_from_definition(concept_code=concept_str)
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
