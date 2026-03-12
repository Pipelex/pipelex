"""Agent CLI pipe command - structure pipes from JSON specs with JSON/TOML output."""

import json
from typing import Annotated, Any

import typer
from pydantic import ValidationError

from pipelex.builder.operations.pipe_ops import PIPE_TYPE_TALENT_HINTS, parse_pipe_spec, pipe_spec_to_toml
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success
from pipelex.core.pipes.pipe_blueprint import PipeType
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error_for_agent


def pipe_cmd(
    pipe_type: Annotated[
        str | None,
        typer.Option("--type", "--pipe-type", "--pipe_type", "-t", help=f"Pipe type. Must be one of: {PipeType.value_list()}"),
    ] = None,
    spec: Annotated[
        str | None,
        typer.Option("--spec", "-s", help="JSON string with pipe specification"),
    ] = None,
    spec_file: Annotated[
        str | None,
        typer.Option("--spec-file", "-f", help="Path to JSON file with pipe specification"),
    ] = None,
) -> None:
    """Structure a pipe from JSON spec and output TOML.

    Takes a pipe specification in JSON format and converts it to valid Pipelex
    TOML format. Validates the spec before conversion.

    Outputs JSON to stdout on success, JSON to stderr on error with exit code 1.

    JSON spec format (varies by pipe type):

    PipeLLM:
    {
        "pipe_code": "my_pipe",
        "description": "What the pipe does",
        "inputs": {"input_name": "ConceptName"},
        "output": "OutputConcept",
        "llm_talent": "creative-writer",
        "prompt": "Your prompt with @block and $inline vars"
    }

    PipeSequence:
    {
        "pipe_code": "my_sequence",
        "description": "Chain of operations",
        "inputs": {"doc": "Document"},
        "output": "Result",
        "steps": [
            {"pipe": "step_one", "result": "step_one_result"},
            {"pipe": "step_two", "result": "step_two_result"}
        ]
    }

    Examples:
        pipelex-agent pipe --type PipeLLM --spec '{"pipe_code": "summarize", ...}'
        pipelex-agent pipe --type PipeSequence --spec-file pipe.json
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

    # Accept "pipe_type" as an alias for "type" in the JSON spec
    if "pipe_type" in spec_data and "type" not in spec_data:
        spec_data["type"] = spec_data.pop("pipe_type")
    elif "pipe_type" in spec_data:
        spec_data.pop("pipe_type")

    # Resolve pipe type: CLI option takes precedence, then extract from spec JSON
    resolved_pipe_type: str
    if pipe_type is not None:
        resolved_pipe_type = pipe_type
    elif "type" in spec_data:
        resolved_pipe_type = spec_data.pop("type")
    else:
        agent_error("Pipe type must be provided either via --type or as 'type' in the JSON spec", "ArgumentError")

    # Validate and convert spec
    try:
        pipe_spec = parse_pipe_spec(resolved_pipe_type, spec_data)
        toml_content = pipe_spec_to_toml(pipe_spec)

        agent_success(
            {
                "success": True,
                "pipe_code": pipe_spec.pipe_code,
                "pipe_type": resolved_pipe_type,
                "toml": toml_content,
            }
        )

    except ValidationError as exc:
        message, details = format_pydantic_validation_error_for_agent(exc)
        field_hints = PIPE_TYPE_TALENT_HINTS.get(resolved_pipe_type, {})
        agent_error(message, "ValidationError", cause=exc, validation_details=details, field_hints=field_hints)

    except ValueError as exc:
        agent_error(str(exc), "ValueError", cause=exc)

    except Exception as exc:
        agent_error(str(exc), type(exc).__name__, cause=exc)
