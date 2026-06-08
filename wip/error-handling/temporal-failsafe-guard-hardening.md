# Temporal fail-safe — harden & consolidate the inline-error guard

**Status:** ✅ **RESOLVED** on `fix/Temporal-failsafe`. All four findings handled; the chain-walk and fail-safe suites are green. Summary of decisions (the original analysis is preserved below for the record):

- **Finding 7 (done).** Extracted one cycle-guarded `iter_cause_chain(exc)` primitive in `base_exceptions.py`; the five hand-rolled `__cause__` walks (`_carries_temporal_failure`, `find_inference_error_category_in_chain`, `_find_error_report_dict`, `_message_from_exc`, and the cycle check in `_enrich_error_report_from_cause` — the doc missed this fifth one) now delegate to it.
- **Finding 9 (done).** Added `test_router_already_terminal_error_propagates_untouched_preserving_leaf_classification` for the guard's `True` branch. Proven meaningful: forcing the guard to `False` flips the submitter's `error_type` from the leaf `LLMCompletionError` to the generic `WorkflowExecutionError`, which the new test catches — while the convert-branch sibling stays green, which is exactly why this branch needed its own coverage.
- **Finding 1 (kept, *not* rewritten).** Verification upgraded the doc's own risk note: the guard's `True` branch is **reachable**, not theoretical — a controller sub-pipe failing as a child workflow is wrapped by `TemporalPipeRouter` as `WorkflowExecutionError(msg)` (no `error_report`) and escapes the parent's `pipe.run_pipe`. Its rich leaf report lives only in the child's `ApplicationError.details`, recoverable solely by `recover_error_report` at the submitter; any worker-side `from_message_exception` flattens it. **Both proposed rewrites regress this** — direction (a) (direct-cause check) is equal-or-worse (a deeper `FailureError` in a legitimate nested wrapper would now flatten), and direction (b) (always-convert) flattens the reachable case outright. So the broad "carries a Temporal `FailureError`" predicate is kept — it *is* the definition of "already terminal", not a proxy for a narrower type — refactored onto the primitive, with its docstring now stating the reachable case and the `raise … from` invariant (the over-inclusive "recover-then-rechain" failure requires an anti-pattern no operator does). The Finding 9 test pins it.
- **Finding 6 (light touch).** The two catch-alls' control flow is irreducibly different (router raises immediately; parent defers so `act_deliver` still fires the FAILED webhook), so they were **not** folded into one helper — that would force a dead, unreachable guarded branch into `WfPipeRun`. Instead the duplicated *rationale prose* (Finding 11) was deduped: the full argument lives once in `_carries_temporal_failure`'s docstring (code contract) + `docs/under-the-hood/error-model.md` "Workflow-Level Fail-Safe Floor" (design narrative); the router / parent / worker-registration comments carry a short statement plus a pointer.

**Left open (followups doc):** Finding 4 (parent lacks the guard) stays open but is assessed harmless — `WfPipeRun`'s `except PipelexError` can only catch errors from the pure `build_search_attributes` / `build_static_summary` argument evaluation, which cannot carry a `FailureError`, so a guarded branch there would be dead code. Findings 2, 3, 5, 8, 10, 12 are untouched (out of this doc's scope).

---

**Original review follow-up (for the record).** These were the highest-value findings from the code review of the fail-safe floor that landed on `fix/Temporal-failsafe`. None blocked the merge — the silent-hang hole *is* closed — but all four concern the single load-bearing mechanism the fix relies on, and they were best done together as one small refactor.

**Companion docs:** the fix itself is described in [`temporal-error-handling-failsafe-gap.md`](./temporal-error-handling-failsafe-gap.md) (the "why" and "what landed"); the landed behavior is summarized in [`track-temporal-integration.md`](./track-temporal-integration.md) under "Workflow-level fail-safe floor". The other, lower-priority review findings are in [`temporal-failsafe-review-followups.md`](./temporal-failsafe-review-followups.md).

**Finding numbers** (1, 6, 7, 9) are kept from the original review so the two follow-up docs cross-reference cleanly.

---

## Background (cold-start)

The fail-safe floor closes a hole where a pipelex **domain** error raised *inline in workflow code* — never dispatched through an activity — was neither an `ActivityError` nor an `ApplicationError`, so Temporal treated it as a *workflow-task* failure and retried it indefinitely: a silent, resource-burning hang surfaced only as a generic timeout after the execution timeout.

The fix has two layers:

- **Workflow-level catch-all.** `WfPipeRouter.run()` (`pipelex/temporal/tprl_pipe/wf_pipe_router.py`) and `WfPipeRun.run()` (`.../wf_pipe_run.py`) each end their boundary handling with an `except PipelexError` clause that converts a *genuine inline* error into a terminal, classified `TemporalError` (an `ApplicationError` carrying the structured `ErrorReport` in `details`).
- **Worker-level floor.** The worker registers `workflow_failure_exception_types=[WorkflowExecutionError, PipelexError]` (`pipelex/temporal/temporal_task_manager.py`), so any domain error that slips past the catch-alls still fails the workflow terminally instead of hanging.

The "genuine inline" decision is made by **`_carries_temporal_failure(exc)`** in `wf_pipe_router.py:26`. It walks the exception's `__cause__` chain and returns `True` if any node is a Temporal `FailureError`. `True` ⇒ the error already originated at a Temporal boundary (activity / child workflow), is already terminal, and its report is recoverable from the chain by `recover_error_report` at the submitter — so the catch-all leaves it untouched. `False` ⇒ a genuine inline error that never crossed a boundary — convert it via `TemporalError.from_message_exception`.

**Key fact established during review (why none of these is a live bug yet):** the real inline-leaf path, `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py`, dispatches activities and, on `ActivityError`, raises `TemporalError.from_app_error(exc=exc.cause) from exc` — a `FailureError`, wired with `from`. So `_carries_temporal_failure` classifies it correctly. Genuine inline errors (the Search-operator-missing-activity case, crate-load, hydration setup) carry no `FailureError` and are converted correctly.

> **Correction (this session).** The original review claimed "no confirmed live trigger" for the guard's `True` branch. That was wrong, and it reshaped Finding 1: the `True` branch **is** reachable — a controller sub-pipe failing as a child workflow is wrapped by `TemporalPipeRouter` (`temporal_pipe_router.py:92-94`) as `WorkflowExecutionError(msg)` and escapes the parent's `pipe.run_pipe`. So the guard is load-bearing on a real path, not just a latent safeguard. What *remains* latent are only the two **misclassification** fragilities below (under-/over-inclusive), each of which requires a `raise … from` discipline violation that no operator currently makes.

---

## ✅ Finding 1 — `_carries_temporal_failure` uses chain-membership as a proxy for "already terminal", which is fragile both ways

> **Resolved — kept the guard, not rewritten.** Both proposed directions regress the *reachable* nested-failure case (worker-side conversion flattens a report only the submitter can recover). The broad "carries a Temporal `FailureError`" predicate is correct — it *is* the definition of "already terminal" — and now sits on `iter_cause_chain` with a docstring stating the reachable case + the `raise … from` invariant. Pinned by the Finding 9 test. (Detail in the top summary.)

**Where:** `pipelex/temporal/tprl_pipe/wf_pipe_router.py:26` (the helper), `:195` (the guard call), `:197` (the conversion it gates).

**What:** the rule "any `FailureError` anywhere in the `__cause__` chain ⇒ propagate untouched" is a *proxy* for the real question, which is "is **this** error already a terminal, report-carrying Temporal failure?". The proxy is both over- and under-inclusive:

- **Under-inclusive (flattening).** A Temporal-failure-carrying error wrapped **without** `from` (implicit `__context__` only, not `__cause__`) reads as "no failure in chain" → the guard returns `False` → the already-classified error is re-converted by `from_message_exception`, flattening its rich leaf report (`model` / `provider` / `error_category`) to the wrapper's generic classification. Pipelex's coding standard is `raise … from exc`, so this requires a *missing* `from` somewhere on a workflow-inline path — the guard is silently fragile to that mistake.
- **Over-inclusive (misattribution).** A genuinely fresh inline error that is chained `from` an unrelated, *already-recovered* side failure (pipe code dispatches a side activity, it fails as a `TemporalError`, the code catches and recovers, then later raises a different fresh domain error `from` the recovered one) carries a `FailureError` in its chain → the guard returns `True` → it propagates untouched and carries **no report of its own**. At the submitter, `recover_error_report` walks the chain and surfaces the **side** failure's `error_type` / `error_category` / `model` — i.e. the run is reported as the wrong failure.

**Why it matters:** this guard is the hinge of the whole fix. The failure modes are latent today (see the key fact above), but a single missing `from`, or one operator that recovers-then-rechains, silently degrades the exact classification fidelity the error-handling project exists to deliver — and there is no test on the `True` branch to catch a regression (see Finding 9).

**Proposed direction:** replace the membership heuristic with a decision about *this* error's own terminality/recoverability. Options to weigh:

- Convert only when the error is **not itself** a `FailureError` *and* does not **directly** wrap one as its immediate `__cause__` (rather than anywhere in the chain) — tightens the over-inclusive case.
- Or: always convert (mint a fresh `TemporalError` from `exc`), but make `from_message_exception` *prefer an already-present report in the chain* over re-deriving — so flattening becomes impossible regardless of `from`/`__cause__` shape. This removes the guard's load-bearing role entirely and may be the deeper fix.

**Open questions:**

1. Do we tighten the predicate (direct-cause check) or eliminate it by making the conversion report-preserving (prefer the chain's existing report)?
2. Is "recover-then-rechain" a pattern we ever want in pipe/operator code, or should we forbid it (and lean on `from`-discipline + a lint)? That answer decides whether the over-inclusive case is worth engineering against at all.

---

## ✅ Finding 7 — `_carries_temporal_failure` is the 4th hand-rolled `__cause__`-chain walk

> **Resolved — done.** Extracted `iter_cause_chain(exc)` in `base_exceptions.py`; all five `__cause__` walks (the four named here + the cycle check in `_enrich_error_report_from_cause`) plus two unguarded strays found while sweeping (`agent_output._build_error_source`, `pipe_llm._format_llm_error` — both previously missing the cycle guard) now delegate to it.

**Where:** `pipelex/temporal/tprl_pipe/wf_pipe_router.py:26`. Siblings that re-implement the same walk: `find_inference_error_category_in_chain` (`pipelex/cogt/exceptions.py`, ~`:129`), `_find_error_report_dict` (`pipelex/temporal/tprl/temporal_error.py:41`), `_message_from_exc` (`.../temporal_error.py:68`).

**What:** all four are the identical loop — `node = exc; seen: set[int] = set(); while node is not None and id(node) not in seen: <predicate>; seen.add(id(node)); node = node.__cause__` — differing only in the per-node predicate. Each re-rolls the cycle guard (the `id()` set that prevents an infinite spin on a cyclic `__cause__` chain) by hand.

**Why it matters:** on the error-reporting path a cycle-guard bug would itself become a hang — the very failure the fail-safe exists to prevent. Four hand-copies mean a fifth will get it subtly wrong. This is pure reuse debt, but it sits on the most safety-critical path.

**Proposed fix:** extract one primitive — e.g. `find_first_in_cause_chain(exc, predicate) -> BaseException | None` (and/or `any_in_cause_chain`) — in `pipelex/base_exceptions.py` (or a small `pipelex/tools` exception util) with the cycle guard written once. Then:

- `_carries_temporal_failure(exc)` collapses to `any_in_cause_chain(exc, lambda n: isinstance(n, FailureError))`.
- `_find_error_report_dict`, `_message_from_exc`, `find_inference_error_category_in_chain` all delegate to it.

**Open question:** where does the primitive live so both `cogt/` and `temporal/` can import it without a layering inversion or circular import? `base_exceptions.py` is the natural home (it already defines `PipelexError` and a cycle-guarded `_enrich_error_report_from_cause` walk) — confirm that placement.

---

## ✅ Finding 6 — Two near-identical catch-alls were copy-pasted into two workflows; the worker-floor registration is the actual hole-closer (altitude)

> **Resolved — light touch.** Catch-alls kept separate (their control flow is irreducibly different: router raises immediately, parent defers so `act_deliver` fires the FAILED webhook). The duplicated *rationale prose* was deduped onto `_carries_temporal_failure`'s docstring (code contract) + `error-model.md` (design); the router / parent / worker-registration comments now carry a statement + pointer. No shared helper — that would have forced a dead guarded branch into `WfPipeRun` (followups Finding 4).

**Where:** the `except PipelexError` clause in `wf_pipe_router.py:174` and in `wf_pipe_run.py:83`; the registration in `temporal_task_manager.py:159`.

**What:** the single line `workflow_failure_exception_types=[…, PipelexError]` already closes the hang for **every** workflow, present and future, with zero per-workflow code — it guarantees an escaping `PipelexError` fails terminally instead of hanging. The two hand-written catch-alls only *upgrade the report* from a synthesized `UnrecoverableWorkflowFailureError` to the original classification. That richness is real and worth having, but it means:

- the actual hole-closer is one config line, while the design doc / CHANGELOG / three multi-paragraph inline comment blocks present the catch-alls as the headline fix;
- the "convert genuine inline error / leave already-terminal alone" decision is split across two ~20-line blocks that are implemented **divergently** — the router guards with `_carries_temporal_failure` and raises immediately; the parent omits the guard and defers via the delivery path (see Finding 4 in the followups doc);
- every future workflow author must remember to copy the clause to get the rich report.

**Why it matters:** maintenance weight and drift. A change to the conversion policy must be applied in N places, and the two existing copies already disagree.

**Proposed fix (right altitude):** hoist the policy into one shared helper, e.g. `convert_inline_pipelex_error(exc) -> TemporalError` that owns the `_carries_temporal_failure` short-circuit (or its Finding-1 replacement) and the `from_message_exception` conversion. Both workflows call it; each chooses only *immediate-raise* (router) vs *deferred-delivery* (parent). The policy then lives once, the guard becomes non-optional, and Finding 4's asymmetry disappears for free.

**Open questions:**

1. Is the per-workflow rich-report richness worth keeping at all, or do we accept the worker floor's synthesized `UnrecoverableWorkflowFailureError` and delete the catch-alls? (The floor already prevents the hang; the question is purely "rich classification vs less code".) Recommendation: keep the richness but centralize it.
2. If we keep it, should the shared helper be a plain function both sites call, or a workflow-root decorator/util applied uniformly to all `@workflow.defn` run methods so new workflows get it automatically?

---

## ✅ Finding 9 — The `_carries_temporal_failure` `True` branch is untested

> **Resolved — done.** Added `test_router_already_terminal_error_propagates_untouched_preserving_leaf_classification`. Proven meaningful: forcing the guard to `False` flips the submitter's `error_type` from the leaf `LLMCompletionError` to the generic `WorkflowExecutionError`, which the new test catches while the convert-branch sibling stays green.

**Where:** `tests/integration/pipelex/temporal/test_workflow_inline_error_failsafe.py`.

**What:** all three new tests inject errors with **no** `FailureError` in the chain (`make_failing_llm_error()` builds a clean `LLMCompletionError`; `WorkflowInputError` is raw). So they exercise only the `False` branch (convert). The `True` branch — "the error already carries a Temporal failure, do **not** re-wrap" — is the trickier, more error-prone arm and has **zero** coverage. Negate or delete the guard and the suite stays green.

**Why it matters:** the guard from Finding 1 is the fix's hinge, and its hardest branch is the one with no regression net. Combined with the retryable-inline gap (Finding 2 in the followups doc), the test suite currently pins the easy paths and leaves the subtle ones open.

**Proposed fix:** add a test that raises, inline in `WfPipeRouter`, a `PipelexError` whose `__cause__` chain already contains a report-carrying `TemporalError`/`ApplicationError` (simulating an already-terminal escapee), and assert it propagates **untouched** — i.e. the submitter recovers the *original* leaf classification, not a re-wrapped generic one. If Finding 1 is reworked to be report-preserving, this test should assert the preserved leaf report either way.

**Open question:** the new tests run **unsandboxed** (`is_not_sandboxed=True`), like the rest of the temporal suite. The catch-all now calls `from_message_exception` (→ `get_config()`, `find_inference_error_category_in_chain`, `ErrorReport.to_dict`, `workflow_log`) inside workflow code under the production `SandboxedWorkflowRunner` — a surface no test covers under the sandbox. Do we add one sandboxed smoke test for the conversion path, or is the existing unsandboxed coverage + the passthrough-module config (`temporal_task_manager.py` `with_passthrough_modules(...)`) sufficient assurance? (This is a pre-existing gap for the whole suite, not introduced here, but the floor is now one more untested-under-sandbox surface.)

---

## What was done (final sequencing)

All four landed as one unit of work:

1. **Finding 7** — extracted `iter_cause_chain` (a generator, not `find_first_in_cause_chain`: it also subsumes the accumulator walk `_message_from_exc` and the is-self cycle check, which a first-match primitive could not). Migrated all five named walks plus two unguarded strays.
2. **Finding 1** — *kept* the guard rather than rewriting it: verification showed the `True` branch is reachable and both proposed rewrites regress it. Refactored the predicate onto the primitive and documented the invariant.
3. **Finding 6** — light touch: deduped the rationale prose, kept the two catch-alls separate (no shared helper — see followups Finding 4's resolution).
4. **Finding 9** — added the `True`-branch test and proved it meaningful via a deliberate guard-regression check. The sandboxed-smoke open question (above) was left as the pre-existing suite-wide gap it is.
