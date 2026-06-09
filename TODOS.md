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
- [x] **(DECIDED) Graph dry-run shape = bridge DIRECT reuse.** Add an in-process/in-memory variant that runs the main pipe through the bridge DIRECT path (`run_pipe_via_bridge` DIRECT + `trace_context`) under `scoped_event_log`; do **not** refactor `PipelexRunner` to force DIRECT.
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
| 1 | `scoped_event_log` + shared in-memory tracing (in-repo, no Temporal) | ☐ not started |
| | **⛔ CHECKPOINT 1 — in-memory tracing verified in direct mode** | |
| 2 | In-process, in-memory graph dry-run safe under a Temporal hub (+ `scoped_content_generator`) | ☐ |
| | **⛔ CHECKPOINT 2 — graph dry-run verified under a Temporal hub** | |
| 3 | The `act_dry_validate` activity + wrapper-workflow dispatch + worker registration + isolation test | ☐ |
| | **⛔ CHECKPOINT 3 — activity registered + isolation-tested** | |
| 4 | API dispatch (cross-repo `pipelex-api`) | ☐ |
| | **⛔ CHECKPOINT F — all requirements met** | |
| G0 | *(optional, deferred)* `temporalio` bump → true standalone activity | ☐ later |

Status legend: ☐ not started · ◐ in progress · ☑ done. **No human gate remains** (dispatch = wrapper workflow).

---

## Phase 1 — `scoped_event_log` + shared in-memory tracing

Pure in-repo capability, no Temporal, no cross-repo. Fully testable in direct mode. **TDD: write the failing tests first.**

- [ ] *Tests first* (`tests/unit/pipelex/tracing/` + a direct-mode dry-run-with-graph integration test): assert that running a dry-run-with-graph under `with scoped_event_log(InMemoryEventLog())` (a) produces a non-empty, correct `GraphSpec`, (b) writes **no** NDJSON file and touches **no** configured backend, and (c) emit and assemble hit the **same** instance. Add a concurrency/nesting test: two concurrently-scoped in-memory logs don't cross-contaminate, and the override restores on exit.
- [ ] Add to `pipelex/hub.py` (mirroring `scoped_pipe_router`): `_event_log_override: ContextVar[EventLogProtocol | None]`, a `scoped_event_log(event_log)` `@contextmanager` (save/set/restore), and an accessor (e.g. `get_event_log_override()`).
- [ ] Make the **write side** prefer the override: in `pipeline_run_setup.py`, where it does `event_log = make_event_log(tracing_config)`, use the scoped override if set, else the factory. (Keep the `is_enabled` gate semantics sane — decide whether a scoped override implies enabled.)
- [ ] Make the **read side** prefer the override: in `tracing_assembly.py::assemble_tracing`, where it does `make_event_log(tracing_config)`, use the scoped override if set, else the factory. Mind the existing `tracing_config.is_enabled` early-return — an override must not be skipped by it.
- [ ] Confirm the `EventLogProtocol` surface is sufficient (`emit` / `read_events` / `next_sequence` / `close` / `cleanup`); no protocol change expected.
- [ ] `make agent-check` clean · relevant tracing tests green.

> ### ⛔ CHECKPOINT 1 — after Phase 1 — **MANDATORY STOP**
>
> A self-contained, separately reviewable in-repo capability. Natural place to split sessions and/or land alone.
>
> **Verify:** `make agent-check` clean · `make agent-test` green · the new in-memory-tracing tests pass (same-instance emit+read, zero file/backend, concurrency-safe) · commit.
>
> **Handoff (fill in):** final `scoped_event_log` signature + accessor name · exact write/read call-site edits (file:symbol) · the `is_enabled`-vs-override semantics decided · any `EventLogProtocol` change (expected: none). **Next: Phase 2.**

---

## Phase 2 — In-process, in-memory graph dry-run safe under a Temporal hub

Make the graph-producing dry-run run fully in-process even under a Temporal-enabled hub, tracing into the Phase-1 in-memory log. Reuse the bridge DIRECT primitive (it already forces in-process via `scoped_pipe_router` + a local `PipeRun`, and `run_pipe_via_bridge` already honors a `trace_context` in DIRECT mode).

- [ ] *Tests first* (`tests/integration/pipelex/temporal/`): under a **Temporal-enabled** hub, the in-process graph dry-run (a) returns a correct `GraphSpec`, (b) dispatches **zero** workflows/activities (spy `WorkflowExecutor.execute_workflow` like `test_validate_sweep_stays_in_process.py`), and (c) writes no files / touches no DDB.
- [ ] Add an in-process graph-dry-run entry (e.g. a sibling to `dry_run_pipeline` or a flag on it): open a `GraphTracerManager` tracer against an `InMemoryEventLog` under `scoped_event_log`, build the `trace_context`, and run the main pipe through the **bridge DIRECT path** (`run_pipe_via_bridge` DIRECT with `trace_context`) — **not** `PipelexRunner`/`get_pipe_run()`. The `GraphSpec` rides back on `PipeOutput` (assembled from the same in-memory log via Phase 1).
- [ ] **(per the pre-flight content-generator decision; default = do it now)** Add `scoped_content_generator(inline_generator)` in `hub.py` mirroring `scoped_pipe_router`, and wrap the in-process run in it so the leaf uses the inline `ContentGenerator` even under a Temporal-enabled hub (where `get_content_generator()` is globally `ContentGeneratorInWorkflow`). The Phase-2 zero-dispatch test must pass **with the leaf mock already at the leaf** (simulate Part B by forcing `run_mode=DRY` through `get_content_generator()`), not only with today's pipe-level mock — otherwise the guard is a no-op until Part B and silently regresses then.
- [ ] Confirm tracer-key alignment: emit and assemble must use the same `pipeline_run_id` / `tracer_key` partition (see `build_pipe_job_from_input`'s `lookup_key` note in `bridge.py`). Pin with a test.
- [ ] Keep `dry_run_pipeline`'s existing (worker-workflow + DynamoDB) path intact for now — the API still uses it until Phase 4.
- [ ] `make agent-check` clean · the zero-dispatch / in-memory-graph tests green.

> ### ⛔ CHECKPOINT 2 — after Phase 2 — **MANDATORY STOP**
>
> **Verify:** under a Temporal-enabled hub the in-process graph dry-run yields a `GraphSpec` with **zero** nested dispatch and **zero** file/DDB I/O · `make agent-test` green · commit.
>
> **Handoff (fill in):** the new entry point's name + signature · how it opens/closes the tracer and threads `trace_context` through the bridge · the tracer-key alignment decision · any divergence from `_run_direct` you had to make. **Next: Phase 3.**

---

## Phase 3 — The `act_dry_validate` activity + wrapper-workflow dispatch + registration + isolation test

Wrap the sweep + the in-memory graph dry-run in one activity, dispatched via a one-step wrapper workflow (DECIDED — no `temporalio` bump). No gate; runs straight through.

- [ ] Define the activity (proposed `pipelex/temporal/tprl_pipe/act_dry_validate.py`): body runs `BundleValidator` (sweep → status map) **and** the Phase-2 in-memory graph dry-run (→ `GraphSpec`), under `with scoped_event_log(InMemoryEventLog()):` + `scoped_content_generator(inline)`. **Graph is best-effort inside the activity:** catch the expected graph-dry-run failures (`PipelexError` per `validate.py`'s current contract) and return `graph=None` — a graph failure must NOT fail validation. Decorate with `convert_pipelex_errors` so genuine failures cross back as structured `ErrorReport`s.
- [ ] Inputs (serializable `BaseModel`): `mthds_contents` / `library_dirs` / `bundle_uris`, `allow_signatures`, optional `--pipe` selection. Output (serializable `BaseModel`): `{pipe_ref: DryRunOutput}` map + `GraphSpec | None` + aggregated signature-check error. (`DryRunOutput` already serializes; `GraphSpec` already crosses the boundary via `TracingAssembly`.)
- [ ] Add the one-step wrapper workflow (e.g. `wf_dry_validate.py`) that runs the single activity and returns its result — this is the dispatch unit the API awaits.
- [ ] Register the activity **and** the wrapper workflow in `pipelex/temporal/tasks.py` (`PackName.PIPE` `activity_list` / `workflow_list`).
- [ ] *Test in isolation* (`tests/integration/pipelex/temporal/`): a worker runs the wrapper-workflow→activity; assert the status map + `GraphSpec` are correct, **zero** nested activity/workflow dispatches occur during the run (spy `WorkflowExecutor.execute_activity`/`execute_workflow`), tracing stayed in memory, a graph-dry-run failure yields `graph=None` with validation still successful, and a forced *validation* failure crosses back as a structured `ErrorReport`. Concurrent invocations don't cross-contaminate the scoped overrides.
- [ ] **Distributed verification (REQUIRED) — add `temporal-e2e-validate` Tier 2d.** The 3-process (server + split workers + submitter) scenario that proves the contract in a real deployment, following the Tier 2c precedent. Full spec + GREEN/RED + master-table row: see [§ Distributed verification — `temporal-e2e-validate`](#distributed-verification--temporal-e2e-validate-mode-1--tier-2d) below.
- [ ] `make agent-check` clean · activity isolation tests green · Temporal e2e green (`temporal-e2e-validate` Tier 2d).

> ### ⛔ CHECKPOINT 3 — after Phase 3 — **MANDATORY STOP**
>
> **Verify:** activity + wrapper workflow registered + isolation-tested (status map + GraphSpec correct, zero nested dispatch, in-memory tracing, best-effort graph, structured error on validation failure) · **Tier 2d (activity arm) GREEN and RED-proven** in `temporal-e2e-validate` · `make agent-test` green · Temporal e2e green · commit.
>
> **Handoff (fill in):** final activity + wrapper-workflow names + input/output models · registration diff · anything that diverged from the plan. **Next: Phase 4.**

---

## Phase 4 — API dispatch (cross-repo `pipelex-api`)

- [ ] In `../pipelex-api/api/routes/pipelex/validate.py`: when Temporal is enabled, dispatch the **wrapper workflow** (→ `act_dry_validate`) and await `{status map, GraphSpec}` in one round-trip, instead of running `validate_bundle` + `dry_run_pipeline` as two paths (the latter a top-level worker workflow). In direct mode, keep the current in-process behavior unchanged. Preserve the best-effort-graph contract (graph failure ⇒ still return the validated bundle, no graph) and the 422/RFC-7807 error shape.
- [ ] Test both backends against the API (Temporal-enabled dispatches the activity and returns graph+status from one round-trip; direct stays in-process).
- [ ] **Distributed verification — extend Tier 2d with the API arm:** with the API process up + Temporal-enabled (+ split workers), a real `POST /validate` returns `{status map, graph_spec}` in one round-trip, the worker shows only the wrapper workflow + one `act_dry_validate` (no nested dispatch), and a bundle that fails its graph dry-run still returns 200 with `graph_spec=null` (best-effort). See the spec below.
- [ ] Update docs in the repo whose code changed (pipelex `docs/` for the activity/tracing; pipelex-api `docs/` for the route) + CHANGELOG `[Unreleased]`.

> ### ⛔ CHECKPOINT F — after Phase 4 — **ALL REQUIREMENTS MET**
>
> req 2 (production dry-run + validation as one in-process Temporal activity, in-memory tracing) · req 3 (direct in-process unchanged). req 1 is delivered by Part B, not here.
>
> **Verify:** `pipelex` `make agent-test` green · Temporal e2e green · **Tier 2d (activity + API arms) GREEN** · `pipelex-api` tests green on **both** backends · commit.
>
> **Handoff (fill in):** as-built summary (what each phase delivered, file:symbol) · how the API now dispatches · any follow-ups (e.g. retiring the old worker-workflow graph path once the activity path is proven; D-plan §7 endpoint unification). Then fold this into `wip/dry-run-refactor/consolidation-as-built.md` and the README open-follow-ups table.

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
