"""Core operations for pipe spec parsing and TOML generation."""

# pyright: reportUnknownMemberType=false
# pyright: reportArgumentType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnusedExcept=false
# mypy: disable-error-code="arg-type,no-any-return,attr-defined"

from typing import Any

import tomlkit

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
from pipelex.builder.talents.extract_talent import ExtractTalent
from pipelex.builder.talents.img_gen_talent import ImgGenTalent
from pipelex.builder.talents.llm_talent import LLMTalent

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

# Reverse mappings: preset name → talent name (for fuzzy resolution)
MODEL_TO_LLM_TALENT: dict[str, str] = {}
for _talent, _preset in LLM_TALENT_TO_MODEL.items():
    MODEL_TO_LLM_TALENT[_preset] = _talent
    MODEL_TO_LLM_TALENT[_preset.lstrip("$@")] = _talent

MODEL_TO_IMG_GEN_TALENT: dict[str, str] = {}
for _talent, _preset in IMG_GEN_TALENT_TO_MODEL.items():
    MODEL_TO_IMG_GEN_TALENT[_preset] = _talent
    MODEL_TO_IMG_GEN_TALENT[_preset.lstrip("$@")] = _talent

MODEL_TO_EXTRACT_TALENT: dict[str, str] = {}
for _talent, _preset in EXTRACT_TALENT_TO_MODEL.items():
    MODEL_TO_EXTRACT_TALENT[_preset] = _talent
    MODEL_TO_EXTRACT_TALENT[_preset.lstrip("$@")] = _talent

# Maps pipe types to their talent field names and valid values.
# Used to enrich validation errors with field_hints so the agent knows
# what values are valid when a talent field is missing or wrong.
PIPE_TYPE_TALENT_HINTS: dict[str, dict[str, list[str]]] = {
    "PipeLLM": {"llm_talent": [talent.value for talent in LLMTalent]},
    "PipeExtract": {"extract_talent": [talent.value for talent in ExtractTalent]},
    "PipeImgGen": {"img_gen_talent": [talent.value for talent in ImgGenTalent]},
}


def resolve_talent_value(pipe_type: str, raw_value: Any) -> Any:
    """Attempt to resolve a talent value, accepting preset names as aliases."""
    if not isinstance(raw_value, str):
        return raw_value
    reverse_maps: dict[str, dict[str, str]] = {
        "PipeLLM": MODEL_TO_LLM_TALENT,
        "PipeImgGen": MODEL_TO_IMG_GEN_TALENT,
        "PipeExtract": MODEL_TO_EXTRACT_TALENT,
    }
    reverse_map = reverse_maps.get(pipe_type)
    if not reverse_map:
        return raw_value
    # If it's already a valid talent, return as-is
    # Otherwise try reverse-mapping from preset
    resolved = reverse_map.get(raw_value)
    if resolved:
        return resolved
    return raw_value  # Let Pydantic validation handle the error


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

    # Add type to spec_data if not present
    spec_data["type"] = pipe_type

    # Accept common aliases for "pipe_code"
    for alias in ("code", "the_pipe_code", "name"):
        if alias in spec_data:
            if "pipe_code" not in spec_data:
                spec_data["pipe_code"] = spec_data.pop(alias)
            else:
                spec_data.pop(alias)

    # Accept generic talent aliases and map to the type-specific field
    talent_aliases = ("talent_name", "talent")
    pipe_type_to_talent_field: dict[str, str] = {
        "PipeLLM": "llm_talent",
        "PipeExtract": "extract_talent",
        "PipeImgGen": "img_gen_talent",
        "PipeSearch": "search_talent",
    }
    talent_field = pipe_type_to_talent_field.get(pipe_type)
    if talent_field:
        for alias in talent_aliases:
            if alias in spec_data:
                if talent_field not in spec_data:
                    spec_data[talent_field] = spec_data.pop(alias)
                else:
                    spec_data.pop(alias)

    # Handle steps/branches conversion - need to convert pipe to pipe_code
    if "steps" in spec_data:
        converted_steps = []
        for step in spec_data["steps"]:
            if "pipe" in step and "pipe_code" not in step:
                step["pipe_code"] = step.pop("pipe")
            converted_steps.append(step)
        spec_data["steps"] = converted_steps

    if "branches" in spec_data:
        converted_branches = []
        for branch in spec_data["branches"]:
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

    # Resolve preset names to talent names (tolerance for agent mistakes)
    talent_field = pipe_type_to_talent_field.get(pipe_type)
    if talent_field and talent_field in spec_data:
        spec_data[talent_field] = resolve_talent_value(pipe_type, spec_data[talent_field])

    # Accept output as dict with "type" key → extract the type string
    if "output" in spec_data and isinstance(spec_data["output"], dict):
        if "type" in spec_data["output"]:
            spec_data["output"] = spec_data["output"]["type"]

    return spec_class.model_validate(spec_data)


def add_type_specific_fields(pipe_spec: PipeSpec, pipe_table: tomlkit.TOMLDocument | tomlkit.items.Table) -> None:  # type: ignore[name-defined]
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
