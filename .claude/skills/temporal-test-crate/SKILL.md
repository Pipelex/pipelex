---
name: temporal-test-crate
description: "Run and diagnose the Phase 2 LibraryCrate integration tests for Temporal. Tests that PipeSequence controllers execute on Temporal workers via LibraryCrate propagation. Use when the user says 'test temporal crate', 'run crate tests', 'phase 2 tests', or wants to verify LibraryCrate on Temporal works."
---

# Temporal LibraryCrate Integration Tests

Run the Phase 2 integration tests that verify LibraryCrate propagation through Temporal workflows.

## What these tests verify

- PipeJob carries a LibraryCrate with expected pipe_refs, concept_refs, and fingerprint
- WfPipeRouter loads the crate on the worker, enabling `get_required_pipe()` for child pipes
- PipeSequence controller (with child PipeLLM steps) executes end-to-end in DRY mode
- Both `library_dirs` (PIPELEXPATH-style) and `mthds_content` (string) loading paths work

## Prerequisites

```bash
# Verify venv and temporalio
.venv/bin/python -c "import temporalio; print(f'temporalio {temporalio.__version__}')"
# Verify test bundle exists
ls tests/integration/pipelex/pipes/controller/pipe_sequence/pipe_sequence_1.mthds
```

## Run the tests

```bash
.venv/bin/pytest -x -v -s tests/integration/pipelex/temporal/async/library_crate/ -m temporal
```

## Interpreting failures

| Error | Cause | Action |
|-------|-------|--------|
| `PipeNotFoundError` on worker | LibraryCrate not loaded or not propagated | Check `WfPipeRouter.run()` loads crate; check `library_crate` is set on PipeJob |
| `KajsonDecoderError: Class 'X' not found` | Dynamic concept classes not registered on worker (Layer 1) | This is a **Phase 3** issue — deferred WorkingMemory hydration needed |
| `RuntimeError: Failed decoding arguments` | Temporal can't deserialize PipeJob | Check Kajson data converter; may be a serialization issue with LibraryCrate |
| `WorkflowFailureError` wrapping `TemporalError` | Pipe execution failed on worker | Read the inner error — it's the real cause |
| Fixture setup error in `pipe_job_from_*` | Library loading failed before Temporal dispatch | Check bundle file exists and is valid MTHDS |

## Interactive debugging

For tmux-based 3-terminal debugging (server + worker + submitter), use the `/temporal-diagnose` skill instead.

## Test files

| File | Purpose |
|------|---------|
| `tests/integration/pipelex/temporal/async/library_crate/test_wf_library_crate.py` | 4 integration tests |
| `tests/integration/pipelex/temporal/async/library_crate/conftest.py` | PipeJob fixtures with LibraryCrate |
| `tests/integration/pipelex/temporal/async/library_crate/test_data.py` | Test constants |
