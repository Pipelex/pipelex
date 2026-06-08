# Temporal fail-safe — secondary review follow-ups

> **Gated on Temporal productionization — parked, not abandoned.** The silent-hang hole this branch closed is *done and shipped*; everything below is latent because Temporal is not in production (Findings 13/14 have no trigger until workflows actually run; C/D/F are pre-prod hardening; 3/12 are decisions, not bugs). **Do not execute piecemeal now** — run it as one focused pass when Temporal is scheduled to ship, with the system exercisable so the fixes are verifiable rather than speculative. The only "now" exception: fold the opportunistic one-liners (5, 8, 10) in *if* their file is touched for another reason.

**Status:** 🔎 open backlog. Lower-priority findings from the code review of the fail-safe floor that landed on `fix/Temporal-failsafe`. None blocks the merge. **Resolved in the guard-hardening session and removed from this doc:** Finding 4 (catch-all asymmetry — won't fix, harmless: a guarded branch in `WfPipeRun` would be dead code) and Finding 11 (rationale duplication — deduped onto `_carries_temporal_failure`'s docstring + `error-model.md`). Finding 12's comment overstatement was fixed there too; only its product question survives below. **Resolved in the review-agent triage session** (independently re-flagged by codex + cubic): Finding 2 — the inline conversions now force `non_retryable=True` (deterministic + terminal); see its resolution banner below. What remains open: a contract decision (Finding 3), small cleanups (5, 8, 10), and two findings added by a later `/review` pass — **Finding 13** (the `_carries_temporal_failure` predicate floors inline errors chained from a report-less `FailureError` — deepens the Finding 1 fragility analysis) and **Finding 14** (a pre-existing replay-determinism hazard: `build_search_attributes` reads config on the recorded child-start command).

**Companion docs:** the fix is described in [`temporal-error-handling-failsafe-gap.md`](./temporal-error-handling-failsafe-gap.md); the landed behavior in [`track-temporal-integration.md`](./track-temporal-integration.md). The four highest-value findings (the guard's correctness, consolidation, reuse, and missing test) are in [`temporal-failsafe-guard-hardening.md`](./temporal-failsafe-guard-hardening.md) — **read its Background section first**; this doc assumes that context.

**Finding numbers** (2, 3, 5, 8, 10, 12) are kept from the original review. Findings 4 and 11 were resolved and removed (see Status). **Findings 13 and 14** were added by a later `/review` pass (adversarial subagent + verification); they continue this doc's numeric scheme. (The gap doc owns the `A`–`F` letters for its fix-plan items, so there is deliberately no letter/number overlap across the two docs.)

---

## Background (cold-start, condensed)

The fail-safe floor makes a pipelex **domain** error raised *inline in workflow code* (never via an activity) fail the workflow **terminally and classified** instead of hanging on indefinite workflow-task retry. Two layers:

- `WfPipeRouter.run()` and `WfPipeRun.run()` each end with an `except PipelexError` clause. The router converts a genuine inline error to a terminal `TemporalError` via `from_message_exception` and raises immediately. The parent (`WfPipeRun`) routes it through its deferred-delivery path so the FAILED webhook still fires, then re-raises terminally.
- The worker registers `workflow_failure_exception_types=[WorkflowExecutionError, PipelexError]` as a backstop.

`from_message_exception` (`pipelex/temporal/tprl/temporal_error.py:232`) builds the terminal `TemporalError`: it sets `error_type = exc.__class__.__name__`, packs `exc.to_error_report().to_dict()` into `ApplicationError.details`, and derives `non_retryable` from the inference error category (or the `non_retryable_error_types` name-list fallback). The full background and the `_carries_temporal_failure` guard are explained in the companion hardening doc.

---

## Finding 2 — Retryable inline errors still re-run the inline leaf on retry (behavioral tradeoff + test gap)

> **✅ Resolved on `fix/Temporal-failsafe`** (review-agent triage; independently re-flagged by codex + cubic). The inline catch-alls now pass `force_non_retryable=True` to `from_message_exception` (the `wf_pipe_router.py` line-195 conversion and the `wf_pipe_run.py` inline carrier). Open question #1 is answered **"force `non_retryable=True`"**: an inline domain error fails the workflow terminally instead of re-running already-completed inline work on a blunt whole-workflow retry — retry belongs at the activity boundary, where it is scoped and observable. Forcing the flag also short-circuits the config-reading `_is_non_retryable`, so the workflow-side conversion is now **config-free / deterministic** — which also resolves the separate review concern that `from_message_exception` read `get_config()` inside workflow code (a replay-fragility risk). The report's own `retryable` field is config-free and preserved as informational metadata. Open question #3 (test the arm) is closed: `test_temporal_error_bridge.py::TestTemporalErrorBridge::test_force_non_retryable_is_deterministic_and_preserves_report_retryable` pins `non_retryable=True`, the preserved `report.retryable`, and that `_is_non_retryable` is not called when forced. Original analysis kept below for the record.

**Where:** `wf_pipe_router.py:195` (the conversion) → `from_message_exception` retryability logic in `temporal_error.py`.

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

## Finding 13 — `_carries_temporal_failure` floors inline errors chained from a non-`ApplicationError` `FailureError` (deepens Finding 1)

> **Provenance:** surfaced by a `/review` adversarial pass and verified against the live Temporal SDK hierarchy. Latent today, not a merge blocker. Extends [`temporal-failsafe-guard-hardening.md`](./temporal-failsafe-guard-hardening.md) Finding 1 with a third fragility mode its analysis did not consider.

**Where:** `wf_pipe_router.py:56` (`_carries_temporal_failure`), gating the conversion at `:198`.

**What:** the predicate is `any(isinstance(node, FailureError) for node in iter_cause_chain(exc))`. Verified: `TimeoutError`, `CancelledError`, `TerminatedError`, `ActivityError`, and `ChildWorkflowError` are **all** `FailureError` subclasses but **not** `ApplicationError` — and only `ApplicationError` carries the `details` payload where the structured `ErrorReport` rides. So an inline `PipelexError` chained `from` a bare Temporal failure that carries no recoverable report — e.g. pipe code that awaits an activity, the activity times out, and the code does `raise SomeDomainError(...) from timeout_exc` — returns `True` and is **propagated untouched**. At the submitter, `recover_error_report` walks `__cause__` for a report-bearing `ApplicationError`, finds none (a `TimeoutError`/`CancelledError` has no `details`), and synthesizes an `UnrecoverableWorkflowFailureError` — **dropping the domain error's own `error_type` / message** that `from_message_exception` (the convert branch) would have preserved. The guard's docstring assumes the chain's `FailureError` is a report-carrier ("the rich leaf classification lives deeper, in the child's `ApplicationError.details`"); that assumption is false for non-`ApplicationError` `FailureError`s.

**Why it matters:** this is the exact classification-fidelity loss the error-handling project exists to prevent — surfacing neither the timeout nor the domain error, but a generic synthesized report. **Latent today:** the one real inline-leaf path (`content_generator_in_workflow.py`) raises `TemporalError.from_app_error(...)` — an `ApplicationError`-with-report — so it is classified correctly, and genuine inline errors (Search-missing-activity, crate-load, hydration) carry no `FailureError` and convert correctly. The gap opens the moment any operator catches a Temporal timeout/cancel and re-raises a *plain* `PipelexError` `from` it inline.

**Why the obvious fix regresses (and what to do instead):** tightening the predicate to "carries a recoverable report" (`isinstance(node, ApplicationError) and error_report_dict_from_details(node.details) is not None`) **breaks the reachable case** Finding 1 protects: the controller-sub-pipe-as-child-workflow failure escapes as `WorkflowExecutionError` → `ChildWorkflowError`, whose leaf report lives in `ChildWorkflowError.cause` (recovered only by the submitter's `.cause`-normalizing walk), **not** in `__cause__` — so a worker-side `__cause__`-only report check would not find it and would wrongly convert. This is third confirmation that the broad-vs-narrow predicate is fundamentally fragile, and it strengthens the case for **Finding 1's deferred option (b)**: stop using the guard as the load-bearing decision — instead always mint a `TemporalError` but have `from_message_exception` *prefer an already-present report in the chain* over re-deriving, so flattening is impossible regardless of the `from`/`__cause__`/`.cause` shape.

**Open questions:**

1. Adopt Finding 1 option (b) (report-preserving conversion, guard demoted)? That subsumes both this finding and Finding 1's original two modes.
2. Until then, is it worth a narrow guard tweak that treats a chain whose only `FailureError`s are report-less (`TimeoutError`/`CancelledError`/`TerminatedError`) as convert-eligible, while still propagating `ChildWorkflowError`/report-bearing `ApplicationError`? (More surface, partial fix — option (b) is cleaner.)
3. Add a `True`-branch test variant where the chain carries a report-less `FailureError`, asserting the domain error's own classification survives (it currently does **not**).

---

## Finding 14 — `build_search_attributes` reads `get_config()` on the recorded child-start command (replay-determinism hazard, pre-existing)

> **Provenance:** surfaced by a `/review` adversarial pass; verified that `build_search_attributes` reads config. **Pre-existing — not introduced by this branch** (`pipelex/temporal/tprl/observability.py` is untouched here). Filed here per the repo's "flag pre-existing bugs" principle because it directly undercuts the fail-safe's anti-hang purpose. Better tracked in a dedicated Temporal wip doc if one is opened.

**Where:** `observability.py:104` (`config = get_config().temporal.search_attributes`) feeding `wf_pipe_run.py:63` and `temporal_pipe_router.py` (`search_attributes=build_search_attributes(pipe_job)` as an argument to `execute_child_workflow`).

**What:** the `search_attributes` value is part of the recorded `StartChildWorkflowExecution` command. Because `build_search_attributes` derives it from `get_config().temporal.search_attributes` (`.enabled`, `.attributes`) — process/deploy state, not workflow input — editing that config while a workflow is live would make a later replay re-derive a *different* attribute set on the child-start command → a Temporal non-determinism mismatch. This contradicts the same file's load-bearing comment (`wf_pipe_run.py:50-57`), which deliberately keeps the child-dispatch command "a pure function of the workflow input" precisely so "replay after a config edit" cannot diverge — the comment enumerates `execution_timeout` / `retry_policy` / `task_queue` but overlooks that `search_attributes` is on the same command and is config-derived. The function's docstring calls itself pure because it "reads everything off `pipe_job`," which is inaccurate.

**Why it matters:** a config-edit-during-live-workflow → stuck/failed replay is the exact silent-hang class the fail-safe exists to eliminate, sitting unguarded on the dispatch path. **Latent:** narrow trigger (a long-running workflow surviving a worker redeploy with edited search-attribute config) and Temporal is not yet in production.

**Open questions:**

1. Stamp the resolved search attributes onto `pipe_job`/`PipeRunArg` at submit time (submitter-side, before the durable boundary) so the workflow reads them off its input instead of `get_config()` — matching how the file already handles `execution_timeout` / `retry_policy` / `task_queue`.
2. Or confirm (with a versioning/patch strategy) that search-attribute config is frozen for a workflow's lifetime, and correct the `build_search_attributes` docstring's "pure" claim either way.
3. Does `build_static_summary` (also on the command) have any config dependency? (Spot-checked: no `get_config()` read — appears input-only, but confirm.)

---

## Suggested handling

- **Finding 2** is resolved (see its banner — inline conversions forced non-retryable + deterministic). **Finding 3** remains a genuine decision — surface it before the next Temporal release; it may be answered by the deferred **C/D** follow-ups in the gap doc.
- **Findings 5 and 8** are cheap standalone cleanups (the Finding-6 shared helper that would have absorbed them was not built — see the hardening doc's light-touch resolution). Best folded in opportunistically the next time `wf_pipe_run.py` is touched; **5** is the higher-value of the two.
- **Finding 10** is a one-line cleanup (drop the redundant entry, or keep it for intent) — batch it whenever `temporal_task_manager.py` is next edited. **Finding 12**'s comment is already fixed; only its product question lingers.
- **Finding 13** is the higher-value of the two new ones: it converts Finding 1 from "resolved — kept the broad predicate" to "the broad predicate has a third, unhandled failure mode," and points at Finding 1 option (b) (report-preserving conversion) as the resolution that subsumes all of it. Decide 13 and Finding 1 together, before the next Temporal release. Latent today, so not urgent — but it is a correctness gap, not a cosmetic one.
- **Finding 14** is pre-existing and out of this branch's scope; fold it into a dedicated Temporal wip doc (or fix it at submit time per its open question 1) when `observability.py` / the child-dispatch path is next touched.
