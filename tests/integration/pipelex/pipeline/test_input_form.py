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
from typing import TYPE_CHECKING, Any, cast

import pytest
from kajson.kajson_manager import KajsonManager
from pydantic import Field

from pipelex.core.memory.exceptions import ListWhereSingularError
from pipelex.core.memory.input_shaper import InputShaper, PipelineInputs
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.interpreter_hub import (
    clear_current_library,
    get_concept_library,
    get_current_library_id_or_none,
    get_library_manager,
    set_current_library,
)
from pipelex.pipeline.input_form import FieldKind, InputFormField, build_input_form
from pipelex.pipeline.pipe_io_contracts import IOMultiplicity, build_pipe_io_contracts
from pipelex.pipeline.validate_bundle import validate_bundle
from tests.helpers.input_form import as_list, fields_by_name

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
_HINTED_BUNDLE_PATH = Path(__file__).parents[3] / "data" / "input_semantics" / "hinted_bundle.mthds"


_LIBRARY_DIR_MTHDS = """
domain = "input_form_lib"
description = "Library domain loaded through library_dirs"

[concept.Invoice]
description = "An invoice"

[concept.Invoice.structure]
number = { type = "text", description = "Invoice number", required = true }
total = { type = "number", description = "Total amount" }

[concept]
Memo = "A short memo"
"""

_LIBRARY_CONSUMER_MTHDS = """
domain = "input_form_consumer"
description = "Bundle whose pipe input is a concept from a library dir"

[concept.SpecialInvoice]
description = "An invoice flagged for review"
refines = "input_form_lib.Invoice"

[pipe.process]
type = "PipeLLM"
description = "Process an invoice"
output = "Text"
prompt = '''
@invoice
@memo
@special
'''

[pipe.process.inputs]
invoice = "input_form_lib.Invoice"
memo = "input_form_lib.Memo"
special = "SpecialInvoice"
"""


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


def _assert_no_null_values(dumped: Any, *, path: str = "$") -> None:
    """No slot on the dumped wire form ever carries JSON null — inapplicable slots are ABSENT."""
    if isinstance(dumped, dict):
        for key, value in cast("dict[str, Any]", dumped).items():
            assert value is not None, f"Slot {path}.{key} dumped as null — inapplicable slots must be absent"
            _assert_no_null_values(value, path=f"{path}.{key}")
    elif isinstance(dumped, list):
        for index, value in enumerate(cast("list[Any]", dumped)):
            _assert_no_null_values(value, path=f"{path}[{index}]")


@pytest.mark.asyncio(loop_scope="class")
class TestBuildInputForm:
    async def _derive_probe(self, load_empty_library: Callable[[], str]) -> tuple[dict[str, PipeInputFormDescriptor], set[str]]:
        outer_library_id = load_empty_library()
        try:
            result = await validate_bundle(mthds_contents=[_PROBE_BUNDLE_PATH.read_text(encoding="utf-8")])
            input_form = build_input_form(result.pipes)
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
        assert stringnote.refines is None, "No refines was authored, and none is reconstructed — text-valuedness is `kind: prose`"

        note = _field_by_name(input_form["input_semantics_probe.probe_single"], "note")
        assert note.kind == FieldKind.PROSE
        assert note.description is not None
        assert "PROBE_desc_concept_PlainNote" in note.description

    async def test_object_fields_carry_authored_facts(self, load_empty_library: Callable[[], str]) -> None:
        """Nested fields state the blueprint's facts: defaults (the E3 pair is rejected upstream), choices (E10), nesting (E1)."""
        input_form, _ = await self._derive_probe(load_empty_library)
        widget = _field_by_name(input_form["input_semantics_probe.probe_single"], "widget")
        assert widget.kind == FieldKind.OBJECT
        assert widget.fields is not None
        by_name = {field.name: field for field in widget.fields}

        # Declared order is preserved.
        assert [field.name for field in widget.fields][:4] == ["shorthand_note", "title", "subtitle", "summary"]

        motto = by_name["motto"]
        assert motto.required is False, "A defaulted field is not required — the E3 pair is rejected upstream"
        assert motto.default_value == "PROBE_default_motto"

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
        assert by_name["released_on"].datetime is False
        assert by_name["launched_at"].kind == FieldKind.DATE
        assert by_name["launched_at"].datetime is True
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
        assert constrained_count.minimum is None, "Unknown blueprint keys are rejected at parse (E7) — a valid bundle cannot carry them"

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
        time_in = _field_by_name(natives, "time_in")
        assert time_in.kind == FieldKind.TEXT
        assert time_in.format == "time"
        assert _field_by_name(natives, "yesno_in").kind == FieldKind.BOOLEAN

        # `native.Date` and `native.Html` sit on the standard's object arm: fields from the pinned
        # definition, like the other structured natives.
        date_in = _field_by_name(natives, "date_in")
        assert date_in.kind == FieldKind.OBJECT
        date_fields = fields_by_name(date_in)
        assert list(date_fields) == ["date", "time"], "Pinned-blueprint fields, in pinned order"
        assert date_fields["date"].kind == FieldKind.DATE
        assert date_fields["date"].datetime is False
        assert date_fields["date"].required is True
        assert date_fields["time"].kind == FieldKind.TEXT
        assert date_fields["time"].format == "time"
        assert date_fields["time"].required is False

        html_in = _field_by_name(natives, "html_in")
        assert html_in.kind == FieldKind.OBJECT
        html_fields = fields_by_name(html_in)
        assert list(html_fields) == ["inner_html", "css_class"], "Pinned-blueprint fields, in pinned order"
        assert html_fields["inner_html"].kind == FieldKind.TEXT
        assert html_fields["inner_html"].required is True
        assert html_fields["css_class"].kind == FieldKind.TEXT
        assert html_fields["css_class"].required is False
        for field in natives.fields:
            assert field.concept_ref is not None
            assert field.concept_ref.startswith("native."), f"{field.name} states its native ref, got {field.concept_ref!r}"

    async def test_no_inputs_pipe_maps_to_empty_fields(self, load_empty_library: Callable[[], str]) -> None:
        """A pipe with no inputs maps to an empty `fields` list — a valid form, not an omitted entry."""
        outer_library_id = load_empty_library()
        try:
            result = await validate_bundle(mthds_contents=[_NO_INPUTS_MTHDS])
            input_form = build_input_form(result.pipes)
        finally:
            _teardown_validation_library(outer_library_id)

        assert input_form["input_form_empty.generate"].fields == []

    async def test_library_dir_concepts_derive_like_local_ones(self, tmp_path: Path, load_empty_library: Callable[[], str]) -> None:
        """Concepts loaded through `library_dirs` are in the library's crate: structured, description-only, and refined alike."""
        (tmp_path / "input_form_lib.mthds").write_text(_LIBRARY_DIR_MTHDS)
        outer_library_id = load_empty_library()
        try:
            result = await validate_bundle(mthds_contents=[_LIBRARY_CONSUMER_MTHDS], library_dirs=[tmp_path])
            input_form = build_input_form(result.pipes)
        finally:
            _teardown_validation_library(outer_library_id)

        descriptor = input_form["input_form_consumer.process"]
        invoice = _field_by_name(descriptor, "invoice")
        assert invoice.kind == FieldKind.OBJECT
        assert invoice.concept_ref == "input_form_lib.Invoice"
        assert invoice.description == "An invoice"
        assert invoice.fields is not None
        number, total = invoice.fields
        assert (number.name, number.kind, number.required) == ("number", FieldKind.TEXT, True)
        assert (total.name, total.kind) == ("total", FieldKind.NUMBER)

        memo = _field_by_name(descriptor, "memo")
        assert memo.kind == FieldKind.PROSE
        assert memo.description == "A short memo"
        assert memo.refines is None, "A description-only concept authored no refines, and none is fabricated"

        special = _field_by_name(descriptor, "special")
        assert special.kind == FieldKind.OBJECT
        assert special.refines == ["input_form_lib.Invoice"]
        assert special.fields is not None
        assert [field.name for field in special.fields] == ["number", "total"]
        assert special.description == "An invoice flagged for review"

    async def test_hinted_slots_carry_effective_hints_on_the_wire(self, load_empty_library: Callable[[], str]) -> None:
        """Authored hints reach the descriptor (H2): slot hints merge over the concept layer, an
        applicable intent feeds `kind`, a plural slot's hints ride list AND item, and hint-free
        slots stay hint-free.
        """
        outer_library_id = load_empty_library()
        try:
            result = await validate_bundle(mthds_contents=[_HINTED_BUNDLE_PATH.read_text(encoding="utf-8")])
            input_form = build_input_form(result.pipes)
        finally:
            _teardown_validation_library(outer_library_id)

        fields = {field.name: field for field in input_form["input_semantics_hinted.hinted_slots"].fields}
        # Plain and collapsed slots derive identically: the concept layer alone (Essay: prose).
        for slot_name in ["plain", "expanded_plain"]:
            assert fields[slot_name].hints == {"intent": "prose"}
            assert fields[slot_name].kind is FieldKind.PROSE
        # Slot hints on a structured concept: inapplicable intent rides, kind stays `object`.
        assert fields["hinted"].hints == {"intent": "prose"}
        assert fields["hinted"].kind is FieldKind.OBJECT
        # Plural slot: merged hints on the list node AND its item; the item's kind flips.
        marked = fields["hinted_marked"]
        assert marked.kind is FieldKind.LIST
        assert marked.hints == {"intent": "label"}
        assert marked.item is not None
        assert marked.item.hints == {"intent": "label"}
        assert marked.item.kind is FieldKind.TEXT

    async def test_hinted_structure_fields_on_the_wire(self, load_empty_library: Callable[[], str]) -> None:
        """Field-site hints from the parsed bundle survive to the descriptor, unknown keys included."""
        outer_library_id = load_empty_library()
        try:
            result = await validate_bundle(mthds_contents=[_HINTED_BUNDLE_PATH.read_text(encoding="utf-8")])
            input_form = build_input_form(result.pipes)
        finally:
            _teardown_validation_library(outer_library_id)

        review = _field_by_name(input_form["input_semantics_hinted.hinted_slots"], "hinted")
        review_fields = fields_by_name(review)
        assert review_fields["headline"].hints == {"intent": "label"}
        assert review_fields["headline"].kind is FieldKind.TEXT
        assert review_fields["body"].hints == {"intent": "prose"}
        assert review_fields["body"].kind is FieldKind.PROSE
        assert review_fields["stars"].hints == {"intent": "rating"}
        assert review_fields["stars"].kind is FieldKind.NUMBER
        assert review_fields["plain"].hints is None
        # Unknown key: preserved content, riding the slot with no kind effect.
        assert review_fields["quirk"].hints == {"emphasis": "HINTED_unknown_value"}
        assert review_fields["quirk"].kind is FieldKind.TEXT

    async def test_hint_free_probe_descriptor_carries_no_hints_key(self, load_empty_library: Callable[[], str]) -> None:
        """Population is wire-additive: the hint-free probe bundle's descriptor is byte-identical
        to before hints existed — no `hints` key at any depth.
        """
        input_form, _ = await self._derive_probe(load_empty_library)

        def assert_no_hints(dumped: dict[str, Any]) -> None:
            assert "hints" not in dumped
            children: list[dict[str, Any]] = dumped.get("fields") or []
            for child in children:
                assert_no_hints(child)
            item: dict[str, Any] | None = dumped.get("item")
            if item:
                assert_no_hints(item)

        for descriptor in input_form.values():
            for field in descriptor.fields:
                assert_no_hints(field.model_dump())

    async def test_wire_dump_has_no_null_slots(self, load_empty_library: Callable[[], str]) -> None:
        """The valid arm is dumped WITHOUT `exclude_none`, so inapplicable slots must self-exclude."""
        input_form, _ = await self._derive_probe(load_empty_library)

        for pipe_ref, descriptor in input_form.items():
            dumped = descriptor.model_dump(mode="json")
            _assert_no_null_values(dumped, path=pipe_ref)
            for dumped_field in dumped["fields"]:
                # Nested fields never carry pipe-slot facts.
                nested_fields: list[dict[str, Any]] = dumped_field.get("fields") or []
                for nested in nested_fields:
                    assert "presence" not in nested
                    assert "gating" not in nested


# ---- Phase 3: the rest of the kind-assignment table ---------------------------------------------


class InputFormConstrainedPayload(StructuredContent):
    """A hand-written structure class a bundle names via `structure = "..."`, with engine-stated constraints."""

    width: int = Field(gt=0, le=4096, description="PROBE_desc_reflected_width")
    code: str = Field(min_length=2, max_length=8, pattern="^[A-Z]+$", description="PROBE_desc_reflected_code")
    ratio: float | None = Field(default=None, ge=0.0, lt=1.0, description="PROBE_desc_reflected_ratio")
    retries: int = Field(default=3, description="PROBE_desc_reflected_retries")
    strict: bool = Field(default=False, description="PROBE_desc_reflected_strict")
    tags: list[str] = Field(default_factory=list, description="PROBE_desc_reflected_tags")


class InputFormFieldLessPayload(StructuredContent):
    """A registered structure class declaring no field — a payload that demands nothing."""


class InputFormAttachment(StructuredContent):
    """A nested non-native model, carrying a file-bearing field one level below the concept."""

    caption: str = Field(description="PROBE_desc_reflected_caption")
    picture: ImageContent = Field(description="PROBE_desc_reflected_picture")


class InputFormPartlyMappablePayload(StructuredContent):
    """A structure class one annotation defeats — every other field, the file-bearing ones included, must still be stated."""

    payload: str | int = Field(description="PROBE_desc_reflected_payload")
    label: str = Field(description="PROBE_desc_reflected_label")
    attachment: InputFormAttachment = Field(description="PROBE_desc_reflected_attachment")
    scans: list[DocumentContent] = Field(description="PROBE_desc_reflected_scans")


_KIND_TABLE_MTHDS = """
domain = "input_form_kinds"
description = "Bundle pinning the rest of the kind-assignment table"

[concept.Constrained]
description = "PROBE_desc_concept_Constrained: class-backed by a hand-written constrained class"
structure = "InputFormConstrainedPayload"

[concept.PartlyMappable]
description = "PROBE_desc_concept_PartlyMappable: class-backed by a class one annotation defeats"
structure = "InputFormPartlyMappablePayload"

[concept.FieldLess]
description = "PROBE_desc_concept_FieldLess: class-backed by a class declaring no field"
structure = "InputFormFieldLessPayload"

[concept.Gadget]
description = "PROBE_desc_concept_Gadget"

[concept.Gadget.structure]
name = { type = "text", description = "PROBE_desc_field_gadget_name", required = true }

[concept.EmptyStruct]
description = "PROBE_desc_concept_EmptyStruct: an authored structure table holding no field"

[concept.EmptyStruct.structure]

[concept.RefinesEmpty]
description = "PROBE_desc_concept_RefinesEmpty: refines the empty-structure base and adds nothing"
refines = "EmptyStruct"

[pipe.remaining_natives]
type = "PipeCompose"
description = "The native concepts the probe bundle does not exercise as direct inputs"
inputs = { tai_in = "TextAndImages", search_result_in = "SearchResult", dynamic_in = "Dynamic", anything_in = "Anything", json_in = "JSON" }
output = "Text"
template = "$tai_in $search_result_in $dynamic_in $anything_in $json_in"

[pipe.empty_structures]
type = "PipeCompose"
description = "Concepts whose authored structure table is empty, directly and through a refines link"
inputs = { empty_in = "EmptyStruct", refining_in = "RefinesEmpty" }
output = "Text"
template = "$empty_in $refining_in"

[pipe.edges]
type = "PipeLLM"
description = "Fixed-count-of-one multiplicity and class-backed reflection"
inputs = { one = "Gadget[1]", constrained = "Constrained", partly_mappable = "PartlyMappable", field_less = "FieldLess" }
output = "Text"
prompt = \"\"\"
@one
@constrained
@partly_mappable
@field_less
\"\"\"
"""


_ONE_SLOT_MTHDS = """
domain = "one_slot"
description = "A single `[1]` slot, for pinning that every surface rules it the same way"

[concept.Gadget]
description = "A gadget"

[concept.Gadget.structure]
name = { type = "text", description = "The gadget name", required = true }

[pipe.take_one]
type = "PipeLLM"
description = "Take exactly one gadget"
inputs = { one = "Gadget[1]" }
output = "Text"
prompt = \"\"\"
@one
\"\"\"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestKindAssignmentTable:
    async def _derive_kind_table(self, load_empty_library: Callable[[], str]) -> dict[str, PipeInputFormDescriptor]:
        outer_library_id = load_empty_library()
        try:
            # Register into the *process-global* registry, not the ambient one: these classes stand in
            # for structure classes a Python module put in the process, and `validate_bundle` opens its
            # own library, whose registry is seeded from the global one. Registering through
            # `get_class_registry()` here would put them in the enclosing empty library's registry,
            # where the validate library cannot see them.
            registry = KajsonManager.get_class_registry()
            registry.register_class(InputFormConstrainedPayload)
            registry.register_class(InputFormPartlyMappablePayload)
            registry.register_class(InputFormFieldLessPayload)
            result = await validate_bundle(mthds_contents=[_KIND_TABLE_MTHDS])
            return build_input_form(result.pipes)
        finally:
            _teardown_validation_library(outer_library_id)

    async def test_remaining_natives_complete_the_table(self, load_empty_library: Callable[[], str]) -> None:
        """With the probe bundle's natives, every `NativeConceptCode` a pipe can take as input has a pinned kind."""
        input_form = await self._derive_kind_table(load_empty_library)
        natives = input_form["input_form_kinds.remaining_natives"]

        text_and_images = _field_by_name(natives, "tai_in")
        assert text_and_images.kind == FieldKind.OBJECT
        assert text_and_images.fields is not None
        assert [field.name for field in text_and_images.fields][:2] == ["text", "images"], "Pinned-blueprint fields, in pinned order"
        search_result = _field_by_name(natives, "search_result_in")
        assert search_result.kind == FieldKind.OBJECT
        assert search_result.fields is not None
        assert _field_by_name(natives, "dynamic_in").kind == FieldKind.UNKNOWN
        assert _field_by_name(natives, "anything_in").kind == FieldKind.UNKNOWN
        assert _field_by_name(natives, "json_in").kind == FieldKind.UNKNOWN
        for field in natives.fields:
            assert field.concept_ref is not None
            assert field.concept_ref.startswith("native.")
            assert field.description, f"{field.name} carries its pinned native description"

    async def test_fixed_count_of_one_is_a_single_node(self, load_empty_library: Callable[[], str]) -> None:
        """`Concept[1]` is not multiple to the runtime (`is_multiple()` is `count > 1`), so the form asks for one value."""
        input_form = await self._derive_kind_table(load_empty_library)
        one = _field_by_name(input_form["input_form_kinds.edges"], "one")

        assert one.kind == FieldKind.OBJECT, "A `[1]` slot is the concept's own node, never a list wrapper"
        assert one.concept_ref == "input_form_kinds.Gadget"
        assert one.required is True
        assert one.gating is True

    async def test_a_fixed_count_of_one_is_ruled_the_same_way_by_every_surface(self, load_empty_library: Callable[[], str]) -> None:
        """The descriptor, the wire contract and the memory shaper agree that a `[1]` slot is single.

        They once did not: the descriptor and the contract published `single` while the shaper framed
        the payload as a one-item list, so a form rendered faithfully on the descriptor submitted a value
        the shaper refused. Each surface pinned on its own can drift into that again and stay green,
        which is why the agreement is asserted here in one place. The payload is exactly what the
        descriptor node describes.
        """
        outer_library_id = load_empty_library()
        try:
            result = await validate_bundle(mthds_contents=[_ONE_SLOT_MTHDS])

            descriptor_node = _field_by_name(build_input_form(result.pipes)["one_slot.take_one"], "one")
            contract_input = build_pipe_io_contracts(result.pipes)["one_slot.take_one"].inputs["one"]
            take_one_pipe = {pipe.pipe_ref: pipe for pipe in result.pipes}["one_slot.take_one"]

            assert descriptor_node.kind == FieldKind.OBJECT, "the descriptor asks for one value"
            assert contract_input.multiplicity == IOMultiplicity.SINGLE, "the contract publishes the single arm"
            assert contract_input.item_count is None

            # The shaper takes what those two describe: the object itself, with no list around it.
            working_memory = InputShaper.shape(
                {"one": {"name": "widget"}},
                input_specs=take_one_pipe.inputs,
                concept_provider=get_concept_library(),
            )
            content = working_memory.root["one"].content
            assert not isinstance(content, ListContent), "the runtime frames a `[1]` slot as the item, never a one-item list"
            assert content.model_dump() == {"name": "widget"}

            # And it refuses a list there on the same grounds a bare declaration does.
            list_payload = cast("PipelineInputs", {"one": [{"name": "widget"}]})
            with pytest.raises(ListWhereSingularError):
                InputShaper.shape(list_payload, input_specs=take_one_pipe.inputs, concept_provider=get_concept_library())
        finally:
            _teardown_validation_library(outer_library_id)

    async def test_an_authored_but_empty_structure_table_is_an_object_with_no_fields(self, load_empty_library: Callable[[], str]) -> None:
        """The engine branches on `structure is not None` (`ConceptFactory`), so an empty `[concept.X.structure]`
        table is backed by a field-less structured model whose schema is `{"type": "object", "properties": {}}`.
        The descriptor states that same fact: testing truthiness instead would report the concept as `prose`,
        contradicting the object schema beside it.
        """
        input_form = await self._derive_kind_table(load_empty_library)
        empties = input_form["input_form_kinds.empty_structures"]

        empty = _field_by_name(empties, "empty_in")
        assert empty.kind == FieldKind.OBJECT
        assert empty.fields == []
        assert empty.refines is None, "Nothing was authored to refine, and nothing is invented"
        assert empty.model_dump()["fields"] == [], "An empty `fields` is applicable, so the wire keeps it"

        refining = _field_by_name(empties, "refining_in")
        assert refining.kind == FieldKind.OBJECT, "The dict structure sits one link up the chain, and still decides"
        assert refining.fields == []
        assert refining.refines == ["input_form_kinds.EmptyStruct"], "The authored chain, with nothing appended to it"

    async def test_custom_class_reflects_to_object_with_constraints(self, load_empty_library: Callable[[], str]) -> None:
        """A hand-written structure class is reflected field by field, with the constraints the engine states."""
        input_form = await self._derive_kind_table(load_empty_library)
        constrained = _field_by_name(input_form["input_form_kinds.edges"], "constrained")

        assert constrained.kind == FieldKind.OBJECT
        assert constrained.concept_ref == "input_form_kinds.Constrained"
        assert constrained.description is not None
        assert "PROBE_desc_concept_Constrained" in constrained.description, "The concept description survives (E6)"
        assert constrained.fields is not None
        by_name = {field.name: field for field in constrained.fields}

        width = by_name["width"]
        assert width.kind == FieldKind.NUMBER
        assert width.integer is True
        assert width.required is True
        assert width.exclusive_minimum == 0
        assert width.maximum == 4096
        assert width.minimum is None
        assert width.description == "PROBE_desc_reflected_width"

        code = by_name["code"]
        assert code.kind == FieldKind.TEXT
        assert code.min_length == 2
        assert code.max_length == 8
        assert code.pattern == "^[A-Z]+$"

        ratio = by_name["ratio"]
        assert ratio.kind == FieldKind.NUMBER
        assert ratio.integer is False
        assert ratio.required is False
        assert ratio.minimum == 0.0
        assert ratio.exclusive_maximum == 1.0
        assert ratio.default_value is None, "A None default is the optionality artifact, never a default_value"

        retries = by_name["retries"]
        assert retries.kind == FieldKind.NUMBER
        assert retries.required is False, "A pydantic default on a reflected class is an authored fact — the field is not required"
        assert retries.default_value == 3

        strict = by_name["strict"]
        assert strict.required is False
        assert strict.default_value is False, "A falsy non-None default is an authored fact — the None guard must not drop it"

        tags = by_name["tags"]
        assert tags.required is False, "A default_factory makes the field not required"
        assert tags.default_value is None, "A default_factory has no reportable value — no default_value is fabricated"

    async def test_a_field_less_class_is_an_object_with_no_fields(self, load_empty_library: Callable[[], str]) -> None:
        """`reflect_structure_class` answers `None` for two different things, and only one is opaque.

        A class declaring no field states a payload that demands nothing — the class-backed twin of an
        empty authored structure table — so the form reports `object` with an empty `fields` list. A
        field reflection could not map stays `unknown`, which the sibling case below pins.
        """
        input_form = await self._derive_kind_table(load_empty_library)
        field_less = _field_by_name(input_form["input_form_kinds.edges"], "field_less")

        assert field_less.kind == FieldKind.OBJECT
        assert field_less.fields == []
        assert field_less.concept_ref == "input_form_kinds.FieldLess"
        assert field_less.required is True
        assert field_less.gating is True

    async def test_an_unmappable_annotation_is_unknown_on_that_field_alone(self, load_empty_library: Callable[[], str]) -> None:
        """Class reflection is partial: the field no annotation maps is `unknown`, its siblings stay stated."""
        input_form = await self._derive_kind_table(load_empty_library)
        partly_mappable = _field_by_name(input_form["input_form_kinds.edges"], "partly_mappable")

        assert partly_mappable.kind == FieldKind.OBJECT, "One defeated annotation no longer collapses the whole payload"
        assert partly_mappable.concept_ref == "input_form_kinds.PartlyMappable"
        assert partly_mappable.description is not None
        assert "PROBE_desc_concept_PartlyMappable" in partly_mappable.description
        by_name = fields_by_name(partly_mappable)

        payload = by_name["payload"]
        assert payload.kind == FieldKind.UNKNOWN, "A union that is neither optional nor numeric has no honest node"
        assert payload.description == "PROBE_desc_reflected_payload", "The unmappable field keeps its identity and helper text"
        assert by_name["label"].kind == FieldKind.TEXT, "The mappable sibling is stated, not lost with it"

    async def test_file_positions_below_a_defeated_sibling_stay_visible(self, load_empty_library: Callable[[], str]) -> None:
        """What partial reflection is for: a consumer preparing inputs must still see every file position.

        The collapse hid these — an `image` nested in a plain model, a list of `document` — behind the
        one sibling annotation the reflection could not map, and a local path at such a position went
        through un-uploaded.
        """
        input_form = await self._derive_kind_table(load_empty_library)
        by_name = fields_by_name(_field_by_name(input_form["input_form_kinds.edges"], "partly_mappable"))

        attachment = by_name["attachment"]
        assert attachment.kind == FieldKind.OBJECT, "A nested non-native model is walked into, not flattened to an opaque dict"
        assert attachment.description == "PROBE_desc_reflected_attachment"
        nested = fields_by_name(attachment)
        assert nested["caption"].kind == FieldKind.TEXT
        assert nested["picture"].kind == FieldKind.IMAGE, "The file position one level down is reported"
        assert nested["picture"].concept_ref == "native.Image", "A content class maps to its native by identity"
        assert nested["picture"].description == "PROBE_desc_reflected_picture", "The field's own description wins over the native's"

        scans = as_list(by_name["scans"])
        assert scans.concept_ref == "native.Document", "A list of a content class names the element concept"
        assert scans.item.kind == FieldKind.DOCUMENT
        assert not hasattr(scans.item, "name"), "A list item has no authored name"
