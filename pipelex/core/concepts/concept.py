from typing import Dict, List

from kajson.kajson_manager import KajsonManager
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self

from pipelex import log
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptStructureBlueprint
from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.core.concepts.exceptions import ConceptCodeError, ConceptDomainError, ConceptStringError
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.create.structured_output_generator import StructureGenerator
from pipelex.tools.misc.string_utils import is_pascal_case, is_snake_case, pascal_case_to_sentence


class Concept(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    code: str
    domain: str
    definition: str
    structure_class_name: str
    refines: List[str] = Field(default_factory=list)

    @property
    def concept_string(self) -> str:
        return Concept.construct_concept_string_with_domain(domain=self.domain, concept_code=self.code)

    @field_validator("code")
    def validate_code(cls, code: str) -> str:
        cls.validate_concept_code(concept_code=code)
        return code

    @field_validator("domain")
    def validate_domain(cls, domain: str) -> str:
        cls.validate_domain_syntax(domain=domain)
        return domain

    @model_validator(mode="after")
    def validate_concept(self) -> Self:
        self.validate_refines()
        return self

    def validate_refines(self) -> None:
        for refine in self.refines:
            try:
                ConceptBlueprint.validate_single_refine(refine)
            except Exception as e:
                # Convert any exception from ConceptBlueprint validation to ConceptCodeError
                raise ConceptCodeError(str(e)) from e

    @classmethod
    def sentence_from_concept(cls, concept: "Concept") -> str:
        return pascal_case_to_sentence(name=concept.code)

    @property
    def node_name(self) -> str:
        return self.code

    @classmethod
    def is_native_concept_code(cls, concept_code: str) -> bool:
        return concept_code in [native_concept.value for native_concept in NativeConceptEnum]

    @classmethod
    def is_native_concept(cls, concept: "Concept") -> bool:
        return concept.domain == SpecialDomain.NATIVE.value

    @classmethod
    def construct_concept_string_with_domain(cls, domain: str, concept_code: str) -> str:
        return f"{domain}.{concept_code}"

    @classmethod
    def validate_domain_syntax(cls, domain: str) -> None:
        if not is_snake_case(domain):
            raise ConceptDomainError(domain=domain)

    @classmethod
    def validate_concept_code(cls, concept_code: str) -> None:
        if "." in concept_code:
            raise ConceptCodeError(code=concept_code)
        if not is_pascal_case(concept_code):
            raise ConceptCodeError(code=concept_code)

    @classmethod
    def validate_concept_string(cls, concept_string: str):
        if "." in concept_string:
            if concept_string.count(".") != 1:
                raise ConceptStringError(concept_string=concept_string)

            domain, concept_code = concept_string.split(".")
            cls.validate_domain_syntax(domain=domain)
            cls.validate_concept_code(concept_code=concept_code)

            if domain == SpecialDomain.NATIVE.value:
                if concept_code not in [native_concept.value for native_concept in NativeConceptEnum]:
                    raise ConceptCodeError(code=concept_code)

    @classmethod
    def are_concept_compatible(cls, concept_1: "Concept", concept_2: "Concept") -> bool:
        if concept_1.code == concept_2.code and concept_1.domain == concept_2.domain:
            return True
        if concept_1.structure_class_name == concept_2.structure_class_name:
            return True
        if set(concept_1.refines) == set(concept_2.refines) and len(concept_1.refines) >= 1:
            return True
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

    @classmethod
    def get_structure(cls, class_name: str, structure_blueprint: Dict[str, ConceptStructureBlueprint]) -> str:
        """Generate Python code from ConceptStructureBlueprint.

        Args:
            class_name: Name of the class to generate
            structure_blueprint: Dictionary mapping field names to their ConceptStructureBlueprint definitions

        Returns:
            Generated Python module content
        """

        return StructureGenerator().generate_from_structure_blueprint(class_name, structure_blueprint)
