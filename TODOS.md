# TODOS

## [done] Recover the structured error report across the Temporal submitter boundary

**Status:** done (landed 2026-05-17 on `feature/Temporal-error-report`) · **Filed:** 2026-05-17 · **Severity:** medium — correctness degradation under distributed execution; no crash, graceful fallback to a generic error.
**Area:** error handling — Temporal integration; the symptom surfaces in CLI delivery.
**Tracks:** primary home is `wip/error-handling/track-temporal-integration.md` (Open gaps); cross-referenced from `wip/error-handling/track-cli-delivery.md`. Context on the activity-side half of the bridge: `wip/error-handling/archive-temporal-activity-boundary.md` (the #911 work).

### TL;DR

When a pipe fails inside a Temporal worker, the structured `ErrorReport` (`error_category`, `retryable`, `model`, `provider`, specific `user_action`, `provider_metadata`) is correctly carried across the activity → workflow boundary but is dropped on the workflow → submitter → CLI hop. The agent — and any HTTP adapter — receives a generic `PipelineExecutionError` with message `"Failed to execute workflow WfPipeRun"` and no classification, where the same pipe failing locally yields a fully classified error. The rich report is not lost: it survives intact inside `ApplicationError.details` on the deserialized failure that reaches the submitter. The fix is to recover it there, so the existing "delivery consumes `to_error_report()`" contract keeps holding for distributed runs.

### Symptom

Run an agent-CLI pipe command (`pipelex-agent run pipe|bundle|method`) with Temporal enabled (`temporal.is_enabled = true` in config, or the `--temporal` flag), against a pipe that fails on a worker — an LLM rate limit, an unavailable model, any `CogtError`. The error payload the agent receives:

```json
{
  "error": true,
  "error_type": "PipelineExecutionError",
  "message": "Failed to execute workflow WfPipeRun",
  "error_domain": "runtime",
  "pipe_code": "<the pipe>",
  "cause_type": "WorkflowExecutionError",
  "cause_message": "Failed to execute workflow WfPipeRun"
}
```

The identical pipe failing in local (non-Temporal) execution yields `error_category`, `retryable`, `model`, `provider`, a specific `user_action`/hint, and the real failure message. Distributed execution silently produces a strictly worse error — exactly when the operator has the least visibility into the worker.

### Impact / blast radius

The defect is in shared `ErrorReport` production, not in any one renderer, so it affects every `to_error_report()` / `ErrorReport` consumer once execution is distributed:

- **Agent CLI** (`pipelex-agent`) — JSON and markdown error payloads lose hint, domain, category, retryable, model, provider. This is the concretely traced path. Affects all of `run pipe`, `run bundle`, `run method` (they share `run_pipeline_core` → `PipelexRunner`).
- **Human Rich CLI** (`pipelex`) — the per-error-type handlers in `pipelex/cli/error_handlers.py` render off the same exceptions; a Temporal-run failure shows as a generic panel.
- **HTTP API adapters** (`pipelex-relay`, `pipelex-back-office`) — `ErrorReport.http_status` drives the status code. A provider 429 raised on a worker collapses to a generic `RUNTIME` → 500, and the `Retry-After` header (sourced from `provider_metadata.retry_after_seconds`) is lost, because `provider_metadata` never makes it into the submitter-side report.

Not affected: the `_agent_cli_output_format` `ContextVar`. See "What is NOT the bug" below.

### Full trace

#### Local execution — works

1. A pipe operator raises a `CogtError` (e.g. `LLMCompletionError`), carrying `error_category` / `model` / `provider`.
2. It is wrapped on the way up: `PipeRunError` → `PipeRouterError` — all `PipelexError` instances, all live Python objects in the `__cause__` chain.
3. `PipelexRunner.execute_pipeline` catches `PipeRouterError` (`pipelex/pipeline/runner.py:154`) and raises `PipelineExecutionError(message=exc.message, ...) from exc`.
4. The agent CLI catches `PipelineExecutionError` (`pipelex/cli/agent_cli/commands/run/pipe_cmd.py:155`) and calls `agent_error(exc.message, "PipelineExecutionError", cause=exc, ...)`.
5. `agent_error` → `_assemble_error_payload` (`pipelex/cli/agent_cli/commands/agent_output.py:192-202`) calls `cause.to_error_report()`. `PipelineExecutionError.to_error_report()` → `PipelexError._enrich_error_report_from_cause` walks the `__cause__` chain, every link is a `PipelexError`, reaches the `CogtError`, and inherits its full classification. **Rich payload.**

#### Temporal execution — broken

1. A pipe operator raises the same `CogtError`, but **inside a Temporal activity**.
2. `convert_pipelex_errors` (`pipelex/temporal/tprl/activity_error_boundary.py:52`) wraps it as `TemporalError.from_message_exception(exc)` — a `TemporalError` (subclass of `temporalio.exceptions.ApplicationError`) with `to_error_report().to_dict()` packed into `ApplicationError.details` and `non_retryable` derived from the inference category.
3. Temporal serializes the failure (default failure converter — see the `activity_error_boundary.py` module docstring for why the `details` packing exists). Workflow code re-wraps via `TemporalError.from_app_error` (`pipelex/temporal/tprl_pipe/wf_pipe_router.py:135`). The workflow fails.
4. **Submitter side:** `WorkflowExecutor.execute_workflow` (`pipelex/temporal/tprl/workflow_caller.py:90`) — `client.execute_workflow` raises `WorkflowFailureError`, whose `.cause` is the deserialized `ApplicationError` still carrying `.details` (the report dict). The `except` at `workflow_caller.py:122` discards all of that: `raise WorkflowExecutionError("Failed to execute workflow WfPipeRun") from exc`.
5. `WorkflowExecutionError` (`pipelex/temporal/exceptions.py:12`, a `TemporalFlowError` → `PipelexError`) has no class-level `error_domain` / `user_action`. Its `__cause__` is `WorkflowFailureError` — **not** a `PipelexError`.
6. `TemporalPipeRun.run` (`pipelex/temporal/tprl_pipe/temporal_pipe_run.py:49`) has no try/except — `WorkflowExecutionError` propagates straight through.
7. `PipelexRunner.execute_pipeline` catches it at the `except PipelexError` arm (`pipelex/pipeline/runner.py:172`) and raises `PipelineExecutionError(message=exc.message, ...) from exc` — `exc.message` is `"Failed to execute workflow WfPipeRun"`.
8. The agent CLI catches `PipelineExecutionError` and calls `agent_error(...)` as in the local case.
9. `to_error_report()` → `_enrich_error_report_from_cause` walks: `PipelineExecutionError.__cause__` = `WorkflowExecutionError` (a `PipelexError` ✓, but empty) → `WorkflowExecutionError.__cause__` = `WorkflowFailureError` (**✗ not a `PipelexError`**). The walk stops. Report floors to generic `RUNTIME` / `UNKNOWN`. **Degraded payload.**

### Root cause

`PipelexError._enrich_error_report_from_cause` in `pipelex/base_exceptions.py:127`:

```python
cause = self.__cause__
if not isinstance(cause, PipelexError):
    return report          # <-- base_exceptions.py:137-138
```

The chain-enrichment that makes wrapper exceptions inherit classification operates purely on **live `PipelexError` objects linked via `__cause__`**. Temporal serialization breaks that precondition: it destroys the original `CogtError` Python object and replaces it with a `temporalio` `ApplicationError` (not a `PipelexError`), inserting a `WorkflowFailureError` link in between. The walk terminates at that link. The data the walk wanted is intact but is now inert dict data in `ApplicationError.details`, a representation `_enrich_error_report_from_cause` knows nothing about.

`ErrorReport` is explicitly the single source of truth "used by CLI JSON output, agent output, and Temporal error details" (`base_exceptions.py:56-59`). The activity → workflow half of the bridge already moves it through `ApplicationError.details`; the missing half is recovering it from `details` once back on the submitter, so it re-enters the `to_error_report()` world.

### What is NOT the bug

The `_agent_cli_output_format` `ContextVar` (`pipelex/cli/agent_cli/commands/agent_output.py:33`) is sound and needs no change. It is set by `set_agent_cli_output_format()` at the top of each command (`run/pipe_cmd.py:73`, etc.) and read by `agent_error` / `agent_success_formatted` after the pipe call returns — all within the **same submitter/CLI process, same root async context**. Temporal distributes pipe *execution* to worker processes; it never distributes CLI *rendering*. Workers never import `agent_output.py` and never read this ContextVar, so there is nothing to propagate across the Temporal boundary. Do not spend time "fixing" the ContextVar — the gap is the report data, not the format plumbing. (This was the original question that surfaced the real bug; recorded here so a cold start does not re-investigate it.)

### Fix

#### Option A — recover the report at the submitter boundary (recommended)

Repair the data at its source so every downstream consumer (agent CLI, Rich CLI, HTTP adapters) is fixed at once, and `pipelex/cli/agent_cli/` stays Temporal-agnostic.

1. **Add `ErrorReport.from_dict`** in `pipelex/base_exceptions.py` — the inverse of the existing `to_dict` (`base_exceptions.py:71`). Mirror it: `TypeAdapter(cls).validate_python(data)`. Verify the nested `UserAction` and `ProviderErrorMetadata` round-trip cleanly (they are dumped with `mode="python", exclude_none=True`). Keep it **strict** — `ErrorReport` is `extra="forbid"`, so `from_dict` raises `pydantic.ValidationError` on a malformed or schema-drifted dict. That is the correct behavior for a pure inverse; robustness against that failure lives at the recovery call site (step 2a), not inside `from_dict`.
2. **Recover the report at `WorkflowExecutor.execute_workflow`** (`pipelex/temporal/tprl/workflow_caller.py:122`). Split the combined `except (WorkflowAlreadyStartedError, RPCError, WorkflowFailureError)` handler into a **dedicated `except WorkflowFailureError as exc:` clause** (report recovery) plus a combined `except (WorkflowAlreadyStartedError, RPCError) as exc:` clause (generic, `error_report=None`) — the two failure kinds get genuinely different handling, so they get separate clauses rather than an `isinstance` branch. In the `WorkflowFailureError` clause, walk its `.cause` / `__cause__` chain for an `ApplicationError` whose `.details` matches the report shape and rebuild an `ErrorReport`. Reuse the existing detection helper — **rename `_error_report_from_details` (`temporal_error.py:14`) to a public name** (e.g. `error_report_dict_from_details`), since it now has callers in two modules, and update its existing `from_app_error` caller.
2a. **Guard the recovery against bad data.** `from_dict` is strict, so a malformed or version-skewed `details` dict makes it raise `ValidationError` — and this runs on the submitter's error path, so an unguarded raise turns a degraded-but-classified error into a hard crash. At the recovery call site, catch `ValidationError` and fall back to today's generic `WorkflowExecutionError` (`error_report=None`). Additionally, drop unknown keys from the recovered dict before calling `from_dict`, so a report serialized by a *newer* Pipelex worker (extra field) degrades silently — mirroring how `error_domain_to_http_status` / `ErrorReport.http_status` already tolerate an unrecognized `error_domain`. Worker/submitter version skew is normal during a rolling deploy.
3. **Carry the recovered report on `WorkflowExecutionError`** — *design decision: option (a), see "Resolved design decision" below.* Give it an optional `error_report: ErrorReport | None` constructor arg + attribute, and override `to_error_report()` to return / enrich from the recovered report when present. When `error_report` is `None`, the override must fall through to base behavior — build the wrapper report and end with `self._enrich_error_report_from_cause(report)` per the contract in `base_exceptions.py:117`. The `WorkflowAlreadyStartedError` / `RPCError` clause passes `error_report=None`, so its behavior is unchanged.
4. **Propagate the real message.** Construct the `WorkflowExecutionError` with the original failure message (from the recovered `ErrorReport.message`, or equivalently `ApplicationError.message`), not the generic `"Failed to execute workflow WfPipeRun"`. `PipelineExecutionError(message=exc.message, ...)` copies the wrapper message upward, so without this the agent still sees the generic message even after classification is restored — local execution propagates the real message, and Temporal should match.
5. No change needed in `PipelexRunner` or `agent_output.py`: once `WorkflowExecutionError.to_error_report()` returns a populated report, `PipelineExecutionError._enrich_error_report_from_cause` inherits it natively (`WorkflowExecutionError` is a `PipelexError`, so the existing walk includes it).

**Resolved design decision (eng review 2026-05-17):** `WorkflowExecutionError` holds the `ErrorReport` as an optional attribute and overrides `to_error_report()` — option (a). Rejected (b) (a `RemotePipelexError` carrier in the `__cause__` chain): although (b) needs no override, it forces a new public exception class plus manual `__cause__` wiring to keep the Temporal `WorkflowFailureError` in the traceback, whereas (a) keeps `raise WorkflowExecutionError(msg) from exc` so the Temporal failure stays in the chain for free, and the override is the same 3-line pattern `PipelineExecutionError.to_error_report()` already uses. Mirror this decision into `wip/error-handling/track-cli-delivery.md`.

#### Option B — read `ApplicationError.details` in the delivery layer

Make `_assemble_error_payload` (`pipelex/cli/agent_cli/commands/agent_output.py:171`) walk `cause.__cause__` for an `ApplicationError` with a details-packed report and prefer it over the outer exception's `to_error_report()`.

Rejected as the primary fix: it pulls a `temporalio` dependency and Temporal-shape knowledge into the CLI delivery layer, duplicates `_error_report_from_details`, and fixes only the agent CLI — the Rich CLI and the HTTP adapters would still see the degraded report. Keep it in mind only as a fallback if Option A proves infeasible.

### Implementation checklist

- [x] `ErrorReport.from_dict` added (strict inverse of `to_dict`) and unit-tested for round-trip, including nested `UserAction` / `ProviderErrorMetadata` and a `provider_metadata` 429.
- [x] `_error_report_from_details` renamed to `error_report_dict_from_details` and reused (not duplicated) on the submitter side; existing `from_app_error` caller updated.
- [x] `execute_workflow`'s combined `except` split into a dedicated `except WorkflowFailureError` clause + a combined `except (WorkflowAlreadyStartedError, RPCError)` clause.
- [x] Recovery guarded: a `ValidationError` from `from_dict` falls back to a generic `WorkflowExecutionError`; unknown keys dropped before validating (version-skew tolerance).
- [x] `WorkflowExecutionError` carries and exposes the recovered report via option (a) — attribute + `to_error_report()` override that falls through to base `_enrich_error_report_from_cause` when no report is present; the no-report arms left intact.
- [x] Real failure message propagated (Option A step 4).
- [x] Decision (a)/(b) recorded — done in this doc ("Resolved design decision") and mirrored into `wip/error-handling/track-cli-delivery.md`.
- [x] `track-temporal-integration.md` "Open gaps" updated to reflect the fix; this `TODOS.md` entry marked `[done]`.
- [x] Run `make agent-check` and `make agent-test`.

### Testing

- **Unit (submitter recovery):** feed `execute_workflow`'s error path a synthetic `WorkflowFailureError` whose `.cause` is an `ApplicationError` with a details-packed report dict; assert the resulting `WorkflowExecutionError.to_error_report()` carries `error_category` / `retryable` / `model` / `provider` / `user_action` and the real message. Use `pytest-mock`, one `TestClass` per module (see `_tprl/CLAUDE.md`).
- **Integration (full chain):** *(landed)* `tests/integration/pipelex/temporal/test_workflow_error_report_full_chain.py` runs a real `WfPipeRouter` workflow on the in-process Temporal server through `WorkflowExecutor.execute_workflow`, with the LLM call mocked to fail — exercising the genuine activity → workflow → submitter serialization round-trip — and asserts the recovered `WorkflowExecutionError.to_error_report()` carries `error_category` / `retryable` / `model` / `provider` / `user_action` and the real message.
- **Regression parity:** *(landed)* the local arm `tests/integration/pipelex/error_handling/test_error_report_local_full_chain.py` runs the same failing pipe through the local `PipeRouter`. Both arms assert the shared `ErrorReportParityTestData` constants, so local/Temporal `ErrorReport` parity holds by construction. Recorded in `wip/error-handling/track-testing.md` ("Temporal boundary").
- **Edge & error coverage (added by eng review 2026-05-17):**
    - **G1** — `from_dict` raises `ValidationError` on a malformed / missing-required dict (asserts the strict-inverse contract).
    - **G2** — a version-skewed dict carrying an unknown extra key is accepted: the key is dropped, `from_dict` validates the rest.
    - **G3** — *(tests the recovery guard, step 2a)* a `WorkflowFailureError` whose recovered `details` fail validation falls back to a generic `WorkflowExecutionError` with no submitter crash.
    - **G4** — a `WorkflowFailureError` whose `.cause` `ApplicationError` carries no report `details` yields a generic `WorkflowExecutionError(error_report=None)`.
    - **G6** *(regression)* — the `WorkflowAlreadyStartedError` / `RPCError` clause still raises a generic `WorkflowExecutionError(error_report=None)`, behavior unchanged.
    - **G7** *(regression)* — `WorkflowExecutionError.to_error_report()` with `error_report=None` falls through to the base `_enrich_error_report_from_cause` behavior.

### File reference index

| File | Role | Key lines |
| --- | --- | --- |
| `pipelex/base_exceptions.py` | `ErrorReport` (shared report type), `PipelexError.to_error_report` + `_enrich_error_report_from_cause` (chain walk) | `ErrorReport` 55, `to_dict` 71, `to_error_report` 106, **breaking line** 137 |
| `pipelex/temporal/tprl/activity_error_boundary.py` | Activity-side: `PipelexError` → `TemporalError`, packs report into `details` | `convert_pipelex_errors` 25, 52 |
| `pipelex/temporal/tprl/temporal_error.py` | `TemporalError` (`ApplicationError` subclass); `_error_report_from_details` recovery helper (workflow-side only today) | `_error_report_from_details` 14, `from_app_error` 99, `from_message_exception` 126 |
| `pipelex/temporal/tprl/workflow_caller.py` | Submitter side — **where the report is dropped** | `execute_workflow` 90, `except WorkflowFailureError → WorkflowExecutionError` 122-125 |
| `pipelex/temporal/exceptions.py` | `WorkflowExecutionError` (`TemporalFlowError` → `PipelexError`), no class-level metadata | `WorkflowExecutionError` 12 |
| `pipelex/temporal/tprl_pipe/temporal_pipe_run.py` | `TemporalPipeRun.run` — submitter entry, no try/except | `run` 49 |
| `pipelex/pipeline/runner.py` | `PipelexRunner.execute_pipeline` — wraps the propagated error as `PipelineExecutionError` | `execute_pipeline` 75, `except PipelexError` 172, `raise PipelineExecutionError` 184 |
| `pipelex/pipeline/exceptions.py` | `PipelineExecutionError` — pure wrapper, `to_error_report()` floors to `RUNTIME`/`UNKNOWN` | `PipelineExecutionError` 14, `to_error_report` 38-48 |
| `pipelex/cli/agent_cli/commands/agent_output.py` | Agent CLI delivery — reads `to_error_report()`, ContextVar (sound, do not touch) | `_assemble_error_payload` 171, `to_error_report()` read 192-202 |
| `pipelex/cli/agent_cli/commands/run/pipe_cmd.py` | Agent CLI `run pipe` — catches `PipelineExecutionError` | `set_agent_cli_output_format` 73, `except PipelineExecutionError` 155 |
| `pipelex/pipelex.py` | Wires `make_temporal_pipe_run()` as the hub pipe-run when Temporal is enabled | ~429-431 |

---

## [done] Recover the structured error report on the Temporal child-workflow boundary

**Status:** done (landed 2026-05-17 on `feature/Temporal-error-report`) · **Filed:** 2026-05-17 (surfaced by the eng review of the submitter-boundary fix) · **Severity:** low — latent; the affected methods are not on Pipelex's traced execution paths.
**Depends on:** the submitter-boundary fix above landing first (it builds `error_report_dict_from_details` and `WorkflowExecutionError.error_report`).

### TL;DR

`WorkflowExecutor.execute_child_workflow` and `start_child_workflow` (`pipelex/temporal/tprl/workflow_caller.py:221`, `:267`) catch `ChildWorkflowError` and, when `exc.cause` is an `ApplicationError`, do `raise WorkflowExecutionError(msg) from exc.cause`. `ApplicationError` is not a `PipelexError`, so `_enrich_error_report_from_cause` stops at that link — the same structured-report drop the submitter-boundary fix addresses, in two more methods.

### Why it is not live today

Both methods carry a docstring (`workflow_caller.py:180`) stating that Pipelex's in-workflow child-spawn sites (`tprl_pipe.wf_pipe_run`, `tprl_pipe.temporal_pipe_router`) deliberately bypass these wrappers and call `workflow.execute_child_workflow(...)` directly to stay replay-deterministic. The workflow → workflow hop is already covered by `TemporalError.from_app_error`. So the bug is latent on public surface, not on a path Pipelex exercises.

### Fix (landed)

In each `except ChildWorkflowError` block of `execute_child_workflow` / `start_child_workflow`, when `exc.cause` is an `ApplicationError` the handler now calls `recover_error_report(exc.cause)` — `recover_error_report` accepts the `ApplicationError` directly and returns it on the first chain-walk iteration. On a recovered report it raises `WorkflowExecutionError(error_report.message, error_report=...)`, mirroring `execute_workflow`; otherwise it falls back to the prior generic `WorkflowExecutionError`. The `_find_application_error` docstring was updated to note callers may pass `ChildWorkflowError.cause` straight in.

Unit coverage in `tests/unit/pipelex/temporal/test_workflow_caller_child_error_recovery.py` mirrors the submitter-boundary tests (recovery success, G3 malformed details → generic, G4 no report payload → generic, non-`ApplicationError` cause → generic), parametrized across both methods. `make agent-check` and the temporal unit suite pass.

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR (PLAN) | 4 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — (backend-only, N/A) |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **UNRESOLVED:** 0 — all six decisions (A1, A2, Q1, Q2, outside-voice, child-workflow TODO) answered.
- **VERDICT:** ENG CLEARED — ready to implement. Architecture, code-quality, test, and performance sections all closed.
