# The Test Duration Map

`.test_durations` is a committed JSON map of `pytest node id -> seconds`. Its only consumer is [`pytest-split`](https://github.com/jerry-git/pytest-split), which reads it to divide the suite into balanced CI shards. Nothing in the runtime touches it, and nobody edits it by hand.

This page explains what the map is for, why it is refreshed the way it is, and what to run.

## What it is used for

The CPU-bound test suite is split across eight free GitHub-hosted runners rather than one large paid machine. Two workflows do this — `tests-check.yml` on pull requests to `dev` (the floor Python version only) and `tests-full-check.yml` on pull requests to `main` (every supported version, so four versions times eight shards). Both invoke the same target:

```bash
SPLITS=8 GROUP=<n> make gha-tests
```

`SPLITS`/`GROUP` are what activate `pytest-split`. Without them — which is every local run — the flags expand to nothing, the map is ignored entirely, and the whole suite runs as usual.

The splitting algorithm is `pytest-split`'s default, `duration_based_chunks`: it walks the tests in collection order and cuts at boundaries where the accumulated duration crosses one eighth of the total. Each shard is therefore a *contiguous* slice of the collection, and the map decides where the cuts fall.

## Coverage matters; precision does not

This is the single fact that shapes everything below, and it is worth stating plainly because the intuitive assumption is the opposite one.

A duration map can be wrong in two independent ways. Its recorded **values** can be out of date, or it can be **missing entries** for tests that exist. Measured against the real eight-way split, these cost wildly different amounts:

| What is wrong with the map | Cost in shard balance |
| --- | --- |
| Values weeks out of date, coverage complete | about 7% |
| Values current, weeks of entries missing | over 50% |
| Both (an untouched map, weeks later) | about 65% |

Stale values are nearly free. Missing coverage is ruinous.

The reason is `pytest-split`'s fallback for a node id it has never seen: it imputes the **mean** of the durations it does know. This suite's mean is around 0.25s while its median is around 0.002s — the distribution is dominated by a small number of slow tests, so the mean sits roughly a hundred times above the typical test. A block of newly added fast tests is therefore charged about a hundred times its real cost, and because the chunks are contiguous, that phantom weight shifts every boundary after it. Genuinely slow new tests hit the same problem from the other direction.

There is no cheap way to impute around this. Filling unknown entries with the median, the 25th percentile, or anything else in that range does not recover the balance, because the missing tests carry real time that is unevenly distributed across the collection — no single fill value can put it in the right places. Coverage has to be measured.

Two consequences follow, and they are the design:

- **Refresh on missing coverage, not on elapsed time.** Calendar age is a poor proxy: a quiet fortnight needs no refresh at all, while a single branch that lands five hundred tests breaks the map the day it merges.
- **Re-measuring an already-covered test buys almost nothing.** So the default refresh does not do it.

## What to run

```bash
make store-test-durations     # alias: make std
```

This is the default and it is incremental. It collects the suite (a few seconds), compares the collected node ids against the map, and measures **only** the tests that are missing. When coverage is already complete it measures nothing at all and exits having done a collection — the common case, and it costs seconds rather than the several minutes a full suite run takes.

There is one threshold. When more than 40% of the collected suite is missing from the map (`FULL_RUN_RATIO` in `duration_map.py`), measuring the missing tests individually stops being worth its own bookkeeping, and the incremental target re-measures everything instead — a full run, with the wall clock that implies. So the cheap-refresh promise holds for the ordinary case of a branch or two of new tests, and deliberately does not hold when the map has fallen far behind the suite. Expect it after a very large merge, or on a first run against an empty map.

```bash
make store-test-durations-force   # alias: make stdf
```

This re-measures every test in the CI selection. Reach for it when recorded values are no longer comparable to each other — the machine changed, or the suite changed shape enough that the accumulated values came from meaningfully different conditions. It is not what you want for routine maintenance.

Both targets regenerate the CI-profile test-model fixtures first, then hand off to `pipelex-dev store-test-durations`. The marker expression that selects the tests is `GHA_PYTEST_MARKERS` in the `Makefile`, shared with `gha-tests` so the map can never be balanced against a different set of tests than the one it was measured from.

### When to run it

At release time is the natural cadence, and the release skill does it as a step. Because the incremental refresh is nearly free when nothing is missing, running it more often costs little. Run it explicitly after a branch that adds a large number of tests, rather than waiting for the release.

## What the refresh does to the file

`--store-durations` **merges** into the existing file rather than replacing it — only `--clean-durations`, which we do not use, replaces wholesale. That merge is what makes measuring a subset a legitimate refresh instead of a partial overwrite. Two post-processing passes then run over the merged result.

**Pruning.** Entries whose test *file* no longer exists are dropped. The criterion is deliberately the filesystem and never the collected set: a marker-filtered collection legitimately hides a large slice of the suite (most of `tests/e2e`), so pruning against it would delete live entries. A vanished file, by contrast, cannot come back under any marker. This is the condition `tests/unit/repo/test_test_durations_paths.py` fails on, so that gate is normally self-healing — running the refresh clears it.

**Stabilisation.** Every duration is rounded, and a previously recorded value is kept whenever the new measurement lands within tolerance of it. A value is rewritten only when it moved by more than 30% or more than 0.05s, whichever is larger. The relative term is what spares slow tests, where a fixed floor would be far too tight; the absolute floor is what spares the thousands of sub-millisecond tests, whose relative jitter between runs is enormous and meaningless.

The point of stabilisation is the diff. Re-measuring the suite rewrites essentially every line, because timings never repeat exactly — a full refresh used to produce a diff of over twenty thousand changed lines. That is not merely noisy: it once pushed a release pull request past the size limits of two automated reviewers, both of which declined to review the branch at all. Stabilisation cuts the changed lines by about 95%, for well under a point of shard balance. Rounding happens on both sides of the comparison so the file converges to short values instead of drifting between spellings of the same measurement.

The policy constants live in `pipelex/cli/dev_cli/commands/duration_map.py`, which holds the pure logic and its rationale; `store_test_durations_cmd.py` is the orchestration around it.

## The committed artifact is gated

`tests/unit/repo/test_test_durations_paths.py` checks three things: the file is present and non-empty, every key is a well-formed `<path.py>::<test>` node id, and every recorded test file still exists on disk.

That last check exists because a bulk rewrite of test paths — a package move, a `sed` over `tests/` — walks straight past the map. The file still parses and the shards still run; they simply balance against tests that can never match again. The gate is on the file path rather than the node id on purpose. Path rewrites break paths; parametrization churn breaks node ids and is benign, since an unknown id is only ever imputed. Pinning node ids would require a full unfiltered collection plus a tolerance policy for legitimate drift, where pinning paths is a filesystem check with no policy at all.

## A caveat worth knowing

Tests measured incrementally run in a smaller batch than a full-suite run, under less parallel contention, so their recorded durations are not measured under identical conditions to the rest of the map. Given how little value precision carries — stale values across weeks cost about 7% — this is an acceptable trade for turning a multi-minute step into a multi-second one. `make store-test-durations-force` is the remedy if the accumulated inconsistency ever seems to matter.
