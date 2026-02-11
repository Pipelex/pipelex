from typing import cast

from openai.types.chat import ChatCompletionReasoningEffort
from pydantic import field_validator

from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.cogt.llm.reasoning_config_base import EffortToLevelMap, get_reasoning_level_str, validate_effort_to_level_map
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.types import StrEnum


class OpenAIReasoningLevel(StrEnum):
    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class OpenAIConfig(ConfigModel):
    effort_to_level_map: EffortToLevelMap

    @field_validator("effort_to_level_map")
    @classmethod
    def validate_effort_map(cls, value: EffortToLevelMap) -> EffortToLevelMap:
        return validate_effort_to_level_map(value, "openai_config", level_type=OpenAIReasoningLevel)

    def get_reasoning_level(self, effort: ReasoningEffort) -> ChatCompletionReasoningEffort | None:
        """Resolve a ReasoningEffort to an OpenAI ChatCompletionReasoningEffort value.

        Returns:
            The OpenAI effort value, or None if reasoning is disabled.

        """
        level_str = get_reasoning_level_str(self.effort_to_level_map, effort)
        if level_str is None:
            return None
        openai_level = OpenAIReasoningLevel(level_str)
        return cast("ChatCompletionReasoningEffort", openai_level)
