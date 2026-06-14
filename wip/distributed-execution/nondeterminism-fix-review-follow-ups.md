# Nondeterminism fixes (H1/M1/H2) — review follow-ups

> **BURN-DOWN COMPLETE.** Every item below reached a terminal state — see the **Status** line under each heading. Summary: 0/0bis/1/2/3/4/5/6/8/9/10/11 FIXED (with one sub-point of 3 dismissed); 7 SURFACED to [nondeterminism-follow-ups-decisions-needed.md](nondeterminism-follow-ups-decisions-needed.md).

Source: code reviews of branch `fix/Config`. Round 1 reviewed the committed H1/M1 fixes (flush activity and tracing setup made pure functions of payload + history); its H2-related findings were handled by the H2 fix session. Round 2 (below, at the end) reviewed the H2 fix itself — its top finding is the priority item in this doc.

Companion diagnosis: [workflow-nondeterminism-audit.md](workflow-nondeterminism-audit.md).

## PRIORITY — from the H2-fix review (round 2)

### 0. Key per-run worker-local state by `run_id`, not `workflow_id` — `wf_pipe_router.py`

**This is a correctness hazard, not a cleanup.** The per-workflow library (`wf_{workflow_id}`), the tracer key, and the report-delegate event-log context are all keyed by `workflow.info().workflow_id`. The H2 fix guarantees an evicted predecessor instance's `finally` now runs its synchronous cleanup (verified against temporalio source: eviction resumes the coroutine, the `finally` executes, and the new flush command raises `_WorkflowBeingEvictedError` at the await). That reliable cleanup is destructive cross-run: workflow id X run A is cached on worker W; A is closed server-side (workflow-level `retry_policy` in `workflow_caller.py` reuses the id — as do Temporal reset and resubmission of the same `pipeline_run_id` via the deterministic `make_workflow_id`); successor run B starts on W and `open_fresh_library` opens fresh `wf_X`; the worker later processes A's eviction, and A's `finally` tears down B's LIVE library, pops B's tracer, and clears B's event-log context. B then fails inline (registry fallback / `LibraryError` from its own teardown → workflow-task retry loop). Pre-fix only the tracer pop was reachable at eviction; the reorder widened the blast radius to the library and usage-event context. The root defect (workflow_id-keyed worker-local state) predates the H2 fix.

Fix: key the per-run worker-local state by `workflow.info().run_id` (replay-stable, unique per run, new on retry/reset/continue-as-new) — e.g. `wf_{run_id}` for the library id and run-scoped tracer/event-log context keys. `open_fresh_library` stays as the same-run self-heal (eviction leak of run A heals when run A itself replays), and cross-run collisions become structurally impossible. Also make `open_fresh_library`'s check-then-teardown tolerant of concurrent teardown (the membership check and the teardown are not atomic across workflow threads). The existing eviction-leak test covers the leak-then-rerun direction only; add the late-eviction-destroys-successor direction if feasible.

**Status: FIXED.** All per-run worker-local state in `wf_pipe_router.py` is keyed by `wf_run_id = workflow.info().run_id` (library `wf_{run_id}`, tracer key, event-log context key), and the run-scoped identity is also what gets stamped into events/node ids (the runner fallback already stamped `tracer_key`, so stamps and keys stay one identity). `open_fresh_library` is now pop-based (`LibraryManager._pop_and_teardown_library`): the membership check IS the atomic pop, so concurrent teardown resolves to a clean miss. Tests: new `test_wf_pipe_router_run_scoped_state_keying.py` (parks the workflow mid-activity and asserts library/tracer/context exist under run-id keys and NOT under workflow-id keys — RED against the old keying); the eviction-leak test converted to start-then-install so the leaked state sits under the actual `wf_{run_id}`. The destroys-successor direction is pinned structurally by the keying test (no workflow-id-keyed state exists to destroy).

### 0bis. Pin the finally-ordering invariant with a cancellation test

The ordering half of the H2 fix ("no await before worker-local cleanup in the `finally`") is enforced only by comments; the regression test pins the `open_fresh_library` self-heal, not the ordering. Deterministic guard shape (verified constructible with existing infra): `substitute_activities` with a flush stub blocked on an `asyncio.Event` (pattern already in `test_wf_pipe_router_tracing_config_nondeterminism.py`), start the workflow, `handle.cancel()` while it sits at the flush await (`CancelledError` is the same BaseException-at-suspension-point shape as eviction), then assert the `LibraryManager` holds no per-run library and the report-delegate context is clear. Land this before or with item 5 below, which plans to edit the flush schedule.

**Status: FIXED (test landed), with one premise corrected empirically.** Cancellation is NOT the same shape as eviction: workflow cancellation delivered at an activity await is surfaced by the SDK as an `ActivityError` (an `Exception`), which the best-effort `except` around the flush swallows — the workflow then completes normally, so cancellation cannot abort the `finally` (good news: it cannot leak either). The guard test instead forces a real eviction: park the workflow at the blocked flush, shut the worker down (shutdown evicts every cached run, resuming the coroutine with the eviction `BaseException` at the await), then assert library/tracer/context are all clean. Verified RED against a deliberately reordered `finally` (cleanup moved after the await). Test: `test_wf_pipe_router_eviction_cleanup_ordering.py`. The router's `finally` comment was updated to drop the incorrect cancellation claim.

## Do anytime (independent of H2)

### 1. Fix the stale runner-fallback warning — `pipelex/tracing/activity_event_log.py`

`warn_once_runner_fallback_engaged` (~line 93) still says the fallback engages "because no `_event_log_contexts` entry was registered in this process" and "is expected when activities run on a separate worker pool from the workflow router". After the H1 fix, the runner fallback is the **universal** path for all activity-side usage emissions (`reporting_manager.py` routes every in-activity emission there, co-located or not), so this WARNING now fires once per worker process on every standard co-located deployment with a false explanation, and it no longer signals anything anomalous about split deployments.

Fix: rewrite the message to describe the actual post-H1 contract (activity emissions always use the per-process runner log, by design, for replay determinism), and consider downgrading to DEBUG/INFO since it is now the normal path — or keep a WARNING only for the genuinely anomalous case if one still exists.

**Status: FIXED.** Renamed to `log_once_runner_fallback_engaged`, downgraded to INFO, message now states the post-H1 contract (activities always emit through the per-process log, by design, co-located or split alike). No anomalous case remains distinguishable at that call site, so no WARNING arm. Module docstring of `activity_event_log.py` rewritten to match; the two unit tests updated to assert the INFO once-flag.

### 2. Remove the dead `_event_log_contexts.clear()` dance — `tests/integration/pipelex/temporal/tracing/helpers.py`

`_runner_isolated_act_llm_gen_text` (~line 220) clears `ReportingManager._event_log_contexts` (with `SLF001`/`reportPrivateUsage` suppressions) to force the fallback path, and its docstring explains that mechanism. Post-fix, `_emit_usage_event` checks `_is_in_temporal_activity()` **before** the contexts lookup, so the clear no longer changes which path is taken — it is dead code with a stale docstring, and the private-state mutation can interfere with other contexts registered in the same process.

Fix: delete the clear + the isinstance scaffolding, rewrite the docstring to say the fallback is now taken unconditionally in activities. This also collapses the helper toward the duplicated stub in item 3.

**Status: FIXED.** Clear + isinstance scaffolding deleted, docstring rewritten (helper renamed `_synthetic_usage_act_llm_gen_text`). The same dead clear existed in `test_split_worker_real_inference_cost.py::_real_runner_act_llm_gen_text` — removed there too, with its docstring and the module docstring corrected.

### 3. Deduplicate the new test scaffolding into shared helpers

The two new regression tests (`test_wf_pipe_router_costs_only_flush_nondeterminism.py`, `test_wf_pipe_router_tracing_config_nondeterminism.py`) plus the eviction test carry copy-pasted blocks, all verified line-for-line:

- the synthetic `LLMTokensUsage`/`LLMJob`/`report_inference_job` construction duplicates `_runner_isolated_act_llm_gen_text` in `tracing/helpers.py` (only the constant strings differ, and after item 2 the bodies become identical modulo constants) → extract a `make_synthetic_usage_llm_job(...)` builder;
- an identical `_act_flush_noop` `@activity.defn(name="act_flush_trace_events")` stub in both new files → move one copy into `tracing/helpers.py`;
- an identical scheduled-activity-names proto scan over fetched history in both new files (a near-variant also pre-exists in `tracing/test_split_worker_extract_pages.py`) → a `scheduled_activity_names(history)` helper;
- the eviction test's Greeting-stuff/`prepare_for_temporal` setup duplicates `library_crate/test_wf_deferred_hydration.py` down to the same payload → a shared builder in `library_crate` helpers.

Also: the new files re-implement the enable/restore-tracing fixture from `tracing/conftest.py` because they sit one directory up — hoisting a parametrizable fixture (or moving the tests under `tracing/`) removes that copy too.

**Status: FIXED**, except two sub-points dismissed on re-verification:

- Extracted `make_synthetic_usage_llm_job(...)`, a shared `act_flush_noop` stub, and `scheduled_activity_names(history)` into `tracing/helpers.py`; all router-level guard tests now consume them. Extracted `make_prepared_greeting_job(...)` into `library_crate/helpers.py`, consumed by both the eviction-leak test and `test_wf_deferred_hydration.py`.
- DISMISSED (fixture hoist): only ONE copy of the enable/restore-tracing fixture exists (`test_wf_pipe_router_tracing_config_nondeterminism.py::enable_tracing_restored`) — the costs-only test never enables tracing (its flush is stubbed and post-H1 the schedule doesn't read config). One user = nothing to dedup; moving the tests under `tracing/` would also subject them to that directory's `gha_disabled` CI skip, which would be a regression.
- DISMISSED (extract-pages scan): the "near-variant" in `tracing/test_split_worker_extract_pages.py` scans `(activity_type.name, activity_id)` pairs and `start_to_close_timeout`s, not bare names — different shape, not servable by `scheduled_activity_names` without contortion.

### 4. `open_tracer` stale-eviction re-implements `close_tracer` — `pipelex/graph/graph_tracer_manager.py`

The stale-tracer path (~line 131) inlines `pop` + `teardown()`, which is exactly `close_tracer`'s body. Delegate to keep one eviction path. **Caveat for the refactor:** gate the "evicting stale tracer" warning on `key in self._tracers` *before* delegating — `close_tracer`'s return value is ambiguous (`None` both when no tracer existed and when a costs-only tracer legitimately tears down without a `GraphSpec`).

**Status: FIXED** exactly as specified (membership-gated warning, then `self.close_tracer(key)`).

## Do with / after the H2 session (same code, avoid conflicts)

> The H2 fix has landed (eviction-safe `finally` ordering + `open_fresh_library`), so these are now unblocked — the `finally` block has its final shape.

These touch the exact `finally` block the H2 fix restructured; they were deferred to avoid churn while that fix was pending.

### 5. Skip the guaranteed-empty flush activity in costs-only LIVE runs — `wf_pipe_router.py`

Post-H1, the workflow's `BufferingEventLog` is deterministically empty in costs-only LIVE mode (the tracer gets `event_log=None`; all activity emissions go to the per-process fallback), yet every `WfPipeRouter` — including every child workflow spawned per sub-pipe by the controllers — schedules `act_flush_trace_events` with an empty payload: a wasted activity round-trip (history events, task-queue dispatch, worker slot) per workflow in the fan-out. The H1 rationale only forbids gating on **buffer content** (activity-fed, hence nondeterministic); a payload-pure gate is fine. Gate the schedule on `trace_context.emit_graph_events or run-mode-is-DRY` — both ride in the payload, so the decision replays identically.

**Status: FIXED.** Determinism argument re-derived independently before trusting it: (1) gate inputs (`emit_graph_events`, `pipe_run_params.run_mode`) are pure payload, identical on replay; (2) in costs-only LIVE the buffer's only possible feeders — inline tracer graph events and inline dry-run usage reporting — are both absent, and every LIVE usage emission is activity-side (always routed to the per-process fallback post-H1), so the skipped flush provably loses nothing; (3) Temporal is unshipped, so no in-flight histories exist to diverge against. Implemented as a `schedule_flush` bool computed in the tracing setup block (where `trace_context` is narrowed) and consumed in the `finally`. The costs-only regression test's vacuity guard inverted accordingly: the costs-only arm now asserts the flush is ABSENT from history and still replays cleanly; the graph arm keeps the original presence guard.

### 6. Trim the redundant null conjuncts in the `finally` block — `wf_pipe_router.py`

Verified redundant given the tracing setup block's atomicity: `and wf_tracer_key is not None` (~line 200), `and trace_context is not None` (~line 203), and the nested `if wf_tracer_key is not None` (~line 233) can never differ from their enclosing conditions. **Do not** go further and collapse the sentinels onto `trace_context is not None`: the sentinels are load-bearing — library-crate setup earlier in the `try` can raise before the tracing block runs, leaving them `None` while `trace_context` is set, and a `trace_context`-gated `finally` would then crash on `event_log.drain()` and unbound `wf_workflow_id`, masking the original error.

**Status: FIXED** (folded into the item 5/9 rewrite of the block). The tracer-close gate is now the single sentinel `wf_tracer_key is not None` (the `wf_graph_tracer_manager` variable is gone — the singleton getter is called in the finally, pure in-memory); the spec-assignment gate is `graph_spec is not None and pipe_output is not None` (costs-only returns `None` by `close_tracer`'s contract, noted in the comment); the nested `wf_tracer_key` re-check is gone (`clear_event_log` takes the always-bound `wf_run_id`, now assigned before the `try`). Sentinels (`wf_library_id`, `event_log`, `wf_tracer_key`) kept, as required.

## Smaller items from the H2-fix review (round 2)

### 8. Document `set_event_log`'s overwrite as load-bearing — `pipelex/reporting/reporting_manager.py`

The leaked-predecessor self-heal now exists as three uncoordinated idioms: `open_fresh_library` (explicit, WARNING), `open_tracer` pop-and-replace (explicit, WARNING), and `set_event_log`'s bare dict assignment (incidental, silent, undocumented). The silent overwrite is genuinely load-bearing: a leaked `_event_log_contexts` entry under the deterministic workflow id remains possible post-H2 (deadlock-detector thread abandonment skips `finally` entirely; worker kill between set and clear), and the overwrite is what heals it. A future hardening pass that adds "context already exists → raise" collision detection — exactly what pre-M1 `open_tracer` did — would reintroduce the eviction-poison class on the cost path with no test catching it. Fix: a comment on `set_event_log` stating the overwrite-on-existing-key is intentional and load-bearing for leaked-predecessor healing; ideally also a shared contract note ("worker-local state keyed by a deterministic workflow id must be self-healing on open/set") tying the three idioms together.

**Status: FIXED.** Comment added on the assignment in `set_event_log`, stating the shared contract and naming the two sibling idioms. (With item 0's run-id keying the leak window is same-run only, but the healing contract stands unchanged.)

### 9. Simplify the `finally` to one event-log block — `wf_pipe_router.py`

Verified equivalent and strictly simpler: move the library-teardown block BEFORE the event-log block, then keep `drain → close → clear_event_log → await flush` together under one `if event_log is not None:` with the await last inside it. Library teardown and event-log cleanup are mutually independent (teardown touches only `LibraryManager` dicts; `clear_event_log` is a bare `dict.pop`; nothing between drain and flush suspends), and the eviction-safety invariant is identical — all synchronous cleanup still precedes the only await. Deletes the `buffered_events` sentinel, the second gate, the TYPE_CHECKING-only `TraceEvent` import, and resolves the comment tension where "the flush activity is scheduled unconditionally" sits directly above a conditional. Natural to fold into item 5/6 since they edit the same block.

**Status: FIXED** (one rewrite together with 5 and 6). `buffered_events` sentinel, second gate, and the TYPE_CHECKING `TraceEvent` import all gone; the eviction-ordering guard test (item 0bis) pins the resulting invariant and was verified RED against a reordered block.

### 10. Extract a shared scoped-library helper for the two uuid-keyed copies — `runtime_bridge`

The seed-registry → open → `set_class_registry` → set-current → `load_from_crate` → teardown-in-finally ceremony exists in three hand-rolled copies. Verified: the two `runtime_bridge` copies (`bridge._scoped_library_for_crate`, `submitter_hydration.rehydrate_pipe_output_with_crate`) use per-call uuid4 ids, so they structurally cannot hit the leaked-predecessor collision and correctly do NOT need `open_fresh_library` — this is consolidation-for-maintenance only. Extract one shared async context manager for those two; leave `wf_pipe_router` bespoke — its teardown sequencing relative to the flush await IS the H2 fix, and folding it into a `with`-helper would fight that ordering.

**Status: FIXED.** One shared SYNC context manager `scoped_library_for_crate(library_crate, library_id_prefix)` in `pipelex/runtime_bridge/primitives/scoped_library.py` (the bridge's was only nominally async — `# noqa: RUF029` — so going sync removed the noqa too). Both copies replaced; id prefixes preserved (`runtime_bridge_*`, `rehydrate_*`); `wf_pipe_router` left bespoke as required, with the why documented on the helper.

### 11. One-line hardening: make `LibraryManager.teardown` forget the entry even if `library.teardown()` raises

Today all sub-teardowns are plain dict reassignments that provably cannot raise, so this is unreachable — but "teardown never raises" is an accident, not a contract. If a future teardown does real work (closing resources, a model gaining `validate_assignment`), a raising teardown would leave the entry in `_libraries` and turn `open_fresh_library` into a deterministic re-raise on every rerun of that id on that worker (permanent worker-local poison). Pop the entry first, or `del` in a `finally`.

**Status: FIXED** (folded into item 0's `_pop_and_teardown_library`): the entry is popped before `library.teardown()` runs and the associated maps are cleared in a `finally`. Unit tests in `tests/unit/pipelex/libraries/test_library_manager_teardown_forgets_entry.py` (RED first): a raising teardown still forgets the entry, and `open_fresh_library` recovers afterwards.

## Deferred design note (no action yet)

### 7. Graph events have no equivalent of the H1 usage-path guard

H1's fix enforces "only workflow-thread emissions land in the workflow buffer" for **usage** events only (via `ReportingManager`'s in-activity check). `GraphTracerManager` is imported in `wf_pipe_router.py` under `workflow.unsafe.imports_passed_through()`, so the singleton **is** shared across the sandbox boundary on co-located workers, and the workflow's tracer key rides into activity args via `job_metadata.trace_context`. No current activity-side code calls tracer hooks, so this is latent — but the first activity that does (bridge instrumentation, future activity-side tracing) would mutate the workflow's tracer from outside the workflow thread, corrupting replay-rebuilt graph data (the H1 mechanism on the graph path; post-fix it corrupts data payloads rather than the command stream, so it is data corruption, not TMPRL1100). The structural fix is the same request-scoped tracing-state direction already tracked as T3 in [tracing-cost-reporting.md](tracing-cost-reporting.md); until then, a guard or an explicit "activities must never call tracer hooks" contract note on the tracer manager would prevent the regression.

**Status: SURFACED** → [nondeterminism-follow-ups-decisions-needed.md](nondeterminism-follow-ups-decisions-needed.md) (options + recommendation; ride along with T3).
