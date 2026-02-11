"""Agent CLI pipe command - structure pipes from JSON specs with JSON/TOML output."""

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

from pipelex.builder.pipe.pipe_batch_spec import PipeBatchSpec
from pipelex.builder.pipe.pipe_compose_spec import PipeComposeSpec
from pipelex.builder.pipe.pipe_condition_spec import PipeConditionSpec
from pipelex.builder.pipe.pipe_extract_spec import PipeExtractSpec
from pipelex.builder.pipe.pipe_func_spec import PipeFuncSpec
from pipelex.builder.pipe.pipe_img_gen_spec import PipeImgGenSpec
from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.builder.pipe.pipe_spec_map import pipe_type_to_spec_class
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success
from pipelex.core.pipes.pipe_blueprint import PipeType
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

# Static talent-to-model preset mappings (from pipelex.toml defaults)
LLM_TALENT_TO_MODEL: dict[str, str] = {
    "data-retrieval": "$retrieval",
    "hr-expert": "$writing-factual",
    "accounting-expert": "$writing-factual",
    "creative-writer": "$writing-creative",
    "engineer": "$engineering-structured",
    "coder": "$engineering-code",
    "code-analyzer": "$engineering-codebase-analysis",
    "vision-language-model": "$vision",
    "visual-designer": "$img-gen-prompting",
}

IMG_GEN_TALENT_TO_MODEL: dict[str, str] = {
    "gen-image": "$gen-image",
    "gen-image-fast": "$gen-image-fast",
    "gen-image-high-quality": "$gen-image-high-quality",
}

EXTRACT_TALENT_TO_MODEL: dict[str, str] = {
    "pdf-basic-text-extractor": "@default-text-from-pdf",
    "image-text-extractor": "@default-extract-image",
    "full-document-extractor": "@default-extract-document",
}


def _pipe_spec_to_toml(pipe_spec: PipeSpec) -> str:
    """Convert a PipeSpec to TOML string format.

    Args:
        pipe_spec: The validated PipeSpec to convert.

    Returns:
        TOML string representation of the pipe.
    """
    doc = tomlkit.document()
    pipe_item_table = tomlkit.table()

    # Add type
    pipe_item_table.add("type", pipe_spec.type)

    # Add description
    pipe_item_table.add("description", pipe_spec.description)

    # Add inputs as inline table
    if pipe_spec.inputs:
        inputs_inline = tomlkit.inline_table()
        for input_name, input_concept in pipe_spec.inputs.items():
            inputs_inline.append(input_name, input_concept)
        pipe_item_table.add("inputs", inputs_inline)

    # Add output
    pipe_item_table.add("output", pipe_spec.output)

    # Add type-specific fields
    _add_type_specific_fields(pipe_spec, pipe_item_table)

    # Build the nested structure: [pipe.pipe_code]
    pipe_section = tomlkit.table()
    pipe_section.add(pipe_spec.pipe_code, pipe_item_table)
    doc.add("pipe", pipe_section)
    return tomlkit.dumps(doc)


def _add_type_specific_fields(pipe_spec: PipeSpec, pipe_table: tomlkit.TOMLDocument | tomlkit.items.Table) -> None:  # type: ignore[name-defined]
    """Add type-specific fields to the pipe TOML table.

    Args:
        pipe_spec: The pipe spec with type-specific fields.
        pipe_table: The TOML table to add fields to.
    """
    if isinstance(pipe_spec, PipeLLMSpec):
        # Convert llm_talent to model preset using static mappings
        model_preset = LLM_TALENT_TO_MODEL.get(pipe_spec.llm_talent, "$writing-creative")
        pipe_table.add("model", model_preset)
        if pipe_spec.system_prompt:
            pipe_table.add("system_prompt", pipe_spec.system_prompt)
        if pipe_spec.prompt:
            pipe_table.add("prompt", pipe_spec.prompt)

    elif isinstance(pipe_spec, PipeComposeSpec):
        pipe_table.add("target_format", pipe_spec.target_format)
        pipe_table.add("template", pipe_spec.template)

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
        if pipe_spec.combined_output:
            pipe_table.add("combined_output", pipe_spec.combined_output)
        parallels_array = tomlkit.array()
        for parallel in pipe_spec.parallels:
            parallel_inline = tomlkit.inline_table()
            parallel_inline.append("pipe", parallel.pipe_code)
            parallel_inline.append("result", parallel.result)
            parallels_array.append(parallel_inline)
        pipe_table.add("parallels", parallels_array)

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
        # Convert extract_talent to model preset using static mappings
        model_preset = EXTRACT_TALENT_TO_MODEL.get(pipe_spec.extract_talent, "@default-extract-document")
        pipe_table.add("model", model_preset)

    elif isinstance(pipe_spec, PipeImgGenSpec):
        # Convert img_gen_talent to model preset using static mappings
        model_preset = IMG_GEN_TALENT_TO_MODEL.get(pipe_spec.img_gen_talent, "$gen-image")
        pipe_table.add("model", model_preset)
        pipe_table.add("prompt", pipe_spec.prompt)

    elif isinstance(pipe_spec, PipeFuncSpec):
        pipe_table.add("function_name", pipe_spec.function_name)


def _parse_pipe_spec_from_json(pipe_type: str, spec_data: dict[str, Any]) -> PipeSpec:
    """Parse and validate a PipeSpec from JSON data.

    Args:
        pipe_type: The type of pipe (e.g., "PipeLLM", "PipeSequence").
        spec_data: Raw JSON data for the pipe spec.

    Returns:
        Validated PipeSpec instance of the correct type.

    Raises:
        ValueError: If the pipe type is invalid.
        ValidationError: If validation fails.
    """
    if pipe_type not in pipe_type_to_spec_class:
        valid_types = list(pipe_type_to_spec_class.keys())
        msg = f"Invalid pipe type '{pipe_type}'. Must be one of: {valid_types}"
        raise ValueError(msg)

    spec_class = pipe_type_to_spec_class[pipe_type]

    # Add type to spec_data if not present
    spec_data["type"] = pipe_type

    # Handle steps/parallels conversion - need to convert pipe to pipe_code
    if "steps" in spec_data:
        converted_steps = []
        for step in spec_data["steps"]:
            if "pipe" in step and "pipe_code" not in step:
                step["pipe_code"] = step.pop("pipe")
            converted_steps.append(step)
        spec_data["steps"] = converted_steps

    if "parallels" in spec_data:
        converted_parallels = []
        for parallel in spec_data["parallels"]:
            if "pipe" in parallel and "pipe_code" not in parallel:
                parallel["pipe_code"] = parallel.pop("pipe")
            converted_parallels.append(parallel)
        spec_data["parallels"] = converted_parallels

    # Handle expression -> jinja2_expression_template for PipeCondition
    if pipe_type == "PipeCondition" and "expression" in spec_data:
        if "jinja2_expression_template" not in spec_data:
            spec_data["jinja2_expression_template"] = spec_data.pop("expression")

    return spec_class.model_validate(spec_data)


def pipe_cmd(
    pipe_type: Annotated[
        str,
        typer.Option("--type", "-t", help=f"Pipe type. Must be one of: {PipeType.value_list()}"),
    ],
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
        "llm_talent": "CREATIVE_WRITER",
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

    # Validate and convert spec
    try:
        pipe_spec = _parse_pipe_spec_from_json(pipe_type, spec_data)
        toml_content = _pipe_spec_to_toml(pipe_spec)

        agent_success(
            {
                "success": True,
                "pipe_code": pipe_spec.pipe_code,
                "pipe_type": pipe_type,
                "toml": toml_content,
            }
        )

    except ValueError as exc:
        agent_error(str(exc), "ValueError", cause=exc)

    except ValidationError as exc:
        agent_error(format_pydantic_validation_error(exc), "ValidationError", cause=exc)

    except Exception as exc:
        agent_error(str(exc), type(exc).__name__, cause=exc)
