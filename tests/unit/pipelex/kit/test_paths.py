from pipelex.kit.paths import get_kit_agents_dir, get_kit_configs_dir, get_kit_root


class TestKitPaths:
    """Test kit path utilities."""

    def test_get_kit_root(self):
        """Test that kit root path is valid."""
        kit_root = get_kit_root()
        assert kit_root is not None
        assert (kit_root / "index.toml").is_file()

    def test_get_agents_dir(self):
        """Test that agents directory path is valid."""
        agents_dir = get_kit_agents_dir()
        assert agents_dir is not None
        assert agents_dir.is_dir()

    def test_get_configs_dir(self):
        """Test that configs directory path is valid."""
        configs_dir = get_kit_configs_dir()
        assert configs_dir is not None
        assert configs_dir.is_dir()
