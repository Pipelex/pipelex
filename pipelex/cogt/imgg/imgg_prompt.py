# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional

from pydantic import BaseModel
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ImggPromptError
from pipelex.tools.runtime_manager import ProblemReaction, runtime_manager
from pipelex.tools.utils.json_utils import json_str


class ImggPrompt(BaseModel):
    positive_text: Optional[str] = None

    def validate_before_execution(self):
        reaction = runtime_manager.problem_reactions.job
        match reaction:
            case ProblemReaction.NONE:
                pass
            case ProblemReaction.RAISE:
                if self.positive_text is None:
                    raise ImggPromptError("Imgg prompt positive_text cannot be None (or can it?)")
                if self.positive_text == "":
                    raise ImggPromptError("Imgg prompt positive_text must not be an empty string")
            case ProblemReaction.LOG:
                if self.positive_text is None:
                    log.warning("Imgg prompt positive_text is None, that's not good, or is it?")
                if self.positive_text == "":
                    log.warning("Imgg prompt positive_text should not be an empty string")

    @override
    def __str__(self) -> str:
        return json_str(self, title="imgg_prompt", is_spaced=True)
