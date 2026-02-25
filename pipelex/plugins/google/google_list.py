from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING, Any

from rich import box
from rich.table import Table

from pipelex.exceptions import MissingDependencyError
from pipelex.hub import get_console

if TYPE_CHECKING:
    from pipelex.cogt.model_backends.backend import InferenceBackend


async def list_google_models(
    sdk: str,
    backend_name: str,
    backend: InferenceBackend,
    flat: bool,
    any_listed: bool,
) -> None:
    """List Google GenAI models."""
    if importlib.util.find_spec("google.genai") is None:
        lib_name = "google-genai"
        lib_extra_name = "google"
        msg = "The google-genai SDK is required to use Google GenAI models."
        raise MissingDependencyError(
            lib_name,
            lib_extra_name,
            msg,
        )

    from pipelex.plugins.google.google_factory import GoogleFactory  # noqa: PLC0415

    client = GoogleFactory.make_google_client(backend)
    google_models: list[Any] = []
    async for model in await client.aio.models.list():
        google_models.append(model)

    if flat:
        _display_google_models_flat(
            models=google_models,
            sdk=sdk,
            backend_name=backend_name,
            any_listed=any_listed,
        )
    else:
        _display_google_models_table(
            models=google_models,
            sdk=sdk,
            backend_name=backend_name,
        )


def _display_google_models_flat(
    models: list[Any],
    sdk: str,
    backend_name: str,
    any_listed: bool,
) -> None:
    """Display Google GenAI models in CSV format."""
    console = get_console()
    if not any_listed:
        console.print("model_name,display_name,description,sdk,backend")
    for google_model in models:
        model_name = google_model.name or "N/A"
        display_name = google_model.display_name.replace(",", ";") if google_model.display_name else "N/A"
        description = google_model.description.replace(",", ";").replace("\n", " ")[:100] if google_model.description else "N/A"
        console.print(f"{model_name},{display_name},{description},{sdk},{backend_name}")


def _display_google_models_table(
    models: list[Any],
    sdk: str,
    backend_name: str,
) -> None:
    """Display Google GenAI models in table format."""
    table = Table(
        title=f"Available Models for Backend '{backend_name}' (SDK: {sdk})",
        show_header=True,
        header_style="bold cyan",
        box=box.SQUARE_DOUBLE_HEAD,
    )
    table.add_column("Model Name", style="green")
    table.add_column("Display Name", style="blue")
    table.add_column("Description", style="yellow", max_width=60)

    for google_model in models:
        model_name = google_model.name or "N/A"
        display_name = google_model.display_name or "N/A"
        description = (
            google_model.description[:100] + "..."
            if google_model.description and len(google_model.description) > 100
            else (google_model.description or "N/A")
        )
        table.add_row(model_name, display_name, description)

    console = get_console()
    console.print("\n")
    console.print(table)
    console.print("\n")
