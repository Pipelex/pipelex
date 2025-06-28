from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, RootModel

from pipelex.cogt.imgg.imgg_platform import ImggPlatform
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.cogt.ocr.ocr_platform import OcrPlatform
from pipelex.libraries.library_config import LibraryConfig
from pipelex.plugins.plugins_config import PluginConfig
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.types import StrEnum


class PluginManager2(BaseModel):
    _plugin_configs: Optional[PluginConfig] = None

    @property
    def plugin_configs(self) -> PluginConfig:
        if self._plugin_configs is None:
            raise RuntimeError("Plugin configs not loaded")
        return self._plugin_configs

    def load_plugin_config(self):
        plugin_config_path = LibraryConfig.get_plugin_config_path()
        plugin_config_dict = load_toml_from_path(path=plugin_config_path)
        self._plugin_configs = PluginConfig.model_validate(plugin_config_dict)
