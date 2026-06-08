# Temporal fail-safe — secondary review follow-ups

**Status:** 🔎 review follow-ups, **NOT implemented.** Lower-priority findings from the code review of the fail-safe floor that landed on `fix/Temporal-failsafe`. None blocks the merge. They range from a real behavioral tradeoff (Finding 2) and a contract decision (Finding 3) down to cleanup, doc duplication, and a comment nit.

**Companion docs:** the fix is described in [`temporal-error-handling-failsafe-gap.md`](./temporal-error-handling-failsafe-gap.md); the landed behavior in [`track-temporal-integration.md`](./track-temporal-integration.md). The four highest-value findings (the guard's correctness, consolidation, reuse, and missing test) are in [`temporal-failsafe-guard-hardening.md`](./temporal-failsafe-guard-hardening.md) — **read its Background section first**; this doc assumes that context.

**Finding numbers** (2, 3, 4, 5, 8, 10, 11, 12) are kept from the original review.

---

## Background (cold-start, condensed)

The fail-safe floor makes a pipelex **domain** error raised *inline in workflow code* (never via an activity) fail the workflow **terminally and classified** instead of hanging on indefinite workflow-task retry. Two layers:

- `WfPipeRouter.run()` and `WfPipeRun.run()` each end with an `except PipelexError` clause. The router converts a genuine inline error to a terminal `TemporalError` via `from_message_exception` and raises immediately. The parent (`WfPipeRun`) routes it through its deferred-delivery path so the FAILED webhook still fires, then re-raises terminally.
- The worker registers `workflow_failure_exception_types=[WorkflowExecutionError, PipelexError]` as a backstop.

`from_message_exception` (`pipelex/temporal/tprl/temporal_error.py:240`) builds the terminal `TemporalError`: it sets `error_type = exc.__class__.__name__`, packs `exc.to_error_report().to_dict()` into `ApplicationError.details`, and derives `non_retryable` from the inference error category (or the `non_retryable_error_types` name-list fallback). The full background and the `_carries_temporal_failure` guard are explained in the companion hardening doc.

---

## Finding 2 — Retryable inline errors still re-run the inline leaf on retry (behavioral tradeoff + test gap)

**Where:** `wf_pipe_router.py:197` (the conversion) → `from_message_exception` retryability logic in `temporal_error.py:240-279`.

**What:** `from_message_exception` sets `non_retryable=False` for a transient/uncategorized-not-listed inline domain error. A *retryable* `ApplicationError` raised in workflow code is then subject to the workflow's `RetryPolicy` — configured for top-level workflows via `WorkflowExecutorFactory`, and the child `WfPipeRouter` is dispatched **without** an explicit retry policy (deliberately, for replay determinism — see `wf_pipe_run.py:50-57`), so it inherits Temporal's default. The consequence: a retryable inline error re-runs `pipe.run_pipe` — **including any real provider/inference call it makes inline** — on each attempt, up to the execution timeout.

**Why it matters:** this is strictly *better* than the pre-fix outcome (an unbounded workflow-task-retry hang that also re-ran the inline work), so it is not a regression. But the fix does **not** make retryable inline errors fail fast — it trades an unbounded hang for a bounded-but-still-resource-burning execution retry. And the tests only exercise the **non-retryable** arm (`make_failing_llm_error()` is a non-retryable `CONFIGURATION`-class error), so the retryable path's behavior is unverified.

**Open questions:**

1. Is execution-level retry of an inline leaf acceptable, or should the inline catch-all force `non_retryable=True` regardless of category? Rationale for forcing: if an operator is running its leaf *inline* (rather than via an activity with its own `RetryPolicy`), retrying the whole workflow execution is a blunt, expensive instrument — the operator was supposed to dispatch an activity precisely so that retry is scoped and observable. Rationale against: a genuinely transient inline error (rare) would then fail instead of self-healing.
2. This overlaps with deferred follow-up **C** (a short submitter-side deadline for the synchronous API path) and **D** (CI guard that every inference operator routes its leaf through an activity) in [`temporal-error-handling-failsafe-gap.md`](./temporal-error-handling-failsafe-gap.md). If **D** lands, "retryable inline error" becomes a should-never-happen state and this question is moot. Decide whether to engineer #1 now or defer behind **D**.
3. Add a test for the retryable-inline arm regardless of the above (it is currently a blind spot).

---

## Finding 3 — `SecurityError` is now routed through `except PipelexError` and the worker floor, contradicting its own contract

**Where:** the catch-alls (`wf_pipe_router.py:174`, `wf_pipe_run.py:83`) and the registration (`temporal_task_manager.py:159`). The contract: `pipelex/base_exceptions.py:549`.

**What:** `SecurityError`'s docstring states it is "kept distinct from domain errors so security signals are not silently swallowed by domain-level `except` handlers (e.g. `except PipelexError`)." `SecurityError` is a `PipelexError`, so the new `except PipelexError` clauses catch it and the `PipelexError` registration floors it — exactly the pattern the docstring warns against.

**Nuance:** the new code does **not** *silence* it — it re-raises it terminally with the type preserved in the report (`error_type` survives via `from_message_exception`). And making a security violation a terminal failure (rather than an indefinite retry) is arguably *correct*. So this may be a benign — even desirable — interaction. But it is the literal anti-pattern the contract calls out, and a maintainer relying on that contract would be surprised.

**Open questions:**

1. Should the catch-alls add an explicit `except SecurityError: raise` (or `except SecurityError` that converts but flags/audits differently) **before** the `except PipelexError`, to honor the contract literally?
2. Or do we update the `SecurityError` docstring/contract to acknowledge that the Temporal workflow boundary legitimately floors it to a terminal failure (because hanging on a security violation is worse)? If so, is there any place a `SecurityError` *should* get differentiated handling at the boundary (e.g. suppressed from the webhook payload, or routed to an audit sink)?
3. Are there other `PipelexError` subclasses with special "do not swallow" intent that the broad registration now captures? (Audit the hierarchy under `base_exceptions.py` for similar contracts.)

---

## Finding 4 — `WfPipeRun`'s catch-all lacks the `_carries_temporal_failure` guard that `WfPipeRouter` has (asymmetry)

**Where:** `wf_pipe_run.py:83` (no guard) vs `wf_pipe_router.py:195` (guard).

**What:** the router converts only when `not _carries_temporal_failure(exc)` (it lets an already-terminal escapee propagate untouched to avoid flattening a recoverable report). The parent's `except PipelexError` has no such guard and unconditionally calls `exc.to_error_report()` + mints a fresh `TemporalError`. The two catch-alls disagree on the same input.

**Why it matters:** unreachable today — `WfPipeRun`'s `try` body holds only `await workflow.execute_child_workflow(...)` (caught by the prior `except ChildWorkflowError`) plus the pure helpers `build_search_attributes` / `build_static_summary`, none of which escapes a `FailureError`-carrying `PipelexError`. So the asymmetry is currently a latent trap, not a live bug. But it rests on an *unstated* invariant: if anything is ever added to that `try` block that lets such an error through, the parent flattens what the router would preserve.

**Open question:** this is **subsumed by Finding 6** in the hardening doc — if both catch-alls are folded onto one `convert_inline_pipelex_error` helper, the guard becomes non-optional and the asymmetry disappears. Decide whether to fix it standalone (add the guard to `WfPipeRun`) or only as part of the Finding-6 consolidation. Recommendation: fold into Finding 6.

---

## Finding 5 — The inline path drops the original exception from the worker-side cause chain

**Where:** `wf_pipe_run.py:106` — `execution_error.__cause__ = TemporalError.from_message_exception(exc=exc)`.

**What:** the minted `TemporalError` itself has `__cause__ = None` (`from_message_exception` returns `cls(...)` and never chains `from exc`). So after `execution_error.__cause__` is set to it, the **original** inline `exc` and its traceback are no longer reachable from `execution_error`. This is asymmetric with:

- the sibling child-failure path (`wf_pipe_run.py:81`: `execution_error.__cause__ = exc`, preserving the `ChildWorkflowError`), and
- the router catch-all (`wf_pipe_router.py:197`: `raise TemporalError.from_message_exception(exc=exc) from exc`, preserving `exc`).

**Why it matters:** low. The classification and message survive (they ride in the `TemporalError.details` report and are logged via `workflow_log.error(f"WfPipeRun inline failure: {exc}")`), and the submitter recovers the report fine. The loss is the original exception object / traceback / any deeper `__cause__` on the worker side — a debuggability and consistency gap, not a behavioral break.

**Open question:** preserve the original by chaining it — e.g. set the minted `TemporalError`'s `__cause__` to `exc` before assigning, or restructure so the chain is `execution_error → TemporalError → exc`. Confirm this does not confuse `recover_error_report`'s walk (it stops at the first report-carrying `ApplicationError`, so a deeper `exc` is harmless). Worth doing as part of the Finding-6 consolidation since the helper would own the chaining.

---

## Finding 8 — `exc.to_error_report()` is computed twice on the inline path (efficiency + drift risk)

**Where:** `wf_pipe_run.py:96` (`error_report = exc.to_error_report()`, for the webhook) and `:106` (`from_message_exception`, which internally recomputes `exc.to_error_report().to_dict()` at `temporal_error.py:251`).

**What:** `to_error_report()` is not trivial — it walks and enriches from the `__cause__` chain (`base_exceptions.py:459` + `_enrich_error_report_from_cause`). On every inline failure it is paid twice. Worse, the webhook gets the object from `:96` while the submitter gets the dict packed at `:106`; if the two derivations ever diverge, the webhook and submitter disagree on classification.

**Why it matters:** small wasted work on the failure path; the drift risk is the more interesting part (single-source-of-truth for the report).

**Proposed fix:** compute the report once and have `from_message_exception` accept a precomputed `ErrorReport` (or expose a variant taking the dict), so the webhook payload and the wire details come from one source.

**Open question:** does `from_message_exception`'s signature change ripple to the activity-side caller (`activity_error_boundary.py:52`)? Prefer an additive optional `error_report=` parameter that defaults to recomputing, so the activity path is unaffected.

---

## Finding 10 — `workflow_failure_exception_types=[WorkflowExecutionError, PipelexError]` is redundant

**Where:** `temporal_task_manager.py:159`.

**What:** `WorkflowExecutionError` is a subclass of `PipelexError` (via `TemporalFlowError`), so the second entry fully subsumes the first. The list is redundant, and the long comment that justifies `WorkflowExecutionError` as a separate, load-bearing entry is now misleading about what the two entries actually do.

**Why it matters:** harmless at runtime; a maintenance trap. A future reader who trusts the comment might narrow the broad `PipelexError` entry believing `WorkflowExecutionError` still covers the child-wrap case — when in fact removing `PipelexError` silently reopens the floor for every non-`WorkflowExecutionError` domain error, and removing `WorkflowExecutionError` changes nothing.

**Open question:** drop to `[PipelexError]` and simplify the comment, **or** keep `WorkflowExecutionError` explicit purely for documentation (signaling the originally-intended terminal type) with a comment that says so? Either is defensible; pick one and make the comment match reality.

---

## Finding 11 — The fail-safe rationale is restated five-to-six times (doc duplication)

**Where:** `_carries_temporal_failure`'s docstring (`wf_pipe_router.py:27-37`), the router catch-all comment (`:175-194`), the `WfPipeRun` catch-all comment (`wf_pipe_run.py:84-105`), the `temporal_task_manager.py` registration comment (`:64-83`), plus `CHANGELOG.md`, `docs/under-the-hood/error-model.md`, and the two wip docs.

**What:** the same argument — "only genuine inline errors are converted / an already-terminal escapee propagates untouched / scoped to `PipelexError` because transient infra errors keep task-retry" — is written out in full in many places. Any change to the policy must be edited in all of them or it rots.

**Open question:** state the rationale once (the shared helper's docstring once Finding 6 lands, plus the `error-model.md` section which is the user-facing home), and have the call-sites carry a one-line pointer instead of re-deriving the whole argument. Confirm which location is canonical — recommendation: the helper docstring for the *code* contract, `error-model.md` for the *design* narrative.

---

## Finding 12 — Comment overstates the webhook guarantee when there is no delivery target

**Where:** `wf_pipe_run.py:89` — the comment "Route it through the same deferred-re-raise path as a child failure so `act_deliver` still fires the FAILED webhook (a terminal failure must always notify the receiver)".

**What:** when `delivery_assignment is None`, Step 3 is skipped (`wf_pipe_run.py:153` `if delivery_assignment is not None:`) and no webhook fires. The behavior is correct (no target ⇒ no delivery, matching direct-mode `PipeRun` semantics), but the comment's "must always notify the receiver" overstates it. The only test always supplies a webhook target, so the no-assignment branch is unexercised.

**Open question:** just soften the comment to "fires the FAILED webhook *when a delivery target is configured*"? Or is "a terminal failure must always notify" an actual product invariant we want to enforce even with no `delivery_assignment` (in which case the gap is in the code, not the comment)? See the memory/feedback note that a run's terminal failure notification should always fire — reconcile this comment with that principle and decide which side is authoritative here.

---

## Suggested handling

- **Finding 2** and **Finding 3** are genuine decisions — surface them before the next Temporal release; both may be answered by the deferred **C/D** follow-ups in the gap doc.
- **Findings 4, 5, 8** are cheap and best folded into the Finding-6 consolidation in the hardening doc (the shared helper would own the guard, the cause-chaining, and the single report computation).
- **Findings 10, 11, 12** are cleanup/doc nits — batch them whenever the file is next touched.
