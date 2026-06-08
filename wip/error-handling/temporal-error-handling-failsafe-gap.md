# The real defect: the Temporal integration can hang silently instead of failing loud

**Status:** ✅ **FIXED** (fixes A + B + E landed on `fix/Temporal-failsafe`). The fail-safe floor is in place; the silent-hang hole is closed. Deferred hardening (C, D, F) is tracked under "Deferred follow-ups" below — none of it is required to close the hole.
**Severity:** high — this is a class of bug, not one bug. The missing Search activity (see [`search-operator-missing-temporal-activity.md`](./search-operator-missing-temporal-activity.md)) is only the first trigger. Any future code path where an exception escapes pipe execution without having been converted to a Temporal terminal failure would hang the runner the same way. Fixing Search closes the instance; the fix below closes the hole.
**Companion brief:** read the Search brief first for the concrete instance; this one is about why the system let that instance become a silent hang.

## Resolution (implemented)

The fix establishes the fail-safe floor the design lacked, scoped to pipelex **domain** errors so transient Temporal/infra errors keep Temporal's (correct) task-retry behavior:

- **Fix A — workflow-level catch-all.** `WfPipeRouter.run()` and `WfPipeRun.run()` each gained a final `except PipelexError` boundary. `WfPipeRouter` converts a *genuine inline* error to a terminal `TemporalError` via `from_message_exception` (rich report in `ApplicationError.details`, exactly as the activity bridge does). `WfPipeRun` routes the inline error through its deferred-delivery path so the FAILED webhook still fires, then chains a details-carrying `TemporalError` so the classification also reaches the submitter. The catch-all converts only genuine inline errors: an escaping `PipelexError` that already carries a Temporal failure in its `__cause__` chain (e.g. a nested `TemporalPipeRouter` child-dispatch that already wrapped a sub-pipe failure as `WorkflowExecutionError`) is already terminal and recoverable, so it propagates untouched (guarded by `_carries_temporal_failure`) rather than being flattened to a generic report.
- **Fix B — worker-level floor.** `workflow_failure_exception_types` is now `[WorkflowExecutionError, PipelexError]` (`pipelex/temporal/temporal_task_manager.py`). Any domain error that slips past the catch-alls fails the workflow terminally instead of hanging — degrading to a synthesized `UnrecoverableWorkflowFailureError` (message preserved) rather than a silent retry loop.
- **Fix E — defensive tests.** `tests/integration/pipelex/temporal/test_workflow_inline_error_failsafe.py` pins the escape path: (1) an inline `PipelexError` in `WfPipeRouter` surfaces fully classified; (2) an inline `PipelexError` in `WfPipeRun` fires the FAILED webhook and reaches the submitter classified; (3) a raw uncaught `PipelexError` on the *production* worker fails terminally with the message preserved. Each sets a short `workflow_execution_timeout` so a regression that reopens the hole fails fast (on the wrong, timeout-shaped classification) instead of hanging the suite. The two contract tests that mirror the production worker config were updated to the broadened list. Full temporal suite green.

Docs updated: `docs/under-the-hood/error-model.md` gains a "Workflow-Level Fail-Safe Floor" subsection.

## Deferred follow-ups

These harden the system further but are **not** required to close the silent-hang hole (A + B already do). They are deferred because each is a distinct concern — cross-repo, a different bug class, or ops:

- **C — separate short submitter-side deadline for the synchronous API path.** Genuinely cross-repo: the sync `/execute` endpoint lives in `pipelex-api`, and giving it a bounded result-wait distinct from the 1h durable `workflow_execution_timeout` requires a caller-side change there (plus a config knob plumbed from `WorkerConfig` here). With A + B the silent hang is already closed — any domain error now fails terminally and fast — so C is defense-in-depth against *other* causes of slowness (genuinely slow pipes, infra hangs), not this defect. The brief's "no `pipelex-api` change" framing rules C out of a pipelex-only fix.
- **D — CI guard for the activity-dispatch invariant.** This is the regression guard for the *Search-class trigger* (an inference operator forgetting to route its leaf through an activity), tracked by the companion Search brief — not the systemic hole this brief is about. The floor (A + B) already degrades any such omission to a loud, classified failure instead of a hang, so D is a quality guard for the trigger, deferrable independently.
- **F — observability on stuck workflows.** A metric/alert on workflow-task-failure accumulation (or workflows open past an interactive threshold). Ops/infra concern; with A + B nothing should reach the stuck state for a domain error, so this is a backstop-for-the-backstop.

## Where the fix happens

Entirely in the `pipelex` repo (the open-source runtime). This brief is filed in `pipelex-api/wip/` because the symptom showed up there, but no `pipelex-api` change is involved. The next session is expected to run from a `pipelex` worktree.

**Path convention:** every `pipelex/...` path is relative to the **pipelex repo root** = your worktree root. Work inside the worktree; do not reach into a sibling `../pipelex/` checkout.

## One-sentence statement of the defect

The error-handling architecture (`pipelex/wip/error-handling/`) makes **terminal** Temporal failures cross the boundary beautifully — but it has **no backstop for the non-terminal "workflow task failure" mode**, which is exactly what any unconverted exception inside pipe code triggers, and which Temporal's default turns into a silent, ~1-hour hang that finally surfaces as the *wrong* error.

## Why this is the actual problem (not "Search forgot an activity")

The error-handling work invested heavily in the **terminal-failure recovery chain**:

- activity → workflow: `convert_pipelex_errors` makes leaf errors `TemporalError(ApplicationError)`; `from_app_error` recovers them in workflow code.
- workflow → submitter: `recover_error_report` + the `except WorkflowFailureError` clause rebuild the `ErrorReport` on the caller.
- child → parent: `WfPipeRun`'s `except ChildWorkflowError` lifts the report out of `exc.cause`.

Every one of these handlers fires **only when the inner unit fails *terminally* with a recognized failure type** (`ApplicationError` / `FailureError` / `WorkflowExecutionError`). That is the unstated, load-bearing precondition of the entire design.

Temporal has a second failure mode that the design never accounts for: a **workflow task failure**. When workflow code raises any exception that is *not* an `ApplicationError`/`FailureError` and *not* in the worker's `workflow_failure_exception_types`, Temporal does **not** fail the workflow. It assumes a transient/code-deploy bug, and **retries the workflow task** — re-running the workflow code from the last consistent point, indefinitely, bounded only by the workflow execution timeout.

A workflow-task failure reaches **none** of the recovery handlers above (there is no terminal failure to recover). The child never produces a `ChildWorkflowError`; the parent's `await execute_child_workflow(...)` simply never returns; the submitter's `execute_workflow(...)` simply never returns. The polished recovery chain is bypassed wholesale, and the system's behavior degrades to its worst possible quadrant: **invisible + unbounded-ish + resource-consuming.**

## The exact chain (Search as the worked example)

1. `WfPipeRouter.run()` executes the pipe inline (`pipelex/temporal/tprl_pipe/wf_pipe_router.py:139`). Its only handler is `except ActivityError` (`:146`).
2. A `SearchJobFailureError` (a `CogtError`/`PipelexError`) is raised inline — **not** an `ActivityError`, **not** an `ApplicationError`, **not** a `WorkflowExecutionError`. It escapes the child workflow raw.
3. Worker registers `workflow_failure_exception_types=[WorkflowExecutionError]` only (`pipelex/temporal/temporal_task_manager.py:148`). The escaping type isn't in it → **child workflow-task failure → child retries its task**, re-executing the inline search call for real on each retry (real provider spend + log spam; no result is recorded in history because there is no activity).
4. The child never fails terminally, so `WfPipeRun`'s `except ChildWorkflowError` (`pipelex/temporal/tprl_pipe/wf_pipe_run.py:67-82`) — the handler that would have produced a classified `WorkflowExecutionError` and fired the failure webhook — **never runs**. The parent's `await workflow.execute_child_workflow(...)` (`:59`) blocks.
5. The submitter's `execute_workflow(...)` (`pipelex/temporal/tprl/workflow_caller.py:91`) is awaiting the parent's result with `execution_timeout = workflow_execution_timeout` (configured **1h**, `:112`). The child has **no** execution timeout of its own (deliberately omitted for replay determinism — `wf_pipe_run.py:54-57`), so the whole tree is bounded only by the parent's 1h.
6. After ~1h the parent execution times out. The submitter gets a `WorkflowFailureError(TimeoutError)`; `recover_error_report` finds no `ApplicationError` report in a timeout chain and synthesizes an `UnrecoverableWorkflowFailureError` (`error_domain=RUNTIME`). The API returns **that opaque timeout** — not the `SearchJobFailureError` that was plainly in the worker logs the entire hour.

Net: a sync `/execute` request hangs for up to an hour and then returns the wrong, generic error, while the worker silently burns retries. The "improve error handling so it behaves well for the API" goal is fully defeated by this single uncovered mode.

## The systemic gaps (each is independent of the Search feature)

1. **The "every leaf error is converted at an activity boundary" invariant is unenforced.** It holds today only by manual enumeration — the hand-maintained `Tasks` activity list (`pipelex/temporal/tasks.py`) and `@convert_pipelex_errors` applied by hand per activity. Nothing fails when a new operator skips activity dispatch. Enumerated coverage rots; Search is the proof.

2. **No workflow-level catch-all that makes escaping domain exceptions terminal.** `WfPipeRouter` catches only `ActivityError`; `WfPipeRun` catches only `ChildWorkflowError`. Neither has a final clause that wraps an escaping `PipelexError` into a `WorkflowExecutionError` (the one type that *is* terminal here). Such a backstop would have turned the Search hang into an immediate, classified, surfaced failure — i.e. exactly the promised behavior — for any cause, known or not.

3. **`workflow_failure_exception_types` is set to the narrowest possible value and the default is the dangerous one.** It's `[WorkflowExecutionError]`. Everything depends on code paths *manually* arriving at that one type. The safer posture is to make Temporal fail the workflow terminally for any pipelex **domain** error by default (e.g. include `PipelexError`), so a missed conversion degrades to "fails loud with a slightly-less-rich report" instead of "hangs for an hour and lies."

4. **The synchronous API path has no short deadline and mis-prioritizes the surfaced error.** Two distinct faults: (a) a sync HTTP endpoint inherits the **1h durable** workflow execution timeout — there is no separate, short submitter-side result-wait for the interactive path; (b) on timeout the caller surfaces an opaque `UnrecoverableWorkflowFailureError` rather than the real, already-observed failure.

5. **Worst-quadrant failure with no observability.** During the hang there is no terminal event, no surfaced error, and (presumably) no alert — only an accumulating count of workflow-task failures visible in the Temporal UI if someone looks. A silent, resource-consuming, unbounded-until-timeout state is the single worst outcome a durable-execution system can produce, and nothing flags it.

6. **Tests pin the *terminal-classification* path, not the *escape* path.** The parity integration tests (`tests/integration/pipelex/temporal/test_workflow_error_report_full_chain.py` ↔ `.../error_handling/test_error_report_local_full_chain.py`) mock an activity to fail and assert `ErrorReport` parity — i.e. they exercise the path where conversion already happened. The defensive case that actually broke — "an unconverted exception escapes the workflow" — is untested. The test suite encoded the architecture's blind spot.

## Recommended fixes (systemic; do these even after Search is wired)

> **Status:** A, B, E are implemented — see [Resolution](#resolution-implemented) above. C, D, F are [deferred](#deferred-follow-ups). The original analysis is kept below for rationale.

Ordered by leverage. A and C are the floor; the rest harden and prevent regression.

**A. Workflow-level fail-safe (highest leverage).** In both `WfPipeRouter.run()` and `WfPipeRun.run()`, add a final boundary that converts an escaping pipelex **domain** exception into a terminal `WorkflowExecutionError` carrying `recover_error_report(...)` classification — mirroring the existing `ActivityError`/`ChildWorkflowError` handlers, but for the "raised inline, never went through an activity" case. This guarantees no pipe-code exception can become a silent workflow-task-retry hang again, for *any* operator.
   - **Scope it carefully.** Do **not** blanket-convert `Exception`. Workflow-task retry is the *correct* behavior for genuinely transient Temporal/infra errors and for deterministic-replay glitches — making those terminal would throw away durability's whole point. Convert pipelex **domain** errors (`PipelexError` and friends), and let Temporal-internal exceptions keep their default. Per repo standards, a workflow-root `except` is one of the two sanctioned `except Exception` sites only if you immediately re-raise as terminal *and* you've reasoned about the transient case; prefer `except PipelexError` here.

**B. Broaden `workflow_failure_exception_types` to include `PipelexError`.** Cheap belt-and-suspenders behind A: even a path that slips past the catch-all fails the workflow terminally instead of hanging. (`pipelex/temporal/temporal_task_manager.py:148`.) Verify interaction with the existing `WfPipeRun` contract test `test_wf_pipe_run_failure_path` (it pins the current `[WorkflowExecutionError]` value).

**C. Separate, short submitter-side deadline for synchronous execution.** Give the sync `/execute` path a bounded result-wait (config, seconds-to-low-minutes) distinct from the 1h durable `workflow_execution_timeout` that the async `/start` path legitimately needs. On deadline, surface a clear, classified timeout — never leave the HTTP request hanging on the durable budget. (Submitter side: `pipelex/temporal/tprl/workflow_caller.py` + the timeout config plumbed from `WorkerConfig`.)

**D. Enforce the activity-dispatch invariant in CI.** A test that walks the inference `PipeOperator` subclasses and asserts each routes its leaf through `get_content_generator()` (equivalently: each inference leaf has a protocol method + a registered activity). The next operator that forgets the wiring then fails CI, not production. (This is the regression guard for the Search-class bug.)

**E. Negative/defensive test for the escape path.** Assert that a raw `PipelexError` raised *inside pipe code* within a workflow (not via an activity) results in a terminal, classified failure promptly surfaced to the submitter — the exact invariant that was silently violated. Pair it across local/Temporal like the existing parity tests.

**F. Observability on stuck workflows.** A metric/alert on workflow-task-failure accumulation (or workflows open past a sane interactive threshold), so a path that still slips through A–E is visible instead of silent.

## The meta-lesson worth recording

The error-handling project optimized the **fail-loud** path to a high polish but never established a **fail-safe floor**. It assumed terminal classification everywhere and built rich recovery on top of that assumption, without a guard for the case where the assumption doesn't hold. In a durable-execution system the default for "unexpected exception in business logic running inside a workflow" is the most dangerous behavior available (retry forever), so "we convert all the errors we know about" is not enough — the system needs a backstop that holds for the errors, and the code paths, that nobody enumerated. Search exposed it; the next gap will too unless the floor exists.

## Reference file map (relative to pipelex repo root / your worktree root)

- Workflow that runs pipe code inline, catches only `ActivityError`: `pipelex/temporal/tprl_pipe/wf_pipe_router.py:139,146`
- Parent workflow, catches only `ChildWorkflowError`; child started without its own execution timeout: `pipelex/temporal/tprl_pipe/wf_pipe_run.py:54-82`
- Worker `workflow_failure_exception_types=[WorkflowExecutionError]`: `pipelex/temporal/temporal_task_manager.py:148`
- Submitter wait + 1h `execution_timeout` applied: `pipelex/temporal/tprl/workflow_caller.py:91-117`
- Timeout config source (`workflow_execution_timeout`, `run_timeout`, `rpc_timeout`): `pipelex/temporal/config_temporal.py` (`WorkerConfig`) + `pipelex/pipelex.toml` temporal section (~line 489)
- Activity error conversion (works for activity-dispatched leaves only): `pipelex/temporal/tprl/activity_error_boundary.py`
- Submitter-side report recovery (terminal-failure path only): `pipelex/temporal/tprl/temporal_error.py` (`recover_error_report`)
- Existing parity tests (terminal path; escape path untested): `tests/integration/pipelex/temporal/test_workflow_error_report_full_chain.py`, `tests/integration/pipelex/error_handling/test_error_report_local_full_chain.py`
- Design docs this critiques/extends: `pipelex/wip/error-handling/track-temporal-integration.md`, `.../track-retry-and-resilience.md`
- The concrete first instance: [`search-operator-missing-temporal-activity.md`](./search-operator-missing-temporal-activity.md)
