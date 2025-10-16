from pipelex.config import PipelexConfig
from pipelex.hub import get_pipelex_hub


class TestLoadConfig:
    def test_load_config(self):
        hub = get_pipelex_hub()
        hub.setup_config(config_cls=PipelexConfig, specific_config_path="pipelex/kit/configs/pipelex.toml")
