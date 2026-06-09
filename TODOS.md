# Dry-run + validation as one in-process Temporal activity (in-memory tracing)

> **Branch:** `feature/Dry-run-as-temporal-activity`. This file is the **executable plan + progress tracker** for **Mode 1** (in-memory activity). Update the checkboxes and the checkpoint handoff blocks as you go.
>
> **Read first, in order:** (1) [`wip/dry-run-refactor/dry-run-modes-master-plan.md`](wip/dry-run-refactor/dry-run-modes-master-plan.md) — the big picture (both dry-run modes, what they share); (2) [`wip/dry-run-refactor/followup-temporal-validation-activity.md`](wip/dry-run-refactor/followup-temporal-validation-activity.md) — this mode's design / why; (3) the "Cold-start context" section just below. **The other mode (full-distribution, leaf-mocks) is out of scope here** — return to the master plan for it after Checkpoint F.
>
> **Goal:** when Temporal is enabled, the API dispatches the whole `/validate` job — validation sweep **+** graph-producing dry-run — to a worker as **one activity** that runs entirely **in-process** and traces the graph in an **in-memory** event log (no DynamoDB round-trip, no NDJSON files, no usage/cost reporting). Direct mode stays in-process and unchanged.

---

## Cold-start context (read this first in a fresh session)

The five facts that shape the whole plan — verify by symbol before relying on them, but they were true at branch start:

1. **The validation sweep is already Temporal-safe and in-process.** `BundleValidator.validate_pipes` wraps its per-pipe loop in `scoped_pipe_router(self._pipe_router)` (PR #976) and runs a locally-constructed `PipeRun` — never `get_pipe_run()`. DRY mocks inline at the pipe level (`ContentGeneratorDry`). So the sweep half is ready to wrap; **Part B is NOT a prerequisite** (it's the opposite cell — a top-level DRY run that *should* hit the worker path).

2. **The graph dry-run is the real work.** `pipelex-api`'s `/validate` (`../pipelex-api/api/routes/pipelex/validate.py`) calls `validate_bundle()` (sweep) **and** `dry_run_pipeline()` (graph). `dry_run_pipeline` (`pipelex/pipe_run/dry_run_pipeline.py`) goes through `PipelexRunner.execute_pipeline` → `get_pipe_run()` → `TemporalPipeRun` under a Temporal hub → dispatches a top-level workflow to the worker, which traces to `temporal_dynamodb` and assembles the `GraphSpec`. That works today (single dispatch, no collision). **Do not move it in-process *in the API*** — the API runs tracing-off; that would break graph generation. The new design moves it in-process *inside the activity, on the worker*.

3. **The two-instance problem (the crux).** Emit and assemble build *separate* event logs from config: write side `pipeline_run_setup.py` (`make_event_log(tracing_config)`, ~line 200, handed to the tracer); read side `pipelex/pipe_run/tracing_assembly.py` `assemble_tracing` (`make_event_log(tracing_config)` again, ~line 95, then `read_events`), triggered from `PipeRun.run`'s `finally` (`pipelex/pipe_run/pipe_run.py` ~line 76). NDJSON/DynamoDB bridge the two instances via an external store; a plain in-memory log can't. **Fix = a shared instance scoped to the run.**

4. **`InMemoryEventLog` already exists** (`pipelex/tracing/in_memory_event_log.py`, implements `EventLogProtocol`, used in unit tests). We don't write it — we *wire* it via a scope.

5. **The scope pattern to mirror** lives in `pipelex/hub.py`: `scoped_current_library` (~line 518) and `scoped_pipe_router` (~line 635) — `ContextVar` + `@contextmanager` + a `get_*` accessor that prefers the override. The in-process "force DIRECT under a Temporal worker" primitive to reuse is `pipelex/runtime_bridge/bridge.py` `_run_direct` (~line 318) / `run_pipe_via_bridge` (~line 111, already accepts a `trace_context` honored in DIRECT mode).

### File map

| Concern | File |
|---|---|
| Event-log protocol / impls | `pipelex/tracing/{event_log_protocol,in_memory_event_log,ndjson_event_log,dynamodb_event_log,buffering_event_log}.py` |
| Event-log factory | `pipelex/tracing/event_log_factory.py` (`make_event_log`) |
| Scope pattern to mirror | `pipelex/hub.py` (`scoped_current_library`, `scoped_pipe_router`, `get_pipe_router`) |
| Write-side wiring | `pipelex/pipeline/pipeline_run_setup.py` (~200) |
| Read-side wiring | `pipelex/pipe_run/tracing_assembly.py` (~95), called from `pipelex/pipe_run/pipe_run.py` (~76) |
| Graph dry-run (to make in-process/in-memory) | `pipelex/pipe_run/dry_run_pipeline.py` |
| In-process run primitive to reuse | `pipelex/runtime_bridge/bridge.py` (`_run_direct`, `run_pipe_via_bridge`, `build_pipe_job_from_input`) |
| Validation sweep | `pipelex/pipeline/bundle_validator.py` |
| Tracer lifecycle | `pipelex/graph/graph_tracer_manager.py` (`open_tracer`, `close_tracer`) |
| Activity error boundary | `pipelex/temporal/tprl/activity_error_boundary.py` (`convert_pipelex_errors`) |
| Existing activities + registration | `pipelex/temporal/tprl_pipe/act_*.py`; `pipelex/temporal/tasks.py` (`PackName.PIPE` activity_list) |
| API route (cross-repo) | `../pipelex-api/api/routes/pipelex/validate.py` |

---

## Pre-flight — ALL DECIDED (2026-06-09)

All decisions are resolved up front so a cold-start session runs autonomously through Checkpoint F. There is **no remaining human gate** — the dispatch question that used to gate this was resolved in favor of the wrapper workflow (no `temporalio` bump).

- [x] **(DECIDED) In-memory exposure = scope-only.** Add `scoped_event_log` only; do **not** add a `TracingBackend.IN_MEMORY` config enum (insufficient alone — the two-instance problem — and it would change the global default instead of being opt-in per call).
- [x] ~~**(DECIDED) Graph dry-run shape = bridge DIRECT reuse.**~~ ⚠️ **REVISED BY ENG REVIEW (2026-06-09) — see GSTACK REVIEW REPORT, decision D-C1.** The bridge **cannot** carry `run_mode=DRY` + `mock_inputs`: `PipelexPipeRunInput` has no run-mode/mock-input field and `build_pipe_job_from_input` (`bridge.py:216`) calls `make_run_params()` → `PipeRunMode.LIVE` with no mock-input synthesis. Running the main pipe through `run_pipe_via_bridge` DIRECT would produce a **LIVE run with no inputs** that fails before reaching the graph. **New shape: use the `prepare_pipe_job` seam** (`execution_seams.py:199`) with `pipe_run_mode=PipeRunMode.DRY` + `execution_config(mock_inputs=True, generate_graph=True)` (what `dry_run_pipeline.py` already does), running a **local `PipeRun`** under `scoped_event_log` + `scoped_pipe_router` + `scoped_content_generator`. Still do **not** refactor `PipelexRunner`; still no bridge wire-contract change.
- [x] **(DECIDED) One activity (status + graph).** One activity returns `{status map, GraphSpec, signature_check_error}`; the graph dry-run is **best-effort inside the activity** — a graph failure still returns a successful validation with `graph=None`, preserving today's `/validate` semantics. (Not two separate activities.)
- [x] **(DECIDED) Dispatch = one-step wrapper workflow (no `temporalio` bump).** The API dispatches a one-step workflow that runs the single activity and returns — works on the current `temporalio` (`1.23.0`), no SDK bump, no Temporal Cloud/server verification, **no hard gate**. Functionally identical to the caller. A true standalone activity is a **later optional optimization** (Phase G0, deferred — not on this branch's critical path).
- [x] **(DECIDED: BUILD THE SCOPE NOW) Force the inline content generator.** Today the in-process sweep/dry-run is safe because DRY mocks at the **pipe** level (`ContentGeneratorDry` inline) and never calls `get_content_generator()`. But under a Temporal-enabled hub `get_content_generator()` is `ContentGeneratorInWorkflow` **globally** (boot-time, `pipelex.py:370-385`). The moment **Part B** ([`wip/dry-run-refactor/followup-leaf-run-mode-mock.md`](wip/dry-run-refactor/followup-leaf-run-mode-mock.md)) relocates the DRY mock to the leaf, this activity's leaf would dispatch `act_llm_gen_*` and break the in-process guarantee. **DECISION (2026-06-09): add the inline content-generator scope now** (`scoped_content_generator`, mirroring `scoped_pipe_router`) in Phases 2–3, so the activity is correct regardless of Part-B ordering and the shared seam is built once. Rejected the "rely on the pipe-level mock, defer the scope" alternative as fragile (would silently regress when Part B lands). The Phase-2/3 zero-dispatch test must simulate the leaf-level mock (not only today's pipe-level mock) so the guard isn't a no-op until then.
  - This scope is **orthogonal to** the req-1 "full-distribution leaf-mock" mode (Mode C) — that mode deliberately *does* dispatch and mocks inside the activity. The two coexist (proof: `is_mock_inference` already ships the LLM slice of Mode C alongside the DRY path). The scope is per-call/ContextVar, so it doesn't disturb Mode C. See [`wip/dry-run-refactor/dry-run-modes-master-plan.md`](wip/dry-run-refactor/dry-run-modes-master-plan.md).

> ### ✅ Former HUMAN GATE — RESOLVED (2026-06-09): wrapper workflow, no bump
>
> The `temporalio` standalone-activity question that used to gate dispatch is **resolved**: we use the **one-step wrapper workflow** on the current `temporalio` (`1.23.0`). No SDK bump, no Temporal Cloud/server verification, nothing to ask. The cold-start session proceeds through all phases without stopping for human input. (Standalone activity is a later optional optimization — Phase G0, deferred.)

---

## Status at a glance

| Phase | Title | Status |
|---|---|---|
| 1 | `scoped_event_log` + shared in-memory tracing (in-repo, no Temporal) | ☑ done |
| | **⛔ CHECKPOINT 1 — in-memory tracing verified in direct mode** | ☑ done (suite green, committed) |
| 2 | In-process, in-memory graph dry-run safe under a Temporal hub (+ `scoped_content_generator`) | ☑ done |
| | **⛔ CHECKPOINT 2 — graph dry-run verified under a Temporal hub** | ☑ done (suite green, committed) |
| 3 | The `act_dry_validate` activity + wrapper-workflow dispatch + worker registration + isolation test | ☑ done |
| | **⛔ CHECKPOINT 3 — activity registered + isolation-tested** | ☑ done (suite green, Tier 2d GREEN+RED, committed) |
| 4 | API dispatch (cross-repo `pipelex-api`) | ☑ done |
| | **⛔ CHECKPOINT F — all requirements met** | ☑ done (both suites green, Tier 2d both arms GREEN, committed) |
| G0 | *(optional, deferred)* `temporalio` bump → true standalone activity | ☐ later |

Status legend: ☐ not started · ◐ in progress · ☑ done. **No human gate remains** (dispatch = wrapper workflow).

---

## Phase 1 — `scoped_event_log` + shared in-memory tracing

Pure in-repo capability, no Temporal, no cross-repo. Fully testable in direct mode. **TDD: write the failing tests first.**

- [x] *Tests first* (`tests/unit/pipelex/tracing/test_scoped_event_log.py` + `tests/integration/pipelex/pipeline/test_scoped_in_memory_tracing.py`): assert that running a dry-run-with-graph under `with scoped_event_log(InMemoryEventLog())` (a) produces a non-empty, correct `GraphSpec`, (b) writes **no** NDJSON file and touches **no** configured backend, and (c) emit and assemble hit the **same** instance. Concurrency/nesting tests included (unit: ContextVar isolation + nesting + exception restore; integration: two concurrent scoped dry-runs stay isolated).
- [x] Added to `pipelex/hub.py` (mirroring `scoped_pipe_router`): `_event_log_override: ContextVar["EventLogProtocol | None"]`, `scoped_event_log(event_log)` `@contextmanager` (save/set/restore), and accessor `get_event_log_override()`.
- [x] Write side prefers the override: `pipeline_run_setup.py` (`event_log = get_event_log_override()`, factory only when `None` and `is_enabled`). D1: a set override implies tracing-enabled.
- [x] Read side prefers the override: `tracing_assembly.py::assemble_tracing` — the `is_enabled` early-return is bypassed when an override is set (D1); the override is read **without** `close()` (the scope owner keeps the instance's lifecycle).
- [x] `EventLogProtocol` surface confirmed sufficient — no protocol change.
- [x] `make agent-check` clean · new tracing tests green (7/7).

> ### ⛔ CHECKPOINT 1 — after Phase 1 — **MANDATORY STOP**
>
> A self-contained, separately reviewable in-repo capability. Natural place to split sessions and/or land alone.
>
> **Verify:** `make agent-check` clean · `make agent-test` green · the new in-memory-tracing tests pass (same-instance emit+read, zero file/backend, concurrency-safe) · commit.
>
> **Handoff (filled in, 2026-06-09):**
>
> - **Scope API (`pipelex/hub.py`, right after `get_pipe_router`):** `scoped_event_log(event_log: EventLogProtocol)` — `@contextmanager`, ContextVar save/set/restore, mirrors `scoped_pipe_router`. Accessor: `get_event_log_override() -> EventLogProtocol | None`. ContextVar: `_event_log_override`.
> - **Write-side edit:** `pipeline_run_setup.py::pipeline_run_setup` — `event_log = get_event_log_override()`; falls back to `make_event_log(tracing_config)` only when no override AND `tracing_config.is_enabled`.
> - **Read-side edit:** `tracing_assembly.py::assemble_tracing` — early-return is now `if event_log_override is None and not tracing_config.is_enabled`; with an override, `read_events` is called on it directly and it is NOT `close()`d (scope owner keeps lifecycle; the no-override branch keeps its `make_event_log` + `close()` shape — D2 symmetric primitive).
> - **`is_enabled` vs override (D1):** a set override **implies tracing-enabled** at both guards; regression-tested (`test_override_implies_enabled_when_tracing_disabled`).
> - **`EventLogProtocol`:** unchanged.
> - **Other `make_event_log` call sites left alone (intentional):** `tracing/activity_event_log.py` (Temporal worker per-process usage log — Phase-3 activity never reaches it) and `runtime_bridge/primitives/trace_flush.py` (bridge DIRECT flush — off-path since D-C1 dropped the bridge).
>
> **Next: Phase 2.**

---

## Phase 2 — In-process, in-memory graph dry-run safe under a Temporal hub

Make the graph-producing dry-run run fully in-process even under a Temporal-enabled hub, tracing into the Phase-1 in-memory log. Reuse the bridge DIRECT primitive (it already forces in-process via `scoped_pipe_router` + a local `PipeRun`, and `run_pipe_via_bridge` already honors a `trace_context` in DIRECT mode).

- [x] *Tests first* (`tests/integration/pipelex/temporal/test_dry_run_graph_in_process.py`): under the suite's **Temporal-enabled** hub (real `TemporalPipeRouter` + `ContentGeneratorInWorkflow` as hub defaults, asserted as preconditions), the in-process graph dry-run (a) returns a correct `GraphSpec` covering the full `temporal_parallel` controller topology, (b) dispatches **zero** workflows (spy `WorkflowExecutor.execute_workflow`), and (c) touches no file/DDB transport (`make_event_log` forbidden via patch).
- [x] Added `dry_run_pipe_in_process(pipe, *, library_id)` in `pipelex/pipe_run/dry_run_pipeline.py`: opens a `GraphTracerManager` tracer against an `InMemoryEventLog`, runs via `prepare_pipe_job` (DRY + mock_inputs + generate_graph) + a local `PipeRun` under the three scopes (`scoped_event_log` + `scoped_pipe_router` + `scoped_content_generator`) — not the bridge, not `PipelexRunner` (D-C1). `GraphSpec` rides back on `PipeOutput`. Caller owns the library lifecycle (mirrors `validate_pipes`, ready for D4).
- [x] Added `scoped_content_generator(content_generator)` in `hub.py` (ContextVar + contextmanager + `get_content_generator()` prefers the override). Leaf-level-mock simulation test (`test_leaf_level_mock_stays_in_process`) forces DRY through `get_content_generator()` and stays zero-dispatch; **RED-proven**: with the scope removed, the leaf reached `ContentGeneratorInWorkflow` and failed with `_NotInWorkflowEventLoopError`.
- [x] Tracer-key alignment (D-C7): tracer opened at `graph_id=pipeline_run_id` and closed by `pipeline_run_id` in `PipeRun.run`'s finally — aligned by construction, no divergent `tracer_key` parameter exposed; pinned by the non-empty-graph assertions (a divergent key would assemble an empty graph).
- [x] `dry_run_pipeline`'s existing (worker-workflow + DynamoDB) path left intact — the API still uses it until Phase 4.
- [x] `make agent-check` clean · zero-dispatch / in-memory-graph tests green.

> ### ⛔ CHECKPOINT 2 — after Phase 2 — **MANDATORY STOP**
>
> **Verify:** under a Temporal-enabled hub the in-process graph dry-run yields a `GraphSpec` with **zero** nested dispatch and **zero** file/DDB I/O · `make agent-test` green · commit.
>
> **Handoff (filled in, 2026-06-09):**
>
> - **Entry point:** `dry_run_pipe_in_process(pipe: PipeAbstract, *, library_id: str) -> GraphSpec` in `pipelex/pipe_run/dry_run_pipeline.py`. Takes a resolved pipe + an already-open library (caller owns the library lifecycle — fits D4's load-once activity shape). Raises `PipelexError` when the run fails or yields no graph.
> - **Tracer lifecycle:** `open_tracer(graph_id=pipeline_run_id, event_log=InMemoryEventLog, workflow_id="direct", emit_graph_events=True, emit_usage_events=False)` before the run; `trace_context` threaded via `prepare_pipe_job(trace_context=...)` (no bridge involved — D-C1); closed by `pipeline_run_id` inside `PipeRun.run`'s `finally` (which also assembles from the scoped log onto `PipeOutput`); a safety-net `close_tracer(pipeline_run_id)` in the entry's own `finally` covers pre-run failures (idempotent pop).
> - **Tracer-key alignment:** `graph_id == pipeline_run_id == close key`, by construction; no `tracer_key` parameter exposed. A unique `dry_run_graph_<uuid>` run id is minted per call.
> - **Scopes:** `scoped_event_log(event_log)` + `scoped_pipe_router(PipeRouter(observer=ObserverNoOp()))` + `scoped_content_generator(ContentGeneratorDry())` wrap `prepare_pipe_job` + `pipe_run.run`. `scoped_content_generator` is new in `hub.py`; `get_content_generator()` now prefers the ContextVar override.
> - **Divergence from plan:** none of substance. No `PipelineManager.add_new_pipeline` registration and no report-delegate usage-event wiring (mirrors the sweep, not `pipeline_run_setup`) — deliberate: no usage/cost in this mode.
>
> **Next: Phase 3.**

---

## Phase 3 — The `act_dry_validate` activity + wrapper-workflow dispatch + registration + isolation test

Wrap the sweep + the in-memory graph dry-run in one activity, dispatched via a one-step wrapper workflow (DECIDED — no `temporalio` bump). No gate; runs straight through.

- [x] Activity defined (`pipelex/temporal/tprl_pipe/act_dry_validate.py`): body runs **`validate_bundle`** (the exact function the direct-mode route calls — sweep → status map AND the categorized `ValidateBundleError` error cascade, so both backends surface the identical 422 contract) **and** `dry_run_pipe_in_process` (→ `GraphSpec`, against the same library `validate_bundle` left loaded+current — D4), teardown once in the activity's `finally`. The scopes live in the callees (the Phase-2 entry carries all three; the sweep carries `scoped_pipe_router` + `scoped_content_generator` itself). **Graph best-effort per D5 (widened to cross-backend parity in the post-implementation review, R-D1):** catches `PipelexError` + `ValidationError`/`FactoryException` — the same catch `_classify_pipe` and the direct route use, and pipe resolution sits inside it — → `graph=None`; non-Pipelex bugs propagate. Decorated with `convert_pipelex_errors`.
- [x] Input `DryValidateArg` (`mthds_contents`/`allow_signatures`/`pipe_code` — no `bundle_uris` and, post-review R-D3, no `library_dirs`: no caller passes them and `library_dirs` was an unconstrained worker-filesystem read surface); output `DryValidateResult` (`dry_run_outputs: dict[str, DryRunOutput]` + `graph_spec: GraphSpec | None`). Per D3: no `signature_check_error` field — signature refusals raise (wrapped as `ValidateBundleError`, same as direct mode).
- [x] One-step wrapper workflow `wf_dry_validate.py` (`WfDryValidate`) runs the single activity with explicit `start_to_close_timeout=5min` + `RetryPolicy(maximum_attempts=2, non_retryable_error_types=["ValidateBundleError"])` (D-C5; post-review the list is just the one name that actually crosses — `validate_bundle` wraps the other deterministic failures into `ValidateBundleError` and the graph arm degrades instead of raising). Submitter helper `dry_validate_dispatch.py::dispatch_dry_validate` is the one-round-trip call the API (Phase 4) and the Tier-2d script share.
- [x] Registered both in `pipelex/temporal/tasks.py` (`PackName.PIPE`).
- [x] *Isolation tests* (`tests/integration/pipelex/temporal/test_dry_validate_activity_in_memory.py`): real worker against the in-process server; status map + GraphSpec correct in one round-trip; **zero nested dispatch asserted on the Temporal history** (exactly one `ActivityTaskScheduled`, zero child workflows — D6, stronger than the wrapper spy); in-memory tracing (`make_event_log` forbidden, no NDJSON); best-effort graph (`graph=None`, validation OK) + bug-propagates arm (D5); `SignaturesNotAllowedError` crosses as structured `ErrorReport` with offender + signature refs intact (T3) and lenient-mode counterpart; concurrent invocations isolated.
- [x] **Tier 2d added** to `.claude/skills/temporal-e2e-validate/` (scenario in `references/mode-2-tiers.md` after Tier 2c, submitter script `scripts/submit_dry_validate.py`, Step-7 master-table row) **and RUN against a real 3-process setup** (server + split router/runner workers): GREEN (exit 0, 5/5 SUCCESS, GraphSpec 5 nodes/6 edges, server history = 1 activity + 0 children, no NDJSON partition, activity ran on the runner process), best-effort sub-case (no main_pipe → `GRAPH: None`, exit 0), concurrency (2 parallel dispatches, distinct graph_ids, no cross-contamination), RED (dropping `scoped_event_log` → exit 1 `did not produce a graph spec` — the two-instance regression fails loudly; doc updated to the observed behavior; the content-generator RED arm is the Mode-1 leaf-mock test from Phase 2), restored + GREEN re-confirmed.
- [x] `make agent-check` clean · activity isolation tests green (7/7) · Tier 2d GREEN+RED.

> ### ⛔ CHECKPOINT 3 — after Phase 3 — **MANDATORY STOP**
>
> **Verify:** activity + wrapper workflow registered + isolation-tested (status map + GraphSpec correct, zero nested dispatch, in-memory tracing, best-effort graph, structured error on validation failure) · **Tier 2d (activity arm) GREEN and RED-proven** in `temporal-e2e-validate` · `make agent-test` green · Temporal e2e green · commit.
>
> **Handoff (filled in, 2026-06-09):**
>
> - **Activity:** `act_dry_validate(arg: DryValidateArg) -> DryValidateResult` in `pipelex/temporal/tprl_pipe/act_dry_validate.py`, `@activity.defn(name="act_dry_validate")` over `@convert_pipelex_errors`. `DryValidateArg{mthds_contents, allow_signatures, pipe_code}` (no `library_dirs` — dropped post-review, R-D3); `DryValidateResult{dry_run_outputs: dict[str, DryRunOutput], graph_spec: GraphSpec | None}`. **The sweep half is `validate_bundle` itself** (not `validate_current_library`) — chosen for cross-backend 422 parity: failures cross as the categorized `ValidateBundleError` (`error_domain=input`, refs in the caller-facing message), exactly what the direct route raises; the API problem document is built from these `ErrorReport` fields (the structured arrays on `ValidateBundleError` never reached the problem document even in direct mode — verified). Graph target = `arg.pipe_code or` the first blueprint's qualified `main_pipe`.
> - **Wrapper workflow:** `WfDryValidate` (`wf_dry_validate.py`, Temporal name `wf_dry_validate`) — one `workflow.execute_activity(act_dry_validate, start_to_close_timeout=5min, RetryPolicy(maximum_attempts=2, non_retryable_error_types=[ValidateBundleError]))` (post-review trim: the other deterministic names never cross — `validate_bundle` wraps them).
> - **Submitter helper (new, for Phase 4):** `dispatch_dry_validate(arg, *, task_queue=None, should_auto_connect_temporal=True)` in `tprl_pipe/dry_validate_dispatch.py` — mints the workflow id (`dry_validate_<uuid>` through `make_workflow_id`) and awaits the wrapper workflow; failures surface as `WorkflowExecutionError` carrying the recovered `ErrorReport`. The API route should call THIS.
> - **Registration:** `tasks.py` `PackName.PIPE` — `WfDryValidate` appended to `workflow_list`, `act_dry_validate` to `activity_list` (split workers pick them up by scope automatically — verified in the 3-process run: workflow on router, activity on runner).
> - **Divergences from plan:** (1) the activity body holds no scopes itself — `dry_run_pipe_in_process` owns its three, and `validate_pipes` now owns `scoped_pipe_router` + `scoped_content_generator` (the Part-B guard now also covers direct CLI sweeps, not just the activity); (2) graph "no main_pipe and no pipe_code" → `graph=None` silently (no error), matching the route's separate main-pipe precondition; (3) ~~the event-log-drop RED fails loudly (exit 1)~~ post-review (R-D1 parity) the event-log-drop regression degrades to `GRAPH: None` in the activity — the loud CI guard is the Mode-1 `test_dry_run_graph_in_process.py` direct-call assertions; Tier-2d doc updated.
>
> **Next: Phase 4.**

---

## Phase 4 — API dispatch (cross-repo `pipelex-api`)

- [x] `../pipelex-api/api/routes/pipelex/validate.py` split into `_validate_direct` (today's body, unchanged) + `_validate_via_temporal`, gated on `get_config().temporal.is_enabled`. Temporal branch: **dispatch FIRST** (before any API-side parsing, so every validation failure surfaces through the worker's `validate_bundle` cascade with the identical categorized `ValidateBundleError` 422 — `WorkflowExecutionError.to_error_report()` returns the recovered report and the existing global handler renders it; zero route-side catch), then re-parse blueprints for the envelope, check the `main_pipe` precondition, and build `pipe_structures` from a local **load-only** `acquire_library` (no sweep, no dry-run, no tracing API-side). Best-effort graph rides back as `graph_spec` on the activity result.
- [x] Both backends tested (`tests/unit/test_validate_temporal_dispatch.py`): Temporal-enabled returns the envelope from one round-trip (graph + blueprint + structures, dispatch awaited exactly once with the request's contents/allow_signatures), best-effort `graph_spec=null` → 200, validation failure renders the same 422 (`ValidateBundleError`/`input`, refs in `detail`), and direct mode **never** touches the dispatch helper. Existing direct-path tests (`test_allow_signatures` etc.) green against the refactored route.
- [x] **Tier 2d API arm RUN live** (real route + real dispatch via TestClient in the pipelex-api venv, against the running server + split workers): 200 with worker-assembled `graph_spec` (3 nodes/3 edges) in one round-trip; signature bundle → 422 `ValidateBundleError`/`input` through the real activity→workflow→submitter→handler chain; **found+fixed in the process:** the config-default workflow retry policy re-ran a deterministically-failed validation (same workflow id listed twice) — `dispatch_dry_validate` now pins `RetryPolicy(maximum_attempts=1)` on the wrapper workflow (D-C5 at the workflow tier), re-verified (failed workflow appears exactly once). API-arm procedure added to the Tier-2d skill scenario.
- [x] Docs + CHANGELOG `[Unreleased]` in both repos (pipelex: tracing doc + temporal-integration doc + CHANGELOG, done in Phases 1–3; pipelex-api: `docs/pipe-validate.md` "Execution Backends" section + CHANGELOG entry noting the pipelex version requirement).

> ### ⛔ CHECKPOINT F — after Phase 4 — **ALL REQUIREMENTS MET**
>
> req 2 (production dry-run + validation as one in-process Temporal activity, in-memory tracing) · req 3 (direct in-process unchanged). req 1 is delivered by Part B, not here.
>
> **Verify:** `pipelex` `make agent-test` green · Temporal e2e green · **Tier 2d (activity + API arms) GREEN** · `pipelex-api` tests green on **both** backends · commit.
>
> **Handoff (filled in, 2026-06-09) — as-built summary:**
>
> - **Phase 1** — `pipelex/hub.py`: `scoped_event_log` / `get_event_log_override` (ContextVar scope); write side `pipeline_run_setup.py` and read side `tracing_assembly.py::assemble_tracing` prefer the override (override implies tracing-enabled, read side doesn't `close()` it). The two-instance fix.
> - **Phase 2** — `pipelex/pipe_run/dry_run_pipeline.py::dry_run_pipe_in_process(pipe, *, library_id)`: graph dry-run with zero dispatch under the three scopes (`scoped_event_log` + `scoped_pipe_router` + new `hub.scoped_content_generator`, which `get_content_generator()` prefers); tracer keys aligned by construction.
> - **Phase 3** — `pipelex/temporal/tprl_pipe/act_dry_validate.py` (`DryValidateArg`/`DryValidateResult`, activity composes `validate_bundle` + `dry_run_pipe_in_process`, D4 load-once, D5 narrow best-effort graph), `wf_dry_validate.py::WfDryValidate` (one-step wrapper, D-C5 activity retry bounds), `dry_validate_dispatch.py::dispatch_dry_validate` (submitter helper, `maximum_attempts=1` at the workflow tier), registered in `tasks.py`; `BundleValidator.validate_pipes` also scopes the dry content generator. Tier 2d (skill scenario + `submit_dry_validate.py` + master-table row) GREEN+RED on a real 3-process stack.
> - **Phase 4** — `pipelex-api` route split (`_validate_direct` unchanged / `_validate_via_temporal` dispatch-first), unit tests for both backends, live API-arm verification, docs+CHANGELOG both repos.
> - **How the API dispatches now:** `dispatch_dry_validate(DryValidateArg(mthds_contents, allow_signatures))` → `wf_dry_validate` → one `act_dry_validate` on the worker → `{dry_run_outputs, graph_spec}` in one round-trip; failures cross as `WorkflowExecutionError` carrying the recovered `ValidateBundleError` report → existing 422 handler.
> - **Cross-repo shipping note:** the `pipelex-api` branch (`feature/Update-dry-run-api`) imports `pipelex.temporal.tprl_pipe.act_dry_validate` — it needs a pipelex release/rev **newer than v0.32.1** (bump the `pipelex` pin + `[tool.uv.sources]` rev) before its CI can pass; local verification used `uv pip install -e ../_dry`.
> - **Follow-ups (deferred):** retire the old worker-workflow graph path for `/validate` (now unused by the API; `dry_run_pipeline` still serves the direct CLI/API path) · Phase G0 standalone activity (`temporalio` bump) · D-plan §7 endpoint unification · consider moving `pipe_structures` into the activity result to drop the API-side load-only library acquisition (today it double-loads: worker + API).
>
> Folded into `wip/dry-run-refactor/consolidation-as-built.md` (§ "Part C as built") and the README workstream table.

---

## Phase G0 — *(optional, deferred — do AFTER Checkpoint F, only if wanted)* true standalone activity

The wrapper workflow ships the feature with no SDK bump. Replacing it with a true standalone activity is a pure runtime optimization (one fewer workflow per call), not a requirement — do it later, on its own branch/PR, only if the round-trip cost matters. Independent regression surface (the SDK underpins the whole worker/runtime).

- [ ] Confirm the target `temporalio` version (past `1.23.0`) and that our Temporal Cloud / server supports standalone-activity execution. *(This is the only step that needs infra input — and it's no longer blocking anything.)*
- [ ] Bump `temporalio` in `pyproject.toml` (+ `uv.lock` via `uv`); run the **full** Temporal e2e suite on the new SDK (`temporal-e2e-validate`) as a separately-reviewable step.
- [ ] Swap the API dispatch from the wrapper workflow to the standalone activity; keep the wrapper-workflow path as fallback if useful.

---

## Distributed verification — `temporal-e2e-validate` (Mode 1 / Tier 2d)

Mode 1's contract must be proven in a **real distributed context**, not only unit/integration. Add a tier to the repo's own skill at `.claude/skills/temporal-e2e-validate/`, following the **Tier 2c precedent** (#976 added: a scenario in `references/mode-2-tiers.md` Step 3, a Mode-1 pytest, and a Step-7 master-table row). Build it as part of Phase 3 (activity arm) and Phase 4 (API arm).

**Tier 2d — dry-run + validation runs as ONE in-process, in-memory activity.** Sibling to Tier 2c: where 2c proves the *direct* `/validate` sweep doesn't leak to Temporal, 2d proves the *Temporal-dispatched* path runs the whole sweep **+** graph dry-run inside a single activity, in memory, returning `{status map, GraphSpec}`.

**Mode 2 (3-process) GREEN** — boot Temporal-enabled, split workers up (`mode-2-setup.md`); dispatch the wrapper-workflow→`act_dry_validate` over a controller bundle (`temporal_parallel.mthds` — interesting graph):

- exit 0; per-pipe status map present (all `SUCCESS`); non-empty `GraphSpec` → `reactflow.html` assembles.
- **Strong check (the point):** during the run the worker ran the wrapper workflow + exactly one `act_dry_validate` and **nothing else** — NO child `WfPipeRouter`/`WfPipeRun`, NO `act_llm_gen_*`, NO `act_assemble_tracing`/`act_flush_trace_events`. Capture both worker sessions and grep — expect none of those for this run. (Mirrors Tier 2c's worker-idle check, but here the activity itself is expected; what must be absent is everything *nested*.)
- **In-memory tracing:** no new NDJSON partition appears under `.pipelex/traces/` for the activity's internal graph dry-run, and no DynamoDB write — the `GraphSpec` rode back on the activity result, assembled from the in-memory log.
- **No usage/cost:** no cost table, no `usage_report` events.
- **Best-effort graph sub-case:** a bundle whose graph dry-run fails (a pipe needing un-mockable input) still returns exit 0 with the status map and `graph=None` (no `reactflow.html`); validation still OK.
- **Concurrency:** two concurrent dispatches return distinct `GraphSpec`s with no shared/merged trace events.

**Mode 2 RED (prove it bites):** in the activity body, drop `scoped_content_generator(inline)` → the leaf reaches the hub `ContentGeneratorInWorkflow` and the activity tries to dispatch `act_llm_gen_*` from inside an activity (illegal) / the strong check shows dispatch; **or** drop `scoped_event_log` → the `GraphSpec` comes back empty (the two-instance regression). Restore immediately.

**Mode 1 (pytest) companion (CI-cheap)** — `tests/integration/pipelex/temporal/test_dry_validate_activity_in_memory.py`: run the wrapper-workflow→activity against the in-process server; spy `WorkflowExecutor.execute_activity`/`execute_workflow` and assert no nested dispatch during the activity; assert the event-log backend received no writes (in-memory only); assert best-effort graph returns `graph=None` on a failing graph dry-run.

**Step-7 master-table row to add:** `Tier 2d: Dry-run+validate as one in-memory activity | the Temporal-dispatched /validate runs the whole sweep + graph dry-run inside ONE in-process activity (zero nested dispatch), traces the graph in memory (no NDJSON/DDB), returns {status, GraphSpec}; best-effort graph → None on failure | PASS/FAIL | path | — `.

## GSTACK REVIEW REPORT

_Eng review (FULL) 2026-06-09 · commit 6434b6e09 · outside voice: Codex._

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | issues_found | 4 substantive (C1/C2/C3 resolved, C5 build-now), C6/C7 folded to tests |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | issues_open | 7 issues, 1 critical-gap-class (T3) |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **CODEX:** caught the Phase-2 `bridge DIRECT` flaw (cannot carry `run_mode=DRY` + `mock_inputs` — verified at `bridge.py:216`), the output-contract contradiction, and the library-lifecycle gap — all missed by the in-review reasoning, all folded as decisions.
- **CROSS-MODEL:** the review and Codex agree the plan's foundation (scoped in-memory event log, one-activity dispatch via wrapper workflow, best-effort graph) is sound. The one tension — Phase 2 seam — resolved in Codex's favor (`prepare_pipe_job`, not the bridge), verified in code.
- **VERDICT:** ENG CLEARED — findings folded as decisions; T1–T10 backlogged (tasks JSONL in gstack project dir). Scope accepted as-is (Step 0). Lake score 8/8. Implement with the decisions below.

**Decisions locked in this review (amend the phases accordingly):**

- **D1 — Phase 1 `is_enabled`:** a set `scoped_event_log` override **implies tracing-enabled** at all three guards (`pipeline_run_setup.py:199`, `tracing_assembly.py:84` early-return, `:95`). Regression test: `is_enabled=False` + override → GraphSpec still assembles in-memory. (T2)
- **D2 — Phase 1 write side:** keep **both** `make_event_log` patches for a symmetric primitive (write side is off this feature's bridge path but works for any `execute_pipeline` caller); test the full path. (T7)
- **D-C1 — Phase 2 seam:** use **`prepare_pipe_job`** (`pipe_run_mode=DRY`, `mock_inputs=True`, `generate_graph=True`) + a **local `PipeRun`** under the three scopes — **not** the bridge (the bridge runs LIVE/no-mock). (T1)
- **D3 — Phase 3 output contract:** output = `{status map (success only), GraphSpec | None}`. Unexpected pipe failures + signature refusals **raise** → `ErrorReport` → API 422. Drop the `signature_check_error` output field. **Mandatory: verify the structured offending-signatures survive the `ErrorReport` crossing** (else 422 degrades to a plain message — the one critical-gap-class). (T3)
- **D4 — Phase 3 library lifecycle:** **load once**, run sweep **and** graph against the same `library_id` (borrow-the-open-library inner sweep, no per-step teardown), tear down once in the activity's `finally`. (T4)
- **D5 — Phase 3 best-effort catch:** **narrow** to the specific dry-run-failure `PipelexError` subclasses → `graph=None`; all other `PipelexError`s and every non-`PipelexError` bug **propagate** (mirrors `assemble_tracing:69`). Test the bug-propagates arm. (T5)
- **D-C5 — Phase 3 retry/timeout:** set explicit `start_to_close_timeout` + `non_retryable_error_types` on `act_dry_validate` so deterministic failures don't retry 3×. (T6)
- **D6 — tests:** harden the Mode-1 spy to assert at the `workflow.execute_activity` SDK site / Temporal history, not the `WorkflowExecutor` wrapper (T8); forbid divergent `tracer_key` (T9).
- **Dismissed:** activity-result payload-size guard — existing S3 payload offload already handles large results.

NO UNRESOLVED DECISIONS

### Post-implementation /review (2026-06-09, on the completed branch)

Pre-landing review (structured pass + specialist subagents + Claude adversarial + Red Team + Codex adversarial + Codex structured review, all on commit 6ba8d8137). Codex structured: clean. Four decisions taken and applied on-branch:

- **R-D1 — graph-arm cross-backend parity (supersedes D5's narrow catch).** The direct route catches base `PipelexError` around the graph dry-run (best-effort for ANY domain failure); the activity's narrow tuple made the same bundle 200 on direct and 422-after-retry on Temporal. Widened to `(PipelexError, ValidationError, FactoryException)` — the `_classify_pipe` catch — with pipe resolution moved inside (unknown `pipe_code` → `graph=None`). `WfDryValidate.non_retryable_error_types` trimmed to `["ValidateBundleError"]` (the only deterministic name that actually crosses). Consequence: the event-log-drop regression degrades to `GRAPH: None` in the activity; the loud CI guard is the Mode-1 direct-call test.
- **R-D2 — cheap hardening.** Activity `finally` mirrors `PipeRun.run`'s suppress-secondary pattern (a teardown raise no longer replaces the user's real error); `dispatch_dry_validate` pins `workflow_execution_timeout=12min` (interactive bound, not the 1-hour batch default); `scoped_event_log` lifecycle docs corrected (the write-side tracer DOES `close()` its log at teardown — a scoped log's `close()` must be idempotent/no-op); `dry_run_pipe_in_process` constructs its primitives before `open_tracer` (no tracer-entry leak window). Design-tradeoff items deferred to [`wip/dry-run-refactor/followup-dry-validate-hardening.md`](wip/dry-run-refactor/followup-dry-validate-hardening.md).
- **R-D3 — `DryValidateArg.library_dirs` dropped.** No caller passed it; it was an unconstrained worker-filesystem read surface. Re-add with allowlist confinement if a real caller appears.
- **R-D4 — test lakes added.** No-retry assertion (D-C5 pinned), no-main-pipe arm, unknown-pipe_code parity arm, `scoped_content_generator` unit tests, restore-prev-library direct-call test, `dispatch_dry_validate` retry/timeout unit test.
