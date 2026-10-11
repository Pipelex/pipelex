"""Generator for JSON Schema from MTHDS blueprint classes.

Produces a Taplo-compatible JSON Schema (Draft 4) from PipelexBundleBlueprint's
Pydantic v2 model schema. The generated schema enables IDE validation and
autocompletion for .mthds files in the vscode-pipelex extension.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, cast, get_args

from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipeBlueprintUnion, PipelexBundleBlueprint
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_machinery.validation import (
    INPUT_NAME_PATTERN,
    PARALLEL_BRANCH_BATCH_OVER_PATTERN,
    RESERVED_NAME_PATTERN,
    SEQUENCE_STEP_BATCH_OVER_PATTERN,
    STORED_NAME_PATTERN,
)
from pipelex.pipe_operators.judge.pipe_judge_blueprint import QUESTION_KIND_FIELDS, JudgeQuestionBlueprint, JudgeRatingLevel, PipeJudgeBlueprint
from pipelex.pipe_signature.pipe_signature_blueprint import PipeSignatureBlueprint
from pipelex.tools.misc.package_utils import get_package_version

if TYPE_CHECKING:
    from collections.abc import Callable

# Fields that are injected at load time, never written by users in .mthds files
_INTERNAL_FIELDS = {"source"}

# Fields that are technical union discriminators, not user-facing
_PIPE_INTERNAL_FIELDS = {"pipe_category"}

# Pipe definition names (as they appear in Pydantic schema $defs), derived from the
# discriminated union so a newly added pipe type is covered automatically — no drift.
# PipeBlueprintUnion is `Annotated[A | B | ..., Field(discriminator="type")]`:
# get_args(...)[0] is the Union, and get_args(union) yields the member classes, whose
# __name__ matches the Pydantic $defs key.
_PIPE_DEFINITION_NAMES: frozenset[str] = frozenset(member.__name__ for member in get_args(get_args(PipeBlueprintUnion)[0]))

# The signature arm is the one typeless arm: `_normalize_type_on_pipe_definitions` REMOVES `type` from
# it entirely, so a contract-only table with no `type` matches it and an explicit `type = "PipeSignature"`
# is rejected (extra property under the arm's `additionalProperties: false`).
_SIGNATURE_DEFINITION_NAME = PipeSignatureBlueprint.__name__

# The definition a PipeParallel branch takes: `SubPipeBlueprint`'s, with a `batch_over` that is never dotted
# (`_constrain_batch_over`). No Python class carries the name, since steps and branches share one blueprint.
_PARALLEL_BRANCH_DEFINITION_NAME = "ParallelBranchBlueprint"

# The fields of a pipe step, and of a PipeParallel branch, naming a slot of working memory the step stores a value under: each
# is a stored name, held to the input-name grammar (`_constrain_stored_names`).
_PIPE_STEP_STORED_NAME_FIELDS: tuple[str, ...] = ("result", "batch_as")


def generate_mthds_schema() -> dict[str, Any]:
    """Generate a Taplo-compatible JSON Schema for .mthds files.

    Uses PipelexBundleBlueprint.model_json_schema() as the base, then applies
    post-processing steps to make it compatible with Taplo (JSON Schema Draft 4)
    and match the user-facing MTHDS file format.

    Returns:
        A JSON Schema dict ready to be serialized to JSON.
    """
    schema = PipelexBundleBlueprint.model_json_schema(
        by_alias=True,
        mode="validation",
    )

    schema = _remove_internal_fields(schema)
    schema = _promote_schema_required_fields(schema)
    schema = _normalize_type_on_pipe_definitions(schema)
    schema = _convert_to_draft4(schema)
    schema = _patch_construct_schema(schema)
    schema = _constrain_input_names(schema)
    # Before `_constrain_batch_over`, so the branch definition it copies from the pipe step's carries these constraints too.
    schema = _constrain_stored_names(schema)
    schema = _constrain_batch_over(schema)
    schema = _constrain_rating_levels(schema)
    schema = _constrain_judge_questions(schema)

    return _add_taplo_metadata(schema)


def _remove_internal_fields(schema: dict[str, Any]) -> dict[str, Any]:
    """Remove fields that users never write in .mthds files.

    - `source` is removed from all definitions (injected at load time)
    - `pipe_category` is removed from pipe definitions (union discriminator)
    """
    schema = copy.deepcopy(schema)
    defs_key = "$defs" if "$defs" in schema else "definitions"
    definitions = schema.get(defs_key, {})

    # Remove 'source' from root properties
    root_props = schema.get("properties", {})
    for field_name in _INTERNAL_FIELDS:
        root_props.pop(field_name, None)
    _remove_from_required(schema, field_names=_INTERNAL_FIELDS)

    # Remove internal fields from all definitions
    for def_name, def_schema in definitions.items():
        props = def_schema.get("properties", {})
        for field_name in _INTERNAL_FIELDS:
            props.pop(field_name, None)
        _remove_from_required(def_schema, field_names=_INTERNAL_FIELDS)

        # Remove pipe_category only from pipe blueprint definitions
        if def_name in _PIPE_DEFINITION_NAMES:
            for field_name in _PIPE_INTERNAL_FIELDS:
                props.pop(field_name, None)
            _remove_from_required(def_schema, field_names=_PIPE_INTERNAL_FIELDS)

    return schema


def _remove_from_required(schema_obj: dict[str, Any], *, field_names: set[str]) -> None:
    """Remove field names from a schema object's 'required' list."""
    required = schema_obj.get("required")
    if required is not None:
        schema_obj["required"] = [req for req in required if req not in field_names]
        if not schema_obj["required"]:
            del schema_obj["required"]


def _promote_schema_required_fields(schema: dict[str, Any]) -> dict[str, Any]:
    """Promote fields marked with x-schema-required into their parent's required array.

    Fields annotated with WithJsonSchema({"x-schema-required": True}) are collected
    and added to the parent schema's `required` list. The marker is then removed
    from the property schema so it doesn't leak into the final output.
    """
    schema = copy.deepcopy(schema)
    defs_key = "$defs" if "$defs" in schema else "definitions"

    for schema_obj in [schema, *schema.get(defs_key, {}).values()]:
        properties = schema_obj.get("properties", {})
        promoted: list[str] = []
        for field_name, field_schema in properties.items():
            if field_schema.get("x-schema-required") is True:
                promoted.append(field_name)
                del field_schema["x-schema-required"]
        if promoted:
            required = schema_obj.get("required", [])
            for field_name in promoted:
                if field_name not in required:
                    required.append(field_name)
            schema_obj["required"] = required

    return schema


def _normalize_type_on_pipe_definitions(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize the `type` discriminator across pipe blueprint definitions for Draft-4 `oneOf`.

    The runtime union disambiguates with `Field(discriminator="type")`, but `_convert_to_draft4`
    strips `discriminator` (Draft 4 has none), so the arms must self-disambiguate. Two shapes:

    - **Concrete arms** declare `type` as a Literal with a default (e.g.
      `type: Literal["PipeLLM"] = "PipeLLM"`), so Pydantic omits it from `required`. We force `type`
      into `required` so a typed table matches exactly one arm and a table lacking `type` fails these
      arms cleanly instead of ambiguously multi-matching.
    - **The signature arm** is the one typeless arm: we REMOVE `type` from it entirely (property and
      `required`). Every pipe def has `additionalProperties: false`, so the signature arm becomes
      `{description, output, inputs?, signature_for?}` with no `type`. A typeless contract table
      therefore matches only this arm (concrete arms require `type`); a table with a *concrete* `type`
      fails this arm (extra `type` property) and matches only its own arm; a typeless table with a
      stray field matches no arm; and an explicit `type = "PipeSignature"` is rejected here too (extra
      `type` property) — the language surface no longer accepts the retired tag.
    """
    schema = copy.deepcopy(schema)
    defs_key = "$defs" if "$defs" in schema else "definitions"
    definitions = schema.get(defs_key, {})

    for def_name in _PIPE_DEFINITION_NAMES:
        def_schema = definitions.get(def_name)
        if def_schema is None:
            continue
        properties = def_schema.get("properties", {})
        if def_name == _SIGNATURE_DEFINITION_NAME:
            # Typeless arm: no `type` at all, so an explicit tag is rejected as an extra property.
            properties.pop("type", None)
            _remove_from_required(def_schema, field_names={"type"})
            continue
        if "type" not in properties:
            continue
        required = def_schema.setdefault("required", [])
        if "type" not in required:
            required.append("type")

    return schema


def _convert_to_draft4(schema: dict[str, Any]) -> dict[str, Any]:
    """Convert JSON Schema from Pydantic's Draft 2020-12 to Draft 4 for Taplo.

    - Renames `$defs` to `definitions`
    - Converts `const` to single-value `enum`
    - Removes `discriminator` (not in Draft 4)
    - Fixes `$ref` paths from `#/$defs/` to `#/definitions/`
    - Converts `exclusiveMinimum`/`exclusiveMaximum` from number (Draft 6+) to boolean (Draft 4)
    """
    schema = copy.deepcopy(schema)

    # Rename $defs to definitions
    if "$defs" in schema:
        schema["definitions"] = schema.pop("$defs")

    # Walk the schema tree to apply conversions
    _walk_schema(schema, visitor=_draft4_visitor)

    return schema


def _draft4_visitor(node: dict[str, Any]) -> None:
    """Visitor that converts Draft 2020-12 constructs to Draft 4."""
    # Convert const to single-value enum
    if "const" in node:
        node["enum"] = [node.pop("const")]

    # Remove discriminator (not in Draft 4)
    node.pop("discriminator", None)

    # Fix $ref paths
    if "$ref" in node:
        ref_value = node["$ref"]
        if isinstance(ref_value, str) and "#/$defs/" in ref_value:
            node["$ref"] = ref_value.replace("#/$defs/", "#/definitions/")

    # Convert exclusiveMinimum/exclusiveMaximum from Draft 6+ (number) to Draft 4 (boolean)
    # Draft 6+: "exclusiveMinimum": 0  →  Draft 4: "minimum": 0, "exclusiveMinimum": true
    if "exclusiveMinimum" in node and not isinstance(node["exclusiveMinimum"], bool):
        node["minimum"] = node["exclusiveMinimum"]
        node["exclusiveMinimum"] = True
    if "exclusiveMaximum" in node and not isinstance(node["exclusiveMaximum"], bool):
        node["maximum"] = node["exclusiveMaximum"]
        node["exclusiveMaximum"] = True


def _patch_construct_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Patch ConstructBlueprint definition to match user-facing MTHDS format.

    In .mthds files, construct fields are written directly at root level:
        [pipe.my_pipe.construct]
        field_a = "value"
        field_b = { from = "var_name" }

    But the Pydantic model wraps them in a `fields` dict. This patch replaces
    the ConstructBlueprint definition with one that uses `additionalProperties`
    to accept arbitrary field names with field-value schemas.

    Also replaces ConstructFieldBlueprint with a user-facing schema that accepts
    the raw MTHDS formats: raw values, {from: str}, {template: str}, or nested constructs.
    """
    schema = copy.deepcopy(schema)
    definitions = schema.get("definitions", {})

    # Build the user-facing field value schema (what goes in each construct field)
    construct_field_schema = _build_construct_field_schema()

    # Replace ConstructBlueprint with MTHDS-format schema
    if "ConstructBlueprint" in definitions:
        definitions["ConstructBlueprint"] = {
            "title": "ConstructBlueprint",
            "description": "Construct section defining how to compose a StructuredContent from working memory fields.",
            "type": "object",
            "additionalProperties": construct_field_schema,
            "minProperties": 1,
        }

    # Replace ConstructFieldBlueprint with user-facing schema
    if "ConstructFieldBlueprint" in definitions:
        definitions["ConstructFieldBlueprint"] = {
            "title": "ConstructFieldBlueprint",
            **construct_field_schema,
        }

    return schema


def _constrain_input_names(schema: dict[str, Any]) -> dict[str, Any]:
    """Constrain every input name to the plain-name grammar, so a structural check refuses a dotted one.

    An input name is a plain snake_case identifier (`INPUT_NAME_PATTERN`), on every pipe's `inputs` keys
    and on a PipeBatch's `input_list_name`; the runtime refuses anything else as `invalid_input_name`, and
    this makes the schema refuse it first, which is what that error type's `fails_at = "schema"` records.

    The keys are constrained with `patternProperties` plus `additionalProperties: false` rather than with
    `propertyNames`: the schema is Draft 4, which has no `propertyNames`, and a Draft-4 validator such as
    plxt's ignores the keyword silently. Moving the value schema under the pattern says the same thing in
    every draft: a key matching the pattern takes the slot schema, and any other key is refused.
    """
    schema = copy.deepcopy(schema)
    definitions = schema.get("definitions", {})

    for def_name in _PIPE_DEFINITION_NAMES:
        inputs_schema = definitions.get(def_name, {}).get("properties", {}).get("inputs")
        if inputs_schema is None:
            continue
        for arm in inputs_schema.get("anyOf", [inputs_schema]):
            if arm.get("type") != "object" or "additionalProperties" not in arm:
                continue
            arm["patternProperties"] = {INPUT_NAME_PATTERN: arm.pop("additionalProperties")}
            arm["additionalProperties"] = False

    input_list_name_schema = definitions.get(PipeBatchBlueprint.__name__, {}).get("properties", {}).get("input_list_name")
    if input_list_name_schema is not None:
        input_list_name_schema["pattern"] = INPUT_NAME_PATTERN

    return schema


def _constrain_stored_names(schema: dict[str, Any]) -> dict[str, Any]:
    """Hold every stored name to the input-name grammar, and keep a plain `batch_over` off the reserved prefix, as the runtime does.

    A pipe step's `result` and `batch_as`, the same fields on a PipeParallel branch, and a PipeBatch's `input_item_name` are
    stored names: a step stores a value under each for a pipe to read through an input, so each takes the plain input-name
    grammar (`STORED_NAME_PATTERN`), as a binding step's `result` does through its own field. The runtime refuses any other
    form as `invalid_input_name` when the bundle is parsed, which keeps that error type's `fails_at = "schema"` true, and no
    name of that grammar takes the `_bound_` prefix the runtime reserves for the bound list of a dotted `batch_over`, being
    never underscore-led. A plain `batch_over` reads a name rather than storing one, so no such grammar holds it, and it is
    kept off the prefix by a Draft-4 `not` holding a `pattern` on its string arm: a negative lookahead in the pattern itself
    would say the same, but not every validator's regex engine has one, while every Draft-4 validator applies `not`, plxt's
    included. `_constrain_batch_over` gives it its path grammar besides.
    """
    schema = copy.deepcopy(schema)
    definitions = schema.get("definitions", {})
    pipe_step_properties = definitions.get(SubPipeBlueprint.__name__, {}).get("properties", {})
    for field_name in _PIPE_STEP_STORED_NAME_FIELDS:
        _set_string_arm_constraint(field_schema=pipe_step_properties.get(field_name), constraint={"pattern": STORED_NAME_PATTERN})
    _set_string_arm_constraint(field_schema=pipe_step_properties.get("batch_over"), constraint={"not": {"pattern": RESERVED_NAME_PATTERN}})
    batch_properties = definitions.get(PipeBatchBlueprint.__name__, {}).get("properties", {})
    _set_string_arm_constraint(field_schema=batch_properties.get("input_item_name"), constraint={"pattern": STORED_NAME_PATTERN})
    return schema


def _set_string_arm_constraint(*, field_schema: dict[str, Any] | None, constraint: dict[str, Any]) -> None:
    """Add a constraint to every string arm of a field, the field itself standing for its one arm when it has no `anyOf`."""
    if field_schema is None:
        return
    for arm in field_schema.get("anyOf", [field_schema]):
        if arm.get("type") == "string":
            arm.update(copy.deepcopy(constraint))


def _constrain_batch_over(schema: dict[str, Any]) -> dict[str, Any]:
    """Give `batch_over` its grammar: a dotted path on a PipeSequence step, and a name with no dot on a PipeParallel branch.

    A dotted `batch_over` binds the list at its path before batching over it, so on a sequence's pipe step it follows the
    binding path grammar, and a PipeParallel branch, which never binds, carries none: the runtime refuses both faults as
    `binding_step_invalid`, which this makes the schema refuse first. Both steps and branches parse into `SubPipeBlueprint`,
    so the branch takes a copy of its definition, `ParallelBranchBlueprint`, carrying the stricter `pattern`. Each is a
    `pattern` on the string arm of the field, which a Draft-4 validator such as plxt's applies.
    """
    schema = copy.deepcopy(schema)
    definitions = schema.get("definitions", {})
    pipe_step_schema = definitions.get(SubPipeBlueprint.__name__)
    branches_schema = definitions.get(PipeParallelBlueprint.__name__, {}).get("properties", {}).get("branches")
    if pipe_step_schema is None or branches_schema is None:
        return schema

    branch_schema = copy.deepcopy(pipe_step_schema)
    branch_schema["title"] = _PARALLEL_BRANCH_DEFINITION_NAME
    _set_batch_over_grammar(
        step_schema=pipe_step_schema,
        pattern=SEQUENCE_STEP_BATCH_OVER_PATTERN,
        description=(
            "The list in working memory to batch this step over, running the pipe once per item. A dotted path such as "
            "`catalog.pages` is a binding followed by a batch: the path is bound under a private name, by the rules of a binding "
            "step's `from`, and the step batches over the bound list, which must be a list."
        ),
    )
    _set_batch_over_grammar(
        step_schema=branch_schema,
        pattern=PARALLEL_BRANCH_BATCH_OVER_PATTERN,
        description=(
            "The list in working memory to batch this branch over, running the pipe once per item. A name with no dot: a branch "
            "never binds, so a list held in a field is bound by the calling sequence before the PipeParallel step."
        ),
    )
    definitions[_PARALLEL_BRANCH_DEFINITION_NAME] = branch_schema
    branches_schema["items"] = {"$ref": f"#/definitions/{_PARALLEL_BRANCH_DEFINITION_NAME}"}
    return schema


def _set_batch_over_grammar(*, step_schema: dict[str, Any], pattern: str, description: str) -> None:
    batch_over_schema = step_schema.get("properties", {}).get("batch_over")
    if batch_over_schema is None:
        return
    batch_over_schema["description"] = description
    for arm in batch_over_schema.get("anyOf", [batch_over_schema]):
        if arm.get("type") == "string":
            arm["pattern"] = pattern


def _constrain_rating_levels(schema: dict[str, Any]) -> dict[str, Any]:
    """Make the `levels` of a PipeJudge, and of each of its `questions`, label every level or none, as its load does.

    A level is a string, which is its description, or a closed `{label, description}` table, and the load
    refuses a scale labelling some of its levels only, since a `Rating` verdict reports the label of its
    level (`_validate_levels`). Draft 4 says so with two array shapes: strings and unlabelled tables, or
    labelled tables only. A table whose `label` is null counts as unlabelled, as it does at load.
    """
    schema = copy.deepcopy(schema)
    definitions = schema.get("definitions", {})
    if JudgeRatingLevel.__name__ not in definitions:
        return schema
    for definition_name in (PipeJudgeBlueprint.__name__, JudgeQuestionBlueprint.__name__):
        levels_schema = definitions.get(definition_name, {}).get("properties", {}).get("levels")
        if levels_schema is not None:
            _split_levels_scale(levels_schema=levels_schema, definition_name=definition_name)
    return schema


def _split_levels_scale(*, levels_schema: dict[str, Any], definition_name: str) -> None:
    level_ref = {"$ref": f"#/definitions/{JudgeRatingLevel.__name__}"}
    unlabelled_level = {"allOf": [level_ref, {"properties": {"label": {"type": "null"}}}]}
    labelled_level = {"allOf": [copy.deepcopy(level_ref), {"required": ["label"], "properties": {"label": {"type": "string"}}}]}
    # `levels` is optional, so its schema is an `anyOf` of the array and null: the array arm splits in two.
    arms: list[dict[str, Any]] = levels_schema.get("anyOf", [])
    array_arms = [arm for arm in arms if arm.get("type") == "array"]
    if len(array_arms) != 1:
        msg = f"Expected one array arm on {definition_name}.levels, found {len(array_arms)}"
        raise RuntimeError(msg)
    array_arm = array_arms[0]
    scale_arms = [
        {**array_arm, "items": {"anyOf": [{"type": "string"}, unlabelled_level]}},
        {**copy.deepcopy(array_arm), "items": labelled_level},
    ]
    levels_schema["anyOf"] = [scale_arm for arm in arms for scale_arm in (scale_arms if arm is array_arm else [arm])]


def _constrain_judge_questions(schema: dict[str, Any]) -> dict[str, Any]:
    """Make a PipeJudge ask one `question` or several `questions`, and keep the kind fields off one asking several, as its load does.

    Exactly one of `question` and `questions` is set, which Draft 4 says with a `oneOf` of the two
    `required`. A PipeJudge asking several sets `options`, `levels`, `criteria` and `threshold` on each
    question rather than on the pipe, which a `not` refuses, and its `questions` holds at least one
    question. The grammar of a question's key, a field name of the output's structure, is left to the
    load, since a Python identifier admits letters no portable pattern spells.
    """
    schema = copy.deepcopy(schema)
    judge_schema = schema.get("definitions", {}).get(PipeJudgeBlueprint.__name__)
    if judge_schema is None:
        return schema
    judge_schema["oneOf"] = [{"required": ["question"]}, {"required": ["questions"]}]
    judge_schema["not"] = {"required": ["questions"], "anyOf": [{"required": [kind_field]} for kind_field in QUESTION_KIND_FIELDS]}
    questions_schema = judge_schema.get("properties", {}).get("questions")
    if questions_schema is not None:
        for arm in questions_schema.get("anyOf", [questions_schema]):
            if arm.get("type") == "object":
                arm["minProperties"] = 1
    return schema


def _build_construct_field_schema() -> dict[str, Any]:
    """Build a JSON Schema for a construct field value as written in MTHDS files.

    Matches the parsing logic in ConstructFieldBlueprint.make_from_raw():
    - Raw values (string, number, boolean, array): fixed value
    - {from: str}: variable reference from working memory
    - {from: str, list_to_dict_keyed_by: str}: variable ref with dict conversion
    - {template: str}: Jinja2 template
    - Object with other keys: nested construct (recursive)
    """
    return {
        "anyOf": [
            {"type": "string", "description": "Fixed string value"},
            {"type": "number", "description": "Fixed numeric value"},
            {"type": "boolean", "description": "Fixed boolean value"},
            {"type": "array", "description": "Fixed array value"},
            {
                "type": "object",
                "description": "Variable reference from working memory",
                "properties": {
                    "from": {"type": "string", "description": "Path to variable in working memory"},
                    "list_to_dict_keyed_by": {
                        "type": "string",
                        "description": "Convert list to dict keyed by this attribute",
                    },
                },
                "required": ["from"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "description": "Jinja2 template string",
                "properties": {
                    "template": {"type": "string", "description": "Jinja2 template string (with $ preprocessing)"},
                },
                "required": ["template"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "description": "Nested construct",
                "additionalProperties": {"$ref": "#/definitions/ConstructFieldBlueprint"},
                "minProperties": 1,
            },
        ],
    }


def _add_taplo_metadata(schema: dict[str, Any]) -> dict[str, Any]:
    """Add Taplo-specific metadata and JSON Schema Draft 4 header.

    - Sets $schema to Draft 4
    - Adds title and version comment
    - Adds x-taplo.initKeys on the root schema for better IDE experience
    """
    schema = copy.deepcopy(schema)

    version = get_package_version()

    schema["$schema"] = "http://json-schema.org/draft-04/schema#"
    schema["title"] = "MTHDS File Schema"
    schema["$comment"] = f"Generated from PipelexBundleBlueprint v{version}. Do not edit manually."

    # x-taplo.initKeys suggests which keys to auto-insert when creating a new .mthds file
    schema["x-taplo"] = {
        "initKeys": ["domain"],
    }

    return schema


def _walk_schema(node: dict[str, Any] | list[Any] | Any, *, visitor: Callable[[dict[str, Any]], None]) -> None:
    """Recursively walk a JSON Schema tree, calling visitor on each dict node.

    Args:
        node: Current node in the schema tree
        visitor: Callable that receives each dict node for in-place modification
    """
    if isinstance(node, dict):
        typed_node = cast("dict[str, Any]", node)
        visitor(typed_node)
        for child_value in typed_node.values():
            _walk_schema(child_value, visitor=visitor)
    elif isinstance(node, list):
        typed_list = cast("list[Any]", node)
        for child_item in typed_list:
            _walk_schema(child_item, visitor=visitor)
