# Fan-out scheduling — design notes

Status: **design scoping**, not yet a plan. One of the design tracks of the concurrency & batching work — see [`README.md`](README.md) for the overview. Read the README's "direct mode vs Temporal mode" section first — this doc assumes that frame.

## Why this is its own doc

Replacing `gather_bounded`'s chunking with a sliding-window semaphore *looks* like a one-liner. The scheduling improvement is real and worth having, but the obvious implementation **silently regresses fail-fast behavior**, and fixing that properly:

- couples this change to the partial-failure policy in [`batch-partial-failure.md`](batch-partial-failure.md);
- raises a Python-version decision (`asyncio.TaskGroup` is 3.11+).

So it carries a design decision, not just an edit.

## The mechanism: chunk barrier vs sliding window

**Today — chunking.** `gather_bounded` splits the factories into chunks of `max_concurrency` and, for each chunk, does `await asyncio.gather(...)` before starting the next. The defining property: **a chunk does not advance until every item in it finishes.** With `max_concurrency=8` and 100 items, that is 13 sequential barriers.

**Proposed — semaphore.** All factories go into one `asyncio.gather`; each acquires a semaphore before running. At any instant ≤ `max_concurrency` run, but the moment *any one* finishes it releases the semaphore and the *next pending* factory starts immediately. No chunk boundaries — a continuous sliding window.

```python
sem = asyncio.Semaphore(max_concurrency)
async def _run(factory):
    async with sem:          # acquired before factory() → materialization still bounded
        return await factory()
```

The semaphore is acquired *before* calling the factory, so the property the comment in `async_utils.py` protects still holds: at most `max_concurrency` deep-copied working memories materialized at once, per `PipeBatch`.

## What it wins

### Win 1 — throughput: idle slots disappear

Under chunking, a chunk's wall-clock cost is its **slowest** item, not its average. As fast items in a chunk finish, their slots sit idle waiting for the chunk's straggler. That idle time is pure waste.

Everyday case (not pathological): 100 items, durations spread uniformly 1–10s, `max_concurrency=8`.

- **Chunking:** each chunk of 8 takes `max` of 8 samples ≈ 9s. 13 chunks ≈ **~115s**.
- **Semaphore:** total work ÷ slots = `100 × 5.5s ÷ 8` ≈ **~70s**.

Roughly a **40% wall-clock reduction**, purely from never leaving a slot idle while work is pending. The wider the spread of item durations, the bigger the gap.

### Win 2 — a slow branch stops poisoning its neighbors

The qualitative win. Under chunking, one 60s branch does two kinds of damage: it pins the other 7 slots in its chunk idle for ~59s, *and* it delays the start of every later chunk. A single straggler taxes ~7 innocent branches plus everything queued behind it.

Under the semaphore, that 60s branch occupies exactly **one** slot for 60s. The other 7 keep cycling through the queue at full speed. The slow branch costs only itself.

## What it does not win

- The bound is unchanged: still `max_concurrency`, still per-`PipeBatch`. Memory footprint identical (≤ `max_concurrency` deep copies per batch).
- No global bound, no rate limiting — weaknesses 2 and 3 are untouched (that is [`rate-limiting.md`](rate-limiting.md)).

It is purely a *scheduling* improvement: same resources, no idle gaps.

## The catch: the naive change regresses fail-fast

Today's `gather_bounded` aborts early. From its docstring: it drains the current chunk, raises the first error by input index, and **starts no later chunk**. A fatal error in item 3 wastes at most one chunk's worth of items.

The naive semaphore version — `asyncio.gather(*(_run(f) for f in factories), return_exceptions=True)` — schedules *all* factories. With `return_exceptions=True`, gather does not stop on the first failure: it runs **every** branch, then raises. For a 1000-document batch where item 3 fails fatally, that is ~997 needless branch runs — and each branch run is real LLM/inference spend.

So the semaphore change done *correctly* needs **sibling cancellation**: on the first exception, cancel the not-yet-started factories. That cancellation is cheap and exactly right — a factory still waiting on the semaphore has not done its deep copy or fired its API call, so cancelling it costs nothing and saves everything.

## Coupling to `batch-partial-failure.md`

Whether cancellation is even wanted depends on the failure policy decided in [`batch-partial-failure.md`](batch-partial-failure.md):

- **Fail-fast (today's default)** → the semaphore version *must* add sibling cancellation, or it is a regression.
- **Collect-partial** → running every branch is the *intended* behavior; `return_exceptions=True` with no cancellation is correct, and the naive version is fine.

So the exact shape of this change is not independent. The two docs should be decided together, or this one should follow the partial-failure decision. A reasonable design keeps both: cancel-on-first-error when the policy is fail-fast, run-all when it is collect-partial — the semaphore wrapper takes the policy as a parameter.

## Decision point: `asyncio.TaskGroup` and Python 3.10

`asyncio.TaskGroup` does sibling cancellation natively — first exception cancels the rest — which is exactly the fail-fast behavior above. But `TaskGroup` is **Python 3.11+**, and it raises `ExceptionGroup`, also 3.11+. The project currently targets 3.10+ (`requires-python = ">=3.10,<3.15"`), and the coding standards explicitly say to avoid `ExceptionGroup` / `except*` unless using the `exceptiongroup` backport.

Three ways forward:

1. **Hand-roll cancellation.** Manual "on first exception, cancel pending tasks" logic works on 3.10 with no new dependency. More code than `TaskGroup`, but not much, and it keeps the door open.
2. **Drop Python 3.10.** Bump `requires-python` to `>=3.11`, use `TaskGroup` natively. Cleanest code, but a breaking support change with its own blast radius beyond this doc — needs a separate, deliberate call.
3. **Version-gated / backport.** Use `TaskGroup` on 3.11+, fall back on 3.10 (the `taskgroup` / `exceptiongroup` backports, or option 1's hand-rolled path). Most complexity for the least benefit.

This is a genuine project-level decision, not something to settle inside `gather_bounded`. Recommendation for scoping: option 1 unblocks this change today without forcing the 3.10 question; option 2 is worth raising on its own merits but should not be driven solely by this doc.

## Direct vs Temporal

`gather_bounded` runs as workflow code under Temporal — it is not disabled. `asyncio.Semaphore` involves no wall-clock; acquisition order follows task scheduling, which Temporal replays deterministically, so the semaphore is workflow-safe (the current chunking is too — worth a sanity check against the workflow sandbox). Under Temporal the bound's meaning shifts from "in-flight coroutines" to "concurrent child-workflow starts", still a useful bound.

Cancellation is also fine under Temporal — cancelling a not-yet-started child-workflow dispatch is deterministic. `TaskGroup`, if chosen, would need the same sandbox sanity check.

## Open questions for the design session

- Decide the failure policy in `batch-partial-failure.md` first, or jointly — the cancellation behavior here depends on it.
- `asyncio.TaskGroup` (drop 3.10) vs hand-rolled cancellation (keep 3.10) vs version-gated. See the decision point above.
- Should the semaphore wrapper take the failure policy as an explicit parameter (cancel-on-error vs run-all), so one primitive serves both modes?
- Does `gather_bounded` keep its current "raise first error by input index" ordering guarantee under the semaphore, where completion order is no longer chunk-aligned?

## Suggested next step

Settle the failure policy with `batch-partial-failure.md`, then implement the semaphore wrapper parameterized by that policy. Treat the Python-3.10 question as a separate, explicit decision rather than letting this change force it.
