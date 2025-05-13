# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from abc import ABC, abstractmethod
from typing import List

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
    def setup(self):
        pass

    @abstractmethod
    def teardown(self):
        pass
