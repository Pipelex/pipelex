# TODOS

Branch: `feature/Concurrency`. Design context lives in [`wip/concurrency/`](wip/concurrency/) — start with [`wip/concurrency/README.md`](wip/concurrency/README.md).

## Done — retry-jitter quick win

Status: **landed** on `feature/Concurrency`. The one self-contained change from the concurrency design doc (see [`wip/concurrency/README.md`](wip/concurrency/README.md#the-one-quick-win--retry-jitter)). Everything else in that doc carries a design decision and is tracked in its own sub-doc.

### Problem

`transport_retry.py` builds its backoff with `wait_exponential` — every retry of a given attempt waits the *same* deterministic interval. Under a 429 storm, all the in-flight requests that got rate-limited at the same moment retry in lockstep, re-firing the storm as a thundering herd. Full jitter (`wait_random_exponential`) spreads the retries across the interval and breaks the synchronization.

### Scope

- One-line change in `pipelex/cogt/inference/transport_retry.py`: `wait_exponential` → `wait_random_exponential`.
- `Retry-After` handling is unaffected — `_transport_retry_wait` returns the header value directly and only falls back to the exponential wait when no header is present.
- Behaves identically in direct mode and Temporal mode: `transport_retry` runs inside the activity in both, where non-determinism is allowed.

### What was done

- [x] Changed the `tenacity` import in `transport_retry.py` from `wait_exponential` to `wait_random_exponential`.
- [x] Updated the `_exponential_wait` binding to `wait_random_exponential(multiplier=1.0, max=_MAX_RETRY_AFTER_SECONDS)` with a comment explaining the full-jitter rationale.
- [x] Updated the `_transport_retry_wait` docstring to say "full-jitter exponential backoff".
- [x] Changelog: folded the full-jitter detail into the existing `[Unreleased]` Added entry for `transport_retry.py` (the module is new in this same cycle, so a separate "Changed" entry would be wrong).
- [x] `make agent-check` — ruff, plxt, pyright, mypy all clean.

### No dedicated test — deliberate

The TDD plan originally called for a test. On review, that was dropped: this is a one-line swap to a different variant of a well-tested third-party function (`tenacity`). Jitter vs. no-jitter has no observable behavioral contract of *our own* to pin — any test would either reason statistically about `random` or mock `tenacity`'s internal `random.uniform` call, i.e. test the library, not our code. The existing `TestRequestWithTransportRetry` suite already covers that retry, `Retry-After` precedence, backoff fallback, and budget exhaustion all still work.

## Larger concurrency design work — not quick wins

Tracked in their own design docs, each needs a dedicated session:

- [`wip/concurrency/fan-out-scheduling.md`](wip/concurrency/fan-out-scheduling.md) — replace `gather_bounded` chunking with a sliding-window semaphore.
- [`wip/concurrency/rate-limiting.md`](wip/concurrency/rate-limiting.md) — per-`PipeBatch` bound + RPM/TPM limiter.
- [`wip/concurrency/batch-partial-failure.md`](wip/concurrency/batch-partial-failure.md) — collecting partial batch results.
