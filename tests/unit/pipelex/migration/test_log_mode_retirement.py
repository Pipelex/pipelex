"""The entry that retires the rich-or-poor log mode, exercised on the files it is about.

It deletes the four retired keys and is `safe`, so a full copy of an older base file, which carries every
one of them at its old default, migrates in one run. What it cannot do is written where a person reads
it: a file that had set `log_mode = "poor"` or `is_console_logging_enabled = false` chose a behaviour the
deletion undoes, no operation in the vocabulary writes the replacement, and the title names it. The recipe
it names for silence is checked against the code, since the base pins the `pipelex` logger and the root
level alone would silence none of Pipelex's records.
"""

import logging
from copy import deepcopy
from typing import Any

from pipelex.migration.engine import replay_ledger_over_text
from pipelex.migration.ledger import load_ledger, packaged_migration_dir
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
    def test_the_retired_keys_are_deleted_and_the_rest_of_the_section_is_kept(self) -> None:
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=PIPELEX_CONFIG_SURFACE_ID)
        replay = replay_ledger_over_text(ledger=ledger, text=FILE_IN_POOR_MODE)

        assert replay.blocked == []
        assert [step.entry_id for step in replay.steps] == [ENTRY_ID]
        migrated: dict[str, Any] = load_toml_from_content(replay.text)
        assert migrated == {"runtime": {"log": {"default_log_level": "INFO"}}}

    def test_the_step_a_person_sees_names_what_a_poor_mode_file_sets_by_hand(self) -> None:
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=PIPELEX_CONFIG_SURFACE_ID)
        replay = replay_ledger_over_text(ledger=ledger, text=FILE_IN_POOR_MODE)

        (step,) = replay.steps
        assert 'sink = "json"' in step.title
        assert 'pipelex = "OFF"' in step.title
        assert 'sink = "json"' in step.description
        assert 'pipelex = "OFF"' in step.description

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

    def test_the_migrated_file_is_accepted_by_the_current_model_and_lands_on_the_console_sink(self) -> None:
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=PIPELEX_CONFIG_SURFACE_ID)
        replay = replay_ledger_over_text(ledger=ledger, text=FILE_IN_POOR_MODE)
        migrated: dict[str, Any] = load_toml_from_content(replay.text)
        base: dict[str, Any] = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")

        log_config = LogConfig.model_validate({**base["runtime"]["log"], **migrated["runtime"]["log"]})

        assert log_config.sink == "console"

    def test_a_file_at_the_current_shape_hears_nothing(self) -> None:
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=PIPELEX_CONFIG_SURFACE_ID)
        replay = replay_ledger_over_text(ledger=ledger, text=FILE_AT_THE_CURRENT_SHAPE)

        assert replay.blocked == []
        assert replay.steps == []
        assert replay.text is FILE_AT_THE_CURRENT_SHAPE
