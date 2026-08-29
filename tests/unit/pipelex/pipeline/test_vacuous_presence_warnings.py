"""The vacuous-presence lint's decision table, over hand-built input-form descriptors.

One case per row of the design's rule table (`wip/full-optional/design.md` §3): a gating slot whose
concept declares no required field warns; everything else is silent, and each silence is asserted
here rather than assumed. The descriptors are built by hand — the lint is pure over them, so the
table needs no library window and no crate.
"""

import pytest

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.core.pipes.variable_multiplicity import PresenceMarker
from pipelex.pipeline.input_form import (
    BooleanField,
    DateField,
    DocumentField,
    EnumField,
    ImageField,
    InputFormField,
    ListField,
    NumberField,
    ObjectField,
    PipeInputFormDescriptor,
    ProseField,
    TextField,
    UnknownField,
)
from pipelex.pipeline.vacuous_presence_warnings import build_vacuous_presence_warnings

ENTRY_PIPE_REF = "demo.run"
OPTIONS_CONCEPT_REF = "demo.RunOptions"


def _nested(*, name: str, required: bool) -> InputFormField:
    """A structure field inside an object node (no slot facts: no presence, no gating)."""
    return TextField(name=name, required=required)


def _object_slot(
    *,
    name: str = "opts",
    nested_fields: list[InputFormField] | None = None,
    presence: PresenceMarker = PresenceMarker.PLAIN,
    required: bool = True,
    gating: bool | None = True,
    concept_ref: str | None = OPTIONS_CONCEPT_REF,
) -> InputFormField:
    """A top-level object slot, defaulting to the all-optional shape the lint fires on."""
    return ObjectField(
        name=name,
        concept_ref=concept_ref,
        required=required,
        presence=presence,
        gating=gating,
        fields=[_nested(name="tone", required=False)] if nested_fields is None else nested_fields,
    )


def _object_item() -> InputFormField:
    """The all-optional object as a list's `item` node: a concept node, so no slot facts."""
    return ObjectField(
        name="opts",
        concept_ref=OPTIONS_CONCEPT_REF,
        required=True,
        fields=[_nested(name="tone", required=False)],
    )


def _lint(*, slots: list[InputFormField], pipe_ref: str = ENTRY_PIPE_REF, entry_pipe_refs: list[str] | None = None) -> list[ValidationErrorItem]:
    return build_vacuous_presence_warnings(
        input_form={pipe_ref: PipeInputFormDescriptor(fields=slots)},
        entry_pipe_refs=entry_pipe_refs if entry_pipe_refs is not None else [ENTRY_PIPE_REF],
    )


class TestVacuousPresenceWarnings:
    # ---- Fires ------------------------------------------------------------------------------

    def test_all_optional_object_warns(self):
        warnings = _lint(slots=[_object_slot()])
        assert len(warnings) == 1
        assert "declares no required field" in warnings[0].message
        assert "an empty object satisfies it" in warnings[0].message

    def test_field_less_object_warns_with_the_variant_wording(self):
        warnings = _lint(slots=[_object_slot(nested_fields=[])])
        assert len(warnings) == 1
        message = warnings[0].message
        assert "declares no field at all" in message
        assert "an empty object satisfies it" in message
        assert f"give '{OPTIONS_CONCEPT_REF}' a required field" in message

    def test_plain_input_message_names_the_absent_marker_and_both_remedies(self):
        message = _lint(slots=[_object_slot()])[0].message
        assert f"Input 'opts' of pipe '{ENTRY_PIPE_REF}' must be supplied (declared without '?')" in message
        assert f'`opts = "{OPTIONS_CONCEPT_REF}?"`' in message
        assert f"make at least one field of '{OPTIONS_CONCEPT_REF}' required" in message

    def test_force_input_warns_and_names_the_marker(self):
        warnings = _lint(slots=[_object_slot(presence=PresenceMarker.FORCE)])
        assert len(warnings) == 1
        assert "declared with a force marker '!'" in warnings[0].message

    def test_item_shape_carries_the_pipe_locator_and_no_concept_code(self):
        warning = _lint(slots=[_object_slot()])[0]
        assert warning.category == ValidationErrorCategory.PIPE_VALIDATION
        assert warning.error_type == "input_presence_vacuous"
        assert warning.pipe_code == "run"
        assert warning.domain_code == "demo"
        assert warning.variable_names == ["opts"]
        assert warning.concept_code is None

    def test_a_hierarchical_domain_keeps_its_full_path_in_the_locator(self):
        """A domain is a dotted path, so the ref splits at its LAST dot, not its first."""
        warning = _lint(slots=[_object_slot()], pipe_ref="legal.contracts.run", entry_pipe_refs=["legal.contracts.run"])[0]

        assert warning.domain_code == "legal.contracts"
        assert warning.pipe_code == "run"

    # ---- Silent -----------------------------------------------------------------------------

    def test_one_required_field_is_silent(self):
        slot = _object_slot(nested_fields=[_nested(name="tone", required=False), _nested(name="topic", required=True)])
        assert _lint(slots=[slot]) == []

    def test_optional_presence_is_silent(self):
        assert _lint(slots=[_object_slot(required=False, presence=PresenceMarker.OPTIONAL, gating=False)]) == []

    def test_a_non_gating_object_slot_is_silent_even_when_required(self):
        """The lint keys on `gating` — the descriptor's stated "block Run until this has content" —
        never on `required`. The two coincide on every object node the deriver builds today, so this
        is the only case that can tell the two reads apart, and it is the rule the design states.
        """
        assert _lint(slots=[_object_slot(required=True, gating=False)]) == []

    def test_variable_multiplicity_list_is_silent(self):
        """`Concept[]` never gates by the descriptor's own rule — `[]` is its legitimate value."""
        slot = ListField(
            name="opts",
            concept_ref=OPTIONS_CONCEPT_REF,
            required=True,
            presence=PresenceMarker.PLAIN,
            gating=False,
            item=_object_item(),
        )
        assert _lint(slots=[slot]) == []

    def test_fixed_count_list_is_silent(self):
        """`Concept[N]` gates, but the vacuity question is per item — deferred (design §7)."""
        slot = ListField(
            name="opts",
            concept_ref=OPTIONS_CONCEPT_REF,
            required=True,
            presence=PresenceMarker.PLAIN,
            gating=True,
            item=_object_item(),
            item_count=2,
        )
        assert _lint(slots=[slot]) == []

    @pytest.mark.parametrize(
        "slot",
        [
            TextField(name="opts", required=True, presence=PresenceMarker.PLAIN, gating=True),
            ProseField(name="opts", required=True, presence=PresenceMarker.PLAIN, gating=True),
            NumberField(name="opts", required=True, presence=PresenceMarker.PLAIN, gating=True, integer=False),
            BooleanField(name="opts", required=True, presence=PresenceMarker.PLAIN, gating=True),
            DateField(name="opts", required=True, presence=PresenceMarker.PLAIN, gating=True, datetime=False),
            EnumField(name="opts", required=True, presence=PresenceMarker.PLAIN, gating=True, choices=["a", "b"]),
            DocumentField(name="opts", required=True, presence=PresenceMarker.PLAIN, gating=True),
            ImageField(name="opts", required=True, presence=PresenceMarker.PLAIN, gating=True),
            UnknownField(name="opts", required=True, presence=PresenceMarker.PLAIN, gating=True),
        ],
        ids=["text", "prose", "number", "boolean", "date", "enum", "document", "image", "unknown"],
    )
    def test_non_object_kinds_are_silent(self, slot: InputFormField):
        assert _lint(slots=[slot]) == []

    def test_a_non_entry_pipe_with_the_warning_shape_is_silent(self):
        assert _lint(slots=[_object_slot()], pipe_ref="demo.helper") == []

    def test_no_entry_pipes_means_no_lint(self):
        assert _lint(slots=[_object_slot()], entry_pipe_refs=[]) == []

    def test_an_entry_ref_absent_from_the_input_form_is_silent(self):
        assert build_vacuous_presence_warnings(input_form={}, entry_pipe_refs=[ENTRY_PIPE_REF]) == []

    def test_a_concept_less_object_node_is_silent(self):
        """With no `concept_ref` there is no concept to name, hence no honest message to state."""
        assert _lint(slots=[_object_slot(concept_ref=None)]) == []

    # ---- Ordering ---------------------------------------------------------------------------

    def test_output_is_by_entry_pipe_ref_then_authored_slot_order(self):
        input_form = {
            "demo.zeta": PipeInputFormDescriptor(fields=[_object_slot(name="zulu"), _object_slot(name="alpha")]),
            "demo.alpha": PipeInputFormDescriptor(fields=[_object_slot(name="yankee")]),
        }
        warnings = build_vacuous_presence_warnings(input_form=input_form, entry_pipe_refs=["demo.zeta", "demo.alpha"])
        assert [(warning.pipe_code, warning.variable_names) for warning in warnings] == [
            ("alpha", ["yankee"]),
            ("zeta", ["zulu"]),
            ("zeta", ["alpha"]),
        ]

    def test_a_repeated_entry_ref_warns_once(self):
        warnings = build_vacuous_presence_warnings(
            input_form={ENTRY_PIPE_REF: PipeInputFormDescriptor(fields=[_object_slot()])},
            entry_pipe_refs=[ENTRY_PIPE_REF, ENTRY_PIPE_REF],
        )
        assert len(warnings) == 1
