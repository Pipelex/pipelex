from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from pipelex.core.domains.domain import Domain


class DomainProviderAbstract(ABC):
    @abstractmethod
    def get_domain(self, domain: str) -> Optional[Domain]:
        pass

    @abstractmethod
    def get_required_domain(self, domain: str) -> Domain:
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
