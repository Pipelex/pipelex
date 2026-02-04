"""Agent CLI concept command - structure concepts from JSON specs with JSON/TOML output."""

# pyright: reportUnknownMemberType=false

import json
import sys
from typing import Annotated, Any

import tomlkit
import typer
from pydantic import ValidationError

from pipelex.builder.concept.concept_spec import ConceptSpec, ConceptStructureSpec
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


def _concept_spec_to_toml(concept_spec: ConceptSpec) -> str:
    """Convert a ConceptSpec to TOML string format.

    Args:
        concept_spec: The validated ConceptSpec to convert.

    Returns:
        TOML string representation of the concept.
    """
    doc = tomlkit.document()

    # Create the [concept.ConceptName] section
    concept_section = tomlkit.table()
    concept_item_table = tomlkit.table()

    # Add description
    concept_item_table.add("description", concept_spec.description)

    # Add refines if present
    if concept_spec.refines:
        concept_item_table.add("refines", concept_spec.refines)

    # Add structure if present
    if concept_spec.structure:
        structure_table = tomlkit.table()
        for field_name, field_spec in concept_spec.structure.items():
            field_dict = _structure_field_to_dict(field_spec)
            # If only description is present, use simple string format
            if len(field_dict) == 1 and "description" in field_dict:
                structure_table.add(field_name, field_dict["description"])
            else:
                inline_table = tomlkit.inline_table()
                for key, value in field_dict.items():
                    inline_table.append(key, value)
                structure_table.add(field_name, inline_table)
        concept_item_table.add("structure", structure_table)

    # Build the nested structure: [concept.ConceptName]
    concept_section.add(concept_spec.the_concept_code, concept_item_table)
    doc.add("concept", concept_section)
    return tomlkit.dumps(doc)


def _structure_field_to_dict(field_spec: ConceptStructureSpec) -> dict[str, Any]:
    """Convert a ConceptStructureSpec to a dictionary for TOML serialization.

    Args:
        field_spec: The field specification to convert.

    Returns:
        Dictionary with field properties.
    """
    result: dict[str, Any] = {}

    # Type is always needed unless it's just a text description
    if field_spec.type.value != "text" or field_spec.required or field_spec.default_value is not None:
        result["type"] = field_spec.type.value

    result["description"] = field_spec.description

    if field_spec.required:
        result["required"] = True

    if field_spec.default_value is not None:
        result["default"] = field_spec.default_value

    if field_spec.concept_ref:
        result["concept_ref"] = field_spec.concept_ref

    return result


def _parse_concept_spec_from_json(spec_data: dict[str, Any]) -> ConceptSpec:
    """Parse and validate a ConceptSpec from JSON data.

    Args:
        spec_data: Raw JSON data for the concept spec.

    Returns:
        Validated ConceptSpec instance.

    Raises:
        ValidationError: If validation fails.
    """
    # Convert structure if present - need to add field names
    if spec_data.get("structure"):
        structure_data = spec_data["structure"]
        converted_structure: dict[str, Any] = {}
        for field_name, field_data in structure_data.items():
            if isinstance(field_data, str):
                # Simple string means just description, default to text type
                converted_structure[field_name] = {
                    "the_field_name": field_name,
                    "description": field_data,
                    "type": "text",
                }
            else:
                # Full field spec
                field_data["the_field_name"] = field_name
                converted_structure[field_name] = field_data
        spec_data["structure"] = converted_structure

    return ConceptSpec.model_validate(spec_data)


def concept_cmd(
    spec: Annotated[
        str | None,
        typer.Option("--spec", "-s", help="JSON string with concept specification"),
    ] = None,
    spec_file: Annotated[
        str | None,
        typer.Option("--spec-file", "-f", help="Path to JSON file with concept specification"),
    ] = None,
) -> None:
    """Structure a concept from JSON spec and output TOML.

    Takes a concept specification in JSON format and converts it to valid Pipelex
    TOML format. Validates the spec before conversion.

    Outputs JSON to stdout on success, JSON to stderr on error with exit code 1.

    JSON spec format:
    {
        "the_concept_code": "MyConceptName",
        "description": "Description of the concept",
        "refines": "Text",  // Optional: native concept to refine
        "structure": {      // Optional: for structured concepts
            "field_name": "Field description",  // Simple text field
            "typed_field": {
                "type": "integer",
                "description": "Field description",
                "required": true
            }
        }
    }

    Examples:
        pipelex-agent concept --spec '{"the_concept_code": "Invoice", "description": "A commercial invoice", "refines": "Text"}'
        pipelex-agent concept --spec-file concept.json
    """
    error_json: dict[str, Any]

    # Validate that exactly one of spec or spec_file is provided
    if spec is None and spec_file is None:
        error_json = {
            "error": True,
            "error_type": "ArgumentError",
            "message": "Either --spec or --spec-file must be provided",
        }
        print(json.dumps(error_json, indent=2), file=sys.stderr)
        raise typer.Exit(1)

    if spec is not None and spec_file is not None:
        error_json = {
            "error": True,
            "error_type": "ArgumentError",
            "message": "Cannot use both --spec and --spec-file",
        }
        print(json.dumps(error_json, indent=2), file=sys.stderr)
        raise typer.Exit(1)

    # Load spec data
    spec_data: dict[str, Any]
    try:
        if spec_file:
            with open(spec_file, encoding="utf-8") as the_file:
                spec_data = json.load(the_file)
        else:
            spec_data = json.loads(spec)  # type: ignore[arg-type]
    except FileNotFoundError:
        error_json = {
            "error": True,
            "error_type": "FileNotFoundError",
            "message": f"Spec file not found: {spec_file}",
        }
        print(json.dumps(error_json, indent=2), file=sys.stderr)
        raise typer.Exit(1) from None
    except json.JSONDecodeError as exc:
        error_json = {
            "error": True,
            "error_type": "JSONDecodeError",
            "message": f"Invalid JSON: {exc.msg}",
        }
        print(json.dumps(error_json, indent=2), file=sys.stderr)
        raise typer.Exit(1) from exc

    # Validate and convert spec
    try:
        concept_spec = _parse_concept_spec_from_json(spec_data)
        toml_content = _concept_spec_to_toml(concept_spec)

        result = {
            "success": True,
            "concept_code": concept_spec.the_concept_code,
            "toml": toml_content,
        }
        print(json.dumps(result, indent=2))

    except ValidationError as exc:
        error_json = {
            "error": True,
            "error_type": "ValidationError",
            "message": format_pydantic_validation_error(exc),
        }
        print(json.dumps(error_json, indent=2), file=sys.stderr)
        raise typer.Exit(1) from exc

    except Exception as exc:
        error_json = {
            "error": True,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        print(json.dumps(error_json, indent=2), file=sys.stderr)
        raise typer.Exit(1) from exc
