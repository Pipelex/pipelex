import tomllib

from pipelex.config import get_config
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.misc.toml_utils import load_toml_from_path


class TestInlineTextThreshold:
    def test_the_shipped_defaults_keep_texts_up_to_four_kib_inline(self) -> None:
        """The package default and the template a project starts from both set the ratified 4 KiB."""
        shipped_config = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
        kit_config = tomllib.loads((get_kit_configs_dir() / "pipelex.toml").read_text(encoding="utf-8"))

        assert shipped_config["runtime"]["storage"]["inline_text_max_bytes"] == 4096
        assert kit_config["runtime"]["storage"]["inline_text_max_bytes"] == 4096

    def test_the_unit_tests_store_every_text(self) -> None:
        """At 0 every non-empty text is past the threshold, so the reference path runs in every test."""
        assert get_config().runtime.storage.inline_text_max_bytes == 0
