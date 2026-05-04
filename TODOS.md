# TODOS — P0 Tracing & Cost Reporting Across Separate-Process Workers

> **Source plan**: [`wip/02-master-plan.md`](wip/02-master-plan.md) §P0 (lines 25–51).
> **As-built reference**: [`wip/tracing-cost-reporting-as-built.md`](wip/tracing-cost-reporting-as-built.md) (issues T1, T2, T3).
> **Mode**: TDD — every behavioural change starts with a failing test.

---

## 1. Goal & non-goals

Make activities deployed on **standalone worker pools** (separate processes from the workflow worker pool) emit `UsageReportEvent`s into the same backend partition as the rest of the run, with no silent drops, no dependence on `WfPipeRouter` having executed in the activity's process, and no regression for the single-process / direct-mode paths.

**In scope**:

- Fix the runner-side `_emit_usage_event` silent drop (T1).
- Fix the `(workflow_id, sequence)` collision that surfaces the moment two separate processes emit into the same partition for the same Temporal workflow id (latent today, breaks immediately when activities split off).
- Replace the `_get_registry` auto-create TODO at `pipelex/reporting/reporting_manager.py:110-118` with the proper distributed path.
- Wire enough scaffolding for P1 (don't ship P1 here — but make P1 a one-step plumbing change).

**Out of scope (this round)**:

- P1 cost-report assembly wiring (tracked separately, depends on this).
- P2/P3 crate dependencies.
- Touching `BufferingEventLog` / `act_flush_trace_events` for events that are emitted from *inside* the workflow body — those still buffer + flush as today. Only the **activity-emitted** path changes.
- Any change to the `ContentGenerator` direct-mode path (it already runs in-process so the existing context lookup keeps working).

---

## 2. Acceptance criteria (verbatim from §P0, with test mapping)

| # | Criterion | Test that proves it |
|---|---|---|
| AC1 | Activities on standalone worker pools emit `UsageReportEvent`s that land in the same backend partition as the rest of the run | Integration: `TestSplitWorkerUsageEmission::test_runner_usage_event_lands_in_same_ndjson_dir` |
| AC2 | No reliance on `WfPipeRouter` having executed in the activity's process | Integration: same test, asserted by the substitute-activity that clears `_event_log_contexts` before the inference activity runs (simulates a cold runner process) |
| AC3 | No silent drops — if tracing is enabled, an activity that fails to emit raises or logs explicitly | Unit: `TestEmitDistributedFallback::test_explicit_log_when_emit_path_unavailable` (single warning, never silent), plus `test_explicit_raise_when_strict_mode` if we add strict mode |
| AC4 | Direct mode and current single-bundle worker mode keep working unchanged | Existing suites pass: `tests/integration/pipelex/temporal/tracing/`, `tests/unit/pipelex/reporting/test_reporting_event_emission.py`, `tests/unit/pipelex/tracing/` |
| AC5a | Standalone activity worker — usage captured | `TestSplitWorkerUsageEmission::test_runner_usage_event_lands_in_same_ndjson_dir` |
| AC5b | Mixed worker pool (some workflows + activities together, plus a separate runner) | `TestSplitWorkerUsageEmission::test_mixed_pool_no_duplicate_usage_events` |
| AC5c | Tracing disabled — no crashes, no events | `TestEmitDistributedFallback::test_disabled_tracing_skips_emit` |
| AC5d | Backend = NDJSON | All split-worker integration tests run with NDJSON config (default) |
| AC5e | Backend = DynamoDB | Unit-level: `TestDynamoDBWriterIdSchema::test_no_collision_when_two_writers_share_workflow_id` (with `moto`/stub) — full DDB e2e is gated behind `pytest -m dynamodb` |

---

## 3. Design — JobMetadata-driven, writer-id disambiguated

### 3.1 What changes conceptually

The fix has two independent parts. Keep them separate in commits and tests.

**Part A — Make the activity's `_emit_usage_event` self-sufficient**.

`ReportingManager._emit_usage_event` (`pipelex/reporting/reporting_manager.py:205-230`) currently drops silently if `_event_log_contexts.get(graph_context.lookup_key)` returns None. That dict is populated only by `WfPipeRouter.run()` (router-process) or `pipeline_run_setup` (direct mode). On a standalone runner process, the dict is permanently empty for every workflow.

The activity already has everything it needs on `inference_job.job_metadata`:

- `pipeline_run_id` → `inference_job.job_metadata.pipeline_run_id`
- `workflow_id` → `inference_job.job_metadata.graph_context.tracer_key` (set by `WfPipeRouter.run` line 86 to `wf_workflow_id` and propagated through `JobMetadata`)
- `node_id` → `inference_job.job_metadata.graph_context.parent_node_id`
- backend choice → `get_config().pipelex.tracing_config` (process-local config, identical on every worker)

So the fix is: when `_event_log_contexts.get(lookup_key)` misses, fall back to constructing (and caching) a per-process event log from `tracing_config` and emitting directly. The context lookup remains the fast path; the fallback covers the runner.

This means **no new field on JobMetadata is required** — the existing `graph_context.tracer_key` is the missing puzzle piece, and it's already populated by `WfPipeRouter.run`. We just stop silently dropping when the context lookup misses.

**Part B — Writer-id disambiguation in TraceEvent**.

If router process A emits a `PipeStartEvent(workflow_id=W, sequence=0)` and runner process B emits `UsageReportEvent(workflow_id=W, sequence=0)` for the same wrapping workflow, current backends collide:

- NDJSON: both write to `wf_{W}.ndjson` and the read-side dedup `(workflow_id, type, sequence)` keeps both *only because they are different types*. But two `UsageReportEvent`s from two writers with the same `(W, 0)` would be silently deduped to one — that's a real data-loss path.
- DynamoDB: SK is `EVENT#{W}#{0:010d}` — `PutItem` overwrites silently, real collision.

Add an optional field to `TraceEvent`:

```python
class TraceEvent(BaseModel):
    pipeline_run_id: str
    workflow_id: str
    writer_id: str = "primary"  # "primary" preserves existing files/SKs for migration
    timestamp: datetime
    sequence: int
```

Backend changes:

- NDJSON: file path becomes `wf_{workflow_id}__w_{writer_id}.ndjson` (when `writer_id != "primary"`, append `__w_{writer_id}` to keep existing file naming for the legacy single-writer case).
- DynamoDB: SK becomes `EVENT#{workflow_id}#{writer_id}#{sequence:010d}` (always include writer_id; use `"primary"` for the legacy path so existing rows are not invalidated by code change — separate migration concern but pragmatic default).
- Read-side dedup key: `(workflow_id, writer_id, type, sequence)`.
- Sort key: `(workflow_id, writer_id, sequence)`.

Each `EventLogProtocol` instance carries an immutable `writer_id`:

- `BufferingEventLog(writer_id="primary")` — legacy, used by the workflow body (router process).
- New `make_event_log_for_activity(tracing_config, writer_id=...)` factory used by the activity-side fallback in (A). The runner generates a stable per-process `writer_id = f"act_{os.getpid()}_{uuid4().hex[:8]}"` once at module-import time and reuses it for every emit on that process.

This decouples sequence counters: each process has its own monotonic counter inside its own writer namespace, and dedup is correct.

### 3.2 New methods / files

| File | Change |
|---|---|
| `pipelex/tracing/trace_events.py` | Add `writer_id: str = "primary"` to `TraceEvent` base. |
| `pipelex/tracing/event_log_protocol.py` | Add `writer_id: str` property (read-only) and document the `(workflow_id, writer_id, sequence)` uniqueness contract. |
| `pipelex/tracing/buffering_event_log.py` | Add `writer_id` ctor arg, default `"primary"`. Stamp it on every emitted event. |
| `pipelex/tracing/ndjson_event_log.py` | (a) Add `writer_id` ctor arg. (b) File name becomes `wf_{workflow_id}__w_{writer_id}.ndjson` when `writer_id != "primary"`. (c) Read-side dedup key adds writer_id; sort key adds writer_id. |
| `pipelex/tracing/dynamodb_event_log.py` | (a) Add `writer_id` ctor arg. (b) SK becomes `EVENT#{workflow_id}#{writer_id}#{sequence:010d}`. (c) Item stores `writer_id` for query convenience. |
| `pipelex/tracing/event_log_factory.py` | New `make_event_log(tracing_config, writer_id="primary") -> EventLogProtocol`. Existing callers default to `"primary"` (zero behaviour change). |
| `pipelex/tracing/activity_event_log.py` (new) | Process-local cache: `get_or_create_activity_event_log(tracing_config) -> EventLogProtocol`. Generates a stable per-process `writer_id` once, reuses the backend instance. Closes on `atexit`. |
| `pipelex/reporting/reporting_manager.py` | `_emit_usage_event` fallback path: when context lookup misses, if `tracing_config.is_enabled` and `graph_context.tracer_key` is set, emit via `get_or_create_activity_event_log` using `tracer_key` as `workflow_id`. Log a single one-shot warning the first time the fallback fires (so we know it engaged in production). |
| `pipelex/reporting/reporting_manager.py` | Replace the `_get_registry` auto-create branch with: log a single warning, return a transient `UsageRegistry` that is **not** stored in `_usage_registries`, so direct-mode and the router still work but the runner doesn't accumulate orphan registries. (P1 will then read events back, aggregate, and `inject_tokens_usages` on the API process — no registry churn on workers.) |
| `pipelex/reporting/reporting_protocol.py` | Document that `_get_registry`'s auto-create behaviour is gone for the runner; the protocol surface is unchanged. |

### 3.3 Why not `TracingActivityInboundInterceptor`

The interceptor design from the original Phase 4.5 Step 6 plan would also work, but the JobMetadata-plumbing approach has three concrete advantages here:

1. **Data is already there.** `tracer_key` is propagated since `WfPipeRouter.run` line 86 — we'd be adding an interceptor only to read what's already on the activity's input.
2. **No Temporal SDK dependency in `pipelex.reporting.*`.** The interceptor would force `pipelex.reporting` to import Temporal types or live behind an indirection. The fallback in `_emit_usage_event` is plain Python.
3. **The same code path covers direct mode** (where tracing is configured but the runner-side context still works — fallback never engages).

If we later want the cleanliness of an interceptor, it's an additive change on top of this fix.

---

## 4. TDD plan — order of work

Each step lists: tests to write **first** (red), then the change that turns them green. Run `make agent-check` after every step. Run `make agent-test` at the end of each phase.

### Phase 0 — Reproduce the bug

**0.1** Write `tests/unit/pipelex/reporting/test_emit_distributed_fallback.py::TestEmitDistributedFallback::test_runner_with_no_context_drops_silently_today`. Build a `ReportingManager`, do **not** call `set_event_log`, build an `LLMJob` with a populated `graph_context` (with `tracer_key="wf_xyz"`, `parent_node_id="...:node_3"`), call `report_inference_job`, assert nothing was emitted anywhere. This documents current behaviour and pins it. Mark with `xfail(reason="bug T1, fix in step 1.x")` and flip to `assert "fallback emitted"` once the fix lands.

(One test, no LLM, sub-second.)

### Phase 1 — Writer-id schema (foundation for both A and B)

**1.1** *Red.* `tests/unit/pipelex/tracing/test_writer_id_schema.py::TestWriterIdSchema`:

- `test_trace_event_has_writer_id_default_primary` — round-trip JSON of a hand-built event, assert `"writer_id": "primary"`.
- `test_two_writers_same_workflow_dedup_keeps_both` — emit `UsageReportEvent(workflow_id="W", writer_id="a", sequence=0)` and `(... writer_id="b", sequence=0)` to an `InMemoryEventLog`, read back, assert two events. (Currently dedup would keep them because type+seq differ across emits, but harden the contract.)
- `test_ndjson_writer_id_in_filename_for_non_primary` — emit to `NdjsonEventLog(traces_dir=tmp, writer_id="act_pid42")`, assert file `wf_W__w_act_pid42.ndjson` exists; emit again with `writer_id="primary"`, assert legacy file name `wf_W.ndjson` exists (no breaking change).
- `test_ndjson_dedup_uses_writer_id` — write two events to two different writer files for same `(workflow_id, sequence)`, read back, assert both present.
- `test_dynamodb_sk_includes_writer_id` — unit test against a stubbed boto3 table (`pytest-mock` MockerFixture, not unittest.mock), assert PutItem SK is `EVENT#W#act_pid42#0000000000`.

**1.2** *Green.* Add `writer_id: str = "primary"` to `TraceEvent`. Thread it through `BufferingEventLog`, `NdjsonEventLog`, `DynamoDBEventLog`, `InMemoryEventLog`, `event_log_factory.make_event_log`. Update read-side dedup key to `(workflow_id, writer_id, type, sequence)` and sort key to `(workflow_id, writer_id, sequence)`. Default `"primary"` keeps every existing test green.

**1.3** *Regression check.* Re-run `tests/unit/pipelex/tracing/`, `tests/unit/pipelex/reporting/`, `tests/integration/pipelex/temporal/tracing/` — all must still pass. NDJSON files for the legacy path keep their old names, DDB rows for legacy path get `"primary"` in their SK (one-time schema bump documented in CHANGELOG.md `[Unreleased]`).

### Phase 2 — Activity-side fallback in `_emit_usage_event`

**2.1** *Red.* `tests/unit/pipelex/reporting/test_emit_distributed_fallback.py::TestEmitDistributedFallback`:

- `test_fallback_engages_when_context_missing_and_tracing_enabled` — `ReportingManager` with no `set_event_log` call. Mock `get_config().pipelex.tracing_config.is_enabled=True` and point NDJSON traces_dir to `tmp_path`. Build an `LLMJob` with `graph_context.tracer_key="wf_xyz"`, `pipeline_run_id="run_abc"`, `parent_node_id="g:node_2"`. Call `report_inference_job`. Assert one NDJSON file under `tmp_path/run_abc/wf_wf_xyz__w_act_*.ndjson` containing one `UsageReportEvent` with the right node_id, workflow_id, pipeline_run_id, tokens_usage.
- `test_fallback_caches_event_log_per_process` — call `report_inference_job` twice; assert only one event log instance was constructed (use `mocker.spy` on `make_event_log`).
- `test_disabled_tracing_skips_emit` — `is_enabled=False`, no event log file is created, no warning raised, registry still gets the usage (so the "console cost report" still works in dev).
- `test_no_graph_context_skips_emit` — `graph_context=None`, no fallback. Existing test already covers this with context registered; add the no-context-no-fallback variant.
- `test_no_tracer_key_skips_fallback` — `graph_context.tracer_key=None` (i.e. an old-style direct-mode context where the lookup key is `graph_id` itself). Falls back to graph_id as workflow_id (so we don't lose events).
- `test_explicit_log_when_emit_path_unavailable` — `tracing_config.is_enabled=True` but `make_event_log` raises (e.g., NDJSON dir is unwritable). Assert exception propagates *or* gets logged loudly (decision: log + drop with WARNING; raising would tank the inference response. **Single warning** so we don't spam.)
- `test_warning_emitted_once_per_process_when_fallback_engages` — call 100 times, assert only the first call emitted the "fallback engaged" warning.

(All sub-second; no LLM.)

**2.2** *Green.* Implement `pipelex/tracing/activity_event_log.py` with:

```python
def get_or_create_activity_event_log(
    tracing_config: TracingConfig,
) -> EventLogProtocol | None:
    """Process-local cached event log for runner-side activity emission.

    Returns None when tracing is disabled. Generates a stable
    per-process writer_id once and reuses it for every emit.
    """
```

Implement the fallback inside `_emit_usage_event`:

```python
def _emit_usage_event(self, inference_job, tokens_usage):
    graph_context = inference_job.job_metadata.graph_context
    if graph_context is None:
        return

    context = self._event_log_contexts.get(graph_context.lookup_key)
    if context is not None:
        # Fast path: process configured this workflow's event log
        # (router process or direct mode). Emit through the cached event log.
        ...existing emit...
        return

    # Fallback: runner process — context was never registered here.
    # Emit through a process-local event log built from tracing_config.
    self._emit_usage_event_distributed(
        inference_job=inference_job,
        tokens_usage=tokens_usage,
        graph_context=graph_context,
    )
```

The fallback method:

- Reads `tracing_config = get_config().pipelex.tracing_config`.
- If not enabled → return.
- `event_log = get_or_create_activity_event_log(tracing_config)` → if None, return.
- `workflow_id = graph_context.tracer_key or graph_context.graph_id`.
- `node_id = graph_context.parent_node_id or "unknown"`.
- Build `UsageReportEvent(pipeline_run_id=job_metadata.pipeline_run_id, workflow_id=workflow_id, writer_id=event_log.writer_id, sequence=event_log.next_sequence(), node_id=node_id, tokens_usage=tokens_usage, timestamp=...)`.
- `event_log.emit(event)`.
- One-shot warning logged the first time per process.

Flip the `xfail` from Phase 0 to a real assertion.

### Phase 3 — Replace `_get_registry` orphan auto-create

**3.1** *Red.* `tests/unit/pipelex/reporting/test_no_orphan_registries.py::TestNoOrphanRegistries`:

- `test_runner_does_not_accumulate_registries` — Build a `ReportingManager`, do **not** call `open_registry`. Call `report_inference_job` with `pipeline_run_id="never_opened"`. Assert `_usage_registries` does **not** contain `"never_opened"` afterwards (no orphan accumulation on runner). The usage event still emitted via the fallback (Phase 2), but no registry sat behind.
- `test_direct_mode_still_accumulates_registry` — `open_registry("run_x")` then `report_inference_job` with `pipeline_run_id="run_x"`, assert registry has the usage record.

**3.2** *Green.* Refactor `_get_registry` (`reporting_manager.py:110-118`) into:

```python
def _get_registry(self, pipeline_run_id: str) -> UsageRegistry:
    return self._usage_registries[pipeline_run_id]

def _get_or_create_local_registry_for_console(self, pipeline_run_id: str) -> UsageRegistry:
    """For the local 'log_costs_to_console' path only."""
    if pipeline_run_id not in self._usage_registries:
        self._usage_registries[pipeline_run_id] = UsageRegistry()
    return self._usage_registries[pipeline_run_id]
```

Update `_report_llm_job` / `_report_img_gen_job` / `_report_extract_job` / `_report_search_job` to:

- Always emit the usage event (fallback covers runner).
- Only `add_tokens_usage` to the local registry **if the registry exists** (i.e. `open_registry` was called on this process — direct mode or router). Don't auto-create.
- Keep the console cost-report path unchanged for dev ergonomics.

This kills the silent orphan-registry accumulation and the TODO comment.

### Phase 4 — Integration: split-worker temporal test (in-process, scoped workers)

This phase uses the **worker-scopes mechanism** to run two `Worker` instances inside the same pytest process — one with `disable_all_activities=true` (router) and one with `disable_all_workflows=true` (runner) — both polling the same task queue. Within a single process the singleton `ReportingManager` is shared, so the runner-side activity would **normally** still see the context the router populated, masking the bug. We deliberately defeat that by substituting the inference activity with a wrapper that clears `_event_log_contexts` on the way in (simulating a cold runner process).

**4.1** *Red.* `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py::TestSplitWorkerUsageEmission`:

```python
@pytest.mark.temporal
@pytest.mark.gha_disabled  # match existing tracing tests' policy until xdist flake is fixed
@pytest.mark.asyncio(loop_scope="class")
class TestSplitWorkerUsageEmission:

    async def test_runner_usage_event_lands_in_same_ndjson_dir(
        self,
        sequence_tracing_job: PipeJob,    # already exists, dry_run friendly
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ):
        """Activity running on a 'runner' scope (no router context registered
        for this workflow) still emits its UsageReportEvent into the same
        traces_dir partition as the workflow-side events.
        """
        ...
```

The fixture work this needs:

- `make_split_workers(temporal_client, task_queue) -> AsyncContextManager` helper in `tests/integration/pipelex/temporal/tracing/helpers.py` that opens **two** workers on the same task queue: one with `WorkerScope(required_tasks_packs=["pipe","crafting"], disable_all_activities=True)` and one with `disable_all_workflows=True`. Reuses `get_task_manager().make_worker(...)` with `scope=...` and `substitute_activities=...`.
- `_simulate_runner_isolation(real_activity)` decorator that wraps an `@activity.defn` to clear `get_report_delegate()._event_log_contexts` at the start of each invocation (only when called from the runner-scope worker — keyed off Temporal's `activity.info().workflow_id` not being in the dict). The substitution is wired only on the runner-scope worker.

Assertions:

- `ndjson_files_for_run(traces_dir, run_id)` returns ≥ 2 files: the router-side `wf_{wf_id}.ndjson` (from `act_flush_trace_events`) **and** at least one `wf_{wf_id}__w_act_*.ndjson` from the runner.
- `read_events(run_id)` contains both `PipeStartEvent`s and `UsageReportEvent`s, no duplicates.

**4.2** *Red.* `test_mixed_pool_no_duplicate_usage_events`: open three workers on the same queue — `full` scope, `router` scope, `runner` scope. Submit one workflow, assert exactly one `UsageReportEvent` per inference call (the `full` worker's local context plus the runner's fallback must not double-emit).

The key invariant: `_emit_usage_event` takes the fast path *or* the fallback path, never both.

**4.3** *Green.* Phases 1–3 should be enough. If `test_mixed_pool_no_duplicate_usage_events` fails because the in-process `full` worker registers the context for one workflow id but the runner-scope substitute happens to clear it after it was registered, tighten the simulator.

### Phase 5 — Removed clutter & docs

**5.1** Remove the `_get_registry` TODO comment at `reporting_manager.py:110-118` (no longer applies).
**5.2** Add CHANGELOG.md entry under `[Unreleased]`:
   ```
   ### Changed
   - Tracing: `TraceEvent` gains a `writer_id` field (default `"primary"`) so
     standalone activity workers can emit into the same backend partition as
     workflow workers without colliding on `(workflow_id, sequence)`.
   - DynamoDB sort key format updated to `EVENT#{workflow_id}#{writer_id}#{sequence:010d}`.
     Existing rows are unaffected (legacy emissions write `writer_id="primary"`).
   ### Fixed
   - `ReportingManager` now emits `UsageReportEvent`s from activities running on
     standalone worker processes (fixes silent drop on runner scope).
   ```
**5.3** Update `wip/tracing-cost-reporting-as-built.md` "What is broken or missing" → mark T1 as fixed (with a forward link to this work). Leave T2 (P1) and T3 (T1 partially mitigates T3 — fully resolved when P1 lands).
**5.4** Update `wip/02-master-plan.md` Priority order table: P0 → "In progress" → "Done" once Phase 6 passes.

### Phase 6 — End-to-end validation via the temporal-e2e-validate skill

Run the existing `/temporal-e2e-validate` skill in **Mode 2 (3-process)** — `temporal-worker-router` + `temporal-worker-runner` + submitter. This is the only setup that proves "true separate Python processes; runner has its own ReportingManager that was never told about this workflow".

**6.1** Run Tier 1 (`native_text_sequence`) and Tier 3 (`temporal_parallel`) in dry-run mode with tracing enabled. Inspect `.pipelex/traces/{run_id}/`:

- Expect ≥ 2 NDJSON files per run: `wf_{router_wf_id}.ndjson` and `wf_{router_wf_id}__w_act_{runner_pid}_{uuid}.ndjson`.
- Expect at least one `UsageReportEvent` from the runner file (PipeLLM dispatches inference activities even in dry-run; the dry-run worker still calls `reporting_delegate.report_inference_job` with mock usage).

If the dry-run path doesn't actually call `report_inference_job` (worth checking — `content_generator_dry.py` may skip reporting), repeat in **live mode** for one canonical test (`native_text_sequence` is cheap — one cheap LLM call).

**6.2** Add a new tier "Tier 8 — Cross-worker usage emission" to `.claude/skills/temporal-e2e-validate/SKILL.md`. Document:

- Run the Tier 8 command (the existing `native_text_sequence` is fine, just `--temporal --no-logo --graph` in live mode against router+runner workers).
- After the run, `ls .pipelex/traces/{run_id}/` should show both writer-id'd and primary NDJSON files.
- `grep '"event_kind":"usage_report"' .pipelex/traces/{run_id}/*.ndjson` should return the inference's usage events; assert the writer_id field on those events is `act_*`, not `primary`.

**6.3** (Stretch / optional, gated on P1 readiness) Add a Tier 9 that asserts the cost report is now non-empty for the cross-worker run by running `pipelex run bundle ... --no-logo --graph` and inspecting the auto-generated cost report file under `cost_report_dir_path`.

---

## 5. Test inventory (single source of truth)

| Layer | File | New / changed | Phases |
|---|---|---|---|
| Unit | `tests/unit/pipelex/tracing/test_writer_id_schema.py` | new (TestWriterIdSchema, ~6 cases) | 1 |
| Unit | `tests/unit/pipelex/reporting/test_emit_distributed_fallback.py` | new (TestEmitDistributedFallback, ~7 cases) | 0 + 2 |
| Unit | `tests/unit/pipelex/reporting/test_no_orphan_registries.py` | new (TestNoOrphanRegistries, ~3 cases) | 3 |
| Unit | `tests/unit/pipelex/reporting/test_reporting_event_emission.py` | edit — add writer_id assertions to existing tests; verify per-context isolation still holds | 1 |
| Unit | `tests/unit/pipelex/tracing/test_ndjson_event_log.py` | edit — file naming / dedup / sort tests for writer_id | 1 |
| Unit | `tests/unit/pipelex/tracing/test_ndjson_dedup_assembly.py` | edit — dedup key includes writer_id | 1 |
| Unit | `tests/unit/pipelex/tracing/test_in_memory_event_log.py` | edit — InMemoryEventLog gains writer_id | 1 |
| Integration | `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py` | new (TestSplitWorkerUsageEmission, 2 cases) | 4 |
| Integration | `tests/integration/pipelex/temporal/tracing/helpers.py` | add `make_split_workers`, `simulate_runner_isolation` | 4 |
| E2E | `.claude/skills/temporal-e2e-validate/SKILL.md` | add Tier 8 (Tier 9 optional) | 6 |

**Constraint reminders (CLAUDE.md)**:

- One `TestX` class per module — every new test file gets exactly one class.
- Use `pytest-mock`'s `MockerFixture`, never `unittest.mock`.
- Markers: `@pytest.mark.temporal` for the integration class; `@pytest.mark.asyncio(loop_scope="class")` if async; `gha_disabled` to match the existing tracing-tests policy until xdist flake is fixed.
- Fixtures in `conftest.py` at the appropriate level (the new helpers go in `tests/integration/pipelex/temporal/tracing/helpers.py`, fixtures in `conftest.py` next to it).

---

## 6. Implementation order — atomic commits

Each commit is independently green (`make agent-check && make agent-test`). Commit messages follow the existing conventional style.

1. `test: pin current runner-side silent-drop behaviour (xfail)` — Phase 0.
2. `feat: add writer_id field to TraceEvent and propagate through event log backends` — Phase 1, all unit tests for writer_id pass, all existing tracing tests pass.
3. `feat: runner-side usage event emission via per-process activity event log` — Phase 2, flips the xfail to green, fallback path covered.
4. `refactor: stop auto-creating orphan UsageRegistry on runner processes` — Phase 3, removes the TODO at `reporting_manager.py:116`.
5. `test(integration): split-worker temporal test for cross-process usage emission` — Phase 4.
6. `docs: changelog + as-built/master-plan updates for P0` — Phase 5.
7. (Optional, separate) `docs(skills): add Tier 8 cross-worker usage emission to temporal-e2e-validate` — Phase 6.

---

## 7. Risks, open questions, and explicit non-decisions

**R1 — Process-local writer_id vs. activity-execution-attempt-local writer_id.**
Per-process is right when the runner pool is stable. If the runner is killed and restarted mid-pipeline, a fresh writer_id is generated on the new process and we keep two writer files for the same workflow_id. That's the *correct* behaviour (no collision) and the assembler handles the union fine.

**R2 — Temporal activity retries.**
A retried activity re-emits the `UsageReportEvent`. Today's NDJSON dedup is `(workflow_id, sequence)`; with `writer_id` added we get `(workflow_id, writer_id, sequence)`. As long as the same process retries (same writer_id) the dedup still works because the sequence is reused — **except** the per-process counter increments on every emit, even retries. So a retry would emit at sequence N+1 instead of N, and dedup wouldn't fire. This is identical to today's behaviour for `BufferingEventLog` (fresh buffer on each replay; sequence resets), and the read-side already accepts duplicates from retries because the underlying tokens were really billed twice. **Decision**: keep current behaviour, document the over-counting risk in the docstring of `_emit_usage_event_distributed`. Suppression of retried-emit duplicates is a separate, harder problem (T3 / future).

**R3 — Boto3 inside an activity.**
The DynamoDB backend uses synchronous boto3. An activity is allowed to do synchronous I/O (unlike a workflow), so this is fine, but each activity invocation that emits a usage event makes one PutItem (or one NDJSON file write). For high-throughput runners this is non-trivial. We accept the cost in this round; batching is an obvious follow-up if the runner becomes a bottleneck.

**R4 — Direct mode regression.**
Direct mode populates `_event_log_contexts` via `pipeline_run_setup.py:282`, so the fallback in `_emit_usage_event` should *never* engage in direct mode. Phase 2's `test_fallback_caches_event_log_per_process` is the canary — if direct mode tests start touching the per-process activity event log, that's the bug.

**R5 — DynamoDB SK schema migration.**
The new SK includes `writer_id`. New rows under `"primary"` are still queryable by old readers that only `Query` on PK (the SK is part of the row but not part of the KeyConditionExpression in `read_events`). External consumers (e.g. `pipelex-api-infra`'s `TraceEventDynamoDBAdapter`) need a heads-up. **Decision**: document in CHANGELOG; if the api-infra side hard-codes the SK pattern, file a separate issue and do not block this PR on it (we own both repos).

**R6 — Why not raise in the silent-drop case?**
Today it's silent. We could raise instead. Raising inside `report_inference_job` would tank the calling pipe — the LLM call already succeeded, the user paid for tokens, it would be perverse to fail the pipeline because we couldn't log the cost. **Decision**: log a single warning per process when the fallback engages, and a WARNING (not ERROR) when even the fallback path can't emit (e.g. NDJSON path unwritable). Add a `tracing_config.strict_mode: bool` later if anyone wants raise-on-emit-failure semantics.

**R7 — `tracer_key` populated by *every* path that emits?**
`WfPipeRouter.run` populates it. `pipeline_run_setup` populates it implicitly (`graph_context.lookup_key` falls back to `graph_id`). Need to audit `pipe_run_setup` in direct mode and the parent-context path in nested workflows to confirm `tracer_key` is always either set or safely substituted by `graph_id`. The fallback uses `graph_context.tracer_key or graph_context.graph_id` so we're robust either way, but the fallback test set should cover both branches explicitly (covered by `test_no_tracer_key_skips_fallback`).

---

## 8. Out of scope (explicitly deferred)

- **P1 (cost report assembly wiring)**: read events → `UsageAggregator.aggregate()` → `ReportingManager.inject_tokens_usages()` → `generate_report()`. Listed at master plan §P1. This work makes that one-step plumbing change possible — do it next, in a separate PR.
- **Real-time consumer / live progress** (Step 5 of the original `distributed-tracing-and-reporting.md`).
- **Phase 6a / 6b crate dependencies** — independent track.
- **Strict-mode raise-on-emit-failure** — flag for future.
- **Retried-activity duplicate suppression** — see R2; needs a deeper rethink of the sequence space.
