import inspect
from typing import Any, cast, get_args, get_origin

from kajson.kajson_manager import KajsonManager
from pydantic import BaseModel, ConfigDict, field_validator

from pipelex import log
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.stuffs.image_field_search import search_for_nested_image_fields
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.exceptions import PipelexUnexpectedError
from pipelex.tools.misc.string_utils import pascal_case_to_sentence
from pipelex.tools.typing.class_utils import are_classes_equivalent, has_compatible_field
from pipelex.types import StrEnum


class Concept(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    code: str
    domain: str
    description: str
    structure_class_name: str
    refines: str | None = None

    @property
    def concept_string(self) -> str:
        return f"{self.domain}.{self.code}"

    @classmethod
    def is_implicit_concept(cls, concept_string: str) -> bool:
        ConceptBlueprint.validate_concept_string(concept_string=concept_string)
        return concept_string.startswith(SpecialDomain.IMPLICIT)

    @field_validator("code")
    @classmethod
    def validate_code(cls, code: str) -> str:
        ConceptBlueprint.validate_concept_code(concept_code=code)
        return code

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, domain: str) -> str:
        DomainBlueprint.validate_domain_code(code=domain)
        return domain

    @field_validator("refines", mode="before")
    @classmethod
    def validate_refines(cls, refines: str | None) -> str | None:
        if refines is None:
            return None
        ConceptBlueprint.validate_concept_string(concept_string=refines)
        return refines

    @classmethod
    def sentence_from_concept(cls, concept: "Concept") -> str:
        return pascal_case_to_sentence(name=concept.code)

    @classmethod
    def is_native_concept(cls, concept: "Concept") -> bool:
        return NativeConceptCode.get_validated_native_concept_string(concept_string_or_code=concept.concept_string) is not None

    @classmethod
    def are_concept_compatible(cls, concept_1: "Concept", concept_2: "Concept", strict: bool = False) -> bool:
        if NativeConceptCode.is_dynamic_concept(concept_code=concept_1.code):
            return True
        if NativeConceptCode.is_dynamic_concept(concept_code=concept_2.code):
            return True
        if concept_1.concept_string == concept_2.concept_string:
            return True
        if concept_1.structure_class_name == concept_2.structure_class_name:
            return True

        # If concept_1 refines concept_2, they are strictly compatible
        if concept_1.refines is not None and concept_1.refines == concept_2.concept_string:
            return True

        if concept_1.refines is None and concept_2.refines is None:
            concept_1_class = KajsonManager.get_class_registry().get_class(name=concept_1.structure_class_name)
            concept_2_class = KajsonManager.get_class_registry().get_class(name=concept_2.structure_class_name)

            if concept_1_class is None or concept_2_class is None:
                return False

            if strict:
                # Check if classes are equivalent (same fields, types, descriptions)
                return are_classes_equivalent(concept_1_class, concept_2_class)
            # Check if concept_1 is a subclass of concept_2
            try:
                if issubclass(concept_1_class, concept_2_class):
                    return True
            except TypeError:
                pass

            # Check if concept_1 has compatible fields with concept_2
            return has_compatible_field(concept_1_class, concept_2_class)
        return False

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

    def search_for_nested_image_fields_in_structure_class(self) -> list[str]:
        """Recursively search for image fields in a structure class."""
        structure_class = KajsonManager.get_class_registry().get_required_subclass(name=self.structure_class_name, base_class=StuffContent)
        if not issubclass(structure_class, StuffContent):
            msg = f"Concept class '{self.structure_class_name}' is not a subclass of StuffContent"
            raise PipelexUnexpectedError(msg)
        return search_for_nested_image_fields(content_class=structure_class)

    def get_compact_memory_example(self, var_name: str) -> dict[str, Any] | str | int:
        """Generate an example value for compact memory format based on this concept.

        Compact memory follows these conventions:
        - For native concepts that can be represented as simple values (Text, Image, PDF): returns a simple string
        - For structured concepts: returns {"concept_code": "...", "content": {...}}

        The content dict is recursively generated based on the StuffContent class structure.
        """
        # Get the structure class
        structure_class = KajsonManager.get_class_registry().get_class(name=self.structure_class_name)

        # If class not found, return placeholder
        if structure_class is None:
            return {
                "concept_code": self.concept_string,
                "content": {},  # Empty dict for unknown structures
            }

        # Verify it's a subclass of StuffContent
        if not issubclass(structure_class, StuffContent):
            return {
                "concept_code": self.concept_string,
                "content": {},  # Empty dict for invalid structures
            }

        # Generate the content based on structure
        content_example = self._generate_content_example_for_class(structure_class, var_name)

        # Check if this is actually a native concept (not just using a native structure class)
        is_native = Concept.is_native_concept(self)

        # For simple native concepts ONLY - return compact format
        if is_native and self.structure_class_name == "TextContent":
            return cast("str", content_example)  # Just a string
        elif is_native and self.structure_class_name == "ImageContent":
            # Return dict with class instantiation info
            return {
                "_class": "ImageContent",
                "url": cast("str", content_example),
            }
        elif is_native and self.structure_class_name == "PDFContent":
            # Return dict with class instantiation info
            return {
                "_class": "PDFContent",
                "url": cast("str", content_example),
            }
        elif is_native and self.structure_class_name == "NumberContent":
            return cast("int", content_example)  # Just a number

        # For refined or complex concepts, wrap with concept_code
        # For Image/PDF content, wrap in the _class format
        if self.structure_class_name == "ImageContent":
            content_wrapped = {
                "_class": "ImageContent",
                "url": cast("str", content_example),
            }
        elif self.structure_class_name == "PDFContent":
            content_wrapped = {
                "_class": "PDFContent",
                "url": cast("str", content_example),
            }
        else:
            content_wrapped = content_example

        return {
            "concept_code": self.concept_string,
            "content": content_wrapped,
        }

    @classmethod
    def _generate_content_example_for_class(cls, content_class: type[StuffContent], var_name: str) -> Any:
        """Recursively generate example content based on a StuffContent class structure.

        Args:
            content_class: The StuffContent class to generate an example for
            var_name: Variable name for generating contextual example values

        Returns:
            Example content dict or simple value
        """
        class_name = content_class.__name__

        # Handle simple native content types
        if class_name == "TextContent":
            return f"{var_name}_text"
        elif class_name in {"ImageContent", "PDFContent"}:
            return f"{var_name}_url"
        elif class_name == "NumberContent":
            return 0

        # For structured content, inspect fields and recursively generate
        # Note: model_fields includes inherited fields from parent classes
        content_dict: dict[str, Any] = {}
        for field_name, field_info in content_class.model_fields.items():
            field_type = field_info.annotation

            # Handle Optional types (e.g., TextContent | None)
            origin = get_origin(field_type)
            args = get_args(field_type)

            if origin is type(None) or (args and type(None) in args):
                # Optional field - get the non-None type
                actual_type = next((arg for arg in args if arg is not type(None)), field_type) if args else field_type
            else:
                actual_type = field_type

            # Re-check origin after unwrapping Optional
            origin = get_origin(actual_type)
            args = get_args(actual_type)

            # Handle list types
            if origin is list:
                list_item_type = args[0] if args else str
                if hasattr(list_item_type, "__name__"):
                    if list_item_type.__name__ == "ImageContent":
                        content_dict[field_name] = [f"{field_name}_url_1", f"{field_name}_url_2"]
                    elif list_item_type.__name__ == "TextContent":
                        content_dict[field_name] = [f"{field_name}_text_1", f"{field_name}_text_2"]
                    elif inspect.isclass(list_item_type) and issubclass(list_item_type, StuffContent):
                        # List of StuffContent - generate examples
                        content_dict[field_name] = [cls._generate_content_example_for_class(list_item_type, f"{field_name}_item")]
                    else:
                        content_dict[field_name] = [f"{field_name}_item_1"]
                else:
                    content_dict[field_name] = []
            # Handle dict types
            elif origin is dict:
                # Simple example with one key-value pair
                content_dict[field_name] = {f"{field_name}_key": f"{field_name}_value"}
            # Handle StrEnum types
            elif inspect.isclass(actual_type) and issubclass(actual_type, StrEnum):
                # Get first enum value
                enum_values = list(actual_type)
                content_dict[field_name] = enum_values[0].value if enum_values else f"{field_name}_enum_value"
            # Handle nested StuffContent
            elif inspect.isclass(actual_type) and issubclass(actual_type, StuffContent):
                content_dict[field_name] = cls._generate_content_example_for_class(actual_type, field_name)
            # Handle basic types
            elif actual_type is str:
                content_dict[field_name] = f"{field_name}_value"
            elif actual_type is int:
                content_dict[field_name] = 0
            elif actual_type is float:
                content_dict[field_name] = 0.0
            elif actual_type is bool:
                content_dict[field_name] = False
            else:
                # For unknown types, try to get a simple repr
                try:
                    type_name = getattr(actual_type, "__name__", str(actual_type))
                    content_dict[field_name] = f"{field_name}_value  # TODO: Fill {type_name}"
                except Exception:
                    content_dict[field_name] = f"{field_name}_value"

        return content_dict
