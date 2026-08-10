import datetime
import json
from typing import Any

from pydantic import Field, field_validator
from rich.json import JSON
from typing_extensions import override

from pipelex.core.stuffs.iso_temporal import parse_iso_time
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.misc.pretty import PrettyPrintable
from pipelex.tools.misc.string_utils import is_numeric_string


class TimeContent(StuffContent):
    """A time of day, optionally with a UTC offset — as precise as its source states.

    The ``time`` carries the UTC offset on its ``tzinfo`` when the source states one
    (fidelity, not normalization). A time of day is not an instant: it has no date to
    attach to, so it never converts to a datetime on its own.
    """

    time: datetime.time = Field(description="The time of day, in ISO 8601 (e.g. 15:40:00, or 15:40:00+02:00 with a UTC offset).")

    @field_validator("time", mode="before")
    @classmethod
    def _validate_temporal(cls, value: Any) -> Any:
        # Reject what pydantic would coerce into silently wrong temporal data, then parse the ISO
        # strings that remain into a real time object. All rejections raise ValueError so pydantic
        # wraps them into a ValidationError the input/factory path catches.
        #  - a bare number, or any purely-numeric string, is read as seconds-since-midnight; a real
        #    ISO time always carries a ':' separator, so a numeric string is only ever a count of
        #    seconds. This guard must stay AHEAD of the parsing below, which would otherwise read the
        #    basic-format "154000" as 15:40:00.
        if isinstance(value, (int, float)) or (isinstance(value, str) and is_numeric_string(value)):  # bool is an int subclass
            msg = "A Time must be an ISO 8601 string or a time object, never a number (no seconds-since-midnight)."
            raise ValueError(msg)
        if isinstance(value, datetime.datetime):
            msg = "A Time takes a time of day alone, not a datetime; use Date for a date with a time."
            raise ValueError(msg)  # noqa: TRY004 — must be ValueError so pydantic wraps it into a ValidationError
        # Parsing the ISO string here — rather than leaving it to the field's own validation — is what
        # keeps this model usable under the strict validation instructor applies to every LLM response:
        # a mode="before" validator forfeits pydantic's strict-JSON acceptance of ISO strings, because
        # whatever it returns is re-validated as PYTHON input, where strict refuses a `str` outright
        # (time_type). Returning a real object satisfies strict JSON, strict Python and lax alike.
        # Non-str values — real time objects, e.g. from `--mock-inputs` — pass through. The parser pins
        # the extended ISO form, so a model and an author are held to one contract.
        if isinstance(value, str):
            return parse_iso_time(value)
        return value

    @property
    @override
    def short_desc(self) -> str:
        return f"a time of day ({self.time.isoformat()})"

    @override
    def rendered_plain(self) -> str:
        return self.time.isoformat()

    @override
    def rendered_html(self) -> str:
        return self.time.isoformat()

    @override
    def rendered_markdown(self, *, level: int = 1, is_pretty: bool = False) -> str:
        return self.time.isoformat()

    @override
    def rendered_json(self) -> str:
        return json.dumps({"time": self.time.isoformat()})

    @override
    def rendered_pretty(self, *, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        # The base renders smart_dump() (a real time object, which stdlib json can't serialize);
        # render the ISO JSON instead so pretty_print of a Time does not crash.
        return JSON(self.rendered_json())
