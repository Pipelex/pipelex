import copy

from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.configs import PipelexConfig
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import load_toml_from_path


class TestLoadConfig:
    def test_load_config(self):
        """Test that the config can be loaded and validates."""
        config = config_manager.load_config()
        PipelexConfig.model_validate(config)

    def test_kit_config_matches_defaults(self):
        """Test that kit config values match the defaults, so overrides change nothing.

        The kit config template is copied to client projects and should contain
        the same values as the base config defaults. This ensures that:
        1. The kit config stays in sync with the base config structure
        2. Users can see and modify the actual default values
        3. Changes to config schema are caught by this test
        """
        # Load only the base pipelex config (not the project .pipelex/ overrides)
        base_config_path = "pipelex/pipelex.toml"
        base_config = load_toml_from_path(base_config_path)

        # Make a deep copy before applying kit config
        base_config_copy = copy.deepcopy(base_config)

        # Load and apply the kit config
        kit_config_path = "pipelex/kit/configs/pipelex.toml"
        kit_config = load_toml_from_path(kit_config_path)
        deep_update(base_config_copy, kit_config)

        # The kit config should not change anything - all values should match defaults
        assert base_config_copy == base_config, (
            "Kit config values do not match base config defaults. Please update pipelex/kit/configs/pipelex.toml to match pipelex/pipelex.toml"
        )
