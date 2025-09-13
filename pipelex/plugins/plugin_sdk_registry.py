from typing import Any, Dict, Optional

from pydantic import Field, RootModel

from pipelex.cogt.imgg.imgg_platform import ImggPlatform
from pipelex.cogt.ocr.ocr_platform import OcrPlatform
from pipelex.types import StrEnum


class PluginSdkHandle(StrEnum):
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    BEDROCK_ANTHROPIC = "bedrock_anthropic"
    MISTRAL = "mistral"
    BEDROCK = "bedrock"
    # PERPLEXITY_OPENAI = "perplexity_openai"
    # VERTEXAI_OPENAI = "vertexai_openai"
    # XAI_OPENAI = "xai_openai"
    # CUSTOM_LLM_OPENAI = "custom_llm_openai"
    FAL = "fal"

    @staticmethod
    def get_for_ocr_engine(ocr_platform: OcrPlatform) -> "PluginSdkHandle":
        match ocr_platform:
            case OcrPlatform.MISTRAL:
                return PluginSdkHandle.MISTRAL

    @staticmethod
    def get_for_imgg_engine(imgg_platform: ImggPlatform) -> "PluginSdkHandle":
        match imgg_platform:
            case ImggPlatform.FAL_AI:
                return PluginSdkHandle.FAL
            case ImggPlatform.OPENAI:
                return PluginSdkHandle.OPENAI


PluginSdkRegistryRoot = Dict[str, Any]


class PluginSdkRegistry(RootModel[PluginSdkRegistryRoot]):
    root: PluginSdkRegistryRoot = Field(default_factory=dict)

    def teardown(self):
        for llm_sdk_instance in self.root.values():
            if hasattr(llm_sdk_instance, "teardown"):
                llm_sdk_instance.teardown()
        self.root = {}

    def get_llm_sdk_instance(self, llm_sdk_handle: PluginSdkHandle) -> Optional[Any]:
        return self.root.get(llm_sdk_handle)

    def set_llm_sdk_instance(self, llm_sdk_handle: PluginSdkHandle, llm_sdk_instance: Any) -> Any:
        self.root[llm_sdk_handle] = llm_sdk_instance
        return llm_sdk_instance

    def get_ocr_sdk_instance(self, ocr_sdk_handle: PluginSdkHandle) -> Optional[Any]:
        return self.root.get(ocr_sdk_handle)

    def set_ocr_sdk_instance(self, ocr_sdk_handle: PluginSdkHandle, ocr_sdk_instance: Any) -> Any:
        self.root[ocr_sdk_handle] = ocr_sdk_instance
        return ocr_sdk_instance

    def get_imgg_sdk_instance(self, imgg_sdk_handle: PluginSdkHandle) -> Optional[Any]:
        return self.root.get(imgg_sdk_handle)

    def set_imgg_sdk_instance(self, imgg_sdk_handle: PluginSdkHandle, imgg_sdk_instance: Any) -> Any:
        self.root[imgg_sdk_handle] = imgg_sdk_instance
        return imgg_sdk_instance
