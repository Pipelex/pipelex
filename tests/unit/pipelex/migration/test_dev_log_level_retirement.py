"""The entry that retires the `DEV` log level, exercised on the files it is about.

`DEV` was an enumerated spelling of both `default_log_level` and every level under
`[runtime.log.package_log_levels]`, whose keys are the user's own package names. The entry remaps it to
`INFO` at both paths, the second through the `*` key a remap alone may take: a threshold at `DEV` passed
`INFO` and above plus the `DEV` records, and nothing logs at `DEV` any more, so `INFO` passes the same
records, where `DEBUG` would have turned on a third-party library's debug output the file had suppressed.
It is `safe` because no current-valid file can carry the retired spelling. Being `safe`, it is also what a
boot replays in memory over a file still naming `DEV`, so such a file boots at `INFO` with a
stale-configuration warning rather than stopping the boot.
"""

import logging
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
openai = "DEV"
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
    def test_dev_becomes_info_at_the_root_level_and_under_every_package_key(self) -> None:
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=PIPELEX_CONFIG_SURFACE_ID)
        replay = replay_ledger_over_text(ledger=ledger, text=FILE_NAMING_DEV)

        assert replay.blocked == []
        assert [step.entry_id for step in replay.steps] == [ENTRY_ID]
        migrated: dict[str, Any] = load_toml_from_content(replay.text)
        assert migrated == {
            "runtime": {
                "log": {
                    "default_log_level": "INFO",
                    "package_log_levels": {"pipelex": "INFO", "openai": "INFO", "my-package": "INFO", "httpx": "WARNING"},
                }
            }
        }

    def test_the_migrated_file_is_accepted_by_the_current_model(self) -> None:
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=PIPELEX_CONFIG_SURFACE_ID)
        replay = replay_ledger_over_text(ledger=ledger, text=FILE_NAMING_DEV)
        migrated: dict[str, Any] = load_toml_from_content(replay.text)

        log_config = LogConfig.model_validate({**_base_log_section(), **migrated["runtime"]["log"]})

        assert log_config.default_log_level is LogLevel.INFO
        assert log_config.package_log_levels["my-package"] is LogLevel.INFO

    def test_a_third_party_dev_threshold_still_suppresses_debug_after_the_migration(self) -> None:
        """`openai = "DEV"` kept the SDK's DEBUG request dumps, prompts included, out of the log; the migrated level must too."""
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=PIPELEX_CONFIG_SURFACE_ID)
        replay = replay_ledger_over_text(ledger=ledger, text=FILE_NAMING_DEV)
        migrated: dict[str, Any] = load_toml_from_content(replay.text)
        log_config = LogConfig.model_validate({**_base_log_section(), **migrated["runtime"]["log"]})
        openai_level = log_config.package_log_levels["openai"]
        # A logger of this module's own, so the threshold is tried without touching the process's `openai` logger
        third_party_logger = logging.getLogger(f"{__name__}.openai")
        third_party_logger.setLevel(openai_level.int_logging_level)

        assert openai_level.int_logging_level > logging.DEBUG
        assert not third_party_logger.isEnabledFor(logging.DEBUG)
        assert third_party_logger.isEnabledFor(logging.INFO)

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
    def test_a_project_file_naming_dev_boots_at_info_with_a_warning(self, tmp_path: Path, mocker: MockerFixture) -> None:
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

        assert config.runtime.log.default_log_level is LogLevel.INFO
        assert config.runtime.log.package_log_levels["pipelex"] is LogLevel.INFO
        assert config.runtime.log.package_log_levels["openai"] is LogLevel.INFO
        assert config.runtime.log.package_log_levels["my-package"] is LogLevel.INFO
        assert config.runtime.log.package_log_levels["httpx"] is LogLevel.WARNING
        assert project_file.read_text(encoding="utf-8") == FILE_NAMING_DEV, "a boot writes nothing"
        parked = loader.take_stale_configuration_warning()
        assert parked is not None
        (stale_file,) = parked.files
        assert stale_file.file_path == project_file
        assert any("Retire the DEV log level" in step for step in stale_file.migration_steps)
        assert stale_file.is_reached_by_migrate
