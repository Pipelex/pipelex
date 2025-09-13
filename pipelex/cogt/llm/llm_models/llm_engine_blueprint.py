from pydantic import field_validator

from pipelex.cogt.llm.llm_models.llm_platform import DEFAULT_PLATFORM_INDICATOR, LLMPlatform, LLMPlatformChoice
from pipelex.tools.config.models import ConfigModel


class LLMEngineBlueprint(ConfigModel):
    llm_name: str
    llm_platform_choice: LLMPlatformChoice = "default"

    @field_validator("llm_platform_choice", mode="before")
    def validate_llm_platform_choice(cls, value: str) -> LLMPlatformChoice:
        if value == DEFAULT_PLATFORM_INDICATOR:
            # Make it a literal "default"
            return "default"
        return LLMPlatform(value)
