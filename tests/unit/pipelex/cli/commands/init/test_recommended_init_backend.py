"""The backend `pipelex init` recommends serves every default tier of the shipped model deck.

Accepting the recommendation enables that backend alone and routes every model to it, so a default
alias it does not serve fails the first method that uses it, with a valid key in hand.
"""

from pathlib import Path

import pytest

from pipelex.cli.commands.init.ui.backends_ui import RECOMMENDED_INIT_BACKEND
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.tools.misc.toml_utils import load_toml_from_path

# The deck families a single provider key serves; search, extraction, judgment and document
# generation default to dedicated backends whichever key the user holds.
DECK_FILE_BY_FAMILY = {
    "llm": "1_llm_deck.toml",
    "img_gen": "2_img_gen_deck.toml",
}


def _inference_dir() -> Path:
    return Path(str(get_kit_configs_dir())) / "inference"


def _recommended_backend_handles() -> set[str]:
    backend_doc = load_toml_from_path(_inference_dir() / "backends" / f"{RECOMMENDED_INIT_BACKEND}.toml")
    return {handle for handle in backend_doc if handle != "defaults"}


class TestRecommendedInitBackend:
    @pytest.mark.parametrize(("family", "deck_file"), DECK_FILE_BY_FAMILY.items())
    def test_serves_every_default_alias_of_the_deck(self, family: str, deck_file: str) -> None:
        deck_doc = load_toml_from_path(_inference_dir() / "deck" / deck_file)
        aliases: dict[str, str] = deck_doc[family]["aliases"]
        default_targets = {alias: target for alias, target in aliases.items() if alias.startswith("default-")}
        assert default_targets, f"the {family} deck declares no default alias"

        served = _recommended_backend_handles()
        unserved = {alias: target for alias, target in default_targets.items() if target not in served}
        assert not unserved, f"'{RECOMMENDED_INIT_BACKEND}' serves none of these {family} defaults: {unserved}"

    def test_is_a_backend_the_template_lists(self) -> None:
        template_doc = load_toml_from_path(_inference_dir() / "backends.toml")
        assert RECOMMENDED_INIT_BACKEND in template_doc
