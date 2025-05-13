# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from abc import ABC, abstractmethod
from typing import ClassVar, Dict, List, Optional

from pipelex.core.domain import Domain


class DomainProviderAbstract(ABC):
    _instance: ClassVar[Optional["DomainProviderAbstract"]] = None

    @abstractmethod
    def get_domain(self, domain_code: str) -> Optional[Domain]:
        pass

    @abstractmethod
    def get_required_domain(self, domain_code: str) -> Domain:
        pass

    @abstractmethod
    def get_domains(self) -> List[Domain]:
        pass

    @abstractmethod
    def get_domains_dict(self) -> Dict[str, Domain]:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass
