# BUG: ClassRegistry Isolation Failure for Same-Named Dynamic Concepts Across Concurrent Temporal Workflows

## Summary

When two Temporal workflows run concurrently on the same worker, and each defines a dynamic concept with the **same class name** but **different field structures**, the per-workflow ClassRegistry scoping fails to fully isolate them. One workflow's dynamically-generated class leaks into the other's deserialization path, causing either a `KajsonDecoderError` (wrong fields) or silent data corruption (wrong data returned without error).

## Severity

**High** — this is a silent data corruption risk in production. If two pipelines happen to define a concept with the same name (e.g., `Result`, `Profile`, `Summary`), the worker can deserialize data using the wrong class. In the best case this crashes; in the worst case it silently returns wrong data.

## Root Cause

The per-workflow ClassRegistry scoping in `WfPipeRouter.run()` (`pipelex/temporal/tprl_pipe/wf_pipe_router.py`) creates a workflow-specific registry pre-seeded from the global one, but the dynamic class registration during `load_from_crate()` doesn't fully isolate from other concurrent workflows. The bare class name (e.g., `Result`, not `conflict_alpha.Result`) is used as the registry key, so two workflows registering different `Result` classes collide.

### Relevant code path

```
WfPipeRouter.run(pipe_job)
  ├─ global_registry = KajsonManager.get_class_registry()           # global, shared
  ├─ workflow_registry = ClassRegistry()                             # new, per-workflow
  ├─ workflow_registry.register_classes_dict(dict(global_registry))  # pre-seed from global
  ├─ library_manager.open_library(library_id=wf_library_id)
  ├─ wf_library.set_class_registry(workflow_registry)
  ├─ set_current_library(library_id=wf_library_id)                  # ContextVar scoping
  ├─ library_manager.load_from_crate(wf_library_id, crate)          # registers dynamic classes
  │   └─ ConceptFactory generates class "Result" → registered in workflow_registry
  │      BUT: class name is bare "Result", not domain-qualified
  └─ hydrate_working_memory(working_memory_raw)                     # uses get_class_registry()
```

The issue: `get_class_registry()` in `hub.py` uses a `ContextVar` to route to the per-workflow registry. But during Kajson deserialization of the PipeJob itself (before `set_current_library` is called), the global registry is used. And if the worker's base library (loaded at startup from PIPELEXPATH) already registered a class named `Result`, that class persists in the global registry and is used for all incoming workflows.

### Key files

| File | Role |
|------|------|
| `pipelex/temporal/tprl_pipe/wf_pipe_router.py` | Per-workflow scoping setup (lines 36-58) |
| `pipelex/hub.py` | `get_class_registry()` with ContextVar routing (lines 381-392) |
| `pipelex/hub.py` | `_library_id` ContextVar (line 462) |
| `kajson/kajson/class_registry.py` | ClassRegistry — bare class name as key |
| `pipelex/core/concepts/concept_factory.py` | Dynamic class generation (line 331) |
| `pipelex/temporal/temporal_data_converter.py` | Kajson data converter for Temporal |
| `pipelex/temporal/worker_cli.py` | Worker startup — loads base library into global registry |

## Reproducing with pytest (fast, automated)

The failing tests are in `tests/integration/pipelex/temporal/library_crate/`. They use an in-process Temporal test server — no external processes needed.

```bash
# Run all temporal isolation tests (4 will fail, rest pass)
.venv/bin/pytest -x -v -s tests/integration/pipelex/temporal/library_crate/ -m temporal

# Run only the concurrent concept isolation test (minimal repro)
.venv/bin/pytest -x -v -s tests/integration/pipelex/temporal/library_crate/test_wf_concurrent_concept_isolation.py -m temporal -k test_concurrent_different_results
```

### Failing tests

| Test | What it proves |
|------|---------------|
| `test_wf_concurrent_concept_isolation.py::test_concurrent_different_results` | Two workflows with `Result(score,label)` vs `Result(value,confidence,is_valid)` run on same worker → wrong class used for deserialization |
| `test_wf_concurrent_concept_isolation.py::test_repeated_concurrent` | Same as above, repeated 5x to catch intermittent races |
| `test_wf_multi_concept_isolation.py::test_concurrent_multi_concept` | Two workflows with conflicting `Profile` AND `Summary` classes → multi-class collision |
| `test_wf_multi_concept_isolation.py::test_high_concurrency_multi_concept` | 6 workflows (3 pairs) running simultaneously → stress test |

### Passing tests (isolation works for these cases)

| Test | Why it passes |
|------|--------------|
| All `*_solo` tests | Single workflow alone — no collision possible |
| `test_wf_concurrent_pipe_isolation.py::*` | Pipe refs are domain-qualified (`pipe_conflict_alpha.shared_step`), so library lookup doesn't collide |
| `test_wf_library_crate.py::*` | Native Text concepts only — no dynamic classes |
| `test_wf_deferred_hydration.py::*` | Single workflow with dynamic concept — no collision |

### Error output

```
KajsonDecoderError: Could not instantiate pydantic BaseModel '<class 'Result'>' using kwargs:
  2 validation errors for Result
  value
    Field required [type=missing, input_value={'score': 2232, 'label': 'hYCLCOKL...'}, input_type=dict]
  confidence
    Field required [type=missing, input_value={'score': 2232, 'label': 'hYCLCOKL...'}, input_type=dict]
  is_valid
    Field required [type=missing, input_value={'score': 2232, 'label': 'hYCLCOKL...'}, input_type=dict]
```

Beta's `Result(value, confidence, is_valid)` class is being used to deserialize alpha's data `{score, label}`.

## Reproducing with the manual 3-terminal setup (realistic, uses `/temporal-diagnose` skill)

This exercises the real Temporal server + external worker path.

### Setup

```bash
# 1. Create isolated bundle directories
mkdir -p /tmp/temporal-test-alpha /tmp/temporal-test-beta
cp tests/integration/pipelex/temporal/library_crate/conflict_concept_alpha.mthds /tmp/temporal-test-alpha/
cp tests/integration/pipelex/temporal/library_crate/conflict_concept_beta.mthds /tmp/temporal-test-beta/

# 2. Start Temporal server
tmux new-session -d -s temporal-server 'temporal server start-dev'
sleep 3

# 3. Start worker with alpha's base library
tmux new-session -d -c "$PWD" -s temporal-worker \
  'PIPELEXPATH=/tmp/temporal-test-alpha .venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed'
sleep 4
```

### Test 1 — Alpha pipeline (should succeed)

```bash
.venv/bin/pipelex run bundle /tmp/temporal-test-alpha/conflict_concept_alpha.mthds \
  --pipe alpha_pipeline --temporal --dry-run --mock-inputs --no-logo
```

Expected: `✓ Dry run completed successfully`

### Test 2 — Beta pipeline on same worker (should fail)

```bash
.venv/bin/pipelex run bundle /tmp/temporal-test-beta/conflict_concept_beta.mthds \
  --pipe beta_pipeline --temporal --dry-run --mock-inputs --no-logo
```

Expected: submitter hangs indefinitely. Worker logs show:

```
KajsonDecoderError: 2 validation errors for Result
  score: Field required [input_value={'value': '...', ...}]
  label: Field required [input_value={'value': '...', ...}]
```

The worker's global ClassRegistry has alpha's `Result(score, label)` from the base library load. When beta's PipeJob arrives carrying `Result(value, confidence, is_valid)` data, Kajson uses the wrong class.

### Cleanup

```bash
tmux kill-session -t temporal-worker 2>/dev/null
tmux kill-session -t temporal-server 2>/dev/null
rm -rf /tmp/temporal-test-alpha /tmp/temporal-test-beta
```

## Test bundles

All test bundles are in `tests/integration/pipelex/temporal/library_crate/`:

| Bundle | Domain | Concept `Result` fields | Purpose |
|--------|--------|------------------------|---------|
| `conflict_concept_alpha.mthds` | `conflict_alpha` | `score` (integer), `label` (text) | Alpha side of concept collision |
| `conflict_concept_beta.mthds` | `conflict_beta` | `value` (text), `confidence` (number), `is_valid` (text) | Beta side of concept collision |
| `conflict_pipe_alpha.mthds` | `pipe_conflict_alpha` | (native Text only) | Alpha side of pipe name collision |
| `conflict_pipe_beta.mthds` | `pipe_conflict_beta` | (native Text only) | Beta side of pipe name collision |
| `multi_concept_alpha.mthds` | `multi_alpha` | `Profile(name,age)` + `Summary(headline,body)` | Multi-class collision alpha |
| `multi_concept_beta.mthds` | `multi_beta` | `Profile(title,department,level)` + `Summary(content)` | Multi-class collision beta |

## Fix direction

The class name used as registry key needs to be **domain-qualified** (e.g., `conflict_alpha.Result` instead of bare `Result`), or the per-workflow ClassRegistry must be used during PipeJob deserialization (not just during `load_from_crate` and hydration). Candidate approaches:

1. **Domain-qualify dynamic class names**: Change `ConceptFactory` / `StructureGenerator` to generate classes named `{domain}_{concept_code}` (e.g., `conflict_alpha_Result`). This avoids collisions at the class name level. Requires updating Kajson serialization to use the qualified name.

2. **Ensure per-workflow registry is active during full deserialization**: Set the `ContextVar` library_id before Temporal deserializes the PipeJob, not after. This may require changes to the Temporal data converter to set up scoping before deserialization.

3. **Isolate the global registry from base library dynamic classes**: Don't register dynamic concept classes from PIPELEXPATH into the global registry at worker startup. Instead, treat all dynamic classes as per-workflow only.

Approach 3 is the most defensive and doesn't require Kajson changes, but needs careful analysis of what breaks if the global registry lacks dynamic classes.
