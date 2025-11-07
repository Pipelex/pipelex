from pydantic import RootModel
from typing_extensions import override

from pipelex.core.domains.domain import Domain
from pipelex.exceptions import DomainLibraryError
from pipelex.libraries.domain.domain_library_abstract import DomainLibraryAbstract
from pipelex.types import Self

DomainLibraryRoot = dict[str, Domain]


class DomainLibrary(RootModel[DomainLibraryRoot], DomainLibraryAbstract):
    def validate_with_libraries(self):
        pass

    def setup(self):
        pass

    @override
    def teardown(self):
        self.root = {}

    def reset(self):
        self.teardown()
        self.setup()

    @classmethod
    def make_empty(cls) -> Self:
        return cls(root=DomainLibraryRoot())

    @override
    def get_domain(self, domain: str) -> Domain:
        the_domain = self.root.get(domain)
        if not the_domain:
            msg = f"Domain '{domain}' not found. Check for typos and make sure it is declared in a pipeline library."
            raise DomainLibraryError(msg)
        return the_domain

    def add_domain(self, domain: Domain):
        domain_code = domain.code
        if existing_domain := self.root.get(domain_code):
            # merge the new domain with the existing one
            self.root[domain_code] = existing_domain.model_copy(update=domain.model_dump())
        else:
            self.root[domain_code] = domain

    def add_domains(self, domains: list[Domain]):
        for domain in domains:
            self.add_domain(domain=domain)

    def remove_domain_by_code(self, domain_code: str) -> None:
        if domain_code in self.root:
            del self.root[domain_code]

    @override
    def get_required_domain(self, domain: str) -> Domain:
        """Get a domain by code from this library, raising an error if not found."""
        the_domain = self.get_domain(domain=domain)
        if not the_domain:
            msg = f"Domain '{domain}' not found. Check for typos and make sure it is declared in a pipeline library."
            raise DomainLibraryError(msg)
        return the_domain
