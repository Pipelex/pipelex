from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field, RootModel, model_validator
from typing_extensions import TYPE_CHECKING, override

from pipelex import log
from pipelex.cogt.exceptions import LLMPromptTemplateInputsError
from pipelex.system.runtime import ProblemReaction, runtime_manager
from pipelex.tools.misc.json_utils import json_str
from pipelex.tools.misc.string_utils import can_inject_text

if TYPE_CHECKING:
    from collections.abc import ItemsView

    from pipelex.types import Self

LLMPromptTemplateInputsDict = dict[str, Any]


class LLMPromptTemplateInputs(RootModel[LLMPromptTemplateInputsDict]):
    root: LLMPromptTemplateInputsDict = Field(default_factory=dict)

    model_config = ConfigDict(validate_assignment=True)

    @model_validator(mode="after")
    def validate_template_inputs(self) -> Self:
        if not self.root:
            # It's important to exit this func before calling get_config() because empty template inputs
            # are created during imports (before Pipelex is fully initialized)
            return self
        template_inputs_reaction = runtime_manager.problem_reactions.template_inputs
        if template_inputs_reaction == ProblemReaction.NONE:
            return self
        for var_name, value in self.root.items():
            if not can_inject_text(value):
                error_msg = f"Template input '{var_name}' cannot inject text"
                if template_inputs_reaction == ProblemReaction.RAISE:
                    raise LLMPromptTemplateInputsError(message=error_msg)
                log.error(error_msg)
        return self

    def items(self) -> ItemsView[str, Any]:
        return self.root.items()

    def list_keys(self) -> list[str]:
        return list(self.root.keys())

    def complemented_by(self, additional_template_inputs: LLMPromptTemplateInputs | None) -> LLMPromptTemplateInputs:
        all_template_inputs = self.root.copy()
        if additional_template_inputs:
            all_template_inputs.update(additional_template_inputs.root)
        return LLMPromptTemplateInputs(root=all_template_inputs)

    def complemented_by_dict(self, additional_inputs_dict: LLMPromptTemplateInputsDict | None) -> LLMPromptTemplateInputs:
        all_template_inputs = self.root.copy()
        if additional_inputs_dict:
            all_template_inputs.update(additional_inputs_dict)
        return LLMPromptTemplateInputs(root=all_template_inputs)

    @override
    def __str__(self) -> str:
        return json_str(self.root, title="llm_prompt_template_inputs", is_spaced=True)

    @staticmethod
    def from_args(**template_inputs: Any) -> LLMPromptTemplateInputs:
        return LLMPromptTemplateInputs(root=template_inputs)
