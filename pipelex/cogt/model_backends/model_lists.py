from __future__ import annotations

import importlib.util
from datetime import datetime
from typing import TYPE_CHECKING, Any

from rich import box
from rich.console import Console
from rich.table import Table

from pipelex.cogt.exceptions import MissingDependencyError
from pipelex.config import get_config

if TYPE_CHECKING:
    from anthropic.types import ModelInfo
    from openai.types import Model

    from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.exceptions import PipelexCLIError
from pipelex.hub import get_models_manager
from pipelex.pipelex import Pipelex
from pipelex.plugins.openai.openai_llms import openai_list_available_models
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.tools.aws.aws_config import AwsCredentialsError


class ModelLister:
    """Handles listing available models for different SDK backends."""

    @classmethod
    async def list_models(
        cls,
        backend_name: str,
        flat: bool = False,
    ) -> None:
        """List available models for a specific backend.

        Args:
            backend_name: Name of the backend to list models for
            flat: Whether to output in flat CSV format
        """
        Pipelex.make()

        try:
            backend = get_models_manager().get_required_inference_backend(backend_name)
        except Exception as exc:
            msg = f"Backend '{backend_name}' not found: {exc}"
            raise PipelexCLIError(msg) from exc

        console = Console()

        # Determine which SDKs are used in this backend
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
                        await cls._list_openai_models(
                            sdk=sdk,
                            backend_name=backend_name,
                            backend=backend,
                            console=console,
                            flat=flat,
                            any_listed=any_listed,
                        )
                        any_listed = True

                    case "anthropic" | "bedrock_anthropic":
                        if importlib.util.find_spec("anthropic") is None:
                            lib_name = "anthropic"
                            lib_extra_name = "anthropic"
                            msg = (
                                "The anthropic SDK is required to use Anthropic models via the anthropic client. "
                                "However, you can use Anthropic models through bedrock directly "
                                "by using the 'bedrock-anthropic-claude' llm family. (eg: bedrock-anthropic-claude)"
                            )
                            raise MissingDependencyError(
                                lib_name,
                                lib_extra_name,
                                msg,
                            )

                        from pipelex.plugins.anthropic.anthropic_exceptions import AnthropicSDKUnsupportedError  # noqa: PLC0415

                        try:
                            await cls._list_anthropic_models(
                                sdk=sdk,
                                backend_name=backend_name,
                                backend=backend,
                                console=console,
                                flat=flat,
                                any_listed=any_listed,
                            )
                            any_listed = True
                        except AnthropicSDKUnsupportedError:
                            unsupported_sdks.append(sdk)
                            continue

                    case "mistral":
                        if importlib.util.find_spec("mistralai") is None:
                            lib_name = "mistralai"
                            lib_extra_name = "mistral"
                            msg = (
                                "The mistralai SDK is required to use Mistral models through the mistralai client. "
                                "However, you can use Mistral models through bedrock directly "
                                "by using the 'bedrock-mistral' llm family. (eg: bedrock-mistral-large)"
                            )
                            raise MissingDependencyError(
                                lib_name,
                                lib_extra_name,
                                msg,
                            )

                        cls._list_mistral_models(
                            sdk=sdk,
                            backend_name=backend_name,
                            console=console,
                            flat=flat,
                            any_listed=any_listed,
                        )
                        any_listed = True

                    case "bedrock" | "bedrock_aioboto3":
                        if importlib.util.find_spec("boto3") is None or importlib.util.find_spec("aioboto3") is None:
                            lib_name = "boto3,aioboto3"
                            lib_extra_name = "bedrock"
                            msg = "The boto3 and aioboto3 SDKs are required to use Bedrock models."
                            raise MissingDependencyError(
                                lib_name,
                                lib_extra_name,
                                msg,
                            )

                        await cls._list_bedrock_models(
                            sdk=sdk,
                            backend_name=backend_name,
                            backend=backend,
                            console=console,
                            flat=flat,
                            any_listed=any_listed,
                        )
                        any_listed = True

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
        cls._display_unsupported_sdks_message(
            any_listed=any_listed,
            unsupported_sdks=unsupported_sdks,
            backend_name=backend_name,
            models_by_sdk=models_by_sdk,
            console=console,
            flat=flat,
        )

    @classmethod
    async def _list_openai_models(
        cls,
        sdk: str,
        backend_name: str,
        backend: InferenceBackend,
        console: Console,
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
            cls._display_openai_models_flat(
                models=openai_models,
                sdk=sdk,
                backend_name=backend_name,
                console=console,
                any_listed=any_listed,
            )
        else:
            cls._display_openai_models_table(
                models=openai_models,
                sdk=sdk,
                backend_name=backend_name,
                console=console,
            )

    @classmethod
    async def _list_anthropic_models(
        cls,
        sdk: str,
        backend_name: str,
        backend: InferenceBackend,
        console: Console,
        flat: bool,
        any_listed: bool,
    ) -> None:
        """List Anthropic models."""
        if importlib.util.find_spec("anthropic") is None:
            lib_name = "anthropic"
            lib_extra_name = "anthropic"
            msg = (
                "The anthropic SDK is required to use Anthropic models via the anthropic client. "
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
                cls._display_anthropic_models_flat(
                    models=anthropic_models,
                    sdk=sdk,
                    backend_name=backend_name,
                    console=console,
                    any_listed=any_listed,
                )
            else:
                cls._display_anthropic_models_table(
                    models=anthropic_models,
                    sdk=sdk,
                    backend_name=backend_name,
                    console=console,
                )
        except AuthenticationError as auth_exc:
            msg = f"Authentication error for SDK '{sdk}' in backend '{backend_name}': {auth_exc}"
            raise PipelexCLIError(msg) from auth_exc

    @classmethod
    def _list_mistral_models(
        cls,
        sdk: str,
        backend_name: str,
        console: Console,
        flat: bool,
        any_listed: bool,
    ) -> None:
        """List Mistral models."""
        if importlib.util.find_spec("mistralai") is None:
            lib_name = "mistralai"
            lib_extra_name = "mistral"
            msg = (
                "The mistralai SDK is required to use Mistral models through the mistralai client. "
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
            cls._display_mistral_models_flat(
                models=mistral_models,
                sdk=sdk,
                backend_name=backend_name,
                console=console,
                any_listed=any_listed,
            )
        else:
            cls._display_mistral_models_table(
                models=mistral_models,
                sdk=sdk,
                backend_name=backend_name,
                console=console,
            )

    @classmethod
    async def _list_bedrock_models(
        cls,
        sdk: str,
        backend_name: str,
        backend: InferenceBackend,
        console: Console,
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
            bedrock_models_list = await bedrock_list_available_models(
                plugin=plugin,
                backend=backend,
            )

            if flat:
                cls._display_bedrock_models_flat(
                    models=bedrock_models_list,
                    sdk=sdk,
                    backend_name=backend_name,
                    aws_region=aws_region,
                    console=console,
                    any_listed=any_listed,
                )
            else:
                cls._display_bedrock_models_table(
                    models=bedrock_models_list,
                    sdk=sdk,
                    aws_region=aws_region,
                    console=console,
                )

        except Exception as exc:
            msg = f"Error listing Bedrock models: {exc}"
            raise PipelexCLIError(msg) from exc

    @staticmethod
    def _display_openai_models_flat(
        models: list[Model],
        sdk: str,
        backend_name: str,
        console: Console,
        any_listed: bool,
    ) -> None:
        """Display OpenAI models in CSV format."""
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

    @staticmethod
    def _display_openai_models_table(
        models: list[Model],
        sdk: str,
        backend_name: str,
        console: Console,
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

        console.print("\n")
        console.print(table)
        console.print("\n")

    @staticmethod
    def _display_anthropic_models_flat(
        models: list[ModelInfo],
        sdk: str,
        backend_name: str,
        console: Console,
        any_listed: bool,
    ) -> None:
        """Display Anthropic models in CSV format."""
        if not any_listed:
            console.print("model_id,display_name,created_at,sdk,backend")
        for anthropic_model in models:
            created_date = anthropic_model.created_at.strftime("%Y-%m-%d") if anthropic_model.created_at else "N/A"
            display_name = anthropic_model.display_name.replace(",", ";") if anthropic_model.display_name else "N/A"
            console.print(f"{anthropic_model.id},{display_name},{created_date},{sdk},{backend_name}")

    @staticmethod
    def _display_anthropic_models_table(
        models: list[ModelInfo],
        sdk: str,
        backend_name: str,
        console: Console,
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

        console.print("\n")
        console.print(table)
        console.print("\n")

    @staticmethod
    def _display_mistral_models_flat(
        models: list[Any],
        sdk: str,
        backend_name: str,
        console: Console,
        any_listed: bool,
    ) -> None:
        """Display Mistral models in CSV format."""
        if not any_listed:
            console.print("model_id,max_context_length,sdk,backend")
        for mistral_model in models:
            max_ctx = str(mistral_model.max_context_length) if mistral_model.max_context_length else "N/A"
            console.print(f"{mistral_model.id},{max_ctx},{sdk},{backend_name}")

    @staticmethod
    def _display_mistral_models_table(
        models: list[Any],
        sdk: str,
        backend_name: str,
        console: Console,
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

        console.print("\n")
        console.print(table)
        console.print("\n")

    @staticmethod
    def _display_bedrock_models_flat(
        models: list[dict[str, Any]],
        sdk: str,
        backend_name: str,
        aws_region: str,
        console: Console,
        any_listed: bool,
    ) -> None:
        """Display Bedrock models in CSV format."""
        if not any_listed:
            console.print("model_id,provider,model_arn,sdk,backend,region")
        for bedrock_model in models:  # pyright: ignore[reportUnknownVariableType]
            model_id = bedrock_model.get("modelId", "N/A")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
            provider = bedrock_model.get("providerName", "N/A")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
            model_arn = bedrock_model.get("modelArn", "N/A")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
            console.print(f"{model_id},{provider},{model_arn},{sdk},{backend_name},{aws_region}")  # pyright: ignore[reportUnknownArgumentType]

    @staticmethod
    def _display_bedrock_models_table(
        models: list[dict[str, Any]],
        sdk: str,
        aws_region: str,
        console: Console,
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

        console.print("\n")
        console.print(table)
        console.print("\n")

    @staticmethod
    def _display_unsupported_sdks_message(
        any_listed: bool,
        unsupported_sdks: list[str],
        backend_name: str,
        models_by_sdk: dict[str, list[str]],
        console: Console,
        flat: bool,
    ) -> None:
        """Display message about unsupported SDKs."""
        if not any_listed and unsupported_sdks:
            if not flat:
                console.print(f"\n[yellow]Note: Backend '{backend_name}' has models using SDKs that don't support remote listing:[/yellow]")
                for sdk in unsupported_sdks:
                    console.print(f"  • {sdk} ({len(models_by_sdk[sdk])} configured model(s))")
                console.print("\n[dim]Configured models are still available for use in pipelines.[/dim]\n")
            else:
                # In flat mode, just print a simple comment
                console.print(f"# Note: Backend '{backend_name}' has {len(unsupported_sdks)} SDK(s) that don't support remote listing")
