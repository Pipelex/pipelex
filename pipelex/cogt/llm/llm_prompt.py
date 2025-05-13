# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import List, Optional

from pydantic import BaseModel
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import LLMPromptError
from pipelex.cogt.image.prompt_image import PromptImage
from pipelex.tools.runtime_manager import ProblemReaction, runtime_manager
from pipelex.tools.utils.string_utils import is_none_or_has_text, is_not_none_and_has_text


class LLMPrompt(BaseModel):
    system_text: Optional[str] = None
    user_text: Optional[str] = None
    user_images: List[PromptImage] = []

    def validate_before_execution(self):
        reaction = runtime_manager.problem_reactions.job
        match reaction:
            case ProblemReaction.NONE:
                pass
            case ProblemReaction.RAISE:
                if not is_none_or_has_text(text=self.system_text):
                    if self.system_text == "":
                        log.warning(f"system_text should be None or contain text. system_text = '{self.system_text}'")
                    else:
                        raise LLMPromptError("system_text should be None or contain text")
                if not is_not_none_and_has_text(text=self.user_text):
                    raise LLMPromptError("user_text should contain text")
            case ProblemReaction.LOG:
                if not is_none_or_has_text(text=self.system_text):
                    if self.system_text == "":
                        log.warning(f"system_text should be None or contain text. system_text = '{self.system_text}'")
                    else:
                        log.error(f"Prompt template system_text should be None or contain text. system_text = '{self.system_text}'")
                if not is_not_none_and_has_text(text=self.user_text):
                    log.error("user_text should contain text")

    @override
    def __str__(self) -> str:
        # return json_str(self, title="llm_prompt", is_spaced=True)
        return self.desc
        # return "test"

    @property
    def desc(self) -> str:
        description = "LLM Prompt:"
        if self.system_text:
            description += f"""
system_text:
{self.system_text}
"""
        if self.user_text:
            description += f"""
user_text:
{self.user_text}
"""
        if self.user_images:
            user_images_desc: str = "\n".join([f"  {image}" for image in self.user_images])

            description += f"""
user_images:
{user_images_desc}
"""
        return description
