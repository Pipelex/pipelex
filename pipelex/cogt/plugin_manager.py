# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from enum import StrEnum
from typing import Any, Dict, Optional

from pydantic import Field, RootModel

from pipelex.cogt.imgg.imgg_platform import ImggPlatform
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.cogt.ocr.ocr_platform import OcrPlatform


class PluginHandle(StrEnum):
    OPENAI_ASYNC = "openai_async"
    AZURE_OPENAI_ASYNC = "azure_openai_async"
    ANTHROPIC_ASYNC = "anthropic_async"
    BEDROCK_ANTHROPIC_ASYNC = "bedrock_anthropic_async"
    MISTRAL_ASYNC = "mistral_async"
    BEDROCK_ASYNC = "bedrock_async"
    PERPLEXITY_ASYNC = "perplexity_async"
    VERTEXAI_OPENAI_ASYNC = "vertexai_openai_async"
    FAL_ASYNC = "fal_async"

    @staticmethod
    def get_for_llm_platform(llm_platform: LLMPlatform) -> "PluginHandle":
        match llm_platform:
            case LLMPlatform.OPENAI:
                return PluginHandle.OPENAI_ASYNC
            case LLMPlatform.AZURE_OPENAI:
                return PluginHandle.AZURE_OPENAI_ASYNC
            case LLMPlatform.ANTHROPIC:
                return PluginHandle.ANTHROPIC_ASYNC
            case LLMPlatform.MISTRAL:
                return PluginHandle.MISTRAL_ASYNC
            case LLMPlatform.BEDROCK:
                return PluginHandle.BEDROCK_ASYNC
            case LLMPlatform.BEDROCK_ANTHROPIC:
                return PluginHandle.BEDROCK_ANTHROPIC_ASYNC
            case LLMPlatform.PERPLEXITY:
                return PluginHandle.PERPLEXITY_ASYNC
            case LLMPlatform.VERTEXAI_OPENAI:
                return PluginHandle.VERTEXAI_OPENAI_ASYNC

    @staticmethod
    def get_for_ocr_engine(ocr_platform: OcrPlatform) -> "PluginHandle":
        match ocr_platform:
            case OcrPlatform.MISTRAL:
                return PluginHandle.MISTRAL_ASYNC

    @staticmethod
    def get_for_imgg_engine(imgg_platform: ImggPlatform) -> "PluginHandle":
        match imgg_platform:
            case ImggPlatform.FAL_AI:
                return PluginHandle.FAL_ASYNC


PluginManagerRoot = Dict[str, Any]


class PluginManager(RootModel[PluginManagerRoot]):
    root: PluginManagerRoot = Field(default_factory=dict)

    def reset(self):
        self.root.clear()

    def get_llm_sdk_instance(self, llm_sdk_handle: PluginHandle) -> Optional[Any]:
        return self.root.get(llm_sdk_handle)

    def set_llm_sdk_instance(self, llm_sdk_handle: PluginHandle, llm_sdk_instance: Any) -> Any:
        self.root[llm_sdk_handle] = llm_sdk_instance
        return llm_sdk_instance

    def get_ocr_sdk_instance(self, ocr_sdk_handle: PluginHandle) -> Optional[Any]:
        return self.root.get(ocr_sdk_handle)

    def set_ocr_sdk_instance(self, ocr_sdk_handle: PluginHandle, ocr_sdk_instance: Any) -> Any:
        self.root[ocr_sdk_handle] = ocr_sdk_instance
        return ocr_sdk_instance

    def get_imgg_sdk_instance(self, imgg_sdk_handle: PluginHandle) -> Optional[Any]:
        return self.root.get(imgg_sdk_handle)

    def set_imgg_sdk_instance(self, imgg_sdk_handle: PluginHandle, imgg_sdk_instance: Any) -> Any:
        self.root[imgg_sdk_handle] = imgg_sdk_instance
        return imgg_sdk_instance
