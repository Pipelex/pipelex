from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from pipelex.cogt.llm.llm_prompt import LLMPrompt


class LLMPromptFactoryAbstract(ABC, BaseModel):
    @abstractmethod
    async def make_llm_prompt_from_args(
        self,
        **prompt_arguments: Any,
    ) -> LLMPrompt:
        pass
