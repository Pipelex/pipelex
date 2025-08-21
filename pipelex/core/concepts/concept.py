import re
from typing import List, Tuple

from kajson.kajson_manager import KajsonManager
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self

from pipelex import log
from pipelex.core.concepts.concept_native import NativeConcept
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.exceptions import ConceptCodeError, ConceptDomainError, ConceptError
from pipelex.tools.misc.string_utils import pascal_case_to_sentence


class Concept(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    code: str
    domain: str
    definition: str
    structure_class_name: str
    refines: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_concept(self) -> Self:
        self.validate_domain_syntax()
        self.validate_concept_code_syntax()

        return self

    def validate_domain_syntax(self) -> None:
        if not re.match(r"^[a-z][a-z0-9_]*$", self.domain):
            raise ConceptDomainError(
                f"Domain must be snake_case (lowercase letters, numbers, and underscores only) "
                f"for concept with code '{self.code}' and domain '{self.domain}': {self.domain}"
            )

    def validate_concept_code_syntax(self) -> None:
        if not re.match(r"^[A-Z][a-zA-Z0-9]*$", self.code):
            raise ConceptCodeError(
                f"Code must be PascalCase (letters and numbers only, starting with uppercase) "
                f"for concept with code '{self.code}' and domain '{self.domain}': {self.code}"
            )

    @field_validator("refines")
    def validate_refines(self, value: List[str]) -> List[str]:
        validated_refines: List[str] = []

        # for refine_code in value:
        #     # Handle NativeConcept values directly without importing ConceptCodeFactory to avoid circular import
        #     if not Concept.concept_str_contains_domain(refine_code):
        #         # Check if it's a valid NativeConcept name
        #         if refine_code in NativeConcept.names():
        #             native_concept = NativeConcept(refine_code)
        #             full_code = native_concept.code
        #             validated_refines.append(full_code)
        #             continue
        #         else:
        #             raise ConceptCodeError(f"Each refine code must contain a single dot (.), got: {refine_code}")
        #     else:
        #         # Already has domain, validate it directly
        #         full_code = refine_code
        #         validated_refines.append(full_code)

        #     # Validate the domain and concept syntax for the full code
        #     domain, code = cls.extract_domain_and_concept_from_str(concept_str=full_code)

        return validated_refines


    @classmethod
    def sentence_from_concept_code(cls, concept_code: str) -> str:
        return pascal_case_to_sentence(name=concept_code)

    @property
    def node_name(self) -> str:
        return self.code

    def is_native_concept(self) -> bool:
        return self.domain == SpecialDomain.NATIVE.value
    
    @classmethod
    def is_valid_structure_class(cls, structure_class_name: str) -> bool:
        # We get_class_registry directly from KajsonManager instead of pipelex hub to avoid circular import
        if KajsonManager.get_class_registry().has_subclass(name=structure_class_name, base_class=StuffContent):
            return True
        else:
            # We get_class_registry directly from KajsonManager instead of pipelex hub to avoid circular import
            if KajsonManager.get_class_registry().has_class(name=structure_class_name):
                log.warning(f"Concept class '{structure_class_name}' is registered but it's not a subclass of StuffContent")
            return False
