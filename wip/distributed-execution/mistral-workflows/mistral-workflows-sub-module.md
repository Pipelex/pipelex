# Mistral Workflows ↔ Pipelex Plugin — Plan & Progress

Self-contained planning document. A fresh session can resume from this file
alone; no need to read prior conversation history.

For anything implemented (Phases 1.0–1.5), the code is authoritative. Read
`pipelex/plugins/mistralai_workflows/` and the matching tests under
`tests/{unit,integration}/pipelex/plugins/mistralai_workflows/`. The
user-facing reference lives at
`docs/under-the-hood/mistralai-workflows-{plugin,recipes}.md`.

---

## Status board

| Phase | Scope                                                  | Status |
| ----- | ------------------------------------------------------ | ------ |
| 1.0   | Framework-agnostic core (`bridge.py`, modes, ...)      | ✅ done |
| 1.1   | Tier-1 `pipelex_run_pipe` activity wrapper             | ✅ done |
| 1.2   | `TEMPORAL_BLOCKING` + `TEMPORAL_FIRE_AND_FORGET` modes | ✅ done |
| 1.3   | Docs + CHANGELOG (mkdocs nav wired)                    | ✅ done¹ |
| 1.5   | Large-payload `pipelex_run_pipe_offloaded` variant     | ✅ done |
| 2.0   | Streaming v1 — one Mistral `task()` per activity       | ✅ done |
| 2.1   | Streaming v2 — per-step `task.update()` (DIRECT only)  | ✅ done |

¹ Cookbook example deferred to a follow-up PR in the sibling
`pipelex-cookbook/` repo (suggested entry:
`examples/c_advanced/mistral-workflows/` with a Tier-1 DIRECT-mode worker
plus a Tier-2 typed activity that uses `library_crate_dump`).

### Outstanding from Phase 1 (not blocking Phase 2)

- [ ] `make agent-check` passes with `mistralai-workflows` NOT installed —
      needs a fresh venv without the extra. The guard placement
      (`activities.py` only; `bridge.py` / `execution_mode.py` /
      `bootstrap.py` / `exceptions.py` are import-clean) should make this
      pass; not yet verified end-to-end.
- [ ] CI matrix for the optional dep — deferred. CI runs
      `uv sync --all-extras`, so layer-2 and layer-3 tests already run on
      every PR. Reconsider when we add an extra whose tests must NOT run
      on the default lane.

---

## 1. Context

Integrate Pipelex with Mistral Workflows (`mistralai-workflows>=3.3.0`),
which wraps Temporal with a thicker DX layer. Two goals were considered:

- **Goal 1** — Port Pipelex orchestration to run *on* Mistral Workflows as
  an alternative durable runtime. Blocked on Mistral exposing extension
  hooks for payload converter, codec, sandbox passthrough, and a
  bare-Temporal `run_worker` mode. **Out of scope.** File issues with the
  Mistral team if/when we want to revisit.
- **Goal 2** — Let users invoke Pipelex pipes from inside their own
  Mistral Workflows activities. **In scope.** Phase 1.x complete; Phase 2
  pending.

The `mistralai-workflows` dependency must remain strictly optional.

---

## 2. Locked-in design decisions (still binding for Phase 2)

- **Library crate transport** is dump-based:
  `PipelexPipeRunInput.library_crate_dump: dict[str, Any] | None`.
- **Execution mode** is an exhaustive `StrEnum`, set per-call (not
  per-worker): `DIRECT`, `TEMPORAL_BLOCKING`, `TEMPORAL_FIRE_AND_FORGET`.
- **Streaming** is phased. Phase 2.0 ships a single Mistral `task()` per
  activity (started / completed / failed). Phase 2.1 ships per-step
  `task.update()` events driven by Pipelex's `report_delegate`,
  conditional on demand.
- **Plugin location**: `pipelex/plugins/mistralai_workflows/`.
- **Optional-dep guard** lives in `activities.py` (and will live in
  `streaming.py`). `__init__.py` is empty per Pipelex's "no re-exports"
  rule. `bridge.py`, `execution_mode.py`, `bootstrap.py`, `exceptions.py`
  are framework-agnostic and importable without `mistralai-workflows`.
- **Boundary types are JSON-only.** No Pipelex internal types (`PipeJob`,
  `PipeOutput`, `WorkingMemory`) cross the activity boundary.

---

## 3. Module layout

```
pipelex/plugins/mistralai_workflows/
├── __init__.py        # empty (no re-exports)
├── exceptions.py      # 4 exception classes
├── execution_mode.py  # PipelexExecutionMode StrEnum
├── bridge.py          # framework-agnostic core (NO mistralai imports)
├── bootstrap.py       # ensure_pipelex_booted() + DI helper
├── activities.py      # Tier-1 wrappers + offloaded variant
└── streaming.py       # Phase 2.0 — pipelex_run_pipe_streaming sibling activity

tests/unit/pipelex/plugins/mistralai_workflows/
├── test_input_models.py     # boundary BaseModels
├── test_execution_mode.py   # StrEnum properties
├── test_validation.py       # _validate_input + decode helpers
└── test_dispatch.py         # mode dispatch with mocked PipeRun

tests/integration/pipelex/plugins/mistralai_workflows/
├── conftest.py                              # bridge_test_library fixture
├── test_data/                               # bridge_test.mthds + bridge_funcs.py
├── test_bridge_direct.py                    # layer 1 (no optional dep)
├── test_activities_direct.py                # layer 2 (Mistral test worker)
├── test_activities_offloaded.py             # layer 2 — offloaded variant
├── test_activities_streaming.py             # layer 2 — Phase 2.0 streaming variant
├── test_bridge_temporal_blocking.py         # layer 3 (+ temporal extra)
└── test_bridge_temporal_fire_and_forget.py  # layer 3 (+ temporal extra)
```

Users import from full paths (no re-exports per Pipelex rule):

```python
from pipelex.plugins.mistralai_workflows.activities import (
    pipelex_run_pipe,
    pipelex_run_pipe_offloaded,
    PipelexPipeRunInputOffloaded,
    PipelexPipeRunOutputOffloaded,
)
from pipelex.plugins.mistralai_workflows.bridge import (
    PipelexPipeRunInput, PipelexPipeRunOutput, run_pipe_via_bridge,
)
from pipelex.plugins.mistralai_workflows.execution_mode import PipelexExecutionMode
from pipelex.plugins.mistralai_workflows.bootstrap import ensure_pipelex_booted
from pipelex.plugins.mistralai_workflows.streaming import (
    pipelex_run_pipe_streaming,
    PipelexPipeRunStreamingState,
    PIPELEX_PIPE_RUN_TASK_TYPE,
)
```

---

## 4. Gotchas from Phase 1 (read before Phase 2)

These bit during Phase 1.1–1.2 and will likely bite again when adding
`streaming.py` plus a new integration test module. Save the cycles.

1. **Workflow sandbox rejects Pipelex imports** seen during workflow
   class validation. Wrap them in
   `mistralai_workflows.workflow.unsafe.imports_passed_through()` AND
   pass `enforce_determinism=False` to `@workflow.define` for test
   workflows. See `test_activities_direct.py:24-30` for the pattern.
   Activities are unrestricted Python — this only matters inside
   workflow class bodies.

2. **`OtelTraceId` search attribute** must be pre-registered on the
   test namespace. Mistral's `@workflow.define` upserts it on every
   workflow run, and the dev server rejects activations against an
   unknown attribute. Pass
   `search_attributes=[SearchAttributeKey.for_keyword("OtelTraceId")]`
   to `WorkflowEnvironment.start_local`.

3. **Task queue mismatch.** Mistral's `@activity` wrapper schedules
   activities on the *global* `mistralai_config.temporal.task_queue`
   (default `"default"`), NOT the workflow's task queue. Spin a worker
   on a custom test queue without overriding the global → activities
   land on `"default"` and the workflow hangs forever. Fix: an autouse
   module-scoped fixture pinning
   `mistralai_config.temporal.task_queue = TEST_TASK_QUEUE` for the
   duration of the test module. See `test_activities_direct.py:48-64`.

4. **Result shape.** Mistral's `convert_result_to_temporal_format`
   wraps non-BaseModel return values in `{"result": ...}`. Return a
   BaseModel directly from the workflow entrypoint to skip the
   wrapping (we return `PipelexPipeRunOutput`).

5. **mypy + Mistral's PEP 695 type syntax.** `mistralai-workflows`'s
   own source uses PEP 695 type parameters that mypy rejects under
   `python_version=3.11`. The `[[tool.mypy.overrides]]` block for
   `mistralai.workflows.*` (`follow_imports = "skip"`,
   `ignore_errors = true`) in `pyproject.toml` is already in place.
   Mypy will still flag `OffloadableField.get_value()` as returning
   `Any` — assign through a typed intermediate variable.

6. **`PipeFunc` is NOT Temporal-compatible.** `asyncio.to_thread`
   inside `PipeFunc` raises `NotImplementedError` in the deterministic
   workflow event loop. The bundle ships `bridge_func_pipe` (PipeFunc,
   DIRECT only) for the no-Temporal layers and `bridge_compose_pipe`
   (PipeCompose, Temporal-compatible) for the Temporal layers; the
   `bridge_envelope_pipe` (PipeCompose with inline-structured concept)
   exists to exercise dynamic-concept round-trip via
   `library_crate_dump`. Pick the right one per execution mode.

7. **`Pipelex.make()` is NOT idempotent** — it raises if a singleton
   already exists. `bootstrap.ensure_pipelex_booted()` only calls it
   when `Pipelex.get_optional_instance() is None`, so an externally-
   booted singleton is adopted. Don't replace this guard with a
   module-level boolean.

---

## 5. Phase 2 — Streaming

Goal: surface live progress events from Pipelex pipes through Mistral's
`task()` event API so users can subscribe via
`create_capturing_mock_events_client` and friends.

### Phase 2.0 — One task per activity (started / completed / failed) ✅

A single Mistral task wraps the whole activity body — no per-step
granularity. Cheapest path to "the user sees something happen."

- [x] Created `pipelex/plugins/mistralai_workflows/streaming.py`. Reuses
      the same optional-dep guard pattern as `activities.py` (top-level
      `try`/`except ImportError` re-raising `MistralWorkflowsNotInstalledError`).
- [x] **Decision: sibling activity** `pipelex_run_pipe_streaming`. Reasons:
      - Keeps the silent path silent — Tier-1 users without observability
        needs don't pay event publishing overhead.
      - Mirrors the `pipelex_run_pipe_offloaded` sibling pattern.
      - Workers register only the variant they actually use.
- [x] Inside the activity: `async with Task[PipelexPipeRunStreamingState](...)`
      then call `run_pipe_via_bridge`, then `update_state` to `phase="completed"`.
      `Task.__aexit__` automatically emits `CustomTaskFailed` on exception
      and the original exception propagates — no extra `try`/`except`
      needed (per Pipelex "don't catch Exception speculatively" rule).
- [x] Layer-2 integration test
      `tests/integration/pipelex/plugins/mistralai_workflows/test_activities_streaming.py`
      uses `create_test_worker_with_events` + `EventContext` + a
      `create_capturing_mock_events_client` to assert that exactly one
      `CustomTaskStarted`, ≥1 `CustomTaskInProgress`, and one
      `CustomTaskCompleted` are emitted with the right `custom_task_type`
      (`pipelex.pipe_run`) and payload shape.

### Phase 2.1 — Per-step granularity (DIRECT mode only) ✅

- [x] Subscribe to Pipelex's trace event channel from inside the
      activity. Implemented as a queue-backed `EventLogProtocol`
      (`QueueEventLog` in `streaming_event_forwarder.py`) injected into a
      per-call `GraphTracerManager` tracer. Note: `ReportingProtocol`
      itself has no observer methods — the right abstraction is the
      event log, not the reporting delegate.
- [x] Map Pipelex events to Mistral `task.update_state(...)` calls:
      - `PipeStartEvent` → `in_progress` with `current_step_pipe_code`,
        `current_step_node_id`, `last_event_kind="pipe_start"`,
        `started_steps`.
      - `PipeEndSuccessEvent` → `in_progress` with
        `last_event_kind="pipe_end_success"`, `completed_steps`,
        `last_output_stuff_name`.
      - `PipeEndErrorEvent` → `in_progress` with
        `last_event_kind="pipe_end_error"`. The activity's
        `Task.__aexit__` then emits `CustomTaskFailed` with the
        propagated exception.
      - Other `TraceEventKind`s (edges, batch fan-out, controller
        outputs, execution data, usage reports) intentionally suppressed
        — too noisy for state updates, already captured by Pipelex's
        own reporting / graph infrastructure.
- [x] Forwarder side-task drains the event log and terminates cleanly
      on both success and failure. Uses `try` / `finally` (no
      `except Exception`); the forwarder is fully drained *before*
      writing the final `phase="completed"` state so the snapshot
      reflects the right phase.
- [x] Multi-step test fixture: `bridge_sequence_pipe` (PipeSequence)
      chaining `bridge_seq_step_one` and `bridge_seq_step_two`
      (PipeCompose). Test asserts ≥3 pipe_start + ≥3 pipe_end_success
      `CustomTaskInProgress` events with `started_steps` monotonic
      `[1, 2, 3]` and per-step pipe codes in declaration order.

Scope: DIRECT mode only. TEMPORAL_BLOCKING / TEMPORAL_FIRE_AND_FORGET
keep Phase 2.0 single-pair semantics — per-step streaming across the
Temporal worker boundary would need cross-process tee logic on top of
the existing `pipeline_run_setup` event log infra, deferred until demand
surfaces.

---

## 6. Open risks (track but don't block)

- [ ] Concurrent activities sharing process-global Pipelex state — already
      mitigated by per-call library scoping in
      `bridge.py::_scoped_library_for_crate`. Verify no leakage under
      concurrent load when we get there.
- [ ] If Mistral upgrades change the `OffloadableField` import path
      (currently `mistralai.workflows.core.encoding.fields_offloader`),
      revisit the imports in `activities.py`.

---

## 7. Resuming a session

1. Read this file end-to-end — it's short by design.
2. **For anything in Phase 1.x: the code is authoritative.** Read
   `pipelex/plugins/mistralai_workflows/*.py` and its tests; do not
   re-derive from this doc.
3. For Phase 2 work: start at §5, pick the first unchecked box, re-read
   §4 (gotchas) before scaffolding the new test module.
4. After each phase, run:
   ```
   make agent-check
   .venv/bin/pytest tests/unit/pipelex/plugins/mistralai_workflows/ \
                    tests/integration/pipelex/plugins/mistralai_workflows/
   ```
   Before declaring Phase 2 done, run the broader sweep:
   ```
   .venv/bin/pytest -n auto \
     -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" \
     tests/unit/pipelex/plugins/ tests/integration/pipelex/plugins/ \
     tests/unit/pipelex/builder/ tests/integration/pipelex/builder/
   ```
5. Update the status board and the §5 boxes as you go.
