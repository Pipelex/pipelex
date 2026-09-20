"""Parity guard for the parked deck variants under `pipelex/kit/deck_variants/`.

Nothing loads a variant at runtime, so nothing else would notice it rotting. This module loads
every variant through the same loader the runtime uses and asserts that it defines exactly the
same alias, preset and waterfall names, per model family, as the deck the kit ships — except for
the names the shipped deck deliberately dropped, which are listed here by variant.
"""

from collections.abc import Mapping
from pathlib import Path

import pytest

from pipelex.cogt.models.deck_manifest import kit_deck_dir, list_managed_kit_files
from pipelex.cogt.models.model_deck import (
    ExtractDeckBlueprint,
    ImgGenDeckBlueprint,
    LLMDeckBlueprint,
    ModelDeckBlueprint,
    SearchDeckBlueprint,
)
from pipelex.cogt.models.model_deck_loader import load_model_deck_blueprint
from pipelex.kit.paths import get_kit_deck_variants_dir

# A vocabulary coordinate: the model family, then the kind of name within it.
DeckFamilyBlueprint = LLMDeckBlueprint | ExtractDeckBlueprint | ImgGenDeckBlueprint | SearchDeckBlueprint
VocabularyKey = tuple[str, str]
Vocabulary = dict[VocabularyKey, set[str]]
PermittedDrops = Mapping[VocabularyKey, frozenset[str]]

# Names the shipped deck deliberately no longer defines, per variant directory. Each one must be
# present in the variant and absent from the shipped deck, so an entry that goes stale fails too.
# A variant absent from this mapping is held to strict equality.
PERMITTED_DROPS_BY_VARIANT: dict[str, PermittedDrops] = {
    "multi_provider": {
        ("llm", "aliases"): frozenset({"best-claude", "best-gemini", "best-mistral"}),
        ("img_gen", "aliases"): frozenset({"best-gemini"}),
    },
}


def list_variant_dirs() -> list[Path]:
    """Every parked variant directory, sorted, skipping Python cruft."""
    variants_root = Path(str(get_kit_deck_variants_dir()))
    return sorted(entry for entry in variants_root.iterdir() if entry.is_dir() and not entry.name.startswith("__"))


def extract_vocabulary(blueprint: ModelDeckBlueprint) -> Vocabulary:
    """The alias, preset and waterfall names a deck defines, per model family."""
    family_blueprints: dict[str, DeckFamilyBlueprint] = {
        "llm": blueprint.llm,
        "extract": blueprint.extract,
        "img_gen": blueprint.img_gen,
        "search": blueprint.search,
    }
    vocabulary: Vocabulary = {}
    for family, family_blueprint in family_blueprints.items():
        vocabulary[family, "aliases"] = set(family_blueprint.aliases)
        vocabulary[family, "presets"] = set(family_blueprint.presets)
        vocabulary[family, "waterfalls"] = set(family_blueprint.waterfalls)
    return vocabulary


def compare_vocabularies(*, shipped: Vocabulary, variant: Vocabulary, permitted_drops: PermittedDrops) -> list[str]:
    """Every way the variant's vocabulary differs from the shipped deck's, as readable sentences."""
    differences: list[str] = []
    for key in sorted(shipped.keys() | variant.keys()):
        family, kind = key
        shipped_names = shipped.get(key, set())
        variant_names = variant.get(key, set())
        dropped = permitted_drops.get(key, frozenset())

        for name in sorted(dropped):
            if name not in variant_names:
                differences.append(f"{family}.{kind}: '{name}' is a permitted drop but the variant does not define it")
            if name in shipped_names:
                differences.append(f"{family}.{kind}: '{name}' is a permitted drop but the shipped deck still defines it")
        for name in sorted(shipped_names - variant_names):
            differences.append(f"{family}.{kind}: '{name}' is in the shipped deck but missing from the variant")
        for name in sorted(variant_names - shipped_names - dropped):
            differences.append(f"{family}.{kind}: '{name}' is in the variant but not in the shipped deck, and is not a permitted drop")
    return differences


def load_deck_from_dir(deck_dir: Path, *, filenames: list[str]) -> ModelDeckBlueprint:
    """Load the named deck files from a directory, the way the runtime loads a deck."""
    return load_model_deck_blueprint([str(deck_dir / filename) for filename in sorted(filenames)])


def make_vocabulary(*, aliases: set[str], presets: set[str]) -> Vocabulary:
    """A minimal single-family vocabulary, for the comparator's own tests."""
    return {("llm", "aliases"): aliases, ("llm", "presets"): presets, ("llm", "waterfalls"): set()}


class TestDeckVariants:
    def test_at_least_one_variant_exists(self):
        """Without this, the parametrized parity test would pass by running zero cases."""
        assert list_variant_dirs(), "No deck variant found under pipelex/kit/deck_variants/"

    @pytest.mark.parametrize("variant_dir", list_variant_dirs(), ids=lambda path: path.name)
    def test_variant_ships_the_same_deck_files(self, variant_dir: Path):
        variant_filenames = {entry.name for entry in variant_dir.iterdir() if entry.is_file() and entry.suffix == ".toml"}
        assert variant_filenames == set(list_managed_kit_files()), (
            f"Variant '{variant_dir.name}' does not hold the same numbered deck files as the kit's shipped deck"
        )

    @pytest.mark.parametrize("variant_dir", list_variant_dirs(), ids=lambda path: path.name)
    def test_variant_matches_the_shipped_vocabulary(self, variant_dir: Path):
        managed_filenames = list(list_managed_kit_files())
        shipped_blueprint = load_deck_from_dir(kit_deck_dir(), filenames=managed_filenames)
        variant_blueprint = load_deck_from_dir(variant_dir, filenames=managed_filenames)

        differences = compare_vocabularies(
            shipped=extract_vocabulary(shipped_blueprint),
            variant=extract_vocabulary(variant_blueprint),
            permitted_drops=PERMITTED_DROPS_BY_VARIANT.get(variant_dir.name, {}),
        )
        assert not differences, f"Variant '{variant_dir.name}' has drifted from the shipped deck:\n" + "\n".join(differences)

    def test_comparator_reports_a_preset_the_variant_is_missing(self):
        differences = compare_vocabularies(
            shipped=make_vocabulary(aliases={"default-general"}, presets={"writing-factual", "vision"}),
            variant=make_vocabulary(aliases={"default-general"}, presets={"writing-factual"}),
            permitted_drops={},
        )
        assert differences == ["llm.presets: 'vision' is in the shipped deck but missing from the variant"]

    def test_comparator_reports_an_alias_only_the_variant_has(self):
        differences = compare_vocabularies(
            shipped=make_vocabulary(aliases={"default-general"}, presets=set()),
            variant=make_vocabulary(aliases={"default-general", "best-claude"}, presets=set()),
            permitted_drops={},
        )
        assert differences == ["llm.aliases: 'best-claude' is in the variant but not in the shipped deck, and is not a permitted drop"]

    def test_comparator_accepts_a_declared_drop(self):
        differences = compare_vocabularies(
            shipped=make_vocabulary(aliases={"default-general"}, presets=set()),
            variant=make_vocabulary(aliases={"default-general", "best-claude"}, presets=set()),
            permitted_drops={("llm", "aliases"): frozenset({"best-claude"})},
        )
        assert differences == []

    def test_comparator_reports_a_drop_the_shipped_deck_still_defines(self):
        differences = compare_vocabularies(
            shipped=make_vocabulary(aliases={"default-general", "best-claude"}, presets=set()),
            variant=make_vocabulary(aliases={"default-general", "best-claude"}, presets=set()),
            permitted_drops={("llm", "aliases"): frozenset({"best-claude"})},
        )
        assert differences == ["llm.aliases: 'best-claude' is a permitted drop but the shipped deck still defines it"]

    def test_comparator_reports_a_drop_the_variant_does_not_define(self):
        differences = compare_vocabularies(
            shipped=make_vocabulary(aliases={"default-general"}, presets=set()),
            variant=make_vocabulary(aliases={"default-general"}, presets=set()),
            permitted_drops={("llm", "aliases"): frozenset({"best-mistral"})},
        )
        assert differences == ["llm.aliases: 'best-mistral' is a permitted drop but the variant does not define it"]
