import datetime

import pytest
from pydantic import ValidationError

from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.exceptions import DateContentError
from tests.unit.pipelex.core.stuffs.date_content.test_data import TestData


class TestDateContentRenders:
    """Tests for DateContent construction, validation, render matrix, short_desc, and to_datetime."""

    def test_construction_date_only(self):
        content = DateContent(date=TestData.SAMPLE_DATE)
        assert content.date == TestData.SAMPLE_DATE
        assert content.time is None

    def test_construction_date_and_naive_time(self):
        content = DateContent(date=TestData.SAMPLE_DATE, time=TestData.SAMPLE_TIME_NAIVE)
        assert content.date == TestData.SAMPLE_DATE
        assert content.time is not None
        assert content.time == TestData.SAMPLE_TIME_NAIVE
        assert content.time.tzinfo is None

    def test_construction_date_and_offset_time(self):
        content = DateContent(date=TestData.SAMPLE_DATE, time=TestData.SAMPLE_TIME_OFFSET)
        assert content.time is not None
        assert content.time.utcoffset() == datetime.timedelta(hours=2)

    def test_parses_iso_date_string(self):
        """The date field accepts a strict ISO date string (dict-content / JSON-wire road)."""
        content = DateContent.model_validate({"date": "2026-07-07"})
        assert content.date == TestData.SAMPLE_DATE
        assert content.time is None

    def test_parses_iso_time_with_offset_string(self):
        content = DateContent.model_validate({"date": "2026-07-07", "time": "15:40:00+02:00"})
        assert content.time is not None
        assert content.time.utcoffset() == datetime.timedelta(hours=2)

    def test_rejects_int_on_time_field(self):
        """A bare int must not coerce into the time field as seconds-of-day (no epoch-seconds; DT6)."""
        with pytest.raises(ValidationError):
            DateContent.model_validate({"date": "2026-07-07", "time": 56400})

    def test_rejects_int_on_date_field(self):
        """A bare int must not coerce into the date field (no epoch interpretation)."""
        with pytest.raises(ValidationError):
            DateContent.model_validate({"date": 1720000000})

    def test_rejects_numeric_string_epoch(self):
        """An all-digit string is an epoch, never an ISO date (which carries '-'), so it must be rejected."""
        with pytest.raises(ValidationError):
            DateContent.model_validate({"date": "1704067200"})

    def test_rejects_datetime_on_date_field(self):
        """A datetime on the date field would silently drop its time and offset — reject it (DT3 fidelity)."""
        with pytest.raises(ValidationError):
            DateContent.model_validate({"date": datetime.datetime(2026, 7, 7, 0, 0, tzinfo=TestData.OFFSET_PLUS_2)})

    def test_rendered_plain_date_only(self):
        content = DateContent(date=TestData.SAMPLE_DATE)
        assert content.rendered_plain() == TestData.EXPECTED_ISO_DATE_ONLY

    def test_rendered_plain_naive(self):
        content = DateContent(date=TestData.SAMPLE_DATE, time=TestData.SAMPLE_TIME_NAIVE)
        assert content.rendered_plain() == TestData.EXPECTED_ISO_NAIVE

    def test_rendered_plain_offset(self):
        content = DateContent(date=TestData.SAMPLE_DATE, time=TestData.SAMPLE_TIME_OFFSET)
        assert content.rendered_plain() == TestData.EXPECTED_ISO_OFFSET

    def test_rendered_markdown_offset(self):
        content = DateContent(date=TestData.SAMPLE_DATE, time=TestData.SAMPLE_TIME_OFFSET)
        assert content.rendered_markdown() == TestData.EXPECTED_ISO_OFFSET

    def test_rendered_html_offset(self):
        content = DateContent(date=TestData.SAMPLE_DATE, time=TestData.SAMPLE_TIME_OFFSET)
        assert content.rendered_html() == TestData.EXPECTED_ISO_OFFSET

    def test_rendered_json_date_only(self):
        content = DateContent(date=TestData.SAMPLE_DATE)
        assert content.rendered_json() == TestData.EXPECTED_JSON_DATE_ONLY

    def test_rendered_json_naive(self):
        content = DateContent(date=TestData.SAMPLE_DATE, time=TestData.SAMPLE_TIME_NAIVE)
        assert content.rendered_json() == TestData.EXPECTED_JSON_NAIVE

    def test_rendered_json_offset(self):
        content = DateContent(date=TestData.SAMPLE_DATE, time=TestData.SAMPLE_TIME_OFFSET)
        assert content.rendered_json() == TestData.EXPECTED_JSON_OFFSET

    def test_rendered_for_prompt_offset(self):
        """A Date input rendered into a prompt is the ISO form (the plain render)."""
        content = DateContent(date=TestData.SAMPLE_DATE, time=TestData.SAMPLE_TIME_OFFSET)
        assert content.rendered_for_prompt() == TestData.EXPECTED_ISO_OFFSET

    def test_short_desc_date_only(self):
        content = DateContent(date=TestData.SAMPLE_DATE)
        assert content.short_desc == TestData.EXPECTED_SHORT_DESC_DATE_ONLY

    def test_short_desc_naive(self):
        content = DateContent(date=TestData.SAMPLE_DATE, time=TestData.SAMPLE_TIME_NAIVE)
        assert content.short_desc == TestData.EXPECTED_SHORT_DESC_NAIVE

    def test_short_desc_offset(self):
        content = DateContent(date=TestData.SAMPLE_DATE, time=TestData.SAMPLE_TIME_OFFSET)
        assert content.short_desc == TestData.EXPECTED_SHORT_DESC_OFFSET

    def test_to_datetime_with_time(self):
        content = DateContent(date=TestData.SAMPLE_DATE, time=TestData.SAMPLE_TIME_OFFSET)
        result = content.to_datetime()
        assert result == datetime.datetime(2026, 7, 7, 15, 40, 0, tzinfo=TestData.OFFSET_PLUS_2)

    def test_to_datetime_without_time_raises(self):
        """Date-only to_datetime raises rather than inventing a midnight (DT2: no silent midnight)."""
        content = DateContent(date=TestData.SAMPLE_DATE)
        with pytest.raises(DateContentError):
            content.to_datetime()

    def test_rendered_pretty_does_not_crash(self):
        """The base rendered_pretty feeds smart_dump()'s real date objects to stdlib json and crashes;
        DateContent overrides it to render the ISO form. Guard against a regression to the base path.
        """
        from pipelex.tools.misc.pretty import pretty_print  # noqa: PLC0415 — local import keeps the render dep test-local

        pretty_print(DateContent(date=TestData.SAMPLE_DATE, time=TestData.SAMPLE_TIME_OFFSET))

    def test_model_json_schema_carries_field_descriptions(self):
        """Both field descriptions are the contract handed to the LLM in the generation schema."""
        schema = DateContent.model_json_schema()
        assert schema["properties"]["date"]["description"] == TestData.EXPECTED_DATE_FIELD_DESCRIPTION
        assert schema["properties"]["time"]["description"] == TestData.EXPECTED_TIME_FIELD_DESCRIPTION
