import json
import time
from pathlib import Path
from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.system.usage_stats import usage_stats_client
from pipelex.system.usage_stats.usage_stats_client import UsageStatsClient, UsageStatsDelivery, UsageStatsSettings, build_settings
from pipelex.system.usage_stats.usage_stats_contract import (
    TOOL_NAME,
    UsageStatsEnvVar,
    UsageStatsEventName,
    UsageStatsIntegration,
    UsageStatsOffBy,
    UsageStatsOutcome,
    UsageStatsSurface,
)
from pipelex.system.usage_stats.usage_stats_core import UsageStatsState, pending_files, read_spool_events
from pipelex.system.usage_stats.usage_stats_events import CommandCompletedProperties, UsageStatsEvent
from pipelex.test_extras.usage_stats_isolation import USAGE_STATS_DEAD_LOOPBACK_ORIGIN
from tests.helpers.usage_stats_capture import capture_server
from tests.helpers.usage_stats_process import make_project_dir
from tests.helpers.usage_stats_schema import assert_envelope_is_valid

_COMMAND_EVENT = UsageStatsEvent(
    name=UsageStatsEventName.COMMAND_COMPLETED,
    properties=CommandCompletedProperties(command="validate", outcome=UsageStatsOutcome.SUCCEEDED, duration_ms=12),
)


def _settings(
    *,
    tmp_path: Path,
    origin: str = USAGE_STATS_DEAD_LOOPBACK_ORIGIN,
    delivery: UsageStatsDelivery = UsageStatsDelivery.CLI_COMMAND,
    env: dict[str, str] | None = None,
    is_ci: bool = False,
) -> UsageStatsSettings:
    settings = build_settings(
        state=UsageStatsState(home=tmp_path / "home"),
        env={UsageStatsEnvVar.ENDPOINT_OVERRIDE: origin, **(env or {})},
        cwd=make_project_dir(parent=tmp_path),
        is_pytest=False,
        surface=UsageStatsSurface.PIPELEX,
        integration=UsageStatsIntegration.CLI,
        delivery=delivery,
        embedder_host=None,
    )
    return settings._replace(is_ci=is_ci, is_container=False)


def _spooled_events(*, state: UsageStatsState) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for spool_file in pending_files(spool_dir=state.spool_dir(tool=TOOL_NAME)):
        events.extend(read_spool_events(path=spool_file) or [])
    return events


class TestUsageStatsClient:
    def test_statistics_off_create_nothing(self, tmp_path: Path) -> None:
        """With any switch off, nothing is recorded and nothing is written to the shared state."""
        settings = _settings(tmp_path=tmp_path, env={UsageStatsEnvVar.DO_NOT_TRACK: "1"})
        assert settings.off_by == (UsageStatsOffBy.DO_NOT_TRACK,)
        client = UsageStatsClient(settings=settings)
        client.record(event=_COMMAND_EVENT)
        client.finish_command()
        assert not settings.state.state_dir.exists()

    def test_debug_prints_the_envelope_instead_of_sending(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Each event is one JSON line on stderr, the envelope as it would be posted; nothing is sent or spooled."""
        settings = _settings(tmp_path=tmp_path, env={UsageStatsEnvVar.DEBUG: "1"})
        client = UsageStatsClient(settings=settings)
        client.record(event=_COMMAND_EVENT)
        client.finish_command()
        captured = capsys.readouterr()
        assert captured.out == ""
        lines = captured.err.splitlines()
        assert len(lines) == 1
        envelope = json.loads(lines[0])["usage_stats_debug"]
        assert_envelope_is_valid(envelope)
        assert envelope["distinct_id"] == settings.state.read_installation_id()
        assert envelope["properties"]["id_new"] is True
        assert pending_files(spool_dir=settings.state.spool_dir(tool=TOOL_NAME)) == []

    def test_envelope_carries_the_common_properties(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        settings = _settings(tmp_path=tmp_path, env={UsageStatsEnvVar.DEBUG: "true", UsageStatsEnvVar.HOST: "cocode"}, is_ci=True)
        settings.state.state_dir.mkdir(parents=True)
        settings.state.internal_file.touch()
        settings.state.record_notice(version=1)
        UsageStatsClient(settings=settings).record(event=_COMMAND_EVENT)
        envelope = json.loads(capsys.readouterr().err.splitlines()[0])["usage_stats_debug"]
        assert_envelope_is_valid(envelope)
        properties = envelope["properties"]
        assert properties["$process_person_profile"] is False
        assert properties["schema"] == 1
        assert properties["tool"] == "pipelex"
        assert properties["surface"] == "pipelex"
        assert properties["integration"] == "cli"
        assert properties["host"] == "cocode"
        assert properties["internal"] is True
        assert properties["ci"] is True
        assert properties["container"] is False
        assert properties["notice_version"] == 1
        assert set(envelope) == {"event", "distinct_id", "uuid", "timestamp", "properties"}

    def test_command_spools_and_starts_the_detached_sender(self, tmp_path: Path, mocker: MockerFixture) -> None:
        start = mocker.patch.object(usage_stats_client, "start_detached_sender", return_value=True)
        settings = _settings(tmp_path=tmp_path, origin="http://127.0.0.1:8123")
        client = UsageStatsClient(settings=settings)
        client.record(event=_COMMAND_EVENT)
        client.finish_command()
        start.assert_called_once_with(state=settings.state, origin="http://127.0.0.1:8123")
        spooled = _spooled_events(state=settings.state)
        assert [event["event"] for event in spooled] == ["command_completed"]
        assert_envelope_is_valid(spooled[0])

    def test_command_posts_in_process_when_the_sender_cannot_start(self, tmp_path: Path, mocker: MockerFixture) -> None:
        mocker.patch.object(usage_stats_client, "start_detached_sender", return_value=False)
        with capture_server() as server:
            settings = _settings(tmp_path=tmp_path, origin=server.origin)
            client = UsageStatsClient(settings=settings)
            client.record(event=_COMMAND_EVENT)
            client.finish_command()
        assert [event["event"] for event in server.events] == ["command_completed"]
        assert pending_files(spool_dir=settings.state.spool_dir(tool=TOOL_NAME)) == []

    def test_ci_posts_in_process_before_the_command_ends(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """In CI the command has posted its events, marked `ci`, when it ends, and leaves nothing queued."""
        start = mocker.patch.object(usage_stats_client, "start_detached_sender", return_value=True)
        with capture_server() as server:
            settings = _settings(tmp_path=tmp_path, origin=server.origin, is_ci=True)
            client = UsageStatsClient(settings=settings)
            client.record(event=_COMMAND_EVENT)
            client.finish_command()
            assert [event["properties"]["ci"] for event in server.events] == [True]
        start.assert_not_called()
        assert pending_files(spool_dir=settings.state.spool_dir(tool=TOOL_NAME)) == []

    def test_ci_spools_what_it_could_not_send(self, tmp_path: Path) -> None:
        settings = _settings(tmp_path=tmp_path, is_ci=True)
        client = UsageStatsClient(settings=settings)
        client.record(event=_COMMAND_EVENT)
        started = time.monotonic()
        client.finish_command()
        assert time.monotonic() - started < 2
        assert [event["event"] for event in _spooled_events(state=settings.state)] == ["command_completed"]

    def test_process_local_identifier_is_never_persisted(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A malformed `id`: the command posts in-process under an identifier of its own and spools nothing on failure."""
        start = mocker.patch.object(usage_stats_client, "start_detached_sender", return_value=True)
        settings = _settings(tmp_path=tmp_path)
        settings.state.state_dir.mkdir(parents=True)
        settings.state.id_file.write_text("malformed", encoding="utf-8")
        client = UsageStatsClient(settings=settings)
        client.record(event=_COMMAND_EVENT)
        client.finish_command()
        start.assert_not_called()
        assert not settings.state.spool_root.exists()
        assert settings.state.id_file.read_text(encoding="utf-8") == "malformed"

    def test_python_program_posts_from_its_thread(self, tmp_path: Path) -> None:
        """A program importing pipelex never starts a process: its daemon thread posts, and a flush sends what is pending."""
        with capture_server() as server:
            settings = _settings(tmp_path=tmp_path, origin=server.origin, delivery=UsageStatsDelivery.PYTHON_PROGRAM)
            client = UsageStatsClient(settings=settings)
            client.record(event=_COMMAND_EVENT)
            client.record(event=_COMMAND_EVENT)
            client.flush()
            deadline = time.monotonic() + 5
            while len(server.events) < 2 and time.monotonic() < deadline:
                time.sleep(0.05)
            assert len(server.events) == 2
        assert len({event["uuid"] for event in server.events}) == 2
        assert pending_files(spool_dir=settings.state.spool_dir(tool=TOOL_NAME)) == []

    def test_thread_drops_events_once_disabled(self, tmp_path: Path) -> None:
        """A `disabled` file created after the event, before its post, keeps it from being sent."""
        with capture_server() as server:
            settings = _settings(tmp_path=tmp_path, origin=server.origin, delivery=UsageStatsDelivery.LONG_RUNNING)
            client = UsageStatsClient(settings=settings)
            client.record(event=_COMMAND_EVENT)
            settings.state.disable()
            client.flush()
        assert server.requests == []

    def test_fork_reset_drops_what_the_parent_held(self, tmp_path: Path, mocker: MockerFixture) -> None:
        start = mocker.patch.object(usage_stats_client, "start_detached_sender", return_value=True)
        client = UsageStatsClient(settings=_settings(tmp_path=tmp_path))
        client.record(event=_COMMAND_EVENT)
        client.reset_after_fork()
        client.finish_command()
        start.assert_not_called()
