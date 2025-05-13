# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Dict, List, Optional

from pydantic import Field, RootModel
from typing_extensions import override

from pipelex import log
from pipelex.core.domain import Domain
from pipelex.core.domain_provider_abstract import DomainProviderAbstract
from pipelex.exceptions import DomainLibraryError
from pipelex.tools.utils.file_utils import save_to_path

DomainLibraryRoot = Dict[str, Domain]


class DomainLibrary(RootModel[DomainLibraryRoot], DomainProviderAbstract):
    root: DomainLibraryRoot = Field(default_factory=dict)

    def validate_with_libraries(self):
        pass

    def reset(self):
        self.root = {}

    def add_new_domain(self, domain: Domain):
        domain_code = domain.code
        if domain_code in self.root:
            raise DomainLibraryError(f"Domain '{domain_code}' already exists in the library")
        self.root[domain_code] = domain

    def print_all(self):
        log.dev("-" * 80)
        log.dev("DomainLibrary")
        log.dev("-" * 80)
        for domain_code, domain in self.root.items():
            log.dev(f"• {domain_code}:")
            log.dev(f"  - definition: {domain.definition}")
            if system_prompt := domain.system_prompt:
                log.dev(f"  - system_prompt: {system_prompt}")

    def _export_as_text_listing(self) -> str:
        exported_lines: List[str] = []
        for domain_code, domain in self.root.items():
            exported_lines.append(f"   • {domain_code}: {domain.definition}")
        return "\n".join(exported_lines)

    def export_listing_to_path(self, export_path: str):
        log.dev("-" * 80)
        log.dev(f"Exporting DomainLibrary to {export_path}")
        log.dev("-" * 80)
        exported_string = self._export_as_text_listing()
        save_to_path(exported_string, export_path)

    @override
    def get_domain(self, domain_code: str) -> Optional[Domain]:
        return self.root.get(domain_code)

    @override
    def get_required_domain(self, domain_code: str) -> Domain:
        the_domain = self.get_domain(domain_code=domain_code)
        if not the_domain:
            raise DomainLibraryError(f"Domain '{domain_code}' not found. Check for typos and make sure it is declared in a pipeline library.")
        return the_domain

    @override
    def get_domains(self) -> List[Domain]:
        return list(self.root.values())

    @override
    def get_domains_dict(self) -> Dict[str, Domain]:
        return self.root

    @override
    def teardown(self) -> None:
        self.root = {}
