"""Tests for MTHDS JSON Schema generation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, cast

import jsonschema
import pytest

from pipelex.core.pipes.pipe_blueprint import PipeType
from pipelex.language.mthds_schema_generator import generate_mthds_schema

if TYPE_CHECKING:
    from collections.abc import Iterator

# Per-pipe-kind required fields beyond the universal {description, output}, with
# minimal schema-valid values. Keyed by the `type` discriminator value. Used to
# build a minimal table that validates against exactly one oneOf arm.
_PIPE_KIND_EXTRA_FIELDS: dict[str, dict[str, Any]] = {
    "PipeFunc": {"function_name": "do_it"},
    "PipeImgGen": {"prompt": "draw a cat"},
    "PipeCompose": {},
    "PipeLLM": {},
    "PipeExtract": {},
    "PipeSearch": {"prompt": "find it"},
    "PipeStructure": {},
    "PipeBatch": {"branch_pipe_code": "sub_pipe", "input_list_name": "items", "input_item_name": "item"},
    "PipeCondition": {"default_outcome": "fallback_pipe", "outcomes": {"yes": "yes_pipe"}},
    "PipeParallel": {"branches": [{"pipe": "sub_pipe"}]},
    "PipeSequence": {"steps": [{"pipe": "sub_pipe"}]},
    "PipeSignature": {},
}


def _minimal_pipe_table(pipe_type: str) -> dict[str, Any]:
    """A minimal schema-valid pipe table for the given `type` discriminator value."""
    return {"type": pipe_type, "description": f"A minimal {pipe_type} pipe", "output": "Text", **_PIPE_KIND_EXTRA_FIELDS[pipe_type]}


class TestMthdsSchemaGeneration:
    """Tests for generate_mthds_schema() and its post-processing pipeline."""

    @pytest.fixture(scope="class")
    def schema(self) -> dict[str, Any]:
        """Generate the schema once for all tests in this class."""
        return generate_mthds_schema()

    def test_schema_is_valid_draft4(self, schema: dict[str, Any]) -> None:
        """Verify the schema uses Draft 4 conventions, not Draft 2020-12."""
        # Must have definitions, not $defs
        assert "definitions" in schema, "Schema should use 'definitions' (Draft 4), not '$defs'"
        assert "$defs" not in schema, "Schema should not contain '$defs' (Draft 2020-12)"

        # Check no const anywhere in the schema (should be converted to enum)
        _assert_key_absent_recursive(schema, "const", "const should be converted to single-value enum")

        # Check no discriminator anywhere in the schema (not in Draft 4)
        _assert_key_absent_recursive(schema, "discriminator", "discriminator is not part of Draft 4")

        # Must have $schema pointing to Draft 4
        assert schema.get("$schema") == "http://json-schema.org/draft-04/schema#"

    def test_exclusive_minimum_is_draft4_boolean(self, schema: dict[str, Any]) -> None:
        """Verify exclusiveMinimum/exclusiveMaximum use Draft 4 boolean syntax, not Draft 6+ number syntax.

        Draft 4: "minimum": 0, "exclusiveMinimum": true
        Draft 6+: "exclusiveMinimum": 0 (number, standalone)
        """
        exclusive_nodes: list[tuple[str, dict[str, Any]]] = []
        _collect_exclusive_nodes(schema, "", exclusive_nodes)

        assert len(exclusive_nodes) > 0, "Schema should contain at least one exclusiveMinimum or exclusiveMaximum"

        for path, node in exclusive_nodes:
            if "exclusiveMinimum" in node:
                assert node["exclusiveMinimum"] is True, (
                    f"exclusiveMinimum at {path} should be boolean true (Draft 4), got {node['exclusiveMinimum']!r}"
                )
                assert "minimum" in node, f"exclusiveMinimum at {path} requires a companion 'minimum' field in Draft 4"
            if "exclusiveMaximum" in node:
                assert node["exclusiveMaximum"] is True, (
                    f"exclusiveMaximum at {path} should be boolean true (Draft 4), got {node['exclusiveMaximum']!r}"
                )
                assert "maximum" in node, f"exclusiveMaximum at {path} requires a companion 'maximum' field in Draft 4"

    def test_source_field_excluded(self, schema: dict[str, Any]) -> None:
        """Verify that 'source' field is not present in any definition."""
        # Check root properties
        root_props = schema.get("properties", {})
        assert "source" not in root_props, "source should be excluded from root properties"

        # Check all definitions
        definitions = schema.get("definitions", {})
        for def_name, def_schema in definitions.items():
            props = def_schema.get("properties", {})
            assert "source" not in props, f"source should be excluded from {def_name}"

    def test_pipe_category_field_excluded(self, schema: dict[str, Any]) -> None:
        """Verify that 'pipe_category' is not present in pipe definitions."""
        definitions = schema.get("definitions", {})
        pipe_def_names = [def_name for def_name in definitions if def_name.startswith("Pipe") and def_name.endswith("Blueprint")]

        assert len(pipe_def_names) > 0, "Should have pipe blueprint definitions"

        for def_name in pipe_def_names:
            props = definitions[def_name].get("properties", {})
            assert "pipe_category" not in props, f"pipe_category should be excluded from {def_name}"

    def test_construct_alias_used(self, schema: dict[str, Any]) -> None:
        """Verify PipeComposeBlueprint uses 'construct' alias, not 'construct_blueprint'."""
        definitions = schema.get("definitions", {})
        compose_def = definitions.get("PipeComposeBlueprint", {})
        props = compose_def.get("properties", {})

        assert "construct" in props, "PipeComposeBlueprint should have 'construct' (alias), not 'construct_blueprint'"
        assert "construct_blueprint" not in props, "Internal name 'construct_blueprint' should not appear in schema"

    def test_all_pipe_types_present(self, schema: dict[str, Any]) -> None:
        """Verify every PipeType has a corresponding blueprint definition in the schema."""
        definitions = schema.get("definitions", {})

        expected_blueprint_names = {f"{pipe_type}Blueprint" for pipe_type in PipeType.value_list()}

        for blueprint_name in expected_blueprint_names:
            assert blueprint_name in definitions, f"{blueprint_name} should be present in schema definitions"

    def test_construct_schema_matches_mthds_format(self, schema: dict[str, Any]) -> None:
        """Verify ConstructBlueprint uses additionalProperties, not 'fields' wrapper."""
        definitions = schema.get("definitions", {})
        construct_def = definitions.get("ConstructBlueprint", {})

        # Should use additionalProperties (MTHDS format: fields at root)
        assert "additionalProperties" in construct_def, "ConstructBlueprint should use additionalProperties for MTHDS-format fields"

        # Should not have a 'fields' property (internal model structure)
        props = construct_def.get("properties", {})
        assert "fields" not in props, "ConstructBlueprint should not expose internal 'fields' wrapper"

        # Should require at least one field
        assert construct_def.get("minProperties") == 1, "ConstructBlueprint should require at least one field"

    def test_taplo_metadata_present(self, schema: dict[str, Any]) -> None:
        """Verify root schema has x-taplo.initKeys metadata."""
        assert "x-taplo" in schema, "Schema should have x-taplo metadata"
        taplo_meta = schema["x-taplo"]
        assert "initKeys" in taplo_meta, "x-taplo should have initKeys"
        assert "domain" in taplo_meta["initKeys"], "initKeys should include 'domain'"

    def test_schema_has_title_and_comment(self, schema: dict[str, Any]) -> None:
        """Verify the schema has proper title and version comment."""
        assert schema.get("title") == "MTHDS File Schema"
        assert "$comment" in schema
        assert "PipelexBundleBlueprint" in schema["$comment"]

    def test_ref_paths_use_definitions(self, schema: dict[str, Any]) -> None:
        """Verify all $ref paths use #/definitions/ (Draft 4), not #/$defs/."""
        refs: list[str] = []
        _collect_refs_recursive(schema, refs)

        for ref_value in refs:
            assert "#/$defs/" not in ref_value, f"$ref should use #/definitions/, got: {ref_value}"

    def test_pipe_condition_outcomes_is_required(self, schema: dict[str, Any]) -> None:
        """Verify outcomes appears in PipeConditionBlueprint's required array."""
        definitions = schema.get("definitions", {})
        condition_def = definitions.get("PipeConditionBlueprint", {})
        required = condition_def.get("required", [])
        assert "outcomes" in required

    def test_no_x_schema_required_markers_in_output(self, schema: dict[str, Any]) -> None:
        """Verify x-schema-required markers are cleaned from the final schema."""
        _assert_key_absent_recursive(schema, "x-schema-required", "x-schema-required marker should be removed from output")

    def test_construct_field_schema_has_all_methods(self, schema: dict[str, Any]) -> None:
        """Verify the construct field schema covers all 4 composition methods."""
        definitions = schema.get("definitions", {})
        field_def = definitions.get("ConstructFieldBlueprint", {})

        any_of = field_def.get("anyOf", [])
        assert len(any_of) >= 4, "ConstructFieldBlueprint should have at least 4 anyOf variants"

        # Check we have the key formats: raw values, {from: ...}, {template: ...}, nested
        descriptions = [item.get("description", "") for item in any_of]
        has_from = any("from" in desc.lower() or "variable" in desc.lower() for desc in descriptions)
        has_template = any("template" in desc.lower() for desc in descriptions)
        has_nested = any("nested" in desc.lower() for desc in descriptions)

        assert has_from, "Should have a 'from' (variable reference) variant"
        assert has_template, "Should have a 'template' variant"
        assert has_nested, "Should have a 'nested construct' variant"

    def test_type_required_on_every_pipe_oneof_arm(self, schema: dict[str, Any]) -> None:
        """Every pipe blueprint variant in the pipe `oneOf` must require `type`.

        Reads the arm names straight from the generated `oneOf`, so a newly added
        pipe type is covered automatically — this doubles as the drift guard.
        """
        definitions = schema["definitions"]
        arms = schema["properties"]["pipe"]["anyOf"][0]["additionalProperties"]["oneOf"]
        arm_def_names = [arm["$ref"].rsplit("/", 1)[-1] for arm in arms]

        assert arm_def_names, "The pipe union oneOf should have at least one arm"
        for def_name in arm_def_names:
            required = definitions[def_name].get("required", [])
            assert "type" in required, f"{def_name} must list 'type' in its required array (got {required})"

    @pytest.mark.parametrize(
        "table",
        [
            pytest.param({"description": "no type at all", "output": "Text"}, id="bare-minimal"),
            # A table whose fields uniquely identify PipeFunc but omits `type`. Before the
            # fix this matched exactly one arm and validated; requiring `type` rejects it.
            pytest.param({"description": "looks like PipeFunc", "output": "Text", "function_name": "do_it"}, id="unique-fields"),
        ],
    )
    def test_typeless_pipe_table_is_rejected(self, schema: dict[str, Any], table: dict[str, Any]) -> None:
        """A pipe table without `type` must fail validation (no ambiguous multi-match)."""
        validator = _pipe_union_oneof_validator(schema)
        assert not validator.is_valid(table), f"A type-less pipe table must be rejected: {table}"

    @pytest.mark.parametrize("pipe_type", sorted(_PIPE_KIND_EXTRA_FIELDS))
    def test_typed_pipe_table_matches_exactly_one_arm(self, schema: dict[str, Any], pipe_type: str) -> None:
        """A minimal typed table for each pipe kind must match exactly one oneOf arm.

        Draft-4 `oneOf` validates iff exactly one subschema matches, so a successful
        validation here proves the `type` discriminator resolves to a single variant.
        """
        validator = _pipe_union_oneof_validator(schema)
        table = _minimal_pipe_table(pipe_type)
        errors = sorted(validator.iter_errors(table), key=str)
        assert not errors, f"{pipe_type} table should match exactly one oneOf arm, got errors: {[e.message for e in errors]}"

    def test_minimal_table_coverage_matches_schema_pipe_kinds(self, schema: dict[str, Any]) -> None:
        """Guard: the test's per-kind table map covers exactly the pipe kinds in the schema.

        If a new pipe type is added, this fails until a minimal table is provided —
        keeping `test_typed_pipe_table_matches_exactly_one_arm` exhaustive.
        """
        definitions = schema["definitions"]
        arms = schema["properties"]["pipe"]["anyOf"][0]["additionalProperties"]["oneOf"]
        schema_types = {definitions[arm["$ref"].rsplit("/", 1)[-1]]["properties"]["type"]["enum"][0] for arm in arms}
        assert set(_PIPE_KIND_EXTRA_FIELDS) == schema_types


class _SchemaValidator(Protocol):
    """Minimal typed view of a jsonschema validator.

    The `types-jsonschema` stubs expose `is_valid` / `iter_errors` as overloads whose
    deprecated second arm carries `Unknown`, which trips strict pyright's
    reportUnknownMemberType. Casting to this Protocol gives clean call-site types.
    """

    def is_valid(self, instance: object) -> bool: ...

    def iter_errors(self, instance: object) -> Iterator[Any]: ...


def _pipe_union_oneof_validator(schema: dict[str, Any]) -> _SchemaValidator:
    """Build a Draft-4 validator for the pipe-union `oneOf` at properties.pipe.anyOf[0].additionalProperties.

    The arms are `$ref`s into `#/definitions/...`, so the wrapper carries the full
    `definitions` map for reference resolution.
    """
    arms = schema["properties"]["pipe"]["anyOf"][0]["additionalProperties"]["oneOf"]
    wrapper = {"oneOf": arms, "definitions": schema["definitions"]}
    return cast("_SchemaValidator", jsonschema.Draft4Validator(wrapper))


def _assert_key_absent_recursive(node: Any, key: str, message: str) -> None:
    """Assert that a key is not present anywhere in a nested dict/list structure."""
    if isinstance(node, dict):
        typed_node = cast("dict[str, Any]", node)
        assert key not in typed_node, f"{message} (found in dict with keys: {list(typed_node.keys())[:5]})"
        for child_value in typed_node.values():
            _assert_key_absent_recursive(child_value, key, message)
    elif isinstance(node, list):
        typed_list = cast("list[Any]", node)
        for child_item in typed_list:
            _assert_key_absent_recursive(child_item, key, message)


def _collect_refs_recursive(node: Any, refs: list[str]) -> None:
    """Collect all $ref values from a nested dict/list structure."""
    if isinstance(node, dict):
        typed_node = cast("dict[str, Any]", node)
        if "$ref" in typed_node and isinstance(typed_node["$ref"], str):
            refs.append(typed_node["$ref"])
        for child_value in typed_node.values():
            _collect_refs_recursive(child_value, refs)
    elif isinstance(node, list):
        typed_list = cast("list[Any]", node)
        for child_item in typed_list:
            _collect_refs_recursive(child_item, refs)


def _collect_exclusive_nodes(node: Any, path: str, results: list[tuple[str, dict[str, Any]]]) -> None:
    """Collect all nodes that contain exclusiveMinimum or exclusiveMaximum."""
    if isinstance(node, dict):
        typed_node = cast("dict[str, Any]", node)
        if "exclusiveMinimum" in typed_node or "exclusiveMaximum" in typed_node:
            results.append((path, typed_node))
        for key, child_value in typed_node.items():
            _collect_exclusive_nodes(child_value, f"{path}.{key}", results)
    elif isinstance(node, list):
        typed_list = cast("list[Any]", node)
        for index, child_item in enumerate(typed_list):
            _collect_exclusive_nodes(child_item, f"{path}[{index}]", results)
