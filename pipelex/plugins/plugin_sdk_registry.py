from typing import Any

from pydantic import BaseModel, Field, RootModel

from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


class Plugin(BaseModel):
    sdk: str
    backend: str

    @property
    def sdk_handle(self) -> str:
        return f"{self.sdk}@{self.backend}"

    @classmethod
    def make_for_inference_model(cls, inference_model: InferenceModelSpec) -> "Plugin":
        return Plugin(
            sdk=inference_model.sdk,
            backend=inference_model.backend_name,
        )


PluginSdkRegistryRoot = dict[str, Any]


class PluginSdkRegistry(RootModel[PluginSdkRegistryRoot]):
    root: PluginSdkRegistryRoot = Field(default_factory=dict)

    def teardown(self):
        for sdk_instance in self.root.values():
            if hasattr(sdk_instance, "teardown"):
                sdk_instance.teardown()
        self.root = {}

    def get_sdk_instance(self, plugin: Plugin) -> Any | None:
        return self.root.get(plugin.sdk_handle)

    def set_sdk_instance(self, plugin: Plugin, sdk_instance: Any) -> Any:
        self.root[plugin.sdk_handle] = sdk_instance
        return sdk_instance
