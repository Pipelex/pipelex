"""Backend configuration logic for the init command."""

from pathlib import Path
from typing import Any

from rich.markup import escape
from tomlkit.exceptions import TOMLKitError

from pipelex import log
from pipelex.cli.commands.init.ide_extension import suggest_extension_install_if_needed
from pipelex.cli.commands.init.ui.backends_ui import (
    build_backend_selection_panel,
    display_selected_backends,
    get_backend_options_from_toml,
    get_currently_enabled_backends,
    prompt_backend_select,
)
from pipelex.cli.commands.init.ui.gateway_ui import (
    display_gateway_accepted_message,
    display_gateway_declined_message,
    prompt_gateway_acceptance,
)
from pipelex.cogt.model_backends.backend import MANAGED_GATEWAY_BACKEND_NAMES
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.runtime_hub import get_console
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.pipelex_service.pipelex_service_agreement import update_service_terms_acceptance
from pipelex.tools.misc.toml_utils import load_toml_from_path, load_toml_with_tomlkit, save_toml_to_path


def update_backends_in_toml(toml_doc: Any, *, selected_indices: list[int], backend_options: list[tuple[str, str]]) -> None:
    """Update the backends.toml document with selected backends.

    Args:
        toml_doc: The TOML document to update.
        selected_indices: List of backend indices to enable.
        backend_options: List of available backend options.
    """
    selected_backend_keys = {backend_options[idx][0] for idx in selected_indices}

    # Disable all backends first (except internal)
    for backend_key in toml_doc:
        if backend_key != "internal" and backend_key in toml_doc:
            backend_section = toml_doc[backend_key]
            # Set enabled field based on selection (works with tomlkit's special types)
            backend_section["enabled"] = backend_key in selected_backend_keys  # type: ignore[index]


def get_selected_backend_keys(backends_toml_path: Path) -> list[str]:
    """Extract the list of enabled backend keys from backends.toml.

    Args:
        backends_toml_path: Path to the backends.toml file.

    Returns:
        List of backend keys that are enabled (excluding 'internal').
    """
    selected_backends: list[str] = []

    if not backends_toml_path.exists():
        return selected_backends

    toml_doc = load_toml_from_path(backends_toml_path)

    for backend_key in toml_doc:
        if backend_key != "internal":
            backend_section = toml_doc[backend_key]
            if isinstance(backend_section, dict):
                # Only include backends that are explicitly enabled
                if backend_section.get("enabled", False) is True:  # type: ignore[union-attr]
                    selected_backends.append(backend_key)

    return selected_backends


def disable_managed_gateway_backends(backends_toml_path: Path) -> None:
    """Disable every Pipelex-managed gateway backend in backends.toml.

    Declining the service terms, or failing to record acceptance, has to leave *no* managed backend
    enabled: the terms are the Pipelex service's terms rather than one dialect's, so a boot that
    reaches the service through any of them is refused for want of the same acceptance.

    Args:
        backends_toml_path: Path to the backends.toml file.
    """
    if not backends_toml_path.exists():
        return

    toml_doc = load_toml_with_tomlkit(backends_toml_path)

    disabled_any = False
    for backend_name in MANAGED_GATEWAY_BACKEND_NAMES:
        if backend_name in toml_doc:
            toml_doc[backend_name]["enabled"] = False  # type: ignore[index]
            disabled_any = True
    if disabled_any:
        save_toml_to_path(toml_doc, path=backends_toml_path)


def customize_backends_config(*, is_first_time_setup: bool = False, target_config_dir: Path | None = None) -> None:
    """Interactively customize which inference backends are enabled in backends.toml.

    Args:
        is_first_time_setup: Whether this is the first time backends.toml is being set up.
        target_config_dir: Explicit target .pipelex directory. If None, uses config_manager.pipelex_config_dir.
    """
    console = get_console()
    effective_config_dir = target_config_dir or config_manager.pipelex_config_dir
    backends_toml_path = effective_config_dir / "inference" / "backends.toml"
    template_backends_path = Path(str(get_kit_configs_dir() / "inference" / "backends.toml"))

    if not backends_toml_path.exists():
        console.print("[yellow]⚠ Warning: backends.toml not found, skipping backend customization[/yellow]")
        return

    try:
        # Get backend options from template and existing config
        existing_path = backends_toml_path if backends_toml_path.exists() else None
        backend_options = get_backend_options_from_toml(template_backends_path, existing_path=existing_path)

        # Get currently enabled backends to show user their current selection
        currently_enabled = get_currently_enabled_backends(backends_toml_path, backend_options=backend_options)

        # If this is first-time setup, ignore what's in the template (all enabled)
        # and use only pipelex_gateway as the default
        if is_first_time_setup or (currently_enabled and len(currently_enabled) == len(backend_options)):
            currently_enabled = []

        # Load the backends.toml file
        toml_doc = load_toml_with_tomlkit(backends_toml_path)
        console.print()

        # UI: Display panel and get user selection
        console.print(build_backend_selection_panel(backend_options, currently_enabled=currently_enabled, is_first_time_setup=is_first_time_setup))
        selected_indices, selected_backends = prompt_backend_select(
            console=console,
            backend_options=backend_options,
            currently_enabled=currently_enabled,
            is_first_time_setup=is_first_time_setup,
        )

        # Suggest IDE extension install after backend selection, before gateway terms
        try:
            suggest_extension_install_if_needed(console=console)
        except EOFError as exc:
            # No stdin available for the install prompt — skip the optional IDE extension suggestion.
            log.debug(f"IDE extension suggestion skipped: {exc}")

        # Any managed gateway backend puts this installation behind the service terms, so the
        # prompt asks the same question the boot does rather than the narrower gateway-only one.
        gateway_terms_accepted: bool | None = None
        if any(backend_name in selected_backends for backend_name in MANAGED_GATEWAY_BACKEND_NAMES):
            gateway_accepted = prompt_gateway_acceptance(console=console)

            if gateway_accepted:
                display_gateway_accepted_message(console=console)
                gateway_terms_accepted = True
            else:
                display_gateway_declined_message(console=console)
                gateway_terms_accepted = False

                # Declining removes every managed backend, not only the one that raised the prompt.
                selected_indices = [idx for idx in selected_indices if backend_options[idx][0] not in MANAGED_GATEWAY_BACKEND_NAMES]

        # Business logic: Update and save backends.toml first (local operation)
        update_backends_in_toml(toml_doc, selected_indices=selected_indices, backend_options=backend_options)
        save_toml_to_path(toml_doc, path=backends_toml_path)

        # UI: Display confirmation
        display_selected_backends(console=console, selected_indices=selected_indices, backend_options=backend_options)

        # Save gateway terms acceptance to global config (separate from backends save)
        if gateway_terms_accepted is not None:
            try:
                global_config_dir = config_manager.global_config_dir
                global_config_dir.mkdir(parents=True, exist_ok=True)
                update_service_terms_acceptance(accepted=gateway_terms_accepted, config_dir=global_config_dir)
            except (OSError, TOMLKitError, TypeError) as terms_exc:
                # TypeError: a malformed service-config TOML (e.g. a scalar [agreement]) makes the
                # terms writer's dict assignment raise TypeError rather than a TOMLKitError.
                log.warning(f"Could not save gateway terms acceptance to global config: {terms_exc}")
                if gateway_terms_accepted:
                    # A managed backend is enabled in backends.toml but terms are not recorded —
                    # the runtime will fail. Disable them as a safety measure.
                    try:
                        disable_managed_gateway_backends(backends_toml_path)
                        console.print("[yellow]⚠ Could not save gateway terms. Gateway has been disabled to prevent errors.[/yellow]")
                    except (OSError, TOMLKitError, TypeError) as disable_exc:
                        log.warning(f"Could not disable gateway backend: {disable_exc}")
                        console.print(
                            "[red]⚠ Could not save gateway terms or disable gateway. Please manually disable pipelex_gateway in backends.toml.[/red]"
                        )
                    console.print("[dim]Re-run 'pipelex init' to set up gateway again.[/dim]")

    except Exception as exc:  # ruff: ignore[blind-except]
        # Command-level boundary: backend customization is optional during init — any failure is reported and init continues.
        console.print(f"[yellow]⚠ Warning: Failed to customize backends: {escape(str(exc))}[/yellow]")
        console.print("[dim]You can manually edit .pipelex/inference/backends.toml later[/dim]")
