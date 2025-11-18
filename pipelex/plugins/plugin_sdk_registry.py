from typing import Any

from pydantic import Field, RootModel

from pipelex.plugins.plugin import Plugin

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
