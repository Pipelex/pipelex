from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import field_validator

from pipelex.cogt.llm.reasoning_config_base import EffortToLevelMap, get_reasoning_level_str, validate_effort_to_level_map
from pipelex.system.configuration.config_model import ConfigModel

if TYPE_CHECKING:
    from google.genai import types as genai_types

    from pipelex.cogt.llm.llm_job_components import ReasoningEffort


class GoogleThinkingLevel(StrEnum):
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GoogleConfig(ConfigModel):
    effort_to_level_map: EffortToLevelMap

    @field_validator("effort_to_level_map")
    @classmethod
    def validate_effort_map(cls, value: EffortToLevelMap) -> EffortToLevelMap:
        return validate_effort_to_level_map(value, config_name="google_config", level_type=GoogleThinkingLevel)

    def get_reasoning_level(self, effort: ReasoningEffort) -> genai_types.ThinkingLevel | None:
        """Resolve a ReasoningEffort to a Google ThinkingLevel enum value.

        Returns:
            The Google ThinkingLevel enum, or None if reasoning is disabled.

        """
        from google.genai import types as genai_types  # ruff: ignore[import-outside-top-level]

        level_str = get_reasoning_level_str(effort_to_level_map=self.effort_to_level_map, effort=effort)
        if level_str is None:
            return None
        google_level = GoogleThinkingLevel(level_str)
        match google_level:
            case GoogleThinkingLevel.MINIMAL:
                return genai_types.ThinkingLevel.MINIMAL
            case GoogleThinkingLevel.LOW:
                return genai_types.ThinkingLevel.LOW
            case GoogleThinkingLevel.MEDIUM:
                return genai_types.ThinkingLevel.MEDIUM
            case GoogleThinkingLevel.HIGH:
                return genai_types.ThinkingLevel.HIGH
