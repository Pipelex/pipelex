# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from enum import StrEnum
from typing import Literal, Union

DEFAULT_PLATFORM_INDICATOR = "default"


class LLMPlatform(StrEnum):
    # Naming scheme:
    # single name => it's the name of the platform and we use the standard sdk
    # double name => <PROVIDER>_<SDK> => we use this sdk with this provider
    # TODO: make this separation more "automatic"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"
    BEDROCK = "bedrock"
    BEDROCK_ANTHROPIC = "bedrock_anthropic"
    MISTRAL = "mistral"
    OPENAI = "openai"
    PERPLEXITY = "perplexity"
    VERTEXAI_OPENAI = "vertexai_openai"

    @staticmethod
    def list_openai_related() -> list["LLMPlatform"]:
        return [
            LLMPlatform.OPENAI,
            LLMPlatform.AZURE_OPENAI,
            LLMPlatform.VERTEXAI_OPENAI,
            LLMPlatform.PERPLEXITY,
        ]

    @staticmethod
    def list_anthropic_related() -> list["LLMPlatform"]:
        return [LLMPlatform.ANTHROPIC, LLMPlatform.BEDROCK_ANTHROPIC]

    @property
    def is_openai_related(self) -> bool:
        return self in LLMPlatform.list_openai_related()

    @property
    def is_gen_object_supported(self) -> bool:
        match self:
            case (
                LLMPlatform.OPENAI
                | LLMPlatform.AZURE_OPENAI
                | LLMPlatform.VERTEXAI_OPENAI
                | LLMPlatform.PERPLEXITY
                | LLMPlatform.ANTHROPIC
                | LLMPlatform.MISTRAL
                | LLMPlatform.BEDROCK_ANTHROPIC
            ):
                return True
            case LLMPlatform.BEDROCK:
                return False

    @property
    def console_color(self) -> str:
        match self:
            case LLMPlatform.OPENAI:
                return "deep_pink1"
            case LLMPlatform.AZURE_OPENAI:
                return "turquoise2"
            case LLMPlatform.ANTHROPIC:
                return "dark_orange"
            case LLMPlatform.MISTRAL:
                return "gold3"
            case LLMPlatform.BEDROCK:
                return "medium_purple1"
            case LLMPlatform.BEDROCK_ANTHROPIC:
                return "spring_green2"
            case LLMPlatform.PERPLEXITY:
                return "gray"
            case LLMPlatform.VERTEXAI_OPENAI:
                return "deep_sky_blue"


LLMPlatformChoice = Union[LLMPlatform, Literal["default"]]
