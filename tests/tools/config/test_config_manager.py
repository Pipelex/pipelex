from pipelex import pretty_print
from pipelex.tools.config.manager import config_manager


class TestConfigManager:
    def test_get_project_name(self):
        project_name = config_manager.get_project_name()
        pretty_print(project_name, title="project_name")
        assert project_name == "pipelex"
