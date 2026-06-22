"""Tests for the env-aware plugin-config loader (D2): packaged default -> {env} -> override, global -> project."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.runtime import RunEnvironment, runtime_manager

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


class _ServerCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str
    port: int


class _DemoPluginConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    retries: int
    server: _ServerCfg


_PLUGIN_NAME = "demo"
_DEFAULT_TOML = 'name = "default"\nretries = 3\n\n[server]\nhost = "localhost"\nport = 7233\n'


class TestPluginConfigLoader:
    """The env-aware plugin-config helper layers packaged default -> {env} -> override across global -> project."""

    @staticmethod
    def _build_loader(
        mocker: MockerFixture,
        *,
        global_dir: Path,
        project_dir: Path | None,
        environment: RunEnvironment,
    ) -> ConfigLoader:
        """Return a ConfigLoader whose config-dir resolution and env are pinned to the test fixtures."""
        mocker.patch.object(ConfigLoader, "global_config_dir", new_callable=mocker.PropertyMock, return_value=global_dir)
        mocker.patch.object(ConfigLoader, "project_config_dir", new_callable=mocker.PropertyMock, return_value=project_dir)
        mocker.patch.object(type(runtime_manager), "environment", new_callable=mocker.PropertyMock, return_value=environment)
        return ConfigLoader()

    def test_packaged_default_only(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """With no override files present, the packaged default alone is a valid, fully-resolved config."""
        package_dir = tmp_path / "pkg"
        package_dir.mkdir()
        (package_dir / f"{_PLUGIN_NAME}.toml").write_text(_DEFAULT_TOML)

        global_dir = tmp_path / "global"
        global_dir.mkdir()
        loader = self._build_loader(mocker, global_dir=global_dir, project_dir=None, environment=RunEnvironment.STAGING)

        config = loader.load_plugin_config(name=_PLUGIN_NAME, package_dir=package_dir, schema=_DemoPluginConfig)

        assert config == _DemoPluginConfig(name="default", retries=3, server=_ServerCfg(host="localhost", port=7233))

    def test_env_file_deep_merges_over_default_and_ignores_other_envs(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """{name}_{env}.toml deep-merges onto the default; a sibling env's file is not read."""
        package_dir = tmp_path / "pkg"
        package_dir.mkdir()
        (package_dir / f"{_PLUGIN_NAME}.toml").write_text(_DEFAULT_TOML)

        global_dir = tmp_path / "global"
        global_dir.mkdir()
        # Selected env: overrides retries and only the nested port; host + name must survive.
        (global_dir / f"{_PLUGIN_NAME}_staging.toml").write_text("retries = 5\n\n[server]\nport = 9999\n")
        # Wrong env: must be ignored entirely.
        (global_dir / f"{_PLUGIN_NAME}_dev.toml").write_text("retries = 99\n")
        loader = self._build_loader(mocker, global_dir=global_dir, project_dir=None, environment=RunEnvironment.STAGING)

        config = loader.load_plugin_config(name=_PLUGIN_NAME, package_dir=package_dir, schema=_DemoPluginConfig)

        assert config == _DemoPluginConfig(name="default", retries=5, server=_ServerCfg(host="localhost", port=9999))

    def test_override_file_wins_over_env_file(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """{name}_override.toml is layered after {name}_{env}.toml, so it wins on collision."""
        package_dir = tmp_path / "pkg"
        package_dir.mkdir()
        (package_dir / f"{_PLUGIN_NAME}.toml").write_text(_DEFAULT_TOML)

        global_dir = tmp_path / "global"
        global_dir.mkdir()
        (global_dir / f"{_PLUGIN_NAME}_staging.toml").write_text("retries = 5\n")
        (global_dir / f"{_PLUGIN_NAME}_override.toml").write_text("retries = 7\n")
        loader = self._build_loader(mocker, global_dir=global_dir, project_dir=None, environment=RunEnvironment.STAGING)

        config = loader.load_plugin_config(name=_PLUGIN_NAME, package_dir=package_dir, schema=_DemoPluginConfig)

        assert config.retries == 7

    def test_project_dir_wins_over_global_dir(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Project .pipelex override files are layered after the global ones, so the project wins."""
        package_dir = tmp_path / "pkg"
        package_dir.mkdir()
        (package_dir / f"{_PLUGIN_NAME}.toml").write_text(_DEFAULT_TOML)

        global_dir = tmp_path / "global"
        global_dir.mkdir()
        (global_dir / f"{_PLUGIN_NAME}_staging.toml").write_text('name = "from-global"\n')
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / f"{_PLUGIN_NAME}_staging.toml").write_text('name = "from-project"\n')
        loader = self._build_loader(mocker, global_dir=global_dir, project_dir=project_dir, environment=RunEnvironment.STAGING)

        config = loader.load_plugin_config(name=_PLUGIN_NAME, package_dir=package_dir, schema=_DemoPluginConfig)

        assert config.name == "from-project"

    def test_extra_overrides_win_last(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Programmatic extra_overrides are the final layer, beating every file."""
        package_dir = tmp_path / "pkg"
        package_dir.mkdir()
        (package_dir / f"{_PLUGIN_NAME}.toml").write_text(_DEFAULT_TOML)

        global_dir = tmp_path / "global"
        global_dir.mkdir()
        (global_dir / f"{_PLUGIN_NAME}_override.toml").write_text("retries = 7\n")
        loader = self._build_loader(mocker, global_dir=global_dir, project_dir=None, environment=RunEnvironment.STAGING)

        config = loader.load_plugin_config(name=_PLUGIN_NAME, package_dir=package_dir, schema=_DemoPluginConfig, extra_overrides={"retries": 42})

        assert config.retries == 42

    def test_validation_runs_after_merge(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A required field absent from the packaged default but supplied by an env file validates fine — merge precedes validation."""
        package_dir = tmp_path / "pkg"
        package_dir.mkdir()
        # Packaged default omits `retries` entirely.
        (package_dir / f"{_PLUGIN_NAME}.toml").write_text('name = "default"\n\n[server]\nhost = "localhost"\nport = 7233\n')

        global_dir = tmp_path / "global"
        global_dir.mkdir()
        (global_dir / f"{_PLUGIN_NAME}_staging.toml").write_text("retries = 11\n")
        loader = self._build_loader(mocker, global_dir=global_dir, project_dir=None, environment=RunEnvironment.STAGING)

        config = loader.load_plugin_config(name=_PLUGIN_NAME, package_dir=package_dir, schema=_DemoPluginConfig)

        assert isinstance(config, _DemoPluginConfig)
        assert config.retries == 11
