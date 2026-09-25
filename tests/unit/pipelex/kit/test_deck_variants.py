"""Parity guard for the parked deck variants under `pipelex/kit/deck_variants/`.

Nothing loads a variant at runtime, so nothing else would notice it rotting. This module loads
every variant through the same loader the runtime uses and holds it to the shipped deck two ways:

- the same alias, preset and waterfall names, per model family, except for the names the shipped
  deck deliberately dropped, which are listed here by variant;
- every model handle the variant names and the shipped deck does not is still declared by one of
  the kit's backend files, because handle retirement is how a parked deck actually goes stale.

The second check is scoped to the handles only the variant names. A handle the shipped deck names
too is already exercised at boot, and some of those are gateway-served with no backend section of
their own, so holding them to a backend declaration would fail on a deck that is perfectly live.
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
from pipelex.cogt.models.model_reference import ModelReference, ModelReferenceKind
from pipelex.kit.paths import get_kit_configs_dir, get_kit_deck_variants_dir
from pipelex.tools.misc.toml_utils import load_toml_from_path

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


def list_declared_backend_handles() -> set[str]:
    """Every model handle the kit's backend files declare. Each top-level table is one, bar `defaults`."""
    backends_dir = Path(str(get_kit_configs_dir())) / "inference" / "backends"
    handles: set[str] = set()
    for backend_path in sorted(backends_dir.glob("*.toml")):
        backend_dict = load_toml_from_path(str(backend_path))
        handles.update(name for name, value in backend_dict.items() if isinstance(value, dict) and name != "defaults")
    return handles


def extract_model_handles(blueprint: ModelDeckBlueprint) -> set[str]:
    """Every concrete handle a deck names, from its alias targets, its waterfall entries and its presets' models.

    A reference naming an alias, a preset or a waterfall carries no handle of its own: it resolves
    through one of the three collections this function reads directly. A waterfall's own entries do
    carry handles, which is why they are read here and not only through whatever names the waterfall.
    """
    family_blueprints: list[DeckFamilyBlueprint] = [blueprint.llm, blueprint.extract, blueprint.img_gen, blueprint.search]
    references: list[str] = []
    for family_blueprint in family_blueprints:
        references.extend(family_blueprint.aliases.values())
        for waterfall_entries in family_blueprint.waterfalls.values():
            references.extend(waterfall_entries)
        references.extend(setting.model for setting in family_blueprint.presets.values())
    handles: set[str] = set()
    for reference in references:
        parsed = ModelReference.parse(reference)
        match parsed.kind:
            case ModelReferenceKind.HANDLE:
                handles.add(parsed.name)
            case ModelReferenceKind.ALIAS | ModelReferenceKind.WATERFALL | ModelReferenceKind.PRESET:
                continue
    return handles


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

    @pytest.mark.parametrize("variant_dir", list_variant_dirs(), ids=lambda path: path.name)
    def test_variant_only_handles_are_still_declared_by_a_backend(self, variant_dir: Path):
        """Name parity says nothing about a handle that was retired from the backends underneath it."""
        managed_filenames = list(list_managed_kit_files())
        shipped_handles = extract_model_handles(load_deck_from_dir(kit_deck_dir(), filenames=managed_filenames))
        variant_handles = extract_model_handles(load_deck_from_dir(variant_dir, filenames=managed_filenames))

        variant_only_handles = variant_handles - shipped_handles
        assert variant_only_handles, f"Variant '{variant_dir.name}' names no handle of its own, which makes this guard vacuous"

        declared_handles = list_declared_backend_handles()
        undeclared = sorted(handle for handle in variant_only_handles if handle not in declared_handles)
        assert not undeclared, f"Variant '{variant_dir.name}' names handles no backend file declares any more: {', '.join(undeclared)}"

    def test_handle_collection_reads_waterfall_entries(self):
        """A handle a deck names only inside a waterfall must still reach the retirement check above.

        No deck declares a waterfall today, so nothing else in this module would notice the
        collector skipping them, and the guard would go quietly blind the moment one does.
        """
        blueprint = load_deck_from_dir(kit_deck_dir(), filenames=list(list_managed_kit_files()))
        probe_handle = "handle-named-only-by-a-waterfall"
        assert probe_handle not in extract_model_handles(blueprint)

        blueprint.llm.waterfalls["waterfall-parity-probe"] = [probe_handle]
        assert probe_handle in extract_model_handles(blueprint), "A handle named inside a waterfall escaped the handle collection"

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
