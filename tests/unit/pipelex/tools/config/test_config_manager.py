from pipelex import pretty_print
from pipelex.config import PipelexConfig
from pipelex.hub import get_pipelex_hub
from pipelex.config.manager import config_manager


class TestConfigManager:
    def test_load_pipelex_template_config(self):
        hub = get_pipelex_hub()
        hub.setup_config(config_cls=PipelexConfig, specific_config_path="pipelex/config_template/pipelex.toml")
