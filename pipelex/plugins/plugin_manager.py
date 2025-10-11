from pipelex.plugins.plugin_sdk_registry import PluginSdkRegistry


class PluginManager:
    def __init__(self):
        self.plugin_sdk_registry = PluginSdkRegistry()

    def setup(self):
        pass

    def teardown(self):
        self.plugin_sdk_registry.teardown()
