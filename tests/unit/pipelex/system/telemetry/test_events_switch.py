from pathlib import Path
from typing import Any

import posthog
import pytest
from posthog import Posthog
from pytest_mock import MockerFixture

from pipelex.kit.paths import get_kit_configs_dir
from pipelex.system.telemetry.events import EventName
from pipelex.system.telemetry.posthog_error_tracker import PostHogErrorTracker
from pipelex.system.telemetry.telemetry_config import (
    PostHogConfig,
    PostHogEventsConfig,
    PostHogMode,
    PostHogTracingConfig,
    TelemetryConfig,
)
from pipelex.system.telemetry.telemetry_loader import load_telemetry_config
from pipelex.system.telemetry.telemetry_manager import TelemetryManager
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider


def _telemetry_config(*, events_enabled: bool, tracing_enabled: bool = True, mode: PostHogMode = PostHogMode.IDENTIFIED) -> TelemetryConfig:
    return TelemetryConfig(
        custom_posthog=PostHogConfig(
            mode=mode,
            user_id="operator",
            api_key="phc_test",
            events=PostHogEventsConfig(enabled=events_enabled),
            tracing=PostHogTracingConfig(enabled=tracing_enabled),
        )
    )


def _build_manager(*, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, telemetry_config: TelemetryConfig) -> tuple[TelemetryManager, Any, Any]:
    """Run the real constructor over a stub PostHog client and a stub tracer factory; returns the manager, the client and the factory.

    `__new__` then `__init__` by hand skips the metaclass's singleton registration, so no process-wide instance is left
    behind, and `monkeypatch` restores the globals the constructor writes on the `posthog` module.
    """
    monkeypatch.setattr(posthog, "default_client", None)
    monkeypatch.setattr(posthog, "privacy_mode", posthog.privacy_mode)
    posthog_client = mocker.MagicMock(spec=Posthog)
    mocker.patch("pipelex.system.telemetry.telemetry_manager.Posthog", return_value=posthog_client)
    make_ai_tracer = mocker.patch(
        "pipelex.system.telemetry.telemetry_manager.OtelFactory.make_ai_tracer",
        return_value=(mocker.MagicMock(), mocker.MagicMock()),
    )
    manager = TelemetryManager.__new__(TelemetryManager)
    manager.__init__(telemetry_config, join_host_trace=False)  # type: ignore[misc]
    return manager, posthog_client, make_ai_tracer


class TestEventsSwitch:
    def test_the_events_are_on_by_default(self) -> None:
        assert PostHogConfig().events.enabled is True
        assert TelemetryConfig().custom_posthog.events.enabled is True

    @pytest.mark.parametrize("mode", [PostHogMode.IDENTIFIED, PostHogMode.ANONYMOUS])
    @pytest.mark.parametrize("event_name", [EventName.PIPELINE_EXECUTE, EventName.PIPE_RUN, EventName.PIPE_DRY_RUN, EventName.PIPES_LIST])
    def test_switched_off_no_event_style_event_is_captured(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, mode: PostHogMode, event_name: EventName
    ) -> None:
        manager, posthog_client, _ = _build_manager(
            mocker=mocker, monkeypatch=monkeypatch, telemetry_config=_telemetry_config(events_enabled=False, mode=mode)
        )

        manager.track_event(event_name)

        posthog_client.capture.assert_not_called()

    def test_switched_on_an_event_is_captured(self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        manager, posthog_client, _ = _build_manager(mocker=mocker, monkeypatch=monkeypatch, telemetry_config=_telemetry_config(events_enabled=True))

        manager.track_event(EventName.PIPELINE_EXECUTE)

        assert posthog_client.capture.call_args.args[0] == EventName.PIPELINE_EXECUTE

    def test_switched_off_the_tracer_is_still_made_over_the_posthog_client(self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """Spans and generations travel through the same client, so the client and the tracer must both survive the switch."""
        manager, posthog_client, make_ai_tracer = _build_manager(
            mocker=mocker, monkeypatch=monkeypatch, telemetry_config=_telemetry_config(events_enabled=False)
        )

        assert manager.custom_posthog_client is posthog_client
        assert make_ai_tracer.call_args.kwargs["custom_posthog_client"] is posthog_client
        assert manager.get_otel_tracer() is not None

    def test_switched_off_the_error_tracker_stays_on(self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """`$exception` is not an event-style event: the `posthog` error tracker keeps its client."""
        manager, _, _ = _build_manager(mocker=mocker, monkeypatch=monkeypatch, telemetry_config=_telemetry_config(events_enabled=False))

        assert isinstance(manager.make_error_tracker(), PostHogErrorTracker)

    @pytest.fixture
    def project_dir(self, tmp_path: Path, mocker: MockerFixture) -> Path:
        fake_home = tmp_path / "home"
        (fake_home / ".pipelex").mkdir(parents=True)
        project_root = tmp_path / "project"
        (project_root / ".git").mkdir(parents=True)
        project_dir = project_root / ".pipelex"
        project_dir.mkdir()
        mocker.patch.object(Path, "home", return_value=fake_home)
        mocker.patch.object(Path, "cwd", return_value=project_root)
        return project_dir

    @pytest.mark.usefixtures("no_pipelex_home")
    def test_the_kit_template_keeps_the_events_on(self, project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POSTHOG_ENDPOINT", "https://posthog.example.test")
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_test")
        (project_dir / "telemetry.toml").write_text((get_kit_configs_dir() / "telemetry.toml").read_text())

        config = load_telemetry_config(secrets_provider=EnvSecretsProvider())

        assert config.custom_posthog.events.enabled is True

    @pytest.mark.usefixtures("no_pipelex_home")
    def test_a_file_switches_the_events_off_and_keeps_tracing(self, project_dir: Path) -> None:
        (project_dir / "telemetry.toml").write_text(
            '[custom_posthog]\nmode = "anonymous"\napi_key = "phc_test"\n\n'
            "[custom_posthog.events]\nenabled = false\n\n"
            "[custom_posthog.tracing]\nenabled = true\n",
        )

        config = load_telemetry_config(secrets_provider=EnvSecretsProvider())

        assert config.custom_posthog.events.enabled is False
        assert config.custom_posthog.tracing.enabled is True
        assert config.operator_span_destinations() == ["custom_posthog"]
