from abc import abstractmethod

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract


class ConceptLibraryAbstract(ConceptProviderAbstract):
    """A loaded method's concept library: resolution (inherited) plus the management half.

    The resolution methods live on :class:`ConceptProviderAbstract` in `core/`, so a core module can
    depend on resolution alone. Everything below is library management and stays here, high.
    """

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
    def setup(self) -> None:
        pass

    @abstractmethod
    def reset(self) -> None:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass
