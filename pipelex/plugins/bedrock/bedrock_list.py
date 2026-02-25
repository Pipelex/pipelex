from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING, Any

from rich import box
from rich.table import Table

from pipelex.cli.exceptions import PipelexCLIError
from pipelex.config import get_config
from pipelex.exceptions import MissingDependencyError
from pipelex.hub import get_console
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.tools.aws.aws_config import AwsCredentialsError

if TYPE_CHECKING:
    from pipelex.cogt.model_backends.backend import InferenceBackend


def list_bedrock_models(
    sdk: str,
    backend_name: str,
    backend: InferenceBackend,
    flat: bool,
    any_listed: bool,
) -> None:
    """List Bedrock models."""
    if importlib.util.find_spec("boto3") is None or importlib.util.find_spec("aioboto3") is None:
        lib_name = "boto3,aioboto3"
        lib_extra_name = "bedrock"
        msg = "The boto3 and aioboto3 SDKs are required to use Bedrock models."
        raise MissingDependencyError(
            lib_name,
            lib_extra_name,
            msg,
        )

    from pipelex.plugins.bedrock.bedrock_llms import bedrock_list_available_models  # noqa: PLC0415

    plugin = Plugin(sdk=sdk, backend=backend_name)

    try:
        # Get AWS region for display
        aws_config = get_config().pipelex.aws_config
        _, _, aws_region = aws_config.get_aws_access_keys()
    except AwsCredentialsError as exc:
        msg = f"Error getting AWS credentials for Bedrock: {exc}"
        raise PipelexCLIError(msg) from exc

    try:
        # List available models using the plugin-specific function
        bedrock_models_list = bedrock_list_available_models(
            plugin=plugin,
            backend=backend,
        )

        if flat:
            _display_bedrock_models_flat(
                models=bedrock_models_list,
                sdk=sdk,
                backend_name=backend_name,
                aws_region=aws_region,
                any_listed=any_listed,
            )
        else:
            _display_bedrock_models_table(
                models=bedrock_models_list,
                sdk=sdk,
                aws_region=aws_region,
            )

    except Exception as exc:
        msg = f"Error listing Bedrock models: {exc}"
        raise PipelexCLIError(msg) from exc


def _display_bedrock_models_flat(
    models: list[dict[str, Any]],
    sdk: str,
    backend_name: str,
    aws_region: str,
    any_listed: bool,
) -> None:
    """Display Bedrock models in CSV format."""
    console = get_console()
    if not any_listed:
        console.print("model_id,provider,model_arn,sdk,backend,region")
    for bedrock_model in models:  # pyright: ignore[reportUnknownVariableType]
        model_id = bedrock_model.get("modelId", "N/A")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        provider = bedrock_model.get("providerName", "N/A")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        model_arn = bedrock_model.get("modelArn", "N/A")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        console.print(f"{model_id},{provider},{model_arn},{sdk},{backend_name},{aws_region}")  # pyright: ignore[reportUnknownArgumentType]


def _display_bedrock_models_table(
    models: list[dict[str, Any]],
    sdk: str,
    aws_region: str,
) -> None:
    """Display Bedrock models in table format."""
    table = Table(
        title=f"Available Bedrock Models in {aws_region} (SDK: {sdk})",
        show_header=True,
        header_style="bold cyan",
        box=box.SQUARE_DOUBLE_HEAD,
    )
    table.add_column("Model ID", style="green")
    table.add_column("Provider", style="blue")
    table.add_column("Model ARN", style="yellow")

    for bedrock_model in models:  # pyright: ignore[reportUnknownVariableType]
        model_id = bedrock_model.get("modelId", "N/A")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        provider = bedrock_model.get("providerName", "N/A")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        model_arn = bedrock_model.get("modelArn", "N/A")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        table.add_row(model_id, provider, model_arn)  # pyright: ignore[reportUnknownArgumentType]

    console = get_console()
    console.print("\n")
    console.print(table)
    console.print("\n")
