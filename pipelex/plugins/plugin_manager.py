from typing import Any, Dict, Optional, Type

from kajson.class_registry import ClassRegistry
from pydantic import Field

from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.libraries.library_config import LibraryConfig
from pipelex.plugins.plugin_sdk_registry import PluginSdkRegistry
from pipelex.plugins.plugins_config import PluginConfig
from pipelex.tools.misc.toml_utils import load_toml_from_path


class PluginManager:
    def __init__(self):
        self._plugin_configs: Optional[PluginConfig] = None
        self._plugin_registry = ClassRegistry()
        self.plugin_sdk_registry = PluginSdkRegistry()

    @property
    def plugin_configs(self) -> PluginConfig:
        if self._plugin_configs is None:
            raise RuntimeError("Plugin configs not loaded")
        return self._plugin_configs

    def load_plugin_config(self):
        plugin_config_path = LibraryConfig.get_plugin_config_path()
        plugin_config_dict = load_toml_from_path(path=plugin_config_path)
        self._plugin_configs = PluginConfig.model_validate(plugin_config_dict)

    def register_plugin(self, name: str, plugin_class: Type[InferenceWorkerAbstract]):
        self._plugin_registry.register_class(name=name, class_type=plugin_class)

    def get_llm_plugin(self, plugin_name: str) -> Type[LLMWorkerAbstract]:
        plugin_class: Type[LLMWorkerAbstract] = self._plugin_registry.get_required_subclass(
            name=plugin_name,
            base_class=LLMWorkerAbstract,
        )
        return plugin_class
