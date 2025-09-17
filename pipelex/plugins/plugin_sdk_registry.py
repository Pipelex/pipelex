from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, RootModel

from pipelex.cogt.imgg.imgg_platform import ImggPlatform
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.ocr.ocr_platform import OcrPlatform


class Plugin(BaseModel):
    sdk: str
    backend: str

    @property
    def sdk_handle(self) -> str:
        return f"{self.sdk}@{self.backend}"

    @classmethod
    def make_for_ocr_engine(cls, ocr_platform: OcrPlatform) -> "Plugin":
        match ocr_platform:
            case OcrPlatform.MISTRAL:
                return Plugin(sdk="mistral", backend="mistral")
            case OcrPlatform.BASIC:
                return Plugin(sdk="basic", backend="none")

    @classmethod
    def make_for_imgg_engine(cls, imgg_platform: ImggPlatform) -> "Plugin":
        match imgg_platform:
            case ImggPlatform.FAL_AI:
                return Plugin(sdk="fal", backend="fal")
            case ImggPlatform.OPENAI:
                return Plugin(sdk="openai", backend="openai")

    @classmethod
    def make_for_inference_model(cls, inference_model: InferenceModelSpec) -> "Plugin":
        return Plugin(
            sdk=inference_model.sdk,
            backend=inference_model.backend_name,
        )


PluginSdkRegistryRoot = Dict[str, Any]


class PluginSdkRegistry(RootModel[PluginSdkRegistryRoot]):
    root: PluginSdkRegistryRoot = Field(default_factory=dict)

    def teardown(self):
        for sdk_instance in self.root.values():
            if hasattr(sdk_instance, "teardown"):
                sdk_instance.teardown()
        self.root = {}

    def get_sdk_instance(self, plugin: Plugin) -> Optional[Any]:
        return self.root.get(plugin.sdk_handle)

    def set_sdk_instance(self, plugin: Plugin, sdk_instance: Any) -> Any:
        self.root[plugin.sdk_handle] = sdk_instance
        return sdk_instance
