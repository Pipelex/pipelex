from pydantic import BaseModel
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ImgGenPromptError
from pipelex.system.runtime import ProblemReaction, runtime_manager
from pipelex.tools.misc.json_utils import json_str


class ImgGenPrompt(BaseModel):
    positive_text: str

    def validate_before_execution(self):
        reaction = runtime_manager.problem_reactions.job
        match reaction:
            case ProblemReaction.NONE:
                pass
            case ProblemReaction.RAISE:
                if self.positive_text == "":
                    msg = "ImgGen prompt positive_text must not be an empty string"
                    raise ImgGenPromptError(msg)
            case ProblemReaction.LOG:
                if self.positive_text == "":
                    log.warning("ImgGen prompt positive_text should not be an empty string")

    @override
    def __str__(self) -> str:
        return json_str(self, title="img_gen_prompt", is_spaced=True)
