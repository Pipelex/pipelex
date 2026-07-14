import datetime
from typing import Any, ClassVar


class TestData:
    OFFSET_PLUS_2 = datetime.timezone(datetime.timedelta(hours=2))

    # Sample values in the three precision states
    SAMPLE_DATE = datetime.date(2026, 7, 7)
    SAMPLE_TIME_NAIVE = datetime.time(15, 40, 0)
    SAMPLE_TIME_OFFSET = datetime.time(15, 40, 0, tzinfo=OFFSET_PLUS_2)

    # Expected smart_dump (python mode keeps real objects — relevant to transport)
    EXPECTED_SMART_DUMP_DATE_ONLY: ClassVar[dict[str, Any]] = {"date": SAMPLE_DATE, "time": None}
    EXPECTED_SMART_DUMP_WITH_TIME: ClassVar[dict[str, Any]] = {"date": SAMPLE_DATE, "time": SAMPLE_TIME_NAIVE}

    # Expected ISO renders (rendered_plain / markdown / html are identical — truncated to stated precision)
    EXPECTED_ISO_DATE_ONLY = "2026-07-07"
    EXPECTED_ISO_NAIVE = "2026-07-07T15:40:00"
    EXPECTED_ISO_OFFSET = "2026-07-07T15:40:00+02:00"

    # Expected rendered_json (two-field form)
    EXPECTED_JSON_DATE_ONLY = '{"date": "2026-07-07", "time": null}'
    EXPECTED_JSON_NAIVE = '{"date": "2026-07-07", "time": "15:40:00"}'
    EXPECTED_JSON_OFFSET = '{"date": "2026-07-07", "time": "15:40:00+02:00"}'

    # Expected short_desc
    EXPECTED_SHORT_DESC_DATE_ONLY = "a date (2026-07-07)"
    EXPECTED_SHORT_DESC_NAIVE = "a date and time (2026-07-07T15:40:00)"
    EXPECTED_SHORT_DESC_OFFSET = "a date and time (2026-07-07T15:40:00+02:00)"

    # The field descriptions are the LLM-facing generation contract (DT2 anti-fabrication instruction).
    EXPECTED_DATE_FIELD_DESCRIPTION = "The calendar date, in ISO 8601 (e.g. 2026-07-07). Always required."
    EXPECTED_TIME_FIELD_DESCRIPTION = (
        "The time of day, in ISO 8601 (e.g. 15:40:00, or 15:40:00+02:00 with a UTC offset). "
        "Include it only when the source states a time — never invent a time. "
        "Keep the UTC offset exactly when the source states one."
    )
