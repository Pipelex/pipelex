"""Agent CLI concept command - structure concepts from JSON specs with raw TOML output."""

# pyright: reportUnknownMemberType=false

import json
from typing import Annotated, Any

import tomlkit
import typer
from pydantic import ValidationError

from pipelex.builder.concept.concept_spec import ConceptSpec
from pipelex.builder.operations.concept_ops import parse_concept_spec, structure_field_to_dict
from pipelex.cli.agent_cli.commands.agent_output import agent_error
from pipelex.language.toml_string_utils import format_toml_string
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error_for_agent


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
    concept_item_table.add("description", format_toml_string(concept_spec.description))

    # Add refines if present
    if concept_spec.refines:
        concept_item_table.add("refines", concept_spec.refines)

    # Add structure if present
    if concept_spec.structure:
        structure_table = tomlkit.table()
        for field_name, field_spec in concept_spec.structure.items():
            field_dict = structure_field_to_dict(field_spec)
            # If only description is present, use simple string format
            if len(field_dict) == 1 and "description" in field_dict:
                structure_table.add(field_name, format_toml_string(field_dict["description"]))
            else:
                inline_table = tomlkit.inline_table()
                for key, value in field_dict.items():
                    inline_table.append(key, value)
                structure_table.add(field_name, inline_table)
        concept_item_table.add("structure", structure_table)

    # Build the nested structure: [concept.ConceptName]
    concept_section.add(concept_spec.concept_code, concept_item_table)
    doc.add("concept", concept_section)
    return tomlkit.dumps(doc)


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

    Outputs raw TOML to stdout on success, JSON to stderr on error with exit code 1.

    JSON spec format:
    {
        "concept_code": "MyConceptName",
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
        pipelex-agent concept --spec '{"concept_code": "Invoice", "description": "A commercial invoice", "refines": "Text"}'
        pipelex-agent concept --spec-file concept.json
    """
    # Validate that exactly one of spec or spec_file is provided
    if spec is None and spec_file is None:
        agent_error("Either --spec or --spec-file must be provided", error_type="ArgumentError")

    if spec is not None and spec_file is not None:
        agent_error("Cannot use both --spec and --spec-file", error_type="ArgumentError")

    # Load spec data
    spec_data: dict[str, Any]
    try:
        if spec_file:
            with open(spec_file, encoding="utf-8") as the_file:
                spec_data = json.load(the_file)
        else:
            spec_data = json.loads(spec)  # type: ignore[arg-type]
    except FileNotFoundError as exc:
        agent_error(f"Spec file not found: {spec_file}", error_type="FileNotFoundError", cause=exc)
    except json.JSONDecodeError as exc:
        agent_error(f"Invalid JSON: {exc.msg}", error_type="JSONDecodeError", cause=exc)

    # Validate and convert spec
    try:
        concept_spec = parse_concept_spec(spec_data)
        toml_content = _concept_spec_to_toml(concept_spec)

        print(toml_content, end="" if toml_content.endswith("\n") else "\n")

    except ValidationError as exc:
        message, details = format_pydantic_validation_error_for_agent(exc)
        agent_error(message, error_type="ValidationError", cause=exc, validation_details=details)

    except ValueError as exc:
        agent_error(str(exc), error_type="ValueError", cause=exc)

    except Exception as exc:  # ruff: ignore[blind-except]
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
        agent_error(str(exc), error_type=type(exc).__name__, cause=exc)
