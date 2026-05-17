# TODO — Drop failed-attempt graph nodes when the PipeRouter retries

> **Status:** RESOLVED BY REMOVAL. The phantom-error-node bug existed only because the `PipeRouter` retry loop reran a failed pipe within a single `run()`. That loop has been removed (Workstream 1 of the retry-and-resilience plan — see [track-retry-and-resilience.md](track-retry-and-resilience.md)): direct execution is now a single pipeline-level attempt, so a pipe runs at most once per `run()` and there is no duplicate error/success node to discard. The rest of this doc is kept only as a record of the original gap.
> **Source:** Follow-up to the `PipeRouter` transient-retry loop — see [track-retry-and-resilience.md](track-retry-and-resilience.md). Raised as a review comment on PR #903.

---

## The gap (one paragraph)

The `PipeRouter` transient-retry loop (`PipeRouterProtocol.run()` in `pipelex/pipe_run/pipe_router_protocol.py`) retries a transient inference failure by rerunning `_run_pipe_job()`, which reruns `pipe.run_pipe()`. But `PipeAbstract.run_pipe()` has *already* called `tracer_manager.on_pipe_end_error(...)` for the failed attempt before the exception reached the router (the `except` branch in `pipe_abstract.py`). So when a transient failure succeeds on a later attempt, the graph still carries the failed attempt's error node — plus a fresh success node for the same pipe. A successful run looks partially failed to graph output and trace consumers.

This is observability-only — the run itself completes correctly. It is separable from the retry-bypass fix that PR #903 delivers, hence deferred.

## Pointers

- **Retry loop:** `pipelex/pipe_run/pipe_router_protocol.py` — `run()`, the `while True` loop and its `except (CogtError, PipeRunError)` branch (~line 62-95). On a retryable error within budget it `continue`s the loop.
- **Where the error node is recorded:** `pipelex/core/pipes/pipe_abstract.py` — `run_pipe()` `except` branch calls `tracer_manager.on_pipe_end_error(...)`.
- **Graph tracer surface:** `pipelex/graph/graph_tracer.py`, `graph_tracer_manager.py`, `graph_tracer_protocol.py` — no supersede/discard/retry mechanism exists today.

## Shape of the change (to be designed)

The graph tracer needs a way to discard (or mark as superseded/retried) a node when its pipe is about to be retried, so a successful retried run shows a single clean node.

**Open design question — settle this first:** the router does not hold the graph `node_id` (it is created and kept inside `run_pipe()`). Two candidate approaches:

1. The router signals "retrying" to the tracer, and the tracer keys the discard off pipe identity / the current graph context.
2. `run_pipe()` itself detects a retryable failure and defers/withholds the error node until the failure is final — pushing the retry-awareness one layer down.

List both in the plan, weigh them, recommend one.

## How to expand (do this in the new session)

1. Read the retry-loop code and `run_pipe()`'s tracing branches in full; confirm the duplicate-node behavior with a trace from a forced transient-then-success run.
2. Decide the design question above and record the decision.
3. Write the plan as RED → GREEN → REFACTOR. RED = a test that forces a transient failure then success and asserts the resulting graph has exactly one node for the pipe, with no error event. Confirm it fails today.
4. Run `make agent-check` after each step, `make agent-test` before wrapping up.

## Out of scope

- The retry loop itself — landed in PR #903.
- The Temporal-side retry path — its activity-boundary wiring landed; see Followup 5 in [track-temporal-integration.md](track-temporal-integration.md).
