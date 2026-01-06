from __future__ import annotations

import importlib.util
from typing import Any

from rich import box
from rich.table import Table

from pipelex.exceptions import MissingDependencyError
from pipelex.hub import get_console


def list_mistral_models(
    sdk: str,
    backend_name: str,
    flat: bool,
    any_listed: bool,
) -> None:
    """List Mistral models."""
    if importlib.util.find_spec("mistralai") is None:
        lib_name = "mistralai"
        lib_extra_name = "mistral"
        msg = (
            "The mistralai SDK is required in order to use Mistral models through the mistralai client. "
            "However, you can use Mistral models through bedrock directly "
            "by using the 'bedrock-mistral' llm family. (eg: bedrock-mistral-large)"
        )
        raise MissingDependencyError(
            lib_name,
            lib_extra_name,
            msg,
        )

    from pipelex.plugins.mistral.mistral_llms import mistral_list_available_models  # noqa: PLC0415

    mistral_models = mistral_list_available_models()

    if flat:
        _display_mistral_models_flat(
            models=mistral_models,
            sdk=sdk,
            backend_name=backend_name,
            any_listed=any_listed,
        )
    else:
        _display_mistral_models_table(
            models=mistral_models,
            sdk=sdk,
            backend_name=backend_name,
        )


def _display_mistral_models_flat(
    models: list[Any],
    sdk: str,
    backend_name: str,
    any_listed: bool,
) -> None:
    """Display Mistral models in CSV format."""
    console = get_console()
    if not any_listed:
        console.print("model_id,max_context_length,sdk,backend")
    for mistral_model in models:
        max_ctx = str(mistral_model.max_context_length) if mistral_model.max_context_length else "N/A"
        console.print(f"{mistral_model.id},{max_ctx},{sdk},{backend_name}")


def _display_mistral_models_table(
    models: list[Any],
    sdk: str,
    backend_name: str,
) -> None:
    """Display Mistral models in table format."""
    table = Table(
        title=f"Available Models for Backend '{backend_name}' (SDK: {sdk})",
        show_header=True,
        header_style="bold cyan",
        box=box.SQUARE_DOUBLE_HEAD,
    )
    table.add_column("Model ID", style="green")
    table.add_column("Max Context Length", style="yellow")

    for mistral_model in models:
        max_ctx = str(mistral_model.max_context_length) if mistral_model.max_context_length else "N/A"
        table.add_row(mistral_model.id, max_ctx)

    console = get_console()
    console.print("\n")
    console.print(table)
    console.print("\n")
