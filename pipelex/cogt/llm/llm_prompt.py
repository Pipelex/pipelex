from pydantic import BaseModel
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import LLMPromptParameterError
from pipelex.cogt.image.prompt_image import PromptImage
from pipelex.system.runtime import ProblemReaction, runtime_manager
from pipelex.tools.misc.string_utils import is_none_or_has_text, is_not_none_and_has_text


class LLMPrompt(BaseModel):
    system_text: str | None = None
    user_text: str | None = None
    user_images: list[PromptImage] = []

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
                        msg = "system_text should be None or contain text"
                        raise LLMPromptParameterError(msg)
                if not is_not_none_and_has_text(text=self.user_text):
                    msg = "user_text should contain text"
                    raise LLMPromptParameterError(msg)
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
        return self.desc()
        # return "test"

    @override
    def __repr__(self) -> str:
        return self.desc()

    @override
    def __format__(self, format_spec: str) -> str:
        return self.desc()

    def desc(self, truncate_text_length: int | None = None) -> str:
        description = "LLM Prompt:"
        if truncate_text_length:
            if self.system_text:
                description += f"""
    system_text:
    {self.system_text[:truncate_text_length]}
    """
            if self.user_text:
                description += f"""
    user_text:
    {self.user_text[:truncate_text_length]}
    """
        else:
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
