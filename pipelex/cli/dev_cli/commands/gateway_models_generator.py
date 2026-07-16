"""Generator for Pipelex Gateway models reference file."""

from __future__ import annotations

from datetime import UTC, datetime
from operator import itemgetter
from typing import TYPE_CHECKING, Any, cast

from pipelex.system.pipelex_service.remote_config_fetcher import RemoteConfigFetcher
from pipelex.urls import URLs

if TYPE_CHECKING:
    from pipelex.cogt.model_backends.model_spec_factory import BackendModelSpecs

# Fields to include in the reference (excluding sensitive/internal details)
REFERENCE_FIELDS = frozenset({"model_type", "inputs", "outputs"})

# Model type display names and order
MODEL_TYPE_SECTIONS = {
    "llm": "Language Models (LLM)",
    "text_extractor": "Document Extraction Models",
    "img_gen": "Image Generation Models",
}

# Preferred column order for inputs and outputs (columns not listed will be appended alphabetically)
PREFERRED_INPUT_ORDER = ["text", "images", "image", "pdf"]
PREFERRED_OUTPUT_ORDER = ["text", "structured", "image", "pages"]


def normalize_for_comparison(content: str) -> str:
    """Remove timestamp line for comparison since it changes every generation."""
    lines = content.split("\n")
    return "\n".join(line for line in lines if not line.startswith("> Last updated:"))


def fetch_gateway_model_specs() -> BackendModelSpecs:
    """Fetch model specifications from Pipelex Gateway remote config.

    Uses ``require_fresh=True`` so a stale cache never gets baked into the committed
    reference docs this command regenerates.

    Returns:
        Dictionary of model specifications.

    Raises:
        RemoteConfigUnavailableError: If the network is unreachable (cache fallback is
            explicitly refused here).
        RemoteConfigValidationError: If the remote config is invalid.
    """
    result = RemoteConfigFetcher.fetch_remote_config(require_fresh=True)
    return dict(result.config.backend_model_specs)


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
        }

        # Add to appropriate group
        if model_type in models_by_type:
            models_by_type[model_type].append(model_info)

    # Sort models alphabetically within each type
    for model_list in models_by_type.values():
        model_list.sort(key=itemgetter("name"))

    return models_by_type


def generate_pure_markdown_list(models: list[dict[str, Any]]) -> str:
    """Generate a pure Markdown bullet list for a list of models (no HTML/tables).

    Args:
        models: List of model info dictionaries.

    Returns:
        Pure Markdown bullet list string.
    """
    if not models:
        return "_No models available in this category._\n"

    lines: list[str] = []
    for model in models:
        name: str = model.get("name", "")
        inputs: list[str] = model.get("inputs", [])
        outputs: list[str] = model.get("outputs", [])

        # Sort inputs and outputs using preferred order
        def sort_by_preferred(items: list[str], *, preferred: list[str]) -> list[str]:
            item_set = set(items)
            ordered = [col for col in preferred if col in item_set]
            remaining = sorted(item_set - set(preferred))
            return ordered + remaining

        sorted_inputs = sort_by_preferred(inputs, preferred=PREFERRED_INPUT_ORDER)
        sorted_outputs = sort_by_preferred(outputs, preferred=PREFERRED_OUTPUT_ORDER)

        inputs_str = ", ".join(sorted_inputs) if sorted_inputs else "none"
        outputs_str = ", ".join(sorted_outputs) if sorted_outputs else "none"

        lines.append(f"- **{name}**")
        lines.append(f"  - inputs: {inputs_str}")
        lines.append(f"  - outputs: {outputs_str}")

    return "\n".join(lines) + "\n"


def generate_markdown_table(models: list[dict[str, Any]]) -> str:
    """Generate an HTML table for a list of models with grouped input/output headers.

    Args:
        models: List of model info dictionaries.

    Returns:
        HTML table string.
    """
    if not models:
        return "_No models available in this category._\n"

    # Collect all unique input and output types across all models
    all_inputs: set[str] = set()
    all_outputs: set[str] = set()
    for model in models:
        all_inputs.update(model.get("inputs", []))
        all_outputs.update(model.get("outputs", []))

    # Sort columns using preferred order, with any unlisted columns appended alphabetically
    def sort_by_preferred(items: set[str], *, preferred: list[str]) -> list[str]:
        ordered = [col for col in preferred if col in items]
        remaining = sorted(items - set(preferred))
        return ordered + remaining

    input_cols = sort_by_preferred(all_inputs, preferred=PREFERRED_INPUT_ORDER)
    output_cols = sort_by_preferred(all_outputs, preferred=PREFERRED_OUTPUT_ORDER)

    # Background colors for visual separation (semi-transparent for dark/light mode compatibility)
    input_bg = "background-color:rgba(33,150,243,0.15)"  # Semi-transparent blue
    output_bg = "background-color:rgba(76,175,80,0.15)"  # Semi-transparent green

    # Build HTML table
    lines = ["<table>", "<thead>"]

    # First header row with grouped columns (Model + Inputs span + Outputs span)
    lines.append("<tr>")
    lines.append('<th rowspan="2">Model</th>')
    if input_cols:
        lines.append(f'<th colspan="{len(input_cols)}" style="text-align:center;{input_bg}">Inputs</th>')
    if output_cols:
        lines.append(f'<th colspan="{len(output_cols)}" style="text-align:center;{output_bg}">Outputs</th>')
    lines.append("</tr>")

    # Second header row with individual column names
    lines.append("<tr>")
    for inp in input_cols:
        lines.append(f'<th style="text-align:center;{input_bg}">{inp}</th>')
    for out in output_cols:
        lines.append(f'<th style="text-align:center;{output_bg}">{out}</th>')
    lines.append("</tr>")

    lines.append("</thead>")
    lines.append("<tbody>")

    # Data rows
    for model in models:
        model_inputs = set(model.get("inputs", []))
        model_outputs = set(model.get("outputs", []))
        name = model.get("name", "")

        lines.append("<tr>")
        lines.append(f"<td>{name}</td>")
        for inp in input_cols:
            check = "✅" if inp in model_inputs else "❌"
            lines.append(f'<td style="text-align:center;{input_bg}">{check}</td>')
        for out in output_cols:
            check = "✅" if out in model_outputs else "❌"
            lines.append(f'<td style="text-align:center;{output_bg}">{check}</td>')
        lines.append("</tr>")

    lines.append("</tbody>")
    lines.append("</table>")

    return "\n".join(lines) + "\n"


def generate_reference_markdown(model_specs: BackendModelSpecs) -> str:
    """Generate the complete Markdown reference file content.

    Args:
        model_specs: Raw model specifications from remote config.

    Returns:
        Complete Markdown content for the reference file.
    """
    models_by_type = extract_reference_data(model_specs)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    sections = [
        "# Pipelex Gateway — Available Models",
        "This file lists the LLMs, document extraction models, and image generation models currently available through Pipelex Gateway.",
        f"For configuration details, see the [documentation]({URLs.gateway_docs}).",
        "",
    ]

    # Add LLM section
    sections.append("## Language Models (LLM)")
    sections.append("")
    sections.append(generate_markdown_table(models_by_type["llm"]))

    # Add document extractor section
    sections.append("## Document Extraction Models")
    sections.append("")
    sections.append(generate_markdown_table(models_by_type["text_extractor"]))
    sections.append("")
    sections.append(
        "!!! info About extracted pages\n"
        "    Each page contains Markdown text (based on AI-interpreted layout) and optional extracted images. "
        "A single image input is treated as one page. Pipelex also wraps the `pypdfium2` library for raw text "
        "(without any AI interpretation) and images extraction and page views rendering. "
        "All these elements can be used as inputs into downstream pipes, including LLM prompts."
    )

    # Add image generation section
    sections.append("## Image Generation Models")
    sections.append("")
    sections.append(generate_markdown_table(models_by_type["img_gen"]))

    # Add auto-generated notice at the bottom
    sections.append("")
    sections.append("> **AUTO-GENERATED FILE** - Do not edit manually.")
    sections.append(f"> Last updated: {timestamp}")
    sections.append(">")
    sections.append("> Run `pipelex-dev update-gateway-models` or `make ugm` to regenerate.")

    return "\n".join(sections)


def generate_reference_pure_markdown(model_specs: BackendModelSpecs) -> str:
    """Generate a pure Markdown reference file content (no HTML, plain text readable).

    Args:
        model_specs: Raw model specifications from remote config.

    Returns:
        Complete pure Markdown content for the reference file.
    """
    models_by_type = extract_reference_data(model_specs)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    sections = [
        "# Pipelex Gateway — Available Models (Plain Text)",
        "",
        "This file lists the LLMs, document extraction models, and image generation models currently available through Pipelex Gateway.",
        f"For configuration details, see the [documentation]({URLs.gateway_docs}).",
        "",
        "**Note:** This is the plain-text readable version. See `pipelex_gateway_models.md` for the HTML-styled version.",
        "",
    ]

    # Add LLM section
    sections.append("## Language Models (LLM)")
    sections.append("")
    sections.append(generate_pure_markdown_list(models_by_type["llm"]))

    # Add document extractor section
    sections.append("## Document Extraction Models")
    sections.append("")
    sections.append(generate_pure_markdown_list(models_by_type["text_extractor"]))
    sections.append("")
    sections.append(
        "**About extracted pages:** "
        "Each page contains Markdown text (based on AI-interpreted layout) and optional extracted images. "
        "A single image input is treated as one page. Pipelex also wraps the `pypdfium2` library for raw text "
        "(without any AI interpretation) and images extraction and page views rendering. "
        "All these elements can be used as inputs into downstream pipes, including LLM prompts."
    )

    # Add image generation section
    sections.append("")
    sections.append("## Image Generation Models")
    sections.append("")
    sections.append(generate_pure_markdown_list(models_by_type["img_gen"]))

    # Add auto-generated notice at the bottom
    sections.append("")
    sections.append("> **AUTO-GENERATED FILE** - Do not edit manually.")
    sections.append(f"> Last updated: {timestamp}")
    sections.append(">")
    sections.append("> Run `pipelex-dev update-gateway-models` or `make ugm` to regenerate.")

    return "\n".join(sections)
