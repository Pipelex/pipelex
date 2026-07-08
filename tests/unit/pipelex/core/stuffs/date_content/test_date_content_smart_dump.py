from pipelex.core.stuffs.date_content import DateContent
from tests.unit.pipelex.core.stuffs.date_content.test_data import TestData


class TestDateContentSmartDump:
    """smart_dump keeps real date/time objects (python mode) — the shape that rides dump_for_transport."""

    def test_smart_dump_date_only(self):
        content = DateContent(date=TestData.SAMPLE_DATE)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP_DATE_ONLY
        assert isinstance(result, dict)

    def test_smart_dump_with_time(self):
        content = DateContent(date=TestData.SAMPLE_DATE, time=TestData.SAMPLE_TIME_NAIVE)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP_WITH_TIME
