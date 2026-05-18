# Concurrency & batching — design doc

Status: **design scoping**. The quick wins below are specced enough to implement; the two larger pieces of design work are split into their own docs — [`rate-limiting.md`](rate-limiting.md) and [`batch-partial-failure.md`](batch-partial-failure.md).

## Context & scope

The resilience strategy is settled: **Temporal is the resilience system.** We deliberately decided *not* to build a cheap resilience system in direct mode (see `TODOS.md` and `wip/error-handling/`).

The open problem is narrower: the direct-mode batching/asyncio system breaks too easily. The driving question: *what is a best-practice basic backpressure / rate-limiting system at the asyncio layer, so the system does not crash when asked to process e.g. 1000 documents?*

"Basic backpressure so it doesn't fall over" — not durable retry, not resilience. That stays Temporal's job.

## Read this first: direct mode vs Temporal mode

Every change in this doc behaves differently depending on the execution mode, so the mode split is the frame for everything that follows — not an afterthought.

There are two modes:

- **Direct mode** — everything runs in one Python process, on one asyncio event loop.
- **Temporal mode** — the same pipes run as Temporal workflows, distributed across N worker processes.

**Temporal slices execution at the activity boundary.** From the temporal code (`temporal_pipe_router.py`, `wf_pipe_run.py`, `act_llm_generate.py`):

- **Controllers run as workflow code.** `TemporalPipeRouter` is a drop-in `PipeRouterProtocol`. `PipeBatch._live_run_controller_pipe` — including `gather_bounded` over the branch factories — runs *inside the workflow*. Each branch's `get_pipe_router().run(...)` becomes a **child workflow**.
- **Inference runs as an activity.** The actual LLM/img-gen/extract call is `act_llm_gen_text` & co. — a Temporal **activity**: normal Python, running in **N separate worker processes**.

The consequences that drive every decision below:

- Code **above** the activity boundary (controllers, `gather_bounded`) is **workflow code** → must be deterministic: no wall-clock, no `time.sleep`, no real-time `asyncio.sleep`. It is *not* disabled under Temporal — it still runs, as workflow code.
- Code **inside** the activity is **normal Python** → wall-clock, sleep, jitter all fine — but it runs **per-process**, blind to the other workers.

| Layer | Direct mode | Temporal mode |
| --- | --- | --- |
| `PipeBatch` fan-out (`gather_bounded`) | In-process coroutines + memory | Workflow code; bounds concurrent child-workflow starts |
| Inference call (LLM/img-gen/extract) | In-process async call | Activity, one of N worker processes |
| Retry | `transport_retry` (`tenacity`) | `transport_retry` *and* Temporal activity `RetryPolicy` |
| Rate / resource limits | Nothing today | Temporal task-queue + worker knobs (see `rate-limiting.md`) |

## Why the current system breaks too easily

Three distinct weaknesses, and they compound under load. Code inspected: `pipelex/tools/misc/async_utils.py` (`gather_bounded`), `pipelex/pipe_controllers/batch/pipe_batch.py` (`PipeBatch`), `pipelex/cogt/inference/transport_retry.py`.

### 1. `gather_bounded` chunks — head-of-line blocking

`gather_bounded` runs items in chunks of `max_concurrency` and waits for the *whole chunk* to drain before starting the next. If one item in a chunk of 8 takes 60s, the other 7 slots sit idle the whole time. Throughput collapses to "slowest item per chunk."

### 2. The bound is per-`PipeBatch`, not process-global

`max_concurrency = 8` (`pipelex.toml`) is applied independently by each `PipeBatch`. Nested batches, or sibling pipes running concurrently, multiply: two batches → 16 in flight, a nested batch → 64. Nothing sees the total.

### 3. Concurrency ≠ rate — and rate is what providers enforce

Providers rate-limit on **requests-per-minute (RPM)** and **tokens-per-minute (TPM)**, not on concurrency. 8 concurrent calls each finishing in ~200ms = ~40 RPS = ~2400 RPM, which blows a 500-RPM tier instantly. The result is a 429 storm; `transport_retry` then re-fires that storm, and because the exponential backoff has no jitter, the retries re-synchronize into a thundering herd.

Weaknesses 1 and the retry-jitter gap are **quick wins** (below). Weaknesses 2 + 3 are the hard part — a real rate limiter — covered in [`rate-limiting.md`](rate-limiting.md).

## Quick wins — do these first

Small, isolated, low-risk. None of them is the full fix, but each removes a sharp edge and they are independent of the rate-limiting design.

### QW1 — semaphore fan-out in `gather_bounded`

Replace `gather_bounded`'s chunking with a semaphore acquired *before* the factory is called:

```python
sem = asyncio.Semaphore(max_concurrency)
async def _run(factory):
    async with sem:          # acquired before factory() → materialization still bounded
        return await factory()
results = await asyncio.gather(*(_run(f) for f in factories), return_exceptions=True)
```

Same memory guarantee — at most `max_concurrency` deep-copied working memories alive at once, the property the comment in `async_utils.py` protects — but no head-of-line blocking: as soon as one finishes, the next starts.

**Direct vs Temporal:** Mode-agnostic improvement. `gather_bounded` runs as workflow code under Temporal; it is not disabled. `asyncio.Semaphore` involves no wall-clock — acquisition order follows task scheduling, which Temporal replays deterministically — so it is workflow-safe (the current chunking is too; worth a sanity check against the workflow sandbox). Under Temporal its meaning shifts from "in-flight coroutines" to "concurrent child-workflow starts", which is still a useful bound.

Effort: small, isolated. Highest impact-per-line. Do first.

### QW2 — jitter in `transport_retry`

`wait_exponential` in `transport_retry.py` is jitter-free; under a 429 storm every retry re-fires in lockstep. Switch to `wait_random_exponential` (full jitter).

**Direct vs Temporal:** `transport_retry` runs inside the activity in both modes — jitter is fine there (non-determinism allowed in activities). Pre-existing nuance, not worsened by this change: under Temporal there are already two retry layers — `tenacity` inside the activity and Temporal's activity `RetryPolicy` outside it. Whether the activity should fail faster and let `RetryPolicy` own retries is a separate, existing design question.

Effort: tiny.

There is no QW3. An earlier draft listed "per-item batch failure policy" as a quick win — it is not. The `gather_bounded` part is trivial, but deciding what `PipeBatch` does with a partial result touches the type system, the MTHDS language contract, reporting, the graph tracer, and the Temporal boundary. It is now its own design doc — see below.

## Larger design work — separate docs

Two pieces of design work are too large to spec inline. Each has its own doc.

### Rate limiting — [`rate-limiting.md`](rate-limiting.md)

Weaknesses 2 + 3 — a per-`PipeBatch` (not global) bound, and the absence of any RPM/TPM limiter — are the real cause of the crash at scale. The fix is genuinely mode-dependent: direct mode needs an in-process limiter, Temporal mode needs server-side task-queue limits. It is **not one system that works in both modes**. The doc also records the finding that the Temporal-mode machinery already exists.

### Batch partial failure — [`batch-partial-failure.md`](batch-partial-failure.md)

`gather_bounded` raises on the first exception, so one malformed document discards every good result in the batch. Collecting partial results sounds like a small change, but it forces a decision on the *type* of a batch output — and the options range from a sparse list to an envelope concept, the latter being an MTHDS language-semantics change. The doc lays out the blast radius and the open questions.

## Layering summary

| Layer | Responsibility |
| --- | --- |
| `PipeBatch` | Fan-out *shape* — how work is split (QW1 fixes the primitive) |
| Inference rate/concurrency gate | The actual backpressure — see `rate-limiting.md` |
| `transport_retry` | Residual 429/5xx — QW2 adds jitter |
| Temporal | Durability — out of scope here |

## Suggested next step

Land QW1 (and optionally QW2) — they are self-contained and unblock nothing else. Then take up [`rate-limiting.md`](rate-limiting.md) and [`batch-partial-failure.md`](batch-partial-failure.md), each as its own design session — they are independent of each other.
