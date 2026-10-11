import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.system.runtime import IntegrationMode
from pipelex.system.usage_stats import usage_stats_client
from pipelex.system.usage_stats.usage_stats_client import (
    UsageStatsClient,
    UsageStatsDelivery,
    UsageStatsSettings,
    build_settings,
    configure_usage_stats_for_cli,
    configure_usage_stats_for_runtime,
    get_usage_stats_client,
)
from pipelex.system.usage_stats.usage_stats_contract import (
    TOOL_NAME,
    UsageStatsEnvVar,
    UsageStatsEventName,
    UsageStatsIntegration,
    UsageStatsOffBy,
    UsageStatsOutcome,
    UsageStatsSurface,
)
from pipelex.system.usage_stats.usage_stats_core import (
    PostVerdict,
    SpoolContent,
    UsageStatsState,
    pending_files,
    read_spool_file,
    write_spool_file,
)
from pipelex.system.usage_stats.usage_stats_events import CommandCompletedProperties, UsageStatsEvent
from pipelex.test_extras.usage_stats_isolation import USAGE_STATS_DEAD_LOOPBACK_ORIGIN
from tests.helpers.usage_stats_capture import capture_server
from tests.helpers.usage_stats_process import CAN_LOCK_DIRECTORIES, locked_directory, make_project_dir, usage_stats_switched_on
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
        events.extend((read_spool_file(path=spool_file) or SpoolContent(endpoint=None, events=[])).events)
    return events


def _seed_spool(*, settings: UsageStatsSettings) -> str:
    """Queue one event an earlier command left under the machine's identifier; its uuid."""
    installation_id = settings.state.obtain_installation_id().value
    queued_uuid = "00000000-0000-4000-8000-0000000000ee"
    event: dict[str, Any] = {"event": "command_completed", "distinct_id": installation_id, "uuid": queued_uuid, "properties": {}}
    write_spool_file(spool_dir=settings.state.spool_dir(tool=TOOL_NAME), content=SpoolContent(endpoint=None, events=[event]))
    return queued_uuid


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
        spool_files = pending_files(spool_dir=settings.state.spool_dir(tool=TOOL_NAME))
        assert [(read_spool_file(path=spool_file) or SpoolContent(endpoint=None, events=[])).endpoint for spool_file in spool_files] == [
            "http://127.0.0.1:8123"
        ]
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

    def test_in_process_posts_also_send_what_earlier_commands_queued(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """In CI, and when the detached sender cannot start, the command sends its own events first, then the spool."""
        mocker.patch.object(usage_stats_client, "start_detached_sender", return_value=False)
        with capture_server() as server:
            for index_case, is_ci in enumerate((True, False)):
                settings = _settings(tmp_path=tmp_path / f"case-{index_case}", origin=server.origin, is_ci=is_ci)
                queued_uuid = _seed_spool(settings=settings)
                client = UsageStatsClient(settings=settings)
                client.record(event=_COMMAND_EVENT)
                client.finish_command()
                received = [event["uuid"] for event in server.events]
                assert received[-1] == queued_uuid
                assert len(received) == 2 * (index_case + 1)
                assert pending_files(spool_dir=settings.state.spool_dir(tool=TOOL_NAME)) == []

    @pytest.mark.parametrize("delivery", [UsageStatsDelivery.LONG_RUNNING, UsageStatsDelivery.CLI_COMMAND])
    @pytest.mark.parametrize(
        ("verdict", "is_drained"),
        [(None, False), (PostVerdict.RETRY, False), (PostVerdict.REFUSED, False), (PostVerdict.ACCEPTED, True)],
    )
    def test_the_spool_goes_only_after_an_accepted_post(
        self, tmp_path: Path, mocker: MockerFixture, delivery: UsageStatsDelivery, verdict: PostVerdict | None, is_drained: bool
    ) -> None:
        """What earlier processes queued is sent once PostHog accepted a post, never after a post of nothing, as when every
        event was screened out, from a program's thread as from a command posting in-process.
        """

        def answered(**kwargs: Any) -> tuple[PostVerdict | None, list[dict[str, Any]]]:
            return verdict, (list(kwargs["events"]) if verdict is not None else [])

        mocker.patch.object(usage_stats_client, "post_in_process", side_effect=answered)
        with capture_server() as server:
            settings = _settings(tmp_path=tmp_path, origin=server.origin, delivery=delivery, is_ci=delivery == UsageStatsDelivery.CLI_COMMAND)
            queued_uuid = _seed_spool(settings=settings)
            client = UsageStatsClient(settings=settings)
            client.record(event=_COMMAND_EVENT)
            if delivery == UsageStatsDelivery.CLI_COMMAND:
                client.finish_command()
            else:
                client.flush()
            received = [event["uuid"] for event in server.events]
        assert (queued_uuid in received) is is_drained

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

    def test_thread_also_sends_what_earlier_processes_queued(self, tmp_path: Path) -> None:
        with capture_server() as server:
            settings = _settings(tmp_path=tmp_path, origin=server.origin, delivery=UsageStatsDelivery.LONG_RUNNING)
            queued_uuid = _seed_spool(settings=settings)
            client = UsageStatsClient(settings=settings)
            client.record(event=_COMMAND_EVENT)
            client.flush()
            received = [event["uuid"] for event in server.events]
        assert len(received) == 2
        assert received[-1] == queued_uuid
        assert pending_files(spool_dir=settings.state.spool_dir(tool=TOOL_NAME)) == []

    @pytest.mark.parametrize(
        ("error", "ends_the_thread"),
        [(OSError("a state that cannot be read"), False), (RuntimeError("a bug in the sender"), True)],
    )
    def test_thread_after_an_error_in_a_post(
        self, tmp_path: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, error: Exception, ends_the_thread: bool
    ) -> None:
        """A recoverable error loses its batch alone; any other ends the thread with its traceback, and the next event starts a new one.

        Either way a flush does not wait for the lost batch, and later events are posted.
        """
        thread_errors: list[threading.ExceptHookArgs] = []
        monkeypatch.setattr(threading, "excepthook", thread_errors.append)
        original_post_in_process = usage_stats_client.post_in_process
        calls: list[int] = []

        def fails_once(**kwargs: Any) -> Any:
            calls.append(1)
            if len(calls) == 1:
                raise error
            return original_post_in_process(**kwargs)

        mocker.patch.object(usage_stats_client, "post_in_process", side_effect=fails_once)
        with capture_server() as server:
            settings = _settings(tmp_path=tmp_path, origin=server.origin, delivery=UsageStatsDelivery.LONG_RUNNING)
            client = UsageStatsClient(settings=settings)
            client.record(event=_COMMAND_EVENT)
            deadline = time.monotonic() + 5
            while not calls and time.monotonic() < deadline:
                time.sleep(0.02)
            if ends_the_thread:
                while not thread_errors and time.monotonic() < deadline:
                    time.sleep(0.02)
                ended_thread = thread_errors[0].thread
                assert ended_thread is not None
                ended_thread.join(timeout=5)
                assert not ended_thread.is_alive()
            else:
                time.sleep(0.1)
            started = time.monotonic()
            client.flush()
            assert time.monotonic() - started < 1
            client.record(event=_COMMAND_EVENT)
            deadline = time.monotonic() + 5
            while not server.events and time.monotonic() < deadline:
                time.sleep(0.05)
            assert len(server.events) == 1
        assert [type(thread_error.exc_value) for thread_error in thread_errors] == ([type(error)] if ends_the_thread else [])

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

    def test_configuration_never_fails_for_want_of_a_home(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture) -> None:
        """No home directory to find: a command and a booting process both run without statistics."""
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "home", cwd=make_project_dir(parent=tmp_path)):
            mocker.patch.object(UsageStatsState, "make_for_current_home", side_effect=RuntimeError("Could not determine home directory."))
            assert configure_usage_stats_for_cli(surface=UsageStatsSurface.PIPELEX, is_machine_read=False) is None
            configure_usage_stats_for_runtime(integration_mode=IntegrationMode.PYTHON)
            assert get_usage_stats_client() is None

    def test_a_command_that_could_not_configure_statistics_keeps_them_off(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A transient failure leaves `pipelex-agent --format json` without statistics: pipelex booting inside it builds no
        program's client, which would print the runtime notice on the stderr the command keeps for JSON.
        """
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "home", cwd=make_project_dir(parent=tmp_path)) as state:
            mocker.patch.object(UsageStatsState, "make_for_current_home", side_effect=[RuntimeError("Could not determine home directory."), state])
            assert configure_usage_stats_for_cli(surface=UsageStatsSurface.PIPELEX_AGENT, is_machine_read=True) is None
            configure_usage_stats_for_runtime(integration_mode=IntegrationMode.PYTHON)
            assert get_usage_stats_client() is None
            assert capsys.readouterr().err == ""

    @pytest.mark.skipif(not CAN_LOCK_DIRECTORIES, reason="needs a directory this process cannot traverse")
    def test_configuration_never_fails_for_a_state_that_cannot_be_looked_into(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A state no one may traverse may hold `disabled`: the command runs with statistics off, and no notice is printed."""
        with (
            usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "locked" / "home", cwd=make_project_dir(parent=tmp_path)),
            locked_directory(path=tmp_path / "locked"),
        ):
            client = configure_usage_stats_for_cli(surface=UsageStatsSurface.PIPELEX, is_machine_read=False)
            assert client is not None
            assert UsageStatsOffBy.MACHINE_CHOICE in client.settings.off_by
        assert capsys.readouterr().err == ""
