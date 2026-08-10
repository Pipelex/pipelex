import datetime

import pytest
from pydantic import BaseModel, ValidationError

from pipelex.core.stuffs.date_content import DateContent


class TestDateContentStrictMode:
    """Structured outputs are validated in strict mode, so a live `PipeLLM` must still land a `Date`.

    Instructor validates every LLM response with `strict=True`, and a `mode="before"` validator
    forfeits pydantic's strict-JSON acceptance of ISO strings — so the validator must return a real
    `date`/`time` object. These cases pin the exact live-run failure and both strict flavours.
    """

    def test_strict_json_date_only(self):
        """The reported `ListOfDateContent` item shape: a bare ISO calendar date."""
        content = DateContent.model_validate_json('{"date": "2025-03-12"}', strict=True)
        assert content.date == datetime.date(2025, 3, 12)
        assert content.time is None

    def test_strict_json_date_and_time_preserves_offset(self):
        """The reported single-`Date` failure: both fields at once, offset kept as stated."""
        content = DateContent.model_validate_json('{"date": "2025-03-12", "time": "14:00:00+00:00"}', strict=True)
        assert content.date == datetime.date(2025, 3, 12)
        assert content.time is not None
        assert content.time.utcoffset() == datetime.timedelta(0)
        assert content.rendered_plain() == "2025-03-12T14:00:00+00:00"

    def test_strict_python_mode(self):
        """Instructor modes that validate an already-parsed dict go through strict Python validation."""
        content = DateContent.model_validate({"date": "2025-03-12", "time": "14:00:00"}, strict=True)
        assert content.date == datetime.date(2025, 3, 12)
        assert content.time == datetime.time(14, 0)

    def test_strict_json_list_wrapper(self):
        """The reported case was the generated `ListOf...` wrapper, whose items validate the same way."""

        class ListOfDateContent(BaseModel):
            items: list[DateContent]

        wrapper = ListOfDateContent.model_validate_json('{"items": [{"date": "2025-03-12"}, {"date": "2025-03-14"}]}', strict=True)
        assert [item.date for item in wrapper.items] == [datetime.date(2025, 3, 12), datetime.date(2025, 3, 14)]

    def test_strict_accepts_real_objects(self):
        """The `--mock-inputs` path supplies real objects; they must pass through untouched."""
        content = DateContent.model_validate({"date": datetime.date(2026, 7, 7), "time": datetime.time(15, 40)}, strict=True)
        assert content.date == datetime.date(2026, 7, 7)
        assert content.time == datetime.time(15, 40)

    @pytest.mark.parametrize(
        "payload",
        [
            {"date": 86400},
            {"date": "86400"},
            {"date": "8.64e4"},
            {"date": "20250312"},  # epoch-lookalike: `fromisoformat` would accept it, the epoch guard must not
            {"date": datetime.datetime(2026, 7, 7, 15, 40)},
            {"date": "2026-07-07T00:00:00"},
            {"date": "2026-07-07", "time": 3600},
            {"date": "2026-07-07", "time": "3600"},
        ],
    )
    def test_rejections_hold_in_both_modes(self, payload: dict[str, object]):
        """Every guard must fire under strict validation exactly as it does under lax."""
        with pytest.raises(ValidationError):
            DateContent.model_validate(payload)
        with pytest.raises(ValidationError):
            DateContent.model_validate(payload, strict=True)

    @pytest.mark.parametrize("payload", [{"date": "not-a-date"}, {"date": "2026-07-07", "time": "not-a-time"}])
    def test_malformed_string_names_the_field(self, payload: dict[str, object]):
        """A string that is neither epoch-shaped nor ISO must fail with a message naming the expectation."""
        with pytest.raises(ValidationError, match="ISO 8601"):
            DateContent.model_validate(payload, strict=True)
