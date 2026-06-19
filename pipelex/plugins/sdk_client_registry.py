from typing import Any

from pydantic import Field, RootModel

from pipelex.plugins.model_handle import ModelHandle

SdkClientRegistryRoot = dict[str, Any]


class SdkClientRegistry(RootModel[SdkClientRegistryRoot]):
    root: SdkClientRegistryRoot = Field(default_factory=dict)

    def teardown(self):
        for sdk_instance in self.root.values():
            if hasattr(sdk_instance, "teardown"):
                sdk_instance.teardown()
        self.root = {}

    def get(self, model_handle: ModelHandle) -> Any | None:
        return self.root.get(model_handle.sdk_handle)

    def set(self, *, model_handle: ModelHandle, sdk_instance: Any) -> Any:
        self.root[model_handle.sdk_handle] = sdk_instance
        return sdk_instance
