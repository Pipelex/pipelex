# Concurrency, batching & rate limiting — findings

Status: **investigation notes**, not a design. This doc captures the analysis from a scoping session so a follow-up session can build the actual design on top of it.

## Context & scope

The resilience strategy is settled: **Temporal is the resilience system.** We deliberately decided *not* to build a cheap resilience system in direct mode (see `TODOS.md` and `wip/error-handling/`).

The open problem is narrower: the direct-mode batching/asyncio system breaks too easily. The question driving this investigation: *what is a best-practice basic rate-limiting / backpressure system at the asyncio layer, so the system does not crash when asked to process e.g. 1000 documents?*

"Basic backpressure so it doesn't fall over" — not durable retry, not resilience. That stays Temporal's job.

## Code inspected

- `pipelex/tools/misc/async_utils.py` — `gather_bounded`, the bounded fan-out primitive.
- `pipelex/pipe_controllers/batch/pipe_batch.py` — `PipeBatch`, the only caller of `gather_bounded` of interest here. Already carries a `LARGE_BATCH_ADVISORY_THRESHOLD` warning that points large batches at Temporal.
- `pipelex/cogt/inference/transport_retry.py` — Tier-1 `tenacity` transport retry for SDK-less inference paths.
- `pipelex/temporal/tprl_pipe/temporal_pipe_router.py`, `wf_pipe_run.py` — how pipes dispatch as workflows / child workflows.
- `pipelex/temporal/tprl_content_generation/act_llm_generate.py` — inference exposed as Temporal activities.
- Config: `pipelex/pipelex.toml` → `pipeline_execution_config.max_concurrency = 8`.

## Why the current system breaks too easily

Three distinct weaknesses, and they compound under load.

### 1. `gather_bounded` chunks — head-of-line blocking

`gather_bounded` runs items in chunks of `max_concurrency` and waits for the *whole chunk* to drain before starting the next. If one item in a chunk of 8 takes 60s, the other 7 slots sit idle the whole time. Throughput collapses to "slowest item per chunk."

A semaphore acquired *before* calling the factory gives the same memory bound — the property the comment in `async_utils.py` is protecting (at most `max_concurrency` deep-copied working memories materialized at once) — without the stall. As soon as one finishes, the next starts.

### 2. The bound is per-`PipeBatch`, not process-global

`max_concurrency = 8` is applied independently by each `PipeBatch`. Nested batches, or sibling pipes running concurrently, multiply: two batches → 16 in flight, a nested batch → 64. Nothing in the system sees the total.

### 3. Concurrency ≠ rate — and rate is what providers enforce

Providers rate-limit on **requests-per-minute (RPM)** and **tokens-per-minute (TPM)**, not on concurrency. 8 concurrent calls each finishing in ~200ms = ~40 RPS = ~2400 RPM, which blows a 500-RPM tier instantly. The result is a 429 storm; `transport_retry` then re-fires that storm, and because the exponential backoff has no jitter, the retries re-synchronize into a thundering herd.

For 1000 documents all three fire at once. On top of that, `gather_bounded` raises on the first exception (first-error-aborts): one malformed document discards 999 good results.

## Proposed changes (direct mode)

The guiding principle: **concurrency and rate are separate concerns and belong at separate layers.** Do not make `PipeBatch` do both.

### A — Fix the fan-out primitive: semaphore over factories, not chunking

Replace `gather_bounded`'s chunking with a semaphore acquired *before* the factory is called:

```python
sem = asyncio.Semaphore(max_concurrency)
async def _run(factory):
    async with sem:          # acquired before factory() → materialization still bounded
        return await factory()
results = await asyncio.gather(*(_run(f) for f in factories), return_exceptions=True)
```

Same memory guarantee, no head-of-line blocking. Small, isolated change. This is the cheapest high-impact change.

### B — A real rate limiter at the inference call site, process-global, keyed by provider/account

This is the missing piece. The scarce resource is the *provider account*, shared across every pipe and batch in the process — so the gate must be a single shared object every inference call passes through, regardless of which batch spawned it. It needs two things:

- a **concurrency semaphore** — global ceiling on in-flight API calls; and
- a **token-bucket rate limiter** on RPM (TPM too if tokens can be estimated pre-call, but RPM is the 80%).

Keyed by `(provider, model)` so each provider's limit is independent. `aiolimiter.AsyncLimiter` is the standard asyncio token bucket (tiny, MIT), or hand-roll ~30 lines. This is the change that actually prevents the crash, because it matches what the provider enforces.

### C — Make the protective bound global, not per-controller

Keep `PipeBatch.max_concurrency` as a fan-out *shape* knob if useful, but the protective bound — concurrency and rate — belongs at the single inference call site as a shared resource. Then "1 batch of 1000" and "10 batches of 100" hit the same gate and behave identically.

### Smaller follow-ons

- **Add jitter to `transport_retry`.** `wait_exponential` in `transport_retry.py` is jitter-free; under a 429 storm every retry re-fires in lockstep. `wait_random_exponential` fixes it.
- **Per-item failure policy for large batches.** Fail-fast (current) discards 999 results for one bad document. For batch fan-out, collecting per-item errors and returning partial results is usually preferable — at minimum a `BatchParams` knob.

### Layering summary

| Layer | Responsibility |
| --- | --- |
| `PipeBatch` | Fan-out *shape* — how work is split |
| Process-global inference gate *(new)* | Concurrency semaphore + token-bucket RPM limiter, per provider — the actual backpressure |
| `transport_retry` *(exists)* | Residual 429/5xx — should add full jitter |
| Temporal | Durability — out of scope here |

## How each change co-exists with Temporal

The fact that determines everything: **Temporal slices execution at the activity boundary.**

- **Controllers run as workflow code.** `TemporalPipeRouter` is a drop-in `PipeRouterProtocol`. `PipeBatch._live_run_controller_pipe` — including `gather_bounded` over the branch factories — runs *inside the workflow*. Each branch's `get_pipe_router().run(...)` becomes a **child workflow** (`TemporalPipeRouter` auto-detects "inside a workflow → `execute_child_workflow`").
- **Inference runs as an activity.** The actual LLM/img-gen/extract call is `act_llm_gen_text` & co. — a Temporal **activity**: normal Python, non-determinism allowed, but running in **N separate worker processes**.

That boundary is the whole story:

- Code **above** the activity boundary (controllers, `gather_bounded`) is **workflow code** → must be deterministic: no wall-clock, no `time.sleep`, no real-time `asyncio.sleep`.
- Code **inside** the activity is **normal Python** → wall-clock, sleep, jitter all fine — but per-process, not cluster-wide.

### A — `gather_bounded` semaphore

**Co-exists. Not disabled. Meaning shifts.** `gather_bounded` runs as workflow code in Temporal mode; Temporal does not bypass it.

- In **direct mode** it bounds in-flight coroutines + working-memory deep copies.
- In **Temporal mode** it bounds *how many child workflows the parent starts concurrently*. The deep copy still happens in workflow memory (in `_run_branch`), so the bound is still real — but the heavy inference work has moved into child-workflow activities running elsewhere.

Determinism: `asyncio.Semaphore` involves no wall-clock — acquisition order follows task scheduling, which Temporal replays deterministically. Workflow-safe in principle (the current chunking is too). Worth confirming against Temporal's workflow sandbox, but no red flag. **Fine in both modes** — strictly a better fan-out primitive.

### B — global rate limiter

**This is the change with a real interaction.** Two problems under Temporal:

1. **A token bucket cannot live in workflow code.** It needs wall-clock + sleep, forbidden in workflows. It can only live *inside the activity*.
2. **Inside the activity it is per-worker, not cluster-wide.** With 5 worker processes, each holding its own in-memory bucket of 500 RPM, the aggregate is 2500 RPM against the provider. An in-memory limiter *fundamentally cannot* bound the aggregate across processes.

Temporal's **native** answer to "rate-limit 1000 documents" is better *for that mode*:

- **`max_activities_per_second` on the task queue** — server-enforced, **cluster-wide** across all workers polling that queue. This is the real RPM cap.
- **`max_concurrent_activities` per worker** — the concurrency ceiling.

Change B does not *interfere* (no crash, no determinism issue — it is activity code), but it would be **redundant and only partially effective** under Temporal. The correct design is **mode-aware**:

- **Direct mode:** in-process token bucket + semaphore is the correct and only tool.
- **Temporal mode:** lean on the task-queue RPS limit + `max_concurrent_activities`. Optionally keep the in-process *concurrency* semaphore as a per-worker safety net, but the *rate* cap must be Temporal's, because only the server sees all workers.

Key takeaway: **the rate limiter is not one system that works in both modes.** It is a direct-mode component whose Temporal-mode counterpart is a pair of Temporal config knobs. They should be designed and configured as two faces of the same setting. The mistake to avoid: building B as a single in-memory limiter and assuming it protects under Temporal — it cannot, because it cannot see the other workers.

### Transport-retry jitter

**Co-exists, no conflict.** `transport_retry` runs inside the activity; jitter on its backoff is fine there.

Pre-existing nuance (not worsened by the jitter change): under Temporal there are already *two* retry layers — `tenacity` inside the activity, and Temporal's activity `RetryPolicy` outside it. Jitter just makes the inner layer better-behaved. A later design question is whether, under Temporal, the activity should fail faster and let Temporal's `RetryPolicy` own retries — existing design question, out of scope here.

### Per-item batch failure policy

**Co-exists, runs as workflow code, and is *more* valuable under Temporal.** Each batch branch is a durably-executed child workflow. "First error aborts" would discard durably-completed child workflows for one bad document. Aggregating per-branch `ChildWorkflowError`s instead is deterministic workflow code — fully compatible — and the durability makes discarding that work even more wasteful than in direct mode.

### Summary table

| Change | Runs as | Temporal interaction |
| --- | --- | --- |
| A — `gather_bounded` semaphore | Workflow code | Co-exists; bounds child-workflow starts instead of coroutines. Keep in both modes. |
| B — rate limiter | Activity code | Per-worker only. Cluster-wide rate cap must be Temporal's task-queue RPS. Make it mode-aware. |
| Retry jitter | Activity code | Co-exists; note the pre-existing 2-layer retry stack. |
| Per-item failure | Workflow code | Co-exists; *more* valuable under Temporal. |

Honest framing: **A and the per-item failure policy are mode-agnostic improvements** — build once, help everywhere. **B is genuinely two things** — an in-process limiter for direct mode, and a delegation to Temporal's task-queue knobs for distributed mode.

## Finding: the Temporal half of change B already exists

Inspected `pipelex/temporal/config_temporal.py`. The Temporal-mode rate-limit machinery is already built and configurable — it is a *configuration story*, not a build:

- **`QueueOptions.max_task_queue_activities_per_second`** (`config_temporal.py:273`) — the **cluster-wide** task-queue rate limit. Its own comment: *"Cluster-wide queue rate limit, conveyed to the Temporal server by every worker on this queue."* This is exactly the server-enforced, all-workers RPM cap.
- **`WorkerRuntimeProfile.max_concurrent_activities`** (`config_temporal.py:332`) — per-worker concurrency ceiling.
- **`WorkerRuntimeProfile.max_activities_per_second`** (`config_temporal.py:336`) — per-worker activity rate limit.
- **`ActivityRouteConfig`** (`config_temporal.py:287`) with `by_handle` — routes `llm_handle` / `img_gen_handle` / `extract_handle` to dedicated task queues. This means **per-provider keying already exists on the Temporal side**: give each provider its own queue, set that queue's `max_task_queue_activities_per_second`.

Consequence for the design: **change B is not "build a limiter that works in both modes."** The Temporal side is done — it only needs sane default values and documentation. The actual *build* in change B is purely the **direct-mode** in-process gate. The design should make the direct-mode gate's config mirror the Temporal knobs conceptually (per-provider RPM + concurrency) so operators reason about one model, two enforcement mechanisms.

## Open questions for the design session

- Where exactly is the single inference call site that every provider request funnels through, and is it the same in direct and Temporal modes? That is where the direct-mode gate must sit.
- How is the rate-limit configuration keyed and sourced — per `(provider, model)`, per account? Does it belong in the existing backend TOML configs alongside the provider definitions?
- TPM limiting needs a pre-call token estimate. Is one already available, or is RPM-only acceptable for v1?
- Should `PipeBatch.max_concurrency` survive as a fan-out shape knob, or fold entirely into the global gate?
- Per-item failure policy: default to fail-fast or collect-partial? What does a partial-failure `PipeOutput` / `BatchParams` surface look like?

## Suggested next step

Locate the single inference call site that every provider request funnels through (direct mode and inside the Temporal activities), then design the direct-mode gate (change B) around it: where the shared limiter object lives, how it is keyed by `(provider, model)`, and where its config is sourced — ideally mirroring the existing Temporal knobs so operators reason about one model with two enforcement mechanisms.
