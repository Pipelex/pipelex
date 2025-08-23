from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_native import NativeConceptEnum

ConceptLibraryRoot = Dict[str, Concept]


class ConceptProviderAbstract(ABC):
    @abstractmethod
    def add_new_concept(self, concept: Concept) -> None:
        pass

    @abstractmethod
    def add_concepts(self, concepts: List[Concept]) -> None:
        pass

    @abstractmethod
    def list_concepts_by_domain(self, domain: str) -> List[Concept]:
        pass

    @abstractmethod
    def list_concepts(self) -> List[Concept]:
        pass

    @abstractmethod
    def get_required_concept(self, concept_string: str) -> Concept:
        pass

    @abstractmethod
    def is_compatible(self, tested_concept: Concept, wanted_concept: Concept, strict: bool = False) -> bool:
        pass

    @abstractmethod
    def setup(self) -> None:
        pass

    @abstractmethod
    def reset(self) -> None:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass

    @abstractmethod
    def is_image_concept(self, concept: Concept) -> bool:
        pass

    @abstractmethod
    def search_for_concept_in_domains(self, concept_code: str, search_domains: List[str]) -> Optional[Concept]:
        pass

    @abstractmethod
    def get_class(self, concept_code: str) -> Optional[Type[Any]]:
        pass

    @abstractmethod
    def get_native_concept(self, native_concept: NativeConceptEnum) -> Concept:
        pass
