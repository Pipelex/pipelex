# Follow-up — Run-outcome seam (the validator consumes the run's outcome, not its raised exception)

> **Status: deferred — own branch, not yet started. OPTIONAL tightening, not a bug.** Implements the deferred half of **D-plan [`D-plan.md`](./D-plan.md) D6**. Unlike the leaf-mock and Temporal-activity follow-ups, this is **not** tied to a user requirement — it's a seam cleanup. Only pursue if the seam smell is judged worth the cross-backend churn.
>
> **Design rationale:** D-plan **D6** (the three-altitude model: L1 run primitive / L2 batch policy / L3 presentation). **Depends on:** the consolidation ([`consolidation-as-built.md`](./consolidation-as-built.md)) has landed (`BundleValidator`, `PipeRun`). Backend symmetry means touching `WfPipeRun` too. **Branch off the same D-plan.**

## What and why

Today the run primitive **discards** the classification it already computes: `PipeRun.run` catches the failure (`pipe_run.py:43`), builds a structured `ErrorReport` for the FAILED-delivery webhook (`pipe_run.py:51-54`), then **re-raises the raw exception** (`pipe_run.py:99-100`). The Temporal run is symmetric — `WfPipeRun` recovers the same `ErrorReport` via `recover_error_report`.

Because the run re-raises raw, `BundleValidator._classify_pipe` wraps the run in a **second** `try/except (PipelexError, ValidationError, FactoryException)` and re-derives the classification by walking the `__cause__`/`__context__` chain (`_root_cause_is`, `bundle_validator.py:272-295`, `:335-353`). Two `try/except` around one execution, the second reverse-engineering what the first already had.

**Goal:** give the run an outcome-**returning** sibling so the validator consumes a typed outcome and does pure L2 policy with **zero** execution `try/except`. The strict `run()` contract stays untouched — `PipelexRunner.execute_pipeline` keeps raising `PipelineExecutionError` on failure (it just raises on the failed-outcome variant).

**Explicitly NOT this:** moving `SKIPPED` / `allowed_to_fail` / aggregation / the signature pre-pass into the run. Those are irreducible **batch policy** (L2) — moving them down recreates the god-object D1 rejected, and `SKIPPED` would corrupt the strict LIVE contract (a LIVE run with a missing cross-package dep *must* hard-fail). See D6.

## Bounded payoff — read before committing

- `ErrorReport` is **wrapper-wins** and **collapses the cause chain** (`base_exceptions.py:459-534`): a `PipeRunError` wrapping a `PipeNotFoundError` reports `error_type="PipeRunError"`, so the not-found identity is **lost** on the report. The validator's `SKIPPED` rule needs "`PipeNotFoundError` *anywhere* in the chain" — which only the **raw exception chain** carries. So the outcome must hand back the **raw exception** (not just the `ErrorReport`); consuming the report alone would *not* let the validator drop the `_root_cause_is` walk. This is the crux: the win is "one catch instead of two", **not** "no chain walk".
- Cross-backend surface: `PipeRunProtocol` + `PipeRun` + `WfPipeRun` all change. Touches the freshly-hardened signature path (`36914511` / `76b96992`) — re-run the signature e2e.

## Status at a glance

| Phase | Title | Status | Commit |
|---|---|---|---|
| | **⛔ HUMAN GATE — is this worth doing?** | | |
| R0 | Decide the outcome type + method shape (pre-flight) | ☐ not started | |
| R1 | `PipeRun.run_to_outcome` (direct) + `run()` becomes raise-on-failed-outcome | ☐ | |
| R2 | `WfPipeRun` parity (Temporal) | ☐ | |
| R3 | Migrate `BundleValidator._classify_pipe` to consume the outcome | ☐ | |
| | **⛔ CHECKPOINT — seam tightened, suite green** | | |

Status legend: ☐ not started · ◐ in progress · ☑ done.

## Pre-flight — needs human input

Resolve **before** R1. Record in the R0 Handoff.

- [ ] **(GATE) Is the cleanup worth the cross-backend churn?** This is a design-tradeoff, not a bug — the current chain-walk is correct and well-tested. Default if unanswered: **leave it** (do not start; the seam smell is documented in D6 and that may be enough).
- [ ] **(before R1) Outcome type shape.** A small result type — e.g. `PipeRunOutcome = PipeOutput | PipeRunFailure(raw_exc, error_report)`. Confirm it carries the **raw exception** (required for the `SKIPPED` chain-walk — see "Bounded payoff"). Default: carry both the raw exception and the `ErrorReport`.
- [ ] **(before R1) Method shape.** New sibling `run_to_outcome(...)` on `PipeRunProtocol` (recommended — keeps the strict `run()` contract for `execute_pipeline` untouched) vs change `run()` to return the union and make `execute_pipeline` raise on the failed variant (higher blast radius). Default: **new sibling**.

> ### ⛔ HUMAN GATE — before R0 — **STOP, confirm intent**
>
> This follow-up is optional. Do not start R1 until the GATE pre-flight item is answered. If the answer is "leave it", close this tracker as *won't-do (documented in D6)* and stop.

## Phase R0 — Decide the outcome type + method shape

- [ ] Confirm the two pre-flight answers (outcome shape carries the raw exception; sibling method vs union return).
- [ ] Sketch the `PipeRunOutcome` / `PipeRunFailure` type next to `PipeRun` (a `pydantic dataclass` or small `BaseModel` — pick the lowest-churn correct form per the off-wire-shape rule; it stays in-process for validation, so no Temporal serialization constraint unless it ever crosses an activity boundary).

## Phase R1 — `PipeRun.run_to_outcome` (direct)

- [ ] *Tests first:* `run_to_outcome` returns the `PipeOutput` variant on success and the `PipeRunFailure` variant (carrying the raw exception + `ErrorReport`) on failure — **without raising**; delivery/tracer side effects still fire exactly as in `run()`.
- [ ] Factor the existing sole `except Exception` (`pipe_run.py:43`) so the failure path can **return** the outcome. Re-express `run()` as a thin wrapper: call `run_to_outcome`, raise the carried exception on the failed variant (preserves the strict contract `execute_pipeline` depends on).
- [ ] `make agent-check` + targeted `pipe_run` / runner suites green. No behavior change for `execute_pipeline`.

## Phase R2 — `WfPipeRun` parity (Temporal)

- [ ] Mirror the sibling on `WfPipeRun` (the Temporal run already builds the total `ErrorReport` via `recover_error_report` — surface it on the same outcome type). Keeps "a run is a run" backend-symmetric.
- [ ] Temporal integration tests green (the run path is exercised by the crate / e2e suites).

## Phase R3 — Migrate `BundleValidator._classify_pipe`

- [ ] *Tests first:* the existing `BundleValidator` classification tests (`tests/unit/pipelex/pipeline/test_bundle_validator.py` — SKIPPED via wrapped cause, widening, collect-all) stay green against the new consume-the-outcome shape.
- [ ] Replace the `try: await self._pipe_run.run(pipe_job) except (...)` with `outcome = await self._pipe_run.run_to_outcome(pipe_job)`; classify off the outcome. **Keep** `_root_cause_is` — now applied to `outcome.raw_exc` (still needed; `ErrorReport` collapses the chain). **Keep** L2 policy (allowed_to_fail, aggregation, signature pre-pass) exactly where it is.
- [ ] Keep the `prepare_pipe_job` call in its own narrow try if it can raise before the run (mock-input build) — that is a *job-build* failure, distinct from a *run* failure; classify both, but don't conflate them under one broad catch.
- [ ] Re-run the signature e2e (`tests/e2e/test_signature_validation_mthds.py`) + `tests/integration/pipelex/pipe_signature/*`.

> ### ⛔ CHECKPOINT — after R3 — **MANDATORY STOP**
>
> The validator no longer wraps execution in its own `try/except`; the run owns the single catch and hands back a typed outcome. L2 policy unchanged.
>
> **Verify:** `make agent-check` clean · `make agent-test` green · signature e2e green · commit.
>
> **Handoff (fill in):** final `PipeRunOutcome` / `PipeRunFailure` shape; `run_to_outcome` signature on `PipeRunProtocol`; confirm `execute_pipeline` behavior identical.
