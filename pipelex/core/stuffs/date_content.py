import datetime
import json
from typing import Any

from pydantic import Field, field_validator
from typing_extensions import override

from pipelex.core.stuffs.exceptions import DateContentError
from pipelex.core.stuffs.stuff_content import StuffContent


class DateContent(StuffContent):
    """A calendar date, optionally with a time of day — as precise as its source states.

    The optional ``time`` carries the UTC offset on its ``tzinfo`` when the source states one
    (fidelity, not normalization). Invalid states are unrepresentable by construction: no time
    without a date, no offset without a time.
    """

    date: datetime.date = Field(description="The calendar date, in ISO 8601 (e.g. 2026-07-07). Always required.")
    time: datetime.time | None = Field(
        default=None,
        description=(
            "The time of day, in ISO 8601 (e.g. 15:40:00, or 15:40:00+02:00 with a UTC offset). "
            "Include it only when the source states a time — never invent a time. "
            "Keep the UTC offset exactly when the source states one."
        ),
    )

    @field_validator("date", "time", mode="before")
    @classmethod
    def _reject_lax_temporal(cls, value: Any) -> Any:
        # Close pydantic's lax-mode coercions that would silently produce wrong temporal data — all
        # raise ValueError so pydantic wraps them into a ValidationError the input/factory path catches
        # (a raw TypeError would escape model_validate uncaught):
        #  - a bare int/float, or an all-digit string, is read as epoch seconds; a real ISO date/time
        #    always carries '-'/':' separators, so an all-digit string is only ever an epoch (DT6).
        #  - a datetime on the `date` field is silently truncated to the date, dropping its time and
        #    UTC offset — exactly the fidelity loss DT3 forbids ("no silent midnight").
        if isinstance(value, datetime.datetime):
            msg = "A Date's `date` field takes a calendar date, not a datetime; put the time and offset in `time` instead."
            raise ValueError(msg)  # noqa: TRY004 — must be ValueError so pydantic wraps it into a ValidationError
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):  # bool is an int subclass
            msg = "A Date's date/time must be an ISO 8601 string or a date/time object, never a number (no epoch-seconds)."
            raise ValueError(msg)
        return value

    def _iso(self) -> str:
        """ISO 8601 of exactly the stored precision: date alone, or date + time (with offset if present)."""
        if self.time is None:
            return self.date.isoformat()
        return f"{self.date.isoformat()}T{self.time.isoformat()}"

    def to_datetime(self) -> datetime.datetime:
        """Combine date and time into a ``datetime.datetime``.

        Raises:
            DateContentError: when there is no time of day — converting would invent one, which
                this concept refuses to do (a silent midnight is exactly the fabrication DT2 forbids).
        """
        if self.time is None:
            msg = "This Date has no time of day, so it cannot be converted to a datetime without inventing one."
            raise DateContentError(msg)
        return datetime.datetime.combine(self.date, self.time)

    @property
    @override
    def short_desc(self) -> str:
        if self.time is None:
            return f"a date ({self._iso()})"
        return f"a date and time ({self._iso()})"

    @override
    def rendered_plain(self) -> str:
        return self._iso()

    @override
    def rendered_html(self) -> str:
        return self._iso()

    @override
    def rendered_markdown(self, *, level: int = 1, is_pretty: bool = False) -> str:
        return self._iso()

    @override
    def rendered_json(self) -> str:
        return json.dumps({"date": self.date.isoformat(), "time": self.time.isoformat() if self.time is not None else None})
