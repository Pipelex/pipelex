"""Core operations for pipe spec parsing and TOML generation."""

# tomlkit lacks type stubs; pydantic `model` field clashes with BaseModel namespace
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportAttributeAccessIssue=false

from typing import Any

import tomlkit
from tomlkit.items import Table

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
from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.builder.pipe.pipe_spec_map import pipe_type_to_spec_class


def parse_pipe_spec(pipe_type: str, spec_data: dict[str, Any]) -> PipeSpec:
    """Parse and validate a PipeSpec from JSON-like data.

    Args:
        pipe_type: The type of pipe (e.g., "PipeLLM", "PipeSequence").
        spec_data: Raw data for the pipe spec.

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

    # Work on a copy to avoid mutating the caller's dict
    spec_data = dict(spec_data)

    # Add type to spec_data if not present
    spec_data["type"] = pipe_type

    # Accept common aliases for "pipe_code"
    for alias in ("the_pipe_code", "code", "name", "pipe_name", "pipe_ref"):
        if alias in spec_data:
            if "pipe_code" not in spec_data:
                spec_data["pipe_code"] = spec_data.pop(alias)
            else:
                spec_data.pop(alias)

    # Handle steps/branches conversion - need to convert pipe to pipe_code
    # Deep-copy nested dicts to avoid mutating caller's nested structures
    if "steps" in spec_data:
        converted_steps = []
        for step in spec_data["steps"]:
            step = dict(step)
            if "pipe" in step and "pipe_code" not in step:
                step["pipe_code"] = step.pop("pipe")
            converted_steps.append(step)
        spec_data["steps"] = converted_steps

    if "branches" in spec_data:
        converted_branches = []
        for branch in spec_data["branches"]:
            branch = dict(branch)
            if "pipe" in branch and "pipe_code" not in branch:
                branch["pipe_code"] = branch.pop("pipe")
            converted_branches.append(branch)
        spec_data["branches"] = converted_branches

    # Handle expression -> jinja2_expression_template for PipeCondition
    if pipe_type == "PipeCondition" and "expression" in spec_data:
        if "jinja2_expression_template" not in spec_data:
            spec_data["jinja2_expression_template"] = spec_data.pop("expression")
        else:
            spec_data.pop("expression")

    # Accept output as dict → extract the concept string
    # Agents sometimes structure the output like inputs (as a dict).
    # Handle {"type": "ConceptName"} and single-item dicts like {"result": "Text"}.
    if "output" in spec_data and isinstance(spec_data["output"], dict):
        output_dict: dict[str, Any] = spec_data["output"]
        if "type" in output_dict:
            spec_data["output"] = output_dict["type"]
        elif len(output_dict) == 1:
            spec_data["output"] = next(iter(output_dict.values()))

    return spec_class.model_validate(spec_data)


def add_type_specific_fields(pipe_spec: PipeSpec, pipe_table: Table) -> None:
    """Add type-specific fields to the pipe TOML table.

    Args:
        pipe_spec: The pipe spec with type-specific fields.
        pipe_table: The TOML table to add fields to.
    """
    if isinstance(pipe_spec, PipeLLMSpec):
        if pipe_spec.model:
            pipe_table.add("model", pipe_spec.model)
        if pipe_spec.system_prompt:
            pipe_table.add("system_prompt", pipe_spec.system_prompt)
        if pipe_spec.prompt:
            pipe_table.add("prompt", pipe_spec.prompt)

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
        if pipe_spec.max_page_images is not None:
            pipe_table.add("max_page_images", pipe_spec.max_page_images)
        if pipe_spec.page_views is not None:
            pipe_table.add("page_views", pipe_spec.page_views)

    elif isinstance(pipe_spec, PipeSearchSpec):
        if pipe_spec.model:
            pipe_table.add("model", pipe_spec.model)
        pipe_table.add("prompt", pipe_spec.prompt)
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

    elif isinstance(pipe_spec, PipeImgGenSpec):
        if pipe_spec.model:
            pipe_table.add("model", pipe_spec.model)
        pipe_table.add("prompt", pipe_spec.prompt)

    elif isinstance(pipe_spec, PipeFuncSpec):
        pipe_table.add("function_name", pipe_spec.function_name)


def pipe_spec_to_toml(pipe_spec: PipeSpec) -> str:
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
    add_type_specific_fields(pipe_spec, pipe_item_table)

    # Build the nested structure: [pipe.pipe_code]
    pipe_section = tomlkit.table()
    pipe_section.add(pipe_spec.pipe_code, pipe_item_table)
    doc.add("pipe", pipe_section)
    return tomlkit.dumps(doc)
