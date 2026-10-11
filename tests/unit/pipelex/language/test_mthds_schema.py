"""Tests for MTHDS JSON Schema generation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, cast

import jsonschema
import pytest

from pipelex.language.mthds_schema_generator import generate_mthds_schema
from pipelex.pipe_machinery.pipe_blueprint import PipeType
from pipelex.pipe_signature.pipe_signature_blueprint import PipeSignatureBlueprint

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
    "PipeDocGen": {"format": "pdf"},
    "PipeJudge": {"prompt": "@message", "question": "is it?"},
    "PipeBatch": {"branch_pipe_code": "sub_pipe", "input_list_name": "items", "input_item_name": "item"},
    "PipeCondition": {"default_outcome": "fallback_pipe", "outcomes": {"yes": "yes_pipe"}},
    "PipeParallel": {"branches": [{"pipe": "sub_pipe"}]},
    "PipeSequence": {"steps": [{"pipe": "sub_pipe"}]},
    # `PipeSignature` is deliberately absent: a signature is typeless, so there is no typed table for
    # it — an explicit `type = "PipeSignature"` table matches no arm (see test_explicit_signature_tag_is_rejected).
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

    def test_pipe_llm_carries_optional_templating_style(self, schema: dict[str, Any]) -> None:
        """The authored styling surface is published as a typed union, and stays optional."""
        definitions = schema.get("definitions", {})
        props = definitions["PipeLLMBlueprint"].get("properties", {})

        assert "templating_style" in props, "PipeLLMBlueprint should publish its authored templating_style"
        arms = props["templating_style"].get("anyOf", [])
        assert {"$ref": "#/definitions/TagStyle"} in arms, "the bare-string arm should be the TagStyle enum, not a free-form string"
        assert {"$ref": "#/definitions/TemplatingStyle"} in arms, "the inline-table arm should be the full TemplatingStyle"
        assert {"type": "null"} in arms, "templating_style must stay optional"

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

    def test_type_required_on_every_concrete_pipe_arm(self, schema: dict[str, Any]) -> None:
        """Every *concrete* pipe arm requires `type`; the signature arm is the one typeless arm.

        Reads the arm names straight from the generated `oneOf`, so a newly added pipe type is
        covered automatically — this doubles as the drift guard. The signature arm is the one typeless
        arm: it has NO `type` property at all (an explicit `type = "PipeSignature"` is rejected as an
        extra property under `additionalProperties: false`), so it lists `type` in neither `properties`
        nor `required`.
        """
        definitions = schema["definitions"]
        arms = schema["properties"]["pipe"]["anyOf"][0]["additionalProperties"]["oneOf"]
        arm_def_names = [arm["$ref"].rsplit("/", 1)[-1] for arm in arms]

        assert arm_def_names, "The pipe union oneOf should have at least one arm"
        signature_def_name = PipeSignatureBlueprint.__name__
        assert signature_def_name in arm_def_names, "The signature arm must be present in the pipe union"
        for def_name in arm_def_names:
            required = definitions[def_name].get("required", [])
            properties = definitions[def_name].get("properties", {})
            if def_name == signature_def_name:
                assert "type" not in properties, f"the signature arm must have NO 'type' property (got {sorted(properties)})"
                assert "type" not in required, f"the signature arm must NOT require 'type' (got {required})"
            else:
                assert "type" in required, f"{def_name} must list 'type' in its required array (got {required})"

    @pytest.mark.parametrize(
        "table",
        [
            pytest.param({"description": "bare contract", "output": "Text"}, id="bare-contract"),
            pytest.param({"description": "with inputs", "output": "Text", "inputs": {"doc": "Text"}}, id="with-inputs"),
            pytest.param({"description": "with hint", "output": "Text", "signature_for": "PipeLLM"}, id="with-signature-for"),
        ],
    )
    def test_typeless_contract_table_matches_signature_arm(self, schema: dict[str, Any], table: dict[str, Any]) -> None:
        """A typeless section carrying only the contract validates — it is a signature."""
        validator = _pipe_union_oneof_validator(schema)
        errors = sorted(validator.iter_errors(table), key=str)
        assert not errors, f"A typeless contract table must validate, got errors: {[e.message for e in errors]}"

    @pytest.mark.parametrize(
        "table",
        [
            # A typeless table that adds an implementation field beyond the contract. `prompt` is
            # shared by PipeLLM/PipeImgGen and `function_name` uniquely looks like PipeFunc, but with
            # no `type` neither matches any arm.
            pytest.param({"description": "looks like an impl", "output": "Text", "prompt": "do it"}, id="stray-prompt"),
            pytest.param({"description": "looks like PipeFunc", "output": "Text", "function_name": "do_it"}, id="stray-function-name"),
        ],
    )
    def test_typeless_table_with_stray_field_is_rejected(self, schema: dict[str, Any], table: dict[str, Any]) -> None:
        """A typeless section that declares more than the contract matches no arm."""
        validator = _pipe_union_oneof_validator(schema)
        assert not validator.is_valid(table), f"A typeless non-contract table must be rejected: {table}"

    def test_typoed_type_is_rejected(self, schema: dict[str, Any]) -> None:
        """A misspelled `type` matches no arm (not a concrete kind; the signature arm pins the tag)."""
        validator = _pipe_union_oneof_validator(schema)
        table = {"type": "PipeLLMM", "description": "typo", "output": "Text"}
        assert not validator.is_valid(table)

    def test_explicit_signature_tag_is_rejected(self, schema: dict[str, Any]) -> None:
        """An explicit `type = "PipeSignature"` table matches no arm: the signature arm has no `type`
        property (extra property under `additionalProperties: false`) and every concrete arm pins its
        own `type` enum. `PipeSignature` is no longer a selectable type.
        """
        validator = _pipe_union_oneof_validator(schema)
        table = {"type": "PipeSignature", "description": "explicit tag", "output": "Text"}
        assert not validator.is_valid(table)

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

    @pytest.mark.parametrize(
        ("judge_fields", "should_validate"),
        [
            pytest.param({"prompt": "@message", "question": "is it?"}, True, id="prompt-and-question"),
            pytest.param({"question": "is it?"}, False, id="question-alone"),
            pytest.param({"prompt": "@message"}, False, id="prompt-alone"),
            pytest.param({}, False, id="neither"),
            pytest.param(
                {
                    "prompt": "@message",
                    "questions": {"urgent": {"question": "is it?", "threshold": 0.7}, "team": {"question": "who?", "options": {"a": ""}}},
                },
                True,
                id="prompt-and-questions",
            ),
            pytest.param(
                {"prompt": "@message", "question": "is it?", "questions": {"urgent": {"question": "is it?"}}}, False, id="question-and-questions"
            ),
            pytest.param({"prompt": "@message", "questions": {}}, False, id="no-question-in-questions"),
            pytest.param({"prompt": "@message", "questions": {"urgent": {"threshold": 0.7}}}, False, id="question-table-without-question"),
            pytest.param(
                {"prompt": "@message", "questions": {"urgent": {"question": "is it?", "prompt": "@message"}}}, False, id="unknown-key-in-a-question"
            ),
            pytest.param(
                {"prompt": "@message", "questions": {"urgent": {"question": "is it?"}}, "threshold": 0.7}, False, id="threshold-on-the-pipe"
            ),
            pytest.param(
                {"prompt": "@message", "questions": {"urgent": {"question": "is it?"}}, "options": {"a": ""}}, False, id="options-on-the-pipe"
            ),
            pytest.param(
                {"prompt": "@message", "questions": {"urgent": {"question": "is it?"}}, "levels": ["a", "b"]}, False, id="levels-on-the-pipe"
            ),
            pytest.param(
                {"prompt": "@message", "questions": {"urgent": {"question": "is it?"}}, "criteria": {"yes": "y", "no": "n"}},
                False,
                id="criteria-on-the-pipe",
            ),
            pytest.param(
                {"prompt": "@message", "questions": {"severity": {"question": "how bad?", "levels": [{"label": "Low"}, "High"]}}},
                False,
                id="a-question-labelling-some-levels-only",
            ),
        ],
    )
    def test_pipe_judge_takes_its_evidence_prompt_and_its_question(
        self, schema: dict[str, Any], judge_fields: dict[str, Any], should_validate: bool
    ) -> None:
        """A PipeJudge writes the evidence in `prompt` and asks about it in one `question` or several `questions`, as its blueprint reads them.

        Asking several, the kind fields go on each question, never on the pipe, and `questions` holds at least one question.
        """
        validator = _pipe_union_oneof_validator(schema)
        table = {"type": "PipeJudge", "description": "A judge", "output": "YesNo", **judge_fields}
        assert validator.is_valid(table) is should_validate, f"{sorted(judge_fields)} should {'' if should_validate else 'not '}validate"

    @pytest.mark.parametrize(
        ("levels", "should_validate"),
        [
            pytest.param(["Minor", "Major"], True, id="descriptions-as-strings"),
            pytest.param([{"label": "Low", "description": "A cosmetic flaw"}, {"label": "High"}], True, id="labelled-tables"),
            pytest.param(["Minor", {"description": "Nothing works"}], True, id="strings-and-unlabelled-tables"),
            pytest.param(["Minor", {"label": "High", "description": "Nothing works"}], False, id="strings-and-labelled-tables"),
            pytest.param([{"label": "Low"}, {"description": "Nothing works"}], False, id="labelled-and-unlabelled-tables"),
            pytest.param([{"label": "Low", "colour": "green"}], False, id="table-with-an-unknown-key"),
            pytest.param([{"label": 3}], False, id="label-not-a-string"),
        ],
    )
    def test_pipe_judge_levels_are_strings_or_closed_tables(self, schema: dict[str, Any], levels: list[Any], should_validate: bool) -> None:
        """A rating level is written as its description or as a closed `{label, description}` table, and a scale labels every level or none.

        The load refuses a scale labelling some of its levels only (`_validate_levels`), so the schema refuses it first.
        """
        validator = _pipe_union_oneof_validator(schema)
        table = {**_minimal_pipe_table("PipeJudge"), "output": "Rating", "levels": levels}
        assert validator.is_valid(table) is should_validate, f"levels={levels!r} should {'' if should_validate else 'not '}validate"

    @pytest.mark.parametrize(
        ("size_value", "should_validate"),
        [
            pytest.param("1k", True, id="tier-token"),
            pytest.param("2048x1152", True, id="exact-size-string"),
            pytest.param({"width": 2048, "height": 1152}, True, id="exact-size-table"),
            pytest.param("banana", False, id="garbage-string"),
            pytest.param("0x100", False, id="zero-width"),
        ],
    )
    def test_pipe_img_gen_size_field_schema(self, schema: dict[str, Any], size_value: Any, should_validate: bool) -> None:
        """The `size` field must accept tier tokens and exact `WxH` strings, as written in .mthds files."""
        validator = _pipe_union_oneof_validator(schema)
        table = {**_minimal_pipe_table("PipeImgGen"), "size": size_value}
        assert validator.is_valid(table) is should_validate, f"size={size_value!r} should {'' if should_validate else 'not '}validate"

    @pytest.mark.parametrize("pipe_type", [*sorted(_PIPE_KIND_EXTRA_FIELDS), None])
    @pytest.mark.parametrize(
        ("input_name", "should_validate"),
        [
            pytest.param("invoice", True, id="plain"),
            pytest.param("invoice_total_2", True, id="plain-with-digits"),
            pytest.param("invoice.total", False, id="dotted"),
            pytest.param("InvoiceTotal", False, id="pascal-case"),
            pytest.param("2nd_total", False, id="leading-digit"),
            pytest.param("_total", False, id="leading-underscore"),
        ],
    )
    def test_input_names_follow_the_plain_name_grammar(
        self, schema: dict[str, Any], pipe_type: str | None, input_name: str, should_validate: bool
    ) -> None:
        """Every pipe kind's `inputs` keys, the typeless signature's included, are refused by the schema unless plain.

        This is what makes `invalid_input_name` a schema fault: a structural check refuses a dotted or
        malformed input name before the runtime is asked, on every pipe, with no per-kind exception.
        """
        validator = _pipe_union_oneof_validator(schema)
        if pipe_type is None:
            table: dict[str, Any] = {"description": "A signature", "output": "Text"}
        else:
            table = _minimal_pipe_table(pipe_type)
        table["inputs"] = {input_name: "Text"}
        assert validator.is_valid(table) is should_validate, f"{pipe_type or 'signature'} inputs key {input_name!r}"

    @pytest.mark.parametrize(
        ("input_list_name", "should_validate"),
        [
            pytest.param("pages", True, id="plain"),
            pytest.param("catalog.pages", False, id="dotted"),
            pytest.param("Pages", False, id="pascal-case"),
        ],
    )
    def test_batch_input_list_name_follows_the_plain_name_grammar(self, schema: dict[str, Any], input_list_name: str, should_validate: bool) -> None:
        """A PipeBatch's `input_list_name` is a plain input name, refused by the schema otherwise, as the runtime does."""
        validator = _pipe_union_oneof_validator(schema)
        table = {**_minimal_pipe_table("PipeBatch"), "input_list_name": input_list_name}
        assert validator.is_valid(table) is should_validate

    @pytest.mark.parametrize(
        ("step", "should_validate"),
        [
            pytest.param({"pipe": "sub_pipe"}, True, id="pipe-step"),
            pytest.param({"from": "invoice.total", "result": "total_amount"}, True, id="binding-step"),
            pytest.param({"from": "invoice", "result": "invoice_copy"}, True, id="binding-step-bare-name"),
            pytest.param({"from": "page.page_view.caption", "result": "caption"}, True, id="binding-step-deep-path"),
            pytest.param({"from": "invoice.Total2", "result": "total"}, True, id="binding-step-mixed-case-segment"),
            pytest.param({"from": "invoice.total", "result": "TotalAmount"}, False, id="result-not-plain"),
            pytest.param({"from": "invoice.total", "result": "invoice.total"}, False, id="result-dotted"),
            pytest.param({"from": "pages[0].text", "result": "text"}, False, id="from-with-a-subscript"),
            pytest.param({"from": "invoice._total", "result": "total"}, False, id="from-with-an-underscore-led-segment"),
            pytest.param({"from": "invoice..total", "result": "total"}, False, id="from-with-an-empty-segment"),
            pytest.param({"from": "invoice.total ", "result": "total"}, False, id="from-with-whitespace"),
            pytest.param({"from": "invoice.total"}, False, id="binding-without-result"),
            pytest.param({"pipe": "sub_pipe", "from": "invoice.total", "result": "total"}, False, id="pipe-and-from"),
            pytest.param({"from": "invoice.lines", "result": "lines", "batch_over": "lines"}, False, id="binding-with-batch-over"),
            pytest.param({"from": "invoice.total", "result": "total", "note": "x"}, False, id="binding-with-a-stray-field"),
            pytest.param({"from_path": "invoice.total", "result": "total"}, False, id="binding-spelled-from-path"),
            pytest.param({"from": "invoice.total", "from_path": "invoice.total", "result": "total"}, False, id="binding-with-from-path-beside-from"),
            pytest.param({"result": "total"}, False, id="neither-pipe-nor-from"),
        ],
    )
    def test_sequence_steps_are_pipe_steps_or_binding_steps(self, schema: dict[str, Any], step: dict[str, Any], should_validate: bool) -> None:
        """A PipeSequence step is a closed pipe step or a closed binding step, `from` following the path grammar and `result` the plain name's."""
        validator = _pipe_union_oneof_validator(schema)
        table = {**_minimal_pipe_table("PipeSequence"), "steps": [step]}
        assert validator.is_valid(table) is should_validate, f"step {step!r}"

    def test_parallel_branches_keep_the_pipe_step_shape(self, schema: dict[str, Any]) -> None:
        """A PipeParallel branch is a pipe step only: a binding step there matches no shape, since branches run concurrently."""
        validator = _pipe_union_oneof_validator(schema)
        table = {**_minimal_pipe_table("PipeParallel"), "branches": [{"from": "invoice.total", "result": "total"}]}
        assert validator.is_valid(table) is False
        branch_items = schema["definitions"]["PipeParallelBlueprint"]["properties"]["branches"]["items"]
        assert branch_items == {"$ref": "#/definitions/ParallelBranchBlueprint"}
        branch_schema = dict(schema["definitions"]["ParallelBranchBlueprint"])
        pipe_step_schema = dict(schema["definitions"]["SubPipeBlueprint"])
        for step_schema in (branch_schema, pipe_step_schema):
            step_schema.pop("title")
            step_schema["properties"] = {name: field for name, field in step_schema["properties"].items() if name != "batch_over"}
        assert branch_schema == pipe_step_schema

    @pytest.mark.parametrize(
        ("batch_over", "is_valid_on_a_step", "is_valid_on_a_branch"),
        [
            pytest.param("pages", True, True, id="a-plain-name"),
            pytest.param("PagesOfTheCatalog", True, True, id="a-name-that-is-not-snake-case"),
            pytest.param("catalog.pages", True, False, id="a-dotted-path"),
            pytest.param("catalogs.pages.page_view", True, False, id="a-deep-dotted-path"),
            pytest.param("catalog..pages", False, False, id="an-empty-segment"),
            pytest.param("catalog.pages[0]", False, False, id="a-subscript"),
            pytest.param("catalog._pages", False, False, id="an-underscore-led-segment"),
            pytest.param(".pages", False, False, id="a-leading-dot"),
        ],
    )
    def test_batch_over_is_a_path_on_a_sequence_step_and_a_plain_name_on_a_parallel_branch(
        self, schema: dict[str, Any], batch_over: str, is_valid_on_a_step: bool, is_valid_on_a_branch: bool
    ) -> None:
        """A dotted `batch_over` binds before it batches: it follows the path grammar on a sequence step, and a branch never binds.

        Both refusals are `binding_step_invalid`, which the runtime raises when the bundle is parsed and the schema refuses first.
        """
        validator = _pipe_union_oneof_validator(schema)
        pipe_step = {"pipe": "describe_page", "batch_over": batch_over, "batch_as": "page", "result": "descriptions"}
        sequence_table = {**_minimal_pipe_table("PipeSequence"), "steps": [pipe_step]}
        parallel_table = {**_minimal_pipe_table("PipeParallel"), "branches": [pipe_step]}
        assert validator.is_valid(sequence_table) is is_valid_on_a_step, f"sequence step batch_over {batch_over!r}"
        assert validator.is_valid(parallel_table) is is_valid_on_a_branch, f"parallel branch batch_over {batch_over!r}"

    @pytest.mark.parametrize(
        ("name", "should_validate"),
        [
            pytest.param("catalog_pages", True, id="a-plain-name"),
            pytest.param("bound_pages", True, id="the-prefix-without-its-underscore"),
            pytest.param("page2", True, id="a-digit-after-the-first-letter"),
            pytest.param("Pages", False, id="pascal-case"),
            pytest.param("catalog.pages", False, id="dotted"),
            pytest.param("_draft", False, id="underscore-led"),
            pytest.param("2nd_pages", False, id="digit-led"),
            pytest.param("_bound_catalog_pages", False, id="the-reserved-prefix"),
            pytest.param("_bound_", False, id="the-reserved-prefix-alone"),
        ],
    )
    @pytest.mark.parametrize("field_name", ["result", "batch_as"])
    def test_a_step_and_a_branch_hold_their_stored_names_to_the_plain_name_grammar(
        self, schema: dict[str, Any], field_name: str, name: str, should_validate: bool
    ) -> None:
        """A pipe step's `result` and `batch_as` are stored names, plain input names on a PipeSequence step and a PipeParallel branch alike.

        The runtime refuses any other form as `invalid_input_name` when the bundle is parsed, and the schema refuses it first,
        through the input-name `pattern` on the string arm, which no underscore-led name, the reserved prefix's included, matches.
        """
        validator = _pipe_union_oneof_validator(schema)
        pipe_step: dict[str, Any] = {"pipe": "describe_page", "batch_over": "pages", "batch_as": "page", "result": "descriptions", field_name: name}
        sequence_table = {**_minimal_pipe_table("PipeSequence"), "steps": [pipe_step]}
        parallel_table = {**_minimal_pipe_table("PipeParallel"), "branches": [pipe_step]}
        assert validator.is_valid(sequence_table) is should_validate, f"sequence step {field_name} {name!r}"
        assert validator.is_valid(parallel_table) is should_validate, f"parallel branch {field_name} {name!r}"

    @pytest.mark.parametrize(
        ("batch_over", "should_validate"),
        [
            pytest.param("catalog_pages", True, id="a-plain-name"),
            pytest.param("bound_pages", True, id="the-prefix-without-its-underscore"),
            pytest.param("_draft", True, id="another-underscore-led-name"),
            pytest.param("_bound_catalog_pages", False, id="the-reserved-prefix"),
            pytest.param("_bound_", False, id="the-reserved-prefix-alone"),
        ],
    )
    def test_a_step_and_a_branch_keep_a_plain_batch_over_off_the_reserved_prefix(
        self, schema: dict[str, Any], batch_over: str, should_validate: bool
    ) -> None:
        """A plain `batch_over` reads a name rather than storing one, and never `_bound_`, the runtime's prefix for a dotted `batch_over`'s list.

        The runtime refuses it as `invalid_input_name` when the bundle is parsed, and the schema refuses it first, through a
        Draft-4 `not` on the string arm, on a PipeSequence step and on a PipeParallel branch alike.
        """
        validator = _pipe_union_oneof_validator(schema)
        pipe_step: dict[str, Any] = {"pipe": "describe_page", "batch_over": batch_over, "batch_as": "page", "result": "descriptions"}
        sequence_table = {**_minimal_pipe_table("PipeSequence"), "steps": [pipe_step]}
        parallel_table = {**_minimal_pipe_table("PipeParallel"), "branches": [pipe_step]}
        assert validator.is_valid(sequence_table) is should_validate, f"sequence step batch_over {batch_over!r}"
        assert validator.is_valid(parallel_table) is should_validate, f"parallel branch batch_over {batch_over!r}"

    @pytest.mark.parametrize(
        ("input_item_name", "should_validate"),
        [
            pytest.param("item", True, id="a-plain-name"),
            pytest.param("item2", True, id="a-digit-after-the-first-letter"),
            pytest.param("Item", False, id="pascal-case"),
            pytest.param("catalog.item", False, id="dotted"),
            pytest.param("_draft_item", False, id="underscore-led"),
            pytest.param("_bound_item", False, id="the-reserved-prefix"),
        ],
    )
    def test_batch_input_item_name_follows_the_plain_name_grammar(self, schema: dict[str, Any], input_item_name: str, should_validate: bool) -> None:
        """A PipeBatch's `input_item_name` is a stored name, the branch pipe reading each item through an input of that name."""
        validator = _pipe_union_oneof_validator(schema)
        table = {**_minimal_pipe_table("PipeBatch"), "input_item_name": input_item_name}
        assert validator.is_valid(table) is should_validate

    @pytest.mark.parametrize(
        "pattern_path",
        [
            pytest.param(("SubPipeBlueprint", "result"), id="step-result"),
            pytest.param(("SubPipeBlueprint", "batch_as"), id="step-batch-as"),
            pytest.param(("ParallelBranchBlueprint", "result"), id="branch-result"),
            pytest.param(("ParallelBranchBlueprint", "batch_as"), id="branch-batch-as"),
            pytest.param(("PipeBatchBlueprint", "input_item_name"), id="batch-input-item-name"),
            pytest.param(("BindingStepBlueprint", "result"), id="binding-step-result"),
        ],
    )
    def test_every_stored_name_carries_the_input_name_pattern(self, schema: dict[str, Any], pattern_path: tuple[str, str]) -> None:
        """Each stored name's string arm carries the same input-name pattern, and nothing else, as a structural consumer reads it."""
        definition_name, field_name = pattern_path
        field_schema = schema["definitions"][definition_name]["properties"][field_name]
        string_arms = [arm for arm in field_schema.get("anyOf", [field_schema]) if arm.get("type") == "string"]
        assert len(string_arms) == 1
        assert string_arms[0]["pattern"] == "^[a-z][a-z0-9_]*$"
        assert "not" not in string_arms[0]

    def test_minimal_table_coverage_matches_schema_pipe_kinds(self, schema: dict[str, Any]) -> None:
        """Guard: the test's per-kind table map covers exactly the *concrete* pipe kinds in the schema.

        If a new pipe type is added, this fails until a minimal table is provided —
        keeping `test_typed_pipe_table_matches_exactly_one_arm` exhaustive. The signature arm is
        excluded: it is typeless (no `type` enum) and is not a selectable type.
        """
        definitions = schema["definitions"]
        arms = schema["properties"]["pipe"]["anyOf"][0]["additionalProperties"]["oneOf"]
        signature_def_name = PipeSignatureBlueprint.__name__
        schema_types = {
            definitions[def_name]["properties"]["type"]["enum"][0]
            for arm in arms
            if (def_name := arm["$ref"].rsplit("/", 1)[-1]) != signature_def_name
        }
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
