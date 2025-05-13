# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from abc import ABC, abstractmethod
from typing import ClassVar, Dict, List, Optional

from pipelex.core.concept import Concept


class ConceptProviderAbstract(ABC):
    _instance: ClassVar[Optional["ConceptProviderAbstract"]] = None

    @abstractmethod
    def get_concept(self, concept_code: str) -> Optional[Concept]:
        pass

    @abstractmethod
    def list_concepts_by_domain(self, domain: str) -> List[Concept]:
        pass

    @abstractmethod
    def list_concepts(self) -> List[Concept]:
        pass

    @abstractmethod
    def is_concept_implicit(self, concept_code: str) -> bool:
        pass

    @abstractmethod
    def get_required_concept(self, concept_code: str) -> Concept:
        pass

    @abstractmethod
    def get_concepts_dict(self) -> Dict[str, Concept]:
        pass

    @abstractmethod
    def is_compatible(self, tested_concept: Concept, wanted_concept: Concept) -> bool:
        pass

    @abstractmethod
    def is_compatible_by_concept_code(self, tested_concept_code: str, wanted_concept_code: str) -> bool:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass
