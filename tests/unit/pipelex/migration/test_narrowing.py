"""Unit tests for the narrowing relation — which schema changes shrink the values a file may carry.

The relation is tested on hand-built `PathFingerprint` records rather than on models, because what
is under test is the *comparison*, not the projection that feeds it. Two directions matter equally
and are asserted equally: a narrowing that goes unreported ships a change that breaks a user's boot
with a green gate behind it, and a widening reported as a narrowing is a gate crying wolf, which is
how a gate gets waved through and then ignored.
"""

import pytest

from pipelex.migration.fingerprint import ConstraintKind, PathFingerprint
from pipelex.migration.narrowing import describe_narrowing, lost_enumerated_spellings


def _record(
    *,
    value_type: str = "int",
    enum_members: list[str] | None = None,
    constraints: dict[ConstraintKind, int | float] | None = None,
) -> PathFingerprint:
    return PathFingerprint(value_type=value_type, required=True, enum_members=enum_members, constraints=constraints)


class TestTheNarrowingRelation:
    @pytest.mark.parametrize(
        ("before_type", "after_type"),
        [
            ("int", "str"),
            ("str", "enum"),
            ("list[str]", "list[int]"),
            ("int | str", "int"),
            ("str", "table"),
        ],
    )
    def test_a_type_that_stops_accepting_what_it_accepted_is_a_narrowing(self, before_type: str, after_type: str) -> None:
        reasons = describe_narrowing(before=_record(value_type=before_type), after=_record(value_type=after_type))
        assert reasons == [f"its type went from '{before_type}' to '{after_type}'"]

    @pytest.mark.parametrize(
        ("before_type", "after_type"),
        [
            ("int", "int | str"),
            ("enum", "str"),
            ("literal", "str"),
            ("enum | literal", "str"),
            ("enum", "enum | int"),
        ],
    )
    def test_a_type_that_still_accepts_everything_it_did_is_not(self, before_type: str, after_type: str) -> None:
        """Both widening shapes: a union that gains members, and an enumerated type relaxed into `str`."""
        assert describe_narrowing(before=_record(value_type=before_type), after=_record(value_type=after_type)) == []

    def test_a_union_inside_a_container_is_one_member_not_two(self) -> None:
        """Splitting a rendered type on `|` without respecting brackets would read this as a widening."""
        reasons = describe_narrowing(before=_record(value_type="list[int | str]"), after=_record(value_type="int"))
        assert reasons == ["its type went from 'list[int | str]' to 'int'"]

    @pytest.mark.parametrize(
        ("before_constraints", "after_constraints", "expected_fragment"),
        [
            ({}, {ConstraintKind.GE: 1}, "its lower bound tightened from unbounded to ge=1"),
            ({ConstraintKind.GE: 1}, {ConstraintKind.GE: 5}, "its lower bound tightened from ge=1 to ge=5"),
            ({ConstraintKind.GE: 0}, {ConstraintKind.GT: 0}, "its lower bound tightened from ge=0 to gt=0"),
            ({ConstraintKind.LE: 10}, {ConstraintKind.LE: 6}, "its upper bound tightened from le=10 to le=6"),
            ({}, {ConstraintKind.MAX_LENGTH: 40}, "its maximum length tightened from unbounded to max_length=40"),
            ({ConstraintKind.MIN_LENGTH: 1}, {ConstraintKind.MIN_LENGTH: 3}, "its minimum length tightened from min_length=1 to min_length=3"),
            ({ConstraintKind.MULTIPLE_OF: 2}, {ConstraintKind.MULTIPLE_OF: 4}, "its step tightened from multiple_of=2 to multiple_of=4"),
            ({ConstraintKind.MULTIPLE_OF: 2}, {ConstraintKind.MULTIPLE_OF: 3}, "its step tightened from multiple_of=2 to multiple_of=3"),
        ],
    )
    def test_a_tightened_bound_is_a_narrowing(
        self,
        before_constraints: dict[ConstraintKind, int | float],
        after_constraints: dict[ConstraintKind, int | float],
        expected_fragment: str,
    ) -> None:
        reasons = describe_narrowing(before=_record(constraints=before_constraints), after=_record(constraints=after_constraints))
        assert reasons == [expected_fragment]

    @pytest.mark.parametrize(
        ("before_constraints", "after_constraints"),
        [
            ({ConstraintKind.GE: 5}, {ConstraintKind.GE: 1}),
            ({ConstraintKind.GE: 1}, {}),
            ({ConstraintKind.GT: 0}, {ConstraintKind.GE: 0}),
            ({ConstraintKind.LE: 6}, {ConstraintKind.LE: 10}),
            ({ConstraintKind.MAX_LENGTH: 40}, {}),
            ({ConstraintKind.MULTIPLE_OF: 4}, {ConstraintKind.MULTIPLE_OF: 2}),
            ({ConstraintKind.MULTIPLE_OF: 2}, {ConstraintKind.MULTIPLE_OF: 2}),
        ],
    )
    def test_a_relaxed_or_dropped_bound_is_not(
        self,
        before_constraints: dict[ConstraintKind, int | float],
        after_constraints: dict[ConstraintKind, int | float],
    ) -> None:
        """A bound that admits more values than it did asks for nothing: every old file survives it."""
        assert describe_narrowing(before=_record(constraints=before_constraints), after=_record(constraints=after_constraints)) == []

    def test_both_halves_are_reported_together(self) -> None:
        """One path can move both ways at once, and the author needs to read both reasons."""
        reasons = describe_narrowing(
            before=_record(value_type="int | str", constraints={ConstraintKind.LE: 10}),
            after=_record(value_type="int", constraints={ConstraintKind.LE: 6}),
        )
        assert reasons == ["its type went from 'int | str' to 'int'", "its upper bound tightened from le=10 to le=6"]

    def test_an_unchanged_record_narrows_nothing(self) -> None:
        record = _record(value_type="int", constraints={ConstraintKind.GE: 1, ConstraintKind.LE: 10})
        assert describe_narrowing(before=record, after=record) == []

    def test_a_spelling_the_new_member_set_lacks_is_lost(self) -> None:
        lost = lost_enumerated_spellings(
            before=_record(value_type="enum", enum_members=["basic", "premium"]),
            after=_record(value_type="enum", enum_members=["premium"]),
        )
        assert lost == ["basic"]

    def test_an_enum_relaxed_into_a_free_string_loses_no_spelling(self) -> None:
        """The set difference says every member vanished; the truth is that `str` accepts them all.

        Left as a raw difference, the most benign loosening a config model can undergo would demand
        a version bump and a remap for every spelling it had.
        """
        lost = lost_enumerated_spellings(
            before=_record(value_type="enum", enum_members=["basic", "premium"]),
            after=_record(value_type="str"),
        )
        assert lost == []

    def test_an_enum_that_became_something_else_entirely_still_loses_its_spellings(self) -> None:
        """The exemption is for widening only — `int` accepts none of the spellings `str` did."""
        lost = lost_enumerated_spellings(
            before=_record(value_type="enum", enum_members=["basic", "premium"]),
            after=_record(value_type="int"),
        )
        assert lost == ["basic", "premium"]
