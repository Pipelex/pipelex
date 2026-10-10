from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

import pytest
from typing_extensions import override

from pipelex import log
from pipelex.tools.log.log_fields import attached_field_names
from pipelex.tools.log.summary_event import SUMMARY_EVENT_FAILED_MESSAGE, SummaryEvent
from pipelex.tools.log.summary_fields import outcome_fields

if TYPE_CHECKING:
    from collections.abc import Generator

    from pytest_mock import MockerFixture

WORK_ENDS_MESSAGE = "Work ends"
STARTED_AT = 10.0
ENDED_AT = 10.5
DURATION_MS = 500.0

# The block a line is logged in, standing for a context such as a span that only the inner block runs under.
_CURRENT_BLOCK: ContextVar[str] = ContextVar("current_block", default="outer")


@contextmanager
def _inner_block() -> Generator[None]:
    token = _CURRENT_BLOCK.set("inner")
    try:
        yield
    finally:
        _CURRENT_BLOCK.reset(token)


class WorkEnds(SummaryEvent):
    """A summary event whose work fields are given, or whose reading of them fails; it notes the block it is logged in."""

    def __init__(self, *, fields_error: Exception | None = None) -> None:
        super().__init__(message=WORK_ENDS_MESSAGE)
        self._fields_error = fields_error
        self.logged_in: list[str] = []

    @override
    def _work_fields(self) -> dict[str, Any]:
        if self._fields_error is not None:
            raise self._fields_error
        return {"work": "compose"}

    @override
    def _log_event(self, *, fields: dict[str, Any]) -> None:
        self.logged_in.append(_CURRENT_BLOCK.get())
        log.info(WORK_ENDS_MESSAGE, fields=fields)


def _refuse_before_the_call() -> None:
    msg = "refused before the call"
    raise RuntimeError(msg)


def _fields(record: logging.LogRecord) -> dict[str, Any]:
    return {name: getattr(record, name) for name in attached_field_names(record=record)}


def _events(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.getMessage() == WORK_ENDS_MESSAGE]


def _failures(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.getMessage() == SUMMARY_EVENT_FAILED_MESSAGE]


@pytest.fixture
def fixed_clock(mocker: MockerFixture) -> None:
    """Every unit of work starts at the same reading and ends half a second later."""
    mocker.patch("pipelex.tools.log.summary_event.start_clock", return_value=STARTED_AT)
    mocker.patch("pipelex.tools.log.summary_fields.perf_counter", return_value=ENDED_AT)


@pytest.mark.usefixtures("fixed_clock")
class TestLogSummaryEvent:
    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (None, {"outcome": "success"}),
            (ValueError("bad input"), {"outcome": "error", "error.type": "ValueError"}),
            (asyncio.CancelledError(), {"outcome": "cancelled"}),
            (KeyboardInterrupt(), {"outcome": "cancelled"}),
            (GeneratorExit(), {"outcome": "cancelled"}),
            (SystemExit(1), {"outcome": "cancelled"}),
        ],
        ids=["returned", "raised", "a task cancelled", "an interrupt", "a generator closed", "the interpreter exiting"],
    )
    def test_the_outcome_says_whether_the_work_returned_failed_or_was_cancelled(self, error: BaseException | None, expected: dict[str, str]) -> None:
        """Only an `Exception` is a failure; the rest of `BaseException` stops work from outside, and names no error type."""
        assert outcome_fields(error=error) == expected

    @pytest.mark.parametrize(
        "error",
        [None, ValueError("bad input"), asyncio.CancelledError()],
        ids=["returned", "raised", "cancelled"],
    )
    def test_the_event_is_logged_once_with_the_work_fields_its_duration_and_its_outcome(
        self, caplog: pytest.LogCaptureFixture, error: BaseException | None
    ) -> None:
        with caplog.at_level(logging.INFO):
            if error is None:
                with WorkEnds():
                    pass
            else:
                with pytest.raises(type(error)), WorkEnds():
                    raise error

        (event,) = _events(caplog)
        assert event.name == __name__
        assert _fields(event) == {"work": "compose", "duration_ms": DURATION_MS, **outcome_fields(error=error)}
        assert not _failures(caplog)

    @pytest.mark.parametrize("raises_inside", [False, True], ids=["the inner block returns", "the inner block raises"])
    def test_ends_here_logs_the_event_at_the_end_of_the_inner_block_and_only_there(
        self, caplog: pytest.LogCaptureFixture, raises_inside: bool
    ) -> None:
        """The event is logged inside whatever the inner block runs under, and the outer block's end logs nothing more."""
        work_ends = WorkEnds()

        with caplog.at_level(logging.INFO), work_ends:
            try:
                with _inner_block(), work_ends.ends_here():
                    if raises_inside:
                        msg = "inner failure"
                        raise ValueError(msg)
            except ValueError:
                pass

        (event,) = _events(caplog)
        assert work_ends.logged_in == ["inner"]
        assert _fields(event)["outcome"] == ("error" if raises_inside else "success")

    def test_a_failure_before_the_inner_block_ends_the_work_with_its_event_from_the_outer_block(self, caplog: pytest.LogCaptureFixture) -> None:
        work_ends = WorkEnds()

        with caplog.at_level(logging.INFO), pytest.raises(RuntimeError, match="refused before the call"), work_ends:
            _refuse_before_the_call()

        (event,) = _events(caplog)
        assert work_ends.logged_in == ["outer"]
        assert _fields(event) == {"work": "compose", "duration_ms": DURATION_MS, "outcome": "error", "error.type": "RuntimeError"}

    def test_the_clock_starts_at_the_first_entry_only(self, mocker: MockerFixture) -> None:
        start_clock = mocker.patch("pipelex.tools.log.summary_event.start_clock", return_value=STARTED_AT)
        work_ends = WorkEnds()

        with work_ends, work_ends.ends_here():
            pass

        start_clock.assert_called_once_with()

    @pytest.mark.parametrize("work_error", [None, ValueError("the provider refused")], ids=["the work returned", "the work raised"])
    def test_an_event_that_cannot_be_built_never_changes_the_works_outcome(
        self, caplog: pytest.LogCaptureFixture, work_error: ValueError | None
    ) -> None:
        """A failure of the event's own is logged once as a warning; the work's result or exception goes on unchanged."""
        broken_event = WorkEnds(fields_error=TypeError("unsupported operand type(s) for -: 'NoneType' and 'int'"))

        with caplog.at_level(logging.INFO):
            if work_error is None:
                with broken_event:
                    result = "the work's result"
                assert result == "the work's result"
            else:
                with pytest.raises(ValueError, match="the provider refused") as raised, broken_event:
                    raise work_error
                assert raised.value is work_error

        assert not _events(caplog)
        (failure,) = _failures(caplog)
        assert failure.levelno == logging.WARNING
        assert _fields(failure) == {
            "summary_event": WORK_ENDS_MESSAGE,
            "error.type": "TypeError",
            "error.message": "unsupported operand type(s) for -: 'NoneType' and 'int'",
        }
