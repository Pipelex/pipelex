import os
import stat
import sys
import threading
import time
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.system.usage_stats.usage_stats_core import (
    SPOOL_TOOLS,
    InstallationId,
    SpoolContent,
    UsageStatsState,
    is_installation_id,
    parse_legacy_config,
    write_spool_file,
)


def _seed_every_spool(*, state: UsageStatsState) -> None:
    for tool in SPOOL_TOOLS:
        write_spool_file(spool_dir=state.spool_dir(tool=tool), content=SpoolContent(endpoint=None, events=[{"event": "command_completed"}]))


def _spooled_files(*, state: UsageStatsState) -> list[Path]:
    return [entry for tool in SPOOL_TOOLS if state.spool_dir(tool=tool).is_dir() for entry in state.spool_dir(tool=tool).iterdir()]


class TestUsageStatsState:
    def test_first_identifier_is_created_once(self, tmp_path: Path) -> None:
        """The first process creates `id` with mode 0700 on its directory; the next reads it, not new."""
        state = UsageStatsState(home=tmp_path)
        first = state.obtain_installation_id()
        assert first.is_new
        assert is_installation_id(value=first.value)
        assert state.id_file.read_text(encoding="utf-8") == first.value
        if sys.platform != "win32":
            assert stat.S_IMODE(state.state_dir.stat().st_mode) == 0o700
        second = state.obtain_installation_id()
        assert second == InstallationId(value=first.value, is_new=False)
        assert [entry.name for entry in state.state_dir.iterdir()] == ["id"]

    def test_racing_first_runs_converge_on_one_identifier(self, tmp_path: Path) -> None:
        """Exactly one of the racing processes reports the identifier as new, and every one sends under it."""
        state = UsageStatsState(home=tmp_path)
        results: list[InstallationId] = []
        lock = threading.Lock()
        barrier = threading.Barrier(8)

        def obtain() -> None:
            barrier.wait()
            installation_id = UsageStatsState(home=tmp_path).obtain_installation_id()
            with lock:
                results.append(installation_id)

        threads = [threading.Thread(target=obtain) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert len({result.value for result in results}) == 1
        assert sum(1 for result in results if result.is_new) == 1
        assert state.read_installation_id() == results[0].value
        assert not [entry for entry in state.state_dir.iterdir() if entry.name.startswith("id.tmp-")]

    @pytest.mark.parametrize("content", ["not-a-uuid", "0F8FAD5B-D9CB-469F-A165-70867728950E", "0f8fad5b-d9cb-169f-a165-70867728950e", ""])
    def test_malformed_identifier_is_never_rewritten(self, tmp_path: Path, content: str) -> None:
        """A malformed `id` gives the process an identifier of its own, persisted nowhere; only `reset-id` replaces it."""
        state = UsageStatsState(home=tmp_path)
        state.state_dir.mkdir(parents=True)
        state.id_file.write_text(content, encoding="utf-8")
        process_local = state.obtain_installation_id()
        assert process_local.is_new
        assert is_installation_id(value=process_local.value)
        assert state.id_file.read_text(encoding="utf-8") == content
        assert state.read_installation_id() is None
        replaced = state.replace_installation_id()
        assert state.read_installation_id() == replaced

    def test_identifier_with_whitespace_is_read(self, tmp_path: Path) -> None:
        state = UsageStatsState(home=tmp_path)
        state.state_dir.mkdir(parents=True)
        state.id_file.write_text("  0f8fad5b-d9cb-469f-a165-70867728950e\n", encoding="utf-8")
        assert state.obtain_installation_id() == InstallationId(value="0f8fad5b-d9cb-469f-a165-70867728950e", is_new=False)

    def test_no_hard_links_means_nothing_persisted(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A filesystem without hard links: the process uses its fresh identifier for itself alone."""
        mocker.patch("pipelex.system.usage_stats.usage_stats_core.os.link", side_effect=OSError("no hard links here"))
        state = UsageStatsState(home=tmp_path)
        installation_id = state.obtain_installation_id()
        assert installation_id.is_new
        assert not state.id_file.exists()
        assert not [entry for entry in state.state_dir.iterdir() if entry.name.startswith("id.tmp-")]

    def test_stale_temporary_identifiers_are_deleted(self, tmp_path: Path) -> None:
        state = UsageStatsState(home=tmp_path)
        state.state_dir.mkdir(parents=True)
        stale = state.state_dir / "id.tmp-crashed"
        stale.write_text("0f8fad5b-d9cb-469f-a165-70867728950e", encoding="utf-8")
        two_hours_ago = time.time() - 7200
        os.utime(stale, (two_hours_ago, two_hours_ago))
        fresh = state.state_dir / "id.tmp-writing"
        fresh.write_text("", encoding="utf-8")
        state.obtain_installation_id()
        assert not stale.exists()
        assert fresh.exists()

    def test_reset_id_empties_every_spool(self, tmp_path: Path) -> None:
        state = UsageStatsState(home=tmp_path)
        first = state.obtain_installation_id()
        _seed_every_spool(state=state)
        replaced = state.replace_installation_id()
        assert replaced != first.value
        assert state.read_installation_id() == replaced
        assert _spooled_files(state=state) == []

    def test_disable_and_enable(self, tmp_path: Path) -> None:
        """`disable` creates `disabled` and empties every tool's spool; `enable` deletes it and sets the legacy marker."""
        state = UsageStatsState(home=tmp_path)
        _seed_every_spool(state=state)
        state.disable()
        assert state.is_disabled()
        assert _spooled_files(state=state) == []
        state.enable()
        assert not state.is_disabled()
        assert state.legacy_marker.exists()

    def test_legacy_opt_out_is_migrated_once(self, tmp_path: Path) -> None:
        """`DISABLE_TELEMETRY` on in `~/.mthds/config` becomes the machine's choice, and `enable` is not undone by it."""
        state = UsageStatsState(home=tmp_path)
        _seed_every_spool(state=state)
        state.legacy_config.write_text("# mthds\nDISABLE_TELEMETRY = Yes\n", encoding="utf-8")
        assert state.legacy_opt_out_is_pending()
        state.migrate_legacy_opt_out()
        assert state.is_disabled()
        assert _spooled_files(state=state) == []
        assert state.legacy_marker.stat().st_mtime_ns >= state.legacy_config.stat().st_mtime_ns
        assert not state.legacy_opt_out_is_pending()
        state.enable()
        state.migrate_legacy_opt_out()
        assert not state.is_disabled()
        later = time.time() + 5
        os.utime(state.legacy_config, (later, later))
        assert state.legacy_opt_out_is_pending()
        state.migrate_legacy_opt_out()
        assert state.is_disabled()

    @pytest.mark.parametrize("content", ["DISABLE_TELEMETRY=0\n", "DISABLE_TELEMETRY=false\n", "OTHER=1\n", "# DISABLE_TELEMETRY=1\n", ""])
    def test_legacy_value_that_does_not_mean_off_migrates_nothing(self, tmp_path: Path, content: str) -> None:
        state = UsageStatsState(home=tmp_path)
        state.legacy_config.parent.mkdir(parents=True)
        state.legacy_config.write_text(content, encoding="utf-8")
        state.migrate_legacy_opt_out()
        assert not state.state_dir.exists()

    def test_legacy_config_dialect(self) -> None:
        content = "  # comment\nDISABLE_TELEMETRY = 0\nno equals here\nKEY=a=b\nDISABLE_TELEMETRY=1\r\n\n"
        assert parse_legacy_config(content=content) == {"DISABLE_TELEMETRY": "1", "KEY": "a=b"}

    def test_notice_markers_and_internal(self, tmp_path: Path) -> None:
        state = UsageStatsState(home=tmp_path)
        assert state.seen_notice_version(up_to=1) == 0
        assert state.record_notice(version=1)
        assert state.seen_notice_version(up_to=1) == 1
        assert not state.is_internal()
        state.internal_file.touch()
        assert state.is_internal()
