from abc import ABC, abstractmethod

from pipelex.core.domains.domain import Domain


class DomainLibraryAbstract(ABC):
    @abstractmethod
    def get_domain(self, domain_code: str) -> Domain | None:
        """Get a domain by code from this library."""

    @abstractmethod
    def get_required_domain(self, domain_code: str) -> Domain:
        """Get a domain by code from this library, raising an error if not found."""

    @abstractmethod
    def teardown(self) -> None:
        pass
