"""A deck installed before the judgment family existed still loads.

``pipelex update`` is the only thing that installs a new deck file, and nothing runs it at boot,
so every project and global deck predating ``5_judgment_deck.toml`` reaches the loader without a
``judgment`` section. That absence has to read as "no judgment model", which is what the kit's own
empty section says, rather than fail every boot.
"""

from pathlib import Path

from pipelex.cogt.models.model_deck_loader import load_model_deck_blueprint
from pipelex.kit.paths import get_kit_configs_dir

JUDGMENT_DECK_FILE_NAME = "5_judgment_deck.toml"


class TestModelDeckLoaderJudgment:
    def _kit_deck_paths(self) -> list[str]:
        deck_dir = Path(str(get_kit_configs_dir())) / "inference" / "deck"
        return sorted(str(path) for path in deck_dir.glob("*.toml"))

    def test_a_deck_without_the_judgment_file_loads_with_no_judgment_model(self) -> None:
        deck_paths = [path for path in self._kit_deck_paths() if not path.endswith(JUDGMENT_DECK_FILE_NAME)]
        assert len(deck_paths) < len(self._kit_deck_paths()), "the kit deck no longer ships the judgment file this test removes"

        blueprint = load_model_deck_blueprint(model_deck_paths=deck_paths)

        assert blueprint.judgment.aliases == {}
        assert blueprint.judgment.presets == {}
        assert blueprint.judgment.waterfalls == {}
        assert blueprint.judgment.choice_default is None
