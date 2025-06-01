from pydantic import BaseModel
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ImggPromptError
from pipelex.tools.misc.json_utils import json_str
from pipelex.tools.runtime_manager import ProblemReaction, runtime_manager


class ImggPrompt(BaseModel):
    positive_text: str

    def validate_before_execution(self):
        reaction = runtime_manager.problem_reactions.job
        match reaction:
            case ProblemReaction.NONE:
                pass
            case ProblemReaction.RAISE:
                if self.positive_text == "":
                    raise ImggPromptError("Imgg prompt positive_text must not be an empty string")
            case ProblemReaction.LOG:
                if self.positive_text == "":
                    log.warning("Imgg prompt positive_text should not be an empty string")

    @override
    def __str__(self) -> str:
        return json_str(self, title="imgg_prompt", is_spaced=True)
