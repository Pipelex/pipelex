# Rate limiting the inference layer — design notes

Status: **design scoping**, not yet a plan. Split out of [`README.md`](README.md) because it is the complex, mode-dependent part. Read the README's "direct mode vs Temporal mode" section first — this doc assumes that frame.

## Why this is its own doc

The quick wins in the README (semaphore fan-out, retry jitter, per-item failure policy) are small, isolated, and mostly mode-agnostic. Rate limiting is none of those things:

- it is the change that actually prevents the crash at scale;
- it is genuinely **two different mechanisms** in the two execution modes;
- one of those mechanisms **already exists** and the other has to be built.

## The problem: concurrency ≠ rate

The current system has only one knob — `PipeBatch.max_concurrency` — and it bounds *concurrency*. Providers do not rate-limit on concurrency. They enforce **requests-per-minute (RPM)** and **tokens-per-minute (TPM)**.

Concurrency 8, with calls finishing in ~200ms, is ~40 RPS ≈ 2400 RPM — enough to blow a 500-RPM tier instantly. Concurrency caps cannot express "no more than 500 requests per minute"; only a rate limiter can.

Two further gaps:

- **The bound is per-`PipeBatch`, not global.** Nested or sibling batches multiply the real in-flight count. The protective bound must be a single shared gate, not a per-controller setting.
- **The scarce resource is the provider account.** The gate must be keyed by `(provider, model)` — or per account — because that is what the provider's limit applies to, shared across every pipe and batch.

## Direct vs Temporal: two mechanisms, not one

This is the crux. A rate limiter is wall-clock-based (token bucket, `asyncio.sleep`). That dictates where it can live.

| | Direct mode | Temporal mode |
| --- | --- | --- |
| Where the inference call runs | In-process async call | Inside an activity, one of N worker processes |
| Can a wall-clock token bucket live there? | Yes — normal async code | Yes inside the *activity* (not workflow code) — but only sees its own process |
| What a single in-process limiter achieves | A correct, global cap | Only a **per-worker** cap — N workers × limit = N× the intended rate |
| Correct mechanism | In-process token bucket + concurrency semaphore | Temporal **task-queue** rate limit (server-enforced, cluster-wide) + per-worker knobs |

The trap to avoid: building one in-memory limiter and assuming it protects both modes. Under Temporal it cannot — an in-memory bucket is blind to the other worker processes, so five workers each holding a 500-RPM bucket hammer the provider at 2500 RPM.

## Finding: the Temporal-mode machinery already exists

Inspected `pipelex/temporal/config_temporal.py`. The Temporal-side rate-limit knobs are already built and configurable — Temomral mode is a *configuration* story, not a build:

- **`QueueOptions.max_task_queue_activities_per_second`** (`config_temporal.py:273`) — the **cluster-wide** task-queue rate limit. Its own comment: *"Cluster-wide queue rate limit, conveyed to the Temporal server by every worker on this queue."* Server-enforced across all workers — exactly the RPM cap.
- **`WorkerRuntimeProfile.max_concurrent_activities`** (`config_temporal.py:332`) — per-worker concurrency ceiling.
- **`WorkerRuntimeProfile.max_activities_per_second`** (`config_temporal.py:336`) — per-worker activity rate limit.
- **`ActivityRouteConfig`** (`config_temporal.py:287`) with `by_handle` — routes `llm_handle` / `img_gen_handle` / `extract_handle` to dedicated task queues. So **per-provider keying already exists on the Temporal side**: give each provider its own queue, set that queue's `max_task_queue_activities_per_second`.

Consequence: the Temporal half needs only sane default values and documentation, not new code. **The actual build is purely the direct-mode gate.**

## Proposed: the direct-mode inference gate

A single process-global gate, sitting at the inference call site, that every provider request funnels through regardless of which `PipeBatch` spawned it. Keyed by `(provider, model)`. Two components:

- a **concurrency semaphore** — global ceiling on in-flight API calls;
- a **token-bucket rate limiter** on RPM (TPM too, if a pre-call token estimate is available; RPM is the 80%).

Implementation options: `aiolimiter.AsyncLimiter` is the standard asyncio token bucket (tiny, MIT), or hand-roll ~30 lines.

`PipeBatch.max_concurrency` can stay as a fan-out *shape* knob, but it stops being the protective bound — the gate is. Then "1 batch of 1000" and "10 batches of 100" hit the same gate and behave identically.

**Design principle: one mental model, two enforcement mechanisms.** The direct-mode gate's config should mirror the Temporal knobs conceptually — per-provider RPM + concurrency — so an operator configures one thing and it is enforced in-process in direct mode and by the Temporal server in Temporal mode. Ideally the config is sourced once (e.g. alongside the provider/backend definitions) and consumed by both paths.

## Open questions for the design session

- Where exactly is the single inference call site that every provider request funnels through? Is it the same code in direct mode and inside the Temporal activities? That is where the direct-mode gate must sit.
- How is the rate-limit config keyed and sourced — per `(provider, model)`, per account? Does it belong in the existing backend TOML configs alongside the provider definitions, so both the direct gate and the Temporal queue config can read one source?
- TPM limiting needs a pre-call token estimate. Is one already available, or is RPM-only acceptable for v1?
- Add `aiolimiter` as a dependency, or hand-roll the token bucket?
- Does `PipeBatch.max_concurrency` survive as a fan-out shape knob, or fold entirely into the global gate?
- How does the gate interact with `transport_retry`? A 429 that slips through should feed back into the limiter (back off the bucket), not just retry blindly.

## Suggested next step

Locate the single inference call site that every provider request funnels through (the same one the Temporal activities wrap), then design the gate around it: where the shared limiter object lives, how it is keyed, and where its config is sourced so direct mode and Temporal mode read one model.
