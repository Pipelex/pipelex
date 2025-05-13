# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from pipelex.cogt.llm.llm_prompt import LLMPrompt


def make_empty_prompt() -> LLMPrompt:
    return LLMPrompt(
        system_text=None,
        user_text=None,
        user_images=[],
    )


class LLMPromptFactoryAbstract(ABC, BaseModel):
    @abstractmethod
    async def make_llm_prompt_from_args(
        self,
        **prompt_arguments: Any,
    ) -> LLMPrompt:
        pass

    @property
    @abstractmethod
    def desc(self) -> str:
        pass
