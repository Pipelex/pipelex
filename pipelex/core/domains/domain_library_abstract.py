from abc import ABC, abstractmethod

from pipelex.core.domains.domain import Domain


class DomainLibraryAbstract(ABC):
    @abstractmethod
    def get_domain(self, domain: str) -> Domain | None:
        pass

    @abstractmethod
    def get_required_domain(self, domain: str) -> Domain:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass
