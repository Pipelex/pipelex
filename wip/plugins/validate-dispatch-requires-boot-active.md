# Deferred: dispatched `/validate` effectively requires `boot_orchestrator == "temporal"`

**Status:** observation surfaced during Phase V1 of `orchestrator-dispatched-validate.md`. Not a bug introduced by this work — a pre-existing property of the reused dispatch machinery. Deferred, not fixed.

## What the plan says

The plan's "Per-call, presence-based, NOT boot-gated" decision (and its resolution of old open question #5) states:

> `dispatch_dry_validate` needs only a reachable Temporal client + a worker with the validate workflow registered — **not** a runner booted-as-Temporal.

## What the code actually does

`TemporalBundleValidator.validate_bundles` reuses `dispatch_dry_validate` as-is. That calls `WorkflowExecutorFactory().create_executor(...).execute_workflow(...)`, and `WorkflowExecutor.temporal_client()` (`pipelex_temporal/tprl/workflow_caller.py`) opens with:

```python
if not is_temporal_boot_active():
    raise AsyncExecutionNotEnabledError.with_default_message()
```

`is_temporal_boot_active()` is `config.plugins.boot_orchestrator == "temporal"`. So the executor refuses to connect unless **this process booted under Temporal** — i.e. dispatched `/validate` does in practice require `boot_orchestrator == "temporal"`, contrary to the plan's decision #5.

## Why this is consistent (and why it's only an observation)

The **registration** is correctly presence-based / unconditional — the validator is contributed under both temporal modes regardless of `boot_orchestrator`, exactly like the Temporal run orchestrators. The runtime boot-active requirement is **identical** for the run orchestrators: `TemporalBlockingOrchestrator.run` → `make_temporal_pipe_run().run` → the same `WorkflowExecutor.temporal_client()` boot-active guard. So validate dispatch is no more boot-coupled than pipe-run dispatch already is; the validator faithfully mirrors the established orchestrator behavior.

The plan's decision #5 was about **the seam not being boot-*gated* at registration** (true — no hub slot is claimed, no `boot_orchestrator` branch in `register`). The phrase "not a runner booted-as-Temporal" overreaches for the *runtime* connect path, which the reused `dispatch_dry_validate`/executor enforces.

## Why not fix it here

Relaxing the `is_temporal_boot_active()` guard so a non-Temporal-booted runner can still open a Temporal client for dispatch is a change to the **shared executor** that governs *all* Temporal dispatch (run + validate), not validate alone. It is out of scope for this feature, would broaden blast radius well beyond `/validate`, and is only meaningful once the hosted runner's boot story (does the agnostic runner boot as temporal, or dispatch per-request without booting?) is settled in the parent effort's Phase D. Until then this is a no-op for correctness: a Temporal-flavor runner boots as Temporal anyway.

## If revisited

Decide the hosted runner's boot model first (Phase D). If a single agnostic runner must dispatch *some* requests to Temporal without booting as Temporal, the fix belongs in `WorkflowExecutor.temporal_client()` (gate on client reachability, not `boot_orchestrator`) and must be validated against the run-dispatch path too — then update the plan's decision #5 wording to match.
