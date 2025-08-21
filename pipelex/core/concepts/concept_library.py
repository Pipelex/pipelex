from typing import Any, Dict, List, Optional, Type

from pydantic import Field, RootModel
from typing_extensions import override

from pipelex import log
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NATIVE_CONCEPTS_DATA, NativeConcept
from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract
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

    def setup(self):
        native_concepts = self.get_native_concepts()
        self.add_concepts(native_concepts)

    def reset(self):
        self.root = {}

    @classmethod
    def make_empty(cls):
        return cls(root={})

    @classmethod
    def get_native_concept(cls, native_concept: NativeConcept) -> Concept:
        return ConceptFactory.make_native_concept(native_concept_data=NATIVE_CONCEPTS_DATA[native_concept])

    @classmethod
    def get_native_concepts(cls) -> List[Concept]:
        """Create all native concepts from the hardcoded data"""
        return [cls.get_native_concept(native_concept=native_concept) for native_concept in NativeConcept]

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
        name = concept.code
        if name in self.root:
            raise ConceptLibraryError(f"Concept '{name}' already exists in the library")
        self.root[name] = concept

    def add_concepts(self, concepts: List[Concept]):
        for concept in concepts:
            self.add_new_concept(concept=concept)

    @override
    def is_compatible(self, tested_concept: Concept, wanted_concept: Concept) -> bool:
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
        if concept_code not in self.root:
            raise ConceptLibraryConceptNotFoundError(f"Concept code was not found and is not implicit: '{concept_code}'")
        return self.root[concept_code]

    @override
    def get_concepts_dict(self) -> Dict[str, Concept]:
        return self.root

    @override
    def teardown(self) -> None:
        self.root = {}

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
        refines_image = self.is_compatible_by_concept_code(tested_concept_code=concept.code, wanted_concept_code="native.Image")
        return is_image_class or refines_image

    @override
    def search_for_concept_in_domains(self, concept_name: str, search_domains: List[str]) -> Optional[Concept]:
        for domain in search_domains:
            concept_code = f"{domain}.{concept_name}"
            if found_concept := self.get_concept(concept_code=concept_code):
                return found_concept

        return None
