"""Agent CLI concept command - structure concepts from JSON specs with JSON/TOML output."""

import json
from typing import Annotated, Any

import typer
from pydantic import ValidationError

from pipelex.builder.operations.concept_ops import concept_spec_to_toml, parse_concept_spec
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error_for_agent


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
    # Validate that exactly one of spec or spec_file is provided
    if spec is None and spec_file is None:
        agent_error("Either --spec or --spec-file must be provided", "ArgumentError")

    if spec is not None and spec_file is not None:
        agent_error("Cannot use both --spec and --spec-file", "ArgumentError")

    # Load spec data
    spec_data: dict[str, Any]
    try:
        if spec_file:
            with open(spec_file, encoding="utf-8") as the_file:
                spec_data = json.load(the_file)
        else:
            spec_data = json.loads(spec)  # type: ignore[arg-type]
    except FileNotFoundError as exc:
        agent_error(f"Spec file not found: {spec_file}", "FileNotFoundError", cause=exc)
    except json.JSONDecodeError as exc:
        agent_error(f"Invalid JSON: {exc.msg}", "JSONDecodeError", cause=exc)

    # Validate and convert spec
    try:
        concept_spec = parse_concept_spec(spec_data)
        toml_content = concept_spec_to_toml(concept_spec)

        agent_success(
            {
                "success": True,
                "concept_code": concept_spec.the_concept_code,
                "toml": toml_content,
            }
        )

    except ValidationError as exc:
        message, details = format_pydantic_validation_error_for_agent(exc)
        agent_error(message, "ValidationError", cause=exc, validation_details=details)

    except Exception as exc:
        agent_error(str(exc), type(exc).__name__, cause=exc)
