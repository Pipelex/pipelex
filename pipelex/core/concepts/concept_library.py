from typing import Any, Dict, List, Optional, Type

from pydantic import Field, RootModel
from typing_extensions import override

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NATIVE_CONCEPTS_DATA, NativeConceptEnum
from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.stuffs.stuff_content import ImageContent
from pipelex.exceptions import ConceptLibraryConceptNotFoundError, ConceptLibraryError
from pipelex.hub import get_class_registry

ConceptLibraryRoot = Dict[str, Concept]


class ConceptLibrary(RootModel[ConceptLibraryRoot], ConceptProviderAbstract):
    root: ConceptLibraryRoot = Field(default_factory=dict)

    def validate_with_libraries(self):
        """Validates that the each refine concept code in the refines array of each concept in the library exists in the library"""
        for concept in self.root.values():
            for refine in concept.refines:
                if refine not in self.root.keys():
                    raise ConceptLibraryError(f"Concept '{concept.code}' refines '{refine}' but no concept with the code '{refine}' exists")

    @override
    def setup(self):
        native_concepts = [
            ConceptFactory.make_native_concept(native_concept_data=NATIVE_CONCEPTS_DATA[native_concept]) for native_concept in NativeConceptEnum
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
    def make_empty(cls):
        return cls(root={})

    @override
    def get_native_concept(self, native_concept: NativeConceptEnum) -> Concept:
        try:
            return self.root[f"{SpecialDomain.NATIVE.value}.{native_concept.value}"]
        except KeyError:
            raise ConceptLibraryConceptNotFoundError(f"Native concept '{native_concept.value}' not found in the library")

    def get_native_concepts(self) -> List[Concept]:
        """Create all native concepts from the hardcoded data"""
        return [self.get_native_concept(native_concept=native_concept) for native_concept in NativeConceptEnum]

    @override
    def list_concepts(self) -> List[Concept]:
        return list(self.root.values())

    @override
    def list_concepts_by_domain(self, domain: str) -> List[Concept]:
        return [concept for key, concept in self.root.items() if key.startswith(f"{domain}.")]

    @override
    def add_new_concept(self, concept: Concept):
        if concept.concept_string in self.root:
            raise ConceptLibraryError(f"Concept '{concept.concept_string}' already exists in the library")
        self.root[concept.concept_string] = concept

    @override
    def add_concepts(self, concepts: List[Concept]):
        for concept in concepts:
            self.add_new_concept(concept=concept)

    @override
    def is_compatible(self, tested_concept: Concept, wanted_concept: Concept) -> bool:
        if Concept.are_concept_compatible(concept_1=tested_concept, concept_2=wanted_concept):
            return True
        # Loop
        return False

    @override
    def get_concept(self, concept_code: str) -> Optional[Concept]:
        return self.root.get(concept_code, None)

    @override
    def get_required_concept(self, concept_string: str) -> Concept:
        """
        `concept_string` can have the domain or not. If it doesn't have the domain, it is assumed to be native.
        If it is not native and doesnt have a domain, it should raise an error
        """
        if "." not in concept_string:
            if not Concept.is_native_concept_code(concept_code=concept_string):
                raise ConceptLibraryError(f"Concept code '{concept_string}' cannot be found in the library without a domain or being native")
            else:
                return self.get_native_concept(native_concept=NativeConceptEnum(concept_string))
        try:
            return self.root[concept_string]
        except KeyError:
            raise ConceptLibraryConceptNotFoundError(f"Concept with key '{concept_string}' not found in the library")

    @override
    def get_class(self, concept_code: str) -> Optional[Type[Any]]:
        return get_class_registry().get_class(concept_code)

    @override
    def is_image_concept(self, concept_code: str) -> bool:
        """
        Check if the concept is an image concept.
        It is an image concept if its structure class is a subclass of ImageContent
        or if it refines the native Image concept.
        """
        concept = self.get_concept(concept_code=concept_code)
        if not concept:
            return False
        pydantic_model = self.get_class(concept_code=concept.structure_class_name)
        is_image_class = bool(pydantic_model and issubclass(pydantic_model, ImageContent))
        refines_image = self.is_compatible(tested_concept=concept, wanted_concept=self.get_native_concept(native_concept=NativeConceptEnum.IMAGE))
        return is_image_class or refines_image

    @override
    def search_for_concept_in_domains(self, concept_name: str, search_domains: List[str]) -> Optional[Concept]:
        for domain in search_domains:
            concept_code = f"{domain}.{concept_name}"
            if found_concept := self.get_concept(concept_code=concept_code):
                return found_concept

        return None
