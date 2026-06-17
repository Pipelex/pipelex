"""Fuzzy model name matching and cross-collection suggestion utilities.

Provides functions to find close matches for model names and detect wrong-sigil usage.
Used by both the CLI check-model command and the model deck validation layer.
"""

import difflib

from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.models.model_reference import (
    SIGIL_ALIAS,
    SIGIL_PRESET,
    SIGIL_WATERFALL,
    ModelReferenceKind,
)

KIND_SIGILS: dict[ModelReferenceKind, str] = {
    ModelReferenceKind.PRESET: SIGIL_PRESET,
    ModelReferenceKind.ALIAS: SIGIL_ALIAS,
    ModelReferenceKind.WATERFALL: SIGIL_WATERFALL,
    ModelReferenceKind.HANDLE: "",
}

KIND_LABELS: dict[ModelReferenceKind, str] = {
    ModelReferenceKind.PRESET: "preset",
    ModelReferenceKind.ALIAS: "alias",
    ModelReferenceKind.WATERFALL: "waterfall",
    ModelReferenceKind.HANDLE: "handle",
}


def get_collection_keys(
    model_deck: ModelDeck,
    *,
    model_type: ModelType,
    kind: ModelReferenceKind,
) -> list[str]:
    """Return known names for a given reference kind and model type."""
    match kind:
        case ModelReferenceKind.PRESET:
            match model_type:
                case ModelType.LLM:
                    return list(model_deck.llm_presets.keys())
                case ModelType.TEXT_EXTRACTOR:
                    return list(model_deck.extract_presets.keys())
                case ModelType.IMG_GEN:
                    return list(model_deck.img_gen_presets.keys())
                case ModelType.SEARCH:
                    return list(model_deck.search_presets.keys())
        case ModelReferenceKind.ALIAS:
            match model_type:
                case ModelType.LLM:
                    return list(model_deck.llm_aliases.keys())
                case ModelType.TEXT_EXTRACTOR:
                    return list(model_deck.extract_aliases.keys())
                case ModelType.IMG_GEN:
                    return list(model_deck.img_gen_aliases.keys())
                case ModelType.SEARCH:
                    return list(model_deck.search_aliases.keys())
        case ModelReferenceKind.WATERFALL:
            match model_type:
                case ModelType.LLM:
                    return list(model_deck.llm_waterfalls.keys())
                case ModelType.TEXT_EXTRACTOR:
                    return list(model_deck.extract_waterfalls.keys())
                case ModelType.IMG_GEN:
                    return list(model_deck.img_gen_waterfalls.keys())
                case ModelType.SEARCH:
                    return list(model_deck.search_waterfalls.keys())
        case ModelReferenceKind.HANDLE:
            return sorted(handle for handle, spec in model_deck.inference_models.items() if spec.model_type == model_type)


def suggest_model_alternatives(
    model_deck: ModelDeck,
    *,
    model_type: ModelType,
    name: str,
    kind: ModelReferenceKind,
) -> tuple[list[str], list[str], list[str]]:
    """Find fuzzy matches and detect wrong-sigil usage for a model name.

    Args:
        model_deck: The model deck to search in.
        model_type: The model type (LLM, TEXT_EXTRACTOR, IMG_GEN, SEARCH).
        name: The bare name (without sigil) to match.
        kind: The reference kind the user specified (PRESET, ALIAS, WATERFALL, HANDLE).

    Returns:
        A tuple of three lists:
        - suggestions: fuzzy matches within the same collection, with sigil prefix
        - wrong_sigil_hints: exact matches found in other collections (e.g. "best-claude exists as @best-claude (alias)")
        - cross_collection_suggestions: fuzzy matches in other collections, with sigil and label
    """
    sigil = KIND_SIGILS[kind]
    candidates = get_collection_keys(model_deck, model_type=model_type, kind=kind)
    fuzzy_matches = difflib.get_close_matches(name, candidates, n=5, cutoff=0.5)
    suggestions = [f"{sigil}{match}" for match in fuzzy_matches]

    wrong_sigil_hints: list[str] = []
    cross_suggestions: list[str] = []
    other_kinds = [other_kind for other_kind in ModelReferenceKind if other_kind != kind]
    for other_kind in other_kinds:
        other_candidates = get_collection_keys(model_deck, model_type=model_type, kind=other_kind)
        other_sigil = KIND_SIGILS[other_kind]
        label = KIND_LABELS[other_kind]
        if name in other_candidates:
            wrong_sigil_hints.append(f"{name} exists as {other_sigil}{name} ({label})")
        else:
            fuzzy = difflib.get_close_matches(name, other_candidates, n=3, cutoff=0.7)
            for match in fuzzy:
                cross_suggestions.append(f"{other_sigil}{match} ({label})")

    return suggestions, wrong_sigil_hints, cross_suggestions
