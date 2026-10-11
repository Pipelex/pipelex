import json
import os
import time
from pathlib import Path

import pytest

from pipelex.system.usage_stats.usage_stats_core import (
    CLAIM_MARKER,
    SPOOL_MAX_FILES_PER_TOOL,
    claim,
    pending_files,
    prune,
    read_spool_events,
    release,
    write_spool_file,
)


def _age(*, path: Path, seconds: float) -> None:
    past = time.time() - seconds
    os.utime(path, (past, past))


class TestUsageStatsSpool:
    def test_written_file_holds_its_events(self, tmp_path: Path) -> None:
        """A spool file is `<created-ms>-<random>.json` holding `spool_version` 1 and the events, and no temporary is left."""
        events = [{"event": "command_completed", "uuid": "a"}, {"event": "run_completed", "uuid": "b"}]
        spool_file = write_spool_file(spool_dir=tmp_path, events=events)
        created_ms, _, rest = spool_file.name.partition("-")
        assert created_ms.isdigit()
        assert rest.endswith(".json")
        assert json.loads(spool_file.read_text(encoding="utf-8")) == {"spool_version": 1, "events": events}
        assert read_spool_events(path=spool_file) == events
        assert [entry.name for entry in tmp_path.iterdir()] == [spool_file.name]

    @pytest.mark.parametrize(
        "content",
        ['{"spool_version": 2, "events": []}', '{"spool_version": 1, "events": {}}', '{"spool_version": 1, "events": [1]}', "[]", "not json"],
    )
    def test_file_of_another_shape_is_not_read(self, tmp_path: Path, content: str) -> None:
        path = tmp_path / "1-abc.json"
        path.write_text(content, encoding="utf-8")
        assert read_spool_events(path=path) is None

    def test_spool_keeps_at_most_its_limit_deleting_the_oldest(self, tmp_path: Path) -> None:
        for index_file in range(SPOOL_MAX_FILES_PER_TOOL + 3):
            (tmp_path / f"{1000 + index_file}-seed.json").write_text('{"spool_version": 1, "events": []}', encoding="utf-8")
        newest = write_spool_file(spool_dir=tmp_path, events=[])
        waiting = pending_files(spool_dir=tmp_path)
        assert len(waiting) == SPOOL_MAX_FILES_PER_TOOL
        assert waiting[-1] == newest
        assert waiting[0].name == "1004-seed.json"

    def test_claim_and_release(self, tmp_path: Path) -> None:
        """A claimed file is no longer pending, a second claim fails, and a release gives it back under its name."""
        spool_file = write_spool_file(spool_dir=tmp_path, events=[])
        claimed = claim(path=spool_file)
        assert claimed is not None
        assert CLAIM_MARKER in claimed.name
        assert pending_files(spool_dir=tmp_path) == []
        assert claim(path=spool_file) is None
        release(claimed=claimed)
        assert pending_files(spool_dir=tmp_path) == [spool_file]

    def test_prune(self, tmp_path: Path) -> None:
        """Stale claims come back, stale temporaries and month-old files go, fresh ones stay."""
        stale_claim = tmp_path / f"{int(time.time() * 1000)}-a.json{CLAIM_MARKER}crashed"
        stale_claim.write_text("{}", encoding="utf-8")
        _age(path=stale_claim, seconds=11 * 60)
        live_claim = tmp_path / f"{int(time.time() * 1000)}-b.json{CLAIM_MARKER}sending"
        live_claim.write_text("{}", encoding="utf-8")
        stale_temp = tmp_path / ".tmp-old"
        stale_temp.write_text("{}", encoding="utf-8")
        _age(path=stale_temp, seconds=61 * 60)
        fresh_temp = tmp_path / ".tmp-new"
        fresh_temp.write_text("{}", encoding="utf-8")
        month_old_ms = int((time.time() - 31 * 24 * 3600) * 1000)
        too_old = tmp_path / f"{month_old_ms}-c.json"
        too_old.write_text("{}", encoding="utf-8")
        prune(spool_dir=tmp_path)
        names = sorted(entry.name for entry in tmp_path.iterdir())
        assert stale_claim.name.split(CLAIM_MARKER)[0] in names
        assert live_claim.name in names
        assert fresh_temp.name in names
        assert stale_temp.name not in names
        assert too_old.name not in names
