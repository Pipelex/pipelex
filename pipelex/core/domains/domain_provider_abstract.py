from abc import ABC, abstractmethod
from typing import Optional

from pipelex.core.domains.domain import Domain


class DomainProviderAbstract(ABC):
    @abstractmethod
    def get_domain(self, domain: str) -> Optional[Domain]:
        pass

    @abstractmethod
    def get_required_domain(self, domain: str) -> Domain:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass
