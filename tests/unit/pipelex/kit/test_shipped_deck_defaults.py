"""Every default alias of the shipped deck reaches a model that one of the kit's own backend files declares, as its family's type.

Boot only checks that an alias exists, not that anything serves what it names, so a default whose every
candidate is served through a Pipelex-managed service alone loads cleanly and then fails the first pipe
that relies on it, for everyone running on their own keys. A waterfall passes when any one of its entries
is declared, which is how a default can put a managed model first and still resolve without it. A handle
names one model per model type, so a default reaches a model only through a handle declared as the type
its family asks for: a judgment default naming a handle the kit declares only as an LLM serves nothing.
"""

import pytest

from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.deck_manifest import KitManagedArea, kit_deck_dir, list_managed_kit_files
from pipelex.cogt.models.model_deck import JudgmentDeckBlueprint
from pipelex.cogt.models.model_reference import ModelReference, ModelReferenceKind
from tests.unit.pipelex.kit.test_deck_variants import (
    FAMILY_MODEL_TYPES,
    DeckFamilyBlueprint,
    DeclaredModel,
    list_declared_backend_models,
    load_deck_from_dir,
)

DEFAULT_ALIAS_PREFIX = "default-"

AnyFamilyBlueprint = DeckFamilyBlueprint | JudgmentDeckBlueprint


def _shipped_family_blueprints() -> dict[str, AnyFamilyBlueprint]:
    blueprint = load_deck_from_dir(kit_deck_dir(), filenames=list(list_managed_kit_files(area=KitManagedArea.DECK)))
    return {
        "llm": blueprint.llm,
        "extract": blueprint.extract,
        "img_gen": blueprint.img_gen,
        "search": blueprint.search,
        "doc_gen": blueprint.doc_gen,
        "judgment": blueprint.judgment,
    }


def _candidate_handles(reference: str, *, family_blueprint: AnyFamilyBlueprint, visited: frozenset[str]) -> set[str]:
    """The concrete handles a reference can resolve to, following aliases and every entry of a waterfall."""
    if reference in visited:
        return set()
    visited |= {reference}
    parsed = ModelReference.parse(reference)
    match parsed.kind:
        case ModelReferenceKind.ALIAS:
            return _candidate_handles(family_blueprint.aliases[parsed.name], family_blueprint=family_blueprint, visited=visited)
        case ModelReferenceKind.WATERFALL:
            candidates: set[str] = set()
            for entry in family_blueprint.waterfalls[parsed.name]:
                candidates |= _candidate_handles(entry, family_blueprint=family_blueprint, visited=visited)
            return candidates
        case ModelReferenceKind.PRESET:
            return _candidate_handles(family_blueprint.presets[parsed.name].model, family_blueprint=family_blueprint, visited=visited)
        case ModelReferenceKind.HANDLE:
            return {parsed.name}


def _unserved_default(*, family: str, alias: str, family_blueprint: AnyFamilyBlueprint, declared_models: set[DeclaredModel]) -> str | None:
    """Why a default alias of this family reaches no model a kit backend declares as the family's type, or `None` when it reaches one."""
    model_type = FAMILY_MODEL_TYPES[family]
    candidates = _candidate_handles(f"@{alias}", family_blueprint=family_blueprint, visited=frozenset())
    if any((model_type, candidate) in declared_models for candidate in candidates):
        return None
    return f"{family} alias '{alias}' can only resolve to {sorted(candidates)}, which no backend file of the kit declares as '{model_type}'"


def _default_aliases() -> list[tuple[str, str]]:
    return [
        (family, alias)
        for family, family_blueprint in _shipped_family_blueprints().items()
        for alias in family_blueprint.aliases
        if alias.startswith(DEFAULT_ALIAS_PREFIX)
    ]


class TestShippedDeckDefaults:
    @pytest.mark.parametrize(("family", "alias"), _default_aliases())
    def test_default_alias_reaches_a_declared_model(self, family: str, alias: str) -> None:
        unserved = _unserved_default(
            family=family, alias=alias, family_blueprint=_shipped_family_blueprints()[family], declared_models=list_declared_backend_models()
        )
        assert unserved is None, unserved

    def test_a_judgment_default_naming_a_handle_the_kit_declares_only_as_an_llm_is_refused(self) -> None:
        """The guard must not count a handle's LLM spec for the judgment family, which asks for a judgment model."""
        declared_models = list_declared_backend_models()
        llm_only_handle = next(
            handle
            for model_type, handle in sorted(declared_models)
            if model_type == ModelType.LLM and (ModelType.JUDGMENT, handle) not in declared_models
        )
        judgment_blueprint = JudgmentDeckBlueprint(aliases={"default-probe": llm_only_handle})

        unserved = _unserved_default(family="judgment", alias="default-probe", family_blueprint=judgment_blueprint, declared_models=declared_models)
        assert unserved is not None
        assert llm_only_handle in unserved
        assert _unserved_default(family="llm", alias="default-probe", family_blueprint=judgment_blueprint, declared_models=declared_models) is None

    def test_a_waterfall_is_read_through_every_entry(self) -> None:
        """The waterfall branch must see past a first entry no backend file declares, or the guard reads it as unserved."""
        extract_blueprint = _shipped_family_blueprints()["extract"]
        extract_blueprint.waterfalls["probe-waterfall"] = ["model-no-backend-declares", "pypdfium2-extract-pdf"]

        candidates = _candidate_handles("~probe-waterfall", family_blueprint=extract_blueprint, visited=frozenset())

        assert candidates == {"model-no-backend-declares", "pypdfium2-extract-pdf"}
