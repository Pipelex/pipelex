"""The entry that retires the rich-or-poor log mode, exercised on the files it is about.

It is `unsafe`, so it is reported and never applied: `is_console_logging_enabled = false` chose silence,
the new model expresses that silence as a value, no operation in this vocabulary writes one, and deleting
the key would hand a deployment that deliberately suppressed its console output back its console output on
the strength of an upgrade alone. So a file carrying any of the retired keys keeps them, the model refuses
them, and the operator writes the replacement the entry names. The recipe it names for silence is checked
against the code, since the base pins the `pipelex` logger and the root level alone would silence none of
Pipelex's records.
"""

import logging
from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.migration.engine import replay_ledger_over_text
from pipelex.migration.ledger import load_ledger, packaged_migration_dir
from pipelex.migration.plan import BlockedEntryReason
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.configuration.config_surface import PIPELEX_CONFIG_SURFACE_ID
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import load_toml_from_content, load_toml_from_path

ENTRY_ID = "pipelex-config@5"

FILE_IN_POOR_MODE = """\
[runtime.log]
default_log_level = "INFO"
log_mode = "poor"
is_console_logging_enabled = false
poor_loggers = ["pipelex"]
generic_poor_logger = "#poor-log"
"""

FILE_AT_THE_CURRENT_SHAPE = """\
[runtime.log]
default_log_level = "INFO"
sink = "json"
"""


class TestTheLogModeRetirement:
    def test_the_retired_keys_are_kept_and_the_entry_is_reported_as_blocked(self) -> None:
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=PIPELEX_CONFIG_SURFACE_ID)
        replay = replay_ledger_over_text(ledger=ledger, text=FILE_IN_POOR_MODE)

        assert replay.steps == []
        (blocked,) = replay.blocked
        assert blocked.entry_id == ENTRY_ID
        assert blocked.reason is BlockedEntryReason.UNSAFE
        migrated: dict[str, Any] = load_toml_from_content(replay.text)
        assert migrated["runtime"]["log"]["is_console_logging_enabled"] is False

    def test_the_suppressed_console_is_not_handed_back_by_the_upgrade_alone(self) -> None:
        """The defect this entry's safety answers: a silent deletion would leave the file valid, and loud again."""
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=PIPELEX_CONFIG_SURFACE_ID)
        replay = replay_ledger_over_text(ledger=ledger, text=FILE_IN_POOR_MODE)
        migrated: dict[str, Any] = load_toml_from_content(replay.text)
        base: dict[str, Any] = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")

        with pytest.raises(ValidationError, match="is_console_logging_enabled"):
            LogConfig.model_validate({**base["runtime"]["log"], **migrated["runtime"]["log"]})

    def test_the_blocked_entry_a_person_sees_names_what_they_set_by_hand(self) -> None:
        """A blocked entry reaches its reader through its guidance — its title and description do not — so the recipes live there."""
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=PIPELEX_CONFIG_SURFACE_ID)
        replay = replay_ledger_over_text(ledger=ledger, text=FILE_IN_POOR_MODE)

        (blocked,) = replay.blocked
        assert blocked.guidance is not None
        assert 'sink = "json"' in blocked.guidance
        assert 'pipelex = "OFF"' in blocked.guidance
        assert "is_console_logging_enabled" in blocked.guidance

    def test_the_silencing_recipe_the_entry_names_silences_every_pipelex_logger(self) -> None:
        """``default_log_level`` governs only what the package levels do not pin, and the base pins ``pipelex``: the recipe is the package level."""
        base: dict[str, Any] = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
        merged = deepcopy(base["runtime"]["log"])
        deep_update(merged, updates={"package_log_levels": {"pipelex": "OFF"}})
        fresh = Log()
        fresh.configure(log_config=LogConfig.model_validate(merged))
        try:
            assert not logging.getLogger("pipelex").isEnabledFor(logging.CRITICAL)
            assert not logging.getLogger("pipelex.pipe_operators.pipe_llm").isEnabledFor(logging.CRITICAL)
            assert logging.getLogger("httpx").isEnabledFor(logging.WARNING)
        finally:
            fresh.reset()

    def test_a_file_at_the_current_shape_hears_nothing(self) -> None:
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=PIPELEX_CONFIG_SURFACE_ID)
        replay = replay_ledger_over_text(ledger=ledger, text=FILE_AT_THE_CURRENT_SHAPE)

        assert replay.blocked == []
        assert replay.steps == []
        assert replay.text is FILE_AT_THE_CURRENT_SHAPE
