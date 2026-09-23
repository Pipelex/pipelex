"""Unit tests for the identity an unhandled exception is captured under.

An `$exception` is the one capture no run can hand its metadata to: the two
interpreter hooks receive `(type, value, traceback)` and nothing else, and there
is no ContextVar layer for them to read a run out of. So what the stream sends
is its runless identity, resolved once when the capture is built — and these
tests are about that resolution reaching this path, because for a while it did
not: the operator's configured `user_id` went out on every crash, `anonymous`
mode included.

The manager is built WITHOUT its constructor, as in the tracker tests beside
these, because `TelemetryManager.__init__` creates live PostHog clients, writes
`posthog.default_client` and registers a process-wide singleton. The wiring is
still what is under test: `_make_exception_capture` is the constructor's own
call, exercised here against stub clients. It installs the interpreter hooks, so
every test closes the capture again.
"""

import sys
import threading
from typing import Any, Generator

import pytest
from posthog import Posthog
from pytest_mock import MockerFixture

from pipelex.system.telemetry.exception_capture import ExceptionCapture
from pipelex.system.telemetry.otel_constants import PostHogAttr
from pipelex.system.telemetry.telemetry_config import PostHogConfig, PostHogMode, TelemetryConfig
from pipelex.system.telemetry.telemetry_manager import TelemetryManager


@pytest.fixture
def restore_excepthooks() -> Generator[None, None, None]:
    """Give the interpreter back the hooks a capture installs when it is built."""
    original_excepthook = sys.excepthook
    original_threading_excepthook = threading.excepthook
    yield
    sys.excepthook = original_excepthook
    threading.excepthook = original_threading_excepthook


def _make_capture(
    *,
    mocker: MockerFixture,
    mode: PostHogMode,
    configured_user_id: str | None,
) -> tuple[ExceptionCapture, Any]:
    """Resolve the capture the constructor would have built, over stub clients."""
    manager = TelemetryManager.__new__(TelemetryManager)
    manager.telemetry_config = TelemetryConfig(
        custom_posthog=PostHogConfig(mode=mode, user_id=configured_user_id, api_key="phc_test"),
    )
    custom_client = mocker.MagicMock(spec=Posthog)
    manager.custom_posthog_client = custom_client

    capture = manager._make_exception_capture()  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
    return capture, custom_client


def _crash(*, capture: ExceptionCapture) -> None:
    capture._capture_exception(exc_info=(ValueError, ValueError("boom"), None))  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]


@pytest.mark.usefixtures("restore_excepthooks")
class TestExceptionCaptureIdentity:
    def test_an_anonymous_stream_captures_an_exception_under_nobody(self, mocker: MockerFixture) -> None:
        """A mode that identifies nobody must not identify somebody when the process crashes.

        The configured `user_id` is deliberately left in place: the config
        validator requires one only for `identified` and never forbids one under
        `anonymous`, so a stale id after a mode switch is the reachable state.
        """
        capture, custom_client = _make_capture(
            mocker=mocker,
            mode=PostHogMode.ANONYMOUS,
            configured_user_id="configured-id",
        )

        _crash(capture=capture)

        capture_kwargs = custom_client.capture_exception.call_args.kwargs
        assert "distinct_id" not in capture_kwargs
        assert capture_kwargs["properties"][PostHogAttr.PROCESS_PERSON_PROFILE] is False

    def test_an_identified_stream_captures_an_exception_under_the_configured_id(self, mocker: MockerFixture) -> None:
        """An exception belongs to no run, so the operator's stream reports it under the fallback."""
        capture, custom_client = _make_capture(
            mocker=mocker,
            mode=PostHogMode.IDENTIFIED,
            configured_user_id="configured-id",
        )

        _crash(capture=capture)

        assert custom_client.capture_exception.call_args.kwargs["distinct_id"] == "configured-id"

    def test_an_exception_carrying_no_value_is_not_captured(self, mocker: MockerFixture) -> None:
        """`threading.excepthook` can hand over a null value, and a null exception is not an event."""
        capture, custom_client = _make_capture(
            mocker=mocker,
            mode=PostHogMode.IDENTIFIED,
            configured_user_id="configured-id",
        )

        capture._capture_exception(exc_info=(ValueError, None, None))  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]

        custom_client.capture_exception.assert_not_called()

    def test_a_failing_capture_never_reaches_the_app(self, mocker: MockerFixture) -> None:
        """Telemetry must not turn one crash into two."""
        capture, custom_client = _make_capture(
            mocker=mocker,
            mode=PostHogMode.IDENTIFIED,
            configured_user_id="configured-id",
        )
        custom_client.capture_exception.side_effect = RuntimeError("posthog is down")

        _crash(capture=capture)
