from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pydantic import field_validator

from pipelex.cogt.llm.reasoning_config_base import EffortToLevelMap, get_reasoning_level_str, validate_effort_to_level_map
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from mistralai.client.models import MistralPromptMode

    from pipelex.cogt.llm.llm_job_components import ReasoningEffort


class MistralReasoningLevel(StrEnum):
    REASONING = "reasoning"


class MistralConfig(ConfigModel):
    effort_to_level_map: EffortToLevelMap

    @field_validator("effort_to_level_map")
    @classmethod
    def validate_effort_map(cls, value: EffortToLevelMap) -> EffortToLevelMap:
        return validate_effort_to_level_map(value, "mistral_config", level_type=MistralReasoningLevel)

    def get_reasoning_level(self, effort: ReasoningEffort) -> MistralPromptMode | None:
        """Resolve a ReasoningEffort to a Mistral MistralPromptMode value.

        Returns:
            The Mistral prompt mode, or None if reasoning is disabled.

        """
        level_str = get_reasoning_level_str(self.effort_to_level_map, effort)
        if level_str is None:
            return None
        mistral_level = MistralReasoningLevel(level_str)
        return cast("MistralPromptMode", mistral_level)
