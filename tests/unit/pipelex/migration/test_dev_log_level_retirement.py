"""The entry that retires the `DEV` log level, exercised on the files it is about.

`DEV` was an enumerated spelling of both `default_log_level` and every level under
`[runtime.log.package_log_levels]`, whose keys are the user's own package names. The entry remaps it to
`DEBUG` at both paths, the second through the `*` key a remap alone may take, and it is `safe` because no
current-valid file can carry the retired spelling.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.migration.engine import replay_ledger_over_text
from pipelex.migration.ledger import load_ledger, packaged_migration_dir
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.configuration.config_surface import PIPELEX_CONFIG_SURFACE_ID
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

    def test_an_unmigrated_file_is_refused_with_the_valid_levels_named(self) -> None:
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
        assert replay.text is FILE_AT_THE_CURRENT_SHAPE
