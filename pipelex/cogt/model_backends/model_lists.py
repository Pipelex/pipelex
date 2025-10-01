from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Annotated, Any

import typer
from anthropic import AuthenticationError
from rich import box
from rich.console import Console
from rich.table import Table

from pipelex import pretty_print
from pipelex.cogt.exceptions import MissingDependencyError
from pipelex.config import get_config
from pipelex.exceptions import PipelexCLIError, PipelexConfigError
from pipelex.hub import get_models_manager, get_pipe_provider, get_required_pipe
from pipelex.pipelex import Pipelex
from pipelex.plugins.anthropic.anthropic_exceptions import AnthropicSDKUnsupportedError
from pipelex.plugins.anthropic.anthropic_llms import anthropic_list_available_models
from pipelex.plugins.mistral.mistral_llms import mistral_list_available_models
from pipelex.plugins.openai.openai_llms import openai_list_available_models
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.tools.aws.aws_config import AwsCredentialsError
from pipelex.tools.config.manager import config_manager

# Check if boto3 is available for Bedrock support
try:
    import boto3

    _has_boto3 = True
except ImportError:
    _has_boto3 = False


async def do_show_models(
    backend_name: str,
    relative_config_folder_path: str = "./pipelex_libraries",
    flat: bool = False,
) -> None:
    """List available models for a specific backend."""
    Pipelex.make(relative_config_folder_path=relative_config_folder_path, from_file=False)

    try:
        backend = get_models_manager().get_required_inference_backend(backend_name)
    except Exception as exc:
        msg = f"Backend '{backend_name}' not found: {exc}"
        raise PipelexCLIError(msg) from exc

    console = Console()

    # Determine which SDKs are used in this backend
    # A backend can have models using different SDKs
    if not backend.model_specs:
        msg = f"Backend '{backend_name}' has no model specifications"
        raise PipelexCLIError(msg)

    # Group models by SDK
    models_by_sdk: dict[str, list[str]] = {}
    for model_name, model_spec in backend.model_specs.items():
        sdk = model_spec.sdk
        if sdk not in models_by_sdk:
            models_by_sdk[sdk] = []
        models_by_sdk[sdk].append(model_name)

    # Process each SDK separately
    any_listed = False
    unsupported_sdks: list[str] = []

    for sdk in models_by_sdk:
        try:
            match sdk:
                case "openai" | "azure_openai":
                    plugin = Plugin(sdk=sdk, backend=backend_name)
                    openai_models = await openai_list_available_models(
                        plugin=plugin,
                        backend=backend,
                    )

                    if flat:
                        # CSV output
                        if not any_listed:
                            console.print("model_id,created,owned_by,sdk,backend")
                        for model in openai_models:
                            # Convert Unix timestamp to formatted date
                            if hasattr(model, "created") and model.created:
                                created = datetime.fromtimestamp(model.created, tz=UTC).strftime("%Y-%m-%d")
                            else:
                                created = "N/A"
                            owned_by = model.owned_by if hasattr(model, "owned_by") else "N/A"
                            console.print(f"{model.id},{created},{owned_by},{sdk},{backend_name}")
                    else:
                        # Create and display table
                        table = Table(
                            title=f"Available Models for Backend '{backend_name}' (SDK: {sdk})",
                            show_header=True,
                            header_style="bold cyan",
                            box=box.SQUARE_DOUBLE_HEAD,
                        )
                        table.add_column("Model ID", style="green")
                        table.add_column("Created", style="yellow")
                        table.add_column("Owned By", style="blue")

                        for model in openai_models:
                            # Convert Unix timestamp to formatted date
                            if hasattr(model, "created") and model.created:
                                created = datetime.fromtimestamp(model.created, tz=UTC).strftime("%Y-%m-%d")
                            else:
                                created = "N/A"
                            owned_by = model.owned_by if hasattr(model, "owned_by") else "N/A"
                            table.add_row(model.id, created, owned_by)

                        console.print("\n")
                        console.print(table)
                        console.print("\n")
                    any_listed = True

                case "anthropic" | "bedrock_anthropic":
                    plugin = Plugin(sdk=sdk, backend=backend_name)
                    try:
                        anthropic_models = await anthropic_list_available_models(
                            plugin=plugin,
                            backend=backend,
                        )

                        if flat:
                            # CSV output
                            if not any_listed:
                                console.print("model_id,display_name,created_at,sdk,backend")
                            for anthropic_model in anthropic_models:
                                created_date = anthropic_model.created_at.strftime("%Y-%m-%d") if anthropic_model.created_at else "N/A"
                                display_name = anthropic_model.display_name.replace(",", ";") if anthropic_model.display_name else "N/A"
                                console.print(f"{anthropic_model.id},{display_name},{created_date},{sdk},{backend_name}")
                        else:
                            # Create and display table
                            table = Table(
                                title=f"Available Models for Backend '{backend_name}' (SDK: {sdk})",
                                show_header=True,
                                header_style="bold cyan",
                                box=box.SQUARE_DOUBLE_HEAD,
                            )
                            table.add_column("Model ID", style="green")
                            table.add_column("Display Name", style="blue")
                            table.add_column("Created At", style="yellow")

                            for anthropic_model in anthropic_models:
                                created_date = anthropic_model.created_at.strftime("%Y-%m-%d") if anthropic_model.created_at else "N/A"
                                table.add_row(anthropic_model.id, anthropic_model.display_name, created_date)

                            console.print("\n")
                            console.print(table)
                            console.print("\n")
                        any_listed = True
                    except AuthenticationError as auth_exc:
                        msg = f"Authentication error for SDK '{sdk}' in backend '{backend_name}': {auth_exc}"
                        raise PipelexCLIError(msg) from auth_exc
                    except AnthropicSDKUnsupportedError:
                        unsupported_sdks.append(sdk)
                        continue

                case "mistral":
                    mistral_models = mistral_list_available_models()

                    if flat:
                        # CSV output
                        if not any_listed:
                            console.print("model_id,max_context_length,sdk,backend")
                        for mistral_model in mistral_models:
                            max_ctx = str(mistral_model.max_context_length) if mistral_model.max_context_length else "N/A"
                            console.print(f"{mistral_model.id},{max_ctx},{sdk},{backend_name}")
                    else:
                        # Create and display table
                        table = Table(
                            title=f"Available Models for Backend '{backend_name}' (SDK: {sdk})",
                            show_header=True,
                            header_style="bold cyan",
                            box=box.SQUARE_DOUBLE_HEAD,
                        )
                        table.add_column("Model ID", style="green")
                        table.add_column("Max Context Length", style="yellow")

                        for mistral_model in mistral_models:
                            max_ctx = str(mistral_model.max_context_length) if mistral_model.max_context_length else "N/A"
                            table.add_row(mistral_model.id, max_ctx)

                        console.print("\n")
                        console.print(table)
                        console.print("\n")
                    any_listed = True

                case "bedrock" | "bedrock_aioboto3":
                    if not _has_boto3:
                        msg = "boto3 is required to list Bedrock models. Please install it with: pip install boto3"
                        raise PipelexCLIError(msg)

                    try:
                        aws_config = get_config().pipelex.aws_config
                        aws_access_key_id, aws_secret_access_key, aws_region = aws_config.get_aws_access_keys()
                    except AwsCredentialsError as exc:
                        msg = f"Error getting AWS credentials for Bedrock: {exc}"
                        raise PipelexCLIError(msg) from exc

                    try:
                        import aioboto3  # noqa: PLC0415
                        import boto3  # noqa: PLC0415
                    except ImportError as exc:
                        lib_name = "boto3,aioboto3"
                        lib_extra_name = "bedrock"
                        msg = "The boto3 and aioboto3 SDKs are required to use Bedrock models."
                        raise MissingDependencyError(
                            lib_name,
                            lib_extra_name,
                            msg,
                        ) from exc

                    try:
                        # Create bedrock client
                        bedrock_client = boto3.client(  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
                            "bedrock",
                            region_name=aws_region,
                            aws_access_key_id=aws_access_key_id,
                            aws_secret_access_key=aws_secret_access_key,
                        )

                        # List foundation models
                        response: dict[str, Any] = bedrock_client.list_foundation_models()  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
                        bedrock_models_list: list[dict[str, Any]] = response["modelSummaries"]  # pyright: ignore[reportUnknownVariableType]

                        if flat:
                            # CSV output
                            if not any_listed:
                                console.print("model_id,provider,model_arn,sdk,backend,region")
                            for bedrock_model in bedrock_models_list:  # pyright: ignore[reportUnknownVariableType]
                                model_id = bedrock_model.get("modelId", "N/A")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
                                provider = bedrock_model.get("providerName", "N/A")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
                                model_arn = bedrock_model.get("modelArn", "N/A")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
                                console.print(f"{model_id},{provider},{model_arn},{sdk},{backend_name},{aws_region}")  # pyright: ignore[reportUnknownArgumentType]
                        else:
                            # Create and display table
                            table = Table(
                                title=f"Available Bedrock Models in {aws_region} (SDK: {sdk})",
                                show_header=True,
                                header_style="bold cyan",
                                box=box.SQUARE_DOUBLE_HEAD,
                            )
                            table.add_column("Model ID", style="green")
                            table.add_column("Provider", style="blue")
                            table.add_column("Model ARN", style="yellow")

                            for bedrock_model in bedrock_models_list:  # pyright: ignore[reportUnknownVariableType]
                                model_id = bedrock_model.get("modelId", "N/A")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
                                provider = bedrock_model.get("providerName", "N/A")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
                                model_arn = bedrock_model.get("modelArn", "N/A")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
                                table.add_row(model_id, provider, model_arn)  # pyright: ignore[reportUnknownArgumentType]

                            console.print("\n")
                            console.print(table)
                            console.print("\n")
                        any_listed = True

                    except Exception as exc:
                        msg = f"Error listing Bedrock models: {exc}"
                        raise PipelexCLIError(msg) from exc

                case _:
                    # SDK doesn't support listing
                    unsupported_sdks.append(sdk)
                    continue

        except PipelexCLIError:
            raise
        except Exception as exc:
            msg = f"Error listing models for SDK '{sdk}' in backend '{backend_name}': {exc}"
            raise PipelexCLIError(msg) from exc

    # After all SDKs have been processed
    if not any_listed and unsupported_sdks:
        if not flat:
            console.print(f"\n[yellow]Note: Backend '{backend_name}' has models using SDKs that don't support remote listing:[/yellow]")
            for sdk in unsupported_sdks:
                console.print(f"  • {sdk} ({len(models_by_sdk[sdk])} configured model(s))")
            console.print("\n[dim]Configured models are still available for use in pipelines.[/dim]\n")
        else:
            # In flat mode, just print a simple comment
            console.print(f"# Note: Backend '{backend_name}' has {len(unsupported_sdks)} SDK(s) that don't support remote listing")
