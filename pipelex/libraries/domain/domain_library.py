from pydantic import RootModel
from typing_extensions import override

from pipelex import log
from pipelex.core.domains.domain import Domain
from pipelex.libraries.domain.domain_library_abstract import DomainLibraryAbstract
from pipelex.libraries.domain.exceptions import DomainLibraryError
from pipelex.types import Self

DomainLibraryRoot = dict[str, Domain]


class DomainLibrary(RootModel[DomainLibraryRoot], DomainLibraryAbstract):
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
        return cls(root={})

    @override
    def get_domain(self, domain_code: str) -> Domain | None:
        return self.root.get(domain_code)

    def add_domain(self, domain: Domain):
        # TODO: resolve domain metadata conflicts properly — currently first-write-wins with a warning.
        # The system_prompt field is used as a PipeLLM fallback; it should be inlined at pipe factory time
        # before LibraryCrate construction so domain-level system_prompt becomes unnecessary.
        domain_code = domain.code
        if domain_code in self.root:
            existing = self.root[domain_code]
            if existing.description != domain.description:
                log.warning(
                    f"Domain '{domain_code}' declared with different descriptions: "
                    f"'{existing.description}' vs '{domain.description}'. Keeping the first.",
                )
            if existing.system_prompt != domain.system_prompt:
                log.warning(
                    f"Domain '{domain_code}' declared with different system_prompts. Keeping the first.",
                )
            return
        self.root[domain_code] = domain

    def add_domains(self, domains: list[Domain]):
        for domain in domains:
            self.add_domain(domain=domain)

    def remove_domain_by_code(self, domain_code: str) -> None:
        if domain_code not in self.root:
            msg = f"Trying to remove domain '{domain_code}' from domain library but it does not exist"
            raise DomainLibraryError(msg)
        del self.root[domain_code]

    @override
    def get_required_domain(self, domain_code: str) -> Domain:
        """Get a domain by code from this library, raising an error if not found."""
        the_domain = self.get_domain(domain_code=domain_code)
        if not the_domain:
            msg = f"Domain '{domain_code}' not found. Check for typos and make sure it is declared in a pipeline library."
            raise DomainLibraryError(msg)
        return the_domain
