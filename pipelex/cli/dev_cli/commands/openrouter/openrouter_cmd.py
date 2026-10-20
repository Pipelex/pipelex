"""Look up public model facts and export draft backend TOML."""

import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import httpx
import typer
from pydantic import ValidationError

from pipelex.cli.dev_cli.commands.openrouter.catalog import OpenRouterModel, fetch_models
from pipelex.cli.dev_cli.commands.openrouter.export import models_to_toml, price_per_million

openrouter_app = typer.Typer(no_args_is_help=True, help="Research OpenRouter models and export draft backend entries.")


class ModelSortKey(StrEnum):
    NAME = "name"
    CONTEXT_LENGTH = "context_length"
    CREATED = "created"


def sort_models(*, models: list[OpenRouterModel], sort_key: ModelSortKey) -> list[OpenRouterModel]:
    match sort_key:
        case ModelSortKey.NAME:
            return sorted(models, key=lambda model: (model.name or model.id).casefold())
        case ModelSortKey.CONTEXT_LENGTH:
            return sorted(models, key=lambda model: model.context_length or 0, reverse=True)
        case ModelSortKey.CREATED:
            return sorted(models, key=lambda model: model.created or 0, reverse=True)


def markdown_cell(*, value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def render_models(*, models: list[OpenRouterModel]) -> str:
    lines = [
        "# OpenRouter models",
        "",
        "| ID | Name | Context tokens | Input USD/M tokens | Output USD/M tokens |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for model in models:
        pricing = model.pricing or {}
        input_price = price_per_million(price=pricing.get("prompt"))
        output_price = price_per_million(price=pricing.get("completion"))
        cells = [
            markdown_cell(value=model.id),
            markdown_cell(value=model.name),
            str(model.context_length) if model.context_length is not None else "Unknown",
            f"{input_price:g}" if input_price is not None else "Unknown",
            f"{output_price:g}" if output_price is not None else "Unknown",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    if not models:
        lines.extend(["", "No models matched."])
    return "\n".join(lines)


@openrouter_app.command("list-models")
def list_models_command(
    category: Annotated[str | None, typer.Option("--category", "-c", help="OpenRouter catalog category filter.")] = None,
    name_filter: Annotated[str | None, typer.Option("--filter", "-f", help="Match a substring of the name or ID, ignoring case.")] = None,
    sort: Annotated[
        ModelSortKey, typer.Option("--sort", "-s", help="Sort by name, context length (context_length), or creation date.")
    ] = ModelSortKey.NAME,
    output_json: Annotated[bool, typer.Option("--json", "-j", help="Emit a JSON envelope instead of Markdown.")] = False,
    save: Annotated[bool, typer.Option("--save", help="Write disabled draft TOML into generated/; refuse to overwrite an existing file.")] = False,
) -> None:
    try:
        models = fetch_models(category=category)
        if name_filter:
            needle = name_filter.casefold()
            models = [model for model in models if needle in model.id.casefold() or needle in model.name.casefold()]
        models = sort_models(models=models, sort_key=sort)
        saved_to: Path | None = None
        skipped_model_ids: list[str] = []
        if save:
            if not models:
                msg = "No models matched; no export was written"
                raise ValueError(msg)
            suffix_parts = [part for part in (category, name_filter) if part]
            suffix = "".join("_" + "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in part) for part in suffix_parts)
            saved_to = Path("generated") / f"openrouter_models{suffix}.toml"
            export_models: list[OpenRouterModel] = []
            for model in models:
                outputs = model.architecture.output_modalities if model.architecture else []
                if outputs and all(output in {"text", "image"} for output in outputs):
                    export_models.append(model)
                else:
                    skipped_model_ids.append(model.id)
            if not export_models:
                msg = "No matched models have exportable text or image output; no export was written"
                raise ValueError(msg)
            content = models_to_toml(models=export_models)
            saved_to.parent.mkdir(parents=True, exist_ok=True)
            with saved_to.open("x", encoding="utf-8") as output_file:
                output_file.write(content)
    except (httpx.HTTPError, ValueError, OSError) as exc:
        if isinstance(exc, ValidationError):
            message = "OpenRouter returned malformed catalog metadata"
        elif isinstance(exc, httpx.HTTPStatusError):
            message = f"OpenRouter catalog request failed with HTTP {exc.response.status_code}"
        elif isinstance(exc, httpx.HTTPError):
            message = "Could not reach the OpenRouter catalog"
        else:
            message = str(exc)
        if output_json:
            typer.echo(json.dumps({"ok": False, "error": message}), err=True)
        else:
            typer.echo(f"# OpenRouter lookup failed\n\n{message}", err=True)
        raise typer.Exit(1) from exc
    if output_json:
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "models": [model.model_dump(exclude_unset=True) for model in models],
                    "saved_to": str(saved_to) if saved_to else None,
                    "skipped_model_ids": skipped_model_ids,
                },
                indent=2,
            )
        )
    else:
        typer.echo(render_models(models=models))
        if saved_to:
            typer.echo(f"\nDraft saved to `{saved_to}`. Review each entry before enabling it.")
            if skipped_model_ids:
                typer.echo("\nSkipped models with unsupported output modalities: " + ", ".join(skipped_model_ids))
