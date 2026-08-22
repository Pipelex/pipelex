"""Unit-pin the input-form wire models: per-kind slot validators and null-free serialization.

The report's valid arm is dumped WITHOUT `exclude_none` on the HTTP surface, so the field model
owns its own wire shape: inapplicable slots are dropped at serialization (never emitted as JSON
null), applicable falsy values (`required: false`, `gating: false`, `integer: false`,
`item_count` on a fixed list) are kept, and the `datetime` wire slot serializes under its spec
name regardless of the Python attribute that carries it.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipelex.pipeline.input_form import FieldKind, InputFormField, PipeInputFormDescriptor


def _prose_field(name: str = "brief") -> InputFormField:
    return InputFormField(kind=FieldKind.PROSE, name=name, concept_ref="demo.Brief", required=True, presence="plain", gating=True)


class TestInputFormFieldValidators:
    def test_enum_requires_choices(self) -> None:
        with pytest.raises(ValidationError):
            InputFormField(kind=FieldKind.ENUM, name="tone", required=False)

    def test_object_requires_fields(self) -> None:
        with pytest.raises(ValidationError):
            InputFormField(kind=FieldKind.OBJECT, name="widget", required=True)

    def test_list_requires_item(self) -> None:
        with pytest.raises(ValidationError):
            InputFormField(kind=FieldKind.LIST, name="notes", required=True)

    def test_number_requires_integer_flag(self) -> None:
        with pytest.raises(ValidationError):
            InputFormField(kind=FieldKind.NUMBER, name="count", required=True)

    def test_date_requires_datetime_flag(self) -> None:
        with pytest.raises(ValidationError):
            InputFormField(kind=FieldKind.DATE, name="released_on", required=True)

    def test_scalar_kinds_accept_minimal_slots(self) -> None:
        field = InputFormField(kind=FieldKind.TEXT, name="title", required=True)
        assert field.kind == FieldKind.TEXT


class TestInputFormSerialization:
    def test_inapplicable_slots_are_absent_not_null(self) -> None:
        dumped = _prose_field().model_dump(mode="json")
        assert dumped["kind"] == "prose"
        assert dumped["name"] == "brief"
        assert dumped["concept_ref"] == "demo.Brief"
        assert dumped["required"] is True
        assert dumped["presence"] == "plain"
        assert dumped["gating"] is True
        for absent in ("title", "refines", "description", "default_value", "examples", "hints", "fields", "item", "item_count", "choices"):
            assert absent not in dumped, f"Inapplicable slot {absent!r} must be absent, not null"
        assert None not in dumped.values()

    def test_applicable_falsy_values_are_kept(self) -> None:
        field = InputFormField(
            kind=FieldKind.NUMBER,
            name="count",
            concept_ref="demo.Count",
            required=False,
            presence="optional",
            gating=False,
            integer=False,
            exclusive_minimum=0,
        )
        dumped = field.model_dump(mode="json")
        assert dumped["required"] is False
        assert dumped["gating"] is False
        assert dumped["integer"] is False
        assert dumped["exclusive_minimum"] == 0

    def test_datetime_slot_serializes_under_its_wire_name(self) -> None:
        field = InputFormField(kind=FieldKind.DATE, name="released_on", required=True, datetime_flag=False)
        dumped = field.model_dump(mode="json")
        assert dumped["datetime"] is False
        assert "datetime_flag" not in dumped

    def test_single_member_choices_stay_a_list(self) -> None:
        field = InputFormField(kind=FieldKind.ENUM, name="only", required=False, choices=["single"])
        assert field.model_dump(mode="json")["choices"] == ["single"]

    def test_descriptor_dump_recurses_the_serializer(self) -> None:
        descriptor = PipeInputFormDescriptor(
            fields=[
                InputFormField(
                    kind=FieldKind.LIST,
                    name="gadgets",
                    concept_ref="demo.Gadget",
                    required=True,
                    presence="plain",
                    gating=True,
                    item_count=2,
                    item=InputFormField(
                        kind=FieldKind.OBJECT,
                        name="gadgets",
                        concept_ref="demo.Gadget",
                        required=True,
                        fields=[InputFormField(kind=FieldKind.TEXT, name="label", required=True)],
                    ),
                )
            ]
        )
        dumped = descriptor.model_dump(mode="json")
        list_node = dumped["fields"][0]
        assert list_node["item_count"] == 2
        item_node = list_node["item"]
        assert "presence" not in item_node, "Nested fields never carry pipe-slot facts"
        assert "gating" not in item_node
        nested = item_node["fields"][0]
        assert nested == {"kind": "text", "name": "label", "required": True}
