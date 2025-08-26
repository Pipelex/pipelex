from typing import Optional

from kajson.kajson_manager import KajsonManager
from pydantic import BaseModel, ConfigDict, field_validator

from pipelex import log
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.class_registry_utils import ClassRegistryUtils
from pipelex.tools.misc.string_utils import pascal_case_to_sentence


class Concept(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    code: str
    domain: str
    definition: str
    structure_class_name: str
    refines: Optional[str] = None

    @property
    def concept_string(self) -> str:
        return f"{self.domain}.{self.code}"

    @classmethod
    def is_implicit_concept(cls, concept_string: str) -> bool:
        ConceptBlueprint.validate_concept_string(concept_string=concept_string)
        return concept_string.startswith(SpecialDomain.IMPLICIT.value)

    @field_validator("code")
    def validate_code(cls, code: str) -> str:
        ConceptBlueprint.validate_concept_code(concept_code=code)
        return code

    @field_validator("domain")
    def validate_domain(cls, domain: str) -> str:
        DomainBlueprint.validate_domain_code(code=domain)
        return domain

    @field_validator("refines", mode="before")
    def validate_refines(cls, refines: Optional[str]) -> Optional[str]:
        if refines is None:
            return None
        ConceptBlueprint.validate_concept_string(concept_string=refines)
        return refines

    @classmethod
    def sentence_from_concept(cls, concept: "Concept") -> str:
        return pascal_case_to_sentence(name=concept.code)

    @classmethod
    def is_native_concept(cls, concept: "Concept") -> bool:
        return ConceptBlueprint.is_native_concept_string_or_concept_code(concept_string_or_concept_code=concept.concept_string)

    @classmethod
    def are_concept_compatible(cls, concept_1: "Concept", concept_2: "Concept", strict: bool = False) -> bool:
        if concept_1.concept_string == concept_2.concept_string:
            return True
        if concept_1.structure_class_name == concept_2.structure_class_name:
            return True
        if concept_1.refines is None and concept_2.refines is None:
            concept_1_class = KajsonManager.get_class_registry().get_class(name=concept_1.structure_class_name)
            concept_2_class = KajsonManager.get_class_registry().get_class(name=concept_2.structure_class_name)

            if concept_1_class is None or concept_2_class is None:
                return False

            if strict:
                # Check if classes are equivalent (same fields, types, descriptions)
                return ClassRegistryUtils.are_classes_equivalent(concept_1_class, concept_2_class)
            else:
                # Check if concept_1 is a subclass of concept_2
                try:
                    if issubclass(concept_1_class, concept_2_class):
                        return True
                except TypeError:
                    pass

                # Check if concept_1 has a field that is of type concept_2_class
                return ClassRegistryUtils.has_compatible_field(concept_1_class, concept_2_class)
        return False

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
