"""Regression test for the tzdata dependency.

kajson decodes timezone-aware datetimes via ``ZoneInfo(tzinfo_str)``, which needs the IANA tz
database: either system tz files (absent on slim containers and uv-managed standalone Pythons,
like the CI test runner) or the ``tzdata`` package. Without either, decoding any payload that
carries an aware datetime — e.g. a ``GraphSpec`` crossing the Temporal boundary — raises
``ZoneInfoNotFoundError`` inside the workflow task, which Temporal retries forever: the caller
hangs instead of failing. These tests pin that the round trip survives with system tz files
hidden, i.e. that the ``tzdata`` package stays a direct dependency.
"""

import zoneinfo
from datetime import datetime, timezone
from typing import Generator
from zoneinfo import ZoneInfo

import pytest
from kajson import kajson


@pytest.fixture
def no_system_tzpath() -> Generator[None, None, None]:
    original_tzpath = zoneinfo.TZPATH
    zoneinfo.reset_tzpath(to=[])
    ZoneInfo.clear_cache()
    try:
        yield
    finally:
        zoneinfo.reset_tzpath(to=original_tzpath)
        ZoneInfo.clear_cache()


@pytest.mark.usefixtures("no_system_tzpath")
class TestTzdataFallback:
    def test_aware_datetime_round_trip_without_system_tz_files(self) -> None:
        """The exact operation that hung CI: kajson round trip of an aware datetime."""
        stamp = datetime(2026, 6, 10, 12, 30, 45, 123456, tzinfo=timezone.utc)

        decoded = kajson.loads(kajson.dumps(stamp))

        assert isinstance(decoded, datetime)
        assert decoded == stamp
        assert decoded.tzinfo is not None
        assert decoded.utcoffset() == stamp.utcoffset()

    def test_zoneinfo_utc_resolves_from_tzdata_package(self) -> None:
        zone = ZoneInfo("UTC")

        assert zone.key == "UTC"
