# The Test Duration Map

`.test_durations` is a committed JSON map of `pytest node id -> seconds`. It has two consumers: [`pytest-split`](https://github.com/jerry-git/pytest-split), which reads it to divide the suite into balanced CI shards, and the `slow` marker, which the everyday test runs use to skip the few tests that hold most of the suite's time. Nothing in the runtime touches it, and nobody edits it by hand.

This page explains what the map is for, why it is refreshed the way it is, and what to run.

## What it is used for

The CPU-bound test suite is split across eight free GitHub-hosted runners rather than one large paid machine. Two workflows do this — `tests-check.yml` on pull requests to `dev` (the floor Python version only) and `tests-full-check.yml` on pull requests to `main` (every supported version, so four versions times eight shards). Both invoke the same target:

```bash
SPLITS=8 GROUP=<n> make gha-tests
```

`SPLITS`/`GROUP` are what activate `pytest-split`. Without them — which is every local run — the flags expand to nothing, the map is ignored entirely, and the whole suite runs as usual.

The splitting algorithm is `pytest-split`'s default, `duration_based_chunks`: it walks the tests in collection order and cuts at boundaries where the accumulated duration crosses one eighth of the total. Each shard is therefore a *contiguous* slice of the collection, and the map decides where the cuts fall.

## The `slow` marker: everyday runs skip the slowest tests

The suite's time is concentrated in very few tests: its median test takes about three milliseconds while its mean is near a quarter of a second. The everyday runs therefore skip the slowest tests, and the full runs keep them.

**Nobody marks a test `slow` by hand.** The root `tests/conftest.py` registers a `--slow-test-seconds` option and, when it is given, marks `slow` at collection time every test whose duration recorded in `.test_durations` is at or above it. The logic lives in `tests/helpers/slow_tests.py`. Three rules follow:

- **A test missing from the map is not slow.** It has not been measured yet; the next `make store-test-durations` records it, and from then on its recorded duration decides.
- **Without the option, nothing is marked**, so `-m "not slow"` then deselects nothing.
- **The marking happens before any deselection.** The hook runs first among the collection hooks, so pytest's own `-m` filter sees the marker, and `pytest-split`, which cuts the shards last, balances only the tests that will actually run.

The threshold is `SLOW_TEST_SECONDS` in the `Makefile`, currently **0.5 seconds**, and it is the one place to change it. The everyday runs combine `and not slow` with their usual marker expression and pass the threshold:

| Run | Slow tests |
| --- | --- |
| `make agent-test` and `make agent-test-debug` | skipped |
| `tests-check.yml`, on every pull request, through `SKIP_SLOW_TESTS=1 make gha-tests` | skipped |
| `tests-full-check.yml`, the gate on pull requests to `main`, through `make gha-tests` | run |
| every other target (`make test`, `make t`, `make tp`, `make codex-tests`, the inference targets) | run |
| the API server's tests (`make api-agent-test`, `make -C api gha-tests`) | run: they are not in the map |

To run the everyday selection in full, empty the threshold: `make agent-test SLOW_TEST_SECONDS=`. A targeted run such as `.venv/bin/pytest tests/unit/...` passes no threshold, so it never skips anything.

The API server's tests, under `api/tests/`, are not in `.test_durations`: `store-test-durations` measures only the library's suite, and the server's runs from its own directory and environment. Since a test missing from the map is never slow, the server's suite always runs whole, which suits it: it is small.

### Why 0.5 seconds

These are the numbers for the `make agent-test` selection, computed from the committed map when the marker was introduced. Of the 22,683 tests that selection collected, 22,636 had a recorded duration, together 5,272 seconds of test time.

| Threshold | Tests marked slow | Share of the tests | Share of the time | Time left to run |
| --- | --- | --- | --- | --- |
| 0.25 s | 2,975 | 13.1% | 89.5% | 553 s |
| 0.5 s | 2,245 | 9.9% | 84.7% | 809 s |
| 1 s | 1,230 | 5.4% | 70.0% | 1,580 s |
| 2 s | 426 | 1.9% | 49.4% | 2,667 s |

At 0.5 seconds, one test in ten is skipped and the time left to run drops by a factor of six and a half. Going lower buys little more time for many more skipped tests, and going higher keeps twice as much time for half as many skipped tests. The slow tests are spread across the suite rather than confined to one directory: in that selection, 1,398 of them were unit tests, 668 integration tests and 178 end-to-end tests, the end-to-end tests being nearly all slow.

The cost of skipping them is that a regression only a slow test catches surfaces on the full run, which is the gate on pull requests to `main`, rather than on the pull request into `dev`. Run `make agent-test SLOW_TEST_SECONDS=` before pushing a change that touches what the slow tests cover, such as whole-method runs and the CLI end to end.

The figures drift as the map is refreshed. To recompute them, collect the selection with `.venv/bin/pytest --collect-only -q -m "<expression>"` and add up the durations the map records for the collected node ids at each threshold.

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
