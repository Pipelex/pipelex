from typing import Any, Dict, Optional

from pydantic import Field, RootModel

from pipelex.cogt.imgg.imgg_platform import ImggPlatform
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.cogt.ocr.ocr_platform import OcrPlatform
from pipelex.types import StrEnum


class PluginHandle(StrEnum):
    OPENAI_SDK = "openai_sdk"
    AZURE_OPENAI_SDK = "azure_openai_sdk"
    ANTHROPIC_SDK = "anthropic_sdk"
    BEDROCK_ANTHROPIC_SDK = "bedrock_anthropic_sdk"
    MISTRAL_SDK = "mistral_sdk"
    BEDROCK_SDK = "bedrock_sdk"
    PERPLEXITY_OPENAI_SDK = "perplexity_openai_sdk"
    VERTEXAI_OPENAI_SDK = "vertexai_openai_sdk"
    XAI_OPENAI_SDK = "xai_openai_sdk"
    CUSTOM_LLM_OPENAI_SDK = "custom_llm_openai_sdk"
    FAL_SDK = "fal_sdk"

    @staticmethod
    def get_for_llm_platform(llm_platform: LLMPlatform) -> "PluginHandle":
        match llm_platform:
            case LLMPlatform.OPENAI:
                return PluginHandle.OPENAI_SDK
            case LLMPlatform.AZURE_OPENAI:
                return PluginHandle.AZURE_OPENAI_SDK
            case LLMPlatform.ANTHROPIC:
                return PluginHandle.ANTHROPIC_SDK
            case LLMPlatform.MISTRAL:
                return PluginHandle.MISTRAL_SDK
            case LLMPlatform.BEDROCK:
                return PluginHandle.BEDROCK_SDK
            case LLMPlatform.BEDROCK_ANTHROPIC:
                return PluginHandle.BEDROCK_ANTHROPIC_SDK
            case LLMPlatform.PERPLEXITY:
                return PluginHandle.PERPLEXITY_OPENAI_SDK
            case LLMPlatform.VERTEXAI:
                return PluginHandle.VERTEXAI_OPENAI_SDK
            case LLMPlatform.XAI:
                return PluginHandle.XAI_OPENAI_SDK
            case LLMPlatform.CUSTOM_LLM:
                return PluginHandle.CUSTOM_LLM_OPENAI_SDK

    @staticmethod
    def get_for_ocr_engine(ocr_platform: OcrPlatform) -> "PluginHandle":
        match ocr_platform:
            case OcrPlatform.MISTRAL:
                return PluginHandle.MISTRAL_SDK

    @staticmethod
    def get_for_imgg_engine(imgg_platform: ImggPlatform) -> "PluginHandle":
        match imgg_platform:
            case ImggPlatform.FAL_AI:
                return PluginHandle.FAL_SDK
            case ImggPlatform.OPENAI:
                return PluginHandle.OPENAI_SDK


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
