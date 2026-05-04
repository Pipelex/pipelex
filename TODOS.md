# TODOS — P0 Tracing & Cost Reporting Across Separate-Process Workers

> **Source plan**: [`wip/02-master-plan.md`](wip/02-master-plan.md) §P0 (lines 25–51).
> **As-built reference**: [`wip/tracing-cost-reporting-as-built.md`](wip/tracing-cost-reporting-as-built.md) (issues T1, T2, T3).
> **Mode**: TDD — every behavioural change starts with a failing test.
> **Last reviewed**: 2026-05-04 via `/plan-eng-review`. Decisions logged: A1=sequence-primary sort, A3=two-task-queue split-worker test, A5=ContentGeneratorDry hooked to reporting, A6=threading.Lock for activity event log, C1=three-method registry split, C2=emitter constructs writer_id, T1=fresh tests (no xfail flip), T2=concurrency barrier test, T3=R2 retry over-counting pinned. Three new follow-on TODOs filed under §8.

---

## 0. Progress overview

High-level tracker. Each phase has a per-phase checklist with finer-grained sub-tasks; see §4. Test-file-level tracking lives in §5; commit-level tracking lives in §6.

- [x] **Phase 0** — Pin baseline (1 test)
- [x] **Phase 1** — Writer-id schema (8 tests + propagation)
- [x] **Phase 2** — Activity-side fallback (11 tests + new module + dry-run hook)
- [x] **Phase 3** — `_get_registry` three-method split (5 tests)
- [x] **Phase 4** — Split-worker integration test (2 tests + helpers, **prereq Q-Phase4**)
- [x] **Phase 5** — Docs + changelog + cleanup (5 tasks)
- [x] **Phase 6** — Skill-level e2e Tier 8 (Tier 8 added to SKILL.md; dry-run path finding documented; 6.3/6.4 deferred)
- [x] **Lint/test gate before each commit:** `make agent-check && make agent-test` green
- [x] **All acceptance criteria checked** (see §2)
- [x] **Master plan updated** (P0 → Done in `wip/02-master-plan.md`)

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

| # | Done | Criterion | Test that proves it |
|---|---|---|---|
| AC1 | [x] | Activities on standalone worker pools emit `UsageReportEvent`s that land in the same backend partition as the rest of the run | Integration: `TestSplitWorkerUsageEmission::test_runner_usage_event_lands_in_same_ndjson_dir` |
| AC2 | [x] | No reliance on `WfPipeRouter` having executed in the activity's process | Integration: same test, asserted by the substitute-activity that clears `_event_log_contexts` before the inference activity runs (simulates a cold runner process) |
| AC3 | [x] | No silent drops — if tracing is enabled, an activity that fails to emit raises or logs explicitly | Unit: `TestEmitRunnerFallback::test_explicit_log_when_emit_path_unavailable` (single warning, never silent); strict mode deferred to follow-up §8 |
| AC4 | [x] | Direct mode and current single-bundle worker mode keep working unchanged | Existing suites pass: `tests/integration/pipelex/temporal/tracing/`, `tests/unit/pipelex/reporting/test_reporting_event_emission.py`, `tests/unit/pipelex/tracing/` |
| AC5a | [x] | Standalone activity worker — usage captured | `TestSplitWorkerUsageEmission::test_runner_usage_event_lands_in_same_ndjson_dir` |
| AC5b | [x] | Split worker pool (router queue + runner queue, no double-emit) | `TestSplitWorkerUsageEmission::test_no_double_emit_in_split_worker_pool` |
| AC5c | [x] | Tracing disabled — no crashes, no events | `TestEmitRunnerFallback::test_disabled_tracing_skips_emit` |
| AC5d | [x] | Backend = NDJSON | All split-worker integration tests run with NDJSON config (default) |
| AC5e | [x] | Backend = DynamoDB | Unit-level: `TestWriterIdSchema::test_dynamodb_sk_includes_writer_id` (with `pytest-mock` stub) — full DDB e2e is gated behind `pytest -m dynamodb` |

---

## 3. Design — JobMetadata-driven, writer-id disambiguated

### 3.0 Data flow (after fix, ASCII)

```
┌──────────────────────────── Workflow Worker (router) ──────────────────────────────┐
│                                                                                    │
│  WfPipeRouter.run                                                                  │
│   ├─ tracing_config.is_enabled = true                                              │
│   ├─ event_log = BufferingEventLog(writer_id="primary")                            │
│   ├─ get_report_delegate().set_event_log(                                          │
│   │      context_key=wf_workflow_id, event_log=…, workflow_id=wf_workflow_id, …)   │
│   ├─ wf_graph_context.tracer_key = wf_workflow_id  ───────────────┐                │
│   │                                                               │ tracer_key on  │
│   ├─ pipe.run_pipe(job_metadata=…, …)  ───────► dispatches ───────┼─► JobMetadata  │
│   │     buffers PipeStartEvent / EdgeEvent / … via emit()         │                │
│   │     (writer_id="primary", per-writer seq 0,1,2…)              │                │
│   │                                                               │                │
│   └─ finally: drain() → act_flush_trace_events(events=[…])        │                │
│                                                                   │                │
└───────────────────────────────────────────────────────────────────┼────────────────┘
                                                                    │
                                                                    ▼
┌──────────────────────────── Activity Runner Pool (separate process) ───────────────┐
│                                                                                    │
│  act_llm_gen_text(arg=LLMJob(job_metadata=… graph_context.tracer_key=wf_xyz, …))   │
│   └─ LLMWorker.work()                                                              │
│       ├─ HTTP to OpenAI / Anthropic / …                                            │
│       └─ self.reporting_delegate.report_inference_job(llm_job)                     │
│            └─ ReportingManager._report_llm_job                                     │
│                ├─ try: _get_registry_strict(run).add_tokens_usage(…)               │
│                │      except KeyError: pass    ← runner case (registry not opened) │
│                └─ self._emit_usage_event(llm_job, llm_tokens_usage)                │
│                     ├─ context = _event_log_contexts.get(graph_context.lookup_key) │
│                     ├─ if context is not None: emit fast path                      │
│                     │      (router process; never reached here on the runner)      │
│                     └─ else: _emit_usage_event_runner_fallback                     │
│                           ├─ tracing_config.is_enabled? → no? return               │
│                           ├─ event_log = get_or_create_activity_event_log(cfg)     │
│                           │     │                                                  │
│                           │     ├─ first call: with _lock → check → make_event_log │
│                           │     │     (cfg, writer_id="act_{pid}_{uuid8}") → cache │
│                           │     └─ subsequent: cached instance (lock-free fast path)│
│                           ├─ workflow_id = ctx.tracer_key or ctx.graph_id          │
│                           ├─ event = UsageReportEvent(workflow_id=workflow_id,     │
│                           │            writer_id=event_log.writer_id, … )          │
│                           │   ← emitter constructs event with writer_id; no copy   │
│                           └─ try: event_log.emit(event)                            │
│                                except OSError | ClientError | … : log WARNING     │
│                                ├─ NDJSON: appends to                               │
│                                │   {traces_dir}/{run}/wf_{wf_id}__w_act_*.ndjson   │
│                                │   (file-handle cache key = (run, wf, writer_id))  │
│                                └─ DDB: PutItem                                     │
│                                    PK=PIPELINE_RUN#{run}                           │
│                                    SK=EVENT#{wf_id}#{writer_id}#{seq:010d}         │
│                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────┘

  Read path (same partition assumption):
    NdjsonEventLog.read_events(run_id) globs *.ndjson under {traces_dir}/{run_id}/
       → reads both wf_{wf_id}.ndjson AND wf_{wf_id}__w_act_*.ndjson
       → dedup key  = (workflow_id, writer_id, type, sequence)
       → sort key   = (workflow_id, sequence, writer_id)   ← seq primary, writer tiebreaks
```

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

- NDJSON: file path becomes `wf_{workflow_id}__w_{writer_id}.ndjson` (when `writer_id != "primary"`, append `__w_{writer_id}` to keep existing file naming for the legacy single-writer case). **The `NdjsonEventLog` file-handle cache key must be `(pipeline_run_id, workflow_id, writer_id)`** — a 2-tuple key would cause two writers with the same `(run, wf)` to share a stale handle, silently writing one writer's events into the other writer's file.
- DynamoDB: SK becomes `EVENT#{workflow_id}#{writer_id}#{sequence:010d}` (always include writer_id; use `"primary"` for the legacy path so existing rows are not invalidated by code change — separate migration concern but pragmatic default).
- Read-side dedup key: `(workflow_id, writer_id, type, sequence)`.
- **Sort key: `(workflow_id, sequence, writer_id)`** — sequence is primary; writer_id only tiebreaks. Sorting writer_id first would put `act_*` events lexicographically before `primary` events for the same workflow, ordering the runner's `UsageReportEvent` *before* the router's `PipeStartEvent`. Cross-writer sequence numbers are independent counters so this is best-effort, but it degrades to today's behavior when only one writer exists, which is strictly better than the writer-first ordering.

Each `EventLogProtocol` instance carries an immutable `writer_id`. **The emitter constructs every `TraceEvent` with `writer_id` read from the event log instance it's about to emit through** — no copy-on-emit. This keeps `BufferingEventLog`'s zero-copy semantic, avoids a per-event `model_copy()` allocation, and keeps the writer_id invariant local to the emit site (every place that builds a `TraceEvent` already has access to the event log it's pushing into).

- `BufferingEventLog(writer_id="primary")` — legacy, used by the workflow body (router process).
- New `make_event_log_for_activity(tracing_config, writer_id=...)` factory used by the activity-side fallback in (A). The runner generates a stable per-process `writer_id = f"act_{os.getpid()}_{uuid4().hex[:8]}"` lazily on first use, **protected by a module-level `threading.Lock`** (double-checked locking) so 1000 concurrent activities first-emitting in parallel observe the same writer_id and reuse the same event log instance. Eager init at import time is rejected because `DynamoDBEventLog.__init__` opens a boto3 resource — undesirable on workers that have tracing disabled at runtime.

This decouples sequence counters: each process has its own monotonic counter inside its own writer namespace, and dedup is correct.

### 3.2 New methods / files

| File | Change |
|---|---|
| `pipelex/tracing/trace_events.py` | Add `writer_id: str = "primary"` to `TraceEvent` base. Default ensures legacy NDJSON files (events serialized before this field existed) read back as `writer_id="primary"` via Pydantic default. |
| `pipelex/tracing/event_log_protocol.py` | Add `writer_id: str` property (read-only) and document the `(workflow_id, writer_id, sequence)` uniqueness contract. The protocol guarantee is "every event emitted through this log carries this writer_id" — which the *emitter* enforces, not the log. |
| `pipelex/tracing/buffering_event_log.py` | Add `writer_id` ctor arg, default `"primary"`. Read-only property exposed to emitters. (Emitters construct events with the right writer_id; the buffer itself does not mutate events.) |
| `pipelex/tracing/ndjson_event_log.py` | (a) Add `writer_id` ctor arg. (b) File name becomes `wf_{workflow_id}__w_{writer_id}.ndjson` when `writer_id != "primary"`. (c) **File-handle cache key becomes `(pipeline_run_id, workflow_id, writer_id)`** — covers the silent cross-writer write bug. (d) Read-side dedup key becomes `(workflow_id, writer_id, type, sequence)`; sort key becomes `(workflow_id, sequence, writer_id)`. (e) One-line docstring note: "For multi-process / multi-host deployments, traces_dir must be a filesystem visible to all writer processes (NFS/EFS); use the DynamoDB backend for fully separated hosts." |
| `pipelex/tracing/dynamodb_event_log.py` | (a) Add `writer_id` ctor arg. (b) SK becomes `EVENT#{workflow_id}#{writer_id}#{sequence:010d}`. (c) Item stores `writer_id` for query convenience. (d) On `ProvisionedThroughputExceededException` / `ClientError` from PutItem, log WARNING and drop (do not raise — failing the inference for a logging error is wrong; see R6). |
| `pipelex/tracing/event_log_factory.py` | New `make_event_log(tracing_config, writer_id="primary") -> EventLogProtocol`. Existing callers default to `"primary"` (zero behaviour change). |
| `pipelex/tracing/activity_event_log.py` (new) | Process-local cache: `get_or_create_activity_event_log(tracing_config) -> EventLogProtocol \| None`. Generates a stable per-process `writer_id = f"act_{os.getpid()}_{uuid4().hex[:8]}"` once, reuses the backend instance. **Wraps cache check + creation in a module-level `threading.Lock` (double-checked locking)** so concurrent first-emitters from N activity threads agree on a single writer_id. Returns `None` when tracing is disabled. Closes on `atexit`. |
| `pipelex/reporting/reporting_manager.py` | `_emit_usage_event` fallback path: when context lookup misses, if `tracing_config.is_enabled` and `graph_context.tracer_key` is set, emit via `get_or_create_activity_event_log` using `tracer_key` (or `graph_id` if `tracer_key` is None) as `workflow_id`. Log a single one-shot warning the first time the fallback fires per process (so we know it engaged in production). The fallback method is named `_emit_usage_event_runner_fallback` (NOT `_distributed`; the emit is local-to-the-runner-process, the *partition* is shared). On `OSError` / `botocore.exceptions.ClientError` / `MissingDependencyError` / `PipelexConfigError`, log WARNING and drop. **Never `except Exception`.** |
| `pipelex/reporting/reporting_manager.py` | **Replace `_get_registry` with a three-method split** (covers C1 in the eng review): `_get_registry_strict(pipeline_run_id) -> UsageRegistry` raises `KeyError` if missing — used by `_report_*_job` paths which now silently skip add when the registry is absent (runner case); `_get_or_create_registry(pipeline_run_id) -> UsageRegistry` creates on miss — used by `inject_tokens_usages` (P1 cross-worker assembly), the console-cost path, and `generate_report` when called for a specific run that wasn't opened. Removes the orphan-accumulation branch entirely. The existing test `test_inject_tokens_usages_auto_creates_registry` continues to pass through `_get_or_create_registry`. |
| `pipelex/reporting/reporting_protocol.py` | No surface change. Implementation notes docstring updated to describe the "register registry first via `open_registry` for runners that own a pipeline" expectation. |
| `pipelex/cogt/content_generation/content_generator_dry.py` | **Hook `report_inference_job` into the dry path** (covers A5 in the eng review): when a `make_*` method completes, build a synthetic `LLMTokensUsage` (zero tokens, dry-run model id) and call `get_report_delegate().report_inference_job(...)`. This makes the cross-worker emission path observable through the existing dry-run e2e harness without forcing every Phase 6 assertion to run live LLM. Add a unit test pinning that this generator emits a usage event. |

### 3.3 Why not `TracingActivityInboundInterceptor`

The interceptor design from the original Phase 4.5 Step 6 plan would also work, but the JobMetadata-plumbing approach has three concrete advantages here:

1. **Data is already there.** `tracer_key` is propagated since `WfPipeRouter.run` line 86 — we'd be adding an interceptor only to read what's already on the activity's input.
2. **No Temporal SDK dependency in `pipelex.reporting.*`.** The interceptor would force `pipelex.reporting` to import Temporal types or live behind an indirection. The fallback in `_emit_usage_event` is plain Python.
3. **The same code path covers direct mode** (where tracing is configured but the runner-side context still works — fallback never engages).

If we later want the cleanliness of an interceptor, it's an additive change on top of this fix.

---

## 4. TDD plan — order of work

Each step lists: tests to write **first** (red), then the change that turns them green. Run `make agent-check` after every step. Run `make agent-test` at the end of each phase.

### Phase 0 — Pin baseline (no xfail)

**Phase checklist:**

- [x] 0.1 — Add `test_no_emit_when_no_event_log_set_and_no_fallback_yet`
- [x] Phase 0 complete: `make agent-check && make agent-test` green

**0.1** Add `tests/unit/pipelex/reporting/test_reporting_event_emission.py::test_no_emit_when_no_event_log_set_and_no_fallback_yet`. This is a one-liner pin of *today's* behavior: `ReportingManager` with `set_event_log` never called, `tracing_config.is_enabled = False` (so no fallback path engages even after Phase 2 lands). Asserts no event written anywhere. Pins the "tracing-disabled is silent" baseline that the fallback in Phase 2 must respect.

The fresh fallback test (`test_fallback_engages_when_context_missing_and_tracing_enabled`) is added in Phase 2 directly as a green test; we don't use the xfail-flip pattern (it adds commit choreography for no real benefit).

(One test, no LLM, sub-second.)

### Phase 1 — Writer-id schema (foundation for both A and B)

**Phase checklist:**

- [x] 1.1 — Red: write `TestWriterIdSchema` (8 cases below)
- [x] 1.2 — Green: thread `writer_id` through all event log backends + emitters
- [x] 1.3 — Regression check: all existing tracing/reporting tests pass
- [x] Phase 1 complete: commit `feat: add writer_id field to TraceEvent and propagate through event log backends`

**1.1** *Red.* `tests/unit/pipelex/tracing/test_writer_id_schema.py::TestWriterIdSchema`:

- [x] `test_trace_event_has_writer_id_default_primary` — round-trip JSON of a hand-built event, assert `"writer_id": "primary"`.
- [x] `test_legacy_ndjson_without_writer_id_field_reads_as_primary` — pre-populate a `wf_W.ndjson` file by hand with a JSON line missing the `writer_id` field, call `read_events`, assert the parsed event has `writer_id == "primary"` (Pydantic default kicks in). Pins backwards-read invariant.
- [x] `test_two_writers_same_workflow_dedup_keeps_both` — emit `UsageReportEvent(workflow_id="W", writer_id="a", sequence=0)` and `(... writer_id="b", sequence=0)` to an `InMemoryEventLog`, read back, assert two events. (Currently dedup would keep them because type+seq differ across emits, but harden the contract.)
- [x] `test_ndjson_writer_id_in_filename_for_non_primary` — emit to `NdjsonEventLog(traces_dir=tmp, writer_id="act_pid42")`, assert file `wf_W__w_act_pid42.ndjson` exists; emit again with `writer_id="primary"`, assert legacy file name `wf_W.ndjson` exists (no breaking change).
- [x] **`test_two_writers_same_workflow_get_separate_handles`** — instantiate two `NdjsonEventLog`s with different `writer_id`, emit `(W, sequence=0)` from each into the same `traces_dir`/`pipeline_run_id`, assert two distinct files exist with one event each. Pins the `(run, wf, writer_id)` cache-key fix (covers A2 in the eng review).
- [x] `test_ndjson_dedup_uses_writer_id` — write two events to two different writer files for same `(workflow_id, sequence)`, read back, assert both present.
- [x] `test_ndjson_sort_order_is_sequence_primary_writer_id_secondary` — emit `(W, primary, PipeStart, seq=2)` then `(W, act_x, UsageReport, seq=0)` then `(W, primary, PipeStart, seq=1)`, read back, assert order `[seq=0, seq=1, seq=2]`. Pins the sort-key correction (covers A1).
- [x] `test_dynamodb_sk_includes_writer_id` — unit test against a stubbed boto3 table (`pytest-mock` MockerFixture, not unittest.mock), assert PutItem SK is `EVENT#W#act_pid42#0000000000`.

**1.2** *Green.* Add `writer_id: str = "primary"` to `TraceEvent`. Thread it through `BufferingEventLog`, `NdjsonEventLog`, `DynamoDBEventLog`, `InMemoryEventLog`, `event_log_factory.make_event_log`. Update read-side dedup key to `(workflow_id, writer_id, type, sequence)`, sort key to `(workflow_id, sequence, writer_id)`, and `NdjsonEventLog._file_handles` cache key to `(pipeline_run_id, workflow_id, writer_id)`. Default `"primary"` keeps every existing test green. Update emitters (`GraphTracer`, `_emit_usage_event` fast path, every test fixture that builds a `TraceEvent`) to construct events with `writer_id` from the event log instance.

**1.3** *Regression check.* Re-run `tests/unit/pipelex/tracing/`, `tests/unit/pipelex/reporting/`, `tests/integration/pipelex/temporal/tracing/` — all must still pass. NDJSON files for the legacy path keep their old names, DDB rows for legacy path get `"primary"` in their SK (one-time schema bump documented in CHANGELOG.md `[Unreleased]`).

### Phase 2 — Activity-side fallback in `_emit_usage_event`

**Phase checklist:**

- [x] 2.1 — Red: write `TestEmitRunnerFallback` (11 cases below) + `test_dry_generator_invokes_report_inference_job`
- [x] 2.2 — Green: implement `pipelex/tracing/activity_event_log.py` + fallback in `_emit_usage_event` + `ContentGeneratorDry` reporting hook
- [x] Phase 2 complete: commit `feat: runner-side usage event emission via per-process activity event log`

**2.1** *Red.* `tests/unit/pipelex/reporting/test_emit_runner_fallback.py::TestEmitRunnerFallback`:

- [x] `test_fallback_engages_when_context_missing_and_tracing_enabled` — `ReportingManager` with no `set_event_log` call. Mock `get_config().pipelex.tracing_config.is_enabled=True` and point NDJSON traces_dir to `tmp_path`. Build an `LLMJob` with `graph_context.tracer_key="wf_xyz"`, `pipeline_run_id="run_abc"`, `parent_node_id="g:node_2"`. Call `report_inference_job`. Assert one NDJSON file under `tmp_path/run_abc/wf_wf_xyz__w_act_*.ndjson` containing one `UsageReportEvent` with the right node_id, workflow_id, pipeline_run_id, tokens_usage, and `writer_id` matching the file name.
- [x] `test_runner_fallback_uses_tracer_key_when_set` — pin the load-bearing assumption that `tracer_key` is what becomes `workflow_id` on the runner side. Build context with `graph_id="run_abc"`, `tracer_key="wf_xyz"`; assert emitted event's `workflow_id == "wf_xyz"`. Then build context with `graph_id="run_abc"`, `tracer_key=None`; assert emitted event's `workflow_id == "run_abc"`. (Replaces the old `test_no_tracer_key_skips_fallback` — that name was misleading; the fallback always emits when tracing is enabled, just with a different workflow_id.)
- [x] `test_fallback_caches_event_log_per_process` — call `report_inference_job` twice; assert only one event log instance was constructed (use `mocker.spy` on `make_event_log`).
- [x] **`test_concurrent_first_call_yields_single_writer_id`** — spawn N=16 threads on a `threading.Barrier`; each calls `get_or_create_activity_event_log(cfg)` once; assert all observe the same `writer_id` and the same event log instance. Pins the `threading.Lock` fix (covers A6 / T2).
- [x] `test_disabled_tracing_skips_emit` — `is_enabled=False`, no event log file is created, no warning raised. (Note: in the runner case the `_report_*_job` paths now skip `add_tokens_usage` because `_get_registry_strict` raises and is caught — see Phase 3. The console cost-report path still works in dev because direct-mode opens the registry first.)
- [x] `test_no_graph_context_skips_emit` — `graph_context=None`, no fallback. Existing test already covers this with context registered; add the no-context-no-fallback variant.
- [x] `test_explicit_log_when_emit_path_unavailable` — `tracing_config.is_enabled=True` but `make_event_log` raises a **specific** exception type. Parametrize over `OSError` (NDJSON dir unwritable), `MissingDependencyError` (boto3 missing for DDB), `PipelexConfigError` (factory misconfigured), and `botocore.exceptions.ClientError` (DDB throttle / auth fail at PutItem time, covered by `test_explicit_log_when_emit_raises_client_error`). Assert each is caught, logged at WARNING, and dropped — never re-raised. **Implementation must NOT use `except Exception`**; it must catch each specific type. (Covers C3 in the eng review.)
- [x] `test_warning_emitted_once_per_process_when_fallback_engages` — call 100 times, assert only the first call emitted the "fallback engaged" warning. Use module-level state for the once-flag so it survives multiple `ReportingManager` instances within a test process.
- [x] `test_warning_emitted_once_even_with_multiple_managers` — instantiate two `ReportingManager`s in sequence, both fallback once each, assert only one warning total (covers the "module-level once" implementation choice).
- [x] **`test_retried_activity_emits_duplicate_usage_event_documenting_r2`** — call `report_inference_job` twice from the same process for the same workflow; assert both events present in the log with sequences 0 and 1. Pins R2's documented over-counting behavior (covers T3).
- [x] **`test_make_llm_text_invokes_report_inference_job`** — placed in `tests/unit/pipelex/cogt/content_generation/test_content_generator_dry_reporting.py`. Build a `ContentGeneratorDry`, configure a stub `ReportingManager`, call `make_llm_text(...)`, assert `report_inference_job` was called once with a synthetic `LLMJob` whose `job_report.llm_tokens_usage` is non-None. Pins the A5 hook so dry-run emission doesn't decay later.

(All sub-second; no LLM.)

**2.2** *Green.* Implement `pipelex/tracing/activity_event_log.py` with:

```python
import threading
from uuid import uuid4

_lock = threading.Lock()
_cached_event_log: EventLogProtocol | None = None
_writer_id: str | None = None


def get_or_create_activity_event_log(
    tracing_config: TracingConfig,
) -> EventLogProtocol | None:
    """Process-local cached event log for runner-side activity emission.

    Returns None when tracing is disabled. Generates a stable
    per-process writer_id once and reuses it for every emit. Thread-safe:
    concurrent first-callers from N activity threads observe the same
    writer_id and the same backend instance.
    """
    global _cached_event_log, _writer_id
    if not tracing_config.is_enabled:
        return None
    if _cached_event_log is not None:
        return _cached_event_log
    with _lock:
        if _cached_event_log is not None:
            return _cached_event_log
        _writer_id = f"act_{os.getpid()}_{uuid4().hex[:8]}"
        _cached_event_log = make_event_log(tracing_config, writer_id=_writer_id)
        atexit.register(_cached_event_log.close)
        return _cached_event_log
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
    self._emit_usage_event_runner_fallback(
        inference_job=inference_job,
        tokens_usage=tokens_usage,
        graph_context=graph_context,
    )
```

The fallback method:

- Reads `tracing_config = get_config().pipelex.tracing_config`.
- If not enabled → return.
- `process_event_log = get_or_create_activity_event_log(tracing_config)` → if None, return.
- `workflow_id = graph_context.tracer_key or graph_context.graph_id`.
- `node_id = graph_context.parent_node_id or "unknown"`.
- Build `UsageReportEvent(pipeline_run_id=job_metadata.pipeline_run_id, workflow_id=workflow_id, writer_id=process_event_log.writer_id, sequence=process_event_log.next_sequence(), node_id=node_id, tokens_usage=tokens_usage, timestamp=...)`. **The emitter constructs the event with writer_id; no copy-on-emit happens later.**
- Wrap `process_event_log.emit(event)` in a try/except catching the specific exception types (`OSError`, `botocore.exceptions.ClientError`, `MissingDependencyError`, `PipelexConfigError`); on catch, log WARNING and drop. **Never `except Exception`.**
- One-shot warning logged the first time per process via a module-level boolean guarded by the same `_lock`.

(No xfail to flip — Phase 0 only pinned the tracing-disabled baseline; the fallback test in Phase 2 is fresh and ships green.)

### Phase 3 — Replace `_get_registry` orphan auto-create (three-method split)

**Phase checklist:**

- [x] 3.1 — Red: write `TestNoOrphanRegistries` (5 cases below)
- [x] 3.2 — Green: split `_get_registry` into `_get_registry_strict` + `_get_or_create_registry`; update all callers; remove orphan auto-create branch + TODO comment
- [x] Phase 3 complete: commit `refactor: split _get_registry into strict and or_create variants`

**3.1** *Red.* `tests/unit/pipelex/reporting/test_no_orphan_registries.py::TestNoOrphanRegistries`:

- [x] `test_runner_does_not_accumulate_registries` — Build a `ReportingManager`, do **not** call `open_registry`. Call `report_inference_job` with `pipeline_run_id="never_opened"`. Assert `_usage_registries` does **not** contain `"never_opened"` afterwards (no orphan accumulation on runner). The usage event still emitted via the fallback (Phase 2), but no registry sat behind.
- [x] `test_direct_mode_still_accumulates_registry` — `open_registry("run_x")` then `report_inference_job` with `pipeline_run_id="run_x"`, assert registry has the usage record.
- [x] `test_inject_tokens_usages_still_creates_on_miss` — pin existing behavior: `inject_tokens_usages("never_opened", [...])` works, registry is created. (Updates the existing `test_inject_tokens_usages_auto_creates_registry` to call through `_get_or_create_registry`.)
- [x] `test_get_registry_strict_raises_when_missing` — direct unit test of `_get_registry_strict("never_opened")`, asserts `KeyError`.
- [x] `test_generate_report_for_unopened_run_creates_empty_registry_and_renders` — `generate_report("never_opened")` should not crash; it goes through `_get_or_create_registry`, finds nothing, renders an empty cost report. (Documents the P1 readback path's interaction with on-the-fly run IDs.)

**3.2** *Green.* Replace `_get_registry` with three explicit methods:

```python
def _get_registry_strict(self, pipeline_run_id: str) -> UsageRegistry:
    """Raises KeyError if the registry was never opened.

    Used by _report_*_job: on the runner, the registry is never opened,
    so callers swallow KeyError and skip add_tokens_usage. The runner-side
    UsageReportEvent emission is independent of the registry.
    """
    return self._usage_registries[pipeline_run_id]


def _get_or_create_registry(self, pipeline_run_id: str) -> UsageRegistry:
    """Returns the registry, creating it on miss.

    Used by inject_tokens_usages (P1 cross-worker assembly path), the
    console cost-report path, and generate_report when called for a
    specific run that wasn't opened on this process.
    """
    if pipeline_run_id not in self._usage_registries:
        self._usage_registries[pipeline_run_id] = UsageRegistry()
    return self._usage_registries[pipeline_run_id]
```

Update `_report_llm_job` / `_report_img_gen_job` / `_report_extract_job` / `_report_search_job` to:

- Always emit the usage event (fallback covers runner).
- Try `_get_registry_strict(pipeline_run_id).add_tokens_usage(...)` and on `KeyError` skip the add silently (this is the runner-process case). Don't auto-create.
- The console cost-report path uses `_get_or_create_registry` for dev ergonomics.

`inject_tokens_usages(pipeline_run_id, ...)` switches its internal `_get_registry(pipeline_run_id)` call to `_get_or_create_registry(pipeline_run_id)` — preserves the existing test `test_inject_tokens_usages_auto_creates_registry`.

`generate_report(pipeline_run_id=...)` uses `_get_or_create_registry` for the targeted-run path so it doesn't crash on never-opened runs.

This kills the silent orphan-registry accumulation and the TODO comment without breaking the P1 distributed assembly path.

### Phase 4 — Integration: split-worker temporal test (two task queues)

**Phase checklist:**

- [x] Q-Phase4 prereq confirmed: router can dispatch activities to a different task queue (`WorkerConfig.inference_task_queue` plumbing landed in commit 935a3022)
- [x] 4.1 — Red: write `TestSplitWorkerUsageEmission` (2 cases) + `make_split_workers` + `_simulate_runner_isolation` helpers
- [x] 4.2 — Green: Phases 1–3 were sufficient; substitute synthesizes the `LLMJob` so the cross-worker hop fires even in DRY mode
- [x] Phase 4 complete: commit `test(integration): split-worker temporal test for cross-process usage emission`

This phase opens **two pure-scope workers on two task queues** in the same pytest process: `q_router` runs a router-scope worker (`disable_all_activities=True`), `q_runner` runs a runner-scope worker (`disable_all_workflows=True`). The router dispatches inference activities to `q_runner` via Temporal's `task_queue=...` argument. This is the production deployment topology: router and runner are physically separated.

Within the single pytest process the `ReportingManager` is still a process singleton, so the router's `set_event_log` populates `_event_log_contexts` for the workflow's `lookup_key`. The runner's activity then runs in the same process and would *also* see that context — masking the bug. We deliberately defeat that by substituting the inference activity on the runner with a wrapper that clears `_event_log_contexts` on the way in (simulates a cold runner process).

This replaces the original Phase 4.2 "three-worker on one queue" design, which Temporal SDK rejects because of overlapping task-type registrations (per `WorkerScope` docstring at `config_temporal.py:60-62`).

**4.1** *Red.* `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py::TestSplitWorkerUsageEmission`:

```python
@pytest.mark.temporal
@pytest.mark.gha_disabled  # match existing tracing tests' policy until xdist flake is fixed
@pytest.mark.asyncio(loop_scope="class")
class TestSplitWorkerUsageEmission:

    async def test_runner_usage_event_lands_in_same_ndjson_dir(
        self,
        sequence_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ):
        """Router on q_router dispatches inference activity to q_runner.
        The runner — with no _event_log_contexts entry — emits its
        UsageReportEvent into the same traces_dir partition via the fallback.
        """
        ...

    async def test_no_double_emit_in_split_worker_pool(
        self,
        sequence_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ):
        """Exactly-once invariant: _emit_usage_event takes either the fast path
        OR the fallback path, never both. Submit one workflow; assert exactly
        one UsageReportEvent per inference call across all NDJSON files.
        """
        ...
```

The fixture work this needs:

- `make_split_workers(temporal_client, q_router, q_runner) -> AsyncContextManager` helper in `tests/integration/pipelex/temporal/tracing/helpers.py` that opens two workers on two distinct task queues: one router-scope on `q_router`, one runner-scope on `q_runner` (with `substitute_activities` for `_simulate_runner_isolation`).
- The router workflow must be configured to dispatch inference activities to `q_runner` — likely via a config plumbing that adds an "activity_task_queue" to the activity options used by `WfMakeLLMText` / `act_llm_gen_text`. **If that plumbing does not yet exist**, this is a small adjacent change (one config field + one read site) that needs to land in this same PR; capture it as TODOS-internal "Phase 4 prereq" if absent. (See open question Q-Phase4 below.)
- `_simulate_runner_isolation(real_activity)` decorator that wraps an `@activity.defn` to clear `get_report_delegate()._event_log_contexts` at the start of each invocation. Use `monkeypatch.setattr(get_report_delegate(), "_event_log_contexts", {})` scoped to the test class to avoid cross-test bleed.

Assertions:

- `ndjson_files_for_run(traces_dir, run_id)` returns ≥ 2 files: the router-side `wf_{wf_id}.ndjson` (from `act_flush_trace_events`) **and** at least one `wf_{wf_id}__w_act_*.ndjson` from the runner.
- `read_events(run_id)` contains `PipeStartEvent`s (`writer_id="primary"`) and `UsageReportEvent`s (`writer_id="act_*"`), with no duplicates after dedup.
- For the exactly-once test: count `UsageReportEvent`s per `(node_id, workflow_id)` and assert == 1.

**4.2** *Green.* Phases 1–3 should be enough. If `test_no_double_emit_in_split_worker_pool` fails because the substitute didn't actually clear `_event_log_contexts` before the runner emit, tighten the simulator (use a `Lock` to make the clear atomic with respect to the activity entry).

**Open question — Q-Phase4:** does the router currently know how to dispatch the inference activities to a different task queue from itself? If yes, this phase is straightforward; if no, the pre-work is "expose `activity_task_queue` on `act_llm_gen_text`-and-friends scheduling options." Confirm before starting Phase 4.

### Phase 5 — Removed clutter & docs

**Phase checklist:**

- [x] 5.1 — Remove `_get_registry` TODO comment at `reporting_manager.py:110-118` (already gone after Phase 3)
- [x] 5.2 — Add CHANGELOG.md entry under `[Unreleased]`
- [x] 5.3 — Add `NdjsonEventLog` shared-FS docstring note (already in place from Phase 1)
- [x] 5.4 — Update `wip/tracing-cost-reporting-as-built.md` (mark T1 fixed)
- [x] 5.5 — Update `wip/02-master-plan.md` (P0 → Done once Phase 6 passes)
- [x] Phase 5 complete: commit `docs: changelog + as-built/master-plan updates for P0 + ndjson docstring`

**5.1** Remove the `_get_registry` TODO comment at `reporting_manager.py:110-118` (no longer applies — the three-method split eliminates the orphan auto-create branch entirely).
**5.2** Add CHANGELOG.md entry under `[Unreleased]`:
   ```
   ### Changed
   - Tracing: `TraceEvent` gains a `writer_id` field (default `"primary"`) so
     standalone activity workers can emit into the same backend partition as
     workflow workers without colliding on `(workflow_id, sequence)`. Emitters
     stamp writer_id at construction time (no copy-on-emit).
   - NDJSON read-side dedup key is now `(workflow_id, writer_id, type, sequence)`;
     sort key is `(workflow_id, sequence, writer_id)` — sequence stays primary
     so the runner's UsageReportEvent doesn't get sorted before the router's
     PipeStartEvent.
   - DynamoDB sort key format updated to `EVENT#{workflow_id}#{writer_id}#{sequence:010d}`.
     Existing rows are unaffected (legacy emissions write `writer_id="primary"`).
   - `ReportingManager._get_registry` replaced with `_get_registry_strict`
     (raises on miss, used by `_report_*_job`) and `_get_or_create_registry`
     (creates on miss, used by `inject_tokens_usages`, console cost path,
     `generate_report`).
   - `ContentGeneratorDry` now invokes `report_inference_job` with a synthetic
     `LLMTokensUsage`, so dry-run mode produces real `UsageReportEvent`s
     observable through the same backend path as live runs.
   ### Fixed
   - `ReportingManager` now emits `UsageReportEvent`s from activities running on
     standalone worker processes (fixes silent drop on runner scope).
   - `NdjsonEventLog` file-handle cache no longer collides between two writers
     for the same `(pipeline_run_id, workflow_id)` — cache key now includes
     `writer_id`, preventing one writer's events from leaking into another
     writer's file.
   ```
**5.3** Add a one-line note to the `NdjsonEventLog` class docstring: "For multi-process / multi-host deployments, traces_dir must be a filesystem visible to all writer processes (NFS/EFS); use the DynamoDB backend for fully separated hosts."
**5.4** Update `wip/tracing-cost-reporting-as-built.md` "What is broken or missing" → mark T1 as fixed (with a forward link to this work). Leave T2 (P1) and T3 (T1 partially mitigates T3 — fully resolved when P1 lands).
**5.5** Update `wip/02-master-plan.md` Priority order table: P0 → "In progress" → "Done" once Phase 6 passes.

### Phase 6 — End-to-end validation via the temporal-e2e-validate skill

**Phase checklist:**

- [x] 6.1 — Ran Tier 1 in dry-run with router+runner workers. **Finding:** dry-run instantiates `ContentGeneratorDry()` directly inside the workflow body (`pipe_llm.py:515`), bypassing `act_llm_gen_text` entirely. So all `usage_report` events emit on the router with `writer_id="primary"`; no `__w_act_*` files are produced in dry-run. The plan's expectation here was based on an incorrect assumption — the runner-side fallback is exercised only by (a) the Phase 4 integration test (which substitutes the inference activity to synthesize an `LLMJob` server-side), or (b) live mode where `act_llm_gen_text` is actually dispatched.
- [x] 6.2 — Added Tier 8 (Cross-worker usage emission) to `temporal-e2e-validate/SKILL.md`. Documents the dry-run limitation, points to `TestSplitWorkerUsageEmission` for deterministic verification, and gives the live-mode CLI command + expected NDJSON file naming (`wf_*__w_act_*`).
- [ ] 6.3 — (Optional sanity) Repeat `native_text_sequence` once in live mode — deferred, costs LLM call; covered by integration test.
- [ ] 6.4 — (Stretch / optional, P1-gated) Add Tier 9 for cost-report assembly — deferred, blocked on P1.
- [x] Phase 6 complete (committable as `docs(skills): add Tier 8 cross-worker usage emission to temporal-e2e-validate`)

Run the existing `/temporal-e2e-validate` skill in **Mode 2 (3-process)** — `temporal-worker-router` + `temporal-worker-runner` + submitter. This is the only setup that proves "true separate Python processes; runner has its own ReportingManager that was never told about this workflow".

**Prerequisite, covered by Phase 2 of this plan:** `ContentGeneratorDry` now invokes `report_inference_job` with a synthetic `LLMTokensUsage`, so dry-run mode produces real `UsageReportEvent`s observable via NDJSON. This unblocks dry-runnable e2e assertions for the cross-worker usage path.

**6.1** Run Tier 1 (`native_text_sequence`) and Tier 3 (`temporal_parallel`) in dry-run mode with tracing enabled. Inspect `.pipelex/traces/{run_id}/`:

- Expect ≥ 2 NDJSON files per run: `wf_{router_wf_id}.ndjson` (router-side, `writer_id="primary"`) and `wf_{router_wf_id}__w_act_{runner_pid}_{uuid}.ndjson` (runner-side).
- Expect at least one `UsageReportEvent` from the runner file with `writer_id` starting `act_`. The mock `LLMTokensUsage` injected by `ContentGeneratorDry` carries zero token counts and a `dry_run` model id — assert that's what's in the event payload.

**6.2** Add a new tier "Tier 8 — Cross-worker usage emission" to `.claude/skills/temporal-e2e-validate/SKILL.md`. Document:

- Run the Tier 8 command (`native_text_sequence` in dry mode against router+runner workers).
- After the run, `ls .pipelex/traces/{run_id}/` should show both writer-id'd and primary NDJSON files.
- `grep '"event_kind":"usage_report"' .pipelex/traces/{run_id}/*.ndjson` should return the inference's usage events; assert the `writer_id` field on those events is `act_*`, not `primary`.

**6.3** (Optional sanity) Repeat `native_text_sequence` once in **live mode** to confirm the same path with real `LLMTokensUsage` from the actual provider. One cheap LLM call. Distinguishes "dry-mock plumbing works" from "real-inference plumbing works."

**6.4** (Stretch / optional, gated on P1 readiness) Add a Tier 9 that asserts the cost report is now non-empty for the cross-worker run by running `pipelex run bundle ... --no-logo --graph` and inspecting the auto-generated cost report file under `cost_report_dir_path`.

---

## 5. Test inventory (single source of truth)

| Done | Layer | File | New / changed | Phases |
|---|---|---|---|---|
| [x] | Unit | `tests/unit/pipelex/tracing/test_writer_id_schema.py` | new (TestWriterIdSchema, includes legacy-without-writer_id read, two-writers-separate-handles, sort-order-sequence-primary) | 1 |
| [x] | Unit | `tests/unit/pipelex/reporting/test_emit_runner_fallback.py` | new (TestEmitRunnerFallback, includes concurrent-first-call, retry-over-counting, parametric specific-exception coverage) | 0 + 2 |
| [x] | Unit | `tests/unit/pipelex/reporting/test_no_orphan_registries.py` | new (TestNoOrphanRegistries, includes get_or_create-keeps-inject_tokens_usages-working, get_registry_strict-raises) | 3 |
| [x] | Unit | `tests/unit/pipelex/cogt/content_generation/test_content_generator_dry_reporting.py` | new — pin that dry generator invokes `report_inference_job` with mock usage | 2 + 6 |
| [x] | Unit | `tests/unit/pipelex/reporting/test_reporting_event_emission.py` | edit (commits 9fb07da9 + c73e44a5) — `inject_tokens_usages_auto_creates_registry` rerouted through `_get_or_create_registry`; writer_id coverage landed in the dedicated `test_writer_id_schema.py` instead | 1 + 3 |
| [~] | Unit | `tests/unit/pipelex/tracing/test_ndjson_event_log.py` | NOT edited — writer_id file-naming/dedup/sort/cache-key coverage absorbed by the dedicated `test_writer_id_schema.py`. Leave a follow-up only if duplicate coverage matters. | 1 |
| [~] | Unit | `tests/unit/pipelex/tracing/test_ndjson_dedup_assembly.py` | NOT edited — dedup-with-writer_id coverage lives in `test_writer_id_schema.py`. | 1 |
| [~] | Unit | `tests/unit/pipelex/tracing/test_in_memory_event_log.py` | NOT edited — `InMemoryEventLog` writer_id property covered transitively by the writer_id schema tests; no behavior gap detected. | 1 |
| [x] | Integration | `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py` | new (TestSplitWorkerUsageEmission, 2 cases: lands-in-same-dir, no-double-emit) | 4 |
| [x] | Integration | `tests/integration/pipelex/temporal/tracing/helpers.py` | added `make_split_workers` (two-queue topology) + `_runner_isolated_act_llm_gen_text` substitute (clears `_event_log_contexts` and synthesizes the LLMJob so the cross-worker hop fires even in DRY mode) | 4 |
| [x] | E2E | `.claude/skills/temporal-e2e-validate/SKILL.md` | added Tier 8 (Cross-worker usage emission) with dry-run-limitation note + live-mode command + pointer to `TestSplitWorkerUsageEmission` | 6 |

**Constraint reminders (CLAUDE.md)**:

- One `TestX` class per module — every new test file gets exactly one class.
- Use `pytest-mock`'s `MockerFixture`, never `unittest.mock`.
- Markers: `@pytest.mark.temporal` for the integration class; `@pytest.mark.asyncio(loop_scope="class")` if async; `gha_disabled` to match the existing tracing-tests policy until xdist flake is fixed.
- Fixtures in `conftest.py` at the appropriate level (the new helpers go in `tests/integration/pipelex/temporal/tracing/helpers.py`, fixtures in `conftest.py` next to it).

---

## 6. Implementation order — atomic commits

Each commit is independently green (`make agent-check && make agent-test`). Commit messages follow the existing conventional style.

- [x] 1. `test: pin tracing-disabled silent-baseline before fallback lands` — Phase 0. (commit 9fb07da9)
- [x] 2. `feat: add writer_id field to TraceEvent and propagate through event log backends` — Phase 1. (commit 69f8c22c)
- [x] 3. `feat: runner-side usage event emission via per-process activity event log` — Phase 2. (commit c70ed394)
- [x] 4. `refactor: split _get_registry into strict and or_create variants` — Phase 3. (commit c73e44a5)
- [x] 4b. `feat(temporal): WorkerConfig.inference_task_queue routes act_llm_gen_text` — Phase 4 prereq (Q-Phase4). (commit 935a3022)
- [x] 5. `test(integration): split-worker temporal test for cross-process usage emission` — Phase 4 (two-task-queue topology). (commit 06a3d26c)
- [x] 6. `docs: changelog + as-built/master-plan updates for P0 + ndjson docstring` — Phase 5.
- [x] 7. `docs(skills): add Tier 8 cross-worker usage emission to temporal-e2e-validate` — Phase 6.

---

## 7. Risks, open questions, and explicit non-decisions

**R1 — Process-local writer_id vs. activity-execution-attempt-local writer_id.**
Per-process is right when the runner pool is stable. If the runner is killed and restarted mid-pipeline, a fresh writer_id is generated on the new process and we keep two writer files for the same workflow_id. That's the *correct* behaviour (no collision) and the assembler handles the union fine.

**R2 — Temporal activity retries.**
A retried activity re-emits the `UsageReportEvent`. Today's NDJSON dedup is `(workflow_id, sequence)`; with `writer_id` added we get `(workflow_id, writer_id, sequence)`. As long as the same process retries (same writer_id) the dedup still works because the sequence is reused — **except** the per-process counter increments on every emit, even retries. So a retry would emit at sequence N+1 instead of N, and dedup wouldn't fire. This is identical to today's behaviour for `BufferingEventLog` (fresh buffer on each replay; sequence resets), and the read-side already accepts duplicates from retries because the underlying tokens were really billed twice. **Decision**: keep current behaviour, document the over-counting risk in the docstring of `_emit_usage_event_runner_fallback`, AND pin it with `test_retried_activity_emits_duplicate_usage_event_documenting_R2` so the documented behavior is reified as a test (per eng review T3). Suppression of retried-emit duplicates is a separate, harder problem (future).

**R3 — Boto3 inside an activity.**
The DynamoDB backend uses synchronous boto3. An activity is allowed to do synchronous I/O (unlike a workflow), so this is fine, but each activity invocation that emits a usage event makes one PutItem (or one NDJSON file write). For high-throughput runners this is non-trivial. We accept the cost in this round; batching is an obvious follow-up if the runner becomes a bottleneck.

**R4 — Direct mode regression.**
Direct mode populates `_event_log_contexts` via `pipeline_run_setup.py:282`, so the fallback in `_emit_usage_event` should *never* engage in direct mode. Phase 2's `test_fallback_caches_event_log_per_process` is the canary — if direct mode tests start touching the per-process activity event log, that's the bug.

**R5 — DynamoDB SK schema migration.**
The new SK includes `writer_id`. New rows under `"primary"` are still queryable by old readers that only `Query` on PK (the SK is part of the row but not part of the KeyConditionExpression in `read_events`). External consumers were grepped for during eng review: `pipelex-api-infra/src/` has **no** `TraceEventDynamoDBAdapter`-style code reading this DDB table — the docstring claim in `dynamodb_event_log.py` is aspirational, not a live consumer dependency. So R5's risk is lower than originally feared. **Decision**: document in CHANGELOG; if `pipelex-back-office` or any other repo hard-codes the SK pattern (worth a quick grep at PR time), coordinate accordingly. Do not block this PR on a hypothetical consumer.

**R6 — Why not raise in the silent-drop case?**
Today it's silent. We could raise instead. Raising inside `report_inference_job` would tank the calling pipe — the LLM call already succeeded, the user paid for tokens, it would be perverse to fail the pipeline because we couldn't log the cost. **Decision**: log a single warning per process when the fallback engages, and a WARNING (not ERROR) when even the fallback path can't emit (e.g. NDJSON path unwritable). Add a `tracing_config.strict_mode: bool` later if anyone wants raise-on-emit-failure semantics.

**R7 — `tracer_key` populated by *every* path that emits?**
`WfPipeRouter.run` populates it. `pipeline_run_setup` populates it implicitly (`graph_context.lookup_key` falls back to `graph_id`). Need to audit `pipe_run_setup` in direct mode and the parent-context path in nested workflows to confirm `tracer_key` is always either set or safely substituted by `graph_id`. The fallback uses `graph_context.tracer_key or graph_context.graph_id` so we're robust either way, but the fallback test set should cover both branches explicitly (covered by `test_no_tracer_key_skips_fallback`).

---

## 8. Out of scope (explicitly deferred)

- **P1 (cost report assembly wiring)**: read events → `UsageAggregator.aggregate()` → `ReportingManager.inject_tokens_usages()` → `generate_report()`. Listed at master plan §P1. This work makes that one-step plumbing change possible — do it next, in a separate PR.
- **Real-time consumer / live progress** (Step 5 of the original `distributed-tracing-and-reporting.md`).
- **Phase 6a / 6b crate dependencies** — independent track.
- **Retried-activity duplicate suppression** — see R2; needs a deeper rethink of the sequence space.

### TODOs added during eng review (deferred follow-ons, all out of scope for P0)

- [ ] **`tracing_config.strict_mode: bool`** — opt-in flag that raises (instead of WARNING + drop) when the runner-side emit path fails. Useful for compliance/audit deployments where missing trace data is a hard error. Keep the option open; no users today. (Eng review TODO-3 / R6.)
- [ ] **DynamoDB `BatchWriteItem` for runner emission** — current path does one `PutItem` per usage event. At 1000 concurrent activities per process, that's 1000 boto3 calls per pipeline run. `BatchWriteItem` batches up to 25 per call. Add when actual runner throughput shows it matters; until then a plain `PutItem` is fine. (Eng review TODO-1 / R3.)
- [ ] **NDJSON shared-filesystem invariant enforcement** — The NDJSON backend assumes `traces_dir` is visible to all writer processes (router pool + runner pool + `act_flush_trace_events`). For multi-host deployments this means an NFS/EFS mount or equivalent. The plan adds a one-line `NdjsonEventLog` docstring spelling this out. The follow-up TODO is "add a startup check that warns if `traces_dir` looks like a local-only path on a multi-worker deployment" — non-trivial because there's no clean cross-process detection signal. (Eng review TODO-2.)

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | not run |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | not run |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 18 issues across architecture/code-quality/tests, 9 decisions resolved via AskUserQuestion, 2 critical failure-mode gaps flagged (DDB throttle exception type + multi-host NDJSON visibility), 3 follow-on TODOs filed |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | not applicable (backend infra) |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | not run |

- **UNRESOLVED:** 0 decisions left open.
- **VERDICT:** ENG CLEARED — ready to implement. Critical gaps are documented in §7 / TODO follow-ons; not blockers for P0.
