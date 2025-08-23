from typing import Dict, Optional

from pydantic import RootModel
from typing_extensions import override

from pipelex.core.domains.domain import Domain
from pipelex.core.domains.domain_provider_abstract import DomainProviderAbstract
from pipelex.exceptions import DomainLibraryError

DomainLibraryRoot = Dict[str, Domain]


class DomainLibrary(RootModel[DomainLibraryRoot], DomainProviderAbstract):
    def validate_with_libraries(self):
        pass

    def reset(self):
        self.root = {}

    @classmethod
    def make_empty(cls):
        return cls(root={})

    def add_domain(self, domain: Domain):
        domain_code = domain.code
        if existing_domain := self.root.get(domain_code):
            # merge the new domain with the existing one
            self.root[domain_code] = existing_domain.model_copy(update=domain.model_dump())
        else:
            self.root[domain_code] = domain

    @override
    def get_domain(self, domain: str) -> Optional[Domain]:
        return self.root.get(domain)

    @override
    def get_required_domain(self, domain: str) -> Domain:
        the_domain = self.get_domain(domain=domain)
        if not the_domain:
            raise DomainLibraryError(f"Domain '{domain}' not found. Check for typos and make sure it is declared in a pipeline library.")
        return the_domain

    @override
    def teardown(self) -> None:
        self.root = {}
