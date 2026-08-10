import datetime

import pytest
from pydantic import BaseModel, ValidationError

from pipelex.core.stuffs.time_content import TimeContent


class TestTimeContentStrictMode:
    """Structured outputs are validated in strict mode, so a live `PipeLLM` must still land a `Time`.

    Instructor validates every LLM response with `strict=True`, and a `mode="before"` validator
    forfeits pydantic's strict-JSON acceptance of ISO strings — so the validator must return a real
    `time` object. These cases pin the exact live-run failure and both strict flavours.
    """

    def test_strict_json_preserves_offset(self):
        """The reported failure: `'14:00:00+00:00'` refused with `time_type` under strict JSON."""
        content = TimeContent.model_validate_json('{"time": "14:00:00+00:00"}', strict=True)
        assert content.time.utcoffset() == datetime.timedelta(0)
        assert content.rendered_plain() == "14:00:00+00:00"

    @pytest.mark.parametrize(
        ("iso_time", "expected"),
        [
            ("14:00:00Z", datetime.time(14, 0, tzinfo=datetime.UTC)),
            ("15:40:00.500", datetime.time(15, 40, 0, 500000)),
            ("15:40:00+02:00", datetime.time(15, 40, tzinfo=datetime.timezone(datetime.timedelta(hours=2)))),
        ],
    )
    def test_strict_json_iso_variants(self, iso_time: str, expected: datetime.time):
        """`Z` suffix, fractional seconds and offsets are all shapes a model legitimately answers."""
        content = TimeContent.model_validate_json(f'{{"time": "{iso_time}"}}', strict=True)
        assert content.time == expected

    def test_strict_python_mode(self):
        """Instructor modes that validate an already-parsed dict go through strict Python validation."""
        content = TimeContent.model_validate({"time": "14:00:00"}, strict=True)
        assert content.time == datetime.time(14, 0)

    def test_strict_json_list_wrapper(self):
        """The generated `ListOf...` wrapper validates its items the same way."""

        class ListOfTimeContent(BaseModel):
            items: list[TimeContent]

        wrapper = ListOfTimeContent.model_validate_json('{"items": [{"time": "09:00:00"}, {"time": "14:00:00+00:00"}]}', strict=True)
        assert [item.time.hour for item in wrapper.items] == [9, 14]

    def test_strict_accepts_real_objects(self):
        """The `--mock-inputs` path supplies real objects; they must pass through untouched."""
        content = TimeContent.model_validate({"time": datetime.time(15, 40)}, strict=True)
        assert content.time == datetime.time(15, 40)

    @pytest.mark.parametrize(
        "payload",
        [
            {"time": 56400},
            {"time": "56400"},
            {"time": "5.64e4"},
            {"time": datetime.datetime(2026, 7, 10, 15, 40)},
        ],
    )
    def test_rejections_hold_in_both_modes(self, payload: dict[str, object]):
        """Every guard must fire under strict validation exactly as it does under lax."""
        with pytest.raises(ValidationError):
            TimeContent.model_validate(payload)
        with pytest.raises(ValidationError):
            TimeContent.model_validate(payload, strict=True)

    def test_malformed_string_names_the_expectation(self):
        """A string that is neither epoch-shaped nor ISO must fail with a message naming the expectation."""
        with pytest.raises(ValidationError, match="ISO 8601"):
            TimeContent.model_validate({"time": "not-a-time"}, strict=True)
