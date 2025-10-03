import types
import typing
from typing import Any

from kajson.kajson_manager import KajsonManager
from pydantic import Field, RootModel
from typing_extensions import override

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NATIVE_CONCEPTS_DATA, NativeConceptEnum
from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.stuffs.stuff_content import ImageContent, ListContent, StuffContent
from pipelex.exceptions import ConceptLibraryConceptNotFoundError, ConceptLibraryError
from pipelex.hub import get_class_registry
from pipelex.types import Self

ConceptLibraryRoot = dict[str, Concept]


class ConceptLibrary(RootModel[ConceptLibraryRoot], ConceptProviderAbstract):
    root: ConceptLibraryRoot = Field(default_factory=dict)

    def validate_with_libraries(self):
        """Validates that the each refine concept code in the refines array of each concept in the library exists in the library"""
        for concept in self.root.values():
            if concept.refines and concept.refines not in self.root:
                msg = f"Concept '{concept.code}' refines '{concept.refines}' but no concept with the code '{concept.refines}' exists"
                raise ConceptLibraryError(msg)

    @override
    def setup(self):
        native_concepts = [
            ConceptFactory.make_native_concept(native_concept_data=NATIVE_CONCEPTS_DATA[native_concept])
            for native_concept in NativeConceptEnum.values_list()
        ]
        self.add_concepts(native_concepts)

    @override
    def reset(self):
        self.root = {}
        self.setup()

    @override
    def teardown(self):
        self.root = {}

    @classmethod
    def make_empty(cls) -> Self:
        return cls(root={})

    @override
    def list_concepts(self) -> list[Concept]:
        return list(self.root.values())

    @override
    def list_concepts_by_domain(self, domain: str) -> list[Concept]:
        return [concept for key, concept in self.root.items() if key.startswith(f"{domain}.")]

    @override
    def add_new_concept(self, concept: Concept):
        if concept.concept_string in self.root:
            msg = f"Concept '{concept.concept_string}' already exists in the library"
            raise ConceptLibraryError(msg)
        self.root[concept.concept_string] = concept

    @override
    def add_concepts(self, concepts: list[Concept]):
        for concept in concepts:
            self.add_new_concept(concept=concept)

    def remove_concepts_by_codes(self, concept_codes: list[str]) -> None:
        for concept_code in concept_codes:
            if concept_code in self.root:
                del self.root[concept_code]

    @override
    def is_compatible(self, tested_concept: Concept, wanted_concept: Concept, strict: bool = False) -> bool:
        return Concept.are_concept_compatible(concept_1=tested_concept, concept_2=wanted_concept, strict=strict)

    def get_optional_concept(self, concept_string: str) -> Concept | None:
        return self.root.get(concept_string)

    @override
    def get_required_concept(self, concept_string: str) -> Concept:
        """`concept_string` can have the domain or not. If it doesn't have the domain, it is assumed to be native.
        If it is not native and doesnt have a domain, it should raise an error
        """
        if Concept.is_implicit_concept(concept_string=concept_string):
            return ConceptFactory.make_implicit_concept(concept_string=concept_string)
        ConceptBlueprint.validate_concept_string(concept_string=concept_string)
        the_concept = self.get_optional_concept(concept_string=concept_string)
        if not the_concept:
            msg = f"Concept '{concept_string}' not found in the library"
            raise ConceptLibraryConceptNotFoundError(msg)
        return the_concept

    @override
    def get_native_concept(self, native_concept: NativeConceptEnum) -> Concept:
        the_native_concept = self.get_optional_concept(f"{SpecialDomain.NATIVE}.{native_concept}")
        if not the_native_concept:
            msg = f"Native concept '{native_concept}' not found in the library"
            raise ConceptLibraryConceptNotFoundError(msg)
        return the_native_concept

    def get_native_concepts(self) -> list[Concept]:
        """Create all native concepts from the hardcoded data"""
        return [self.get_native_concept(native_concept=native_concept) for native_concept in NativeConceptEnum.values_list()]

    @override
    def get_class(self, concept_code: str) -> type[Any] | None:
        return get_class_registry().get_class(concept_code)

    @override
    def is_image_concept(self, concept: Concept) -> bool:
        """Check if the concept is an image concept.
        It is an image concept if its structure class is a subclass of ImageContent
        or if it refines the native Image concept.
        """
        pydantic_model = self.get_class(concept_code=concept.structure_class_name)
        is_image_class = bool(pydantic_model and issubclass(pydantic_model, ImageContent))
        refines_image = self.is_compatible(
            tested_concept=concept,
            wanted_concept=self.get_native_concept(native_concept=NativeConceptEnum.IMAGE),
            strict=True,
        )
        return is_image_class or refines_image

    @override
    # TODO: Refactor this function. Codesmell, it is not a proper way to do this.
    def find_image_field_paths(self, concept: Concept) -> list[str]:
        """Find all field paths in the concept's structure that are strictly compatible with Image concept.

        Args:
            concept: The concept to analyze for image field paths

        Returns:
            List of dotted field paths (e.g., ["field1", "field2.subfield"]) that contain Image content.
        """
        # Get the structure class
        structure_class = KajsonManager.get_class_registry().get_class(name=concept.structure_class_name)
        if structure_class is None or not hasattr(structure_class, "model_fields"):
            return []

        image_concept = self.get_native_concept(NativeConceptEnum.IMAGE)
        paths: list[str] = []

        def find_image_fields_in_class(cls: type[StuffContent], current_path: str = "") -> None:
            """Recursively find image fields in a structure class."""
            # Check if the class has model_fields (is a Pydantic model)
            if not hasattr(cls, "model_fields"):
                return

            # Iterate through all fields
            for field_name, field_info in cls.model_fields.items():
                # Build the path for this field
                field_path = f"{current_path}.{field_name}" if current_path else field_name

                # Get the field type annotation
                field_type = field_info.annotation

                # Handle Optional types (Union with None)
                is_union = False
                union_args = None

                # Check for typing.Union (typing.Optional)
                is_typing_union = hasattr(field_type, "__origin__") and field_type.__origin__ is typing.Union  # type: ignore[union-attr] # pyright: ignore[reportOptionalMemberAccess]
                is_types_union = hasattr(types, "UnionType") and isinstance(field_type, types.UnionType)  # pyright: ignore[reportUnnecessaryIsInstance]
                if is_typing_union or is_types_union:
                    is_union = True
                    union_args = field_type.__args__  # type: ignore[union-attr]

                if is_union and union_args:
                    # Get non-None types from the Union
                    args = [arg for arg in union_args if arg is not type(None)]
                    if len(args) == 1:
                        field_type = args[0]
                    elif len(args) == 0:
                        continue  # All args were None, skip this field

                # Skip if field type is not a class
                if not isinstance(field_type, type):
                    continue

                # Check if it's a ListContent - skip it
                try:
                    if issubclass(field_type, ListContent):
                        continue
                except (TypeError, AttributeError):
                    pass

                # Get the class name
                field_class_name = field_type.__name__

                # Check if it's a direct ImageContent first
                try:
                    if issubclass(field_type, ImageContent):
                        paths.append(field_path)
                        continue
                except TypeError:
                    pass

                # Try to find a concept for this field type
                try:
                    # Look for a concept with this structure class
                    matching_concept = None
                    for existing_concept in self.list_concepts():
                        if existing_concept.structure_class_name == field_class_name:
                            matching_concept = existing_concept
                            break

                    if matching_concept:
                        # Check if this concept is strictly compatible with Image
                        if Concept.are_concept_compatible(
                            concept_1=matching_concept,
                            concept_2=image_concept,
                            strict=True,
                        ):
                            paths.append(field_path)
                            continue  # Found an image field, no need to recurse deeper

                except Exception:  # noqa: S110
                    pass  # If we can't find a concept, continue with recursive search

                # If it's a StuffContent subclass, recurse into it
                try:
                    if issubclass(field_type, StuffContent):
                        find_image_fields_in_class(field_type, field_path)  # pyright: ignore[reportUnknownArgumentType]
                except TypeError:
                    pass

        find_image_fields_in_class(structure_class)
        return paths

    @override
    def search_for_concept_in_domains(self, concept_code: str, search_domains: list[str]) -> Concept | None:
        ConceptBlueprint.validate_concept_code(concept_code=concept_code)
        for domain in search_domains:
            if found_concept := self.get_required_concept(
                concept_string=ConceptFactory.make_concept_string_with_domain(domain=domain, concept_code=concept_code),
            ):
                return found_concept

        return None
