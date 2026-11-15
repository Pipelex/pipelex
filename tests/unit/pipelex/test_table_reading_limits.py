from pytest_mock import MockerFixture

from pipelex.config import TABLE_READING_FALLBACK, get_config, table_reading_limits
from pipelex.runtime_hub import RuntimeHub
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.misc.toml_utils import load_toml_from_path


class TestTableReadingLimits:
    def test_the_fallback_is_the_value_the_shipped_config_sets(self) -> None:
        """The limits a process without a config reads a spreadsheet under are the shipped defaults, so the two cannot drift apart."""
        shipped_config = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")

        assert shipped_config["runtime"]["table_reading"] == TABLE_READING_FALLBACK.model_dump()

    def test_without_a_config_the_limits_still_hold(self, mocker: MockerFixture) -> None:
        mocker.patch.object(RuntimeHub, "_instance", None)

        assert table_reading_limits() == TABLE_READING_FALLBACK

    def test_a_loaded_config_sets_the_limits(self, mocker: MockerFixture) -> None:
        mocker.patch.object(get_config().runtime.table_reading, "max_table_cells", 1234)

        assert table_reading_limits().max_table_cells == 1234
