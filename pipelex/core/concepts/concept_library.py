from typing import Any

from pydantic import Field, RootModel
from typing_extensions import override

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_library_abstract import ConceptLibraryAbstract
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.exceptions import ConceptLibraryConceptNotFoundError, ConceptLibraryError
from pipelex.hub import get_class_registry
from pipelex.types import Self

ConceptLibraryRoot = dict[str, Concept]


class ConceptLibrary(RootModel[ConceptLibraryRoot], ConceptLibraryAbstract):
    root: ConceptLibraryRoot = Field(default_factory=dict)

    def validate_with_libraries(self):
        """Validates that the each refine concept code in the refines array of each concept in the library exists in the library"""
        for concept in self.root.values():
            if concept.refines and concept.refines not in self.root:
                msg = f"Concept '{concept.code}' refines '{concept.refines}' but no concept with the code '{concept.refines}' exists"
                raise ConceptLibraryError(msg)

    @override
    def setup(self):
        all_native_concepts = ConceptFactory.make_all_native_concepts()
        self.add_concepts(concepts=all_native_concepts)

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

    @override
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
    def get_native_concept(self, native_concept: NativeConceptCode) -> Concept:
        the_native_concept = self.get_optional_concept(f"{SpecialDomain.NATIVE}.{native_concept}")
        if not the_native_concept:
            msg = f"Native concept '{native_concept}' not found in the library"
            raise ConceptLibraryConceptNotFoundError(msg)
        return the_native_concept

    def get_native_concepts(self) -> list[Concept]:
        """Create all native concepts from the hardcoded data"""
        return [self.get_native_concept(native_concept=native_concept) for native_concept in NativeConceptCode.values_list()]

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
            wanted_concept=self.get_native_concept(native_concept=NativeConceptCode.IMAGE),
            strict=True,
        )
        return is_image_class or refines_image

    @override
    def search_for_concept_in_domains(self, concept_code: str, search_domains: list[str]) -> Concept | None:
        ConceptBlueprint.validate_concept_code(concept_code=concept_code)
        for domain in search_domains:
            if found_concept := self.get_required_concept(
                concept_string=ConceptFactory.make_concept_string_with_domain(domain=domain, concept_code=concept_code),
            ):
                return found_concept

        return None
