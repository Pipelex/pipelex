"""Fuzzy model name matching and cross-collection suggestion utilities.

Provides functions to find close matches for model names and detect wrong-sigil usage.
Used by the CLI check-model command, the model deck validation layer and the model reference check.
"""

import difflib
from typing import NamedTuple

from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.models.model_reference import (
    SIGIL_ALIAS,
    SIGIL_PRESET,
    SIGIL_WATERFALL,
    ModelReferenceKind,
    write_model_handle,
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
    """Return known names for a given reference kind and model type, read through the deck's own per-type accessors."""
    match kind:
        case ModelReferenceKind.PRESET:
            return list(model_deck.get_presets_for_type(model_type=model_type))
        case ModelReferenceKind.ALIAS:
            aliases, _ = model_deck.get_aliases_and_waterfalls_for_type(model_type)
            return list(aliases)
        case ModelReferenceKind.WATERFALL:
            _, waterfalls = model_deck.get_aliases_and_waterfalls_for_type(model_type)
            return list(waterfalls)
        case ModelReferenceKind.HANDLE:
            return model_deck.get_model_handles_for_type(model_type=model_type)


class ModelReferenceName(NamedTuple):
    """A name the deck holds under one kind of model reference."""

    kind: ModelReferenceKind
    name: str

    @property
    def written(self) -> str:
        """The name as a method writes it: a sigil for a preset, an alias or a waterfall, and the bare name for a handle.

        A handle whose bare name would read as another kind of reference is written `handle:<name>` (`write_model_handle`).
        """
        match self.kind:
            case ModelReferenceKind.HANDLE:
                return write_model_handle(name=self.name)
            case ModelReferenceKind.PRESET | ModelReferenceKind.ALIAS | ModelReferenceKind.WATERFALL:
                return f"{KIND_SIGILS[self.kind]}{self.name}"

    @property
    def labelled(self) -> str:
        """The written name followed by its kind in words, as a validation's report shows it (`@best-gpt (alias)`)."""
        return f"{self.written} ({KIND_LABELS[self.kind]})"


class ModelAlternatives(NamedTuple):
    """What a caller who named a model the deck does not hold most likely meant, in one model type."""

    # The nearest names of the reference's own kind, nearest first, as many as `_SAME_KIND_MAX_MATCHES` allows.
    same_kind: list[ModelReferenceName]
    # The same name under each other kind the deck defines it as, which is the likeliest fault.
    other_kinds: list[ModelReferenceName]
    # For each other kind the name does not exist under exactly, the nearest names of that kind, as many as `_CROSS_KIND_MAX_MATCHES` allows.
    cross_kind: list[ModelReferenceName]


# How near a name must be to be offered, as difflib's similarity ratio, and how many are offered: the
# threshold is stricter for another kind than for the reference's own, since a slip of the name alone is
# likelier than a slip of both the name and the sigil.
_SAME_KIND_CUTOFF = 0.5
_SAME_KIND_MAX_MATCHES = 5
_CROSS_KIND_CUTOFF = 0.7
_CROSS_KIND_MAX_MATCHES = 3


def find_model_alternatives(*, model_deck: ModelDeck, model_type: ModelType, name: str, kind: ModelReferenceKind) -> ModelAlternatives:
    """Find the names a caller most likely meant by a model name the deck does not hold as `kind` for `model_type`.

    This is the rule a validation follows when it refuses an unknown model, and the rule the model
    reference check follows when it answers that a reference resolves nowhere.

    Args:
        model_deck: The model deck to search in.
        model_type: The model type the name was asked for.
        name: The bare name (without sigil) to match.
        kind: The reference kind the caller specified.

    Returns:
        The close matches of the same kind, the exact matches under other kinds, and the close matches under other kinds.
    """
    candidates = get_collection_keys(model_deck, model_type=model_type, kind=kind)
    same_kind = [
        ModelReferenceName(kind=kind, name=match)
        for match in difflib.get_close_matches(name, candidates, n=_SAME_KIND_MAX_MATCHES, cutoff=_SAME_KIND_CUTOFF)
    ]

    other_kinds: list[ModelReferenceName] = []
    cross_kind: list[ModelReferenceName] = []
    for other_kind in ModelReferenceKind:
        if other_kind == kind:
            continue
        other_candidates = get_collection_keys(model_deck, model_type=model_type, kind=other_kind)
        if name in other_candidates:
            other_kinds.append(ModelReferenceName(kind=other_kind, name=name))
        else:
            cross_kind.extend(
                ModelReferenceName(kind=other_kind, name=match)
                for match in difflib.get_close_matches(name, other_candidates, n=_CROSS_KIND_MAX_MATCHES, cutoff=_CROSS_KIND_CUTOFF)
            )

    return ModelAlternatives(same_kind=same_kind, other_kinds=other_kinds, cross_kind=cross_kind)


def suggest_model_alternatives(
    *, model_deck: ModelDeck, model_type: ModelType, name: str, kind: ModelReferenceKind
) -> tuple[list[str], list[str], list[str]]:
    """Find fuzzy matches and detect wrong-sigil usage for a model name, phrased as a validation's report shows them.

    Args:
        model_deck: The model deck to search in.
        model_type: The model type (LLM, TEXT_EXTRACTOR, IMG_GEN, SEARCH).
        name: The bare name (without sigil) to match.
        kind: The reference kind the user specified (PRESET, ALIAS, WATERFALL, HANDLE).

    Returns:
        A tuple of three lists:
        - suggestions: fuzzy matches within the same collection, with sigil prefix
        - wrong_sigil_hints: exact matches found in other collections (e.g. "best-gpt exists as @best-gpt (alias)")
        - cross_collection_suggestions: fuzzy matches in other collections, with sigil and label
    """
    alternatives = find_model_alternatives(model_deck=model_deck, model_type=model_type, name=name, kind=kind)
    suggestions = [match.written for match in alternatives.same_kind]
    wrong_sigil_hints = [f"{name} exists as {match.labelled}" for match in alternatives.other_kinds]
    cross_suggestions = [match.labelled for match in alternatives.cross_kind]
    return suggestions, wrong_sigil_hints, cross_suggestions
