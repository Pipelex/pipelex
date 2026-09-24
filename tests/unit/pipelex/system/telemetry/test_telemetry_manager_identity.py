"""Unit tests for the tracker half: `track_event` and `handle_trace_start`.

Events resolve their identity exactly as spans do, from the run in hand, so a
run's `pipe_run` and its `$ai_span` land on the same person. The emitters that
hold a `PipeJob` pass its `RunMetadata`; a CLI command passes nothing and reports
under the configured id.

The manager is built WITHOUT its constructor. `TelemetryManager.__init__` creates
live PostHog clients, installs an `sys.excepthook`, writes `posthog.default_client`
and registers a process-wide singleton — none of which these tests are about, and
all of which would leak into the rest of the suite. What they are about is the
resolution the two methods perform, so the instance is assembled with exactly the
attributes those methods read.
"""

from typing import Any

from posthog import Posthog
from pytest_mock import MockerFixture

from pipelex.system.caller_identity import CallerIdentity, scoped_caller_identity
from pipelex.system.job_metadata import RunMetadata
from pipelex.system.storage_scope import LOCAL_USER_ID
from pipelex.system.telemetry.events import EventName
from pipelex.system.telemetry.otel_constants import PostHogAttr
from pipelex.system.telemetry.telemetry_config import PostHogConfig, PostHogMode, PostHogTracingConfig, TelemetryConfig
from pipelex.system.telemetry.telemetry_manager import TelemetryManager


def _run_metadata(*, user_id: str = "user-42", extras: dict[str, str] | None = None) -> RunMetadata:
    return RunMetadata(
        user_id=user_id,
        pipeline_run_id="run-1",
        storage_scope="tenant/run-1",
        extras=extras or {},
    )


def _make_manager(
    *,
    mocker: MockerFixture,
    mode: PostHogMode,
    configured_user_id: str | None,
    tracing_enabled: bool = True,
) -> tuple[TelemetryManager, Any]:
    """Assemble a manager with stub clients, bypassing the constructor's global side effects."""
    telemetry_config = TelemetryConfig(
        custom_posthog=PostHogConfig(
            mode=mode,
            user_id=configured_user_id,
            api_key="phc_test",
            tracing=PostHogTracingConfig(enabled=tracing_enabled),
        )
    )
    manager = TelemetryManager.__new__(TelemetryManager)
    manager.telemetry_config = telemetry_config
    custom_client = mocker.MagicMock(spec=Posthog)
    manager.custom_posthog_client = custom_client
    return manager, custom_client


_CALLER = CallerIdentity(user_id="caller-7", extras={"organization": "org_caller"})


class TestTelemetryManagerIdentity:
    def test_an_event_from_a_run_is_attributed_to_the_runs_user(self, mocker: MockerFixture) -> None:
        manager, custom_client = _make_manager(mocker=mocker, mode=PostHogMode.IDENTIFIED, configured_user_id="configured-id")

        manager.track_event(
            EventName.PIPE_RUN,
            run_metadata=_run_metadata(extras={"organization": "org_acme"}),
        )

        capture_kwargs = custom_client.capture.call_args.kwargs
        assert capture_kwargs["distinct_id"] == "user-42"
        assert capture_kwargs["groups"] == {"organization": "org_acme"}

    def test_an_event_with_no_run_reports_under_the_configured_id(self, mocker: MockerFixture) -> None:
        """A CLI command, a dry-run sweep — the configured id is what "no run" means."""
        manager, custom_client = _make_manager(mocker=mocker, mode=PostHogMode.IDENTIFIED, configured_user_id="configured-id")

        manager.track_event(EventName.PIPES_LIST)

        capture_kwargs = custom_client.capture.call_args.kwargs
        assert capture_kwargs["distinct_id"] == "configured-id"
        assert capture_kwargs["groups"] is None

    def test_an_anonymous_mode_does_not_apply_the_runs_identity(self, mocker: MockerFixture) -> None:
        manager, custom_client = _make_manager(mocker=mocker, mode=PostHogMode.ANONYMOUS, configured_user_id=None)

        manager.track_event(
            EventName.PIPE_RUN,
            run_metadata=_run_metadata(extras={"organization": "org_acme"}),
        )

        capture_kwargs = custom_client.capture.call_args.kwargs
        assert "distinct_id" not in capture_kwargs
        assert "groups" not in capture_kwargs
        assert capture_kwargs["properties"][PostHogAttr.PROCESS_PERSON_PROFILE] is False

    def test_an_off_mode_captures_nothing(self, mocker: MockerFixture) -> None:
        manager, custom_client = _make_manager(mocker=mocker, mode=PostHogMode.OFF, configured_user_id=None)

        manager.track_event(EventName.PIPE_RUN, run_metadata=_run_metadata())

        custom_client.capture.assert_not_called()

    def test_the_trace_start_is_attributed_to_the_run(self, mocker: MockerFixture) -> None:
        """It is the first event of the trace, so it has to land on the same person its spans will."""
        manager, custom_client = _make_manager(mocker=mocker, mode=PostHogMode.IDENTIFIED, configured_user_id="configured-id")

        manager.handle_trace_start(
            trace_name="some_pipe_abc12345",
            trace_name_redacted="abc12345",
            trace_id=1234,
            run_metadata=_run_metadata(extras={"organization": "org_acme"}),
        )

        capture_kwargs = custom_client.capture.call_args.kwargs
        assert capture_kwargs["distinct_id"] == "user-42"
        assert capture_kwargs["groups"] == {"organization": "org_acme"}

    def test_without_a_run_it_keeps_the_configured_identity(self, mocker: MockerFixture) -> None:
        manager, custom_client = _make_manager(mocker=mocker, mode=PostHogMode.IDENTIFIED, configured_user_id="configured-id")

        manager.handle_trace_start(trace_name="some_pipe_abc12345", trace_name_redacted="abc12345", trace_id=1234)

        assert custom_client.capture.call_args.kwargs["distinct_id"] == "configured-id"

    def test_an_anonymous_operator_stream_still_identifies_nobody(self, mocker: MockerFixture) -> None:
        manager, custom_client = _make_manager(mocker=mocker, mode=PostHogMode.ANONYMOUS, configured_user_id=None)

        manager.handle_trace_start(
            trace_name="some_pipe_abc12345",
            trace_name_redacted="abc12345",
            trace_id=1234,
            run_metadata=_run_metadata(extras={"organization": "org_acme"}),
        )

        capture_kwargs = custom_client.capture.call_args.kwargs
        assert "distinct_id" not in capture_kwargs
        assert capture_kwargs["properties"][PostHogAttr.PROCESS_PERSON_PROFILE] is False

    def test_an_anonymous_stream_ignores_a_user_id_left_behind_in_the_config(self, mocker: MockerFixture) -> None:
        """`anonymous` mode does not forbid a `user_id`, so one survives a mode switch.

        While the trace-start and the span exporter read that leftover as their
        fallback, a stream documented as identifying nobody created a person
        profile on every capture but its ordinary events.
        """
        manager, custom_client = _make_manager(mocker=mocker, mode=PostHogMode.ANONYMOUS, configured_user_id="left-behind-id")

        manager.handle_trace_start(
            trace_name="some_pipe_abc12345",
            trace_name_redacted="abc12345",
            trace_id=1234,
            run_metadata=_run_metadata(extras={"organization": "org_acme"}),
        )

        capture_kwargs = custom_client.capture.call_args.kwargs
        assert "distinct_id" not in capture_kwargs
        assert capture_kwargs["properties"][PostHogAttr.PROCESS_PERSON_PROFILE] is False

    def test_the_identity_never_becomes_a_property(self, mocker: MockerFixture) -> None:
        manager, custom_client = _make_manager(mocker=mocker, mode=PostHogMode.IDENTIFIED, configured_user_id="configured-id")

        manager.handle_trace_start(
            trace_name="some_pipe_abc12345",
            trace_name_redacted="abc12345",
            trace_id=1234,
            run_metadata=_run_metadata(extras={"organization": "org_acme"}),
        )

        rendered = repr(custom_client.capture.call_args.kwargs["properties"])
        assert "user-42" not in rendered
        assert "org_acme" not in rendered

    def test_an_event_with_no_run_is_attributed_to_the_caller_in_scope(self, mocker: MockerFixture) -> None:
        manager, custom_client = _make_manager(mocker=mocker, mode=PostHogMode.IDENTIFIED, configured_user_id="pipelex-runner")

        with scoped_caller_identity(caller_identity=_CALLER):
            manager.track_event(EventName.PIPE_DRY_RUN)

        capture_kwargs = custom_client.capture.call_args.kwargs
        assert capture_kwargs["distinct_id"] == "caller-7"
        assert capture_kwargs["groups"] == {"organization": "org_caller"}

    def test_the_run_in_hand_wins_over_the_caller_in_scope(self, mocker: MockerFixture) -> None:
        """The run the emitter holds is the most specific fact there is."""
        manager, custom_client = _make_manager(mocker=mocker, mode=PostHogMode.IDENTIFIED, configured_user_id="pipelex-runner")

        with scoped_caller_identity(caller_identity=_CALLER):
            manager.track_event(EventName.PIPE_RUN, run_metadata=_run_metadata())

        assert custom_client.capture.call_args.kwargs["distinct_id"] == "user-42"

    def test_a_placeholder_caller_in_scope_still_reports_under_the_configured_id(self, mocker: MockerFixture) -> None:
        """A local runtime states `local`, which names nobody — the CLI keeps reporting as it did."""
        manager, custom_client = _make_manager(mocker=mocker, mode=PostHogMode.IDENTIFIED, configured_user_id="configured-id")

        with scoped_caller_identity(caller_identity=CallerIdentity(user_id=LOCAL_USER_ID)):
            manager.track_event(EventName.PIPE_DRY_RUN)

        assert custom_client.capture.call_args.kwargs["distinct_id"] == "configured-id"

    def test_an_anonymous_stream_identifies_nobody_whatever_the_scope_says(self, mocker: MockerFixture) -> None:
        manager, custom_client = _make_manager(mocker=mocker, mode=PostHogMode.ANONYMOUS, configured_user_id="configured-id")

        with scoped_caller_identity(caller_identity=_CALLER):
            manager.track_event(EventName.PIPE_DRY_RUN)

        capture_kwargs = custom_client.capture.call_args.kwargs
        assert "distinct_id" not in capture_kwargs
        assert capture_kwargs["properties"][PostHogAttr.PROCESS_PERSON_PROFILE] is False

    def test_the_caller_in_scope_never_becomes_a_property(self, mocker: MockerFixture) -> None:
        manager, custom_client = _make_manager(mocker=mocker, mode=PostHogMode.IDENTIFIED, configured_user_id="configured-id")

        with scoped_caller_identity(caller_identity=_CALLER):
            manager.track_event(EventName.PIPE_DRY_RUN)

        properties = custom_client.capture.call_args.kwargs["properties"]
        assert "caller-7" not in repr(properties)
        assert "org_caller" not in repr(properties)

    def test_a_trace_start_with_no_run_is_attributed_to_the_caller_in_scope(self, mocker: MockerFixture) -> None:
        manager, custom_client = _make_manager(mocker=mocker, mode=PostHogMode.IDENTIFIED, configured_user_id="pipelex-runner")

        with scoped_caller_identity(caller_identity=_CALLER):
            manager.handle_trace_start(trace_name="some_pipe_abc12345", trace_name_redacted="abc12345", trace_id=1234)

        capture_kwargs = custom_client.capture.call_args.kwargs
        assert capture_kwargs["distinct_id"] == "caller-7"
        assert capture_kwargs["groups"] == {"organization": "org_caller"}
