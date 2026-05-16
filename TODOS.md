# TODOS — Wire `from_message_exception` into the Temporal activity boundary

> **Type:** TDD plan (RED → GREEN → REFACTOR), multi-phase with checkpoints.
> **Source:** Followup 5 of [wip/error-handling/track-temporal-integration.md](wip/error-handling/track-temporal-integration.md) and the stub [wip/error-handling/todos-temporal-activity-boundary.md](wip/error-handling/todos-temporal-activity-boundary.md).
> **Branch:** `fix/temporal-activity-error-boundary`.

---

## The gap

Phase 6 built `TemporalError.from_message_exception()` — category-aware retry decisions (`InferenceErrorCategory.is_retryable`) plus packing `to_error_report().to_dict()` into `ApplicationError.details`. **No activity calls it.** The activity functions in `pipelex/temporal/tprl_content_generation/act_*.py` and `pipelex/temporal/tprl_pipe/act_*.py` raise raw `CogtError` / `PipelexError`. Temporal's default failure converter auto-wraps them: it does not pack our `ErrorReport` into `details` and leaves `non_retryable=False`.

Net effect in production today:

- On the workflow side, `TemporalError.from_app_error()` always lands in its `error_report is None` fallback branch (`temporal_error.py:95`). The structured `ErrorReport` — `error_category`, `user_action`, `model`, `provider` — is lost.
- The category-aware retry decision (`_is_non_retryable`) never runs. A non-retryable `CogtError` (`CONFIGURATION`, `CONTENT`, `CAPACITY`) is treated as retryable unless its class name happens to be in the static `non_retryable_error_types` list — which `CogtError` is not.

Phase 6's logic is built but dead. This task wires it in.

This is the Temporal-side twin of the non-Temporal `PipeRouter` retry-bypass fixed in PR #903.

---

## Key files

- **Bridge (do not change — Phase 6 landed it):** `pipelex/temporal/tprl/temporal_error.py` — `from_message_exception` (line 109), `from_app_error` (line 82), `_is_non_retryable` (line 134).
- **Activity entry points to convert:**
  - `pipelex/temporal/tprl_content_generation/act_llm_generate.py` — `act_llm_gen_text`, `act_llm_gen_object`, `act_llm_gen_object_list`
  - `pipelex/temporal/tprl_content_generation/act_img_gen_generate.py` — `act_img_gen_images`
  - `pipelex/temporal/tprl_content_generation/act_extract_generate.py` — `act_extract_gen_extract_pages`
  - `pipelex/temporal/tprl_content_generation/act_jinja2_generate.py` — `act_jinja2_gen_text`
  - `pipelex/temporal/tprl_content_generation/act_render_page_views.py` — `act_render_page_views`
  - `pipelex/temporal/tprl_pipe/act_deliver.py` — `act_deliver`
  - `pipelex/temporal/tprl_pipe/act_flush_trace_events.py` — `act_flush_trace_events` (see Decision 2)
- **Workflow side (already calls `from_app_error`):** `content_generator_in_workflow.py` (nine call sites), `wf_pipe_router.py:135`.
- **Existing unit test:** `tests/unit/pipelex/temporal/test_temporal_error_bridge.py` — proves the bridge round-trips in isolation; never crosses a real activity → workflow boundary.
- **Failure-path integration test pattern to mirror:** `tests/integration/pipelex/temporal/test_wf_pipe_run_failure_path.py` — constructs a `Worker` directly, registers a stub workflow + activity, drives it through `temporal_client.execute_workflow`.
- **Retry config:** `pipelex/temporal/config_temporal.py` — `RetryPolicyConfig.non_retryable_error_types` / `non_retryable_error_types_extra` (name-based fallback).

---

## Phase 0 — Resolve design decisions (do this first, record the outcome here)

These must be settled before writing code. Each has a recommendation; confirm or override and write the decision back into this doc.

### Decision 1 — Per-activity `try/except` vs. shared decorator

**Option A — per-activity `try/except`.** Every `@activity.defn` function body wraps its call:

```python
@activity.defn
async def act_llm_gen_text(llm_assignment: LLMAssignment) -> str:
    log.dev("act_llm_gen_text")
    try:
        return await llm_gen_text(llm_assignment=llm_assignment)
    except PipelexError as exc:
        raise TemporalError.from_message_exception(exc=exc) from exc
```

- Pro: explicit, no decorator-ordering subtlety.
- Con: repeated in every activity; easy to forget on the next activity added; multi-statement activities (`act_render_page_views`, `act_img_gen_images`) need the whole body wrapped.

**Option B — shared decorator (RECOMMENDED).** A single `@convert_pipelex_errors` decorator applied beneath `@activity.defn`:

```python
@activity.defn
@convert_pipelex_errors
async def act_llm_gen_text(llm_assignment: LLMAssignment) -> str:
    log.dev("act_llm_gen_text")
    return await llm_gen_text(llm_assignment=llm_assignment)
```

- Pro: one conversion point; cannot be forgotten; the whole activity body is covered with no indentation churn.
- Con: decorator ordering matters — it must sit *below* `@activity.defn` so Temporal sees the wrapped function; the wrapper must use `functools.wraps` so `@activity.defn` still resolves the original name and signature (Temporal's `inspect.signature` follows `__wrapped__`).

**Recommendation: Option B.** New module `pipelex/temporal/tprl/activity_error_boundary.py` exposing `convert_pipelex_errors`. It catches `PipelexError` only (never `Exception` — the project bans the generic catch) and re-raises `TemporalError.from_message_exception(exc=exc) from exc`. A non-`PipelexError` propagates untouched and Temporal's default converter handles it as before.

> **DECISION:** Option B — shared decorator `convert_pipelex_errors` in `pipelex/temporal/tprl/activity_error_boundary.py`.

### Decision 2 — Which activities get the boundary

- `act_assemble_graph` (`tprl_pipe/act_assemble_graph.py`) **must NOT be wired.** It already wraps its body in `except Exception` (best-effort observability) and degrades to `return None` — it never propagates an error across the boundary. Converting it would be dead code. Leave it; note it explicitly so a future reader does not "fix" the omission.
- `act_flush_trace_events` (`tprl_pipe/act_flush_trace_events.py`) **does** propagate errors and is observability-only. **Recommendation: wire it** for consistency — a failed flush is a real error and should carry a structured report — but flag it as the lowest-value target. If the team prefers it stay best-effort, that is a separate decision (make it swallow like `act_assemble_graph`), out of scope here.

> **DECISION:** Wire `act_flush_trace_events`; leave `act_assemble_graph` unwired (it already swallows and degrades to `None`).

### Decision 3 — `from_message_exception` logs through `workflow_log` but runs activity-side

`from_message_exception` calls `cls._log_critical` / `cls._log_error`, which call `workflow_log.*` (`WorkflowLog` → `workflow.logger`). But `from_message_exception` runs **inside an activity**, not a workflow. `workflow.logger` outside a workflow context logs without workflow metadata (it does not crash — `workflow` runtime is simply absent), so it is not a hard bug, but it is semantically wrong and routes activity-side log lines through the workflow logger.

**Recommendation:** out of scope for the *wiring* but record it. Either (a) leave as-is and note it, or (b) small follow-up: make `_log_critical` / `_log_error` pick `activity_log` when `activity.in_activity()` is true, else `workflow_log`. Do **not** silently change Phase 6 bridge behavior inside this task without calling it out — the bridge unit test patches `_log_critical` / `_log_error` and would still pass, so the change is safe but should be deliberate.

> **DECISION:** Option (b) — fix it in this task. `_log_critical` / `_log_error` select `activity_log` when `activity.in_activity()`, else `workflow_log`. Done deliberately in **Phase 4**; the bridge unit test still passes (it patches both helpers). Add a unit test asserting the activity-context branch picks `activity_log`.

---

## Phase 1 — RED: failing integration test across a real activity → workflow boundary

Goal: a test that drives a **real activity** through a **real Temporal worker**, has the activity raise a real `CogtError`, and asserts what `from_app_error` receives on the workflow side. It must **fail today** (fallback branch) and **pass after Phase 2/3**.

### Files

- `tests/integration/pipelex/temporal/test_activity_error_boundary.py` — one `TestClass`, per the pytest standards.

### Test workflow + result model (defined in the test module)

A minimal probe workflow that executes one real activity, catches `ActivityError`, runs `from_app_error`, and **returns** the observed `non_retryable` + `error_report` (returns rather than re-raises, so the test can assert on the payload):

```python
class ErrorBoundaryProbeResult(BaseModel):
    non_retryable: bool
    error_report: dict[str, Any] | None

@workflow.defn(name="wf_error_boundary_probe")
class WfErrorBoundaryProbe:
    @workflow.run
    async def run(self, llm_assignment: LLMAssignment) -> ErrorBoundaryProbeResult:
        try:
            await workflow.execute_activity(
                act_llm_gen_text,
                arg=llm_assignment,
                start_to_close_timeout=timedelta(seconds=30),
                # maximum_attempts=1 so a (today wrongly) retryable error does
                # not loop and hang the test — we only care about the first hop.
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except ActivityError as exc:
            if isinstance(exc.cause, ApplicationError):
                temporal_error = TemporalError.from_app_error(exc=exc.cause)
                return ErrorBoundaryProbeResult(
                    non_retryable=temporal_error.non_retryable,
                    error_report=temporal_error.error_report,
                )
            raise
        raise AssertionError("activity was expected to fail")
```

### Making the real activity raise a real `CogtError`

The test worker runs **in-process** (same process as the test), so the activity's module-level reference can be patched. The activity imports `llm_gen_text` into its own module namespace — patch it there:

```python
mocker.patch(
    "pipelex.temporal.tprl_content_generation.act_llm_generate.llm_gen_text",
    side_effect=CogtError("simulated", error_category=InferenceErrorCategory.CONFIGURATION),
)
```

Use an `async` mock (`side_effect` on an `AsyncMock`, via `mocker.patch(..., new=mocker.AsyncMock(side_effect=...))`) so `await llm_gen_text(...)` works.

### Worker construction

Mirror `test_wf_pipe_run_failure_path.py`: build a `Worker` directly with a unique `task_queue`, register `WfErrorBoundaryProbe` and the real `act_llm_gen_text`, `workflow_runner=UnsandboxedWorkflowRunner()`. Drive it with `temporal_client.execute_workflow(...)` using a fresh `workflow_id`.

### Test cases (parametrized)

| Case | Activity raises | Expected `non_retryable` | Expected `error_report` |
|---|---|---|---|
| `configuration-non-retryable` | `CogtError(error_category=CONFIGURATION)` | `True` | populated, `error_category == CONFIGURATION` |
| `transient-retryable` | `CogtError(error_category=TRANSIENT)` | `False` | populated, `retryable is True` |
| `category-less-fallback` | `CogtError()` (no category) | `False` (name-list fallback, `CogtError` unlisted) | populated, `error_type == "CogtError"` |

Strong asserts: check the actual `error_report["error_category"]`, `error_report["retryable"]`, `error_report["error_type"]`, `error_report["message"]` — not just "is not None".

### Markers

`@pytest.mark.temporal`, `@pytest.mark.asyncio(loop_scope="class")`. No `inference`/`llm` marker — the LLM call is mocked away, never reaches a provider.

### Confirm RED

Run the new test against today's code:

```bash
.venv/bin/pytest tests/integration/pipelex/temporal/test_activity_error_boundary.py -q
```

Expected failure today: `error_report is None` (Temporal's default converter packed no `details`) and `non_retryable is False` even for the `CONFIGURATION` case (auto-wrap leaves `non_retryable=False`; `from_app_error`'s name-list fallback does not list `CogtError`). Record the exact failure output here, then proceed.

> **CHECKPOINT 1 — RED confirmed.** ✅ Test `tests/integration/pipelex/temporal/test_activity_error_boundary.py` written and committed. All 3 parametrized cases fail for the documented reason — the workflow side observed `ErrorBoundaryProbeResult: non_retryable=False error_report=None` (log line `Error from ApplicationError[CogtError]: ...` confirms `from_app_error` hit the name-list fallback). The test asserts `error_report is not None` (fails) and, for `configuration-non-retryable`, `non_retryable is True` (fails — got `False`). The worker → activity → workflow boundary mechanics all work; `make agent-check` clean. Phase 0 decisions recorded above. Next session: Phase 2.

---

## Phase 2 — GREEN (minimal): wire one activity, make the test pass

Implement the decision from Phase 0. For Option B (recommended):

### Step 2.1 — `convert_pipelex_errors` decorator

New file `pipelex/temporal/tprl/activity_error_boundary.py`:

- `convert_pipelex_errors` — wraps an `async` activity function with `functools.wraps`. Body: `try: return await func(*args, **kwargs)` / `except PipelexError as exc: raise TemporalError.from_message_exception(exc=exc) from exc`.
- Typing: parametrize with a `ParamSpec` and return `TypeVar` so the wrapped signature is preserved for the type checker and for Temporal's signature inspection. (`ParamSpec` is available on 3.10 via `typing` — fine.)
- Catch `PipelexError` only. Never `except Exception` — see CLAUDE.md error-handling rules. A non-`PipelexError` propagates unchanged.
- No speculative handling: the decorator only converts; it does not log, swallow, or add fallbacks.

### Step 2.2 — Apply to `act_llm_gen_text` only

Add `@convert_pipelex_errors` beneath `@activity.defn` on `act_llm_gen_text`. Leave the other activities for Phase 3 — Phase 2 is the minimal change that turns the test green for the one activity the probe exercises.

### Step 2.3 — Verify GREEN

```bash
.venv/bin/pytest tests/integration/pipelex/temporal/test_activity_error_boundary.py -q
make agent-check
```

All three Phase 1 cases must pass: `CONFIGURATION` → `non_retryable True` + populated report; `TRANSIENT` → `non_retryable False`; category-less → `non_retryable False` + report present.

> **CHECKPOINT 2 — GREEN for one activity.** The bridge is proven live across a real worker boundary. The mechanism is settled. Phase 3 is mechanical replication. Commit here.

---

## Phase 3 — Wire the remaining activities

Apply the same decorator (or per-activity `try/except`, per Decision 1) to every remaining in-scope activity:

- [ ] `act_llm_gen_object`, `act_llm_gen_object_list` (`act_llm_generate.py`)
- [ ] `act_img_gen_images` (`act_img_gen_generate.py`)
- [ ] `act_extract_gen_extract_pages` (`act_extract_generate.py`)
- [ ] `act_jinja2_gen_text` (`act_jinja2_generate.py`)
- [ ] `act_render_page_views` (`act_render_page_views.py`)
- [ ] `act_deliver` (`act_deliver.py`)
- [ ] `act_flush_trace_events` (`act_flush_trace_events.py`) — per Decision 2
- [ ] `act_assemble_graph` — **deliberately NOT wired** (Decision 2). Add a one-line comment in the file stating why, so the omission reads as intentional.

### Extend the integration test

Add at least one more probe workflow + case covering a non-LLM activity — `act_img_gen_images` or `act_extract_gen_extract_pages` — patching its inner generate function to raise a `CogtError`. This proves the wiring is not LLM-specific. Keep it in the same `TestClass` (one class per module); add a second probe workflow class at module scope and a parametrized case, or a second test method.

Also confirm no double-wrapping: `content_generator_in_workflow.py` and `wf_pipe_router.py` already call `from_app_error` on the workflow side — that is the *receiving* end and is correct. The activity side had no conversion before; there is nothing to un-wrap. Verify no activity already has a competing `try/except` that would convert differently.

### Verify

```bash
.venv/bin/pytest tests/integration/pipelex/temporal/test_activity_error_boundary.py tests/unit/pipelex/temporal/test_temporal_error_bridge.py -q
make agent-check
```

---

## Phase 4 — REFACTOR + docs

- Re-read the decorator and the wired activities for consistency: decorator order identical everywhere (`@activity.defn` above `@convert_pipelex_errors`), no stray imports, `make fix-unused-imports` clean.
- Docstring on `convert_pipelex_errors`: state that it is the activity-side half of the bridge whose workflow-side half is `from_app_error`, and that it catches `PipelexError` (not `Exception`) by design.
- If Decision 3 was taken (b), apply the `activity_log` / `workflow_log` selection and note it in the changelog.
- `CHANGELOG.md` — under `[Unreleased]` (per project memory: never add a versioned header on a work branch), add an entry: Temporal activities now convert `PipelexError` to a category-aware `TemporalError` at their boundary, so retry decisions and the structured `ErrorReport` survive into workflow code.
- Update [wip/error-handling/track-temporal-integration.md](wip/error-handling/track-temporal-integration.md): mark Followup 5 as landed. Delete or mark done the stub [wip/error-handling/todos-temporal-activity-boundary.md](wip/error-handling/todos-temporal-activity-boundary.md).

---

## Phase 5 — Full verification

- [ ] `make agent-check` — clean.
- [ ] `make agent-test` — full suite (this touches `pipelex/temporal/` broadly; the targeted run is `tests/unit/pipelex/temporal/ tests/integration/pipelex/temporal/`, but run the full suite before wrapping up per `_tprl/CLAUDE.md`).
- [ ] Optionally, against a real server: `.venv/bin/pytest tests/integration/pipelex/temporal/test_activity_error_boundary.py --temporal-server local` — confirms cross-process serialization (the in-process test server already exercises the real failure converter, so this is a confidence check, not strictly required).
- [ ] Watch for zombie Temporal processes if a run stalls (project memory `feedback_test_timeouts`).

---

## Out of scope

- Changing the bridge methods `from_message_exception` / `from_app_error` themselves — Phase 6 landed them; only the wiring is missing. (Decision 3 is the one allowed, deliberate, called-out exception.)
- The non-Temporal `PipeRouter` retry path — that is PR #903.
- Making `act_assemble_graph` propagate errors — it is intentionally best-effort.
- Extending `error_category` to non-`CogtError` `PipelexError` subclasses — that is [wip/error-handling/track-metadata-model.md](wip/error-handling/track-metadata-model.md); the name-list fallback covers them until then.

---

## Risks / gotchas

- **Decorator order.** `@convert_pipelex_errors` must be *below* `@activity.defn`. If placed above, Temporal registers the wrapper and `from_message_exception` never runs. `functools.wraps` is mandatory so Temporal resolves the activity name and argument types.
- **Async mock.** The inner generate functions are `async`; patch with an async-capable mock or `await` fails before the `CogtError` is raised.
- **Patch target.** Activities do `from pipelex.cogt... import llm_gen_text` — patch the *activity module's* name, not the source module's.
- **Retry loop hang.** Without `maximum_attempts=1` on the probe's activity retry policy, a `TRANSIENT` (retryable) case retries until timeout and the test hangs. Always pin it.
- **`non_retryable` is the inverse of `is_retryable`.** `ApplicationError(non_retryable=True)` ⇔ `category.is_retryable is False`. The bridge already handles this (`temporal_error.py:137`); just keep it straight when writing assertions.
