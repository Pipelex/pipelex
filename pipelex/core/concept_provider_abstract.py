from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type

from pipelex.core.concept import Concept

ConceptLibraryRoot = Dict[str, Concept]


class ConceptProviderAbstract(ABC):
    @abstractmethod
    def get_concept(self, concept_code: str) -> Optional[Concept]:
        pass

    @abstractmethod
    def list_concepts_by_domain(self, domain: str) -> List[Concept]:
        pass

    @abstractmethod
    def list_concepts(self) -> List[Concept]:
        pass

    @abstractmethod
    def is_concept_implicit(self, concept_code: str) -> bool:
        pass

    @abstractmethod
    def get_required_concept(self, concept_code: str) -> Concept:
        pass

    @abstractmethod
    def get_concepts_dict(self) -> Dict[str, Concept]:
        pass

    @abstractmethod
    def is_compatible(self, tested_concept: Concept, wanted_concept: Concept) -> bool:
        pass

    @abstractmethod
    def is_compatible_by_concept_code(self, tested_concept_code: str, wanted_concept_code: str) -> bool:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass

    @abstractmethod
    def get_class(self, concept_code: str) -> Optional[Type[Any]]:
        pass

    @abstractmethod
    def is_image_concept(self, concept_code: str) -> bool:
        pass

    @abstractmethod
    def is_concept_code_legal(self, concept_code: str) -> bool:
        pass
