# Temporal fail-safe — secondary review follow-ups

**Status:** 🔎 open backlog. Lower-priority findings from the code review of the fail-safe floor that landed on `fix/Temporal-failsafe`. None blocks the merge. **Resolved in the guard-hardening session and removed from this doc:** Finding 4 (catch-all asymmetry — won't fix, harmless: a guarded branch in `WfPipeRun` would be dead code) and Finding 11 (rationale duplication — deduped onto `_carries_temporal_failure`'s docstring + `error-model.md`). Finding 12's comment overstatement was fixed there too; only its product question survives below. What remains open: a behavioral tradeoff (Finding 2), a contract decision (Finding 3), and small cleanups (5, 8, 10).

**Companion docs:** the fix is described in [`temporal-error-handling-failsafe-gap.md`](./temporal-error-handling-failsafe-gap.md); the landed behavior in [`track-temporal-integration.md`](./track-temporal-integration.md). The four highest-value findings (the guard's correctness, consolidation, reuse, and missing test) are in [`temporal-failsafe-guard-hardening.md`](./temporal-failsafe-guard-hardening.md) — **read its Background section first**; this doc assumes that context.

**Finding numbers** (2, 3, 5, 8, 10, 12) are kept from the original review. Findings 4 and 11 were resolved and removed (see Status).

---

## Background (cold-start, condensed)

The fail-safe floor makes a pipelex **domain** error raised *inline in workflow code* (never via an activity) fail the workflow **terminally and classified** instead of hanging on indefinite workflow-task retry. Two layers:

- `WfPipeRouter.run()` and `WfPipeRun.run()` each end with an `except PipelexError` clause. The router converts a genuine inline error to a terminal `TemporalError` via `from_message_exception` and raises immediately. The parent (`WfPipeRun`) routes it through its deferred-delivery path so the FAILED webhook still fires, then re-raises terminally.
- The worker registers `workflow_failure_exception_types=[WorkflowExecutionError, PipelexError]` as a backstop.

`from_message_exception` (`pipelex/temporal/tprl/temporal_error.py:232`) builds the terminal `TemporalError`: it sets `error_type = exc.__class__.__name__`, packs `exc.to_error_report().to_dict()` into `ApplicationError.details`, and derives `non_retryable` from the inference error category (or the `non_retryable_error_types` name-list fallback). The full background and the `_carries_temporal_failure` guard are explained in the companion hardening doc.

---

## Finding 2 — Retryable inline errors still re-run the inline leaf on retry (behavioral tradeoff + test gap)

**Where:** `wf_pipe_router.py:195` (the conversion) → `from_message_exception` retryability logic in `temporal_error.py:232-271`.

**What:** `from_message_exception` sets `non_retryable=False` for a transient/uncategorized-not-listed inline domain error. A *retryable* `ApplicationError` raised in workflow code is then subject to the workflow's `RetryPolicy` — configured for top-level workflows via `WorkflowExecutorFactory`, and the child `WfPipeRouter` is dispatched **without** an explicit retry policy (deliberately, for replay determinism — see `wf_pipe_run.py:50-57`), so it inherits Temporal's default. The consequence: a retryable inline error re-runs `pipe.run_pipe` — **including any real provider/inference call it makes inline** — on each attempt, up to the execution timeout.

**Why it matters:** this is strictly *better* than the pre-fix outcome (an unbounded workflow-task-retry hang that also re-ran the inline work), so it is not a regression. But the fix does **not** make retryable inline errors fail fast — it trades an unbounded hang for a bounded-but-still-resource-burning execution retry. And the tests only exercise the **non-retryable** arm (`make_failing_llm_error()` is a non-retryable `CONFIGURATION`-class error), so the retryable path's behavior is unverified.

**Open questions:**

1. Is execution-level retry of an inline leaf acceptable, or should the inline catch-all force `non_retryable=True` regardless of category? Rationale for forcing: if an operator is running its leaf *inline* (rather than via an activity with its own `RetryPolicy`), retrying the whole workflow execution is a blunt, expensive instrument — the operator was supposed to dispatch an activity precisely so that retry is scoped and observable. Rationale against: a genuinely transient inline error (rare) would then fail instead of self-healing.
2. This overlaps with deferred follow-up **C** (a short submitter-side deadline for the synchronous API path) and **D** (CI guard that every inference operator routes its leaf through an activity) in [`temporal-error-handling-failsafe-gap.md`](./temporal-error-handling-failsafe-gap.md). If **D** lands, "retryable inline error" becomes a should-never-happen state and this question is moot. Decide whether to engineer #1 now or defer behind **D**.
3. Add a test for the retryable-inline arm regardless of the above (it is currently a blind spot).

---

## Finding 3 — `SecurityError` is now routed through `except PipelexError` and the worker floor, contradicting its own contract

**Where:** the catch-alls (`wf_pipe_router.py:184`, `wf_pipe_run.py:83`) and the registration (`temporal_task_manager.py:147`). The contract: `pipelex/base_exceptions.py:567`.

**What:** `SecurityError`'s docstring states it is "kept distinct from domain errors so security signals are not silently swallowed by domain-level `except` handlers (e.g. `except PipelexError`)." `SecurityError` is a `PipelexError`, so the new `except PipelexError` clauses catch it and the `PipelexError` registration floors it — exactly the pattern the docstring warns against.

**Nuance:** the new code does **not** *silence* it — it re-raises it terminally with the type preserved in the report (`error_type` survives via `from_message_exception`). And making a security violation a terminal failure (rather than an indefinite retry) is arguably *correct*. So this may be a benign — even desirable — interaction. But it is the literal anti-pattern the contract calls out, and a maintainer relying on that contract would be surprised.

**Open questions:**

1. Should the catch-alls add an explicit `except SecurityError: raise` (or `except SecurityError` that converts but flags/audits differently) **before** the `except PipelexError`, to honor the contract literally?
2. Or do we update the `SecurityError` docstring/contract to acknowledge that the Temporal workflow boundary legitimately floors it to a terminal failure (because hanging on a security violation is worse)? If so, is there any place a `SecurityError` *should* get differentiated handling at the boundary (e.g. suppressed from the webhook payload, or routed to an audit sink)?
3. Are there other `PipelexError` subclasses with special "do not swallow" intent that the broad registration now captures? (Audit the hierarchy under `base_exceptions.py` for similar contracts.)

---

## Finding 5 — The inline path drops the original exception from the worker-side cause chain

**Where:** `wf_pipe_run.py:99` — `execution_error.__cause__ = TemporalError.from_message_exception(exc=exc)`.

**What:** the minted `TemporalError` itself has `__cause__ = None` (`from_message_exception` returns `cls(...)` and never chains `from exc`). So after `execution_error.__cause__` is set to it, the **original** inline `exc` and its traceback are no longer reachable from `execution_error`. This is asymmetric with:

- the sibling child-failure path (`wf_pipe_run.py:81`: `execution_error.__cause__ = exc`, preserving the `ChildWorkflowError`), and
- the router catch-all (`wf_pipe_router.py:195`: `raise TemporalError.from_message_exception(exc=exc) from exc`, preserving `exc`).

**Why it matters:** low. The classification and message survive (they ride in the `TemporalError.details` report and are logged via `workflow_log.error(f"WfPipeRun inline failure: {exc}")`), and the submitter recovers the report fine. The loss is the original exception object / traceback / any deeper `__cause__` on the worker side — a debuggability and consistency gap, not a behavioral break.

**Open question:** preserve the original by chaining it — set the minted `TemporalError`'s `__cause__` to `exc` before assigning it to `execution_error`, giving `execution_error → TemporalError → exc`. Confirm this does not confuse `recover_error_report`'s walk (it stops at the first report-carrying `ApplicationError`, so a deeper `exc` is harmless). Standalone fix now — the Finding-6 shared helper that would have owned the chaining was not built (the catch-alls stayed separate; see the hardening doc's light-touch resolution).

---

## Finding 8 — `exc.to_error_report()` is computed twice on the inline path (efficiency + drift risk)

**Where:** `wf_pipe_run.py:92` (`error_report = exc.to_error_report()`, for the webhook) and `:99` (`from_message_exception`, which internally recomputes `exc.to_error_report().to_dict()` at `temporal_error.py:243`).

**What:** `to_error_report()` is not trivial — it walks and enriches from the `__cause__` chain (`base_exceptions.py:482` + `_enrich_error_report_from_cause`). On every inline failure it is paid twice. Worse, the webhook gets the object from `:92` while the submitter gets the dict packed at `:99`; if the two derivations ever diverge, the webhook and submitter disagree on classification.

**Why it matters:** small wasted work on the failure path; the drift risk is the more interesting part (single-source-of-truth for the report).

**Proposed fix:** compute the report once and have `from_message_exception` accept a precomputed `ErrorReport` (or expose a variant taking the dict), so the webhook payload and the wire details come from one source.

**Open question:** does `from_message_exception`'s signature change ripple to the activity-side caller (`activity_error_boundary.py:52`)? Prefer an additive optional `error_report=` parameter that defaults to recomputing, so the activity path is unaffected.

---

## Finding 10 — `workflow_failure_exception_types=[WorkflowExecutionError, PipelexError]` is redundant

**Where:** `temporal_task_manager.py:147`.

**What:** `WorkflowExecutionError` is a subclass of `PipelexError` (via `TemporalFlowError`), so the second entry fully subsumes the first. The list is redundant. The previously-misleading comment was already trimmed in the guard-hardening session — it now says `WorkflowExecutionError` is "listed explicitly for intent" rather than claiming it is separately load-bearing — so what remains is purely the cosmetic list decision below.

**Why it matters:** harmless at runtime; a maintenance trap. A future reader who trusts the comment might narrow the broad `PipelexError` entry believing `WorkflowExecutionError` still covers the child-wrap case — when in fact removing `PipelexError` silently reopens the floor for every non-`WorkflowExecutionError` domain error, and removing `WorkflowExecutionError` changes nothing.

**Open question:** drop to `[PipelexError]` and simplify the comment, **or** keep `WorkflowExecutionError` explicit purely for documentation (signaling the originally-intended terminal type) with a comment that says so? Either is defensible; pick one and make the comment match reality.

---

## Finding 12 — Should a terminal failure with no delivery target still notify?

**Where:** `wf_pipe_run.py:89` (the webhook comment) and `:146` (`if delivery_assignment is not None:`).

**Comment half — done.** The guard-hardening trim dropped the "a terminal failure must always notify the receiver" overstatement; the comment now reads "fires the FAILED webhook on the failure path," which is accurate. Only the product question below remains.

**What:** when `delivery_assignment is None`, Step 3 is skipped (`wf_pipe_run.py:146`) and no webhook fires. This matches direct-mode `PipeRun` semantics (no target ⇒ no delivery), so the current behavior is intentional. The only test always supplies a webhook target, so the no-assignment branch is unexercised.

**Open question:** is "no target ⇒ no notification" the right product contract, or should a terminal failure always notify *somewhere* even without a `delivery_assignment` (cf. the memory note that a run's terminal failure webhook must always fire)? If the latter, the gap is in the code, not the comment. Current lean: keep as-is (parity with direct mode); revisit only if a "must-always-notify" product invariant is adopted.

---

## Suggested handling

- **Finding 2** and **Finding 3** are genuine decisions — surface them before the next Temporal release; both may be answered by the deferred **C/D** follow-ups in the gap doc.
- **Findings 5 and 8** are cheap standalone cleanups (the Finding-6 shared helper that would have absorbed them was not built — see the hardening doc's light-touch resolution). Best folded in opportunistically the next time `wf_pipe_run.py` is touched; **5** is the higher-value of the two.
- **Finding 10** is a one-line cleanup (drop the redundant entry, or keep it for intent) — batch it whenever `temporal_task_manager.py` is next edited. **Finding 12**'s comment is already fixed; only its product question lingers.
