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

---

The items below were surfaced by the pre-landing review army on PR #987 (gstack `/review`: specialists + adversarial passes). Same rule as above: real, but judgment calls — deferred rather than fixed unilaterally. The review's clear wins (full-teardown forget-even-on-raise hardening with every sibling teardown still attempted, stale-key healing unit tests, best-effort containment of the stale tracer's teardown inside the healing branch, conftest cache-reset hoist, doc/changelog corrections, finally-block key symmetry + discarded-buffer tripwire) were applied directly on the branch and are NOT listed here.

## 2. Tracing-disabled workers silently drop submitter-requested trace/cost events

The worker-local `tracing_config.is_enabled` check deliberately lives activity-side (deterministic-safe), but both drop sites are silent: `flush_trace_events_to_backend` bare-returns on a NON-empty event list when tracing is disabled, and `_emit_usage_event_runner_fallback` bare-returns before building the event log — post-H1 the path for every LIVE usage emission. A submitter that requested tracing (payload carries `trace_context` with emit flags) against a tracing-disabled worker fleet gets a green workflow and an empty event stream: costs undercounted, no operator signal. This is intentional for deliberately-disabled fleets, which is exactly why a warning is a judgment call — it would fire once per flush/process on every such deployment.

**Options:** (a) one-shot-per-process WARNING at each drop site when the payload requested emission; (b) a config-drift metric/health signal instead of logs; (c) keep silent (current), treat disabled-worker fleets as fully intentional. Leans (a) — cheap and aligned with "a run's terminal reporting must not silently vanish" — but decide alongside the broader config-drift observability story.

## 3. Non-`PipelexError` raised in the now-unguarded tracing-setup block retries forever

The catch-all around tracing setup was removed on purpose (M1: worker-local state must not decide setup success; failures must surface). But the workflow's inline fail-safe floor catches `PipelexError` only — a non-PipelexError from the setup block (e.g. a pydantic `ValidationError` from the `model_copy` calls after a refactor) escapes both except clauses, fails the workflow task, and Temporal retries it forever: the silent-hang failure mode this whole series eliminates, reintroduced for one error class. Being inline-deterministic it re-fires identically on every retry. **Option:** widen the inline fail-safe floor (or wrap just the setup block) to convert any inline exception deterministically into a terminal `TemporalError`. This is one instance of the already-open "should deterministic converter/workflow-task errors be fail-fast instead of retry-forever" question (see the dry-validate hardening follow-up) — decide them together.

## 4. Residual worker-local-state risks under run-id keying (follow-ups item 0 residuals)

Two accepted-but-undocumented residuals of the run-id rekeying, plus one perf note, recorded so they're findable when symptoms appear:

- **Permanent leak on finally-skipping paths:** run ids are unique, so state leaked by a path that skips the `finally` entirely (e.g. deadlock-detector thread abandonment) is never reclaimed by the overwrite/self-heal idioms that workflow-id reuse used to trigger. Unbounded growth of `LibraryManager._libraries` / tracers / event-log contexts over a long-lived worker's life, on rare paths. Mitigation candidates: TTL sweep, size-bounded eviction, worker-eviction callbacks.
- **Zombie abandoned thread vs the same run's replay:** if an abandoned (deadlock-detector) thread later unblocks, its `finally` tears down `wf_{run_id}` state while a retried replay of the SAME run (same run id) is live on the same worker — the replay then fails inline with a `LibraryError`, which the fail-safe floor converts to a terminal failure. Low probability (abandonment + later resume + timing window); structural fix would be epoch/ownership tokens on the per-run entries.
- **Blocking backend write per usage emission on the activity event loop** (`_emit_best_effort` → e.g. boto3 `put_item`): pre-existing on the split path, now universal post-H1. Dwarfed by inference latency today; offload to a thread or batch if emission frequency grows.

## 5. `LibraryManager._pipe_source_map` is a shared keyspace across concurrent libraries (pre-existing)

`load_from_crate` writes `_pipe_source_map[pipe_ref] = source` keyed by bare `pipe_ref`, and teardown pops the dying library's refs — semantics unchanged by this branch (verified against the pre-branch code) but newly load-bearing now that per-run libraries are the norm: two concurrent runs loading the same crate share keys, so run A's teardown deletes source attribution run B still needs, and loads are last-writer-wins. Blast radius is error-traceability diagnostics (`get_pipe_source`), not execution. **Fix shape:** scope the map per `library_id` (nested dict or move it onto `Library`) — touches `get_pipe_source` callers, so it didn't belong in this PR.

## 6. `_is_in_temporal_activity()` is a process-global signal, not a pipelex-run boundary (contract note)

Two latent edges of the H1 routing check: (a) a host app running a DIRECT pipelex pipeline inside its **own** temporalio activity (legit runtime-bridge embedding) gets its registered direct-mode context bypassed — emissions divert to the per-process fallback with a restamped `workflow_id`, ignoring a custom event-log backend; (b) an emission from a thread spawned inside an activity without contextvar propagation (the `run_in_executor(None, ...)` pattern that exists in `bedrock_client_boto3.py`) would report `in_activity()=False` and resurrect the H1 cross-thread buffer write. All current `report_inference_job` call sites run in the activity's own context, so both are latent — same class as item 1; fold into the same T3-adjacent decision.

