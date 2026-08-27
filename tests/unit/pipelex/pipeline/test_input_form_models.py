"""Characterize the wire this engine emits through the standard's input-form models.

The descriptor's shapes are declared by `mthds.protocol.input_form` and re-exported from
`pipelex.pipeline.input_form`, so the per-kind slot rules and the closed shapes are the standard's
own and are pinned in the package that declares them. What this module pins is the engine's side of
the bargain: the report's valid arm is dumped WITHOUT `exclude_none` on the HTTP surface, so a node
must render its own wire — inapplicable slots absent rather than JSON null, applicable falsy values
(`required: false`, `gating: false`, `integer: false`, `item_count` on a fixed list) kept, the
`datetime` slot under its spec name, and the serializer recursing through a descriptor.
"""

from __future__ import annotations

from pipelex.core.pipes.variable_multiplicity import PresenceMarker
from pipelex.pipeline.input_form import (
    DateField,
    EnumField,
    InputFormField,
    ListField,
    NumberField,
    ObjectItem,
    PipeInputFormDescriptor,
    ProseField,
    TextField,
)


def _prose_field(name: str = "brief") -> InputFormField:
    return ProseField(name=name, concept_ref="demo.Brief", required=True, presence=PresenceMarker.PLAIN, gating=True)


class TestInputFormSerialization:
    def test_inapplicable_slots_are_absent_not_null(self) -> None:
        dumped = _prose_field().model_dump(mode="json")
        assert dumped["kind"] == "prose"
        assert dumped["name"] == "brief"
        assert dumped["concept_ref"] == "demo.Brief"
        assert dumped["required"] is True
        assert dumped["presence"] == "plain"
        assert dumped["gating"] is True
        for absent in ("title", "refines", "description", "default_value", "examples", "hints", "min_length", "max_length", "pattern", "format"):
            assert absent not in dumped, f"Inapplicable slot {absent!r} must be absent, not null"
        assert None not in dumped.values()

    def test_applicable_falsy_values_are_kept(self) -> None:
        field = NumberField(
            name="count",
            concept_ref="demo.Count",
            required=False,
            presence=PresenceMarker.OPTIONAL,
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
        field = DateField(name="released_on", required=True, datetime=False)
        dumped = field.model_dump(mode="json")
        assert dumped["datetime"] is False

    def test_single_member_choices_stay_a_list(self) -> None:
        field = EnumField(name="only", required=False, choices=["single"])
        assert field.model_dump(mode="json")["choices"] == ["single"]

    def test_descriptor_dump_recurses_the_serializer(self) -> None:
        descriptor = PipeInputFormDescriptor(
            fields=[
                ListField(
                    name="gadgets",
                    concept_ref="demo.Gadget",
                    required=True,
                    presence=PresenceMarker.PLAIN,
                    gating=True,
                    item_count=2,
                    item=ObjectItem(
                        concept_ref="demo.Gadget",
                        required=True,
                        fields=[TextField(name="label", required=True)],
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
        assert "name" not in item_node, "A list's item has no authored name and carries no name member"
        nested = item_node["fields"][0]
        assert nested == {"kind": "text", "name": "label", "required": True}
