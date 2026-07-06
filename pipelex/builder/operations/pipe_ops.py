"""Core operations for pipe spec parsing and TOML generation."""

# tomlkit lacks type stubs; pydantic `model` field clashes with BaseModel namespace
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportAttributeAccessIssue=false

from typing import Any, cast

import tomlkit
from pydantic import ValidationError
from tomlkit.items import Table

from pipelex.builder.bundle_spec import SIGNATURE_ONLY_SPEC_KEYS
from pipelex.builder.pipe.exceptions import PipeSpecError
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
from pipelex.core.pipes.pipe_blueprint import (
    PIPE_SIGNATURE_TYPE_TAG,
    explicit_signature_tag_migration_message,
    normalize_typeless_signature_section,
)

# Aliases that agents may use instead of "pipe_code". First found is promoted when canonical key is absent; extras are dropped.
_PIPE_CODE_ALIASES = ("pipe", "the_pipe_code", "code", "name", "pipe_name", "pipe_ref")

# Aliases that agents may use instead of "output". First found is promoted when canonical key is absent; extras are dropped.
_OUTPUT_ALIASES = ("output_concept", "output_type")

# Aliases that agents may use instead of "prompt". First found is promoted when canonical key is absent; extras are dropped.
_PROMPT_ALIASES = ("prompt_template",)


def _normalize_sub_pipe_dict(data: dict[str, Any]) -> None:
    """Normalize a step/branch dict: resolve pipe_code aliases and drop extraneous fields."""
    _normalize_pipe_code_aliases(data)
    # Agents sometimes add "inputs" to individual steps — silently drop.
    # Step-level inputs are not supported; inputs set by the pipe definition.
    data.pop("inputs", None)


def _normalize_sub_pipe_list(raw_value: Any, *, field_name: str) -> list[dict[str, Any]]:
    """Validate and normalize a raw ``steps`` / ``branches`` value into a list of step dicts.

    Each entry is copied (to avoid mutating the caller's nested dicts) and passed
    through :func:`_normalize_sub_pipe_dict`. A non-list ``raw_value`` or a
    non-mapping entry is a caller-input fault, raised as a typed ``PipeSpecError``
    before validation rather than leaking a bare ``TypeError`` / ``ValueError``.
    """
    if not isinstance(raw_value, list):
        msg = f"Pipe spec '{field_name}' must be a list of step mappings, got {type(raw_value).__name__}"
        raise PipeSpecError(msg)
    normalized: list[dict[str, Any]] = []
    for entry in cast("list[Any]", raw_value):
        if not isinstance(entry, dict):
            msg = f"Each entry in pipe spec '{field_name}' must be a mapping, got {type(entry).__name__}"
            raise PipeSpecError(msg)
        entry_copy = dict(cast("dict[str, Any]", entry))
        _normalize_sub_pipe_dict(entry_copy)
        normalized.append(entry_copy)
    return normalized


def _normalize_pipe_code_aliases(data: dict[str, Any]) -> None:
    """Convert any alias of ``pipe_code`` to the canonical field name, in-place."""
    for alias in _PIPE_CODE_ALIASES:
        if alias in data:
            if "pipe_code" not in data:
                data["pipe_code"] = data.pop(alias)
            else:
                data.pop(alias)


def _normalize_prompt_aliases(data: dict[str, Any]) -> None:
    """Convert any alias of ``prompt`` to the canonical field name, in-place."""
    for alias in _PROMPT_ALIASES:
        if alias in data:
            if "prompt" not in data:
                data["prompt"] = data.pop(alias)
            else:
                data.pop(alias)


def _normalize_output(data: dict[str, Any]) -> Any | None:
    """Canonicalize output authoring aliases in-place: promote ``output_concept`` / ``output_type`` →
    ``output``, and flatten a dict-shaped ``output`` to its concept string.

    Returns the displaced original ``output`` value when an alias overrode an existing ``output`` (so a
    typed caller can retry with the alias then fall back to the original), else ``None``. Runs for both
    the typeless-signature and typed paths so the same authoring conveniences apply to signatures.
    """
    # Accept output aliases (e.g. "output_concept", "output_type") for "output".
    # When both "output" and an alias coexist, try the alias value first (agents often put
    # the correct concept name in the alias), falling back to the original "output" value.
    output_fallback: Any | None = None
    for output_alias in _OUTPUT_ALIASES:
        if output_alias not in data:
            continue
        alias_value = data.pop(output_alias)
        if "output" not in data:
            data["output"] = alias_value
        else:
            output_fallback = data["output"]
            data["output"] = alias_value
        # First alias wins — drop any remaining aliases without using them.
        for remaining_alias in _OUTPUT_ALIASES:
            data.pop(remaining_alias, None)
        break

    # Accept output as dict → extract the concept string
    # Agents sometimes structure the output like inputs (as a dict).
    # Handle {"type": "ConceptName"} and single-item dicts like {"result": "Text"}.
    if "output" in data and isinstance(data["output"], dict):
        output_dict: dict[str, Any] = data["output"]
        if "concept_ref" in output_dict:
            data["output"] = output_dict["concept_ref"]
        elif "type" in output_dict:
            data["output"] = output_dict["type"]
        elif len(output_dict) == 1:
            data["output"] = next(iter(output_dict.values()))
    return output_fallback


def parse_pipe_spec(spec_data: Any, *, pipe_type: str | None) -> PipeSpec:
    """Parse and validate a PipeSpec from JSON-like data.

    Args:
        spec_data: Raw data for the pipe spec (untrusted JSON-like input).
        pipe_type: The type of pipe (e.g., "PipeLLM", "PipeSequence"), or ``None`` when the caller
            supplied no type. A typeless spec is a signature when it declares only the contract
            (``description``, ``inputs``, ``output``, ``signature_for``), else a teaching error. An
            explicit ``"PipeSignature"`` is rejected with the migration error — a signature has no type.

    Returns:
        Validated PipeSpec instance of the correct type.

    Raises:
        ValueError: If the pipe type is invalid, or the retired ``"PipeSignature"`` tag is passed, or a
            typeless spec declares more than the contract.
        PipeSpecError: If the top-level value is not a mapping, ``steps`` /
            ``branches`` is not a list, or an entry within them is not a mapping.
            Carries the INPUT error domain.
        ValidationError: If Pydantic validation of the assembled spec fails.
    """
    # Validate the top-level shape first so a non-mapping caller input (scalar / list / None) surfaces
    # as a typed, INPUT-domain PipeSpecError instead of a bare TypeError / ValueError, and so the
    # typeless-signature routing below can operate on a dict.
    if not isinstance(spec_data, dict):
        msg = f"Pipe spec must be a mapping, got {type(spec_data).__name__}"
        raise PipeSpecError(msg)
    # Work on a copy to avoid mutating the caller's dict.
    spec_data = dict(cast("dict[str, Any]", spec_data))

    # Canonicalize pipe_code aliases up front so the typeless-signature routing and the migration
    # message both see the real pipe code.
    _normalize_pipe_code_aliases(spec_data)

    # Canonicalize output authoring aliases (output_concept/output_type, dict output) up front so both
    # the typeless-signature path and every typed pipe see a canonical `output` — a signature keeps the
    # same authoring conveniences as typed pipes. The typed path reuses the returned fallback for its
    # retry-then-fall-back below; the typeless path takes the canonical value directly.
    output_fallback = _normalize_output(spec_data)

    # A signature is typeless. Reject the retired explicit `type = "PipeSignature"` tag, and route a
    # typeless contract-only spec to `PipeSignatureSpec` via the shared normalizer (which injects the
    # internal tag, or raises the same teaching error as the bundle layer for a stray field). This
    # mirrors `PipelexBundleSpec.validate_pipe_keys` for the single-pipe authoring surface.
    if pipe_type == PIPE_SIGNATURE_TYPE_TAG:
        raise ValueError(explicit_signature_tag_migration_message(spec_data.get("pipe_code")))
    if pipe_type is None:
        normalized = normalize_typeless_signature_section(spec_data.get("pipe_code"), pipe_section=spec_data, allowed_keys=SIGNATURE_ONLY_SPEC_KEYS)
        return PipeSignatureSpec.model_validate(normalized)

    if pipe_type not in pipe_type_to_spec_class:
        valid_types = list(pipe_type_to_spec_class.keys())
        msg = f"Invalid pipe type '{pipe_type}'. Must be one of: {valid_types}"
        raise ValueError(msg)

    spec_class = pipe_type_to_spec_class[pipe_type]

    # Add type to spec_data
    spec_data["type"] = pipe_type

    # Accept common aliases for "prompt" (e.g. "prompt_template")
    _normalize_prompt_aliases(spec_data)

    # Handle steps/branches conversion — normalize aliases and drop unknown fields.
    # Deep-copy nested dicts to avoid mutating caller's nested structures.
    # Validate the raw shape before iterating so a malformed ``steps`` / ``branches``
    # surfaces as a typed, INPUT-domain PipeSpecError instead of a bare TypeError /
    # ValueError (which the caller cannot tell apart from a real programming bug).
    if "steps" in spec_data:
        spec_data["steps"] = _normalize_sub_pipe_list(spec_data["steps"], field_name="steps")

    if "branches" in spec_data:
        spec_data["branches"] = _normalize_sub_pipe_list(spec_data["branches"], field_name="branches")

    # Handle expression -> jinja2_expression_template for PipeCondition
    if pipe_type == "PipeCondition" and "expression" in spec_data:
        if "jinja2_expression_template" not in spec_data:
            spec_data["jinja2_expression_template"] = spec_data.pop("expression")
        else:
            spec_data.pop("expression")

    # When an output alias conflicted with an existing "output" (see `_normalize_output` above), try the
    # alias value first and fall back to the original value if validation fails.
    if output_fallback is not None:
        try:
            return spec_class.model_validate(spec_data)
        except ValidationError:
            spec_data["output"] = output_fallback
    return spec_class.model_validate(spec_data)


def add_type_specific_fields(pipe_spec: PipeSpec, *, pipe_table: Table) -> None:
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

    elif isinstance(pipe_spec, PipeSignatureSpec):
        # A signature is typeless, but the optional `signature_for` hint still round-trips. Mirrors
        # `pipe_cmd._add_type_specific_fields` so the two TOML renderers stay faithful copies.
        if pipe_spec.signature_for is not None:
            pipe_table.add("signature_for", pipe_spec.signature_for)


def pipe_spec_to_toml(pipe_spec: PipeSpec) -> str:
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
    add_type_specific_fields(pipe_spec, pipe_table=pipe_item_table)

    # Build the nested structure: [pipe.pipe_code]
    pipe_section = tomlkit.table()
    pipe_section.add(pipe_spec.pipe_code, pipe_item_table)
    doc.add("pipe", pipe_section)
    return tomlkit.dumps(doc)
