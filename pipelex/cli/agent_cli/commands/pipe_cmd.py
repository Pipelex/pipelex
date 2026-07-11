"""Agent CLI pipe command - structure pipes from JSON specs with raw TOML output."""

# pyright: reportUnknownMemberType=false
# pyright: reportArgumentType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnusedExcept=false
# mypy: disable-error-code="arg-type,no-any-return,attr-defined"

import json
from typing import Annotated, Any

import tomlkit
import typer
from pydantic import ValidationError

from pipelex.builder.operations.pipe_ops import parse_pipe_spec
from pipelex.builder.pipe.pipe_batch_spec import PipeBatchSpec
from pipelex.builder.pipe.pipe_compose_spec import PipeComposeSpec
from pipelex.builder.pipe.pipe_condition_spec import PipeConditionSpec
from pipelex.builder.pipe.pipe_extract_spec import PipeExtractSpec
from pipelex.builder.pipe.pipe_func_spec import PipeFuncSpec
from pipelex.builder.pipe.pipe_img_gen_spec import PipeImgGenSpec
from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.builder.pipe.pipe_search_spec import PipeSearchSpec
from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.builder.pipe.pipe_signature_spec import PipeSignatureSpec
from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.builder.pipe.pipe_spec_map import pipe_type_to_spec_class
from pipelex.builder.pipe.pipe_structure_spec import PipeStructureSpec
from pipelex.cli.agent_cli.commands.agent_output import agent_error
from pipelex.language.toml_string_utils import format_toml_string
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error_for_agent


def _pipe_spec_to_toml(pipe_spec: PipeSpec) -> str:
    """Convert a PipeSpec to TOML string format.

    Args:
        pipe_spec: The validated PipeSpec to convert.

    Returns:
        TOML string representation of the pipe.
    """
    doc = tomlkit.document()
    pipe_item_table = tomlkit.table()

    # Add type — a signature is typeless (no type line; omitting the type IS the signature); every
    # concrete pipe names its type.
    if not isinstance(pipe_spec, PipeSignatureSpec):
        pipe_item_table.add("type", pipe_spec.type)

    # Add description
    pipe_item_table.add("description", format_toml_string(pipe_spec.description))

    # Add inputs as inline table
    if pipe_spec.inputs:
        inputs_inline = tomlkit.inline_table()
        for input_name, input_concept in pipe_spec.inputs.items():
            inputs_inline.append(input_name, input_concept)
        pipe_item_table.add("inputs", inputs_inline)

    # Add output
    pipe_item_table.add("output", pipe_spec.output)

    # Add type-specific fields
    _add_type_specific_fields(pipe_spec, pipe_table=pipe_item_table)

    # Build the nested structure: [pipe.pipe_code]
    pipe_section = tomlkit.table()
    pipe_section.add(pipe_spec.pipe_code, pipe_item_table)
    doc.add("pipe", pipe_section)
    return tomlkit.dumps(doc)


def _add_type_specific_fields(pipe_spec: PipeSpec, *, pipe_table: tomlkit.TOMLDocument | tomlkit.items.Table) -> None:  # type: ignore[name-defined]
    """Add type-specific fields to the pipe TOML table.

    Args:
        pipe_spec: The pipe spec with type-specific fields.
        pipe_table: The TOML table to add fields to.
    """
    if isinstance(pipe_spec, PipeLLMSpec):
        if pipe_spec.model:
            pipe_table.add("model", pipe_spec.model)
        if pipe_spec.system_prompt:
            pipe_table.add("system_prompt", format_toml_string(pipe_spec.system_prompt))
        if pipe_spec.prompt:
            pipe_table.add("prompt", format_toml_string(pipe_spec.prompt))
        if pipe_spec.structuring_method is not None:
            pipe_table.add("structuring_method", pipe_spec.structuring_method)

    elif isinstance(pipe_spec, PipeStructureSpec):
        if pipe_spec.model:
            pipe_table.add("model", pipe_spec.model)

    elif isinstance(pipe_spec, PipeComposeSpec):
        if pipe_spec.construct_spec is not None:
            # Construct mode: serialize the construct block as a nested TOML table
            construct_table = tomlkit.table()
            for field_name, field_value in pipe_spec.construct_spec.items():
                if isinstance(field_value, dict):
                    field_inline = tomlkit.inline_table()
                    inner_dict: dict[str, Any] = field_value
                    for key, value in inner_dict.items():
                        field_inline.append(key, value)
                    construct_table.add(field_name, field_inline)
                else:
                    construct_table.add(field_name, field_value)
            pipe_table.add("construct", construct_table)
        else:
            # Template mode — guard optional fields like other pipe types do
            if pipe_spec.target_format is not None:
                pipe_table.add("target_format", str(pipe_spec.target_format))
            if pipe_spec.template is not None:
                pipe_table.add("template", format_toml_string(pipe_spec.template))

    elif isinstance(pipe_spec, PipeSequenceSpec):
        steps_array = tomlkit.array()
        for step in pipe_spec.steps:
            step_inline = tomlkit.inline_table()
            step_inline.append("pipe", step.pipe_code)
            step_inline.append("result", step.result)
            if step.batch_over is not None:
                step_inline.append("batch_over", step.batch_over)
            if step.batch_as is not None:
                step_inline.append("batch_as", step.batch_as)
            steps_array.append(step_inline)
        pipe_table.add("steps", steps_array)

    elif isinstance(pipe_spec, PipeParallelSpec):
        pipe_table.add("add_each_output", pipe_spec.add_each_output)
        branches_array = tomlkit.array()
        for branch in pipe_spec.branches:
            branch_inline = tomlkit.inline_table()
            branch_inline.append("pipe", branch.pipe_code)
            branch_inline.append("result", branch.result)
            branches_array.append(branch_inline)
        pipe_table.add("branches", branches_array)

    elif isinstance(pipe_spec, PipeConditionSpec):
        pipe_table.add("expression", pipe_spec.jinja2_expression_template)
        outcomes_table = tomlkit.inline_table()
        for condition, outcome in pipe_spec.outcomes.items():
            outcomes_table.append(condition, outcome)
        pipe_table.add("outcomes", outcomes_table)
        pipe_table.add("default_outcome", pipe_spec.default_outcome)

    elif isinstance(pipe_spec, PipeBatchSpec):
        pipe_table.add("branch_pipe_code", pipe_spec.branch_pipe_code)
        pipe_table.add("input_list_name", pipe_spec.input_list_name)
        pipe_table.add("input_item_name", pipe_spec.input_item_name)

    elif isinstance(pipe_spec, PipeExtractSpec):
        if pipe_spec.model:
            pipe_table.add("model", pipe_spec.model)

    elif isinstance(pipe_spec, PipeImgGenSpec):
        if pipe_spec.model:
            pipe_table.add("model", pipe_spec.model)
        pipe_table.add("prompt", format_toml_string(pipe_spec.prompt))

    elif isinstance(pipe_spec, PipeFuncSpec):
        pipe_table.add("function_name", pipe_spec.function_name)

    elif isinstance(pipe_spec, PipeSearchSpec):
        if pipe_spec.model:
            pipe_table.add("model", pipe_spec.model)
        pipe_table.add("prompt", format_toml_string(pipe_spec.prompt))
        if pipe_spec.from_date is not None:
            pipe_table.add("from_date", pipe_spec.from_date)
        if pipe_spec.to_date is not None:
            pipe_table.add("to_date", pipe_spec.to_date)
        if pipe_spec.include_domains is not None:
            pipe_table.add("include_domains", pipe_spec.include_domains)
        if pipe_spec.exclude_domains is not None:
            pipe_table.add("exclude_domains", pipe_spec.exclude_domains)
        if pipe_spec.max_results is not None:
            pipe_table.add("max_results", pipe_spec.max_results)

    elif isinstance(pipe_spec, PipeSignatureSpec):
        if pipe_spec.signature_for is not None:
            pipe_table.add("signature_for", pipe_spec.signature_for)


def pipe_cmd(
    pipe_type: Annotated[
        str | None,
        typer.Option(
            "--type",
            "--pipe-type",
            "--pipe_type",
            "-t",
            help=f"Pipe type. Must be one of: {list(pipe_type_to_spec_class)}. Omit for a signature (contract only, no type).",
        ),
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

    Outputs raw TOML to stdout on success, JSON to stderr on error with exit code 1.

    JSON spec format (varies by pipe type):

    PipeLLM:
    {
        "pipe_code": "my_pipe",
        "description": "What the pipe does",
        "inputs": {"input_name": "ConceptName"},
        "output": "OutputConcept",
        "model": "$writing-creative",
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

    PipeSignature (contract only — omit the type): a pipe with no type and no implementation is a
    signature. Omit --type (and any "type" key) and declare only the contract:
    {
        "pipe_code": "summarize_doc",
        "description": "Produces a summary of a document.",
        "inputs": {"doc": "Document"},
        "output": "Text"
    }

    Examples:
        pipelex-agent pipe --type PipeLLM --spec '{"pipe_code": "summarize", ...}'
        pipelex-agent pipe --type PipeSequence --spec-file pipe.json
        pipelex-agent pipe --spec '{"pipe_code": "summarize_doc", "description": "...", "output": "Text"}'
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

    # Accept "pipe_type" as an alias for "type" in the JSON spec
    if "pipe_type" in spec_data and "type" not in spec_data:
        spec_data["type"] = spec_data.pop("pipe_type")
    elif "pipe_type" in spec_data:
        spec_data.pop("pipe_type")

    # Resolve pipe type: CLI option takes precedence, then extract from spec JSON, else None (typeless).
    # A typeless spec is a signature — parse_pipe_spec routes it to PipeSignatureSpec (or raises a
    # teaching error if it declares more than the contract). An explicit "PipeSignature" is rejected
    # there with a migration error — a signature has no type.
    resolved_pipe_type: str | None
    if pipe_type is not None:
        resolved_pipe_type = pipe_type
    elif "type" in spec_data:
        raw_pipe_type = spec_data.pop("type")
        if raw_pipe_type is None:
            # A signature is authored by OMITTING the `type` key — an explicit null is not the same as
            # absent, and must not silently collapse to a typeless signature.
            agent_error(
                "A JSON `type` key cannot be null. Delete the `type` key — a pipe with no `type` and no "
                "implementation is a signature (contract only).",
                error_type="ArgumentError",
            )
        if not isinstance(raw_pipe_type, str):
            # A non-string `type` (list/dict/number) is an authoring mistake — sanitize it at this
            # untrusted-input boundary so it surfaces as an actionable ArgumentError, not a cryptic
            # internal TypeError (an unhashable list/dict would blow up the membership test downstream).
            agent_error(
                f"Invalid pipe type '{raw_pipe_type}'. Must be one of: {list(pipe_type_to_spec_class)}, "
                "or omit `type` for a signature (contract only, no type).",
                error_type="ArgumentError",
            )
        resolved_pipe_type = raw_pipe_type
    else:
        resolved_pipe_type = None

    # Validate and convert spec
    try:
        pipe_spec = parse_pipe_spec(spec_data, pipe_type=resolved_pipe_type)
        toml_content = _pipe_spec_to_toml(pipe_spec)

        print(toml_content, end="" if toml_content.endswith("\n") else "\n")

    except ValidationError as exc:
        message, details = format_pydantic_validation_error_for_agent(exc)
        agent_error(message, error_type="ValidationError", cause=exc, validation_details=details)

    except ValueError as exc:
        agent_error(str(exc), error_type="ValueError", cause=exc)

    except Exception as exc:  # noqa: BLE001
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
        agent_error(str(exc), error_type=type(exc).__name__, cause=exc)
