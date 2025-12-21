from typing import Any

from kajson.kajson_manager import KajsonManager
from pydantic import BaseModel, ConfigDict, field_validator

from pipelex import log
from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.core.concepts.concept_representation_generator import (
    ConceptRepresentationFormat,
    ConceptRepresentationGenerator,
)
from pipelex.core.concepts.exceptions import ConceptCodeError, ConceptValueError
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.validation import validate_concept_code
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.domains.exceptions import DomainCodeError
from pipelex.core.domains.validation import validate_domain_code
from pipelex.core.stuffs.image_field_search import search_for_nested_image_fields
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.misc.string_utils import pascal_case_to_sentence
from pipelex.tools.typing.class_utils import are_classes_equivalent, has_compatible_field


class Concept(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    code: str
    domain_code: str
    description: str
    structure_class_name: str
    # TODO: rethink this refines field here.
    refines: str | None = None

    @field_validator("code")
    @classmethod
    def validate_code(cls, code: str) -> str:
        try:
            validate_concept_code(concept_code=code)
        except ConceptCodeError as exc:
            msg = f"Concept code '{code}' is not a valid concept code for concept '{cls.concept_ref}'"
            raise ConceptValueError(msg) from exc
        return code

    @field_validator("domain_code")
    @classmethod
    def validate_domain(cls, domain_code: str) -> str:
        try:
            validate_domain_code(code=domain_code)
        except DomainCodeError as exc:
            msg = f"Domain code '{domain_code}' is not a valid domain code for concept '{cls.concept_ref}'"
            raise ConceptValueError(msg) from exc
        return domain_code

    @field_validator("refines", mode="before")
    @classmethod
    def validate_refines(cls, refines: str | None) -> str | None:
        if refines is None:
            return None
        if not NativeConceptCode.is_valid_native_concept_ref(concept_ref=refines):
            valid_native_concepts = ", ".join(native.concept_ref for native in NativeConceptCode.values_list())
            msg = f"Refines '{refines}' is not a valid native concept string. Valid options are: {valid_native_concepts}"
            raise ConceptValueError(msg)
        return refines

    @property
    def concept_ref(self) -> str:
        return f"{self.domain_code}.{self.code}"

    @property
    def simple_concept_ref(self) -> str:
        if SpecialDomain.is_native(domain_code=self.domain_code):
            return self.code
        else:
            return self.concept_ref

    @classmethod
    def sentence_from_concept(cls, concept: "Concept") -> str:
        return pascal_case_to_sentence(name=concept.code)

    @classmethod
    def is_native_concept(cls, concept: "Concept") -> bool:
        return NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept.concept_ref)

    @classmethod
    def are_concept_compatible(cls, concept_1: "Concept", concept_2: "Concept", strict: bool = False) -> bool:
        if NativeConceptCode.is_dynamic_concept(concept_code=concept_1.code):
            return True
        if NativeConceptCode.is_dynamic_concept(concept_code=concept_2.code):
            return True
        if concept_1.concept_ref == concept_2.concept_ref:
            return True
        if concept_1.structure_class_name == concept_2.structure_class_name:
            return True

        # If concept_1 refines concept_2 by string, they are strictly compatible
        if concept_1.refines is not None and concept_1.refines == concept_2.concept_ref:
            return True

        # If both concepts refine the same concept, they are compatible
        if concept_1.refines is not None and concept_2.refines is not None and concept_1.refines == concept_2.refines:
            return True

        # Check class-based compatibility
        # This now works even when one or both concepts have refines, since we generate
        # structure classes that inherit from the refined concept's class
        concept_1_class = KajsonManager.get_class_registry().get_class(name=concept_1.structure_class_name)
        concept_2_class = KajsonManager.get_class_registry().get_class(name=concept_2.structure_class_name)

        if concept_1_class is None or concept_2_class is None:
            return False

        # Check if classes are structurally equivalent (same fields, types)
        if are_classes_equivalent(concept_1_class, concept_2_class):
            return True

        if strict:
            # In strict mode, only structural equivalence is accepted
            return False

        # Check if concept_1 is a subclass of concept_2
        # This handles inheritance from refined concepts (e.g., RefusalEmail inherits from TextContent)
        try:
            if issubclass(concept_1_class, concept_2_class):
                return True
        except TypeError:
            pass

        # Check if concept_1 has compatible fields with concept_2
        return has_compatible_field(concept_1_class, concept_2_class)

    @classmethod
    def is_valid_structure_class(cls, structure_class_name: str) -> bool:
        # TODO: DO NOT use the KajsonManager here. Pipelex needs to be instantiated to use the get_class_registry.
        # And when we go through KajsonManager, no error raises if pipelex is not instantiated.
        # We get_class_registry directly from KajsonManager instead of pipelex hub to avoid circular import
        if KajsonManager.get_class_registry().has_subclass(name=structure_class_name, base_class=StuffContent):
            return True
        # We get_class_registry directly from KajsonManager instead of pipelex hub to avoid circular import
        if KajsonManager.get_class_registry().has_class(name=structure_class_name):
            log.warning(f"Concept class '{structure_class_name}' is registered but it's not a subclass of StuffContent")
        return False

    def get_structure_class(self) -> type[StuffContent]:
        """Get the structure class for this concept.

        Returns:
            The StuffContent subclass, or None if not found
        """
        structure_class = KajsonManager.get_class_registry().get_class(name=self.structure_class_name)
        if structure_class is None:
            msg = f"Concept class '{self.structure_class_name}' not found"
            raise ConceptValueError(msg)
        return structure_class

    def search_for_nested_image_fields_in_structure_class(self) -> list[str]:
        """Recursively search for image fields in a structure class."""
        structure_class = KajsonManager.get_class_registry().get_required_subclass(name=self.structure_class_name, base_class=StuffContent)
        if not issubclass(structure_class, StuffContent):
            msg = f"Concept class '{self.structure_class_name}' is not a subclass of StuffContent"
            raise PipelexUnexpectedError(msg)
        return search_for_nested_image_fields(content_class=structure_class)

    def generate_input_representation(
        self,
        output_format: ConceptRepresentationFormat,
        is_multiple: bool = False,
    ) -> tuple[dict[str, Any], set[str]]:
        """Generate a representation for this concept's input.

        Args:
            output_format: The format to generate (JSON or PYTHON)
            is_multiple: If True, wrap content in a list (only for JSON format)

        Returns:
            Tuple of (representation dict, imports_needed set)
            - For JSON: content is a dict (or list of dicts if is_multiple)
            - For Python: content is a class instantiation string (wrapping handled by caller)
        """
        structure_class = self.get_structure_class()

        generator = ConceptRepresentationGenerator(output_format)
        # For inputs, we only want required fields (not optional ones)
        result = generator.generate_representation(self.concept_ref, structure_class, include_optional=False)

        # If multiple and JSON format, wrap content in a list
        # For Python format, the caller handles wrapping since content is a string
        if is_multiple and output_format == ConceptRepresentationFormat.JSON:
            result["content"] = [result["content"]]

        return result, generator.imports_needed
