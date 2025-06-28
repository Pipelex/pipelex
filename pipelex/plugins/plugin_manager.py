from typing import Any, Optional

from kajson.class_registry import ClassRegistry

from pipelex import log
from pipelex.libraries.library_config import LibraryConfig
from pipelex.plugins.plugins_config import PluginConfig
from pipelex.plugins.specific_llm.template_llm_worker import TemplateLLMWorker
from pipelex.tools.misc.toml_utils import load_toml_from_path


class PluginManager:
    def __init__(self):
        self._plugin_configs: Optional[PluginConfig] = None
        self._plugin_registry = ClassRegistry()
        self._plugin_registry.register_class(class_type=TemplateLLMWorker)

    @property
    def plugin_configs(self) -> PluginConfig:
        if self._plugin_configs is None:
            raise RuntimeError("Plugin configs not loaded")
        return self._plugin_configs

    def load_plugin_config(self):
        plugin_config_path = LibraryConfig.get_plugin_config_path()
        plugin_config_dict = load_toml_from_path(path=plugin_config_path)
        self._plugin_configs = PluginConfig.model_validate(plugin_config_dict)

    def get_required_plugin(self, plugin_name: str) -> Any:
        plugin_class_name = self.plugin_configs.specific_llm_config.llm_worker_classes[plugin_name]
        plugin_class = self._plugin_registry.get_required_class(plugin_class_name)
        return plugin_class
