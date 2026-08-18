"""Guards the committed `.test_durations` bookkeeping artifact against a bulk path rewrite.

`.test_durations` maps every test node id to how long it took, and pytest-split reads it to balance the
CI shards (`make gha-tests` with `SPLITS`/`GROUP`; refresh with `make store-test-durations`). It is
generated, committed, and edited by hand by nobody — which is exactly why a bulk rewrite of test paths
(a package move, a sed over `tests/`) walks straight past it: the file still parses, the shards still
run, and they silently unbalance because entries for files that no longer exist can never match a test
again.

The refresh prunes these entries itself (`duration_map.prune_dead_paths`), so this gate is normally
self-healing — running `make store-test-durations` clears it, and on a complete map that costs only a
collection rather than a suite run. The gate stays because the pruning happens when someone *runs* the
refresh, which may be many merges after the rewrite that orphaned the entries.

The gate is on the **file path**, not the node id. A path rewrite breaks paths; parametrization churn
breaks node ids and is benign — a parametrization keyed on a generated fixture legitimately drifts
between runs, and pytest-split treats an unknown id as average duration. Pinning node ids would need a
full unfiltered collection plus a tolerance policy for those; pinning paths is a filesystem check with
no policy at all, and it catches the failure that actually costs something.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

#: Anchored on `tests/` by name rather than by a parent count — a depth index is silently wrong from the
#: workspace root, which holds a sibling `pipelex/` checkout (see `test_hub_layering_guard.py`).
REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests").parent

DURATIONS_PATH = REPO_ROOT / ".test_durations"


def _recorded_durations() -> dict[str, float]:
    """The committed node-id → seconds map."""
    return cast("dict[str, float]", json.loads(DURATIONS_PATH.read_text(encoding="utf-8")))


class TestTestDurationsPaths:
    def test_durations_file_is_committed_and_not_empty(self) -> None:
        """Anti-vacuity: an empty (or absent) map would make every assertion below trivially true."""
        assert DURATIONS_PATH.is_file(), f"{DURATIONS_PATH.name} is committed at the repo root — regenerate it with `make store-test-durations`"
        assert _recorded_durations(), f"{DURATIONS_PATH.name} is empty — regenerate it with `make store-test-durations`"

    def test_every_node_id_is_rooted_in_a_test_file_path(self) -> None:
        """The path extraction below is only meaningful while every key really starts with one."""
        malformed = sorted(node_id for node_id in _recorded_durations() if "::" not in node_id or not node_id.partition("::")[0].endswith(".py"))
        assert not malformed, f"{DURATIONS_PATH.name} holds entries that are not '<path.py>::<test>' node ids: {malformed[:10]}"

    def test_every_recorded_test_file_still_exists(self) -> None:
        """A path that no longer exists is dead weight the shard balancer can never spend."""
        recorded_paths = {node_id.partition("::")[0] for node_id in _recorded_durations()}
        dead = sorted(path for path in recorded_paths if not (REPO_ROOT / path).is_file())
        assert not dead, (
            f"{len(dead)} test file path(s) in {DURATIONS_PATH.name} no longer exist, so the CI shards are "
            f"balanced against tests that cannot run: {dead[:10]}. Run `make store-test-durations` "
            "(alias `make std`), which prunes them."
        )
