# TODO — Fix: PipeLLM wrapping defeats the PipeRouter transient-retry loop

> **Status:** RESOLVED on branch `fix/llm-retry-loop-bypass` (branched off `feature/Error-handling-2`, not `main` — `main` does not carry the Phase 5 retry loop this fix depends on).
>
> **Decision:** Option B. The router's `except (CogtError, PipeRunError)` branch now derives the retry classification from `exc` itself when it is a `CogtError`, or from `exc.__cause__` when it is a `PipeRunError` (the operator wrap). On exhaustion a `PipeRunError` still wraps into `PipeRouterError`, preserving the pipe location context and keeping the Phase 8 full-chain test (`test_run_error_chain.py`) green. Option A (operators stop wrapping) was rejected because it would drop the `PipeRouterError` frame from the LLM error chain and force a rewrite of that Phase 8 test.
>
> **Coverage:** `tests/integration/pipelex/pipes/operator/test_operator_transient_retry.py` (real `PipeLLM` + `PipeStructure` through the router, worker mocked TRANSIENT) and a cause-chain case added to `tests/unit/pipelex/pipe_run/test_pipe_router_retry.py`.

> **Branch:** create a fresh branch off `main` (e.g. `fix/llm-retry-loop-bypass`).
> **Scope:** one focused change. Not a multi-phase plan.
> **Discipline:** RED (failing test) → GREEN (minimal fix) → REFACTOR. `make agent-check` after each step; `make agent-test` before wrapping up.

---

## ▶ Start here — cold-start context

The error-handling Phase-2 plan landed in full (archived at [wip/error-handling/archive-error-handling-2.md](wip/error-handling/archive-error-handling-2.md)). Phase 8 surfaced a **pre-existing resilience bug** that was deliberately scoped out of Phase 8 — this TODO is that follow-up.

**The bug.** Phase 5 added an application-level transient-retry loop to `PipeRouter`. `PipeRouterProtocol.run()` (`pipelex/pipe_run/pipe_router_protocol.py`, around line 66) retries on `except CogtError` when `error_category.is_retryable` is true (i.e. `InferenceErrorCategory.TRANSIENT`). But the LLM pipe operators **catch the worker's `LLMCompletionError` (a `CogtError`) and re-raise it as a plain `PipeRunError` before it ever reaches the router.** The router's `except PipeRunError` branch (around line 82) does *not* retry — it wraps into `PipeRouterError` and gives up. So:

- The router's `except CogtError` retry branch is **dead for the LLM path**.
- A `TRANSIENT` LLM failure (rate limit, timeout, brief outage) is **never retried in-process**, even though `max_transient_retries` defaults to 3.
- The Phase 5 CHANGELOG entry ("Application-level retry of transient inference failures — `PipeRouter` now retries failures classified as `TRANSIENT`") is **effectively false for the most common case**, an LLM call.

**Why the existing test misses it.** `tests/unit/pipelex/pipe_run/test_pipe_router_retry.py` mocks `_run_pipe_job` to raise a *raw* `CogtError` — which the real PipeLLM path never lets through. The test passes but does not reflect production.

---

## Verified facts (checked against the code)

**Operator wrapping sites that swallow the `CogtError` into a plain `PipeRunError`:**

- `pipelex/pipe_operators/llm/pipe_llm.py` — `except LLMCompletionError` → `raise PipeRunError(...) from exc` at **lines 251, 360, 377** (text-gen, object-list-direct, single-object-direct). Line 266 wraps a `ValidationError` the same way — *not* a `CogtError`, so out of scope for retry (a schema-validation failure is not transient).
- `pipelex/pipe_operators/structure/pipe_structure.py` — same pattern at **lines 166, 179** (object-list, single-object).

**Operator that does NOT wrap (the inconsistency):**

- `pipelex/pipe_operators/img_gen/pipe_img_gen.py` — does not appear to catch the worker's `ImgGenGenerationError`/`CogtError`; it only raises `PipeImgGenRunError` for a stuff-not-found case. So a transient *image-gen* error likely propagates as a raw `CogtError` and **is** retried by the router. Confirm this during investigation — it means LLM pipes and img-gen pipes currently behave differently, which is itself a bug.

**Router branches** (`pipe_router_protocol.py`, `run()`):

- `except CogtError` (~line 66): retry loop — consults `error_category.is_retryable`, sleeps with backoff, re-raises as-is on exhaustion.
- `except PipeRunError` (~line 82): no retry — wraps into `PipeRouterError`.

---

## The open design decision (settle this first)

Pick the exception contract before writing code:

- **Option A — operators let the `CogtError` propagate.** PipeLLM / PipeStructure stop converting `LLMCompletionError` into `PipeRunError`; they add context another way (e.g. attach the location to the message, or raise an `LLMCompletionError` subclass) and let the `CogtError` reach the router. Cleanest and most honest — the router then retries it and, on exhaustion, re-raises the `CogtError` as-is (Phase 5 already does this; it is *not* wrapped into `PipeRouterError`). `PipelexRunner`'s `except PipelexError` branch then wraps it into `PipelineExecutionError`. **Cost:** changes what exception type a caller of these operators sees; check every `except PipeRunError` that currently relies on the wrap.
- **Option B — the router inspects `__cause__`.** Keep the operator wrapping; in the `except PipeRunError` branch, if `exc.__cause__` is a retryable `CogtError`, retry instead of wrapping. More contained, no operator-contract change — but less honest (the router reaching into `__cause__` is a smell) and the retry decision logic gets duplicated/forked.

**Recommendation:** Option A — it makes the operator layer say what it means and keeps the router's retry decision in one place. But verify the blast radius of `except PipeRunError` callers first. Record the decision in the commit message / a short note here.

Whatever the choice, **apply it consistently** to PipeLLM *and* PipeStructure (and reconcile with PipeImgGen so all inference operators behave the same).

---

## RED

- [ ] Write a test that runs a real pipe operator (not a mocked `_run_pipe_job`) through `PipeRouter` with the LLM worker mocked to raise a `TRANSIENT` `LLMCompletionError`, and asserts the router **retries** `max_transient_retries` times before failing. Model it on the Phase 8 full-chain test `tests/integration/pipelex/cli/agent_cli/test_run_error_chain.py` (which already mocks `ContentGenerator.make_llm_text` to raise and runs a real `PipeLLM`). Mock `asyncio.sleep` (in the `pipe_router_protocol` module) so the backoff does not actually wait. This test fails today: the worker is called once, not `1 + max_transient_retries` times.
- [ ] Cover `PipeStructure` too (and `PipeImgGen` if the investigation shows it needs aligning).

## GREEN

- [ ] Apply the chosen option (A or B) so a `TRANSIENT` `CogtError` from an LLM operator reaches the router's retry path. Minimal change to make the RED test pass.
- [ ] Run `make agent-check`.

## REFACTOR

- [ ] Fix `tests/unit/pipelex/pipe_run/test_pipe_router_retry.py` so it is no longer misleading — either route it through a real operator, or add a comment that it intentionally tests the router in isolation and the operator-level coverage lives in the new test.
- [ ] Run `make agent-test`. Run the Temporal integration suite (`tests/integration/pipelex/temporal/`) — the Temporal retry path (Phase 6) consults the same `is_retryable` signal; confirm no regression.
- [ ] Update the CHANGELOG (`### Fixed`) — the transient-retry feature now actually fires for LLM pipes.
- [ ] Flip the "Known follow-up" note in [wip/error-handling/README.md](wip/error-handling/README.md) (retry & resilience track) to resolved.
- [ ] Archive this `TODOS.md` into `wip/error-handling/` if you want to keep the running notes.

---

## Out of scope

- `pipe_func.py` `PipeRunError` raises (lines 208/266/320/326) — these wrap *user-function* failures, not transient inference errors. A failing user function is not retryable; leave it.
- Workers not setting `model_handle` / `backend_name` on `LLMCompletionError` (so `ErrorReport.model`/`provider` come back `None` in production) — a separate, smaller follow-up noted in the Phase 8 archive notes. Not this task.
