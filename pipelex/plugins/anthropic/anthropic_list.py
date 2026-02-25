from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

from rich import box
from rich.table import Table

from pipelex.cli.exceptions import PipelexCLIError
from pipelex.exceptions import MissingDependencyError
from pipelex.hub import get_console
from pipelex.plugins.plugin_sdk_registry import Plugin

if TYPE_CHECKING:
    from anthropic.types import ModelInfo

    from pipelex.cogt.model_backends.backend import InferenceBackend


async def list_anthropic_models(
    sdk: str,
    backend_name: str,
    backend: InferenceBackend,
    flat: bool,
    any_listed: bool,
) -> None:
    """List Anthropic models."""
    if importlib.util.find_spec("anthropic") is None:
        lib_name = "anthropic"
        lib_extra_name = "anthropic"
        msg = (
            "The anthropic SDK is required in order to use Anthropic models via the anthropic client. "
            "However, you can use Anthropic models through bedrock directly "
            "by using the 'bedrock-anthropic-claude' llm family. (eg: bedrock-anthropic-claude)"
        )
        raise MissingDependencyError(
            lib_name,
            lib_extra_name,
            msg,
        )

    from anthropic import AuthenticationError  # noqa: PLC0415

    from pipelex.plugins.anthropic.anthropic_llms import anthropic_list_available_models  # noqa: PLC0415

    plugin = Plugin(sdk=sdk, backend=backend_name)
    try:
        anthropic_models = await anthropic_list_available_models(
            plugin=plugin,
            backend=backend,
        )

        if flat:
            _display_anthropic_models_flat(
                models=anthropic_models,
                sdk=sdk,
                backend_name=backend_name,
                any_listed=any_listed,
            )
        else:
            _display_anthropic_models_table(
                models=anthropic_models,
                sdk=sdk,
                backend_name=backend_name,
            )
    except AuthenticationError as auth_exc:
        msg = f"Authentication error for SDK '{sdk}' in backend '{backend_name}': {auth_exc}"
        raise PipelexCLIError(msg) from auth_exc


def _display_anthropic_models_flat(
    models: list[ModelInfo],
    sdk: str,
    backend_name: str,
    any_listed: bool,
) -> None:
    """Display Anthropic models in CSV format."""
    console = get_console()
    if not any_listed:
        console.print("model_id,display_name,created_at,sdk,backend")
    for anthropic_model in models:
        created_date = anthropic_model.created_at.strftime("%Y-%m-%d") if anthropic_model.created_at else "N/A"
        display_name = anthropic_model.display_name.replace(",", ";") if anthropic_model.display_name else "N/A"
        console.print(f"{anthropic_model.id},{display_name},{created_date},{sdk},{backend_name}")


def _display_anthropic_models_table(
    models: list[ModelInfo],
    sdk: str,
    backend_name: str,
) -> None:
    """Display Anthropic models in table format."""
    table = Table(
        title=f"Available Models for Backend '{backend_name}' (SDK: {sdk})",
        show_header=True,
        header_style="bold cyan",
        box=box.SQUARE_DOUBLE_HEAD,
    )
    table.add_column("Model ID", style="green")
    table.add_column("Display Name", style="blue")
    table.add_column("Created At", style="yellow")

    for anthropic_model in models:
        created_date = anthropic_model.created_at.strftime("%Y-%m-%d") if anthropic_model.created_at else "N/A"
        table.add_row(anthropic_model.id, anthropic_model.display_name, created_date)

    console = get_console()
    console.print("\n")
    console.print(table)
    console.print("\n")
