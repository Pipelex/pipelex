from enum import StrEnum
from typing import Any, Dict, Optional

from pydantic import Field, RootModel

from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.cogt.ocr.ocr_platform import OcrPlatform


class SdkHandle(StrEnum):
    OPENAI_ASYNC = "openai_async"
    AZURE_OPENAI_ASYNC = "azure_openai_async"
    ANTHROPIC_ASYNC = "anthropic_async"
    BEDROCK_ANTHROPIC_ASYNC = "bedrock_anthropic_async"
    MISTRAL_ASYNC = "mistral_async"
    BEDROCK_ASYNC = "bedrock_async"
    PERPLEXITY_ASYNC = "perplexity_async"
    VERTEXAI_OPENAI_ASYNC = "vertexai_openai_async"

    @staticmethod
    def get_for_llm_platform(llm_platform: LLMPlatform) -> "SdkHandle":
        match llm_platform:
            case LLMPlatform.OPENAI:
                return SdkHandle.OPENAI_ASYNC
            case LLMPlatform.AZURE_OPENAI:
                return SdkHandle.AZURE_OPENAI_ASYNC
            case LLMPlatform.ANTHROPIC:
                return SdkHandle.ANTHROPIC_ASYNC
            case LLMPlatform.MISTRAL:
                return SdkHandle.MISTRAL_ASYNC
            case LLMPlatform.BEDROCK:
                return SdkHandle.BEDROCK_ASYNC
            case LLMPlatform.BEDROCK_ANTHROPIC:
                return SdkHandle.BEDROCK_ANTHROPIC_ASYNC
            case LLMPlatform.PERPLEXITY:
                return SdkHandle.PERPLEXITY_ASYNC
            case LLMPlatform.VERTEXAI_OPENAI:
                return SdkHandle.VERTEXAI_OPENAI_ASYNC

    @staticmethod
    def get_for_ocr_engine(ocr_platform: OcrPlatform) -> "SdkHandle":
        match ocr_platform:
            case OcrPlatform.MISTRAL:
                return SdkHandle.MISTRAL_ASYNC


SdkManagerRoot = Dict[str, Any]


class SdkManager(RootModel[SdkManagerRoot]):
    root: SdkManagerRoot = Field(default_factory=dict)

    def reset(self):
        self.root.clear()

    def get_llm_sdk_instance(self, llm_sdk_handle: SdkHandle) -> Optional[Any]:
        return self.root.get(llm_sdk_handle)

    def set_llm_sdk_instance(self, llm_sdk_handle: SdkHandle, llm_sdk_instance: Any) -> Any:
        self.root[llm_sdk_handle] = llm_sdk_instance
        return llm_sdk_instance

    def get_ocr_sdk_instance(self, ocr_sdk_handle: SdkHandle) -> Optional[Any]:
        return self.root.get(ocr_sdk_handle)

    def set_ocr_sdk_instance(self, ocr_sdk_handle: SdkHandle, ocr_sdk_instance: Any) -> Any:
        self.root[ocr_sdk_handle] = ocr_sdk_instance
        return ocr_sdk_instance
