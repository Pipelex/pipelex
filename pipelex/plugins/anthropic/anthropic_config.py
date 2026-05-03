from pydantic import field_validator

from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.cogt.llm.reasoning_config_base import EffortToLevelMap, get_reasoning_level_str, validate_effort_to_level_map
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.types import StrEnum


class AnthropicEffortLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


class AnthropicConfig(ConfigModel):
    structured_output_timeout_seconds: int
    effort_to_level_map: EffortToLevelMap

    @field_validator("effort_to_level_map")
    @classmethod
    def validate_effort_map(cls, value: EffortToLevelMap) -> EffortToLevelMap:
        return validate_effort_to_level_map(value, "anthropic_config", level_type=AnthropicEffortLevel)

    def get_reasoning_level(self, effort: ReasoningEffort) -> AnthropicEffortLevel | None:
        """Resolve a ReasoningEffort to an Anthropic effort level.

        Returns:
            The Anthropic effort level string, or None if reasoning is disabled.

        """
        level_str = get_reasoning_level_str(self.effort_to_level_map, effort)
        if level_str is None:
            return None
        return AnthropicEffortLevel(level_str)
