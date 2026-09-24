"""Unit tests for the identity an unhandled exception is captured under.

An `$exception` is the one capture no run can hand its metadata to: the two
interpreter hooks receive `(type, value, traceback)` and nothing else. So the
caller is read back from the error — the caller of the pipe run it escaped,
stamped on it as it left the run's scope — or from the caller still in scope,
and only an error that belongs to no caller goes out under the stream's
fallback. These tests are about that resolution reaching this path, because for
a while it did not: the operator's configured `user_id` went out on every crash,
`anonymous` mode included, and later the constant went out even for a crash
inside a known caller's run.

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

from pipelex.system.caller_identity import CallerIdentity, scoped_caller_identity, stamp_caller_identity
from pipelex.system.telemetry.exception_capture import DualClientExceptionCapture
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
    pipelex_distinct_id: str | None = None,
) -> tuple[DualClientExceptionCapture, Any, Any]:
    """Resolve the capture the constructor would have built, over stub clients."""
    manager = TelemetryManager.__new__(TelemetryManager)
    manager.telemetry_config = TelemetryConfig(
        custom_posthog=PostHogConfig(mode=mode, user_id=configured_user_id, api_key="phc_test"),
    )
    custom_client = mocker.MagicMock(spec=Posthog)
    pipelex_client = mocker.MagicMock(spec=Posthog) if pipelex_distinct_id else None
    manager.custom_posthog_client = custom_client
    manager.pipelex_posthog_client = pipelex_client
    manager._pipelex_distinct_id = pipelex_distinct_id  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]

    capture = manager._make_exception_capture()  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
    return capture, custom_client, pipelex_client


def _crash(*, capture: DualClientExceptionCapture) -> None:
    capture._capture_exception((ValueError, ValueError("boom"), None))  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]


_CALLER = CallerIdentity(user_id="caller-7", extras={"organization": "org_caller"})


def _crash_with(*, capture: DualClientExceptionCapture, error: BaseException) -> None:
    capture._capture_exception((type(error), error, None))  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]


def _escaped_from_a_run() -> ValueError:
    """An error as it reaches the interpreter hook after leaving a pipe run's caller scope."""
    msg = "boom inside the run"
    try:
        with scoped_caller_identity(caller_identity=_CALLER):
            raise ValueError(msg)
    except ValueError as exc:
        return exc


@pytest.mark.usefixtures("restore_excepthooks")
class TestExceptionCaptureIdentity:
    def test_an_anonymous_stream_captures_an_exception_under_nobody(self, mocker: MockerFixture) -> None:
        """A mode that identifies nobody must not identify somebody when the process crashes.

        The configured `user_id` is deliberately left in place: the config
        validator requires one only for `identified` and never forbids one under
        `anonymous`, so a stale id after a mode switch is the reachable state.
        """
        capture, custom_client, _ = _make_capture(
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
        capture, custom_client, _ = _make_capture(
            mocker=mocker,
            mode=PostHogMode.IDENTIFIED,
            configured_user_id="configured-id",
        )

        _crash(capture=capture)

        assert custom_client.capture_exception.call_args.kwargs["distinct_id"] == "configured-id"

    def test_the_pipelex_stream_captures_an_exception_under_its_fallback(self, mocker: MockerFixture) -> None:
        """No run means no caller and no groups, so the stream's fallback is the person."""
        capture, _, pipelex_client = _make_capture(
            mocker=mocker,
            mode=PostHogMode.IDENTIFIED,
            configured_user_id="configured-id",
            pipelex_distinct_id="gateway-hash",
        )

        _crash(capture=capture)

        capture_kwargs = pipelex_client.capture_exception.call_args.kwargs
        assert capture_kwargs["distinct_id"] == "gateway-hash"
        assert capture_kwargs["groups"] is None

    def test_the_pipelex_stream_is_unaffected_by_the_operators_anonymous_mode(self, mocker: MockerFixture) -> None:
        """The two streams answer to different settings, and anonymity on one is not anonymity on the other."""
        capture, _, pipelex_client = _make_capture(
            mocker=mocker,
            mode=PostHogMode.ANONYMOUS,
            configured_user_id="configured-id",
            pipelex_distinct_id="gateway-hash",
        )

        _crash(capture=capture)

        assert pipelex_client.capture_exception.call_args.kwargs["distinct_id"] == "gateway-hash"

    def test_an_exception_carrying_no_value_is_not_captured(self, mocker: MockerFixture) -> None:
        """`threading.excepthook` can hand over a null value, and a null exception is not an event."""
        capture, custom_client, _ = _make_capture(
            mocker=mocker,
            mode=PostHogMode.IDENTIFIED,
            configured_user_id="configured-id",
        )

        capture._capture_exception((ValueError, None, None))  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]

        custom_client.capture_exception.assert_not_called()

    def test_a_failing_capture_never_reaches_the_app(self, mocker: MockerFixture) -> None:
        """Telemetry must not turn one crash into two."""
        capture, custom_client, _ = _make_capture(
            mocker=mocker,
            mode=PostHogMode.IDENTIFIED,
            configured_user_id="configured-id",
        )
        custom_client.capture_exception.side_effect = RuntimeError("posthog is down")

        _crash(capture=capture)

    def test_a_crash_inside_a_run_is_attributed_to_the_runs_caller(self, mocker: MockerFixture) -> None:
        """The hosted plane's constant must not stand in for a caller the run knew."""
        capture, custom_client, _ = _make_capture(mocker=mocker, mode=PostHogMode.IDENTIFIED, configured_user_id="pipelex-worker")

        _crash_with(capture=capture, error=_escaped_from_a_run())

        capture_kwargs = custom_client.capture_exception.call_args.kwargs
        assert capture_kwargs["distinct_id"] == "caller-7"
        assert capture_kwargs["groups"] == {"organization": "org_caller"}

    def test_a_host_error_raised_from_the_runs_error_keeps_the_caller(self, mocker: MockerFixture) -> None:
        """A host wraps the run's failure in its own error, and that outer error is what reaches the hook."""
        capture, custom_client, _ = _make_capture(mocker=mocker, mode=PostHogMode.IDENTIFIED, configured_user_id="pipelex-worker")
        host_error = RuntimeError("the pipeline failed")
        host_error.__cause__ = _escaped_from_a_run()

        _crash_with(capture=capture, error=host_error)

        assert custom_client.capture_exception.call_args.kwargs["distinct_id"] == "caller-7"

    def test_an_error_raised_while_a_caller_is_in_scope_is_attributed_to_it(self, mocker: MockerFixture) -> None:
        """A thread that inherited a caller's context crashes with the scope still open."""
        capture, custom_client, _ = _make_capture(mocker=mocker, mode=PostHogMode.IDENTIFIED, configured_user_id="pipelex-worker")

        with scoped_caller_identity(caller_identity=_CALLER):
            _crash_with(capture=capture, error=ValueError("boom"))

        assert custom_client.capture_exception.call_args.kwargs["distinct_id"] == "caller-7"

    def test_the_stamp_wins_over_the_caller_in_scope(self, mocker: MockerFixture) -> None:
        capture, custom_client, _ = _make_capture(mocker=mocker, mode=PostHogMode.IDENTIFIED, configured_user_id="pipelex-worker")
        error = ValueError("boom")
        stamp_caller_identity(exception=error, caller_identity=_CALLER)

        with scoped_caller_identity(caller_identity=CallerIdentity(user_id="someone-else")):
            _crash_with(capture=capture, error=error)

        assert custom_client.capture_exception.call_args.kwargs["distinct_id"] == "caller-7"

    def test_an_error_that_belongs_to_no_caller_reports_under_the_fallback(self, mocker: MockerFixture) -> None:
        capture, custom_client, _ = _make_capture(mocker=mocker, mode=PostHogMode.IDENTIFIED, configured_user_id="pipelex-worker")

        _crash_with(capture=capture, error=ValueError("boom outside any run"))

        capture_kwargs = custom_client.capture_exception.call_args.kwargs
        assert capture_kwargs["distinct_id"] == "pipelex-worker"
        assert capture_kwargs["groups"] is None

    def test_an_anonymous_stream_identifies_nobody_even_for_a_known_caller(self, mocker: MockerFixture) -> None:
        capture, custom_client, _ = _make_capture(mocker=mocker, mode=PostHogMode.ANONYMOUS, configured_user_id="configured-id")

        _crash_with(capture=capture, error=_escaped_from_a_run())

        capture_kwargs = custom_client.capture_exception.call_args.kwargs
        assert "distinct_id" not in capture_kwargs
        assert capture_kwargs["properties"][PostHogAttr.PROCESS_PERSON_PROFILE] is False

    def test_the_pipelex_stream_resolves_the_caller_under_its_own_policy(self, mocker: MockerFixture) -> None:
        capture, _, pipelex_client = _make_capture(
            mocker=mocker,
            mode=PostHogMode.IDENTIFIED,
            configured_user_id="pipelex-worker",
            pipelex_distinct_id="gateway-hash",
        )

        _crash_with(capture=capture, error=_escaped_from_a_run())

        assert pipelex_client.capture_exception.call_args.kwargs["distinct_id"] == "caller-7"
