"""Generator for JSON Schema from MTHDS blueprint classes.

Produces a Taplo-compatible JSON Schema (Draft 4) from PipelexBundleBlueprint's
Pydantic v2 model schema. The generated schema enables IDE validation and
autocompletion for .mthds files in the vscode-pipelex extension.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.tools.misc.package_utils import get_package_version

# Fields that are injected at load time, never written by users in .mthds files
_INTERNAL_FIELDS = {"source"}

# Fields that are technical union discriminators, not user-facing
_PIPE_INTERNAL_FIELDS = {"pipe_category"}

# Pipe definition names (as they appear in Pydantic schema $defs)
_PIPE_DEFINITION_NAMES = {
    "PipeFuncBlueprint",
    "PipeImgGenBlueprint",
    "PipeComposeBlueprint",
    "PipeLLMBlueprint",
    "PipeExtractBlueprint",
    "PipeSearchBlueprint",
    "PipeStructureBlueprint",
    "PipeBatchBlueprint",
    "PipeConditionBlueprint",
    "PipeParallelBlueprint",
    "PipeSequenceBlueprint",
    "PipeSignatureBlueprint",
}


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
    schema = _convert_to_draft4(schema)
    schema = _patch_construct_schema(schema)

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
    _remove_from_required(schema, _INTERNAL_FIELDS)

    # Remove internal fields from all definitions
    for def_name, def_schema in definitions.items():
        props = def_schema.get("properties", {})
        for field_name in _INTERNAL_FIELDS:
            props.pop(field_name, None)
        _remove_from_required(def_schema, _INTERNAL_FIELDS)

        # Remove pipe_category only from pipe blueprint definitions
        if def_name in _PIPE_DEFINITION_NAMES:
            for field_name in _PIPE_INTERNAL_FIELDS:
                props.pop(field_name, None)
            _remove_from_required(def_schema, _PIPE_INTERNAL_FIELDS)

    return schema


def _remove_from_required(schema_obj: dict[str, Any], field_names: set[str]) -> None:
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
    _walk_schema(schema, _draft4_visitor)

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


def _walk_schema(node: dict[str, Any] | list[Any] | Any, visitor: Callable[[dict[str, Any]], None]) -> None:
    """Recursively walk a JSON Schema tree, calling visitor on each dict node.

    Args:
        node: Current node in the schema tree
        visitor: Callable that receives each dict node for in-place modification
    """
    if isinstance(node, dict):
        typed_node = cast("dict[str, Any]", node)
        visitor(typed_node)
        for child_value in typed_node.values():
            _walk_schema(child_value, visitor)
    elif isinstance(node, list):
        typed_list = cast("list[Any]", node)
        for child_item in typed_list:
            _walk_schema(child_item, visitor)
