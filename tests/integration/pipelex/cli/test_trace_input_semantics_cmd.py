"""Pin the `pipelex-dev trace-input-semantics` capture harness: one artifact per hop of the
input-schema emission chain, captured inside the validation window.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cli.dev_cli.commands.trace_input_semantics_cmd import (
    HOP1_FILE_NAME,
    HOP2_DIR_NAME,
    HOP2_PYTHON_STRUCTURES_FILE_NAME,
    HOP3_DIR_NAME,
    HOP4_DIR_NAME,
    HOP5_FILE_NAME,
    HOP5_INPUT_FORM_FILE_NAME,
    MANIFEST_FILE_NAME,
    trace_input_semantics,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_SMALL_BUNDLE = """
domain = "trace_tool_test"
description = "Bundle for trace-input-semantics tests"

[concept.Item]
description = "SENT_concept_item"

[concept.Item.structure]
label = { type = "text", description = "SENT_field_label", required = true }
qty = { type = "integer", description = "SENT_field_qty", default_value = 3 }

[pipe.do_one]
type = "PipeLLM"
description = "Make text from item"
inputs = { item = "Item", items = "Item[]", hint = "Text?", loose = "Anything" }
output = "Text"
prompt = '''
@item
@items
@?hint
$loose
'''
"""

_PADDED_BUNDLE = """
domain = "trace_tool_padded"
description = "Bundle for trace-input-semantics docstring and default-factory tests"

[concept.Padded]
description = "\\n\\nSENT_padded_first_line\\n    SENT_padded_second_line"

[concept.Padded.structure]
label = { type = "text", description = "SENT_field_label" }

[pipe.read_padded]
type = "PipeLLM"
description = "Make text from a padded concept and a search result"
inputs = { padded = "Padded", found = "SearchResult" }
output = "Text"
prompt = '''
@padded
@found
'''
"""

_PROBE_BUNDLE_PATH = Path(__file__).parents[3] / "data" / "input_semantics" / "probe_bundle.mthds"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.asyncio(loop_scope="class")
class TestTraceInputSemantics:
    async def test_per_hop_captures_on_small_bundle(self, tmp_path: Path, load_empty_library: Callable[[], str]) -> None:
        """Each hop of the chain lands one artifact, and authored sentinels are found where expected."""
        load_empty_library()
        bundle_path = tmp_path / "small_bundle.mthds"
        bundle_path.write_text(_SMALL_BUNDLE, encoding="utf-8")
        output_dir = tmp_path / "trace"

        manifest = await trace_input_semantics(bundle_paths=[bundle_path], output_dir=output_dir)

        # Hop 1: the parsed blueprint dump carries the authored field facts.
        hop1 = _read_json(output_dir / HOP1_FILE_NAME)
        item_structure = hop1[0]["concept"]["Item"]["structure"]
        assert item_structure["label"]["description"] == "SENT_field_label"
        assert item_structure["label"]["required"] is True
        assert item_structure["qty"]["default_value"] == 3

        # Hop 2: the structure class the library holds, read off the class, carries description, presence and default.
        hop2_relative = manifest["hop2_structure_classes"]["trace_tool_test.Item"]
        assert hop2_relative is not None
        hop2 = _read_json(output_dir / hop2_relative)
        assert hop2["class_name"] == "trace_tool_test__Item"
        assert hop2["bases"] == ["StructuredContent"]
        assert hop2["doc"] == "SENT_concept_item"
        assert hop2["fields"]["label"] == {
            "annotation": "<class 'str'>",
            "required": True,
            "admits_none": False,
            "default": "PydanticUndefined",
            "default_factory": None,
            "description": "SENT_field_label",
        }
        assert hop2["fields"]["qty"]["required"] is False
        assert hop2["fields"]["qty"]["default"] == 3
        # `native.Anything` declares no structure class.
        assert manifest["hop2_structure_classes"]["native.Anything"] is None
        # Beside it, the module the `python-structures` target writes for the loaded crate.
        assert manifest["hop2_python_structures"] == HOP2_PYTHON_STRUCTURES_FILE_NAME
        module_source = (output_dir / HOP2_PYTHON_STRUCTURES_FILE_NAME).read_text(encoding="utf-8")
        assert "class trace_tool_test__Item(StructuredContent):" in module_source
        assert 'description="SENT_field_label"' in module_source

        # Hop 3: the raw pydantic schema for the concept's structure class.
        hop3 = _read_json(output_dir / manifest["hop3_raw_pydantic_schemas"]["trace_tool_test.Item"])
        assert hop3["properties"]["label"]["description"] == "SENT_field_label"
        assert hop3["properties"]["qty"]["default"] == 3

        # Hop 4: the SCHEMA render per pipe input — envelope with concept ref, array wrap on [].
        hop4_single = _read_json(output_dir / manifest["hop4_schema_renders"]["trace_tool_test.do_one.item"])
        assert hop4_single["concept"] == "trace_tool_test.Item"
        assert hop4_single["content"]["properties"]["label"]["description"] == "SENT_field_label"
        hop4_multi = _read_json(output_dir / manifest["hop4_schema_renders"]["trace_tool_test.do_one.items"])
        assert hop4_multi["content"]["type"] == "array"
        # `native.Anything` declares no structure class: hop 3 records the skip rather than resolving
        # one, and hop 4 still renders — through the structureless arm, excluding only array and null.
        assert any("native.Anything" in entry for entry in manifest["hop3_skipped"])
        hop4_loose = _read_json(output_dir / manifest["hop4_schema_renders"]["trace_tool_test.do_one.loose"])
        assert hop4_loose["concept"] == "native.Anything"
        assert set(hop4_loose["content"]) == {"title", "description", "not"}

        # Hop 5: the final wire contracts, keyed by namespaced pipe_ref, with presence flags.
        hop5 = _read_json(output_dir / HOP5_FILE_NAME)
        do_one = hop5["trace_tool_test.do_one"]
        assert do_one["inputs"]["item"]["concept_ref"] == "trace_tool_test.Item"
        assert do_one["inputs"]["hint"]["presence"] == "optional"
        assert do_one["inputs"]["items"]["multiplicity"] == "variable"
        assert do_one["inputs"]["items"]["json_schema"]["type"] == "array"
        # The contract's item_count slot is always on the wire — `null` off the fixed arm, per the
        # protocol spec (unlike the descriptor, which omits inapplicable slots).
        assert "item_count" in do_one["inputs"]["items"]
        assert do_one["inputs"]["items"]["item_count"] is None

        # Hop 5, descriptor side: the same pipes, keyed identically, with the authored facts stated directly.
        input_form = _read_json(output_dir / HOP5_INPUT_FORM_FILE_NAME)
        assert set(input_form) == set(hop5)
        do_one_fields = {field["name"]: field for field in input_form["trace_tool_test.do_one"]["fields"]}
        assert do_one_fields["items"]["kind"] == "list"
        assert do_one_fields["items"]["concept_ref"] == "trace_tool_test.Item"
        assert do_one_fields["hint"]["presence"] == "optional"

        # Manifest: wire framing pairs the authored ref string with the resolved spec.
        framing_by_input = {f"{entry['pipe_ref']}.{entry['input_name']}": entry for entry in manifest["wire_framing"]}
        assert framing_by_input["trace_tool_test.do_one.items"]["authored_spec"] == "Item[]"
        assert framing_by_input["trace_tool_test.do_one.items"]["is_multiple"] is True
        assert framing_by_input["trace_tool_test.do_one.hint"]["presence"] == "optional"
        assert (output_dir / MANIFEST_FILE_NAME).is_file()

    async def test_rerun_into_same_output_dir_prunes_stale_hop_artifacts(self, tmp_path: Path, load_empty_library: Callable[[], str]) -> None:
        """A rerun into an existing output directory replaces the per-item hop captures wholesale —
        no artifact from a removed or renamed concept, pipe, or input survives on disk.
        """
        load_empty_library()
        bundle_path = tmp_path / "small_bundle.mthds"
        bundle_path.write_text(_SMALL_BUNDLE, encoding="utf-8")
        output_dir = tmp_path / "trace"
        await trace_input_semantics(bundle_paths=[bundle_path], output_dir=output_dir)

        renamed_bundle_path = tmp_path / "renamed_bundle.mthds"
        renamed_bundle_path.write_text(_SMALL_BUNDLE.replace("Item", "Widget"), encoding="utf-8")
        manifest = await trace_input_semantics(bundle_paths=[renamed_bundle_path], output_dir=output_dir)

        assert manifest["hop2_structure_classes"]["trace_tool_test.Widget"] is not None
        hop_dirs_to_manifest_keys = {
            HOP2_DIR_NAME: "hop2_structure_classes",
            HOP3_DIR_NAME: "hop3_raw_pydantic_schemas",
            HOP4_DIR_NAME: "hop4_schema_renders",
        }
        for hop_dir_name, manifest_key in hop_dirs_to_manifest_keys.items():
            on_disk = {str(path.relative_to(output_dir)) for path in (output_dir / hop_dir_name).rglob("*") if path.is_file()}
            expected = {relative_path for relative_path in manifest[manifest_key].values() if relative_path is not None}
            assert on_disk == expected, f"stale artifacts under {hop_dir_name}: {sorted(on_disk - expected)}"

    async def test_probe_fixture_validates_and_traces(self, tmp_path: Path, load_empty_library: Callable[[], str]) -> None:
        """The committed audit probe bundle validates cleanly and every hop capture lands."""
        load_empty_library()
        output_dir = tmp_path / "probe_trace"

        manifest = await trace_input_semantics(bundle_paths=[_PROBE_BUNDLE_PATH], output_dir=output_dir)

        assert manifest["hop2_structure_classes"]["input_semantics_probe.Widget"] is not None
        # A `structure = "ClassName"` concept holds the class it names, which the runtime built nothing for.
        class_backed = _read_json(output_dir / manifest["hop2_structure_classes"]["input_semantics_probe.ClassBacked"])
        assert class_backed["class_name"] == "TextContent"
        # A description-only concept holds a plain refinement of `TextContent`, documented by its description.
        plain_note = _read_json(output_dir / manifest["hop2_structure_classes"]["input_semantics_probe.PlainNote"])
        assert plain_note["class_name"] == "input_semantics_probe__PlainNote"
        assert plain_note["bases"] == ["TextContent"]
        assert plain_note["doc"] == "PROBE_desc_concept_PlainNote: description-only concept (basic blueprint)"
        assert plain_note["fields"]["text"]["annotation"] == class_backed["fields"]["text"]["annotation"]
        assert "input_semantics_probe.Widget" in manifest["hop3_raw_pydantic_schemas"]
        # Native concepts appearing as direct pipe inputs are traced too.
        assert "native.Image" in manifest["hop3_raw_pydantic_schemas"]
        assert manifest["hop4_schema_renders"]
        hop5 = _read_json(output_dir / HOP5_FILE_NAME)
        assert "input_semantics_probe.probe_markers" in hop5
        assert "input_semantics_probe.probe_markers" in _read_json(output_dir / HOP5_INPUT_FORM_FILE_NAME)

    async def test_hop2_reads_docstrings_and_default_factories_as_pydantic_does(self, tmp_path: Path, load_empty_library: Callable[[], str]) -> None:
        """Hop 2's doc is the schema description hop 3 shows, and a default factory is named rather than read as required."""
        load_empty_library()
        bundle_path = tmp_path / "padded_bundle.mthds"
        bundle_path.write_text(_PADDED_BUNDLE, encoding="utf-8")
        output_dir = tmp_path / "trace"

        manifest = await trace_input_semantics(bundle_paths=[bundle_path], output_dir=output_dir)

        padded = _read_json(output_dir / manifest["hop2_structure_classes"]["trace_tool_padded.Padded"])
        padded_schema = _read_json(output_dir / manifest["hop3_raw_pydantic_schemas"]["trace_tool_padded.Padded"])
        assert padded["doc"] == padded_schema["description"]
        assert padded["doc"].startswith("SENT_padded_first_line")
        assert padded["fields"]["label"]["default_factory"] is None

        search_result = _read_json(output_dir / manifest["hop2_structure_classes"]["native.SearchResult"])
        sources = search_result["fields"]["sources"]
        assert sources["required"] is False
        assert sources["default"] == "PydanticUndefined"
        # The factory is named by its module and qualified name, which hold no memory address, so the capture is the same
        # on every run.
        assert sources["default_factory"] == "pipelex.tools.typing.pydantic_utils.empty_list_factory_of.<locals>._factory"
        assert " at 0x" not in sources["default_factory"]
