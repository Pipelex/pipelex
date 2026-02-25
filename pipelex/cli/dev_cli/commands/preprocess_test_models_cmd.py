"""Command to preprocess test models and generate fixture files."""

from __future__ import annotations

import fnmatch
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from pipelex.hub import get_console
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.configs import ConfigPaths
from pipelex.system.pipelex_service.exceptions import RemoteConfigFetchError, RemoteConfigValidationError
from pipelex.system.pipelex_service.remote_config_fetcher import RemoteConfigFetcher
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import TomlError, load_toml_from_path

if TYPE_CHECKING:
    from rich.console import Console


# Default paths for generated files
MODEL_AVAILABILITY_JSON_PATH = Path(ConfigPaths.DEV_CONFIG_DIR_PATH) / "model_availability.json"
GENERATED_FIXTURES_PATH = Path("tests/integration/pipelex/fixtures/_generated_model_sets.py")
TEST_PROFILES_PATH = Path(ConfigPaths.DEV_CONFIG_DIR_PATH) / "test_profiles.toml"
TEST_PROFILES_OVERRIDE_PATH = Path(ConfigPaths.DEV_CONFIG_DIR_PATH) / "test_profiles_override.toml"

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
    except (TomlError, OSError):
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

    backends_dir = Path(config_manager.backends_dir_path)

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


def _load_merged_profiles_config() -> dict[str, Any]:
    """Load test profiles config, merging override file if present.

    The override file (.pipelex/test_profiles_override.toml) allows developers
    to customize profiles locally without modifying the tracked base file.

    Returns:
        Merged configuration dictionary.

    Raises:
        TOMLDecodeError: If either config file has invalid TOML syntax.
    """
    if not TEST_PROFILES_PATH.exists():
        return {}

    config = load_toml_from_path(str(TEST_PROFILES_PATH))

    # Merge override file if it exists
    if TEST_PROFILES_OVERRIDE_PATH.exists():
        override_config = load_toml_from_path(str(TEST_PROFILES_OVERRIDE_PATH))
        deep_update(config, override_config)

    return dict(config)


def _load_test_profile(profile_name: str) -> dict[str, Any]:
    """Load a test profile from the test_profiles.toml file.

    Args:
        profile_name: Name of the profile to load.

    Returns:
        Profile configuration dictionary.

    Raises:
        ValueError: If the profile is not found in the configuration.
    """
    profiles_config = _load_merged_profiles_config()
    if not profiles_config:
        return {"include_all": True}

    profiles = profiles_config.get("profiles", {})
    if profile_name in profiles:
        return dict(profiles[profile_name])
    else:
        available_profiles = sorted(profiles.keys())
        msg = f"Profile '{profile_name}' not found. Available profiles: {', '.join(available_profiles)}"
        raise ValueError(msg)


def _process_collections_from_toml(
    collections_raw: Any,  # pyright: ignore[reportExplicitAny]
    collections: dict[str, dict[str, list[str]]],
) -> None:
    """Process raw TOML collections data into typed collections dict.

    This helper exists to isolate untyped TOML boundary handling.
    """
    for collection_type in collections_raw:  # pyright: ignore[reportUnknownVariableType]
        collection_data = collections_raw[collection_type]  # pyright: ignore[reportUnknownVariableType]
        if isinstance(collection_data, dict):
            type_key = str(collection_type)
            collections[type_key] = {}
            for coll_name in collection_data:  # pyright: ignore[reportUnknownVariableType]
                model_list = collection_data[coll_name]  # pyright: ignore[reportUnknownVariableType]
                if isinstance(model_list, list):
                    name_key = str(coll_name)  # pyright: ignore[reportUnknownArgumentType]
                    collections[type_key][name_key] = [str(mdl) for mdl in model_list]  # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType]


def _load_collections() -> dict[str, dict[str, list[str]]]:
    """Load model collections from the test_profiles.toml file.

    Returns:
        Dictionary mapping collection type (llm, img_gen, extract) to
        collection name to list of models.
    """
    profiles_config = _load_merged_profiles_config()
    if not profiles_config:
        return {}

    collections_raw = profiles_config.get("collections", {})

    # Build collections dict with proper typing
    collections: dict[str, dict[str, list[str]]] = {}
    if not isinstance(collections_raw, dict):
        return {}

    # Process TOML collections (untyped data at boundary)
    _process_collections_from_toml(collections_raw, collections)

    return collections


def _resolve_model_list(
    raw_list: list[str],
    collections: dict[str, list[str]],
    backend_models: dict[str, list[str]],
    all_known_models: list[str],
) -> list[str]:
    """Expand references, wildcards, and glob patterns in a model list.

    Args:
        raw_list: List of model specifiers (may include @references, backend:*, globs).
        collections: Collections for this model type (name -> list of models).
        backend_models: Backend name -> list of models from that backend.
        all_known_models: All known models of this type (for glob matching).

    Returns:
        Resolved list of model names (deduplicated, preserving order).

    Supported syntax:
        - `@collection_name`: Include all models from named collection (static)
        - `backend:*`: All models available from that backend (dynamic)
        - `gpt-*`, `claude-*`: Glob pattern matching model names (dynamic)
        - `*`: All available models (same as include_all=true)
        - `!pattern`: Exclude models matching pattern (negation)
        - `"model-name"`: Specific model (existing behavior)
    """
    resolved: list[str] = []
    exclusions: list[str] = []

    for item in raw_list:
        # Handle negation (exclusions)
        if item.startswith("!"):
            pattern = item[1:]
            # Support glob patterns in exclusions
            if "*" in pattern or "?" in pattern:
                exclusions.extend(fnmatch.filter(all_known_models, pattern))
            else:
                exclusions.append(pattern)
            continue

        if item == "*":
            # All models from all backends
            resolved.extend(all_known_models)
        elif item.startswith("@"):
            # Collection reference: @anthropic -> collections.llm.anthropic
            collection_name = item[1:]
            if collection_name in collections:
                resolved.extend(collections[collection_name])
        elif ":" in item and item.endswith("*"):
            # Backend wildcard: openai:* -> all models from openai backend
            backend_name = item.split(":")[0]
            if backend_name in backend_models:
                resolved.extend(backend_models[backend_name])
        elif "*" in item or "?" in item:
            # Glob pattern: gpt-*, claude-4.5-*, mistral-?-*
            matched = fnmatch.filter(all_known_models, item)
            resolved.extend(matched)
        else:
            # Direct model name
            resolved.append(item)

    # Apply exclusions
    resolved = [model for model in resolved if model not in exclusions]

    # Dedupe preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for model in resolved:
        if model not in seen:
            seen.add(model)
            deduped.append(model)

    return deduped


def _filter_models_by_profile(
    availability: dict[str, Any],
    profile: dict[str, Any],
    collections: dict[str, dict[str, list[str]]],
) -> dict[str, list[tuple[str, str]]]:
    """Filter model availability by test profile, returning (model, backend) pairs.

    Supports advanced model specifiers:
        - `@collection_name`: Include all models from named collection
        - `backend:*`: All models available from that backend
        - `gpt-*`, `claude-*`: Glob patterns
        - `*`: All available models
        - `!pattern`: Exclude models matching pattern

    Args:
        availability: Full model availability data.
        profile: Test profile configuration.
        collections: Model collections from test_profiles.toml.

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

    # Get profile filters - resolve @collection references for backends
    # None means "include all backends", empty set means "include no backends"
    allowed_backends: set[str] | None = None
    if "backends" in profile:
        raw_backends = profile.get("backends", [])
        allowed_backends = set()
        backends_collections = collections.get("backends", {})
        for item in raw_backends:
            if item.startswith("@"):
                collection_name = item[1:]
                if collection_name in backends_collections:
                    allowed_backends.update(backends_collections[collection_name])
            else:
                allowed_backends.add(item)

    # Build backend -> models mappings and all_known_models for each model type
    model_type_data: dict[str, dict[str, list[str]]] = {}
    all_models_by_type: dict[str, list[str]] = {}

    for model_type in MODEL_TYPES:
        model_type_data[model_type] = {}
        all_models: list[str] = []
        for backend_name, models in availability.get(model_type, {}).items():
            model_type_data[model_type][backend_name] = models
            all_models.extend(models)
        # Dedupe while preserving order
        seen: set[str] = set()
        deduped_models: list[str] = []
        for mdl in all_models:
            if mdl not in seen:
                seen.add(mdl)
                deduped_models.append(mdl)
        all_models_by_type[model_type] = deduped_models

    # Profile key to model type mapping
    profile_keys = {
        "llm_models": "llm",
        "img_gen_models": "img_gen",
        "extract_models": "text_extractor",
    }

    # Model type to collection type mapping (internal name -> TOML section name)
    collection_type_map = {
        "llm": "llm",
        "img_gen": "img_gen",
        "text_extractor": "extract",
    }

    # Resolve model lists from profile using advanced specifiers
    # None means "include all", empty set means "include none"
    resolved_models: dict[str, set[str] | None] = {}
    for profile_key, model_type in profile_keys.items():
        if profile_key not in profile:
            # Key not present - include all models from allowed backends
            resolved_models[model_type] = None
        else:
            raw_list = profile.get(profile_key, [])
            if raw_list:
                # Get collections for this model type (using TOML section name)
                collection_type = collection_type_map.get(model_type, model_type)
                type_collections = collections.get(collection_type, {})
                # Resolve the model list
                resolved = _resolve_model_list(
                    raw_list=list(raw_list),
                    collections=type_collections,
                    backend_models=model_type_data[model_type],
                    all_known_models=all_models_by_type[model_type],
                )
                resolved_models[model_type] = set(resolved)
            else:
                # Empty list - include no models
                resolved_models[model_type] = set()

    for model_type in MODEL_TYPES:
        allowed_models = resolved_models[model_type]
        for backend_name, models in availability.get(model_type, {}).items():
            # Skip backends not in the profile (if backends filter is set)
            # None means "include all", empty set means "include none"
            if allowed_backends is not None and backend_name not in allowed_backends:
                continue

            for model in models:
                # None means include all, empty set means include none, set with items means filter
                if allowed_models is not None and model not in allowed_models:
                    continue

                result[model_type].append((model, backend_name))

    return result


def _generate_fixtures_python(
    combo_pairs: dict[str, list[tuple[str, str]]],
    profile_name: str,
) -> str:
    """Generate Python module content with pre-computed model/backend pairs.

    Args:
        combo_pairs: Dictionary mapping model_type to (model, backend) tuples.
        profile_name: Name of the test profile used.

    Returns:
        Python module source code.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        '"""AUTO-GENERATED - DO NOT EDIT.',
        "",
        "Pre-computed model/backend combos for test fixtures.",
        f"Generated by: pipelex-dev preprocess-test-models --profile {profile_name}",
        f"Generated at: {timestamp}",
        '"""',
        "",
        "from tests.integration.pipelex.fixtures.model_combo import ModelCombo",
        "",
    ]

    # LLM combos
    llm_pairs = combo_pairs.get("llm", [])
    lines.append("LLM_COMBOS: list[ModelCombo] = [")
    for model, backend in sorted(llm_pairs):
        lines.append(f"    ModelCombo({model!r}, {backend!r}),")
    lines.append("]")
    lines.append("")

    # Image generation combos
    img_gen_pairs = combo_pairs.get("img_gen", [])
    lines.append("IMG_GEN_COMBOS: list[ModelCombo] = [")
    for model, backend in sorted(img_gen_pairs):
        lines.append(f"    ModelCombo({model!r}, {backend!r}),")
    lines.append("]")
    lines.append("")

    # Extract combos
    extract_pairs = combo_pairs.get("text_extractor", [])
    lines.append("EXTRACT_COMBOS: list[ModelCombo] = [")
    for model, backend in sorted(extract_pairs):
        lines.append(f"    ModelCombo({model!r}, {backend!r}),")
    lines.append("]")
    lines.append("")

    return "\n".join(lines)


def _display_summary(
    availability: dict[str, Any],
    combo_pairs: dict[str, list[tuple[str, str]]],
    profile_name: str,
    console: Console,
) -> None:
    """Display a summary of the preprocessing results.

    Args:
        availability: Full model availability data.
        combo_pairs: Filtered model/backend pairs.
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

    filtered_models = sum(len(pairs) for pairs in combo_pairs.values())

    # Create summary table
    table = Table(title="Model Availability Summary")
    table.add_column("Category", style="cyan")
    table.add_column("Total Available", justify="right")
    table.add_column(f"In '{profile_name}' Profile", justify="right", style="green")

    llm_total = sum(len(models) for models in availability.get("llm", {}).values())
    img_gen_total = sum(len(models) for models in availability.get("img_gen", {}).values())
    extract_total = sum(len(models) for models in availability.get("text_extractor", {}).values())

    table.add_row("LLM Models", str(llm_total), str(len(combo_pairs.get("llm", []))))
    table.add_row("Image Gen Models", str(img_gen_total), str(len(combo_pairs.get("img_gen", []))))
    table.add_row("Extract Models", str(extract_total), str(len(combo_pairs.get("text_extractor", []))))
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
    backends_dir = Path(config_manager.backends_dir_path)
    if not backends_dir.exists():
        if quiet:
            console.print(f"[red]✗ Preprocessing failed:[/red] Backends directory not found: {backends_dir}")
        else:
            error_panel = Panel(
                f"[red]✗[/red] Backends directory not found\n\n"
                f"[dim]Expected directory: {backends_dir}[/dim]\n\n"
                f"The backends directory contains TOML configuration files\n"
                f"for each inference backend (OpenAI, Anthropic, etc.).",
                title="[bold red]Configuration Missing[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()
            console.print("[bold yellow]Recommended Actions:[/bold yellow]")
            console.print("  • Run: [cyan]pipelex init config[/cyan] to create the configuration")
            console.print("  • Or copy the default configs from [cyan]pipelex/kit/configs[/cyan]")
            console.print()
        sys.exit(1)

    try:
        availability = _collect_all_model_availability()
    except OSError as exc:
        # File system errors (permissions, disk issues, etc.)
        if quiet:
            console.print(f"[red]✗ Preprocessing failed:[/red] File system error - {escape(str(exc))}")
        else:
            error_panel = Panel(
                f"[red]✗[/red] File system error while reading backend configurations\n\n[dim]{escape(str(exc))}[/dim]",
                title="[bold red]File System Error[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()
            console.print("[bold yellow]Recommended Actions:[/bold yellow]")
            console.print(f"  • Check file permissions in: [cyan]{backends_dir}[/cyan]")
            console.print("  • Verify disk space and filesystem health")
            console.print()
        sys.exit(1)
    except Exception as exc:
        # Catch-all for unexpected errors
        if quiet:
            console.print(f"[red]✗ Preprocessing failed:[/red] {escape(str(exc))}")
        else:
            error_panel = Panel(
                f"[red]✗[/red] Unexpected error while collecting model availability\n\n[dim]{type(exc).__name__}: {escape(str(exc))}[/dim]",
                title="[bold red]Preprocessing Failed[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()
            console.print("[bold yellow]Recommended Actions:[/bold yellow]")
            console.print("  • Check the error message above for details")
            console.print("  • Report this issue if it persists: [cyan]https://github.com/pipelex/pipelex/issues[/cyan]")
            console.print()
        sys.exit(1)

    # Output JSON if requested
    if output_json:
        MODEL_AVAILABILITY_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with MODEL_AVAILABILITY_JSON_PATH.open("w", encoding="utf-8") as json_file:
            json.dump(availability, json_file, indent=2)

        if not quiet:
            console.print(f"[green]✓[/green] Wrote model availability to {MODEL_AVAILABILITY_JSON_PATH}")

    # Load test profile, collections, and filter
    try:
        test_profile = _load_test_profile(profile)
    except TomlError as exc:
        # TOML parsing error in config file
        if quiet:
            console.print(f"[red]✗ Preprocessing failed:[/red] TOML syntax error - {escape(exc.message)}")
        else:
            error_panel = Panel(
                f"[red]✗[/red] TOML syntax error in configuration file\n\n"
                f"[dim]{escape(exc.message)}[/dim]\n\n"
                f"Check these files for syntax errors:\n"
                f"  • [cyan]{TEST_PROFILES_PATH}[/cyan]\n"
                f"  • [cyan]{TEST_PROFILES_OVERRIDE_PATH}[/cyan] (if it exists)",
                title="[bold red]Configuration Error[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()
            console.print("[bold yellow]Recommended Actions:[/bold yellow]")
            console.print("  • Validate your TOML syntax at: [cyan]https://www.toml-lint.com/[/cyan]")
            console.print("  • Check for unclosed brackets, missing quotes, or invalid characters")
            console.print()
        sys.exit(1)
    except ValueError as exc:
        # Profile not found error
        error_message = str(exc)
        if quiet:
            console.print(f"[red]✗ Preprocessing failed:[/red] {escape(error_message)}")
        else:
            error_panel = Panel(
                f"[red]✗[/red] {escape(error_message)}\n\n[dim]The specified profile does not exist in the configuration.[/dim]",
                title="[bold red]Profile Not Found[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()
            console.print("[bold yellow]Recommended Actions:[/bold yellow]")
            console.print("  • Use one of the available profiles listed above")
            console.print("  • Check for typos (profiles are case-sensitive)")
            console.print(f"  • Review profiles in: [cyan]{TEST_PROFILES_PATH}[/cyan]")
            console.print()
        sys.exit(1)
    except OSError as exc:
        # File system errors (file deleted, permissions, etc.)
        if quiet:
            console.print(f"[red]✗ Preprocessing failed:[/red] File system error - {escape(str(exc))}")
        else:
            error_panel = Panel(
                f"[red]✗[/red] File system error while reading test profiles\n\n[dim]{escape(str(exc))}[/dim]",
                title="[bold red]File System Error[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()
            console.print("[bold yellow]Recommended Actions:[/bold yellow]")
            console.print(f"  • Check file permissions for: [cyan]{TEST_PROFILES_PATH}[/cyan]")
            console.print(f"  • Verify file exists: [cyan]{TEST_PROFILES_OVERRIDE_PATH}[/cyan] (if used)")
            console.print()
        sys.exit(1)

    collections = _load_collections()
    combo_pairs = _filter_models_by_profile(availability, test_profile, collections)

    # Generate fixtures if requested
    if generate_fixtures:
        fixtures_content = _generate_fixtures_python(combo_pairs, profile)
        GENERATED_FIXTURES_PATH.parent.mkdir(parents=True, exist_ok=True)
        GENERATED_FIXTURES_PATH.write_text(fixtures_content, encoding="utf-8")

        if not quiet:
            console.print(f"[green]✓[/green] Generated fixtures at {GENERATED_FIXTURES_PATH}")

    # Display summary
    if not quiet:
        console.print()
        _display_summary(availability, combo_pairs, profile, console)
        console.print()

        # Show profile info
        if test_profile.get("include_all"):
            console.print(f"[dim]Profile '{profile}': Including all available models[/dim]")
        else:
            backends = test_profile.get("backends", [])
            console.print(f"[dim]Profile '{profile}': {len(backends)} backends configured[/dim]")

        console.print()

    # Final status
    total_pairs = sum(len(pairs) for pairs in combo_pairs.values())
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
