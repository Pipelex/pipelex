"""Agent CLI init command -- non-interactive Pipelex initialization."""

import json
import os
import shutil
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from tomlkit import table

from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_error,
    agent_success_formatted,
    set_agent_cli_output_format,
)
from pipelex.cli.commands.init.backends import get_selected_backend_keys, update_backends_in_toml
from pipelex.cli.commands.init.config_files import init_config
from pipelex.cli.commands.init.ui.backends_ui import get_backend_options_from_toml
from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.cogt.model_routing.routing_profile import PipelexRoutingProfile
from pipelex.cogt.models.deck_manifest import compute_kit_manifest, write_manifest
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.pipelex_service.pipelex_service_agreement import (
    update_inference_setup_completed,
    update_service_terms_acceptance,
)
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME, TELEMETRY_PROJECT_TEMPLATE_FILE_NAME
from pipelex.tools.misc.file_utils import path_exists
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path


def _parse_config_arg(config_arg: str | None) -> dict[str, Any]:
    """Parse the --config argument as inline JSON or file path.

    Args:
        config_arg: Inline JSON string or path to a JSON file, or None.

    Returns:
        Parsed config dict. Empty dict if config_arg is None.
    """
    if config_arg is None:
        return {}

    if config_arg.startswith("{"):
        try:
            result: dict[str, Any] = json.loads(config_arg)
            return result
        except json.JSONDecodeError as exc:
            agent_error(f"Failed to parse inline JSON config: {exc}", "JSONDecodeError", cause=exc)
    else:
        try:
            with open(config_arg, encoding="utf-8") as file:
                loaded: Any = json.load(file)
                if not isinstance(loaded, dict):
                    agent_error(f"Config file must contain a JSON object, got {type(loaded).__name__}", "JSONDecodeError")
                return cast("dict[str, Any]", loaded)
        except FileNotFoundError as exc:
            agent_error(f"Config file not found: {config_arg}", "FileNotFoundError", cause=exc)
        except json.JSONDecodeError as exc:
            agent_error(f"Failed to parse config file JSON: {exc}", "JSONDecodeError", cause=exc)

    return {}


def _format_init_markdown(result: dict[str, Any]) -> str:
    """Render an init result dict as agent-readable markdown."""
    backends_enabled: list[str] = result.get("backends_enabled") or []
    lines: list[str] = [
        "# Pipelex initialized",
        "",
        f"**Target directory:** `{result['target_dir']}`",
        "",
        f"**Backends enabled:** {', '.join(backends_enabled) or 'none'}",
        "",
        f"**Routing profile:** `{result['routing_profile']}`",
        "",
        f"**Inference setup completed:** {result.get('inference_setup_completed', False)}",
    ]
    return "\n".join(lines)


def _resolve_target_dir(global_: bool) -> Path:
    """Resolve the target directory for initialization.

    Args:
        global_: If True, force global ~/.pipelex/ directory.

    Returns:
        Absolute path to the target config directory.
    """
    if global_:
        return config_manager.global_config_dir
    # Default: project-level .pipelex/ at detected project root
    project_root = config_manager.project_root
    if project_root is None:
        agent_error(
            "No project root found (no .git, pyproject.toml, etc. in parent directories). "
            "Use --global/-g to target the global ~/.pipelex/ directory.",
            "ArgumentError",
        )
    return project_root / ".pipelex"


def _copy_inference_templates(target_dir: Path) -> None:
    """Copy inference template files to the target directory.

    init_config() skips the inference/ directory (handled independently).
    This function copies the inference templates that the agent CLI needs
    for backend and routing configuration.

    Args:
        target_dir: Target config directory (e.g. .pipelex/).
    """
    template_inference_dir = Path(str(get_kit_configs_dir())) / "inference"
    target_inference_dir = target_dir / "inference"

    # Copy backends.toml
    template_backends_path = template_inference_dir / "backends.toml"
    target_backends_path = target_inference_dir / "backends.toml"
    target_backends_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template_backends_path, target_backends_path)

    # Copy backends/*.toml
    template_backends_dir = template_inference_dir / "backends"
    target_backends_dir = target_inference_dir / "backends"
    target_backends_dir.mkdir(parents=True, exist_ok=True)
    for backend_file in os.listdir(template_backends_dir):
        if backend_file.endswith(".toml"):
            shutil.copy2(template_backends_dir / backend_file, target_backends_dir / backend_file)

    # Copy deck/*.toml
    template_deck_dir = template_inference_dir / "deck"
    target_deck_dir = target_inference_dir / "deck"
    target_deck_dir.mkdir(parents=True, exist_ok=True)
    for deck_file in os.listdir(template_deck_dir):
        if deck_file.endswith(".toml"):
            shutil.copy2(template_deck_dir / deck_file, target_deck_dir / deck_file)

    write_manifest(target_deck_dir, compute_kit_manifest())

    # Copy routing_profiles.toml
    template_routing_path = template_inference_dir / "routing_profiles.toml"
    if template_routing_path.exists():
        shutil.copy2(template_routing_path, target_inference_dir / "routing_profiles.toml")


def _copy_telemetry_template(target_dir: Path, for_project: bool) -> None:
    """Copy the appropriate telemetry template to the target directory.

    The global template (`telemetry.toml`) carries active defaults. The project
    template (`telemetry.project.toml`) is fully commented out so a project's
    `.pipelex/telemetry.toml` doesn't shadow the user's global telemetry
    settings during layered loading.

    Args:
        target_dir: Target config directory (e.g. .pipelex/).
        for_project: True when targeting a project's `.pipelex/`; False when
            targeting the global `~/.pipelex/`.
    """
    template_name = TELEMETRY_PROJECT_TEMPLATE_FILE_NAME if for_project else TELEMETRY_CONFIG_FILE_NAME
    template_path = Path(str(get_kit_configs_dir())) / template_name
    target_path = target_dir / TELEMETRY_CONFIG_FILE_NAME
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template_path, target_path)


def _configure_backends(
    config: dict[str, Any],
    backends_toml_path: str,
    template_backends_path: str,
) -> list[str]:
    """Configure backends in backends.toml based on config input.

    Args:
        config: Parsed config dict with optional 'backends' key.
        backends_toml_path: Path to the user's backends.toml.
        template_backends_path: Path to the template backends.toml.

    Returns:
        List of enabled backend keys.
    """
    if not path_exists(backends_toml_path):
        agent_error("backends.toml not found after config initialization", "InitConfigError")

    requested_backends: list[str] | None = config.get("backends")

    if requested_backends is None:
        # Keep template defaults — return what's currently enabled
        return get_selected_backend_keys(backends_toml_path)

    # Validate requested backend keys
    backend_options = get_backend_options_from_toml(template_backends_path, backends_toml_path)
    available_keys = [key for key, _ in backend_options]

    for backend_key in requested_backends:
        if backend_key not in available_keys:
            agent_error(
                f"Unknown backend: {backend_key}. Available: {', '.join(available_keys)}",
                "ArgumentError",
            )

    # Build selected indices from requested backend keys
    key_to_index = {key: idx for idx, (key, _) in enumerate(backend_options)}
    selected_indices = [key_to_index[key] for key in requested_backends]

    # Update backends.toml
    toml_doc = load_toml_with_tomlkit(backends_toml_path)
    update_backends_in_toml(toml_doc, selected_indices, backend_options)
    save_toml_to_path(toml_doc, backends_toml_path)

    # Handle pipelex_gateway terms acceptance (only when explicitly provided)
    if PipelexBackend.GATEWAY in requested_backends:
        accept_terms = config.get("accept_gateway_terms")
        if accept_terms is not None:
            config_manager.global_config_dir.mkdir(parents=True, exist_ok=True)
            update_service_terms_acceptance(accepted=accept_terms, config_dir=config_manager.global_config_dir)

    return requested_backends


def _configure_routing(selected_backend_keys: list[str], config: dict[str, Any], target_dir: Path) -> str:
    """Configure routing profile based on selected backends and config.

    Args:
        selected_backend_keys: List of enabled backend keys.
        config: Parsed config dict with optional 'primary_backend' key.
        target_dir: Target config directory.

    Returns:
        Name of the active routing profile.
    """
    routing_profiles_toml_path = str(target_dir / "inference" / "routing_profiles.toml")

    if not path_exists(routing_profiles_toml_path):
        agent_error("routing_profiles.toml not found after config initialization", "InitConfigError")

    toml_doc = load_toml_with_tomlkit(routing_profiles_toml_path)

    # Case 1: pipelex_gateway is enabled → use all_pipelex_gateway
    if PipelexBackend.GATEWAY in selected_backend_keys:
        toml_doc["active"] = PipelexRoutingProfile.ALL_PIPELEX_GATEWAY
        save_toml_to_path(toml_doc, routing_profiles_toml_path)
        return PipelexRoutingProfile.ALL_PIPELEX_GATEWAY

    # Case 2: Only one backend → use all_{backend_key}
    if len(selected_backend_keys) == 1:
        backend_key = selected_backend_keys[0]
        profile_name = f"all_{backend_key}"

        # Create profile if it doesn't exist
        profiles: dict[str, Any] = toml_doc.get("profiles") or {}  # type: ignore[assignment]
        if profile_name not in profiles:
            if "profiles" not in toml_doc:
                toml_doc["profiles"] = {}
            profile_data = {
                "description": f"Use {backend_key} backend for all its supported models",
                "default": backend_key,
            }
            toml_doc["profiles"][profile_name] = profile_data  # type: ignore[index]

        toml_doc["active"] = profile_name
        save_toml_to_path(toml_doc, routing_profiles_toml_path)
        return profile_name

    # Case 3: Multiple backends (no pipelex_gateway) → need primary_backend
    primary_backend: str | None = config.get("primary_backend")

    if primary_backend is None:
        agent_error(
            f"primary_backend is required when multiple backends are selected ({', '.join(selected_backend_keys)}) "
            "and pipelex_gateway is not among them",
            "ArgumentError",
        )

    if primary_backend not in selected_backend_keys:
        agent_error(
            f"primary_backend '{primary_backend}' is not in the selected backends: {', '.join(selected_backend_keys)}",
            "ArgumentError",
        )

    # Build custom_routing profile
    remaining_backends = [backend for backend in selected_backend_keys if backend != primary_backend]
    fallback_order = [primary_backend, *remaining_backends]

    if "profiles" not in toml_doc:
        toml_doc["profiles"] = {}

    new_profiles = table()

    custom_routing_profile = table()
    custom_routing_profile["description"] = "Custom routing"
    custom_routing_profile["default"] = primary_backend
    custom_routing_profile["fallback_order"] = fallback_order
    custom_routing_profile["routes"] = table()
    new_profiles["custom_routing"] = custom_routing_profile

    # Preserve existing profiles after custom_routing
    existing_profiles: dict[str, Any] = toml_doc.get("profiles") or {}  # type: ignore[assignment]
    for profile_key, profile_value in existing_profiles.items():  # type: ignore[union-attr]
        if profile_key != "custom_routing":
            new_profiles[profile_key] = profile_value

    toml_doc["profiles"] = new_profiles  # type: ignore[assignment]
    toml_doc["active"] = "custom_routing"

    save_toml_to_path(toml_doc, routing_profiles_toml_path)
    return "custom_routing"


def agent_init_cmd(
    config: Annotated[
        str | None,
        typer.Option(
            "--config",
            "-c",
            help=(
                "Inline JSON string or path to a JSON file. "
                'Schema: {"backends": list[str], "primary_backend": str, "accept_gateway_terms": bool}. '
                "All fields are optional. "
                "backends: backend keys to enable (e.g. 'openai', 'anthropic', 'pipelex_gateway'). Omit to keep template defaults. "
                "primary_backend: required only when 2+ backends are selected and pipelex_gateway is not among them. "
                "accept_gateway_terms: true/false, required when pipelex_gateway is in backends."
            ),
        ),
    ] = None,
    global_: Annotated[
        bool,
        typer.Option(
            "--global",
            "-g",
            help="Force global ~/.pipelex/ directory.",
        ),
    ] = False,
    output_format: Annotated[
        CliOutputFormat,
        typer.Option("--format", help="Output format: markdown (default) or json (structured)"),
    ] = CliOutputFormat.MARKDOWN,
) -> None:
    """Initialize Pipelex configuration (non-interactive).

    Sets up config files, inference backends, routing profile, and telemetry.
    Credentials are NOT configured — use 'pipelex-agent doctor' to check credential
    health, and 'pipelex init credentials' if needed.

    Target directory: project .pipelex/ at detected project root by default.
    Use --global/-g to force global ~/.pipelex/.

    Config JSON schema::

        {
            "backends": ["pipelex_gateway", "openai"],
            "accept_gateway_terms": true,
            "primary_backend": "openai"
        }

    - backends: list of backend keys to enable. Omit to keep all template defaults.
    - accept_gateway_terms: sets gateway terms acceptance (true/false).
    - primary_backend: required when 2+ backends are selected and pipelex_gateway
      is not among them. Auto-derived when only 1 backend or pipelex_gateway is present.

    Telemetry: global init seeds an active `telemetry.toml` template with all destinations
    off; project init drops in a commented-out template that inherits the user's global
    telemetry settings via layered loading. Edit `telemetry.toml` to enable destinations.
    """
    set_agent_cli_output_format(output_format)

    try:
        # Parse config
        parsed_config = _parse_config_arg(config)

        # Resolve target directory
        target_dir = _resolve_target_dir(global_)

        # Step 1: Copy config files (skips inference/ directory)
        config_files_copied = init_config(reset=True, target_dir=str(target_dir))

        # Step 1.5: Copy inference templates (init_config skips inference/)
        _copy_inference_templates(target_dir)

        # Step 1.6: Copy telemetry template. Global init seeds active defaults;
        # project init drops in a commented-out template so it doesn't shadow
        # the user's global telemetry settings during layered loading.
        _copy_telemetry_template(target_dir, for_project=not global_)

        # Step 2: Configure backends
        template_backends_path = str(get_kit_configs_dir() / "inference" / "backends.toml")
        backends_toml_path = str(target_dir / "inference" / "backends.toml")
        backends_enabled = _configure_backends(parsed_config, backends_toml_path, template_backends_path)

        # Step 3: Configure routing
        routing_profile = _configure_routing(backends_enabled, parsed_config, target_dir)

        # Step 4: Mark inference setup as completed
        update_inference_setup_completed(completed=True, config_dir=config_manager.global_config_dir)

        # Output result
        agent_success_formatted(
            {
                "success": True,
                "target_dir": str(target_dir),
                "config_files_copied": config_files_copied,
                "backends_enabled": backends_enabled,
                "routing_profile": routing_profile,
                "inference_setup_completed": True,
            },
            _format_init_markdown,
        )

    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
        agent_error(f"Initialization failed: {exc}", type(exc).__name__, cause=exc)
