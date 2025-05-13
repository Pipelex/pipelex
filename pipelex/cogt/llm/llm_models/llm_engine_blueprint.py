# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from pydantic import field_validator

from pipelex.cogt.llm.llm_models.llm_model import LATEST_VERSION_NAME
from pipelex.cogt.llm.llm_models.llm_platform import DEFAULT_PLATFORM_INDICATOR, LLMPlatform, LLMPlatformChoice
from pipelex.tools.config.models import ConfigModel


class LLMEngineBlueprint(ConfigModel):
    llm_name: str
    llm_version: str = LATEST_VERSION_NAME
    llm_platform_choice: LLMPlatformChoice = "default"

    @field_validator("llm_platform_choice", mode="before")
    def validate_llm_platform_choice(cls, value: str) -> LLMPlatformChoice:
        if value == DEFAULT_PLATFORM_INDICATOR:
            # Make it a literal "default"
            return "default"
        return LLMPlatform(value)
