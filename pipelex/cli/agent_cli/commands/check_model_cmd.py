"""Agent CLI check-model command -- validate a model reference and suggest alternatives."""

import difflib
from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, agent_error, agent_success
from pipelex.cli.agent_cli.commands.models_cmd import CATEGORY_TO_MODEL_TYPE, ModelCategory
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.models.model_reference import (
    SIGIL_ALIAS,
    SIGIL_PRESET,
    SIGIL_WATERFALL,
    ModelReference,
    ModelReferenceKind,
)
from pipelex.hub import get_model_deck
from pipelex.pipelex import Pipelex

# Maps reference kind to its sigil prefix for display
KIND_SIGILS: dict[ModelReferenceKind, str] = {
    ModelReferenceKind.PRESET: SIGIL_PRESET,
    ModelReferenceKind.ALIAS: SIGIL_ALIAS,
    ModelReferenceKind.WATERFALL: SIGIL_WATERFALL,
    ModelReferenceKind.HANDLE: "",
}

# Human-readable labels for reference kinds
KIND_LABELS: dict[ModelReferenceKind, str] = {
    ModelReferenceKind.PRESET: "preset",
    ModelReferenceKind.ALIAS: "alias",
    ModelReferenceKind.WATERFALL: "waterfall",
    ModelReferenceKind.HANDLE: "handle",
}


def _get_collection_keys(
    model_deck: ModelDeck,
    category: ModelCategory,
    kind: ModelReferenceKind,
) -> list[str]:
    """Return the list of known names for a given reference kind and category."""
    match kind:
        case ModelReferenceKind.PRESET:
            match category:
                case ModelCategory.LLM:
                    return list(model_deck.llm_presets.keys())
                case ModelCategory.EXTRACT:
                    return list(model_deck.extract_presets.keys())
                case ModelCategory.IMG_GEN:
                    return list(model_deck.img_gen_presets.keys())
                case ModelCategory.SEARCH:
                    return list(model_deck.search_presets.keys())
        case ModelReferenceKind.ALIAS:
            match category:
                case ModelCategory.LLM:
                    return list(model_deck.llm_aliases.keys())
                case ModelCategory.EXTRACT:
                    return list(model_deck.extract_aliases.keys())
                case ModelCategory.IMG_GEN:
                    return list(model_deck.img_gen_aliases.keys())
                case ModelCategory.SEARCH:
                    return list(model_deck.search_aliases.keys())
        case ModelReferenceKind.WATERFALL:
            match category:
                case ModelCategory.LLM:
                    return list(model_deck.llm_waterfalls.keys())
                case ModelCategory.EXTRACT:
                    return list(model_deck.extract_waterfalls.keys())
                case ModelCategory.IMG_GEN:
                    return list(model_deck.img_gen_waterfalls.keys())
                case ModelCategory.SEARCH:
                    return list(model_deck.search_waterfalls.keys())
        case ModelReferenceKind.HANDLE:
            target_model_type = CATEGORY_TO_MODEL_TYPE[category]
            return sorted(handle for handle, spec in model_deck.inference_models.items() if spec.model_type == target_model_type)


def _check_other_collections(
    model_deck: ModelDeck,
    category: ModelCategory,
    name: str,
    exclude_kind: ModelReferenceKind,
) -> tuple[list[str], list[str]]:
    """Check other collections for exact matches (wrong-sigil) and fuzzy matches.

    Returns:
        A tuple of (wrong_sigil_hints, cross_collection_suggestions).
        wrong_sigil_hints: e.g. ["best-claude exists as @best-claude (alias)"]
        cross_collection_suggestions: e.g. ["$writing-creative"]
    """
    wrong_sigil_hints: list[str] = []
    cross_suggestions: list[str] = []
    other_kinds = [kind for kind in ModelReferenceKind if kind != exclude_kind]
    for kind in other_kinds:
        candidates = _get_collection_keys(model_deck, category, kind)
        sigil = KIND_SIGILS[kind]
        label = KIND_LABELS[kind]
        if name in candidates:
            wrong_sigil_hints.append(f"{name} exists as {sigil}{name} ({label})")
        else:
            fuzzy = difflib.get_close_matches(name, candidates, n=3, cutoff=0.7)
            for match in fuzzy:
                cross_suggestions.append(f"{sigil}{match} ({label})")
    return wrong_sigil_hints, cross_suggestions


def _format_check_markdown(result: dict[str, Any]) -> str:
    """Format the check-model result as concise markdown."""
    name: str = result["name"]
    kind_label: str = result["kind"]
    category: str = result["model_type"]

    if result["valid"]:
        return f"{name} is a valid {category} {kind_label}."

    lines: list[str] = [f"{name} is not a valid {category} {kind_label}."]

    suggestions: list[str] = result.get("suggestions", [])
    if suggestions:
        lines.append("\nDid you mean:")
        for suggestion in suggestions:
            lines.append(f"- {suggestion}")

    cross_suggestions: list[str] = result.get("cross_collection_suggestions", [])
    if cross_suggestions:
        if not suggestions:
            lines.append("\nDid you mean:")
        for suggestion in cross_suggestions:
            lines.append(f"- {suggestion}")

    wrong_sigil_hints: list[str] = result.get("wrong_sigil_hints", [])
    for hint in wrong_sigil_hints:
        lines.append(f"\nNote: {hint}")

    return "\n".join(lines)


def agent_check_model_cmd(
    ctx: typer.Context,
    name: Annotated[
        str,
        typer.Argument(help="Model reference to check (e.g. $writing-creative, @best-claude, gpt-4o)"),
    ],
    model_type: Annotated[
        ModelCategory,
        typer.Option("--type", "-t", help="Model category: llm, extract, img_gen, search"),
    ],
    output_format: Annotated[
        CliOutputFormat,
        typer.Option("--format", help="Output format: markdown (default) or json (structured)"),
    ] = CliOutputFormat.MARKDOWN,
) -> None:
    """Check if a model reference is valid and suggest alternatives if not.

    Parses the reference (with sigil prefix if present), validates it against the
    model deck, and on failure provides fuzzy suggestions and wrong-sigil hints.
    """
    try:
        make_pipelex_for_agent_cli(log_level=ctx.obj["log_level"], needs_inference=False, needs_model_specs=True)

        model_deck = get_model_deck()
        ref = ModelReference.parse(name)

        candidates = _get_collection_keys(model_deck, model_type, ref.kind)
        is_valid = ref.name in candidates

        result: dict[str, Any] = {
            "success": True,
            "valid": is_valid,
            "name": name,
            "kind": KIND_LABELS[ref.kind],
            "model_type": str(model_type),
        }

        if not is_valid:
            sigil = KIND_SIGILS[ref.kind]
            fuzzy_matches = difflib.get_close_matches(ref.name, candidates, n=5, cutoff=0.5)
            result["suggestions"] = [f"{sigil}{match}" for match in fuzzy_matches]
            wrong_sigil_hints, cross_suggestions = _check_other_collections(model_deck, model_type, ref.name, ref.kind)
            result["wrong_sigil_hints"] = wrong_sigil_hints
            result["cross_collection_suggestions"] = cross_suggestions

        match output_format:
            case CliOutputFormat.JSON:
                agent_success(result)
            case CliOutputFormat.MARKDOWN:
                print(_format_check_markdown(result))
    except SystemExit:
        raise
    except Exception as exc:
        agent_error(f"Failed to check model: {exc}", type(exc).__name__, cause=exc)
    finally:
        Pipelex.teardown_if_needed()
