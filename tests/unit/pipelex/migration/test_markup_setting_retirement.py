"""The entry that retires `is_markup_enabled`, exercised on the files it is about.

The console reads no log message as Rich markup, so the `[runtime.log.rich_log]` key that switched it is gone and
the entry deletes it, whichever value the file gave. It is `safe`, so it is also what a boot replays in memory over
a file still setting the key: such a file boots with a stale-configuration warning rather than stopping the boot.
"""

from pathlib import Path
from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.migration.engine import replay_ledger_over_text
from pipelex.migration.ledger import load_ledger, packaged_migration_dir
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.configuration.config_surface import PIPELEX_CONFIG_SURFACE_ID
from pipelex.system.configuration.configs import PipelexConfig
from pipelex.tools.misc.toml_utils import load_toml_from_content

ENTRY_ID = "pipelex-config@7"

FILE_SETTING_MARKUP = """\
[runtime.log.rich_log]
is_show_time = true
is_markup_enabled = false
"""


class TestTheMarkupSettingRetirement:
    @pytest.mark.parametrize("value", ["true", "false"])
    def test_the_key_is_deleted_and_its_neighbours_kept(self, value: str) -> None:
        ledger = load_ledger(migration_dir=packaged_migration_dir(), surface_id=PIPELEX_CONFIG_SURFACE_ID)
        replay = replay_ledger_over_text(ledger=ledger, text=f"[runtime.log.rich_log]\nis_show_time = true\nis_markup_enabled = {value}\n")

        assert replay.blocked == []
        assert [step.entry_id for step in replay.steps] == [ENTRY_ID]
        migrated: dict[str, Any] = load_toml_from_content(replay.text)
        assert migrated == {"runtime": {"log": {"rich_log": {"is_show_time": True}}}}

    @pytest.mark.usefixtures("no_pipelex_home")
    def test_a_project_file_setting_the_key_boots_with_a_warning(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Through the boot's own loader: the file is migrated in memory, left as it is on disk, and the warning names the remedy."""
        fake_home = tmp_path / "home"
        (fake_home / ".pipelex").mkdir(parents=True)
        project_root = tmp_path / "project"
        (project_root / ".git").mkdir(parents=True)
        project_dir = project_root / ".pipelex"
        project_dir.mkdir()
        project_file = project_dir / "pipelex.toml"
        project_file.write_text(FILE_SETTING_MARKUP, encoding="utf-8")
        mocker.patch.object(Path, "home", return_value=fake_home)
        mocker.patch.object(Path, "cwd", return_value=project_root)
        loader = ConfigLoader()

        config = loader.load_config_validated(config_cls=PipelexConfig)

        assert config.runtime.log.rich_log.is_show_time is True
        assert "is_markup_enabled" not in type(config.runtime.log.rich_log).model_fields
        assert project_file.read_text(encoding="utf-8") == FILE_SETTING_MARKUP, "a boot writes nothing"
        parked = loader.take_stale_configuration_warning()
        assert parked is not None
        assert str(project_file) in parked
        assert "The console reads no log message as markup" in parked
        assert "Run `pipelex migrate`" in parked
