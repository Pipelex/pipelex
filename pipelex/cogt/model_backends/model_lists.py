from __future__ import annotations

import importlib.util

from pipelex.cli.exceptions import PipelexCLIError
from pipelex.exceptions import MissingDependencyError
from pipelex.hub import get_console, get_models_manager


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
        try:
            backend = get_models_manager().get_required_inference_backend(backend_name)
        except Exception as exc:
            msg = f"Backend '{backend_name}' not found: {exc}"
            # TODO: This should not raise this error in here.
            raise PipelexCLIError(msg) from exc

        # Determine which SDKs are used in this backend
        if not backend.model_specs:
            msg = f"Backend '{backend_name}' has no model specifications"
            # TODO: This should not raise this error in here.
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
                    case "openai" | "azure_openai" | "openai_responses" | "azure_openai_responses":
                        from pipelex.plugins.openai.openai_list import list_openai_models  # noqa: PLC0415

                        await list_openai_models(
                            sdk=sdk,
                            backend_name=backend_name,
                            backend=backend,
                            flat=flat,
                            any_listed=any_listed,
                        )
                        any_listed = True

                    case "anthropic":
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

                        from pipelex.plugins.anthropic.anthropic_exceptions import AnthropicSDKUnsupportedError  # noqa: PLC0415
                        from pipelex.plugins.anthropic.anthropic_list import list_anthropic_models  # noqa: PLC0415

                        try:
                            await list_anthropic_models(
                                sdk=sdk,
                                backend_name=backend_name,
                                backend=backend,
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
                                "The mistralai SDK is required in order to use Mistral models through the mistralai client. "
                                "However, you can use Mistral models through bedrock directly "
                                "by using the 'bedrock-mistral' llm family. (eg: bedrock-mistral-large)"
                            )
                            raise MissingDependencyError(
                                lib_name,
                                lib_extra_name,
                                msg,
                            )

                        from pipelex.plugins.mistral.mistral_list import list_mistral_models  # noqa: PLC0415

                        list_mistral_models(
                            sdk=sdk,
                            backend_name=backend_name,
                            flat=flat,
                            any_listed=any_listed,
                        )
                        any_listed = True

                    case "google":
                        if importlib.util.find_spec("google.genai") is None:
                            lib_name = "google-genai"
                            lib_extra_name = "google"
                            msg = "The google-genai SDK is required to use Google GenAI models."
                            raise MissingDependencyError(
                                lib_name,
                                lib_extra_name,
                                msg,
                            )

                        from pipelex.plugins.google.google_list import list_google_models  # noqa: PLC0415

                        await list_google_models(
                            sdk=sdk,
                            backend_name=backend_name,
                            backend=backend,
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

                        from pipelex.plugins.bedrock.bedrock_list import list_bedrock_models  # noqa: PLC0415

                        list_bedrock_models(
                            sdk=sdk,
                            backend_name=backend_name,
                            backend=backend,
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
            flat=flat,
        )

    @staticmethod
    def _display_unsupported_sdks_message(
        any_listed: bool,
        unsupported_sdks: list[str],
        backend_name: str,
        models_by_sdk: dict[str, list[str]],
        flat: bool,
    ) -> None:
        """Display message about unsupported SDKs."""
        if not any_listed and unsupported_sdks:
            console = get_console()
            if not flat:
                console.print(f"\n[yellow]Note: Backend '{backend_name}' has models using SDKs that we don't support for remote listing:[/yellow]")
                for sdk in unsupported_sdks:
                    console.print(f"  • {sdk} ({len(models_by_sdk[sdk])} configured model(s))")
                console.print("\n[dim]Configured models are still available for use in pipelines.[/dim]\n")
            else:
                # In flat mode, just print a simple comment
                console.print(f"# Note: Backend '{backend_name}' has {len(unsupported_sdks)} SDK(s) that we don't support for remote listing")
