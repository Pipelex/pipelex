---
name: temporal-e2e-validate
description: >
  Full end-to-end validation of Temporal distributed execution (Phases 2-4).
  Two modes: (1) pytest against a real Temporal server for detailed assertions on
  all 19 test cases, and (2) true 3-process setup (server + separate worker process
  + submitter) that validates the actual deployment topology including cross-process
  serialization, LibraryCrate propagation, deferred hydration, and concurrent
  isolation. Use when the user says "validate temporal", "e2e temporal",
  "temporal regression", "temporal validation", "3-process test", "full temporal
  test", "validate phases", or wants comprehensive verification that distributed
  execution works end-to-end. Also use proactively after changes to LibraryCrate,
  deferred hydration, ClassRegistry scoping, or Temporal workflow code.
---

# Temporal E2E Validation Suite

Comprehensive regression and validation test suite for Temporal distributed execution.
Covers Phases 2-4 of the master plan: LibraryCrate propagation, deferred WorkingMemory
hydration, and per-workflow ClassRegistry/Library isolation.

## What each phase validates

| Phase | Feature | Risk if broken |
|-------|---------|----------------|
| **2** | LibraryCrate ships pipes to worker | `PipeNotFoundError` — worker can't resolve child pipes |
| **3** | Deferred WorkingMemory hydration | `KajsonDecoderError: Class not found` — dynamic concepts fail |
| **4** | Explicit ClassRegistry scoping | Silent data corruption — wrong concept fields, wrong pipe executed |

## How the two test modes complement each other

```
Mode 1: pytest --temporal-server local
  Client + Worker = same process, Real Temporal server
  --> Full assertions on 19 tests, fast (dry mode), catches logic regressions

Mode 2: pipelex run bundle --temporal (3-process)
  Server / Worker / Submitter = 3 separate OS processes
  --> Validates cross-process serialization, decoder bypass bug, real deployment path
```

Mode 1 catches logic regressions cheaply. Mode 2 catches topology-specific bugs that only
manifest with separate processes (e.g., `__module__="builtins"` decoder bypass, worker
sys.modules divergence). Run both for full confidence.

---

## Prerequisites

Verify these before starting:

```bash
which tmux && echo "ok" || echo "MISSING: brew install tmux"
which temporal && echo "ok" || echo "MISSING: brew install temporal"
.venv/bin/python -c "import temporalio; print(f'temporalio {temporalio.__version__}')"
```

---

## Mode 1: Automated Test Suite (pytest against real Temporal server)

This runs all 19 integration tests with detailed assertions. The Temporal server is real
(localhost:7233) but the worker runs in-process via test fixtures. No external worker needed.

### Step 1: Start the Temporal dev server

Check if already running (from a previous session or another terminal):

```bash
curl -s http://localhost:8233 > /dev/null 2>&1 && echo "running" || echo "not running"
```

If **not running**, start it:

```bash
tmux new-session -d -s temporal-server 'temporal server start-dev'
sleep 3
curl -s http://localhost:8233 > /dev/null 2>&1 && echo "running" || echo "FAILED"
```

Do NOT start the server if it's already running — it will fail with a bind error.

### Step 2: Run the full pytest suite

**Dry mode (default, fast, no LLM costs):**

```bash
.venv/bin/pytest -x -v tests/integration/pipelex/temporal/library_crate/ \
  -m temporal --temporal-server local 2>&1
```

**Live mode (real LLM calls, for full validation):**

```bash
.venv/bin/pytest -x -v tests/integration/pipelex/temporal/library_crate/ \
  -m temporal --temporal-server local --pipe-run-mode live 2>&1
```

### Step 3: Report results

Present results as a table:

| Suite | Tests | What it validates |
|-------|-------|-------------------|
| **TestWfLibraryCrate** | 5 | Crate structure, PipeSequence e2e, library_dirs + mthds_content paths, negative test (missing crate) |
| **TestWfDeferredHydration** | 2 | Dynamic concept class generation, WorkingMemory hydration after class registration |
| **TestWfConcurrentConceptIsolation** | 4 | Conflicting `Result` concepts in parallel workflows (5x repeated) |
| **TestWfConcurrentPipeIsolation** | 4 | Conflicting `shared_step` pipes in parallel workflows (5x repeated) |
| **TestWfMultiConceptIsolation** | 4 | Worst case: `Profile` + `Summary` with incompatible structures, 6 concurrent workflows |
| **TestWfPipeParallel** | 2 | PipeParallel concurrent child workflow dispatch + branch output merging |
| **TestWfPipeCondition** | 2 (1 xfail) | PipeCondition crate structure + child workflow dispatch |
| **TestWfPipeBatch** | 2 (1 xfail) | PipeBatch crate structure + fan-out child workflow dispatch |
| **TestWfPipeCompose** | 2 (1 xfail) | PipeCompose crate structure + deferred hydration of Report concept |
| **TestWfCombinedPipeline** | 2 (1 xfail) | Combined PipeParallel + PipeCondition nested dispatch |

**Known limitation (xfail tests):** PipeCondition, PipeBatch, and PipeCompose execution tests
fail in Temporal dry-run mode because their internal sub-workflows (`WfMakeJinja2Text` for
expression/template evaluation) try to serialize dry-run `StuffArtefact` objects through the
Temporal data converter. The crate structure tests pass, and PipeParallel execution works.
These xfail tests will automatically pass once the StuffArtefact serialization issue is fixed.

The test `test_missing_crate_fails_pipe_resolution` is a **negative test** — it intentionally
submits without a crate and expects `WorkflowFailureError`. The Temporal warning
`Failed activation on workflow` with `RuntimeError: No current library set` is expected.

---

## Mode 2: True 3-Process Validation

This runs the actual deployment topology: Temporal server, worker process, and submitter
as three separate OS processes. The worker has its own Python runtime with its own
`sys.modules` and ClassRegistry — no shared memory with the submitter.

This is the only way to validate:
- Cross-process Kajson deserialization (decoder bypass with `__module__="builtins"`)
- Worker receiving and loading a LibraryCrate it has never seen
- Real Temporal data converter encoding/decoding path

### Step 1: Ensure Temporal server is running

Same as Mode 1 Step 1. Skip if already running from Mode 1.

### Step 2: Start the worker process

The worker should NOT have test bundles in its PIPELEXPATH — the whole point is that
bundles arrive via the LibraryCrate in the PipeJob.

```bash
tmux has-session -t temporal-worker 2>/dev/null && tmux kill-session -t temporal-worker
tmux new-session -d -c "$PWD" -s temporal-worker \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed'
sleep 4
tmux capture-pane -t temporal-worker -p -S -30
```

Look for `Temporal Worker started for 'temporal_task_queue'`.

If the worker fails to start, check:
- Is the Temporal server running? (`curl -s http://localhost:8233`)
- Is the venv intact? (`.venv/bin/python --version`)

### Step 3: Run sequential tests (Tiers 1-3)

Submit each bundle one at a time. Each validates a specific phase.

**Tier 1 — Basic crate propagation (Phase 2):**

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/native_text_sequence.mthds \
  --pipe native_text_sequence \
  --temporal --dry-run --mock-inputs --no-logo
```

**Tier 2 — Deferred hydration with dynamic concepts (Phase 3):**

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/dynamic_concept_sequence.mthds \
  --pipe dynamic_greeting_sequence \
  --temporal --dry-run --mock-inputs --no-logo
```

**Tier 3 — PipeParallel controller (concurrent child workflows):**

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/temporal_parallel.mthds \
  --pipe temporal_parallel_sequence \
  --temporal --dry-run --mock-inputs --no-logo
```

If Tier 2 fails with `KajsonDecoderError: Class 'X' not found`, the deferred hydration
path is broken — the worker tried to deserialize WorkingMemory before registering
dynamic concept classes from the crate.

**For all tiers**: if the command hangs for more than 30 seconds, check worker output:

```bash
tmux capture-pane -t temporal-worker -p -S -100
```

### Step 4: Run concurrent isolation tests (Tier 3 — Phase 4)

These test that two workflows with conflicting class/pipe names can run simultaneously
on the same worker without cross-contamination. Submit alpha and beta jobs in parallel.

**Concurrent concept isolation** (conflicting `Result` concept):

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/conflict_concept_alpha.mthds \
  --pipe alpha_pipeline \
  --temporal --dry-run --mock-inputs --no-logo &
PID_ALPHA=$!

.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/conflict_concept_beta.mthds \
  --pipe beta_pipeline \
  --temporal --dry-run --mock-inputs --no-logo &
PID_BETA=$!

wait $PID_ALPHA && echo "Alpha: PASS" || echo "Alpha: FAIL"
wait $PID_BETA && echo "Beta: PASS" || echo "Beta: FAIL"
```

**Concurrent pipe isolation** (conflicting `shared_step` pipe):

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/conflict_pipe_alpha.mthds \
  --pipe pipe_alpha_pipeline \
  --temporal --dry-run --mock-inputs --no-logo &
PID_ALPHA=$!

.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/conflict_pipe_beta.mthds \
  --pipe pipe_beta_pipeline \
  --temporal --dry-run --mock-inputs --no-logo &
PID_BETA=$!

wait $PID_ALPHA && echo "Alpha: PASS" || echo "Alpha: FAIL"
wait $PID_BETA && echo "Beta: PASS" || echo "Beta: FAIL"
```

**Multi-concept worst case** (conflicting `Profile` + `Summary`):

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/multi_concept_alpha.mthds \
  --pipe multi_alpha_pipeline \
  --temporal --dry-run --mock-inputs --no-logo &
PID_ALPHA=$!

.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/multi_concept_beta.mthds \
  --pipe multi_beta_pipeline \
  --temporal --dry-run --mock-inputs --no-logo &
PID_BETA=$!

wait $PID_ALPHA && echo "Alpha: PASS" || echo "Alpha: FAIL"
wait $PID_BETA && echo "Beta: PASS" || echo "Beta: FAIL"
```

### Step 5: Report 3-process results

Present a summary table:

| Test | Bundle | Status | Phase validated |
|------|--------|--------|-----------------|
| Basic crate propagation | native_text_sequence | PASS/FAIL | Phase 2 |
| Deferred hydration | dynamic_concept_sequence | PASS/FAIL | Phase 3 |
| PipeParallel controller | temporal_parallel | PASS/FAIL | Phase 2 |
| Concurrent concepts (alpha) | conflict_concept_alpha | PASS/FAIL | Phase 4 |
| Concurrent concepts (beta) | conflict_concept_beta | PASS/FAIL | Phase 4 |
| Concurrent pipes (alpha) | conflict_pipe_alpha | PASS/FAIL | Phase 4 |
| Concurrent pipes (beta) | conflict_pipe_beta | PASS/FAIL | Phase 4 |
| Multi-concept (alpha) | multi_concept_alpha | PASS/FAIL | Phase 4 |
| Multi-concept (beta) | multi_concept_beta | PASS/FAIL | Phase 4 |

If any concurrent tests fail, capture worker output for diagnosis:

```bash
tmux capture-pane -t temporal-worker -p -S -200
```

---

## Cleanup

Kill tmux sessions when done:

```bash
tmux kill-session -t temporal-worker 2>/dev/null
tmux kill-session -t temporal-server 2>/dev/null
```

Or leave the server running if you plan to iterate.

---

## Interpreting failures

| Error | Cause | Phase |
|-------|-------|-------|
| `PipeNotFoundError` on worker | LibraryCrate not loaded or not propagated | Phase 2 |
| `KajsonDecoderError: Class 'X' not found` | Dynamic concept classes not registered before WM deserialization | Phase 3 |
| `RuntimeError: Failed decoding arguments` | Kajson data converter can't deserialize PipeJob on worker | Phase 3/4 |
| `WorkflowFailureError` wrapping `TemporalError` | Pipe execution failed — read inner error for real cause | Any |
| `AssertionError: StructuredContent missing field` | ClassRegistry scoping failed — wrong concept class used | Phase 4 |
| Submitter hangs indefinitely | Worker crashed during deserialization (check worker pane output) | Phase 3 |
| Both concurrent jobs succeed but with wrong data | ContextVar leak between workflows — per-workflow scoping broken | Phase 4 |

---

## Bundle reference

All bundles are in `tests/integration/pipelex/temporal/library_crate/`:

| Bundle | Domain | Concepts | Main pipe | Phase |
|--------|--------|----------|-----------|-------|
| `native_text_sequence.mthds` | `native_text_test` | (native Text only) | `native_text_sequence` | 2 |
| `dynamic_concept_sequence.mthds` | `dynamic_concept_test` | Greeting(message, language) | `dynamic_greeting_sequence` | 3 |
| `conflict_concept_alpha.mthds` | `conflict_alpha` | Result(score, label) | `alpha_pipeline` | 4 |
| `conflict_concept_beta.mthds` | `conflict_beta` | Result(value, confidence, is_valid) | `beta_pipeline` | 4 |
| `conflict_pipe_alpha.mthds` | `pipe_conflict_alpha` | (native Text only) | `pipe_alpha_pipeline` | 4 |
| `conflict_pipe_beta.mthds` | `pipe_conflict_beta` | (native Text only) | `pipe_beta_pipeline` | 4 |
| `multi_concept_alpha.mthds` | `multi_alpha` | Profile(name, age), Summary(headline, body) | `multi_alpha_pipeline` | 4 |
| `multi_concept_beta.mthds` | `multi_beta` | Profile(title, department, level), Summary(content) | `multi_beta_pipeline` | 4 |
| `temporal_condition.mthds` | `temporal_condition_test` | CategoryLabel | `temporal_condition_sequence` | Controller coverage |
| `temporal_parallel.mthds` | `temporal_parallel_test` | ToneAnalysis, LengthAnalysis | `temporal_parallel_sequence` | Controller coverage |
| `temporal_batch.mthds` | `temporal_batch_test` | Topic, TopicNote | `temporal_batch_sequence` | Controller coverage |
| `temporal_compose.mthds` | `temporal_compose_test` | Report(title, body) | `temporal_compose_sequence` | Operator + Phase 3 |
| `temporal_combined.mthds` | `temporal_combined_test` | QualityReport(assessment, confidence), PartContent | `temporal_combined_pipeline` | Mixed controllers |
