"""``include_exception`` carries the exception being handled on the record, and never in the message.

The traceback used to be spliced into the message text, which a structured sink would have carried as
a message and the Rich handler would have rendered twice once the record's ``exc_info`` was set. It now
rides the record as ``exc_info``, the stdlib's own channel, so every sink renders it its own way: the
console as a Rich traceback, the JSON sink as an ``exception`` field, the OTLP sink as the
``exception.*`` attributes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pipelex import log

if TYPE_CHECKING:
    import pytest


def _own_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == __name__]


class TestLogDispatchIncludeException:
    def test_include_exception_carries_the_active_exception_as_exc_info(self, caplog: pytest.LogCaptureFixture) -> None:
        cause = "boom-cause"
        with caplog.at_level(logging.ERROR):
            try:
                raise ValueError(cause)
            except ValueError:
                log.error("something failed", include_exception=True)

        (record,) = _own_records(caplog)
        assert record.getMessage() == "something failed"
        assert "Traceback" not in record.getMessage()
        assert record.exc_info is not None
        exc_type, exc_value, exc_traceback = record.exc_info
        assert exc_type is ValueError
        assert str(exc_value) == cause
        assert exc_traceback is not None
        # The stdlib formatter renders it once, from the record, the way any sink can.
        assert "ValueError: boom-cause" in logging.Formatter().format(record)

    def test_no_exc_info_when_include_exception_is_false(self, caplog: pytest.LogCaptureFixture) -> None:
        cause = "boom-cause"
        with caplog.at_level(logging.ERROR):
            try:
                raise ValueError(cause)
            except ValueError:
                log.error("something failed", include_exception=False)

        (record,) = _own_records(caplog)
        assert record.getMessage() == "something failed"
        assert record.exc_info is None

    def test_include_exception_outside_an_except_block_carries_nothing(self, caplog: pytest.LogCaptureFixture) -> None:
        """No exception is being handled, so there is nothing to carry: no ``NoneType: None`` anywhere."""
        with caplog.at_level(logging.ERROR):
            log.error("nothing active", include_exception=True)

        (record,) = _own_records(caplog)
        assert record.getMessage() == "nothing active"
        assert record.exc_info is None
        assert "NoneType" not in logging.Formatter().format(record)
