import datetime

from kajson import kajson

from pipelex.core.stuffs.date_content import DateContent
from pipelex.hub import get_class_registry
from tests.unit.pipelex.core.stuffs.date_content.test_data import TestData


class TestDateContentSerialization:
    """kajson round-trip is the distributed-execution safety net.

    A content class that fails payload decode inside a Temporal workflow does not fail loudly —
    it hangs (converter exceptions retry forever). So each precision state must round-trip to a
    TYPED-equal object (real date/time/tzinfo, not string forms), and resolve by class name.
    """

    def _round_trip(self, content: DateContent) -> DateContent:
        restored = kajson.loads(kajson.dumps(content))
        assert isinstance(restored, DateContent)
        return restored

    def test_registry_resolves_by_name(self):
        registry = get_class_registry()
        if not registry.has_class(name="DateContent"):
            registry.register_class(DateContent)
        assert registry.get_class(name="DateContent") is DateContent

    def test_round_trip_date_only(self):
        restored = self._round_trip(DateContent(date=TestData.SAMPLE_DATE))
        assert restored.date == TestData.SAMPLE_DATE
        assert isinstance(restored.date, datetime.date)
        assert restored.time is None

    def test_round_trip_naive_time(self):
        restored = self._round_trip(DateContent(date=TestData.SAMPLE_DATE, time=TestData.SAMPLE_TIME_NAIVE))
        assert restored.time == TestData.SAMPLE_TIME_NAIVE
        assert isinstance(restored.time, datetime.time)
        assert restored.time.tzinfo is None

    def test_round_trip_offset_time_preserves_offset(self):
        restored = self._round_trip(DateContent(date=TestData.SAMPLE_DATE, time=TestData.SAMPLE_TIME_OFFSET))
        assert restored.time is not None
        assert restored.time.utcoffset() == datetime.timedelta(hours=2)
        assert restored.time == TestData.SAMPLE_TIME_OFFSET
