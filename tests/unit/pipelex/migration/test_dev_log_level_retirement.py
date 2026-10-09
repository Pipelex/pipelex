"""The entry that retires the `DEV` log level, exercised on the files it is about.

`DEV` was an enumerated spelling of both `default_log_level` and every level under
`[runtime.log.package_log_levels]`, whose keys are the user's own package names. The entry remaps it to
`DEBUG` at both paths, the second through the `*` key a remap alone may take, and it is `safe` because no
current-valid file can carry the retired spelling. Being `safe`, it is also what a boot replays in memory
over a file still naming `DEV`, so such a file boots at `DEBUG` with a stale-configuration warning rather
than stopping the boot.
"""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.migration.engine import replay_ledger_over_text
from pipelex.migration.ledger import load_ledger, packaged_migration_dir
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.configuration.config_surface import PIPELEX_CONFIG_SURFACE_ID
from pipelex.system.configuration.configs import PipelexConfig
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.log_levels import LogLevel
from pipelex.tools.misc.toml_utils import load_toml_from_content, load_toml_from_path

ENTRY_ID = "pipelex-config@6"

FILE_NAMING_DEV = """\
[runtime.log]
default_log_level = "DEV"

[runtime.log.package_log_levels]
pipelex = "DEV"
my-package = "DEV"
httpx = "WARNING"
"""

FILE_AT_THE_CURRENT_SHAPE = """\
[runtime.log]
default_log_level = "DEBUG"

[runtime.log.package_log_levels]
pipelex = "VERBOSE"
"""


def _base_log_section() -> dict[str, Any]:
    base: dict[str, Any] = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    log_section: dict[str, Any] = base["runtime"]["log"]
    return log_section


class TestTheDevLogLevelRetirement:
    def test_dev_becomes_debug_at_the_root_level_and_under_every_package_key(self) -> None:
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=PIPELEX_CONFIG_SURFACE_ID)
        replay = replay_ledger_over_text(ledger=ledger, text=FILE_NAMING_DEV)

        assert replay.blocked == []
        assert [step.entry_id for step in replay.steps] == [ENTRY_ID]
        migrated: dict[str, Any] = load_toml_from_content(replay.text)
        assert migrated == {
            "runtime": {
                "log": {
                    "default_log_level": "DEBUG",
                    "package_log_levels": {"pipelex": "DEBUG", "my-package": "DEBUG", "httpx": "WARNING"},
                }
            }
        }

    def test_the_migrated_file_is_accepted_by_the_current_model(self) -> None:
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=PIPELEX_CONFIG_SURFACE_ID)
        replay = replay_ledger_over_text(ledger=ledger, text=FILE_NAMING_DEV)
        migrated: dict[str, Any] = load_toml_from_content(replay.text)

        log_config = LogConfig.model_validate({**_base_log_section(), **migrated["runtime"]["log"]})

        assert log_config.default_log_level is LogLevel.DEBUG
        assert log_config.package_log_levels["my-package"] is LogLevel.DEBUG

    def test_the_model_alone_refuses_dev_and_names_the_valid_levels(self) -> None:
        """The refusal the boot's in-memory replay answers: validated without the ledger, `DEV` is no level."""
        unmigrated: dict[str, Any] = load_toml_from_content(FILE_NAMING_DEV)

        with pytest.raises(ValidationError) as exc_info:
            LogConfig.model_validate({**_base_log_section(), **unmigrated["runtime"]["log"]})

        message = str(exc_info.value)
        assert "default_log_level" in message
        for level in ("VERBOSE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "OFF"):
            assert level in message

    def test_a_file_at_the_current_shape_hears_nothing(self) -> None:
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=PIPELEX_CONFIG_SURFACE_ID)
        replay = replay_ledger_over_text(ledger=ledger, text=FILE_AT_THE_CURRENT_SHAPE)

        assert replay.blocked == []
        assert replay.steps == []
        assert replay.text == FILE_AT_THE_CURRENT_SHAPE

    @pytest.mark.usefixtures("no_pipelex_home")
    def test_a_project_file_naming_dev_boots_at_debug_with_a_warning(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Through the boot's own loader: the file is migrated in memory, left as it is on disk, and the warning names the remedy."""
        fake_home = tmp_path / "home"
        (fake_home / ".pipelex").mkdir(parents=True)
        project_root = tmp_path / "project"
        (project_root / ".git").mkdir(parents=True)
        project_dir = project_root / ".pipelex"
        project_dir.mkdir()
        project_file = project_dir / "pipelex.toml"
        project_file.write_text(FILE_NAMING_DEV, encoding="utf-8")
        mocker.patch.object(Path, "home", return_value=fake_home)
        mocker.patch.object(Path, "cwd", return_value=project_root)
        loader = ConfigLoader()

        config = loader.load_config_validated(config_cls=PipelexConfig)

        assert config.runtime.log.default_log_level is LogLevel.DEBUG
        assert config.runtime.log.package_log_levels["pipelex"] is LogLevel.DEBUG
        assert config.runtime.log.package_log_levels["my-package"] is LogLevel.DEBUG
        assert config.runtime.log.package_log_levels["httpx"] is LogLevel.WARNING
        assert project_file.read_text(encoding="utf-8") == FILE_NAMING_DEV, "a boot writes nothing"
        parked = loader.take_stale_configuration_warning()
        assert parked is not None
        assert str(project_file) in parked
        assert "Retire the DEV log level" in parked
        assert "Run `pipelex migrate`" in parked
