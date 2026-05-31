"""Tests for the ``UserAction`` model and ``UserActionKind`` enum.

The structured ``user_action`` field replaces the free-form string so that the
CLI can render consistent advice and agent JSON can be typed.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.types import StrEnum


class TestUserAction:
    """``UserActionKind`` is a ``StrEnum`` and ``UserAction`` is a ``BaseModel`` with ``kind`` + ``detail``."""

    def test_user_action_kind_is_strenum(self) -> None:
        assert issubclass(UserActionKind, StrEnum)

    def test_user_action_kind_has_expected_members(self) -> None:
        expected = {
            "WAIT_AND_RETRY",
            "CHECK_BILLING",
            "CHECK_CREDENTIALS",
            "CHANGE_INPUT",
            "CHANGE_MODEL",
            "CONTACT_SUPPORT",
            "UNKNOWN",
        }
        actual = {member.name for member in UserActionKind}
        assert actual == expected

    def test_user_action_kind_values_match_lowercase_names(self) -> None:
        for member in UserActionKind:
            assert member == member.name.lower()

    def test_user_action_holds_kind_and_detail(self) -> None:
        action = UserAction(kind=UserActionKind.WAIT_AND_RETRY, detail="Rate limited — will retry")
        assert action.kind is UserActionKind.WAIT_AND_RETRY
        assert action.detail == "Rate limited — will retry"

    def test_user_action_requires_kind(self) -> None:
        with pytest.raises(ValidationError):
            UserAction(detail="missing kind")  # type: ignore[call-arg]

    def test_user_action_requires_detail(self) -> None:
        with pytest.raises(ValidationError):
            UserAction(kind=UserActionKind.UNKNOWN)  # type: ignore[call-arg]

    def test_user_action_round_trips(self) -> None:
        action = UserAction(kind=UserActionKind.CHECK_BILLING, detail="Account quota exceeded")
        dumped = action.model_dump()
        rebuilt = UserAction.model_validate(dumped)
        assert rebuilt == action
        assert dumped == {"kind": "check_billing", "detail": "Account quota exceeded"}
