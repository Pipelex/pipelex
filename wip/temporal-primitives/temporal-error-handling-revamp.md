# Temporal exception model — revamp proposal (deferred)

## Problem statement

Pipelex exposes workflow execution failures as `pipelex.temporal.exceptions.WorkflowExecutionError`, which extends `PipelexError(Exception)`. The `WorkflowExecutor` wrapper in `pipelex/temporal/tprl/workflow_caller.py` raises this from inside workflows when a child workflow fails (catches `ChildWorkflowError` → re-raises `WorkflowExecutionError(msg) from exc.cause`).

But Temporal's Python SDK has a strict rule: only exceptions that subclass `temporalio.exceptions.FailureError` are treated as **workflow execution failures** (terminal, propagated to client as `WorkflowFailureError`). Anything else is treated as a **workflow task failure** (programmer bug — workflow task is retried indefinitely, the workflow never completes).

`WorkflowExecutionError` doesn't subclass `FailureError`. So any workflow that catches it and re-raises it (the pattern in `wf_pipe_run.py` after the Phase 5 follow-up) would hang forever — except we worked around it by registering `WorkflowExecutionError` in the Worker's `workflow_failure_exception_types` list (commit `117bbe01`).

## What this revamp would do

Make `WorkflowExecutionError` (and likely other workflow-layer exceptions in `pipelex/temporal/exceptions.py`) inherit from `temporalio.exceptions.ApplicationError` (which is a `FailureError`). Then:

- `raise WorkflowExecutionError(msg)` inside a workflow → Temporal recognizes it natively → workflow ends terminally → client sees `WorkflowFailureError`. No Worker-side registration needed.
- The `workflow_failure_exception_types=[WorkflowExecutionError]` block in `pipelex/temporal/temporal_task_manager.py:make_worker` becomes redundant and can be removed.
- The "invisible discipline" of having to register every new domain exception type with the Worker goes away — the type system enforces the contract.

## Why we didn't do it during the pre-Phase-6 cleanup

- It expanded scope beyond the planned cleanup.
- `ApplicationError` has a different `__init__` signature than `PipelexError`. `ApplicationError(message, *details, type=None, non_retryable=False, ...)` vs. `PipelexError(message)`. Compatibility requires either:
    - Overriding `__init__` on `WorkflowExecutionError` to call both parent constructors compatibly, or
    - Accepting that callers must pass `(message,)` only and pinning that contract.
- It mixes Pipelex's exception hierarchy with temporalio's. The other `TemporalFlowError` subclasses (`WorkflowInputError`, `TemporalConfigError`, `TemporalServerError`, etc.) probably should NOT inherit from `ApplicationError` — only the ones that might be raised from inside a workflow. Drawing that line cleanly is the actual design work.
- The Worker-side registration was good enough to ship; this is the cleaner-but-not-strictly-necessary final form.

## Scope of the revamp

Likely changes:

- `pipelex/temporal/exceptions.py` — rework the hierarchy. At minimum `WorkflowExecutionError` inherits from `ApplicationError`. Possibly `ContentGenerationError` too if it's ever raised from inside a workflow.
- `pipelex/temporal/temporal_task_manager.py:make_worker` — drop the `workflow_failure_exception_types=[WorkflowExecutionError]` kwarg (no longer needed).
- `tests/integration/pipelex/temporal/test_wf_pipe_run_failure_path.py` — drop the matching kwarg on the test Worker. The test should still pass.
- Audit any other Worker constructions outside `make_worker` (none today, but possible in future tests / scripts) — they no longer need the registration.
- `pipelex/temporal/tprl/workflow_caller.py` — verify the `raise WorkflowExecutionError(msg) from exc` and `raise WorkflowExecutionError(msg) from exc.cause` patterns still work with the new `__init__` signature.

Likely **not** changed:

- The non-workflow-layer exceptions in `pipelex/base_exceptions.py` — those have nothing to do with Temporal.
- The catch sites — they still catch `WorkflowExecutionError`, and that name doesn't change.

## Open questions for the revamp

- Should `TemporalFlowError` itself inherit from `ApplicationError`, or only `WorkflowExecutionError`? The former is bolder (any "Temporal flow error" gets Temporal-native handling) but pulls in any subclass we add later. The latter is surgical.
- `ApplicationError` has a `non_retryable` field. Should `WorkflowExecutionError` set it on construction (e.g. always non-retryable since the parent workflow's retry policy is what controls retry semantics)? Or leave it to callers? Pre-Phase-5 behavior was effectively retryable-by-default (since `ChildWorkflowError.cause` was usually retryable `ApplicationError`).
- Should `ApplicationError.type` be set to a fixed string (e.g. `"WorkflowExecutionError"`) for filtering on the Temporal dashboard? Currently the Rust core logs already show `r#type: "WorkflowExecutionError"` — confirm whether that's auto-derived from the class name or needs explicit setting.
- What happens to error attribution if `WorkflowExecutionError` inherits from `ApplicationError` and gets re-raised across multiple workflow layers? `ApplicationError` chains via `cause` (a Temporal-specific cause chain), not Python's `__cause__`. Need to verify the chain stays intelligible.

## Trigger to do this

- A second-time encounter of the "I forgot to add my new exception to `workflow_failure_exception_types`" footgun (any test that hangs forever with the same root cause).
- A new domain exception type that needs to behave the same way as `WorkflowExecutionError`.
- A Phase 7+ effort to clean up the Temporal layer's error model holistically.
- About 1-2 hours of focused work, plus reviewer time.

## Related work

- Phase 5 follow-up commit `117bbe01` — "Pre-Phase-6 cleanup: tighten exception handling + WfPipeRun failure-path test" — added the `workflow_failure_exception_types` workaround.
- `pipelex/temporal/tprl/workflow_caller.py` — the four `WorkflowExecutor` entry points and their named-exception catches.
- `pipelex/temporal/exceptions.py` — the current `TemporalFlowError` hierarchy.
- `tests/integration/pipelex/temporal/test_wf_pipe_run_failure_path.py` — the test that surfaced this issue.
