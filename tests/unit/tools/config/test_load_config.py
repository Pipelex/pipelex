from pipelex.config import PipelexConfig
from pipelex.system.configuration.config_loader import config_manager
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import load_toml_from_path


class TestLoadConfig:
    def test_load_kit_config(self):
        # The base condif must validate
        config = config_manager.load_config()
        PipelexConfig.model_validate(config)

        # The confiug updated by the kit config must validate too
        config_path = "pipelex/kit/configs/pipelex.toml"
        kit_config = load_toml_from_path(config_path)
        deep_update(config, kit_config)
        PipelexConfig.model_validate(config)
