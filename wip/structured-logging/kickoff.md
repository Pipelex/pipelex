# Structured logging refactor — kickoff briefing

**Status:** kicked off, not started. Sequenced AFTER `feature/API-readiness-2` and the surrounding error-handling stack merge. Will get its own branch and its own PR.

**Purpose of this doc:** cold-start briefing for the session that picks this up. Captures *why* the refactor exists, *what good looks like*, *what the current code constrains us to*, and the first open questions to resolve. **Not a plan** — the plan is the first artifact of that session.

## TL;DR

Pipelex's `log` API is string-shaped today (`log.info("a message string with stuff baked in")`). That shape forced the recent `request_id` correlation work into per-line text interpolation, which is leaky, fragile, and unqueryable downstream. The right answer is **structured logging** (each record is a dict / JSON object with named fields) combined with **contextvars for request-scoped attributes** (`request_id`, `user_id`, `pipeline_run_id`) bound once at the entry boundary and auto-stamped onto every log record in scope. That replaces the current threading-and-interpolation pattern entirely, and removes a whole class of "we forgot to add `request_id` on the failure path" bugs by construction.

## What triggered this

`wip/error-handling/archive-delivery-error-path-request-id.md` opened the question of whether to thread `request_id` into the failure-path messages of `DeliveryExecutor` (mirroring the success-path threading from commits `ceb018b5` and `07f9cce9`). The proximate decision was "do it the manual way OR do the structural fix." We chose to defer the structural fix to a dedicated branch — this one.

Two preceding commits did manual per-line threading on the success path:

- `ceb018b5` — thread `request_id` through `DeliveryExecutor.execute` and into success log lines.
- `07f9cce9` — forward `request_id` from `PipeRun.run` direct-mode dispatcher to `DeliveryExecutor`.

Both commits also introduced the ad-hoc `request_id_suffix = f", request_id={request_id}" if request_id is not None else ""` pattern. That pattern is exactly what this refactor exists to delete.

## The deeper insight (the senior-engineer take)

Text interpolation of contextual identifiers into log message strings is a 2010-era anti-pattern. In 2025:

- **Each log record is a dict.** Message body is human-readable narrative; identifiers, request scope, user scope, error codes, durations are *fields*. Sinks consume them as fields, not as substrings to grep.
- **Request-scoped attributes ride on contextvars.** Bind once at the entry boundary; let a logging filter / processor stamp them onto every record in scope. The author of an individual `log.info(...)` call shouldn't be able to forget the request id, because they were never asked to include it in the first place.
- **f-strings stay for the narrative.** `log.info("Storage delivery completed", files=n)` — not `log.info(f"Storage delivery completed: files={n}, request_id={r}, pipeline_run_id={p}")`.

Why a senior systems engineer cares (each row is a property the current text-mode design fails at):

| Property | Text-interpolated | Structured + contextvar |
|---|---|---|
| Queryable in Datadog / Honeycomb / Loki | grep over message strings | exact field match, joins, aggregations |
| Survives a field rename (`pipeline_run_id` → `run_id`) | breaks every dashboard | one schema bump |
| Correlates with traces / spans | regex parse | attribute join via OTel |
| New log line in the request path | each author must remember to interpolate the context | auto-stamped by filter, can't be forgotten |
| Long / binary / escape-sensitive values | breaks formatting | structured field handles it |
| Sampling / routing by attribute | not possible | first-class |
| Asymmetry between success and failure paths | requires discipline; we already drifted | impossible by construction |

The asymmetry row is the load-bearing one: it's precisely the gap the track-delivery doc was trying to close on the failure path. With structured + contextvar, that gap can't exist.

## What good looks like (destination shape, not the plan)

Sketch of the steady-state API and behavior we're aiming at — leave room for the kickoff session to refine the exact ergonomics:

```python
# Entry boundary (API request handler, Temporal activity start, CLI command):
with bind_log_context(request_id=req_id, user_id=user_id):
    await pipe_run.run(pipe_job)

# Inside the request path — any module, any depth:
log.info("Storage delivery completed", files=len(result_files), pipeline_run_id=pipeline_run_id)
# Sink receives: {"msg": "Storage delivery completed", "files": 7, "pipeline_run_id": "...",
#                 "request_id": "...", "user_id": "...", "level": "INFO", "ts": "..."}
```

Key properties of the destination state:

- `pipelex.log` gains a structured-field surface (likely `**fields` kwargs, or an explicit `extra: dict` — to settle in the kickoff session).
- A `ContextVar`-backed context manager (`bind_log_context`) sets request-scoped attributes; a logging filter / processor reads them and merges into every record.
- The two boundaries that bind today's `request_id` continue to bind it — but at the *context* level, not by threading kwargs through 4-deep call stacks. The API request handler binds; `PipeRun.run` binds for non-API direct-mode invocations (whatever metadata it has); the Temporal activity entry re-binds from `DeliveryActivityArg.*` (the wire-format fields stay; only the propagation mechanism inside the activity changes).
- The manual `request_id` kwargs on `DeliveryExecutor.execute` / `_store_results` / `_notify_webhook` are **deleted**. So is the `request_id_suffix` interpolation. The success log lines auto-pick up `request_id` from the filter; the failure log lines do too; the exception messages can stop carrying it (and stop pretending to).
- Non-API invocations (CLI, direct library use, tests) simply don't bind `request_id`; the filter sees None; the field is absent from the record. No conditional suffix code anywhere.

## Reality of the current code (what we found during the trigger discussion)

The `pipelex.log` public API is **string-shaped**:

```python
# pipelex/tools/log/log.py
def info(self, content: str | Any, title: str | None = None, inline: str | None = None): ...
def warning(self, content: str | Any, ..., problem_id: str | None = None): ...
def error(self, content: str | Any, ..., include_exception: bool = False, problem_id: str | None = None): ...
```

No `extra=` kwarg, no `**fields`, no structured pathway. Dispatch flows through `pipelex/tools/log/log_dispatch.py` → `log_formatter.py`. **Whether the dispatch + formatter layers could thread structured attrs through to the underlying stdlib `LogRecord.extra` without breaking existing sinks is the first thing to verify in the kickoff session** (see open questions).

Specific sites currently doing manual interpolation / threading of `request_id` and `pipeline_run_id` (these become the regression-test fixtures for the refactor, and the places we delete code):

- `pipelex/pipe_run/delivery_executor.py`
  - `execute(... request_id: str | None = None)` — kwarg added by `ceb018b5`. To delete.
  - `_store_results(... request_id: str | None = None)` — same. To delete.
  - `_notify_webhook(... request_id: str | None = None)` — same. To delete.
  - Success log lines (lines around 239 and 280) interpolate `request_id_suffix`. To revert to plain narrative.
  - Failure exception messages (lines 243, 282, 285) interpolate `pipeline_run_id`. Probably revert to plain narrative; the catch site's log carries the structured fields.
- `pipelex/pipe_run/pipe_run.py`
  - Debug entry log (around line 79) interpolates `pipeline_run_id` and `status`.
  - Pipe-execution-failed log (around line 55) interpolates `pipeline_run_id`.
  - Delivery-also-failed and tracer-close-also-failed logs (around lines 64-68 and 93-97) interpolate `pipeline_run_id`.
  - The kwarg pass-through `request_id=pipe_job.job_metadata.request_id` on line 88 — to delete (binding happens at context-manager level instead).

These are the sites *we found during the trigger discussion*. A full sweep across the codebase for `f"...pipeline_run_id={...}..."` and similar patterns is part of the kickoff session's discovery step.

## Constraints, risks, and unknowns to size

- **Log sink consumers.** Whatever currently consumes pipelex log output (Temporal activity logs, container stdout, ECS log driver to CloudWatch, dev-time console formatter) needs to handle records with new structured attrs. The container path is probably fine (CloudWatch ingests JSON nicely); the local dev formatter (`log_formatter.py`) needs review — it likely pretty-prints strings today and will need a structured-aware mode.
- **Temporal worker boundary.** ContextVars do NOT propagate across the activity wire automatically. The current code passes `request_id` as an explicit field on `DeliveryActivityArg` — that stays. What changes is that the activity's entry code re-binds the contextvar from the arg, so everything *inside the activity* gets auto-stamped. Same pattern for any other cross-process boundary.
- **Async / task boundaries within a single process.** ContextVars do propagate across `asyncio` tasks created from a context where the var is bound (Python 3.7+ semantics). Worth a focused test, especially around `asyncio.create_task` and the `PipeRun.run` finally-block delivery dispatch.
- **Non-API callers.** CLI, tests, direct library use — these have no `request_id`. Filter must tolerate unbound contextvars cleanly (emit records with the field absent, not with the literal string "None"). Tests should pin this.
- **Backwards compatibility on `log.error` / `log.warning`.** They have extra kwargs today (`include_exception`, `problem_id`). The new structured-field surface needs to coexist with those without ambiguity. Likely cleanest: explicit `extra: dict[str, Any] | None = None` rather than `**fields`, to keep the existing kwarg surface unambiguous.
- **Existing tests that grep log strings.** Any test that does `assert "request_id=" in caplog.text` or similar needs to migrate to `assert caplog.records[0].request_id == ...`. That's a one-time mechanical fix but it's broad.
- **No backward-compat shim.** Per CLAUDE.md, we don't ship deprecation transitions. The refactor lands as a single coherent change; manual threading on `DeliveryExecutor` is deleted, not double-supported.

## First open questions for the kickoff session

The session should answer these before writing the plan:

1. **Does `log_dispatch` + `log_formatter` already preserve `LogRecord.extra` end-to-end, or does the formatter layer drop it?** This determines whether the refactor is half-a-day (preserve and surface) or several days (rebuild the formatter / sink pathway). Read `pipelex/tools/log/log_dispatch.py` and `log_formatter.py` first.
2. **What's the destination wire format for production sinks?** If we're emitting to CloudWatch / Datadog / Honeycomb, the formatter needs a JSON mode for prod and a human-readable mode for local dev. What's wired up today?
3. **Structured-field API shape:** explicit `extra: dict | None` parameter, or `**fields: Any` kwargs? The explicit-dict variant is unambiguous against existing kwargs (`title`, `inline`, `problem_id`, `include_exception`); the `**fields` variant reads cleaner at call sites. Pick one consciously.
4. **Bind-once boundaries:** confirm the entry points. API request handler is one. `PipeRun.run` for direct-mode is another. Temporal activity entry is a third. CLI command entries are a fourth. Anything else?
5. **Field naming convention.** `request_id` or `request.id` (dotted)? Plural / singular for collections? Standardize before stamping it across the codebase.
6. **Existing observability conventions.** Does pipelex already emit anything OTel-flavored? If so, align field names with the OTel semantic conventions where they exist (`http.request.id`, `user.id`, etc.) so traces and logs join cleanly downstream.

## Sequencing

- **Do not start until `feature/API-readiness-2` merges.** That branch is the trigger context; this refactor touches the same files.
- **Do not start until the error-handling stack settles.** Several `wip/error-handling/track-*.md` items are still open; they shouldn't be racing this refactor through the same files.
- **Branch:** `refactor/structured-logging` (or similar — confirm at branch-creation time).
- **Scope discipline:** the refactor is the API extension + the contextvar machinery + the migration of the request-scoped fields we know about (`request_id`, `pipeline_run_id`, `user_id`). It is NOT "rewrite every log line in the codebase." Other call sites migrate opportunistically as they're touched.

## References

- `wip/error-handling/archive-delivery-error-path-request-id.md` — the trigger doc; closing rationale references this refactor as the deferred altitude fix.
- Commit `ceb018b5` — `feat(delivery): thread request_id through DeliveryExecutor for cross-phase log correlation`. To be partially reverted.
- Commit `07f9cce9` — `fix(delivery): forward request_id from PipeRun direct-mode dispatcher to DeliveryExecutor`. To be partially reverted.
- `pipelex/tools/log/log.py` — current string-shaped Log API. The surface to extend.
- `pipelex/tools/log/log_dispatch.py` — dispatch layer. First file to investigate (open question 1).
- `pipelex/tools/log/log_formatter.py` — formatter layer. Second file to investigate (open questions 1 and 2).
- `pipelex/pipe_run/delivery_executor.py` — site of the manual threading. Deletion target.
- `pipelex/pipe_run/pipe_run.py` — site of additional uncorrelated failure logs (lines 55, 64-68, 79, 93-97 approximately). Deletion / migration target.
- Python `contextvars` docs — https://docs.python.org/3/library/contextvars.html
- OpenTelemetry log data model + semantic conventions — for field-naming alignment (look up at session start).
