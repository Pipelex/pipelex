from collections.abc import Callable

import pytest

from pipelex.system.exceptions import InvocationPathError
from pipelex.system.invocation_path import (
    DEFAULT_OUTCOME_SEGMENT,
    branch_segment,
    child_path,
    item_segment,
    outcome_segment,
    step_segment,
)


class TestInvocationPath:
    def test_ordinal_segments_count_from_one(self) -> None:
        assert (step_segment(step_number=3), branch_segment(branch_number=1), item_segment(item_number=12)) == ("step_3", "branch_1", "item_12")
        assert DEFAULT_OUTCOME_SEGMENT == "default"

    @pytest.mark.parametrize(
        ("build", "segment_kind"),
        [
            (lambda: step_segment(step_number=0), "step"),
            (lambda: branch_segment(branch_number=-1), "branch"),
            (lambda: item_segment(item_number=0), "item"),
        ],
        ids=["step_zero", "negative_branch", "item_zero"],
    )
    def test_an_ordinal_below_one_names_no_segment(self, build: Callable[[], str], segment_kind: str) -> None:
        with pytest.raises(InvocationPathError, match=f"'{segment_kind}' segment counts from 1"):
            build()

    @pytest.mark.parametrize(
        ("outcome_key", "expected_segment"),
        [
            ("detailed", "outcome_detailed"),
            ("high risk", "outcome_high%20risk"),
            ("legal/tax review", "outcome_legal%2Ftax%20review"),
            ("a-b.c_d~e", "outcome_a-b.c_d~e"),
            ("décision", "outcome_d%C3%A9cision"),
            ("50%", "outcome_50%25"),
        ],
        ids=["plain", "space", "slash", "unreserved_kept", "utf8_upper_hex", "percent"],
    )
    def test_an_outcome_key_is_percent_encoded(self, outcome_key: str, expected_segment: str) -> None:
        segment = outcome_segment(outcome_key=outcome_key)
        assert segment == expected_segment
        assert "/" not in segment

    def test_a_child_path_adds_one_segment(self) -> None:
        batch_path = child_path(parent_path="filings.review_filings", segment=step_segment(step_number=3))
        assert child_path(parent_path=batch_path, segment=item_segment(item_number=2)) == "filings.review_filings/step_3/item_2"
