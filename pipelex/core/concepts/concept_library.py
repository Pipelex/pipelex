from typing import Any, Dict, List, Optional, Type

from pydantic import Field, RootModel
from typing_extensions import override

from pipelex import log
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
        return self.root[f"{SpecialDomain.NATIVE.value}.{native_concept.value}"]

    def get_native_concepts(self) -> List[Concept]:
        """Create all native concepts from the hardcoded data"""
        return [self.get_native_concept(native_concept=native_concept) for native_concept in NativeConceptEnum]

    @override
    def is_concept_implicit(self, concept_code: str) -> bool:
        concept_names = [concept.code for concept in self.list_concepts()]
        is_implicit = concept_code not in concept_names
        if is_implicit:
            log.debug(f"Concept '{concept_code}' is implicit")
        return is_implicit

    @override
    def list_concepts(self) -> List[Concept]:
        return list(self.root.values())

    @override
    def list_concepts_by_domain(self, domain: str) -> List[Concept]:
        return [concept for key, concept in self.root.items() if key.startswith(f"{domain}.")]

    def add_new_concept(self, concept: Concept):
        if concept.library_key in self.root:
            raise ConceptLibraryError(f"Concept '{concept.library_key}' already exists in the library")
        self.root[concept.library_key] = concept

    def add_concepts(self, concepts: List[Concept]):
        for concept in concepts:
            self.add_new_concept(concept=concept)

    @override
    def is_compatible(self, tested_concept: Concept, wanted_concept: Concept) -> bool:
        from pipelex import pretty_print

        pretty_print(tested_concept, "tested_concept")
        pretty_print(wanted_concept, "wanted_concept")
        if tested_concept.code == wanted_concept.code:
            return True
        for inherited_concept_code in tested_concept.refines:
            inherited_concept = self.get_required_concept(concept_code=inherited_concept_code)
            if self.is_compatible(inherited_concept, wanted_concept):
                return True
        return False

    @override
    def get_concept(self, concept_code: str) -> Optional[Concept]:
        return self.root.get(concept_code, None)

    @override
    def get_required_concept(self, concept_code: str) -> Concept:
        if "." not in concept_code:
            if not Concept.is_native_concept_code(concept_code=concept_code):
                raise ConceptLibraryError(f"Concept code '{concept_code}' is not a native concept")
            else:
                return self.get_native_concept(native_concept=NativeConceptEnum(concept_code))
        try:
            return self.root[concept_code]
        except KeyError:
            raise ConceptLibraryConceptNotFoundError(f"Concept code was not found and is not implicit: '{concept_code}'")

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
