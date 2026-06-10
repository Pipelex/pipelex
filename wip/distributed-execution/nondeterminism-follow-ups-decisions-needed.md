# Nondeterminism follow-ups — decisions needed

Items from [nondeterminism-fix-review-follow-ups.md](nondeterminism-fix-review-follow-ups.md) that are real but a judgment call: design tradeoffs with several defensible shapes, surfaced here for discussion instead of being fixed unilaterally. Everything fixable in that doc has been fixed (statuses recorded there).

## 1. Graph events have no equivalent of the H1 usage-path guard (follow-ups item 7)

H1's fix enforces "only workflow-thread emissions land in the workflow buffer" for **usage** events only: `ReportingManager._emit_usage_event` checks `_is_in_temporal_activity()` before any context lookup, so an in-activity emission can never write into the workflow's replay-rebuilt `BufferingEventLog`.

The **graph** path has no such guard. `GraphTracerManager` is imported in `wf_pipe_router.py` under `workflow.unsafe.imports_passed_through()`, so the singleton IS shared across the sandbox boundary on co-located workers, and the workflow's tracer key rides into activity args via `job_metadata.trace_context`. No current activity-side code calls tracer hooks, so the hazard is latent — but the first activity that does (bridge instrumentation, future activity-side tracing) would mutate the workflow's tracer from outside the workflow thread, corrupting replay-rebuilt graph data. Post-H1/H2 this corrupts **data payloads** (the assembled GraphSpec), not the command stream, so it is silent data corruption rather than a [TMPRL1100] failure — harder to notice, not easier.

### Options

- **A. Structural fix (T3 direction):** request-scoped tracing state instead of the process-singleton `GraphTracerManager` — already tracked as Issue T3 in [tracing-cost-reporting.md](tracing-cost-reporting.md). Solves the class, not just this instance. Largest change; touches every tracer lookup site.
- **B. H1-style guard on the tracer hooks:** make the tracer-hook entry points check `_is_in_temporal_activity()` and refuse (or no-op + WARNING) in-activity calls against a workflow-keyed tracer. Small, targeted, mirrors the proven usage-path mechanism — but adds temporal-awareness to `pipelex/graph/`, which is otherwise temporal-free.
- **C. Contract note only:** an explicit "activities must never call tracer hooks" note on `GraphTracerManager`. Zero code risk, but nothing enforces it — exactly the kind of cross-file invariant that rots.

### Recommendation

B as the cheap interim guard if any activity-side tracing work is planned before T3 lands; otherwise C now and fold the real fix into T3. A is the right end state either way — this item should ride along with T3 rather than spawn a separate effort.

> Status: no action taken in the fix/Config burn-down (carried here from the follow-ups doc, which marked it "no action yet"). Decide when T3 is scheduled.
