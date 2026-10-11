import ast
import subprocess  # ruff: ignore[suspicious-subprocess-import] — runs the detached sender module the way a command does
import sys
import time
import venv
from pathlib import Path
from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.system.usage_stats import usage_stats_core
from pipelex.system.usage_stats.usage_stats_contract import TOOL_NAME
from pipelex.system.usage_stats.usage_stats_core import (
    BATCH_PATH,
    PROJECT_TOKEN,
    PostVerdict,
    UsageStatsState,
    drain_spool,
    pending_files,
    post_batch,
    post_in_process,
    sender_command,
    write_spool_file,
)
from pipelex.system.usage_stats.usage_stats_core import main as sender_main
from pipelex.system.usage_stats.usage_stats_delivery import start_detached_sender
from tests.helpers.usage_stats_capture import capture_server, trickling_server
from tests.helpers.usage_stats_process import stats_on_environment


def _event(*, distinct_id: str, uuid: str) -> dict[str, Any]:
    return {"event": "command_completed", "distinct_id": distinct_id, "uuid": uuid, "timestamp": "2026-10-11T09:30:00.123Z", "properties": {}}


def _state_with_id(*, home: Path) -> tuple[UsageStatsState, str]:
    state = UsageStatsState(home=home)
    return state, state.obtain_installation_id().value


class TestUsageStatsDelivery:
    def test_batch_is_posted_with_the_project_token(self) -> None:
        events = [_event(distinct_id="x", uuid="1")]
        with capture_server() as server:
            verdict = post_batch(origin=server.origin, events=events, timeout_seconds=2)
        assert verdict == PostVerdict.ACCEPTED
        assert len(server.requests) == 1
        request = server.requests[0]
        assert request.path == BATCH_PATH
        assert request.content_type == "application/json"
        assert request.body == {"api_key": PROJECT_TOKEN, "batch": events}

    @pytest.mark.parametrize(
        ("status", "verdict", "is_kept"),
        [
            (200, PostVerdict.ACCEPTED, False),
            (400, PostVerdict.REFUSED, False),
            (413, PostVerdict.REFUSED, False),
            (429, PostVerdict.RETRY, True),
            (503, PostVerdict.RETRY, True),
        ],
    )
    def test_answer_decides_what_happens_to_the_file(self, tmp_path: Path, status: int, verdict: PostVerdict, is_kept: bool) -> None:
        """Accepted or refused for good deletes the file; anything else gives it back, resent later with its uuid."""
        state, installation_id = _state_with_id(home=tmp_path)
        spool_file = write_spool_file(spool_dir=state.spool_dir(tool=TOOL_NAME), events=[_event(distinct_id=installation_id, uuid="u-1")])
        with capture_server(statuses=[status]) as server:
            drain_spool(state=state, tool=TOOL_NAME, origin=server.origin, budget_ms=2000)
        assert pending_files(spool_dir=state.spool_dir(tool=TOOL_NAME)) == ([spool_file] if is_kept else [])
        assert [event["uuid"] for event in server.requests[0].body["batch"]] == ["u-1"]
        assert verdict.is_final is not is_kept

    def test_unreachable_endpoint_keeps_the_file(self, tmp_path: Path) -> None:
        state, installation_id = _state_with_id(home=tmp_path)
        spool_file = write_spool_file(spool_dir=state.spool_dir(tool=TOOL_NAME), events=[_event(distinct_id=installation_id, uuid="u-1")])
        drain_spool(state=state, tool=TOOL_NAME, origin="http://127.0.0.1:9", budget_ms=1000)
        assert pending_files(spool_dir=state.spool_dir(tool=TOOL_NAME)) == [spool_file]

    def test_events_of_a_replaced_identifier_are_dropped(self, tmp_path: Path) -> None:
        """Before each post the sender reads `id`: events made under an identifier `reset-id` replaced never leave."""
        state, installation_id = _state_with_id(home=tmp_path)
        events = [_event(distinct_id=installation_id, uuid="kept"), _event(distinct_id="0f8fad5b-d9cb-469f-a165-70867728950e", uuid="dropped")]
        write_spool_file(spool_dir=state.spool_dir(tool=TOOL_NAME), events=events)
        with capture_server() as server:
            drain_spool(state=state, tool=TOOL_NAME, origin=server.origin, budget_ms=2000)
        assert [event["uuid"] for event in server.events] == ["kept"]

    def test_nothing_is_sent_once_disabled_or_migrated(self, tmp_path: Path) -> None:
        """A `disabled` file, or a legacy opt-out migrated before the post, sends nothing and deletes the queue."""
        state, installation_id = _state_with_id(home=tmp_path)
        write_spool_file(spool_dir=state.spool_dir(tool=TOOL_NAME), events=[_event(distinct_id=installation_id, uuid="u-1")])
        state.legacy_config.write_text("DISABLE_TELEMETRY=true\n", encoding="utf-8")
        with capture_server() as server:
            drain_spool(state=state, tool=TOOL_NAME, origin=server.origin, budget_ms=2000)
            verdict, posted = post_in_process(
                state=state,
                events=[_event(distinct_id=installation_id, uuid="u-2")],
                origin=server.origin,
                deadline=time.monotonic() + 1,
                own_id=None,
            )
        assert server.requests == []
        assert (verdict, posted) == (None, [])
        assert state.is_disabled()
        assert pending_files(spool_dir=state.spool_dir(tool=TOOL_NAME)) == []

    def test_sender_drains_only_its_own_tool(self, tmp_path: Path) -> None:
        state, installation_id = _state_with_id(home=tmp_path)
        write_spool_file(spool_dir=state.spool_dir(tool="plxt"), events=[_event(distinct_id=installation_id, uuid="plxt-1")])
        write_spool_file(spool_dir=state.spool_dir(tool=TOOL_NAME), events=[_event(distinct_id=installation_id, uuid="pipelex-1")])
        with capture_server() as server:
            assert sender_main(argv=["--home", str(tmp_path), "--origin", server.origin, "--tool", TOOL_NAME]) == 0
        assert [event["uuid"] for event in server.events] == ["pipelex-1"]
        assert len(pending_files(spool_dir=state.spool_dir(tool="plxt"))) == 1

    @pytest.mark.parametrize("origin", ["https://example.com", "http://10.0.0.1:8123", "http://127.0.0.1:8123/batch/"])
    def test_sender_refuses_any_other_origin(self, tmp_path: Path, origin: str) -> None:
        state, installation_id = _state_with_id(home=tmp_path)
        write_spool_file(spool_dir=state.spool_dir(tool=TOOL_NAME), events=[_event(distinct_id=installation_id, uuid="u-1")])
        assert sender_main(argv=["--home", str(tmp_path), "--origin", origin, "--tool", TOOL_NAME]) == 2
        assert len(pending_files(spool_dir=state.spool_dir(tool=TOOL_NAME))) == 1

    def test_post_returns_within_its_budget_whatever_the_network_does(self) -> None:
        """An answer trickling in byte by byte never trips a socket timeout; the post still returns within its budget."""
        with trickling_server(seconds_per_byte=0.1) as origin:
            started = time.monotonic()
            verdict = post_batch(origin=origin, events=[_event(distinct_id="x", uuid="1")], timeout_seconds=0.5)
            elapsed = time.monotonic() - started
        assert verdict == PostVerdict.RETRY
        assert elapsed < 1.5

    def test_drain_returns_within_its_budget_and_keeps_the_file(self, tmp_path: Path) -> None:
        state, installation_id = _state_with_id(home=tmp_path)
        write_spool_file(spool_dir=state.spool_dir(tool=TOOL_NAME), events=[_event(distinct_id=installation_id, uuid="u-1")])
        with trickling_server(seconds_per_byte=0.1) as origin:
            started = time.monotonic()
            drain_spool(state=state, tool=TOOL_NAME, origin=origin, budget_ms=500)
            elapsed = time.monotonic() - started
        assert elapsed < 1.5
        assert len(pending_files(spool_dir=state.spool_dir(tool=TOOL_NAME))) == 1

    def test_detached_sender_file_posts_the_queue(self, tmp_path: Path) -> None:
        """The sender's file run by path in isolated mode, as a command starts it, posts the queue and leaves it empty."""
        state, installation_id = _state_with_id(home=tmp_path)
        write_spool_file(spool_dir=state.spool_dir(tool=TOOL_NAME), events=[_event(distinct_id=installation_id, uuid="u-1")])
        with capture_server() as server:
            completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] — a fixed argument list, no shell
                sender_command(executable=sys.executable, home=tmp_path, origin=server.origin, tool=TOOL_NAME),
                env={**stats_on_environment(origin=server.origin), "HOME": str(tmp_path)},
                capture_output=True,
                check=False,
                timeout=60,
            )
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout == b""
        assert [event["uuid"] for event in server.events] == ["u-1"]
        assert pending_files(spool_dir=state.spool_dir(tool=TOOL_NAME)) == []

    def test_sender_imports_the_standard_library_alone(self) -> None:
        """The sender is one file a bare interpreter can run: every module it imports is the standard library's."""
        tree = ast.parse(Path(usage_stats_core.__file__).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0, "the sender is run by path, so it can import nothing relative to itself"
                imported.add((node.module or "").split(".")[0])
        assert imported <= sys.stdlib_module_names, sorted(imported - sys.stdlib_module_names)

    def test_detached_sender_delivers_where_pipelex_is_not_importable(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A sender started by an interpreter that cannot import pipelex, as with a user or `PYTHONPATH` install, still delivers."""
        bare_environment = tmp_path / "bare-venv"
        venv.create(bare_environment, with_pip=False, symlinks=sys.platform != "win32")
        bare_python = bare_environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        cannot_import = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] — a fixed argument list, no shell
            [str(bare_python), "-I", "-c", "import pipelex"], capture_output=True, check=False, timeout=60
        )
        assert cannot_import.returncode != 0
        home = tmp_path / "home"
        state, installation_id = _state_with_id(home=home)
        write_spool_file(spool_dir=state.spool_dir(tool=TOOL_NAME), events=[_event(distinct_id=installation_id, uuid="u-1")])
        mocker.patch.object(sys, "executable", str(bare_python))
        with capture_server() as server:
            assert start_detached_sender(state=state, origin=server.origin)
            deadline = time.monotonic() + 30
            while not server.events and time.monotonic() < deadline:
                time.sleep(0.05)
            received = [event["uuid"] for event in server.events]
        assert received == ["u-1"]
