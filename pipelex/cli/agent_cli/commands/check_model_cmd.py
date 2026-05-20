"""Agent CLI check-model command -- validate a model reference and suggest alternatives."""

from typing import Annotated, Any

import typer

from pipelex.builder.operations.models_ops import CATEGORY_TO_MODEL_TYPE, ModelCategory
from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, agent_error, agent_success, set_agent_cli_error_format
from pipelex.cogt.models.model_reference import ModelReference, ModelReferenceParseError
from pipelex.cogt.models.model_suggestion import (
    KIND_LABELS,
    get_collection_keys,
    suggest_model_alternatives,
)
from pipelex.hub import get_model_deck
from pipelex.pipelex import Pipelex


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
        else:
            lines.append("\nOr from a different collection:")
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
        typer.Option("--format", help="Success output format: markdown (default) or json (structured)"),
    ] = CliOutputFormat.MARKDOWN,
    error_format: Annotated[
        CliOutputFormat | None,
        typer.Option("--error-format", help="Error output format (defaults to --format value): markdown or json"),
    ] = None,
) -> None:
    """Check if a model reference is valid and suggest alternatives if not.

    Parses the reference (with sigil prefix if present), validates it against the
    model deck, and on failure provides fuzzy suggestions and wrong-sigil hints.
    """
    set_agent_cli_error_format(error_format or output_format)
    try:
        make_pipelex_for_agent_cli(log_level=ctx.obj["log_level"], needs_inference=False, needs_model_specs=True)

        model_deck = get_model_deck()
        ref = ModelReference.parse(name)
        resolved_model_type = CATEGORY_TO_MODEL_TYPE[model_type]

        candidates = get_collection_keys(model_deck, resolved_model_type, ref.kind)
        is_valid = ref.name in candidates

        result: dict[str, Any] = {
            "success": True,
            "valid": is_valid,
            "name": name,
            "kind": KIND_LABELS[ref.kind],
            "model_type": str(model_type),
        }

        if not is_valid:
            suggestions, wrong_sigil_hints, cross_suggestions = suggest_model_alternatives(model_deck, resolved_model_type, ref.name, ref.kind)
            result["suggestions"] = suggestions
            result["wrong_sigil_hints"] = wrong_sigil_hints
            result["cross_collection_suggestions"] = cross_suggestions

        match output_format:
            case CliOutputFormat.JSON:
                agent_success(result)
            case CliOutputFormat.MARKDOWN:
                print(_format_check_markdown(result))
    except SystemExit:
        raise
    except ModelReferenceParseError as exc:
        agent_error(f"Invalid model reference: {exc}", "ArgumentError", cause=exc)
    except Exception as exc:  # noqa: BLE001
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
        agent_error(f"Failed to check model: {exc}", type(exc).__name__, cause=exc)
    finally:
        Pipelex.teardown_if_needed()
