from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from rich import box
from rich.table import Table

from pipelex.hub import get_console
from pipelex.plugins.openai.openai_llms import openai_list_available_models
from pipelex.plugins.plugin_sdk_registry import Plugin

if TYPE_CHECKING:
    from openai.types import Model

    from pipelex.cogt.model_backends.backend import InferenceBackend


async def list_openai_models(
    sdk: str,
    backend_name: str,
    backend: InferenceBackend,
    flat: bool,
    any_listed: bool,
) -> None:
    """List OpenAI models."""
    plugin = Plugin(sdk=sdk, backend=backend_name)
    openai_models = await openai_list_available_models(
        plugin=plugin,
        backend=backend,
    )

    if flat:
        _display_openai_models_flat(
            models=openai_models,
            sdk=sdk,
            backend_name=backend_name,
            any_listed=any_listed,
        )
    else:
        _display_openai_models_table(
            models=openai_models,
            sdk=sdk,
            backend_name=backend_name,
        )


def _display_openai_models_flat(
    models: list[Model],
    sdk: str,
    backend_name: str,
    any_listed: bool,
) -> None:
    """Display OpenAI models in CSV format."""
    console = get_console()
    if not any_listed:
        console.print("model_id,created,owned_by,sdk,backend")
    for model in models:
        # Convert Unix timestamp to formatted date
        if hasattr(model, "created") and model.created:
            created = datetime.fromtimestamp(model.created).strftime("%Y-%m-%d")  # noqa: DTZ006
        else:
            created = "N/A"
        owned_by = model.owned_by if hasattr(model, "owned_by") else "N/A"
        console.print(f"{model.id},{created},{owned_by},{sdk},{backend_name}")


def _display_openai_models_table(
    models: list[Model],
    sdk: str,
    backend_name: str,
) -> None:
    """Display OpenAI models in table format."""
    table = Table(
        title=f"Available Models for Backend '{backend_name}' (SDK: {sdk})",
        show_header=True,
        header_style="bold cyan",
        box=box.SQUARE_DOUBLE_HEAD,
    )
    table.add_column("Model ID", style="green")
    table.add_column("Created", style="yellow")
    table.add_column("Owned By", style="blue")

    for model in models:
        # Convert Unix timestamp to formatted date
        if hasattr(model, "created") and model.created:
            created = datetime.fromtimestamp(model.created).strftime("%Y-%m-%d")  # noqa: DTZ006
        else:
            created = "N/A"
        owned_by = model.owned_by if hasattr(model, "owned_by") else "N/A"
        table.add_row(model.id, created, owned_by)
    console = get_console()
    console.print("\n")
    console.print(table)
    console.print("\n")
