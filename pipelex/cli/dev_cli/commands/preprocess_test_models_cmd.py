"""Command to preprocess test models and generate fixture files."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from rich.panel import Panel
from rich.table import Table

from pipelex.hub import get_console
from pipelex.system.configuration.configs import ConfigPaths
from pipelex.system.pipelex_service.exceptions import RemoteConfigFetchError, RemoteConfigValidationError
from pipelex.system.pipelex_service.remote_config_fetcher import RemoteConfigFetcher
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from rich.console import Console


# Default paths for generated files
MODEL_AVAILABILITY_JSON_PATH = Path(ConfigPaths.DEFAULT_CONFIG_DIR_PATH) / "inference" / "_model_availability.json"
GENERATED_FIXTURES_PATH = Path("tests/integration/pipelex/fixtures/_generated_model_sets.py")
TEST_PROFILES_PATH = Path(ConfigPaths.DEFAULT_CONFIG_DIR_PATH) / "test_profiles.toml"

# Model types we care about
MODEL_TYPES = ["llm", "img_gen", "text_extractor"]

# Default model type from backend config
DEFAULT_MODEL_TYPE = "llm"


def _extract_models_from_backend_toml(backend_path: Path) -> dict[str, list[str]]:
    """Extract model handles from a backend TOML file, grouped by model type.

    Args:
        backend_path: Path to the backend TOML file.

    Returns:
        Dictionary mapping model_type to list of model handles.
    """
    try:
        config = load_toml_from_path(str(backend_path))
    except Exception:
        return {}

    # Get defaults
    defaults = config.get("defaults", {})
    default_model_type = defaults.get("model_type", DEFAULT_MODEL_TYPE)

    models_by_type: dict[str, list[str]] = {
        "llm": [],
        "img_gen": [],
        "text_extractor": [],
    }

    for key, value in config.items():
        # Skip defaults and non-dict entries
        if key == "defaults" or not isinstance(value, dict):
            continue

        # Skip rules sub-sections
        if ".rules" in key:
            continue

        # Determine model type (cast for type safety)
        value_dict = cast("dict[str, Any]", value)
        model_type_raw = value_dict.get("model_type", default_model_type)
        model_type = str(model_type_raw) if model_type_raw else default_model_type

        # Add to appropriate list
        if model_type in models_by_type:
            models_by_type[model_type].append(key)

    # Sort model lists
    for model_list in models_by_type.values():
        model_list.sort()

    return models_by_type


def _fetch_gateway_models() -> dict[str, list[str]]:
    """Fetch model handles from Pipelex Gateway remote config, grouped by model type.

    Returns:
        Dictionary mapping model_type to list of model handles.
    """
    try:
        remote_config = RemoteConfigFetcher.fetch_remote_config()
        model_specs = dict(remote_config.backend_model_specs)
    except (RemoteConfigFetchError, RemoteConfigValidationError):
        return {"llm": [], "img_gen": [], "text_extractor": []}

    # Get defaults
    defaults = model_specs.get("defaults", {})
    default_model_type: str = DEFAULT_MODEL_TYPE
    if isinstance(defaults, dict):
        defaults_dict = cast("dict[str, Any]", defaults)
        default_type_raw = defaults_dict.get("model_type")
        if default_type_raw:
            default_model_type = str(default_type_raw)

    models_by_type: dict[str, list[str]] = {
        "llm": [],
        "img_gen": [],
        "text_extractor": [],
    }

    for key, value in model_specs.items():
        # Skip defaults and non-dict entries
        if key == "defaults" or not isinstance(value, dict):
            continue

        # Skip rules sub-sections
        if ".rules" in key:
            continue

        # Determine model type (cast for type safety)
        value_dict = cast("dict[str, Any]", value)
        model_type_raw = value_dict.get("model_type", default_model_type)
        model_type = str(model_type_raw) if model_type_raw else default_model_type

        # Add to appropriate list
        if model_type in models_by_type:
            models_by_type[model_type].append(key)

    # Sort model lists
    for model_list in models_by_type.values():
        model_list.sort()

    return models_by_type


def _collect_all_model_availability() -> dict[str, Any]:
    """Collect model availability from all backends.

    Returns:
        Dictionary with structure:
        {
            "generated_at": "ISO timestamp",
            "llm": {"backend_name": ["model1", "model2", ...], ...},
            "img_gen": {"backend_name": ["model1", "model2", ...], ...},
            "text_extractor": {"backend_name": ["model1", "model2", ...], ...}
        }
    """
    result: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "llm": {},
        "img_gen": {},
        "text_extractor": {},
    }

    backends_dir = Path(ConfigPaths.BACKENDS_DIR_PATH)

    # Process each backend TOML file
    for backend_file in sorted(backends_dir.glob("*.toml")):
        backend_name = backend_file.stem

        # Skip pipelex_gateway (handled separately) and pipelex_inference (alias)
        if backend_name in {"pipelex_gateway", "pipelex_inference"}:
            continue

        models_by_type = _extract_models_from_backend_toml(backend_file)

        for model_type in MODEL_TYPES:
            if models_by_type.get(model_type):
                result[model_type][backend_name] = models_by_type[model_type]

    # Add Pipelex Gateway models
    gateway_models = _fetch_gateway_models()
    for model_type in MODEL_TYPES:
        if gateway_models.get(model_type):
            result[model_type]["pipelex_gateway"] = gateway_models[model_type]

    return result


def _load_test_profile(profile_name: str) -> dict[str, Any]:
    """Load a test profile from the test_profiles.toml file.

    Args:
        profile_name: Name of the profile to load.

    Returns:
        Profile configuration dictionary.
    """
    if not TEST_PROFILES_PATH.exists():
        # Return default "full" profile behavior
        return {"include_all": True}

    try:
        profiles_config = load_toml_from_path(str(TEST_PROFILES_PATH))
        profiles = profiles_config.get("profiles", {})
        if profile_name in profiles:
            return dict(profiles[profile_name])
        # Default to full if profile not found
        return {"include_all": True}
    except Exception:
        return {"include_all": True}


def _filter_models_by_profile(
    availability: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, list[tuple[str, str]]]:
    """Filter model availability by test profile, returning (model, backend) pairs.

    Args:
        availability: Full model availability data.
        profile: Test profile configuration.

    Returns:
        Dictionary mapping model_type to list of (model_handle, backend_name) tuples.
    """
    result: dict[str, list[tuple[str, str]]] = {
        "llm": [],
        "img_gen": [],
        "text_extractor": [],
    }

    # If include_all is set, return all valid pairs
    if profile.get("include_all"):
        for model_type in MODEL_TYPES:
            for backend_name, models in availability.get(model_type, {}).items():
                for model in models:
                    result[model_type].append((model, backend_name))
        return result

    # Get profile filters
    allowed_backends = set(profile.get("backends", []))
    allowed_llm_models = set(profile.get("llm_models", []))
    allowed_img_gen_models = set(profile.get("img_gen_models", []))
    allowed_extract_models = set(profile.get("extract_models", []))

    model_filters = {
        "llm": allowed_llm_models,
        "img_gen": allowed_img_gen_models,
        "text_extractor": allowed_extract_models,
    }

    for model_type in MODEL_TYPES:
        allowed_models = model_filters[model_type]
        for backend_name, models in availability.get(model_type, {}).items():
            # Skip backends not in the profile (if backends filter is set)
            if allowed_backends and backend_name not in allowed_backends:
                continue

            for model in models:
                # Skip models not in the profile (if models filter is set)
                if allowed_models and model not in allowed_models:
                    continue

                result[model_type].append((model, backend_name))

    return result


def _generate_fixtures_python(
    model_backend_pairs: dict[str, list[tuple[str, str]]],
    profile_name: str,
) -> str:
    """Generate Python module content with pre-computed model/backend pairs.

    Args:
        model_backend_pairs: Dictionary mapping model_type to (model, backend) tuples.
        profile_name: Name of the test profile used.

    Returns:
        Python module source code.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        '"""AUTO-GENERATED - DO NOT EDIT.',
        "",
        "Pre-computed model/backend pairs for test fixtures.",
        f"Generated by: pipelex-dev preprocess-test-models --profile {profile_name}",
        f"Generated at: {timestamp}",
        '"""',
        "",
        "# Valid (model_handle, backend_name) pairs",
        "",
    ]

    # LLM pairs
    llm_pairs = model_backend_pairs.get("llm", [])
    lines.append("LLM_MODEL_BACKEND_PAIRS: list[tuple[str, str]] = [")
    for model, backend in sorted(llm_pairs):
        lines.append(f'    ("{model}", "{backend}"),')
    lines.append("]")
    lines.append("")

    # Image generation pairs
    img_gen_pairs = model_backend_pairs.get("img_gen", [])
    lines.append("IMG_GEN_MODEL_BACKEND_PAIRS: list[tuple[str, str]] = [")
    for model, backend in sorted(img_gen_pairs):
        lines.append(f'    ("{model}", "{backend}"),')
    lines.append("]")
    lines.append("")

    # Extract pairs
    extract_pairs = model_backend_pairs.get("text_extractor", [])
    lines.append("EXTRACT_MODEL_BACKEND_PAIRS: list[tuple[str, str]] = [")
    for model, backend in sorted(extract_pairs):
        lines.append(f'    ("{model}", "{backend}"),')
    lines.append("]")
    lines.append("")

    return "\n".join(lines)


def _display_summary(
    availability: dict[str, Any],
    model_backend_pairs: dict[str, list[tuple[str, str]]],
    profile_name: str,
    console: Console,
) -> None:
    """Display a summary of the preprocessing results.

    Args:
        availability: Full model availability data.
        model_backend_pairs: Filtered model/backend pairs.
        profile_name: Name of the test profile used.
        console: Rich console for output.
    """
    # Count totals
    total_backends: set[str] = set()
    total_models = 0
    for model_type in MODEL_TYPES:
        model_type_data = availability.get(model_type, {})
        if isinstance(model_type_data, dict):
            model_type_dict = cast("dict[str, list[str]]", model_type_data)
            total_backends.update(model_type_dict.keys())
            for models in model_type_dict.values():
                total_models += len(models)

    filtered_models = sum(len(pairs) for pairs in model_backend_pairs.values())

    # Create summary table
    table = Table(title="Model Availability Summary")
    table.add_column("Category", style="cyan")
    table.add_column("Total Available", justify="right")
    table.add_column(f"In '{profile_name}' Profile", justify="right", style="green")

    llm_total = sum(len(models) for models in availability.get("llm", {}).values())
    img_gen_total = sum(len(models) for models in availability.get("img_gen", {}).values())
    extract_total = sum(len(models) for models in availability.get("text_extractor", {}).values())

    table.add_row("LLM Models", str(llm_total), str(len(model_backend_pairs.get("llm", []))))
    table.add_row("Image Gen Models", str(img_gen_total), str(len(model_backend_pairs.get("img_gen", []))))
    table.add_row("Extract Models", str(extract_total), str(len(model_backend_pairs.get("text_extractor", []))))
    table.add_row("", "", "")
    table.add_row("Total Backends", str(len(total_backends)), "-")
    table.add_row("Total Model/Backend Pairs", str(total_models), str(filtered_models))

    console.print(table)


def preprocess_test_models_cmd(
    profile: str = "dev",
    generate_fixtures: bool = False,
    output_json: bool = False,
    quiet: bool = False,
) -> None:
    """Preprocess test models from backend TOMLs and generate fixture files.

    This command reads all backend TOML configurations and the Pipelex Gateway
    remote config to build a complete mapping of available models. It can optionally
    generate a Python fixture file with pre-computed (model, backend) pairs.

    Args:
        profile: Test profile to use (ci, dev, coverage, full).
        generate_fixtures: If True, generate the Python fixtures file.
        output_json: If True, output the full availability JSON.
        quiet: If True, output only minimal status lines.
    """
    console = get_console()

    if not quiet:
        console.print()
        console.print("[bold]Preprocessing test models...[/bold]")
        console.print()

    # Collect model availability
    try:
        availability = _collect_all_model_availability()
    except Exception as exc:
        if quiet:
            console.print(f"[red]✗ Preprocess failed:[/red] {exc}")
        else:
            error_panel = Panel(
                f"[red]✗[/red] Failed to collect model availability\n\n[dim]{exc}[/dim]",
                title="[bold red]Preprocessing Failed[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
        sys.exit(1)

    # Output JSON if requested
    if output_json:
        MODEL_AVAILABILITY_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with MODEL_AVAILABILITY_JSON_PATH.open("w", encoding="utf-8") as json_file:
            json.dump(availability, json_file, indent=2)

        if not quiet:
            console.print(f"[green]✓[/green] Wrote model availability to {MODEL_AVAILABILITY_JSON_PATH}")

    # Load test profile and filter
    test_profile = _load_test_profile(profile)
    model_backend_pairs = _filter_models_by_profile(availability, test_profile)

    # Generate fixtures if requested
    if generate_fixtures:
        fixtures_content = _generate_fixtures_python(model_backend_pairs, profile)
        GENERATED_FIXTURES_PATH.parent.mkdir(parents=True, exist_ok=True)
        GENERATED_FIXTURES_PATH.write_text(fixtures_content, encoding="utf-8")

        if not quiet:
            console.print(f"[green]✓[/green] Generated fixtures at {GENERATED_FIXTURES_PATH}")

    # Display summary
    if not quiet:
        console.print()
        _display_summary(availability, model_backend_pairs, profile, console)
        console.print()

        # Show profile info
        if test_profile.get("include_all"):
            console.print(f"[dim]Profile '{profile}': Including all available models[/dim]")
        else:
            backends = test_profile.get("backends", [])
            console.print(f"[dim]Profile '{profile}': {len(backends)} backends configured[/dim]")

        console.print()

    # Final status
    total_pairs = sum(len(pairs) for pairs in model_backend_pairs.values())
    if quiet:
        status_parts = [f"[green]✓ Preprocessed:[/green] {total_pairs} model/backend pairs"]
        if generate_fixtures:
            status_parts.append(f"(fixtures: {GENERATED_FIXTURES_PATH})")
        console.print(" ".join(status_parts))
    else:
        success_panel = Panel(
            f"[green]✓[/green] Successfully preprocessed {total_pairs} model/backend pairs\n\n[dim]Profile: {profile}[/dim]",
            title="[bold green]Preprocessing Complete[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
        console.print(success_panel)
