from typing import Optional

from pipelex.libraries.library_config import LibraryConfig
from pipelex.plugins.plugin_sdk_registry import PluginSdkRegistry
from pipelex.plugins.plugins_config import PluginConfig
from pipelex.tools.misc.toml_utils import load_toml_from_path


class PluginManager:
    def __init__(self):
        self._plugin_configs: Optional[PluginConfig] = None
        self.plugin_sdk_registry = PluginSdkRegistry()

    @property
    def plugin_configs(self) -> PluginConfig:
        if self._plugin_configs is None:
            raise RuntimeError("Plugin configs not loaded")
        return self._plugin_configs

    def setup(self, library_config: LibraryConfig):
        plugin_config_path = library_config.get_default_plugin_config_path()
        plugin_config_dict = load_toml_from_path(path=plugin_config_path)
        self._plugin_configs = PluginConfig.model_validate(plugin_config_dict)

    def teardown(self):
        self._plugin_configs = None
        self.plugin_sdk_registry.teardown()
