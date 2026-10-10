"""A `pipelex.toml` member of the wrong type fails the config load with the loader's own error.

The boot catches the loader's `ConfigValidationError`; a bare `AttributeError` raised by a `mode="before"`
validator used to escape it.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.system.configuration.config_loader import CONFIG_NAME, ConfigLoader
from pipelex.system.configuration.configs import PipelexConfig
from pipelex.system.exceptions import ConfigValidationError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.mark.usefixtures("no_pipelex_home")
class TestTheConfigLoadReportsAWrongTypedMember:
    def test_a_project_file_with_a_scalar_package_log_levels_fails_the_load_with_the_loaders_error(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        fake_home = tmp_path / "home"
        (fake_home / ".pipelex").mkdir(parents=True)
        project_root = tmp_path / "project"
        (project_root / ".git").mkdir(parents=True)
        (project_root / ".pipelex").mkdir()
        (project_root / ".pipelex" / CONFIG_NAME).write_text('[runtime.log]\npackage_log_levels = "x"\n', encoding="utf-8")
        mocker.patch.object(Path, "home", return_value=fake_home)
        mocker.patch.object(Path, "cwd", return_value=project_root)

        with pytest.raises(ConfigValidationError, match="package_log_levels"):
            ConfigLoader().load_config_validated(config_cls=PipelexConfig)
