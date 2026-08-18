"""Pure logic for the pytest-split duration map committed at ``.test_durations``.

The map is a ``node id -> seconds`` dict that ``pytest-split`` reads to balance the CI shards
(``make gha-tests`` with ``SPLITS``/``GROUP``). This module owns the three policies that keep it
useful without making it a diff-churn machine; the ``rich``/subprocess orchestration lives in
``store_test_durations_cmd.py``, and the committed artifact is gated by
``tests/unit/repo/test_test_durations_paths.py``.

**Coverage is what matters, not precision.** Measured against the real 8-way split: a map whose
values are weeks out of date but whose *coverage* is complete costs about 7% of shard balance, while
a map with current values and weeks of *missing* entries costs over 50%. The reason is
``pytest-split``'s fallback — an unknown node id is imputed at the mean duration, and this suite's
mean (~0.25s) sits about a hundred times above its median (~0.002s), so a block of new tests both
mis-sizes itself and shifts every chunk boundary after it. That asymmetry is why the refresh is
triggered by :func:`missing_node_ids` rather than by the age of the file, and why re-measuring an
already-covered test buys nothing.

**Stability is bought cheaply because precision is worth so little.** Re-measuring the whole suite
rewrites essentially every line (timings never repeat exactly), which historically made the release
diff large enough that automated PR reviewers declined to read it. :func:`stabilize` keeps the
previously recorded value whenever the new measurement lands within tolerance of it, so only entries
that moved meaningfully are rewritten — a ~95% cut in changed lines for well under a point of shard
balance. The stored value is a rounded one, and the comparison happens on the rounded grid, so the
file converges to short values instead of drifting between spellings.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pathlib import Path

#: A re-measurement is written only if it differs from the stored value by more than
#: ``max(RELATIVE_TOLERANCE * stored, ABSOLUTE_TOLERANCE)``. The absolute floor is what spares the
#: thousands of sub-millisecond tests, whose relative jitter between runs is enormous and meaningless;
#: the relative term is what spares the slow tests, where a fixed floor would be far too tight.
RELATIVE_TOLERANCE = 0.3
ABSOLUTE_TOLERANCE = 0.05

#: Durations are stored rounded to this many decimals. Four decimals is well below the precision the
#: shard balancer can act on and keeps the entries short; values that round to zero are tests that are
#: genuinely free at this granularity, and recording them as zero is correct rather than lossy.
ROUNDING_DECIMALS = 4

#: Above this share of the collected suite missing from the map, the incremental refresh stops being
#: worth its own bookkeeping and the full suite is re-measured instead. It also keeps the node-id
#: argument vector to a sane size.
FULL_RUN_RATIO = 0.4


def load_duration_map(*, path: Path) -> dict[str, float]:
    """Read the committed map, treating an absent file as an empty one."""
    if not path.is_file():
        return {}
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(loaded, list):
        # pytest-split's pre-v1 list-of-lists format, normalised the same way the plugin still does.
        return dict(cast("list[tuple[str, float]]", loaded))
    return dict(cast("dict[str, float]", loaded))


def write_duration_map(*, path: Path, durations: dict[str, float]) -> None:
    """Write the map in pytest-split's own on-disk shape, plus a trailing newline for git."""
    path.write_text(json.dumps(durations, sort_keys=True, indent=4) + "\n", encoding="utf-8")


def file_path_of(*, node_id: str) -> str:
    """The test file path a node id is rooted in (``a/b.py::TestX::test_y`` -> ``a/b.py``)."""
    return node_id.partition("::")[0]


def missing_node_ids(*, collected: list[str], durations: dict[str, float]) -> list[str]:
    """Collected tests the map has no entry for — the only staleness that costs real balance.

    Order follows ``collected`` so the refresh runs them in collection order.
    """
    return [node_id for node_id in collected if node_id not in durations]


def prune_dead_paths(*, durations: dict[str, float], repo_root: Path) -> tuple[dict[str, float], list[str]]:
    """Drop entries whose test *file* no longer exists, returning the survivors and the dropped ids.

    The criterion is the filesystem, never the collected set: a marker-filtered collection legitimately
    hides a large slice of the suite (most of ``tests/e2e``), so pruning against it would delete live
    entries. A vanished file cannot come back under any marker, which is exactly the condition
    ``tests/unit/repo/test_test_durations_paths.py`` fails on — pruning here is what makes that gate
    self-healing, since ``--store-durations`` only ever merges and would otherwise keep the corpse.
    """
    kept: dict[str, float] = {}
    dropped: list[str] = []
    existing_paths: dict[str, bool] = {}
    for node_id, duration in durations.items():
        file_path = file_path_of(node_id=node_id)
        if file_path not in existing_paths:
            existing_paths[file_path] = (repo_root / file_path).is_file()
        if existing_paths[file_path]:
            kept[node_id] = duration
        else:
            dropped.append(node_id)
    return kept, dropped


def stabilize(
    *,
    previous: dict[str, float],
    current: dict[str, float],
    relative_tolerance: float = RELATIVE_TOLERANCE,
    absolute_tolerance: float = ABSOLUTE_TOLERANCE,
    decimals: int = ROUNDING_DECIMALS,
) -> dict[str, float]:
    """Round every duration, then keep the previously stored value wherever it is still within tolerance.

    Rounding happens *before* the comparison so both sides live on the same grid — otherwise an entry
    would flip between two spellings of the same measurement and defeat the point. Entries absent from
    ``previous`` are new, and are taken at their rounded measurement.

    Applying this to an un-normalised map rewrites it once, wholesale, onto the rounded grid; every
    refresh after that touches only the entries that genuinely moved.
    """
    stabilized: dict[str, float] = {}
    for node_id, measurement in current.items():
        rounded = round(measurement, decimals)
        previously_recorded = previous.get(node_id)
        if previously_recorded is None:
            stabilized[node_id] = rounded
            continue
        # Both sides are rounded before they are compared, and the ROUNDED recorded value is what gets
        # kept. Keeping the raw stored spelling instead would be self-defeating: an entry inside
        # tolerance would preserve its original long float forever, so the file would never converge
        # and the rounding would only ever apply to entries that were being rewritten anyway.
        recorded = round(previously_recorded, decimals)
        if abs(rounded - recorded) <= max(relative_tolerance * recorded, absolute_tolerance):
            stabilized[node_id] = recorded
        else:
            stabilized[node_id] = rounded
    return stabilized
