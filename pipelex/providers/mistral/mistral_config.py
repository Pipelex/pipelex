from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import field_validator

from pipelex.cogt.llm.reasoning_config_base import EffortToLevelMap, get_reasoning_level_str, validate_effort_to_level_map
from pipelex.system.configuration.config_model import ConfigModel

if TYPE_CHECKING:
    from mistralai.client.models import ReasoningEffort as MistralReasoningEffort

    from pipelex.cogt.llm.llm_job_components import ReasoningEffort


class MistralReasoningLevel(StrEnum):
    """The level map's vocabulary for Mistral, whose reasoning models have one reasoning setting: on."""

    REASONING = "reasoning"

    def as_reasoning_effort(self) -> MistralReasoningEffort:
        """The `reasoning_effort` value that turns this level on.

        Mistral's reasoning models take `reasoning_effort`, refuse every value but `none` and `high`, and refuse
        the older `prompt_mode="reasoning"` this level was first sent as.
        """
        match self:
            case MistralReasoningLevel.REASONING:
                return "high"


class MistralConfig(ConfigModel):
    effort_to_level_map: EffortToLevelMap

    @field_validator("effort_to_level_map")
    @classmethod
    def validate_effort_map(cls, value: EffortToLevelMap) -> EffortToLevelMap:
        return validate_effort_to_level_map(value, config_name="mistral_config", level_type=MistralReasoningLevel)

    def get_reasoning_level(self, effort: ReasoningEffort) -> MistralReasoningEffort | None:
        """Resolve a ReasoningEffort to a Mistral `reasoning_effort` value.

        Returns:
            The Mistral reasoning effort, or None if reasoning is disabled.

        """
        level_str = get_reasoning_level_str(effort_to_level_map=self.effort_to_level_map, effort=effort)
        if level_str is None:
            return None
        return MistralReasoningLevel(level_str).as_reasoning_effort()
