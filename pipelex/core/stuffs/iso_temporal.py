import datetime
import re

# The temporal natives accept EXTENDED ISO 8601 only. `date.fromisoformat` / `time.fromisoformat`
# (3.11+) additionally accept the basic forms ("20260707", "154000") and the week / ordinal calendars
# ("2026-W27-2", "2026-189"): all of those restate the value in a calendar the source did not use, and
# the ones carrying a suffix ("154000+00:00") slip past the natives' numeric-string guard. Pinning the
# extended form here — once, for both the content models and `StuffContentFactory` — is what keeps the
# form a `Date`/`Time` accepts from a model identical to the form it accepts from an author.
# The fraction separator is either '.' or ',' — ISO 8601 allows both, and `fromisoformat` parses both.
# The offset is `Z`, `±hh` or `±hh:mm`: the colon-less `±hhmm` is the basic spelling, so it is out.
# The offset's minutes are range-checked here because nothing downstream does it: they are summed into
# a timedelta, so `+02:60` would arrive as a silent `+03:00` (an out-of-range offset HOUR does raise,
# and the time's own minute/second components are range-checked by `fromisoformat`).
_EXTENDED_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
_EXTENDED_TIME_PATTERN = re.compile(r"(?P<hour>\d{2}):\d{2}(:\d{2}([.,]\d+)?)?([Zz]|[+-]\d{2}(:[0-5]\d)?)?")


def parse_iso_date(text: str) -> datetime.date:
    """Parse an extended ISO 8601 calendar date (``YYYY-MM-DD``).

    Args:
        text (str): The candidate date string.

    Returns:
        datetime.date: The parsed calendar date.

    Raises:
        ValueError: When the string is not an extended ISO 8601 calendar date. Callers in a pydantic
            validator rely on this staying a ValueError, which pydantic wraps into a ValidationError.

    """
    if not _EXTENDED_DATE_PATTERN.fullmatch(text):
        msg = f"'{text}' is not an extended ISO 8601 calendar date (e.g. '2026-07-07')."
        raise ValueError(msg)
    try:
        return datetime.date.fromisoformat(text)
    except ValueError as exc:
        msg = f"'{text}' is not a valid ISO 8601 calendar date (e.g. '2026-07-07')."
        raise ValueError(msg) from exc


def parse_iso_time(text: str) -> datetime.time:
    """Parse an extended ISO 8601 time of day (``HH:MM[:SS[.ffffff]]``, optionally with a UTC offset).

    Args:
        text (str): The candidate time string.

    Returns:
        datetime.time: The parsed time of day, carrying the UTC offset when the string states one.

    Raises:
        ValueError: When the string is not an extended ISO 8601 time of day, or uses the end-of-day
            ``24:00`` form. Callers in a pydantic validator rely on this staying a ValueError, which
            pydantic wraps into a ValidationError.

    """
    match = _EXTENDED_TIME_PATTERN.fullmatch(text)
    if not match:
        msg = f"'{text}' is not an extended ISO 8601 time of day (e.g. '15:40:00' or '15:40:00+02:00')."
        raise ValueError(msg)
    # ISO 8601's end-of-day 24:00 names the NEXT day's midnight, which a time of day alone cannot
    # carry. It must be rejected explicitly rather than left to the parser: Python 3.14 silently
    # returns 00:00 for it (3.11-3.13 raise), so accepting it would move the value back a full day —
    # and only on some of the interpreters we support.
    if match.group("hour") == "24":
        msg = f"'{text}' uses the ISO 8601 end-of-day form 24:00, which names the next day's midnight; state that day with '00:00:00' instead."
        raise ValueError(msg)
    # `fromisoformat` takes only the upper-case UTC designator, while RFC 3339 states the two spellings
    # are equivalent and pydantic accepted both before this parser existed. Case-folding the designator
    # is not normalization of the value — it names the same offset — so admit it rather than refuse a
    # spelling a model may legitimately answer, and keep the pattern above honest about what it accepts.
    parsable = f"{text[:-1]}Z" if text.endswith("z") else text
    try:
        return datetime.time.fromisoformat(parsable)
    except ValueError as exc:
        msg = f"'{text}' is not a valid ISO 8601 time of day (e.g. '15:40:00' or '15:40:00+02:00')."
        raise ValueError(msg) from exc
