from abc import ABC, abstractmethod

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.native.concept_native import NativeConceptCode


class ConceptLibraryAbstract(ABC):
    @abstractmethod
    def add_new_concept(self, concept: Concept) -> None:
        pass

    @abstractmethod
    def add_concepts(self, concepts: list[Concept]) -> None:
        pass

    @abstractmethod
    def remove_concepts_by_concept_refs(self, concept_refs: list[str]) -> None:
        pass

    @abstractmethod
    def list_concepts_by_domain(self, domain_code: str) -> list[Concept]:
        pass

    @abstractmethod
    def list_concepts(self) -> list[Concept]:
        pass

    @abstractmethod
    def get_required_concept(self, concept_ref: str) -> Concept:
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
    def get_native_concept(self, native_concept: NativeConceptCode) -> Concept:
        pass

    @abstractmethod
    def get_required_concept_from_concept_ref_or_code(self, concept_ref_or_code: str, search_domain_codes: list[str] | None = None) -> Concept:
        pass
