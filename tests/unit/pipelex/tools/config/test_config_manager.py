from pipelex import pretty_print
from pipelex.config import PipelexConfig
from pipelex.hub import get_pipelex_hub
from pipelex.system.configuration.config_loader import config_manager


class TestConfigManager:
    def test_get_project_name(self):
        project_name = config_manager.get_project_name()
        pretty_print(project_name, title="project_name")
        assert project_name == "pipelex"

    def test_load_pipelex_template_config(self):
        hub = get_pipelex_hub()
        hub.setup_config(config_cls=PipelexConfig, specific_config_path="pipelex/kit/configs/pipelex.toml")
