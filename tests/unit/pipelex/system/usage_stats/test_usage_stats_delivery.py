import subprocess  # ruff: ignore[suspicious-subprocess-import] — runs the detached sender module the way a command does
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from pipelex.system.usage_stats.usage_stats_contract import BATCH_PATH, PROJECT_TOKEN, TOOL_NAME
from pipelex.system.usage_stats.usage_stats_delivery import SENDER_MODULE, drain_spool, post_in_process
from pipelex.system.usage_stats.usage_stats_sender import main as sender_main
from pipelex.system.usage_stats.usage_stats_spool import pending_files, write_spool_file
from pipelex.system.usage_stats.usage_stats_state import UsageStatsState
from pipelex.system.usage_stats.usage_stats_transport import PostVerdict, post_batch
from tests.helpers.usage_stats_capture import capture_server
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
            assert sender_main(argv=["--home", str(tmp_path), "--origin", server.origin]) == 0
        assert [event["uuid"] for event in server.events] == ["pipelex-1"]
        assert len(pending_files(spool_dir=state.spool_dir(tool="plxt"))) == 1

    @pytest.mark.parametrize("origin", ["https://example.com", "http://10.0.0.1:8123", "http://127.0.0.1:8123/batch/"])
    def test_sender_refuses_any_other_origin(self, tmp_path: Path, origin: str) -> None:
        state, installation_id = _state_with_id(home=tmp_path)
        write_spool_file(spool_dir=state.spool_dir(tool=TOOL_NAME), events=[_event(distinct_id=installation_id, uuid="u-1")])
        assert sender_main(argv=["--home", str(tmp_path), "--origin", origin]) == 2
        assert len(pending_files(spool_dir=state.spool_dir(tool=TOOL_NAME))) == 1

    def test_detached_sender_module_posts_the_queue(self, tmp_path: Path) -> None:
        """`python -I -m` the sender module, as a command starts it, posts the queue and leaves it empty."""
        state, installation_id = _state_with_id(home=tmp_path)
        write_spool_file(spool_dir=state.spool_dir(tool=TOOL_NAME), events=[_event(distinct_id=installation_id, uuid="u-1")])
        with capture_server() as server:
            completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] — a fixed argument list, no shell
                [sys.executable, "-I", "-m", SENDER_MODULE, "--home", str(tmp_path), "--origin", server.origin],
                env={**stats_on_environment(origin=server.origin), "HOME": str(tmp_path)},
                capture_output=True,
                check=False,
                timeout=60,
            )
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout == b""
        assert [event["uuid"] for event in server.events] == ["u-1"]
        assert pending_files(spool_dir=state.spool_dir(tool=TOOL_NAME)) == []
