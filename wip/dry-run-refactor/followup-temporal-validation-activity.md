# Follow-up — Distributed dry-run + validation as one in-process Temporal activity

> **Status: in progress — branch `feature/Dry-run-as-temporal-activity`.** Implements **D-plan Part C / D5 / req 2**, expanded with the **in-memory tracing** requirement surfaced 2026-06-09. The executable phase-by-phase plan with checkboxes and checkpoints lives in [`../../TODOS.md`](../../TODOS.md) (repo root) — this doc is the durable design reference (the *why* + the decisions).
>
> **Design rationale:** [`D-plan.md`](./D-plan.md) §4.9 (distributed validation activity). **Risks:** D-plan §8 (nested-dispatch from the sweep, `temporalio` bump regression surface).
>
> **Depends on:** the consolidation (`BundleValidator`, [`consolidation-as-built.md`](./consolidation-as-built.md)) — **shipped (#956)**. Part B ([`followup-leaf-run-mode-mock.md`](./followup-leaf-run-mode-mock.md)) is **no longer a hard prerequisite** — see "Dependency picture, corrected" below.

## What this delivers (req 2)

Production flow: the web app calls the Pipelex API to validate a bundle; when Temporal is enabled the API dispatches the whole job — **validation sweep + graph-producing dry-run** — to a worker as **one activity**; the worker runs it all **in-process, in memory**, and returns the per-pipe status map **and** the `GraphSpec`. No usage/cost reporting (dry runs are free). In direct mode the API keeps running it in-process unchanged (req 3).

## Dependency picture, corrected (2026-06-09)

The original brief said this work "depends on Part B (leaf-level run-mode mock)" and hinged on a new `scoped_content_generator` ContextVar. Both have been overtaken by what shipped since:

- **The sweep already stays in-process under a Temporal hub.** PR #976 wrapped `BundleValidator`'s per-pipe loop in `scoped_pipe_router(self._pipe_router)` (`bundle_validator.py`), so nested controller sub-pipes resolve the local in-process router instead of leaking to the Temporal router. The nested-dispatch risk D-plan §8 worried about — the load-bearing reason for `scoped_content_generator` — is **already handled** for the sweep.
- **DRY already mocks inline at the pipe level.** Pre-Part-B, each operator's dry path uses `ContentGeneratorDry()` inline, so a DRY sweep never dispatches `act_llm_gen_*`. That is exactly what we want *inside* a single activity (everything in-process). Part B is about the **opposite** cell (a top-level DRY run that *should* exercise the worker path and mock inside the activity) — it does not gate hosting the sweep in one activity.
- **The usage registry is gone.** Post-#967 (distributed cost reporting) usage rides on `PipeOutput`, not a process-global report registry. The sweep accumulates no per-run reporting state (`bundle_validator.py` step-4 comment), so overlapping sweeps can't collide on it. The "open one throwaway per-sweep registry" worry from earlier drafts is moot.

**Caveat — `scoped_content_generator` is deferred, not dead.** "Largely superseded" holds *only pre-Part-B*. Today a DRY sweep mocks at the **pipe** level (`ContentGeneratorDry` inline) and never touches `get_content_generator()`, so the hub's global generator is irrelevant and `scoped_pipe_router` alone keeps the sweep in-process. But under a Temporal-enabled hub `get_content_generator()` returns `ContentGeneratorInWorkflow` **globally** (set once at boot — `pipelex.py:370-385`, not contextual). So once **Part B** relocates the DRY mock *down to the leaf* (routing it through `get_content_generator()`), this in-process activity would reach `ContentGeneratorInWorkflow` and try to dispatch `act_llm_gen_*` — breaking the in-process guarantee. **Part B therefore reintroduces the need for the inline content-generator scope here.** This is the same `scoped_content_generator` seam Part C originally specced and the same one Shape C ([`followup-leaf-run-mode-mock.md`](./followup-leaf-run-mode-mock.md)) needs — whichever follow-up lands first should build it; the other consumes it. **Recommendation: add the inline content-generator scope to this activity now**, so it is correct regardless of Part-B ordering (robust over quick).

**Net:** the validation-sweep half is essentially ready to wrap. The real new work is the **graph-producing dry-run half**, specifically **in-memory graph tracing** (so it runs inside one activity without the heavyweight cross-worker DynamoDB round-trip) plus forcing the inline content generator so the leaf never dispatches.

## The graph step today vs. the new design

**Today (the thin-submitter design — see the #976 reviewer note).** `pipelex-api`'s `/validate` route does two things: `validate_bundle()` (the in-process sweep → status map) and, best-effort, `dry_run_pipeline()` → a `GraphSpec`. `dry_run_pipeline` goes through `PipelexRunner.execute_pipeline` → the hub's `get_pipe_run()`, which under a Temporal hub is `TemporalPipeRun` — so it dispatches **one top-level workflow** to the worker. The worker runs the pipeline, traces to the DynamoDB event-log backend (`BufferingEventLog` in the workflow → `act_flush_trace_events` → DynamoDB), and `act_assemble_tracing` reads the events back and assembles the `GraphSpec`. The API itself runs with tracing **off** (thin submitter); the worker owns tracing + assembly. This works because the graph step is a *single* dispatch (no concurrent same-id collision — unlike the sweep's fan-out, which #976 fixed). **Do not move this step in-process in the API** — that breaks graph generation (tracing off in the API → empty graph).

**New (this follow-up).** Host the dry-run + validation in **one activity on the worker** that runs entirely in-process and traces the graph in an **in-memory** event log:

- No per-pipe child workflows / activities (the whole pipeline dry-runs in-process inside the one activity — like the sweep does).
- No DynamoDB round-trip and no NDJSON files for the graph — the trace events live and die in memory inside the activity, just long enough to assemble the `GraphSpec`.
- No usage/cost events at all (dry run).

This is lighter than the current top-level-workflow + DynamoDB path and is the natural shape for "validate this bundle and show me its graph" — the webapp's actual call.

## The core technical problem — emit and assemble use *two* event-log instances

The blocker that makes "just add an in-memory backend" insufficient: the write side and the read side each construct their **own** event log from config, and only an **external store** bridges them.

- **Write side:** `pipeline_run_setup` (`pipeline_run_setup.py`) calls `make_event_log(tracing_config)` and hands it to the graph tracer, which emits `PipeStart`/`PipeEnd`/edge events into it during the run.
- **Read side:** after the run, `PipeRun.run`'s `finally` calls `assemble_tracing_on_output` → `assemble_tracing` (`tracing_assembly.py`), which calls `make_event_log(tracing_config)` **again** — a brand-new instance — and `read_events(pipeline_run_id)` to rebuild the `GraphSpec`.

For NDJSON the two instances connect through the file on disk; for DynamoDB through the table. For a plain `InMemoryEventLog` they would be **two empty lists** — the reader sees nothing.

`InMemoryEventLog` already exists (`pipelex/tracing/in_memory_event_log.py`, fully implements `EventLogProtocol`, used in unit tests). It is not the missing piece. **The missing piece is a way to share one instance across emit and assemble for the duration of a run.**

### The fix — a scoped event-log override (mirror the existing scope pattern)

Add a hub-level `_event_log_override: ContextVar[EventLogProtocol | None]` + a `scoped_event_log(event_log)` context manager, exactly mirroring `scoped_current_library` and `scoped_pipe_router` (`hub.py`). Make **both** `make_event_log` call sites (`pipeline_run_setup` write, `assemble_tracing` read) prefer the override when set, else fall back to `make_event_log(tracing_config)`. The activity wraps its dry-run in `with scoped_event_log(InMemoryEventLog()):` so emit and assemble hit the **same** instance — fully in memory, no file, no DynamoDB. ContextVar-scoped ⇒ coroutine-local ⇒ concurrent activities on one worker don't cross-contaminate (same property that makes `scoped_pipe_router` concurrency-safe).

**Decision (default): scope-only; no new `TracingBackend.IN_MEMORY` config enum.** A config-selectable in-memory backend is *insufficient on its own* (the two-instance problem) unless the factory caches a per-run singleton keyed by run id — uglier than the scope, and it would change the global default rather than being opt-in per call. The scope is the clean mechanism. (Revisit only if a use case wants in-memory tracing selected purely by config, with no caller scope.)

## The in-process graph dry-run must be safe under a Temporal hub

`dry_run_pipeline` → `PipelexRunner.execute_pipeline` → `get_pipe_run()` → `TemporalPipeRun` under a Temporal hub → dispatches a workflow. Inside an activity that is illegal, and it defeats the in-process goal. The runtime bridge already solved this exact "force in-process even inside a Temporal worker" problem: `runtime_bridge.bridge._run_direct` scopes a local `PipeRouter` via `scoped_pipe_router` + runs a local `PipeRun`, and `run_pipe_via_bridge` already accepts a `trace_context` that is honored in DIRECT mode. So the in-process graph dry-run = open a `GraphTracerManager` tracer against an `InMemoryEventLog` (under `scoped_event_log`), build the `trace_context`, run the main pipe through the **bridge DIRECT path** (not `PipelexRunner`/`get_pipe_run()`), and the `GraphSpec` rides back on `PipeOutput` — assembled from the same in-memory log. Net: GraphSpec produced, zero nested dispatch, zero files/DDB.

## The activity + dispatch

- **`act_dry_validate`** — a thin activity wrapping the validation sweep (`BundleValidator`) **and** the in-memory graph dry-run, wrapped in `scoped_event_log(InMemoryEventLog())` + `scoped_content_generator(inline)` and the existing `convert_pipelex_errors` boundary (`tprl/activity_error_boundary.py`) so failures cross back as structured `ErrorReport`s. The graph dry-run is **best-effort inside the activity** (a graph failure returns `graph=None` with validation still successful — today's `/validate` contract). Inputs (serializable): `mthds_contents` / `library_dirs` / `bundle_uris`, `allow_signatures`, optional `--pipe` selection. Output (serializable): `{pipe_ref: DryRunOutput}` map + `GraphSpec | None` + the aggregated signature-check error. Registered in `pipelex/temporal/tasks.py` (the `PackName.PIPE` lists).
- **Dispatch — DECIDED (2026-06-09): one-step wrapper workflow.** A one-step workflow runs the single activity and returns — works on the current `temporalio` (`1.23.0`), **no SDK bump, no Temporal Cloud/server verification, no hard gate**. Functionally identical to the caller. A true standalone activity (no workflow) is a **later optional optimization** only — deferred, off the critical path.
- **API wiring (cross-repo `pipelex-api`).** When Temporal enabled, `/validate` dispatches the wrapper workflow and awaits `{status map, GraphSpec}`; in direct mode it keeps the current in-process `validate_bundle` + `dry_run_pipeline`. This *replaces* today's "graph as a top-level workflow to the worker + DynamoDB" path with the single-activity in-memory path.

## ✅ Former HUMAN GATE — RESOLVED (2026-06-09)

The `temporalio` standalone-activity question is **resolved**: dispatch uses the **one-step wrapper workflow** on the current `temporalio`. No bump, no infra verification, nothing left to ask — the whole plan (Phases 1→4 in [`../../TODOS.md`](../../TODOS.md)) runs without stopping for human input. Switching to a true standalone activity later is a pure runtime optimization (Phase G0, deferred); only *that* would need the version + Cloud/server-support facts.

## Acceptance (Checkpoint F)

req 1 (distributed DRY testing, activity-level mocks — delivered by Part B, not here) · **req 2 (production dry-run + validation as one in-process Temporal activity, in-memory tracing) — this follow-up** · req 3 (direct in-process unchanged).
