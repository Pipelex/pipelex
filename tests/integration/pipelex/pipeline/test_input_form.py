"""Pin the D2 `build_input_form` deriver: the per-pipe input-form descriptor from authored facts.

Contract: the workspace spec `docs/specs/mthds-input-form-descriptor.md`. The descriptor is derived
from the loaded pipes (slot facts: order, presence, multiplicity) plus the authored blueprints
(concept facts: descriptions, refinement chains, structure fields) — never from the emitted JSON
Schema, so the facts the schema projection destroys (S1 findings E1-E10) survive here:

- concept identity on every concept-typed node (E1) and the refinement chain as a stated list (E2);
- three-valued `presence` so `!` is not flattened (E5), and `gating` stated as its own fact;
- structured multiplicity including fixed `[N]` counts (E4/E9);
- authored `required` AND `default_value` both reported (E3 — the descriptor reports authored
  intent, not the generator's silent drop);
- single-member `choices` normalized to a list, never `const` (E10);
- concept descriptions on class-backed and native nodes (E6).

The deriver runs against the open validation library (`validate_bundle` leaves it loaded on
success), mirroring `build_pipe_io_contracts` — same window, same key space.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library
from pipelex.pipeline.input_form import FieldKind, InputFormField, build_input_form
from pipelex.pipeline.pipe_io_contracts import build_pipe_io_contracts
from pipelex.pipeline.validate_bundle import validate_bundle

if TYPE_CHECKING:
    from collections.abc import Callable

    from pipelex.pipeline.input_form import PipeInputFormDescriptor


def _teardown_validation_library(outer_library_id: str) -> None:
    """Tear down the library `validate_bundle` left open on success, restoring the outer one."""
    validation_library_id = get_current_library_id_or_none()
    if validation_library_id is not None and validation_library_id != outer_library_id:
        set_current_library(library_id=outer_library_id)
        get_library_manager().teardown(library_id=validation_library_id)
    clear_current_library()


_PROBE_BUNDLE_PATH = Path(__file__).parents[3] / "data" / "input_semantics" / "probe_bundle.mthds"


_NO_INPUTS_MTHDS = """
domain = "input_form_empty"
description = "Bundle with a pipe declaring no inputs"

[pipe.generate]
type = "PipeLLM"
description = "Generate something from nothing"
output = "Text"
prompt = "Write a haiku."
"""


def _field_by_name(descriptor: PipeInputFormDescriptor, name: str) -> InputFormField:
    by_name = {field.name: field for field in descriptor.fields}
    assert name in by_name, f"Expected a field named {name!r}, got {sorted(by_name)}"
    return by_name[name]


def _assert_no_null_values(dumped: object, *, path: str = "$") -> None:
    """No slot on the dumped wire form ever carries JSON null — inapplicable slots are ABSENT."""
    if isinstance(dumped, dict):
        for key, value in dumped.items():
            assert value is not None, f"Slot {path}.{key} dumped as null — inapplicable slots must be absent"
            _assert_no_null_values(value, path=f"{path}.{key}")
    elif isinstance(dumped, list):
        for index, value in enumerate(dumped):
            _assert_no_null_values(value, path=f"{path}[{index}]")


@pytest.mark.asyncio(loop_scope="class")
class TestBuildInputForm:
    async def _derive_probe(self, load_empty_library: Callable[[], str]) -> tuple[dict[str, PipeInputFormDescriptor], set[str]]:
        outer_library_id = load_empty_library()
        try:
            result = await validate_bundle(mthds_contents=[_PROBE_BUNDLE_PATH.read_text(encoding="utf-8")])
            input_form = build_input_form(result.pipes, blueprints=result.blueprints)
            contract_keys = set(build_pipe_io_contracts(result.pipes))
        finally:
            _teardown_validation_library(outer_library_id)
        return input_form, contract_keys

    async def test_keyed_like_pipe_io_contracts_in_authored_order(self, load_empty_library: Callable[[], str]) -> None:
        """Same namespaced `pipe_ref` key set as `pipe_io_contracts`; `fields` follow authored slot order."""
        input_form, contract_keys = await self._derive_probe(load_empty_library)

        assert set(input_form) == contract_keys
        single = input_form["input_semantics_probe.probe_single"]
        assert [field.name for field in single.fields] == ["widget", "gadget_q", "note"]
        markers = input_form["input_semantics_probe.probe_markers"]
        assert [field.name for field in markers.fields] == ["opt", "many", "two", "forced"]

    async def test_presence_required_and_gating_markers(self, load_empty_library: Callable[[], str]) -> None:
        """Presence is three-valued (E5); `required` derives from it; `gating` diverges on variable lists."""
        input_form, _ = await self._derive_probe(load_empty_library)
        markers = input_form["input_semantics_probe.probe_markers"]

        opt = _field_by_name(markers, "opt")
        assert opt.presence == "optional"
        assert opt.required is False
        assert opt.gating is False

        many = _field_by_name(markers, "many")
        assert many.kind == FieldKind.LIST
        assert many.presence == "plain"
        assert many.required is True
        assert many.gating is False, "A variable-multiplicity list never gates: `[]` is its legitimate value"
        assert many.item_count is None
        assert many.item is not None
        assert many.item.concept_ref == "input_semantics_probe.Widget"
        assert many.concept_ref == "input_semantics_probe.Widget", "A list node names the ELEMENT concept"

        two = _field_by_name(markers, "two")
        assert two.kind == FieldKind.LIST
        assert two.item_count == 2, "The fixed `[N]` count is a structured fact (E4)"
        assert two.required is True
        assert two.gating is True, "A fixed-count list gates like any other slot"

        forced = _field_by_name(markers, "forced")
        assert forced.presence == "force"
        assert forced.required is True
        assert forced.gating is True

        widget = _field_by_name(input_form["input_semantics_probe.probe_single"], "widget")
        assert widget.presence == "plain"
        assert widget.required is True
        assert widget.gating is True

    async def test_concept_identity_and_refinement_chain(self, load_empty_library: Callable[[], str]) -> None:
        """Every concept node states its namespaced ref (E1); chains are walked to their end (E2)."""
        input_form, _ = await self._derive_probe(load_empty_library)
        refined = input_form["input_semantics_probe.probe_refined"]

        refdoc = _field_by_name(refined, "refdoc")
        assert refdoc.concept_ref == "input_semantics_probe.RefinedDoc"
        assert refdoc.kind == FieldKind.DOCUMENT, "Document-ness is a chain fact, never `properties.url` sniffing"
        assert refdoc.refines == ["native.Document"]

        special = _field_by_name(refined, "special")
        assert special.refines == ["input_semantics_probe.BaseEntity"]
        assert special.kind == FieldKind.OBJECT

        extra = _field_by_name(refined, "extra")
        assert extra.refines == ["input_semantics_probe.SpecialEntity", "input_semantics_probe.BaseEntity"]

        classbacked = _field_by_name(refined, "classbacked")
        assert classbacked.kind == FieldKind.PROSE, "A class-backed text concept flattens to its scalar kind"
        assert classbacked.description is not None
        assert "PROBE_desc_concept_ClassBacked" in classbacked.description, "The concept description survives (E6)"

        stringnote = _field_by_name(refined, "stringnote")
        assert stringnote.kind == FieldKind.PROSE
        assert stringnote.concept_ref == "input_semantics_probe.StringNote"
        assert stringnote.refines == ["native.Text"], "A string-described concept is this engine's TextContent fact"

        note = _field_by_name(input_form["input_semantics_probe.probe_single"], "note")
        assert note.kind == FieldKind.PROSE
        assert note.description is not None
        assert "PROBE_desc_concept_PlainNote" in note.description

    async def test_object_fields_carry_authored_facts(self, load_empty_library: Callable[[], str]) -> None:
        """Nested fields state the blueprint's facts: E3 both-facts, defaults, choices (E10), nesting (E1)."""
        input_form, _ = await self._derive_probe(load_empty_library)
        widget = _field_by_name(input_form["input_semantics_probe.probe_single"], "widget")
        assert widget.kind == FieldKind.OBJECT
        assert widget.fields is not None
        by_name = {field.name: field for field in widget.fields}

        # Declared order is preserved.
        assert [field.name for field in widget.fields][:4] == ["shorthand_note", "title", "subtitle", "summary"]

        titled_default = by_name["titled_default"]
        assert titled_default.required is True, "Authored required-ness survives beside a default (E3)"
        assert titled_default.default_value == "PROBE_default_titled"

        assert by_name["shorthand_note"].required is True, "A shorthand string field implies required text"
        assert by_name["shorthand_note"].kind == FieldKind.TEXT
        assert by_name["subtitle"].required is False
        assert by_name["subtitle"].default_value is None, "The optional-field null is an emission artifact, never a default"
        assert by_name["motto"].default_value == "PROBE_default_motto"

        count = by_name["count"]
        assert count.kind == FieldKind.NUMBER
        assert count.integer is True
        assert count.default_value == 42
        price = by_name["price"]
        assert price.kind == FieldKind.NUMBER
        assert price.integer is False
        assert by_name["enabled"].kind == FieldKind.BOOLEAN

        assert by_name["released_on"].kind == FieldKind.DATE
        assert by_name["released_on"].datetime_flag is False
        assert by_name["launched_at"].kind == FieldKind.DATE
        assert by_name["launched_at"].datetime_flag is True
        daily_at = by_name["daily_at"]
        assert daily_at.kind == FieldKind.TEXT
        assert daily_at.format == "time"

        tone = by_name["tone"]
        assert tone.kind == FieldKind.ENUM
        assert tone.choices == ["PROBE_choice_formal", "PROBE_choice_casual", "PROBE_choice_playful"]
        assert tone.default_value == "PROBE_choice_casual"
        only_choice = by_name["only_choice"]
        assert only_choice.kind == FieldKind.ENUM
        assert only_choice.choices == ["PROBE_choice_single"], "A single choice is a one-member list, never `const` (E10)"
        assert by_name["typed_choice"].kind == FieldKind.ENUM, "`choices` win over `type`, matching the generator"

        tags = by_name["tags"]
        assert tags.kind == FieldKind.LIST
        assert tags.item is not None
        assert tags.item.kind == FieldKind.TEXT
        assert tags.default_value == ["PROBE_tag_a", "PROBE_tag_b"]
        matrix = by_name["matrix"]
        assert matrix.kind == FieldKind.LIST
        assert matrix.item is not None
        assert matrix.item.kind == FieldKind.UNKNOWN, "The inner item type of a nested list is inexpressible"

        gadgets = by_name["gadgets"]
        assert gadgets.kind == FieldKind.LIST
        assert gadgets.item is not None
        assert gadgets.item.kind == FieldKind.OBJECT
        assert gadgets.item.concept_ref == "input_semantics_probe.Gadget", "A nested concept node states its ref (E1)"
        assert gadgets.item.fields is not None
        trinket = {field.name: field for field in gadgets.item.fields}["trinket"]
        assert trinket.concept_ref == "input_semantics_probe.Trinket"
        assert trinket.kind == FieldKind.OBJECT

        assert by_name["attributes"].kind == FieldKind.UNKNOWN, "A dict field has no form kind — raw escape hatch"

        icon = by_name["icon"]
        assert icon.kind == FieldKind.IMAGE
        assert icon.concept_ref == "native.Image"

        constrained_count = by_name["constrained_count"]
        assert constrained_count.kind == FieldKind.NUMBER
        assert constrained_count.minimum is None, "Unknown blueprint keys died at parse (E7) — nothing to report"

    async def test_native_direct_inputs_kind_assignment(self, load_empty_library: Callable[[], str]) -> None:
        """Native concepts as direct inputs map by identity, never by shape sniffing."""
        input_form, _ = await self._derive_probe(load_empty_library)
        natives = input_form["input_semantics_probe.probe_native_inputs"]

        assert _field_by_name(natives, "text_in").kind == FieldKind.PROSE
        assert _field_by_name(natives, "image_in").kind == FieldKind.IMAGE
        assert _field_by_name(natives, "document_in").kind == FieldKind.DOCUMENT
        assert _field_by_name(natives, "page_in").kind == FieldKind.OBJECT
        number_in = _field_by_name(natives, "number_in")
        assert number_in.kind == FieldKind.NUMBER
        assert number_in.integer is False
        date_in = _field_by_name(natives, "date_in")
        assert date_in.kind == FieldKind.DATE
        assert date_in.datetime_flag is False
        time_in = _field_by_name(natives, "time_in")
        assert time_in.kind == FieldKind.TEXT
        assert time_in.format == "time"
        assert _field_by_name(natives, "html_in").kind == FieldKind.PROSE
        assert _field_by_name(natives, "yesno_in").kind == FieldKind.BOOLEAN
        for field in natives.fields:
            assert field.concept_ref is not None
            assert field.concept_ref.startswith("native."), f"{field.name} states its native ref, got {field.concept_ref!r}"

    async def test_no_inputs_pipe_maps_to_empty_fields(self, load_empty_library: Callable[[], str]) -> None:
        """A pipe with no inputs maps to an empty `fields` list — a valid form, not an omitted entry."""
        outer_library_id = load_empty_library()
        try:
            result = await validate_bundle(mthds_contents=[_NO_INPUTS_MTHDS])
            input_form = build_input_form(result.pipes, blueprints=result.blueprints)
        finally:
            _teardown_validation_library(outer_library_id)

        assert input_form["input_form_empty.generate"].fields == []

    async def test_wire_dump_has_no_null_slots(self, load_empty_library: Callable[[], str]) -> None:
        """The valid arm is dumped WITHOUT `exclude_none`, so inapplicable slots must self-exclude."""
        input_form, _ = await self._derive_probe(load_empty_library)

        for pipe_ref, descriptor in input_form.items():
            dumped = descriptor.model_dump(mode="json")
            _assert_no_null_values(dumped, path=pipe_ref)
            for dumped_field in dumped["fields"]:
                # Nested fields never carry pipe-slot facts.
                for nested in dumped_field.get("fields") or []:
                    assert "presence" not in nested
                    assert "gating" not in nested
