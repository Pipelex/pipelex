from abc import ABC, abstractmethod
from typing import List, Optional

from pipelex.cogt.llm.llm_models.llm_model import LLMModel
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatformChoice


class LLMModelProviderAbstract(ABC):
    @property
    @abstractmethod
    def desc(self) -> str:
        pass

    @abstractmethod
    def get_all_llm_models(self) -> List[LLMModel]:
        pass

    @abstractmethod
    def get_llm_model(
        self,
        llm_name: str,
        llm_version: str,
        llm_platform_choice: LLMPlatformChoice,
    ) -> LLMModel:
        pass

    @abstractmethod
    def get_optional_llm_model(
        self,
        llm_name: str,
        llm_version: str,
        llm_platform_choice: LLMPlatformChoice,
    ) -> Optional[LLMModel]:
        pass

    @abstractmethod
    def setup(self):
        pass

    @abstractmethod
    def teardown(self):
        pass
