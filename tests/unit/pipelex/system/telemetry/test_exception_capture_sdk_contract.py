"""Unit tests for what the real PostHog SDK does with the crash this class hands it.

The module beside this one pins the identity each stream resolves, and it does
so against `MagicMock(spec=Posthog)` — which is the right stub for that question
and a blind one for this. Two defects lived underneath those mocks: the SDK
drops a capture of an error it has already sent, so whichever stream went second
received nothing; and the privacy wrapper redacted a `PipelexError` handed over
bare but not the `(type, value, traceback)` triple an excepthook is given, which
is the only form this path has. A mock answers neither, because neither happens
until the SDK runs.

So these tests use real `Posthog` clients with only `capture` stubbed — the one
call that would put an event on the wire. Everything above it is the production
article: the wrapper the manager installs, the SDK's own deduplication, and the
event the SDK builds out of the triple. `sync_mode=True` keeps the client from
starting its consumer threads, and the stub returns an event id because the SDK
marks an error as captured only when the send reported one.
"""

import sys
import threading
from typing import Any, Generator

import pytest
from posthog import Posthog
from pytest_mock import MockerFixture

from pipelex.system.exceptions import ToolError
from pipelex.system.telemetry.exception_capture import DualClientExceptionCapture
from pipelex.system.telemetry.telemetry_config import PostHogConfig, PostHogMode, TelemetryConfig
from pipelex.system.telemetry.telemetry_manager import TelemetryManager

_CONFIDENTIAL_MESSAGE = "could not read patient record 123-45-6789 at /home/acme/confidential.pdf"


@pytest.fixture
def restore_excepthooks() -> Generator[None, None, None]:
    """Give the interpreter back the hooks a capture installs when it is built."""
    original_excepthook = sys.excepthook
    original_threading_excepthook = threading.excepthook
    yield
    sys.excepthook = original_excepthook
    threading.excepthook = original_threading_excepthook


def _make_stubbed_client(*, mocker: MockerFixture, api_key: str) -> tuple[Posthog, Any]:
    """A real client whose only stubbed method is the one that would reach the network."""
    client = Posthog(project_api_key=api_key, host="http://localhost:1", sync_mode=True, disabled=False)
    capture = mocker.patch.object(client, "capture", return_value=f"{api_key}-event-id")
    return client, capture


def _make_dual_capture(*, custom_client: Posthog, pipelex_client: Posthog) -> DualClientExceptionCapture:
    """Assemble the capture the constructor would have built, over the two given clients.

    The manager is built without its constructor, as in the module beside this
    one, because `TelemetryManager.__init__` creates live clients, writes
    `posthog.default_client` and registers a process-wide singleton. The two
    steps under test are its own: wrapping each client for privacy, then
    resolving each stream's runless identity.
    """
    manager = TelemetryManager.__new__(TelemetryManager)
    manager.telemetry_config = TelemetryConfig(
        custom_posthog=PostHogConfig(mode=PostHogMode.IDENTIFIED, user_id="operator-user", api_key="phc_custom"),
    )
    manager.custom_posthog_client = custom_client
    manager.pipelex_posthog_client = pipelex_client
    manager._pipelex_distinct_id = "gateway-hash"  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]

    manager._wrap_capture_exception(custom_client)  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
    manager._wrap_capture_exception(pipelex_client)  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
    return manager._make_exception_capture()  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]


def _crash(*, capture: DualClientExceptionCapture, error: BaseException) -> None:
    """Hand the capture the triple an excepthook would, which is all it ever receives."""
    capture._capture_exception((type(error), error, None))  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]


def _sent_exception_values(*, capture_mock: Any) -> str:
    """Render the `$exception_list` of the one event this client was asked to send."""
    return repr(capture_mock.call_args.kwargs["properties"]["$exception_list"])


@pytest.mark.usefixtures("restore_excepthooks")
class TestExceptionCaptureSdkContract:
    def test_both_streams_record_one_crash(self, mocker: MockerFixture) -> None:
        """Both streams record the crash, which is the whole point of capturing to two.

        A `PipelexError` is handed to each client as its own redacted stand-in,
        so the SDK never sees one object twice on this path and its
        deduplication has nothing to bite on. The crash with no stand-in is the
        test below, and that is the one the clearing is there for.
        """
        custom_client, custom_capture = _make_stubbed_client(mocker=mocker, api_key="phc_custom")
        pipelex_client, pipelex_capture = _make_stubbed_client(mocker=mocker, api_key="phc_pipelex")
        capture = _make_dual_capture(custom_client=custom_client, pipelex_client=pipelex_client)

        _crash(capture=capture, error=ToolError(_CONFIDENTIAL_MESSAGE))

        assert custom_capture.call_count == 1
        assert pipelex_capture.call_count == 1

    def test_both_streams_record_a_crash_that_is_not_a_pipelex_error(self, mocker: MockerFixture) -> None:
        """The SDK drops an error it has already sent, and both streams are handed the same object.

        A `ValueError` is never redacted and so never copied: it is the object
        PostHog stamps, and the stamp is still on it when the second stream
        asks. Left in place, the stream that goes second — always Pipelex's, on
        a machine that also reports to an operator's own project — returns
        before building an event, and the deployment group it resolved is
        recorded nowhere.
        """
        custom_client, custom_capture = _make_stubbed_client(mocker=mocker, api_key="phc_custom")
        pipelex_client, pipelex_capture = _make_stubbed_client(mocker=mocker, api_key="phc_pipelex")
        capture = _make_dual_capture(custom_client=custom_client, pipelex_client=pipelex_client)

        _crash(capture=capture, error=ValueError("boom"))

        assert custom_capture.call_count == 1
        assert pipelex_capture.call_count == 1

    def test_no_stream_is_sent_the_message_as_it_was_written(self, mocker: MockerFixture) -> None:
        """A `PipelexError` message repeats what the caller passed in, so it does not travel.

        The redaction was written for an error handed over bare and was never
        reached by the triple, which is the only form an excepthook produces —
        so the one path that captures without anybody asking was the one path
        sending the message verbatim.
        """
        custom_client, custom_capture = _make_stubbed_client(mocker=mocker, api_key="phc_custom")
        pipelex_client, pipelex_capture = _make_stubbed_client(mocker=mocker, api_key="phc_pipelex")
        capture = _make_dual_capture(custom_client=custom_client, pipelex_client=pipelex_client)

        _crash(capture=capture, error=ToolError(_CONFIDENTIAL_MESSAGE))

        for capture_mock in (custom_capture, pipelex_capture):
            sent = _sent_exception_values(capture_mock=capture_mock)
            assert _CONFIDENTIAL_MESSAGE not in sent
            assert TelemetryManager.PRIVACY_NOTICE in sent

    def test_the_stand_in_keeps_the_class_that_failed(self, mocker: MockerFixture) -> None:
        """Redaction costs the message, not the diagnosis: the error's own class still travels."""
        custom_client, custom_capture = _make_stubbed_client(mocker=mocker, api_key="phc_custom")
        pipelex_client, _ = _make_stubbed_client(mocker=mocker, api_key="phc_pipelex")
        capture = _make_dual_capture(custom_client=custom_client, pipelex_client=pipelex_client)

        _crash(capture=capture, error=ToolError(_CONFIDENTIAL_MESSAGE))

        assert ToolError.__name__ in _sent_exception_values(capture_mock=custom_capture)

    def test_each_stream_is_recorded_under_its_own_identity(self, mocker: MockerFixture) -> None:
        """Both streams emitting is only worth having if each still emits as itself."""
        custom_client, custom_capture = _make_stubbed_client(mocker=mocker, api_key="phc_custom")
        pipelex_client, pipelex_capture = _make_stubbed_client(mocker=mocker, api_key="phc_pipelex")
        capture = _make_dual_capture(custom_client=custom_client, pipelex_client=pipelex_client)

        _crash(capture=capture, error=ToolError(_CONFIDENTIAL_MESSAGE))

        assert custom_capture.call_args.kwargs["distinct_id"] == "operator-user"
        assert pipelex_capture.call_args.kwargs["distinct_id"] == "gateway-hash"

    def test_a_pipelex_error_raised_as_the_cause_is_redacted(self, mocker: MockerFixture) -> None:
        """PostHog sends every error it reaches through `__cause__`, not only the one at the top."""
        custom_client, custom_capture = _make_stubbed_client(mocker=mocker, api_key="phc_custom")
        pipelex_client, pipelex_capture = _make_stubbed_client(mocker=mocker, api_key="phc_pipelex")
        capture = _make_dual_capture(custom_client=custom_client, pipelex_client=pipelex_client)

        try:
            try:
                raise ToolError(_CONFIDENTIAL_MESSAGE)
            except ToolError as pipelex_error:
                wrapper_message = "wrapper"
                raise RuntimeError(wrapper_message) from pipelex_error
        except RuntimeError as crash:
            _crash(capture=capture, error=crash)

        for capture_mock in (custom_capture, pipelex_capture):
            sent = _sent_exception_values(capture_mock=capture_mock)
            assert _CONFIDENTIAL_MESSAGE not in sent
            assert TelemetryManager.PRIVACY_NOTICE in sent
            assert "wrapper" in sent

    def test_a_pipelex_error_being_handled_when_another_is_raised_is_redacted(self, mocker: MockerFixture) -> None:
        """An error raised inside `except PipelexError` carries it as `__context__`, which PostHog sends too."""
        custom_client, custom_capture = _make_stubbed_client(mocker=mocker, api_key="phc_custom")
        pipelex_client, pipelex_capture = _make_stubbed_client(mocker=mocker, api_key="phc_pipelex")
        capture = _make_dual_capture(custom_client=custom_client, pipelex_client=pipelex_client)

        try:
            try:
                raise ToolError(_CONFIDENTIAL_MESSAGE)
            except ToolError:
                handling_message = "while handling"
                raise RuntimeError(handling_message)  # ruff: ignore[raise-without-from-inside-except] — the implicit __context__ is what this test exercises
        except RuntimeError as crash:
            _crash(capture=capture, error=crash)

        for capture_mock in (custom_capture, pipelex_capture):
            assert _CONFIDENTIAL_MESSAGE not in _sent_exception_values(capture_mock=capture_mock)

    def test_a_pipelex_error_inside_an_exception_group_is_redacted(self, mocker: MockerFixture) -> None:
        """PostHog expands an exception group's members, and a `TaskGroup` wraps whatever its tasks raised."""
        custom_client, custom_capture = _make_stubbed_client(mocker=mocker, api_key="phc_custom")
        pipelex_client, pipelex_capture = _make_stubbed_client(mocker=mocker, api_key="phc_pipelex")
        capture = _make_dual_capture(custom_client=custom_client, pipelex_client=pipelex_client)

        _crash(capture=capture, error=ExceptionGroup("tasks failed", [ToolError(_CONFIDENTIAL_MESSAGE), ValueError("other")]))

        for capture_mock in (custom_capture, pipelex_capture):
            sent = _sent_exception_values(capture_mock=capture_mock)
            assert _CONFIDENTIAL_MESSAGE not in sent
            assert TelemetryManager.PRIVACY_NOTICE in sent

    def test_a_capture_with_no_argument_is_redacted(self, mocker: MockerFixture) -> None:
        """Given `None`, the SDK reads `sys.exc_info()` itself, past any wrapper that did not resolve it first.

        `None` is what the module-level `posthog.capture_exception()` passes.
        """
        client, capture_mock = _make_stubbed_client(mocker=mocker, api_key="phc_custom")
        manager = TelemetryManager.__new__(TelemetryManager)
        manager._wrap_capture_exception(client)  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]

        try:
            raise ToolError(_CONFIDENTIAL_MESSAGE)
        except ToolError:
            client.capture_exception(None)

        assert _CONFIDENTIAL_MESSAGE not in _sent_exception_values(capture_mock=capture_mock)

    def test_the_live_exception_is_left_as_it_was(self, mocker: MockerFixture) -> None:
        """Only a copy of the chain is redacted: the interpreter prints the original after the hook returns."""
        custom_client, _ = _make_stubbed_client(mocker=mocker, api_key="phc_custom")
        pipelex_client, _ = _make_stubbed_client(mocker=mocker, api_key="phc_pipelex")
        capture = _make_dual_capture(custom_client=custom_client, pipelex_client=pipelex_client)
        pipelex_error = ToolError(_CONFIDENTIAL_MESSAGE)
        crash = RuntimeError("wrapper")
        crash.__cause__ = pipelex_error

        _crash(capture=capture, error=crash)

        assert crash.__cause__ is pipelex_error
        assert str(pipelex_error) == _CONFIDENTIAL_MESSAGE

    def test_an_error_the_host_already_captured_is_not_sent_again(self, mocker: MockerFixture) -> None:
        """A host that captures an error and re-raises it has sent it once, and the hook must not add a second."""
        custom_client, custom_capture = _make_stubbed_client(mocker=mocker, api_key="phc_custom")
        pipelex_client, pipelex_capture = _make_stubbed_client(mocker=mocker, api_key="phc_pipelex")
        capture = _make_dual_capture(custom_client=custom_client, pipelex_client=pipelex_client)
        error = ValueError("boom")

        custom_client.capture_exception(error)
        _crash(capture=capture, error=error)

        assert custom_capture.call_count == 1
        assert pipelex_capture.call_count == 0

    def test_a_redacted_error_the_host_already_captured_is_not_sent_again(self, mocker: MockerFixture) -> None:
        """The SDK marks the redacted copy it sent, so the mark has to reach the error the host holds."""
        custom_client, custom_capture = _make_stubbed_client(mocker=mocker, api_key="phc_custom")
        pipelex_client, pipelex_capture = _make_stubbed_client(mocker=mocker, api_key="phc_pipelex")
        capture = _make_dual_capture(custom_client=custom_client, pipelex_client=pipelex_client)
        error = ToolError(_CONFIDENTIAL_MESSAGE)

        custom_client.capture_exception(error)
        custom_client.capture_exception(error)
        _crash(capture=capture, error=error)

        assert custom_capture.call_count == 1
        assert pipelex_capture.call_count == 0

    def test_an_argument_less_capture_of_a_redacted_error_is_not_sent_again(self, mocker: MockerFixture) -> None:
        """`capture_exception()` inside `except`, which passes `None`, is the SDK's documented form, and the mark must reach the error it resolved.

        Given nothing, the wrapper reads the error being handled out of
        `sys.exc_info()` and sends a redacted copy, which is what PostHog marks.
        Carrying that mark back onto the argument it was handed, `None`, left the
        live error unmarked, so a second capture and then the excepthook each
        sent it again.
        """
        custom_client, custom_capture = _make_stubbed_client(mocker=mocker, api_key="phc_custom")
        pipelex_client, pipelex_capture = _make_stubbed_client(mocker=mocker, api_key="phc_pipelex")
        capture = _make_dual_capture(custom_client=custom_client, pipelex_client=pipelex_client)
        error = ToolError(_CONFIDENTIAL_MESSAGE)

        try:
            raise error
        except ToolError:
            custom_client.capture_exception(None)
            custom_client.capture_exception(None)
        _crash(capture=capture, error=error)

        assert custom_capture.call_count == 1
        assert pipelex_capture.call_count == 0

    def test_a_chain_longer_than_the_recursion_limit_is_still_sent(self, mocker: MockerFixture) -> None:
        """PostHog walks a chain with a loop, so the check deciding whether it needs redacting must not recurse either.

        Nothing in this chain is a `PipelexError`, so nothing in it is copied,
        and the SDK sends it as it would have without the wrapper.
        """
        client, capture_mock = _make_stubbed_client(mocker=mocker, api_key="phc_custom")
        manager = TelemetryManager.__new__(TelemetryManager)
        manager._wrap_capture_exception(client)  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
        error: BaseException = ValueError("root")
        for link_index in range(sys.getrecursionlimit()):
            wrapper = ValueError(f"link {link_index}")
            wrapper.__context__ = error
            error = wrapper

        client.capture_exception(error)

        assert capture_mock.call_count == 1

    def test_a_capture_the_redaction_cannot_complete_is_dropped_rather_than_raised_or_sent_raw(self, mocker: MockerFixture) -> None:
        """PostHog's `capture_exception` never raises into its caller, and the redaction in front of it must not either.

        A `PipelexError` at the bottom of a chain longer than the recursion
        limit cannot be copied. Sending the original instead is the one fallback
        that is not open, so nothing goes out.
        """
        client, capture_mock = _make_stubbed_client(mocker=mocker, api_key="phc_custom")
        manager = TelemetryManager.__new__(TelemetryManager)
        manager._wrap_capture_exception(client)  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
        error: BaseException = ToolError(_CONFIDENTIAL_MESSAGE)
        for link_index in range(sys.getrecursionlimit()):
            wrapper = ValueError(f"link {link_index}")
            wrapper.__context__ = error
            error = wrapper

        assert client.capture_exception(error) is None
        assert capture_mock.call_count == 0

    @pytest.mark.parametrize("malformed", ["not an exception", (ValueError, ValueError("two")), 42])
    def test_an_argument_the_sdk_would_decline_does_not_raise_into_the_caller(self, mocker: MockerFixture, malformed: Any) -> None:
        """The SDK answers `None` to an argument it cannot use, and the wrapper answers the same instead of raising."""
        client, capture_mock = _make_stubbed_client(mocker=mocker, api_key="phc_custom")
        manager = TelemetryManager.__new__(TelemetryManager)
        manager._wrap_capture_exception(client)  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]

        assert client.capture_exception(malformed) is None
        assert capture_mock.call_count == 0
