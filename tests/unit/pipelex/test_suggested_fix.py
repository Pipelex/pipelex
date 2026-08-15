"""Unit tests for the suggested-fix wire models (``pipelex/suggested_fix.py``).

``SuggestedFix`` rides ``ValidationErrorItem.suggested_fix`` — the additive, optional,
runtime-only wire field (D2). These tests pin the serialization round-trip and the
``exclude_none`` invariant: a non-fixable error item serializes byte-identically to
what it was before the field existed.
"""

import json

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.suggested_fix import FixOpKind, FixSafety, SetKeyOp, SuggestedFix


def _sample_fix() -> SuggestedFix:
    return SuggestedFix(
        fix_code="match-sequence-output",
        description="Set output to 'Idea[]' to match the last step",
        safety=FixSafety.SAFE,
        source="main.mthds",
        ops=[
            SetKeyOp(
                table_path=["pipe", "list_ideas"],
                key="output",
                value="Idea[]",
            ),
        ],
    )


class TestSuggestedFixModels:
    def test_round_trip_preserves_all_fields(self) -> None:
        """A SuggestedFix survives a JSON dump/load round-trip unchanged."""
        fix = _sample_fix()
        reloaded = SuggestedFix.model_validate_json(fix.model_dump_json())
        assert reloaded == fix
        assert reloaded.ops[0].kind == FixOpKind.SET_KEY
        assert reloaded.ops[0].table_path == ["pipe", "list_ideas"]
        assert reloaded.ops[0].value == "Idea[]"
        assert reloaded.safety == FixSafety.SAFE

    def test_enum_fields_serialize_to_plain_strings(self) -> None:
        """StrEnum fields ride the wire as their plain string values."""
        dumped = _sample_fix().model_dump(mode="json")
        assert dumped["safety"] == "safe"
        assert dumped["ops"][0]["kind"] == "set_key"

    def test_validation_error_item_carries_suggested_fix(self) -> None:
        """ValidationErrorItem gains the optional suggested_fix field and dumps it when set."""
        item = ValidationErrorItem(
            category=ValidationErrorCategory.PIPE_VALIDATION,
            message="output mismatch",
            pipe_code="list_ideas",
            suggested_fix=_sample_fix(),
        )
        dumped = item.model_dump(mode="json", exclude_none=True)
        assert dumped["suggested_fix"]["fix_code"] == "match-sequence-output"
        assert dumped["suggested_fix"]["ops"][0]["key"] == "output"

    def test_non_fixable_item_stays_byte_identical(self) -> None:
        """An item without a fix serializes with NO suggested_fix key — byte-identical to today."""
        item = ValidationErrorItem(
            category=ValidationErrorCategory.PIPE_VALIDATION,
            message="output mismatch",
            pipe_code="list_ideas",
        )
        dumped = item.model_dump(mode="json", exclude_none=True)
        assert "suggested_fix" not in dumped
        assert json.dumps(dumped, sort_keys=True) == json.dumps(
            {"category": "pipe_validation", "message": "output mismatch", "pipe_code": "list_ideas"},
            sort_keys=True,
        )

    def test_op_wire_shape_is_exactly_its_variant_fields(self) -> None:
        """An op carries its own fields and no others — no ``exclude_none`` projection needed.

        Under the flat model this needed ``exclude_none=True`` to keep a ``set_key``'s unused
        ``new_key`` off the wire. The union removes the question: ``SetKeyOp`` has no such field,
        so the plain dump is already the minimal shape.
        """
        dumped = _sample_fix().model_dump(mode="json")
        assert set(dumped["ops"][0]) == {"kind", "table_path", "key", "value"}
