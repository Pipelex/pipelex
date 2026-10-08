"""The model reference check: whether one model reference resolves on this runtime, as what, to which model, and what the caller meant if not.

The check answers from the parser and the deck lookups a validation runs (`ModelReference.parse` and
`ModelDeck.is_reference_defined`), so a reference it finds resolved in a category is one a pipe of that
category may name in its `model` field, and one it finds not found is one a validation refuses. Its
suggestions follow the rule a validation's refusal follows (`find_model_alternatives`). The Pipelex API
serves it as `GET /v1/models/check`.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.exceptions import ModelReferenceParseError
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.models.model_reference import ModelReference, ModelReferenceKind
from pipelex.cogt.models.model_suggestion import ModelReferenceName, find_model_alternatives


class ModelCheckCategory(StrEnum):
    """The categories the model reference check covers, in the order every list it returns follows.

    These are the MTHDS Protocol's model categories, in the protocol's order, then `doc_gen`, the family
    of `PipeDocGen`. The protocol defines no category for `doc_gen`, so the model listing leaves it out,
    but a method names a `doc_gen` model in its `model` field like any other, so the check covers it.
    """

    LLM = "llm"
    EXTRACT = "extract"
    IMG_GEN = "img_gen"
    SEARCH = "search"
    JUDGMENT = "judgment"
    DOC_GEN = "doc_gen"

    @property
    def model_type(self) -> ModelType:
        """The model type of the deck family this category names."""
        match self:
            case ModelCheckCategory.LLM:
                return ModelType.LLM
            case ModelCheckCategory.EXTRACT:
                return ModelType.TEXT_EXTRACTOR
            case ModelCheckCategory.IMG_GEN:
                return ModelType.IMG_GEN
            case ModelCheckCategory.SEARCH:
                return ModelType.SEARCH
            case ModelCheckCategory.JUDGMENT:
                return ModelType.JUDGMENT
            case ModelCheckCategory.DOC_GEN:
                return ModelType.DOC_GEN


class ModelReferenceResolution(StrEnum):
    """Whether a reference resolves in a category in scope. Both values are definitive."""

    RESOLVED = "resolved"
    NOT_FOUND = "not_found"


_CATEGORY_DESCRIPTION = "The category this entry is about."
_RESOLVES_TO_DESCRIPTION = (
    "The model handle a run through the reference would call now in this category, "
    "or null when it would find none (a target on a backend the runner has not enabled, "
    "a waterfall none of whose usable steps the runner serves, an alias cycle)."
)


class PresetMatch(BaseModel):
    """What a preset reference is in one category."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: ModelCheckCategory = Field(description=_CATEGORY_DESCRIPTION)
    resolves_to: str | None = Field(description=_RESOLVES_TO_DESCRIPTION)
    target: str = Field(description="The model the deck binds the preset to, as the deck writes it, which may itself be a reference.")
    description: str | None = Field(description="The preset's description, or null when the deck gives it none.")


class AliasMatch(BaseModel):
    """What an alias reference is in one category."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: ModelCheckCategory = Field(description=_CATEGORY_DESCRIPTION)
    resolves_to: str | None = Field(description=_RESOLVES_TO_DESCRIPTION)
    target: str = Field(description="The model the deck binds the alias to, as the deck writes it, which may itself be a reference.")


class WaterfallMatch(BaseModel):
    """What a waterfall reference is in one category."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: ModelCheckCategory = Field(description=_CATEGORY_DESCRIPTION)
    resolves_to: str | None = Field(description=_RESOLVES_TO_DESCRIPTION)
    fallbacks: list[str] = Field(description="The waterfall's steps, in order.")


class HandleMatch(BaseModel):
    """What a bare handle reference is in one category."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: ModelCheckCategory = Field(description=_CATEGORY_DESCRIPTION)
    resolves_to: str | None = Field(description=_RESOLVES_TO_DESCRIPTION)
    via: list[str] = Field(
        description="The presets, aliases and waterfalls of this category whose binding names the handle directly, each written as a reference."
    )


ModelReferenceMatch = PresetMatch | AliasMatch | WaterfallMatch | HandleMatch


class ModelReferenceVerdict(BaseModel):
    """The verdict of the model reference check, discriminated on `resolution`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reference: str = Field(description="The caller's reference, trimmed.")
    kind: ModelReferenceKind = Field(description="What the reference names, from its parsing.")
    name: str = Field(description="The reference without its sigil or namespace.")
    category: ModelCheckCategory | None = Field(description="The `type` asked, or null when none was.")
    resolution: ModelReferenceResolution = Field(description="Whether the reference resolves in a category in scope.")
    matches: list[ModelReferenceMatch] = Field(
        description="One entry per category in scope where the reference resolves, in the order of the categories the check covers."
    )
    suggestions: list[str] = Field(description="On `not_found`, the nearest names the caller may have meant; empty when it is `resolved`.")
    other_kinds: list[str] = Field(
        description="On `not_found`, the same name under another kind, in the categories in scope; empty when it is `resolved`."
    )
    other_categories: list[ModelCheckCategory] = Field(
        description="On `not_found` with a `type`, the categories outside it where the same reference resolves; empty otherwise."
    )


def check_model_reference(*, model_deck: ModelDeck, reference: ModelReference, category: ModelCheckCategory | None) -> ModelReferenceVerdict:
    """Check whether a parsed model reference resolves on this runtime, in `category` or, when it is None, in every category the check covers.

    Args:
        model_deck: The deck the runtime booted with.
        reference: The reference, parsed as a method's `model` field is.
        category: The category to check in, or None to check in every category the check covers.

    Returns:
        The verdict: `resolved` with one match per category in scope where the reference resolves, or
        `not_found` with what the caller most likely meant.
    """
    categories_in_scope = [category] if category is not None else list(ModelCheckCategory)
    matches: list[ModelReferenceMatch] = []
    for scope_category in categories_in_scope:
        match_in_category = _match_in_category(model_deck=model_deck, reference=reference, category=scope_category)
        if match_in_category is not None:
            matches.append(match_in_category)

    if matches:
        return ModelReferenceVerdict(
            reference=reference.raw,
            kind=reference.kind,
            name=reference.name,
            category=category,
            resolution=ModelReferenceResolution.RESOLVED,
            matches=matches,
            suggestions=[],
            other_kinds=[],
            other_categories=[],
        )

    suggestions: list[str] = []
    other_kinds: list[str] = []
    for scope_category in categories_in_scope:
        alternatives = find_model_alternatives(
            model_deck=model_deck,
            model_type=scope_category.model_type,
            name=reference.name,
            kind=reference.kind,
        )
        suggestions.extend(_written(names=[*alternatives.same_kind, *alternatives.cross_kind]))
        other_kinds.extend(_written(names=alternatives.other_kinds))

    other_categories: list[ModelCheckCategory] = []
    if category is not None:
        other_categories = [
            other_category
            for other_category in ModelCheckCategory
            if other_category != category and model_deck.is_reference_defined(reference=reference, model_type=other_category.model_type)
        ]

    return ModelReferenceVerdict(
        reference=reference.raw,
        kind=reference.kind,
        name=reference.name,
        category=category,
        resolution=ModelReferenceResolution.NOT_FOUND,
        matches=[],
        suggestions=_first_occurrences(items=suggestions),
        other_kinds=_first_occurrences(items=other_kinds),
        other_categories=other_categories,
    )


def _match_in_category(*, model_deck: ModelDeck, reference: ModelReference, category: ModelCheckCategory) -> ModelReferenceMatch | None:
    """What the reference is in one category, or None when it does not resolve there."""
    model_type = category.model_type
    if not model_deck.is_reference_defined(reference=reference, model_type=model_type):
        return None
    aliases, waterfalls = model_deck.get_aliases_and_waterfalls_for_type(model_type)
    match reference.kind:
        case ModelReferenceKind.PRESET:
            preset = model_deck.get_presets_for_type(model_type=model_type)[reference.name]
            return PresetMatch(
                category=category,
                resolves_to=_model_a_run_calls(model_deck=model_deck, model_handle=preset.model, model_type=model_type),
                target=preset.model,
                description=preset.description,
            )
        case ModelReferenceKind.ALIAS:
            alias_target = aliases[reference.name]
            return AliasMatch(
                category=category,
                resolves_to=_model_a_run_calls(model_deck=model_deck, model_handle=alias_target, model_type=model_type),
                target=alias_target,
            )
        case ModelReferenceKind.WATERFALL:
            waterfall = ModelReferenceName(kind=ModelReferenceKind.WATERFALL, name=reference.name)
            return WaterfallMatch(
                category=category,
                resolves_to=_model_a_run_calls(model_deck=model_deck, model_handle=waterfall.written, model_type=model_type),
                fallbacks=list(waterfalls[reference.name]),
            )
        case ModelReferenceKind.HANDLE:
            return HandleMatch(
                category=category,
                resolves_to=_model_a_run_calls(model_deck=model_deck, model_handle=reference.name, model_type=model_type),
                via=_deck_names_binding_the_handle(model_deck=model_deck, handle=reference.name, model_type=model_type),
            )


def _model_a_run_calls(*, model_deck: ModelDeck, model_handle: str, model_type: ModelType) -> str | None:
    """The handle of the model a run through `model_handle` would call now, or None when it would find none.

    The deck is read without side effects: a check logs nothing and leaves the fallback notice to the run.
    """
    inference_model = model_deck.peek_inference_model(model_handle=model_handle, model_type=model_type)
    if inference_model is None:
        return None
    return inference_model.name


def _deck_names_binding_the_handle(*, model_deck: ModelDeck, handle: str, model_type: ModelType) -> list[str]:
    """The presets, aliases and waterfalls of this model type whose binding names `handle` directly, each written as a reference."""
    via: list[ModelReferenceName] = []
    for preset_name, preset in model_deck.get_presets_for_type(model_type=model_type).items():
        if _binding_names_handle(binding=preset.model, handle=handle):
            via.append(ModelReferenceName(kind=ModelReferenceKind.PRESET, name=preset_name))
    aliases, waterfalls = model_deck.get_aliases_and_waterfalls_for_type(model_type)
    for alias_name, alias_target in aliases.items():
        if _binding_names_handle(binding=alias_target, handle=handle):
            via.append(ModelReferenceName(kind=ModelReferenceKind.ALIAS, name=alias_name))
    for waterfall_name, fallbacks in waterfalls.items():
        if any(_binding_names_handle(binding=fallback, handle=handle) for fallback in fallbacks):
            via.append(ModelReferenceName(kind=ModelReferenceKind.WATERFALL, name=waterfall_name))
    return _written(names=via)


def _binding_names_handle(*, binding: str, handle: str) -> bool:
    """Whether a deck binding (a preset's model, an alias's target, a waterfall's step) names `handle` as a bare handle, however spelled."""
    try:
        bound = ModelReference.parse(binding)
    except ModelReferenceParseError:
        return False
    match bound.kind:
        case ModelReferenceKind.HANDLE:
            return bound.name == handle
        case ModelReferenceKind.PRESET | ModelReferenceKind.ALIAS | ModelReferenceKind.WATERFALL:
            return False


def _written(*, names: list[ModelReferenceName]) -> list[str]:
    return [name.written for name in names]


def _first_occurrences(*, items: list[str]) -> list[str]:
    """The items in order, each kept once, at its first place."""
    return list(dict.fromkeys(items))
