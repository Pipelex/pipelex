from __future__ import annotations

from rich.markup import escape

from pipelex.cli.exceptions import PipelexCLIError
from pipelex.cogt.exceptions import ModelListingUnsupportedError, ModelManagerError
from pipelex.hub import get_console, get_model_lister_registry, get_models_manager


class ModelLister:
    """Handles listing available models for different SDK backends."""

    @classmethod
    async def list_models(
        cls,
        backend_name: str,
        *,
        flat: bool = False,
    ) -> None:
        """List available models for a specific backend.

        Args:
            backend_name: Name of the backend to list models for
            flat: Whether to output in flat CSV format
        """
        try:
            backend = get_models_manager().get_required_inference_backend(backend_name)
        except ModelManagerError as exc:
            # CLI boundary: convert the domain error to a ClickException so Typer renders it cleanly (no traceback).
            raise PipelexCLIError(str(exc)) from exc

        # A backend with no model specs is a valid config state — there is simply nothing to list.
        if not backend.model_specs:
            console = get_console()
            if flat:
                console.print(f"# Note: Backend '{escape(backend_name)}' has no models configured")
            else:
                console.print(f"\n[yellow]Note: Backend '{escape(backend_name)}' has no models configured.[/yellow]\n")
            return

        # Group models by SDK
        models_by_sdk: dict[str, list[str]] = {}
        for model_name, model_spec in backend.model_specs.items():
            sdk = model_spec.sdk
            if sdk not in models_by_sdk:
                models_by_sdk[sdk] = []
            models_by_sdk[sdk].append(model_name)

        # Process each SDK separately, dispatching to the lister its backend plugin registered.
        # A missing-extra guard lives inside each lister (it raises MissingDependencyError when
        # called without its SDK installed), so the loop names no integration.
        lister_registry = get_model_lister_registry()
        any_listed = False
        unsupported_sdks: list[str] = []

        for sdk in models_by_sdk:
            lister = lister_registry.get_optional(sdk=sdk)
            if lister is None:
                # No plugin registered a lister for this SDK — it does not support remote listing.
                unsupported_sdks.append(sdk)
                continue
            try:
                await lister(sdk=sdk, backend_name=backend_name, backend=backend, flat=flat, any_listed=any_listed)
                any_listed = True
            except ModelListingUnsupportedError:
                # The lister's client variant cannot enumerate models (e.g. a bedrock-backed
                # Anthropic client) — the same soft outcome as a missing lister.
                unsupported_sdks.append(sdk)
                continue
            except PipelexCLIError:
                raise
            except Exception as exc:
                # Case 2: lister dispatch is an unbounded surface (lazy plugin imports, network, remote
                # provider APIs); any failure is converted to PipelexCLIError with context. Never swallows.
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
        *,
        unsupported_sdks: list[str],
        backend_name: str,
        models_by_sdk: dict[str, list[str]],
        flat: bool,
    ) -> None:
        """Display message about unsupported SDKs."""
        if not any_listed and unsupported_sdks:
            console = get_console()
            if not flat:
                console.print(
                    f"\n[yellow]Note: Backend '{escape(backend_name)}' has models using SDKs that we don't support for remote listing:[/yellow]"
                )
                for sdk in unsupported_sdks:
                    console.print(f"  • {sdk} ({len(models_by_sdk[sdk])} configured model(s))")
                console.print("\n[dim]Configured models are still available for use in pipelines.[/dim]\n")
            else:
                # In flat mode, just print a simple comment
                console.print(f"# Note: Backend '{escape(backend_name)}' has {len(unsupported_sdks)} SDK(s) that we don't support for remote listing")
