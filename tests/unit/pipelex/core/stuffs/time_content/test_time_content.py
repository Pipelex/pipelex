import datetime

import pytest
from pydantic import ValidationError

from pipelex.core.stuffs.time_content import TimeContent


class TestTimeContent:
    """TimeContent fidelity rules: ISO time of day, offset kept when stated, never a number."""

    def test_iso_string_round_trip(self):
        content = TimeContent(time="15:40:00")  # pyright: ignore[reportArgumentType] — pydantic lax ISO parsing is the point
        assert content.time == datetime.time(15, 40)
        assert content.rendered_plain() == "15:40:00"
        assert TimeContent.model_validate(content.model_dump(mode="json")) == content

    def test_offset_is_preserved(self):
        content = TimeContent(time="15:40:00+02:00")  # pyright: ignore[reportArgumentType]
        assert content.time.utcoffset() == datetime.timedelta(hours=2)
        assert content.rendered_plain() == "15:40:00+02:00"
        assert TimeContent.model_validate(content.model_dump(mode="json")) == content

    def test_number_is_rejected(self):
        """A bare number must never be read as seconds-since-midnight."""
        with pytest.raises(ValidationError):
            TimeContent.model_validate({"time": 56400})

    @pytest.mark.parametrize("value", ["56400", "+56400", "56400.0", "5.64e4"])
    def test_numeric_string_is_rejected(self, value: str):
        """Pydantic must not reinterpret number-shaped strings as seconds-since-midnight."""
        with pytest.raises(ValidationError):
            TimeContent.model_validate({"time": value})

    def test_datetime_is_rejected(self):
        """A datetime carries a date — that belongs to Date, not Time."""
        with pytest.raises(ValidationError):
            TimeContent.model_validate({"time": datetime.datetime(2026, 7, 10, 15, 40)})
