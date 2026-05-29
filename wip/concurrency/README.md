# Concurrency & batching — design doc

Status: **design scoping**. The one quick win this doc identified — retry jitter — has since shipped (see below). What remains is three larger pieces of design work, split into their own docs — [`fan-out-scheduling.md`](fan-out-scheduling.md), [`rate-limiting.md`](rate-limiting.md), and [`batch-partial-failure.md`](batch-partial-failure.md).

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

Providers rate-limit on **requests-per-minute (RPM)** and **tokens-per-minute (TPM)**, not on concurrency. 8 concurrent calls each finishing in ~200ms = ~40 RPS = ~2400 RPM, which blows a 500-RPM tier instantly. The result is a 429 storm; `transport_retry` then re-fires that storm. The backoff used to be jitter-free, so retries re-synchronized into a thundering herd — that part is now fixed (full jitter shipped, see below), but the underlying RPM/TPM overrun that triggers the storm remains.

The retry-jitter gap was the one true quick win and has since shipped (below). Weakness 1 looked like one but is not — fixing it correctly carries a design decision, so it has its own doc, [`fan-out-scheduling.md`](fan-out-scheduling.md). Weaknesses 2 + 3 are the hard part — a real rate limiter — covered in [`rate-limiting.md`](rate-limiting.md).

## Where `max_concurrency` lives today

`max_concurrency` is a field on `PipelineExecutionConfig` (`pipelex/system/configuration/configs.py`), read at `pipe_batch.py` via `get_config().pipelex.pipeline_execution_config.max_concurrency`. It is an `int >= 1` or the literal `"unbounded"`, set to `8` in `pipelex.toml`.

So today it is **one global config value**, not a per-`PipeBatch` setting — `BatchParams` carries only the input list/item names, no concurrency field. Every `PipeBatch` reads the same global number and applies it **independently** to its own fan-out.

Scope across processes:

- **Direct mode** — the submitter is the only process, so the global config value is global to everything.
- **Temporal mode** — `PipeBatch` runs as workflow code on a worker, and `get_config()` reads *that worker's* config. So the value comes from the worker, not the submitter — incidentally, because config is per-process. It is **not** the Temporal worker-runtime knob (`WorkerRuntimeProfile.max_concurrent_activities` & co. in `config_temporal.py` are separate); `max_concurrency` is a pure Pipelex setting the controller reads wherever it runs.

This is the mechanism behind weakness 2: a global *number* applied per-batch is not a global *bound*. Each `PipeBatch` independently permits `max_concurrency` branches, so sibling batches sum and nested batches multiply (`max_concurrency²`).

**Design option — make it per-`PipeBatch`.** An optional `max_concurrency` field could be added to `BatchParams` (the per-`PipeBatch` object parsed from `.mthds`), falling back to the global config. This is a *fan-out shape* knob — useful, but it does not fix weakness 2, since shape knobs still multiply under nesting. It carries one Temporal advantage worth noting: a value on `BatchParams` is part of the fixed pipe blueprint / workflow input, so it replays deterministically — strictly safer than `PipeBatch` reading global config inside workflow code, which `wf_pipe_run.py` already warns against for "config-derived" values that "change across deploys". Tracked as an open question — see [`rate-limiting.md`](rate-limiting.md).

## Shipped — retry jitter

`transport_retry.py` now uses full-jitter `wait_random_exponential` (`transport_retry.py:44`); it was previously jitter-free `wait_exponential`, so under a 429 storm every retry re-fired in lockstep. With full jitter each wait is drawn from `uniform(0, exponential_bound)`, breaking the lockstep.

**Direct vs Temporal:** `transport_retry` runs inside the activity in both modes — jitter is fine there (non-determinism allowed in activities). Pre-existing nuance, unaffected by this change: under Temporal there are already two retry layers — `tenacity` inside the activity and Temporal's activity `RetryPolicy` outside it. Whether the activity should fail faster and let `RetryPolicy` own retries is a separate, existing design question.

## Larger design work — separate docs

Three pieces of design work are too large to spec inline. Each has its own doc. They are related — all three touch `gather_bounded` or the inference path — but can be taken in separate sessions, with one coupling noted below.

### Fan-out scheduling — [`fan-out-scheduling.md`](fan-out-scheduling.md)

Replacing `gather_bounded`'s chunking with a sliding-window semaphore (weakness 1) is a real throughput win — idle slots disappear and a slow branch stops blocking its neighbors. But the obvious one-liner silently regresses fail-fast: it would run all branches even when branch 3 fails fatally, burning ~997 needless LLM calls in a 1000-document batch. Doing it right needs sibling cancellation, which **couples this doc to `batch-partial-failure.md`** (the cancellation behavior depends on the fail-fast vs collect-partial policy) and raises a Python-version question (`asyncio.TaskGroup` is 3.11+; the project still supports 3.10).

### Rate limiting — [`rate-limiting.md`](rate-limiting.md)

Weaknesses 2 + 3 — a per-`PipeBatch` (not global) bound, and the absence of any RPM/TPM limiter — are the real cause of the crash at scale. The fix is genuinely mode-dependent: direct mode needs an in-process limiter, Temporal mode needs server-side task-queue limits. It is **not one system that works in both modes**. The doc also records the finding that the Temporal-mode machinery already exists.

### Batch partial failure — [`batch-partial-failure.md`](batch-partial-failure.md)

`gather_bounded` raises on the first exception, so one malformed document discards every good result in the batch. Collecting partial results sounds like a small change, but it forces a decision on the *type* of a batch output — and the options range from a sparse list to an envelope concept, the latter being an MTHDS language-semantics change. The doc lays out the blast radius and the open questions.

## Layering summary

| Layer | Responsibility |
| --- | --- |
| `PipeBatch` | Fan-out *shape* — how work is split (scheduling redesign in `fan-out-scheduling.md`) |
| Inference rate/concurrency gate | The actual backpressure — see `rate-limiting.md` |
| `transport_retry` | Residual 429/5xx — full jitter (`wait_random_exponential`) shipped |
| Temporal | Durability — out of scope here |

## Suggested next step

The retry-jitter quick win has shipped. Take up the three design docs as design sessions: [`fan-out-scheduling.md`](fan-out-scheduling.md) and [`batch-partial-failure.md`](batch-partial-failure.md) are coupled through the failure-handling policy and are best taken together (or in that order); [`rate-limiting.md`](rate-limiting.md) is independent of both.
