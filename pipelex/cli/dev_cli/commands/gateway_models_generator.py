"""Generator for Pipelex Gateway models reference file."""

from __future__ import annotations

from datetime import datetime, timezone
from operator import itemgetter
from typing import TYPE_CHECKING, Any, cast

from pipelex.system.pipelex_service.remote_config_fetcher import RemoteConfigFetcher
from pipelex.urls import URLs

if TYPE_CHECKING:
    from pipelex.cogt.model_backends.model_spec_factory import BackendModelSpecs

# Fields to include in the reference (excluding sensitive/internal details)
REFERENCE_FIELDS = frozenset({"model_type", "inputs", "outputs", "sdk", "structure_method"})

# Model type display names and order
MODEL_TYPE_SECTIONS = {
    "llm": "Language Models (LLM)",
    "text_extractor": "Document Extraction Models",
    "img_gen": "Image Generation Models",
}


def fetch_gateway_model_specs() -> BackendModelSpecs:
    """Fetch model specifications from Pipelex Gateway remote config.

    Returns:
        Dictionary of model specifications.

    Raises:
        RemoteConfigFetchError: If the remote config cannot be fetched.
        RemoteConfigValidationError: If the remote config is invalid.
    """
    remote_config = RemoteConfigFetcher.fetch_remote_config()
    return dict(remote_config.backend_model_specs)


def extract_reference_data(model_specs: BackendModelSpecs) -> dict[str, list[dict[str, Any]]]:
    """Extract and organize model data for the reference file.

    Args:
        model_specs: Raw model specifications from remote config.

    Returns:
        Dictionary mapping model_type to list of model info dicts.
    """
    # Get defaults for fallback values
    defaults = model_specs.get("defaults", {})
    default_model_type = defaults.get("model_type", "llm")
    default_sdk = defaults.get("sdk", "")
    default_structure_method = defaults.get("structure_method", "")

    # Group models by type
    models_by_type: dict[str, list[dict[str, Any]]] = {
        "llm": [],
        "text_extractor": [],
        "img_gen": [],
    }

    for model_name, spec in model_specs.items():
        # Skip defaults and non-dict entries
        if model_name == "defaults" or not isinstance(spec, dict):
            continue

        # Skip .rules sub-sections (e.g., "flux-pro.rules")
        if ".rules" in model_name:
            continue

        # Cast spec for type checking (we verified it's a dict above)
        spec_dict = cast("dict[str, Any]", spec)

        # Determine model type
        model_type: str = spec_dict.get("model_type", default_model_type)

        # Extract reference fields
        model_info: dict[str, Any] = {
            "name": model_name,
            "inputs": spec_dict.get("inputs", []),
            "outputs": spec_dict.get("outputs", []),
            "sdk": spec_dict.get("sdk", default_sdk),
        }

        # Only include structure_method for LLMs (not relevant for img_gen)
        if model_type in {"llm", "text_extractor"}:
            model_info["structure_method"] = spec_dict.get("structure_method", default_structure_method)

        # Add to appropriate group
        if model_type in models_by_type:
            models_by_type[model_type].append(model_info)

    # Sort models alphabetically within each type
    for model_list in models_by_type.values():
        model_list.sort(key=itemgetter("name"))

    return models_by_type


def generate_markdown_table(models: list[dict[str, Any]], include_structure_method: bool = True) -> str:
    """Generate a Markdown table for a list of models.

    Args:
        models: List of model info dictionaries.
        include_structure_method: Whether to include the structure_method column.

    Returns:
        Markdown table string.
    """
    if not models:
        return "_No models available in this category._\n"

    # Build header
    if include_structure_method:
        header = "| Model | Inputs | Outputs | SDK | Structure Method |"
        separator = "|-------|--------|---------|-----|------------------|"
    else:
        header = "| Model | Inputs | Outputs | SDK |"
        separator = "|-------|--------|---------|-----|"

    lines = [header, separator]

    for model in models:
        inputs = ", ".join(model.get("inputs", []))
        outputs = ", ".join(model.get("outputs", []))
        sdk = model.get("sdk", "")
        name = model.get("name", "")

        if include_structure_method:
            structure_method = model.get("structure_method", "")
            lines.append(f"| {name} | {inputs} | {outputs} | {sdk} | {structure_method} |")
        else:
            lines.append(f"| {name} | {inputs} | {outputs} | {sdk} |")

    return "\n".join(lines) + "\n"


def generate_reference_markdown(model_specs: BackendModelSpecs) -> str:
    """Generate the complete Markdown reference file content.

    Args:
        model_specs: Raw model specifications from remote config.

    Returns:
        Complete Markdown content for the reference file.
    """
    models_by_type = extract_reference_data(model_specs)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    sections = [
        "# Pipelex Gateway - Available Models",
        "",
        "> **AUTO-GENERATED FILE** - Do not edit manually.",
        f"> Last updated: {timestamp}",
        ">",
        "> Run `pipelex-dev update-gateway-models` or `make ugm` to regenerate.",
        "",
        "This file documents models available through Pipelex Gateway.",
        f"For configuration details, see the [documentation]({URLs.gateway_docs}).",
        "",
    ]

    # Add LLM section
    sections.append("## Language Models (LLM)")
    sections.append("")
    sections.append(generate_markdown_table(models_by_type["llm"], include_structure_method=True))

    # Add document extractor section
    sections.append("## Document Extraction Models")
    sections.append("")
    sections.append(generate_markdown_table(models_by_type["text_extractor"], include_structure_method=True))

    # Add image generation section
    sections.append("## Image Generation Models")
    sections.append("")
    sections.append(generate_markdown_table(models_by_type["img_gen"], include_structure_method=False))

    return "\n".join(sections)
