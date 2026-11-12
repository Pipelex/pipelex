from pytest_mock import MockerFixture

from pipelex.config import FETCH_MAX_BYTES_FALLBACK, fetch_max_bytes, get_config
from pipelex.runtime_hub import RuntimeHub
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.misc.toml_utils import load_toml_from_path


class TestFetchMaxBytes:
    def test_the_fallback_is_the_value_the_shipped_config_sets(self) -> None:
        """The cap a process without a config fetches under is the shipped default, so the two cannot drift apart."""
        shipped_config = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")

        assert shipped_config["runtime"]["network"]["max_fetch_bytes"] == FETCH_MAX_BYTES_FALLBACK

    def test_without_a_config_the_cap_still_holds(self, mocker: MockerFixture) -> None:
        """A process that fetches before, or without, loading the config fails closed: the fetch is capped."""
        mocker.patch.object(RuntimeHub, "_instance", None)

        assert fetch_max_bytes() == FETCH_MAX_BYTES_FALLBACK

    def test_a_loaded_config_sets_the_cap(self, mocker: MockerFixture) -> None:
        mocker.patch.object(get_config().runtime.network, "max_fetch_bytes", 1234)

        assert fetch_max_bytes() == 1234
