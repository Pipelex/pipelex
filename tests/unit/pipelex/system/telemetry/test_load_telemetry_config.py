"""Tests for layered telemetry config loading.

Validates that ~/.pipelex/telemetry.toml and ~/.pipelex/telemetry_override.toml
are layered under the project's equivalents instead of being silently shadowed.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.system.telemetry.telemetry_config import load_telemetry_config
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestLoadTelemetryConfigLayering:
    """Cover global → project layering for telemetry.toml and telemetry_override.toml."""

    @pytest.fixture
    def fake_dirs(self, tmp_path: Path, mocker: MockerFixture) -> tuple[Path, Path]:
        """Set up a fake home + project tree and patch Path.home / Path.cwd."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        global_dir = fake_home / ".pipelex"
        global_dir.mkdir()

        project_root = tmp_path / "project"
        (project_root / ".git").mkdir(parents=True)
        project_dir = project_root / ".pipelex"
        project_dir.mkdir()

        mocker.patch.object(Path, "home", return_value=fake_home)
        mocker.patch.object(Path, "cwd", return_value=project_root)

        return global_dir, project_dir

    @pytest.fixture
    def secrets_provider(self) -> EnvSecretsProvider:
        return EnvSecretsProvider()

    @pytest.mark.usefixtures("fake_dirs")
    def test_empty_returns_defaults(self, secrets_provider: EnvSecretsProvider) -> None:
        """No config files at any layer → defaults from pydantic model."""
        config = load_telemetry_config(secrets_provider=secrets_provider)

        assert config.langfuse.enabled is False
        assert config.langfuse.public_key is None

    def test_global_config_applies_when_no_project_config(self, fake_dirs: tuple[Path, Path], secrets_provider: EnvSecretsProvider) -> None:
        """Settings declared in ~/.pipelex/telemetry.toml are picked up."""
        global_dir, _ = fake_dirs
        (global_dir / "telemetry.toml").write_text(
            '[langfuse]\nenabled = true\npublic_key = "pk_global"\nsecret_key = "sk_global"\n',
        )

        config = load_telemetry_config(secrets_provider=secrets_provider)

        assert config.langfuse.enabled is True
        assert config.langfuse.public_key == "pk_global"
        assert config.langfuse.secret_key == "sk_global"

    def test_project_config_layers_over_global(self, fake_dirs: tuple[Path, Path], secrets_provider: EnvSecretsProvider) -> None:
        """Keys set only in global telemetry.toml survive when project sets other keys."""
        global_dir, project_dir = fake_dirs
        (global_dir / "telemetry.toml").write_text(
            '[langfuse]\nenabled = true\npublic_key = "pk_global"\nsecret_key = "sk_global"\n',
        )
        (project_dir / "telemetry.toml").write_text(
            '[langfuse]\nendpoint = "https://project.langfuse.example"\n',
        )

        config = load_telemetry_config(secrets_provider=secrets_provider)

        # Project added endpoint without redefining keys → global keys survive.
        assert config.langfuse.enabled is True
        assert config.langfuse.public_key == "pk_global"
        assert config.langfuse.secret_key == "sk_global"
        assert config.langfuse.endpoint == "https://project.langfuse.example"

    def test_project_override_wins_over_global_on_collision(self, fake_dirs: tuple[Path, Path], secrets_provider: EnvSecretsProvider) -> None:
        """When a key is defined at both layers, the project value wins."""
        global_dir, project_dir = fake_dirs
        (global_dir / "telemetry.toml").write_text('[langfuse]\nenabled = true\npublic_key = "pk_global"\n')
        (project_dir / "telemetry.toml").write_text('[langfuse]\npublic_key = "pk_project"\n')

        config = load_telemetry_config(secrets_provider=secrets_provider)

        assert config.langfuse.enabled is True  # from global
        assert config.langfuse.public_key == "pk_project"  # from project

    def test_override_files_layer_after_base_files(self, fake_dirs: tuple[Path, Path], secrets_provider: EnvSecretsProvider) -> None:
        """telemetry_override.toml at either layer wins over telemetry.toml at that layer."""
        global_dir, project_dir = fake_dirs
        (global_dir / "telemetry.toml").write_text('[langfuse]\nenabled = true\npublic_key = "pk_global_base"\n')
        (global_dir / "telemetry_override.toml").write_text('[langfuse]\npublic_key = "pk_global_override"\n')
        (project_dir / "telemetry.toml").write_text('[langfuse]\nsecret_key = "sk_project_base"\n')
        (project_dir / "telemetry_override.toml").write_text('[langfuse]\nsecret_key = "sk_project_override"\n')

        config = load_telemetry_config(secrets_provider=secrets_provider)

        assert config.langfuse.enabled is True  # global base, never overridden
        assert config.langfuse.public_key == "pk_global_override"  # global override beats global base
        assert config.langfuse.secret_key == "sk_project_override"  # project override beats project base

    def test_project_layer_skipped_when_global_equals_project(
        self, tmp_path: Path, mocker: MockerFixture, secrets_provider: EnvSecretsProvider
    ) -> None:
        """When cwd has no .pipelex/, only global layers load (no double-merge of same dir)."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        global_dir = fake_home / ".pipelex"
        global_dir.mkdir()
        (global_dir / "telemetry.toml").write_text('[langfuse]\npublic_key = "pk_global"\n')

        project_root = tmp_path / "project"
        (project_root / ".git").mkdir(parents=True)
        # No project .pipelex/ — project_config_dir resolves to None.

        mocker.patch.object(Path, "home", return_value=fake_home)
        mocker.patch.object(Path, "cwd", return_value=project_root)

        config = load_telemetry_config(secrets_provider=secrets_provider)

        assert config.langfuse.public_key == "pk_global"
