"""The expanded input-slot form (spec: intent-hints.md): strict shape, the parse-time collapse
rule, grammar parity between the two arms, and fingerprint-neutral serialization.
"""

import json

import pytest
from pydantic import ValidationError

from pipelex.pipe_machinery.pipe_blueprint import InputSlotBlueprint, PipeBlueprint, slot_concept_spec


class ConcretePipeBlueprint(PipeBlueprint):
    pass


def make_blueprint(inputs: dict[str, object]) -> ConcretePipeBlueprint:
    return ConcretePipeBlueprint.model_validate(
        {
            "type": "PipeLLM",
            "pipe_category": "PipeOperator",
            "description": "slot-form test pipe",
            "inputs": inputs,
            "output": "Text",
        }
    )


class TestInputSlotAcceptance:
    def test_hinted_table_is_kept_as_slot_blueprint(self):
        blueprint = make_blueprint({"doc": {"concept": "Text", "hints": {"intent": "prose"}}})
        assert blueprint.inputs is not None
        slot = blueprint.inputs["doc"]
        assert isinstance(slot, InputSlotBlueprint)
        assert slot.concept == "Text"
        assert slot.hints == {"intent": "prose"}

    def test_unknown_hint_key_is_preserved(self):
        # Content is lenient: an unknown, well-formed hint entry parses and survives.
        blueprint = make_blueprint({"doc": {"concept": "Text", "hints": {"emphasis": "strong"}}})
        assert blueprint.inputs is not None
        slot = blueprint.inputs["doc"]
        assert isinstance(slot, InputSlotBlueprint)
        assert slot.hints == {"emphasis": "strong"}

    def test_hints_keys_are_sorted(self):
        blueprint = make_blueprint({"doc": {"concept": "Text", "hints": {"zeta": "z", "alpha": "a"}}})
        assert blueprint.inputs is not None
        slot = blueprint.inputs["doc"]
        assert isinstance(slot, InputSlotBlueprint)
        assert list(slot.hints or {}) == ["alpha", "zeta"]

    def test_marked_concept_travels_through_the_table_arm(self):
        blueprint = make_blueprint(
            {"many": {"concept": "Widget[]", "hints": {"intent": "label"}}, "opt": {"concept": "Text?", "hints": {"intent": "prose"}}}
        )
        assert blueprint.inputs is not None
        assert slot_concept_spec(blueprint.inputs["many"]) == "Widget[]"
        assert slot_concept_spec(blueprint.inputs["opt"]) == "Text?"


class TestInputSlotCollapse:
    def test_table_without_hints_collapses_to_string(self):
        blueprint = make_blueprint({"doc": {"concept": "Text"}})
        assert blueprint.inputs is not None
        assert blueprint.inputs["doc"] == "Text"

    def test_table_with_empty_hints_collapses_to_string(self):
        blueprint = make_blueprint({"doc": {"concept": "Text?", "hints": {}}})
        assert blueprint.inputs is not None
        assert blueprint.inputs["doc"] == "Text?"

    def test_collapsed_blueprint_equals_string_form(self):
        expanded = make_blueprint({"doc": {"concept": "Text"}})
        plain = make_blueprint({"doc": "Text"})
        assert expanded.model_dump(mode="json") == plain.model_dump(mode="json")


class TestInputSlotRejection:
    def test_unknown_slot_table_key_is_rejected(self):
        with pytest.raises(ValidationError, match=r"[Ee]xtra"):
            make_blueprint({"doc": {"concept": "Text", "description": "the document"}})

    def test_non_table_hints_are_rejected(self):
        with pytest.raises(ValidationError):
            make_blueprint({"doc": {"concept": "Text", "hints": "prose"}})

    def test_non_string_hint_value_is_rejected(self):
        with pytest.raises(ValidationError):
            make_blueprint({"doc": {"concept": "Text", "hints": {"intent": 3}}})

    def test_nested_hint_table_is_rejected(self):
        with pytest.raises(ValidationError):
            make_blueprint({"doc": {"concept": "Text", "hints": {"intent": {"word": "prose"}}}})

    def test_table_arm_concept_passes_the_slot_grammar(self):
        with pytest.raises(ValidationError):
            make_blueprint({"doc": {"concept": "not a concept ref !!", "hints": {"intent": "prose"}}})


class TestInputsConceptSpecsProjection:
    def test_projection_reads_both_arms(self):
        blueprint = make_blueprint({"plain": "Text", "hinted": {"concept": "Widget[]", "hints": {"intent": "label"}}})
        assert blueprint.inputs_concept_specs == {"plain": "Text", "hinted": "Widget[]"}

    def test_projection_is_none_when_inputs_absent(self):
        blueprint = ConcretePipeBlueprint(
            type="PipeLLM",
            pipe_category="PipeOperator",
            description="no inputs",
            output="Text",
        )
        assert blueprint.inputs_concept_specs is None


class TestInputSlotSerialization:
    def test_hint_free_pipe_serializes_without_hints_key_at_any_depth(self):
        blueprint = make_blueprint({"doc": {"concept": "Text"}, "plain": "Widget"})
        assert '"hints"' not in json.dumps(blueprint.model_dump(mode="json"))

    def test_directly_constructed_hint_free_slot_drops_the_member(self):
        slot = InputSlotBlueprint(concept="Text")
        assert slot.model_dump(mode="json") == {"concept": "Text"}

    def test_hinted_slot_serializes_hints(self):
        blueprint = make_blueprint({"doc": {"concept": "Text", "hints": {"intent": "prose"}}})
        dumped = blueprint.model_dump(mode="json")
        assert dumped["inputs"]["doc"] == {"concept": "Text", "hints": {"intent": "prose"}}
