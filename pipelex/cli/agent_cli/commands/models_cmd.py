"""Agent CLI models command -- list available model presets, aliases, and talent mappings."""

from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.config import get_config
from pipelex.hub import get_model_deck
from pipelex.pipelex import Pipelex
from pipelex.types import StrEnum


class ModelCategory(StrEnum):
    LLM = "llm"
    EXTRACT = "extract"
    IMG_GEN = "img_gen"


CATEGORY_TO_MODEL_TYPE: dict[ModelCategory, ModelType] = {
    ModelCategory.LLM: ModelType.LLM,
    ModelCategory.EXTRACT: ModelType.TEXT_EXTRACTOR,
    ModelCategory.IMG_GEN: ModelType.IMG_GEN,
}


def _should_include(category: ModelCategory, categories: list[ModelCategory] | None) -> bool:
    """Check whether a category should be included given the filter list.

    Returns True when no filter is set (None or empty) or when the category is in the filter list.
    """
    return categories is None or len(categories) == 0 or category in categories


def _resolve_preset_backend(
    model_deck: ModelDeck,
    model_handle: str,
    model_type: ModelType,
) -> InferenceModelSpec | None:
    """Resolve a preset's model handle to an InferenceModelSpec, returning None if unresolvable."""
    return model_deck.get_optional_inference_model(model_handle=model_handle, model_type=model_type)


def _filter_presets_by_backend(
    presets_list: list[dict[str, Any]],
    presets_dict: dict[str, Any],
    model_deck: ModelDeck,
    model_type: ModelType,
    backend: str,
) -> list[dict[str, Any]]:
    """Filter a presets list to only include presets whose model resolves to the given backend."""
    filtered: list[dict[str, Any]] = []
    for preset_entry in presets_list:
        preset_name = preset_entry["name"]
        setting = presets_dict.get(preset_name)
        if setting is None:
            continue
        spec = _resolve_preset_backend(model_deck, setting.model, model_type)
        if spec is not None and spec.backend_name == backend:
            filtered.append(preset_entry)
    return filtered


def _filter_aliases_by_backend(
    aliases: dict[str, str],
    model_deck: ModelDeck,
    model_type: ModelType,
    backend: str,
) -> dict[str, str]:
    """Filter aliases to only include those whose target resolves to the given backend."""
    filtered: dict[str, str] = {}
    for alias_name, alias_target in aliases.items():
        spec = model_deck.get_optional_inference_model(model_handle=alias_target, model_type=model_type)
        if spec is not None and spec.backend_name == backend:
            filtered[alias_name] = alias_target
    return filtered


def _filter_waterfalls_by_backend(
    waterfalls: dict[str, list[str]],
    model_deck: ModelDeck,
    model_type: ModelType,
    backend: str,
) -> dict[str, list[str]]:
    """Filter waterfalls to only include those where at least one fallback resolves to the given backend."""
    filtered: dict[str, list[str]] = {}
    for waterfall_name, fallback_list in waterfalls.items():
        for fallback in fallback_list:
            spec = model_deck.get_optional_inference_model(model_handle=fallback, model_type=model_type)
            if spec is not None and spec.backend_name == backend:
                filtered[waterfall_name] = fallback_list
                break
    return filtered


def _filter_talent_mappings_by_backend(
    mappings: dict[str, str],
    presets_dict: dict[str, Any],
    model_deck: ModelDeck,
    model_type: ModelType,
    backend: str,
) -> dict[str, str]:
    """Filter talent mappings to only include those whose preset resolves to the given backend."""
    filtered: dict[str, str] = {}
    for talent_name, preset_name in mappings.items():
        setting = presets_dict.get(preset_name)
        if setting is None:
            continue
        spec = _resolve_preset_backend(model_deck, setting.model, model_type)
        if spec is not None and spec.backend_name == backend:
            filtered[talent_name] = preset_name
    return filtered


def _build_presets_for_category(
    model_deck: ModelDeck,
    category: ModelCategory,
    backend: str | None,
) -> list[dict[str, Any]]:
    """Build the presets list for a given category, optionally filtered by backend."""
    presets_dict: dict[str, Any]
    model_type = CATEGORY_TO_MODEL_TYPE[category]
    match category:
        case ModelCategory.LLM:
            presets_dict = model_deck.llm_presets
        case ModelCategory.EXTRACT:
            presets_dict = model_deck.extract_presets
        case ModelCategory.IMG_GEN:
            presets_dict = model_deck.img_gen_presets

    presets_list: list[dict[str, Any]] = []
    for preset_name, setting in presets_dict.items():
        entry: dict[str, Any] = {"name": preset_name}
        if setting.description is not None:
            entry["description"] = setting.description
        presets_list.append(entry)

    if backend is not None:
        presets_list = _filter_presets_by_backend(presets_list, presets_dict, model_deck, model_type, backend)

    return presets_list


def _build_aliases_for_category(
    model_deck: ModelDeck,
    category: ModelCategory,
    backend: str | None,
) -> dict[str, str]:
    """Build the aliases dict for a given category, optionally filtered by backend."""
    model_type = CATEGORY_TO_MODEL_TYPE[category]
    aliases: dict[str, str]
    match category:
        case ModelCategory.LLM:
            aliases = model_deck.llm_aliases
        case ModelCategory.EXTRACT:
            aliases = model_deck.extract_aliases
        case ModelCategory.IMG_GEN:
            aliases = model_deck.img_gen_aliases

    if backend is not None:
        aliases = _filter_aliases_by_backend(aliases, model_deck, model_type, backend)

    return aliases


def _build_waterfalls_for_category(
    model_deck: ModelDeck,
    category: ModelCategory,
    backend: str | None,
) -> dict[str, list[str]]:
    """Build the waterfalls dict for a given category, optionally filtered by backend."""
    model_type = CATEGORY_TO_MODEL_TYPE[category]
    waterfalls: dict[str, list[str]]
    match category:
        case ModelCategory.LLM:
            waterfalls = model_deck.llm_waterfalls
        case ModelCategory.EXTRACT:
            waterfalls = model_deck.extract_waterfalls
        case ModelCategory.IMG_GEN:
            waterfalls = model_deck.img_gen_waterfalls

    if backend is not None:
        waterfalls = _filter_waterfalls_by_backend(waterfalls, model_deck, model_type, backend)

    return waterfalls


def _build_talent_mappings_for_category(
    model_deck: ModelDeck,
    category: ModelCategory,
    mappings: dict[str, str],
    backend: str | None,
) -> dict[str, str]:
    """Build the talent mappings dict for a given category, optionally filtered by backend."""
    if backend is None:
        return mappings

    model_type = CATEGORY_TO_MODEL_TYPE[category]
    presets_dict: dict[str, Any]
    match category:
        case ModelCategory.LLM:
            presets_dict = model_deck.llm_presets
        case ModelCategory.EXTRACT:
            presets_dict = model_deck.extract_presets
        case ModelCategory.IMG_GEN:
            presets_dict = model_deck.img_gen_presets

    return _filter_talent_mappings_by_backend(mappings, presets_dict, model_deck, model_type, backend)


def agent_models_cmd(
    ctx: typer.Context,
    model_type: Annotated[
        list[ModelCategory] | None,
        typer.Option("--type", "-t", help="Filter by model category (repeatable): llm, extract, img_gen"),
    ] = None,
    backend: Annotated[
        str | None,
        typer.Option("--backend", "-b", help="Filter by backend name"),
    ] = None,
) -> None:
    """List available model presets, aliases, waterfalls, and talent mappings.

    Outputs structured JSON to stdout with all model configuration
    that an agent needs to reference when building pipelines.
    """
    try:
        make_pipelex_for_agent_cli(log_level=ctx.obj["log_level"])

        model_deck = get_model_deck()
        builder_config = get_config().pipelex.builder_config
        talent_mappings = builder_config.talent_preset_mappings

        presets: dict[str, list[dict[str, Any]]] = {}
        aliases: dict[str, dict[str, str]] = {}
        waterfalls: dict[str, dict[str, list[str]]] = {}
        talent: dict[str, dict[str, str]] = {}

        if _should_include(ModelCategory.LLM, model_type):
            presets["llm"] = _build_presets_for_category(model_deck, ModelCategory.LLM, backend)
            aliases["llm"] = _build_aliases_for_category(model_deck, ModelCategory.LLM, backend)
            waterfalls["llm"] = _build_waterfalls_for_category(model_deck, ModelCategory.LLM, backend)
            talent["llm"] = _build_talent_mappings_for_category(model_deck, ModelCategory.LLM, talent_mappings.llm, backend)

        if _should_include(ModelCategory.IMG_GEN, model_type):
            presets["img_gen"] = _build_presets_for_category(model_deck, ModelCategory.IMG_GEN, backend)
            aliases["img_gen"] = _build_aliases_for_category(model_deck, ModelCategory.IMG_GEN, backend)
            waterfalls["img_gen"] = _build_waterfalls_for_category(model_deck, ModelCategory.IMG_GEN, backend)
            talent["img_gen"] = _build_talent_mappings_for_category(model_deck, ModelCategory.IMG_GEN, talent_mappings.img_gen, backend)

        if _should_include(ModelCategory.EXTRACT, model_type):
            presets["extract"] = _build_presets_for_category(model_deck, ModelCategory.EXTRACT, backend)
            aliases["extract"] = _build_aliases_for_category(model_deck, ModelCategory.EXTRACT, backend)
            waterfalls["extract"] = _build_waterfalls_for_category(model_deck, ModelCategory.EXTRACT, backend)
            talent["extract"] = _build_talent_mappings_for_category(model_deck, ModelCategory.EXTRACT, talent_mappings.extract, backend)

        result: dict[str, Any] = {
            "success": True,
            "presets": presets,
            "aliases": aliases,
            "waterfalls": waterfalls,
            "talent_mappings": {
                "usage_hint": (
                    "Use the talent name (key) as the value for llm_talent / extract_talent / img_gen_talent"
                    " in pipe specs passed to 'pipelex-agent pipe --spec'"
                ),
                **talent,
            },
        }

        agent_success(result)
    except SystemExit:
        # agent_error already handled and called sys.exit
        raise
    except Exception as exc:
        agent_error(f"Failed to list models: {exc}", type(exc).__name__, cause=exc)
    finally:
        Pipelex.teardown_if_needed()
