# runtime-bridge — review follow-ups from PR #959

Cold-start entry point for finishing the triage of the SWE-agent review comments on **PR #959** (`feat: extract framework-agnostic Pipelex runtime bridge`, branch `feature/Runtime-bridge-extraction`). The PR extracts `pipelex/runtime_bridge/` — a host-runtime-agnostic surface (`run_pipe_via_bridge`) that lets Mistral Workflows / raw Temporal / future plugins invoke Pipelex pipes from inside their own activities.

Two review bots left 12 unresolved threads: **greptile-apps** and **cubic-dev-ai**. All 12 were verified against the code. They split into three buckets.

## 1. Deferred design forks (this folder)

Each is a **confirmed** finding whose resolution is a genuine design choice, not a mechanical fix. **Do not apply a fix yet** — each doc lays out the fork, pros/cons, and a recommendation for a human to decide. All three are low-urgency: the Temporal integration has not shipped to production, so the Temporal-routing/tracing ones are *latent*.

- **[direct-mode-nested-router-leak.md](direct-mode-nested-router-leak.md)** — (greptile P1, + cubic P2 on the enabler) In `DIRECT` mode, nested controller sub-pipes resolve the *hub default* router and leak to Temporal when a worker has `[temporal] is_enabled`. Fix needs a `scoped_pipe_router` helper (cubic's hub.py:615 comment). Fork is about the `multi_observer` side-effect + whether to fix now.
- **[graph-context-temporal-contract.md](graph-context-temporal-contract.md)** — (greptile P2) `graph_context` is threaded into the `PipeJob` for *all* modes, but the docstring says DIRECT-only and `WfPipeRouter` actually consumes it. Fork: honor the contract (null it for Temporal) vs fix the docstring (keep threading it).
- **[trace-flush-blocking-io.md](trace-flush-blocking-io.md)** — (cubic P2) `flush_trace_events_to_backend` is `async` with blocking boto3/file I/O. Assessed as **false positive / acceptable** (runs in an activity), with an optional throughput-offload note. Documented here so the thread reply has a paper trail.

## 2. Mechanical fixes still pending (no design needed)

These were confirmed during triage but **not yet applied** (the session was redirected to write up the forks first). They're local and unambiguous — just do them, add the two small regression tests, then reply/resolve their threads:

- **Boot race** — `pipelex/runtime_bridge/bootstrap.py:24` (greptile P1 + cubic P2). `ensure_pipelex_booted` does check-then-`Pipelex.make()` with no lock; two concurrent first-calls in a fresh worker → one wins, the other hits `PipelexSetupError("Pipelex is already initialized")`. `MetaSingleton` has no lock either. Fix: double-checked locking with a module-level `threading.Lock` (re-check inside the lock). Test: threaded barrier forcing two concurrent first-calls; assert no raise + singleton made once. *(Note: race is only across threads — the function is a sync `def` with no `await` between check and make, so asyncio tasks on one loop can't interleave there; it bites Temporal's sync-activity thread-pool / multi-thread workers.)*
- **Exceptions caller-facing flag** — `pipelex/runtime_bridge/exceptions.py:8,12` (cubic P2). `MissingPipelexTemporalExtraError` and `MissingMistralWorkflowsPluginError` carry pip-install hints but don't set `_authors_caller_facing_message: ClassVar[bool] = True`; under STRICT disclosure their message is replaced by `INTERNAL_ERROR_PLACEHOLDER`, hiding the hint. Siblings like `PipelexInterpreterError` set it. Fix: add the flag to both. Test: assert STRICT disclosure keeps the message.
- **streaming.mdx missing import** — `.claude/skills/workflows/references/guides/streaming.mdx:99` (cubic P1). Example uses `asyncio.sleep(0.1)` but never imports `asyncio`. Fix: add `import asyncio` to the example's import block.
- **observability.mdx frontmatter id** — `.claude/skills/workflows/references/guides/observability.mdx:2` (cubic P2). `id: observabilities` breaks every link targeting `observability` (SKILL.md, value-proposition.mdx, _deployment-patterns.mdx, …). Fix: `id: observability`.
- **your-first-workflow.mdx grammar** — `.../getting-started/your-first-workflow.mdx:~50-53` (cubic P3). "It coordinate multiple activities" → "It coordinates".
- **your-first-workflow.mdx broken image** — same file, `:~83` (cubic P3). `![expected_workflow_output](expected_workflow_output.png)` — PNG does not exist in the repo. Fix: remove the broken image, keep the instruction text.
- **durable-execution.md overgeneralization** — `docs/reliability/durable-execution.md:21` (cubic P2). "flip `[temporal] is_enabled = true` and the work dispatches through Temporal" conflates the two backends — that flag is the *Pipelex Temporal* backend only, not the *Mistral Workflows* path. Apply cubic's suggested rewrite distinguishing the two (Mistral path is configured through the runtime bridge in a worker activity).

## 3. False positive

Folded into [trace-flush-blocking-io.md](trace-flush-blocking-io.md) (the #8 thread). No code change.

## How to resume

1. Read the three fork docs, get a human decision on each.
2. Apply the mechanical fixes in §2 (+ the two regression tests).
3. Apply whatever was decided for the forks.
4. `make agent-check` + `make agent-test`.
5. Per the `/review-pr-agents` skill: reply on each PR thread (`✅ Fixed` / `➖ False positive` / `⏭️ Deferred`) and resolve the addressed ones; leave deferred forks' threads open until decided.
