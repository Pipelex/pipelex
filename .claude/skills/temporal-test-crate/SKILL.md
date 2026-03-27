---
name: temporal-test-crate
description: "Run and diagnose the Phase 2+ LibraryCrate integration tests for Temporal. Tests that PipeSequence controllers execute on Temporal workers via LibraryCrate propagation, including concurrent isolation tests for conflicting concepts and pipes. Use when the user says 'test temporal crate', 'run crate tests', 'phase 2 tests', 'isolation tests', or wants to verify LibraryCrate on Temporal works."
---

# Temporal LibraryCrate Integration Tests

Run the integration tests that verify LibraryCrate propagation and per-workflow isolation through Temporal workflows.

## Architecture overview

```
┌──────────────────────────────────────────────────────────────┐
│                    Temporal Test Server                       │
│                   (in-process, local)                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────── Worker (shared process) ────────────────┐ │
│  │                                                          │ │
│  │  ┌─ Workflow A ─────────────┐ ┌─ Workflow B ──────────┐ │ │
│  │  │ LibraryCrate A           │ │ LibraryCrate B         │ │ │
│  │  │ ClassRegistry A (scoped) │ │ ClassRegistry B (scoped)│ │ │
│  │  │ Library A (ContextVar)   │ │ Library B (ContextVar) │ │ │
│  │  └──────────────────────────┘ └────────────────────────┘ │ │
│  │                                                          │ │
│  │  Global ClassRegistry (base types only, pre-seeded)      │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                              │
│  Each workflow gets its own ClassRegistry (pre-seeded from   │
│  global) and library (scoped via ContextVar). Dynamic        │
│  concept classes are registered per-workflow, not globally.  │
└──────────────────────────────────────────────────────────────┘
```

## What these tests verify

### Phase 2: Single-workflow crate propagation
- PipeJob carries a LibraryCrate with expected pipe_refs, concept_refs, and fingerprint
- WfPipeRouter loads the crate on the worker, enabling `get_required_pipe()` for child pipes
- PipeSequence controller (with child PipeLLM steps) executes end-to-end
- Both `library_dirs` (PIPELEXPATH-style) and `mthds_content` (string) loading paths work

### Phase 3: Deferred hydration
- Dynamic concept classes are generated on the worker from the crate
- WorkingMemory is hydrated after class registration (deferred hydration)
- StructuredContent fields are accessible on the worker

### Phase 4: Concurrent isolation

**Scenario 1 — Same concept name, incompatible structures:**
```
┌─ Workflow A ─────────────┐ ┌─ Workflow B ─────────┐
│ concept "Result":        │ │ concept "Result":     │
│   score: int             │ │   value: text         │
│   label: text            │ │   confidence: number  │
│                          │ │   is_valid: text      │
│ ClassRegistry A (scoped) │ │ ClassRegistry B       │
└──────────────────────────┘ └───────────────────────┘
```
Without per-workflow scoping, one `Result` class overwrites the other — **silent data corruption**.

**Scenario 2 — Same pipe name, different behavior:**
```
┌─ Workflow A ─────────────┐ ┌─ Workflow B ─────────┐
│ pipe "shared_step":      │ │ pipe "shared_step":   │
│   prompt: about colors   │ │   prompt: about animals│
│ Library A (ContextVar)   │ │ Library B (ContextVar) │
└──────────────────────────┘ └────────────────────────┘
```
Without per-workflow library scoping, `get_required_pipe("shared_step")` resolves the wrong pipe.

**Scenario 3 — Multiple conflicting dynamic classes (worst case):**
```
┌─ Workflow A ─────────────┐ ┌─ Workflow B ─────────┐
│ "Profile":               │ │ "Profile":            │
│   name: text             │ │   title: text         │
│   age: integer           │ │   department: text    │
│                          │ │   level: integer      │
│ "Summary":               │ │ "Summary":            │
│   headline: text         │ │   content: text       │
│   body: text             │ │                       │
└──────────────────────────┘ └───────────────────────┘
```
Two dynamic classes named `Profile` and two named `Summary` coexist on the same worker.

## Run the tests

```bash
# DRY mode (fast, no API calls — default)
.venv/bin/pytest -x -v -s tests/integration/pipelex/temporal/library_crate/ -m temporal

# LIVE mode (real LLM calls, realistic concurrency timing)
.venv/bin/pytest -x -v -s tests/integration/pipelex/temporal/library_crate/ -m temporal --pipe-run-mode live

# Run only the isolation tests
.venv/bin/pytest -x -v -s tests/integration/pipelex/temporal/library_crate/ -m temporal -k "Concurrent or Multi"
```

## Prerequisites

```bash
# Verify venv and temporalio
.venv/bin/python -c "import temporalio; print(f'temporalio {temporalio.__version__}')"
# Verify test bundles exist
ls tests/integration/pipelex/temporal/library_crate/*.mthds
```

## Interpreting failures

| Error | Cause | Action |
|-------|-------|--------|
| `PipeNotFoundError` on worker | LibraryCrate not loaded or not propagated | Check `WfPipeRouter.run()` loads crate; check `library_crate` is set on PipeJob |
| `KajsonDecoderError: Class 'X' not found` | Dynamic concept classes not registered on worker | Check deferred hydration path in `WfPipeRouter.run()` |
| `RuntimeError: Failed decoding arguments` | Temporal can't deserialize PipeJob | Check Kajson data converter; may be a serialization issue with LibraryCrate |
| `WorkflowFailureError` wrapping `TemporalError` | Pipe execution failed on worker | Read the inner error — it's the real cause |
| Fixture setup error in `pipe_job_from_*` | Library loading failed before Temporal dispatch | Check bundle file exists and is valid MTHDS |
| `AssertionError: StructuredContent missing field` | ClassRegistry scoping failed — wrong class used | Per-workflow ContextVar is leaking; check `set_current_library` / `teardown_current_library` |
| `AssertionError` in repeated/high-concurrency tests | Intermittent ContextVar race condition | Scoping mechanism has a race under load |

## Interactive debugging

For tmux-based 3-terminal debugging (server + worker + submitter), use the `/temporal-diagnose` skill instead.

## Test files

| File | Purpose |
|------|---------|
| `tests/integration/pipelex/temporal/library_crate/test_wf_library_crate.py` | Phase 2: single-workflow crate propagation (native Text concepts) |
| `tests/integration/pipelex/temporal/library_crate/test_wf_deferred_hydration.py` | Phase 3: deferred hydration with dynamic concept (Greeting) |
| `tests/integration/pipelex/temporal/library_crate/test_wf_concurrent_concept_isolation.py` | Phase 4: two workflows with conflicting 'Result' concepts |
| `tests/integration/pipelex/temporal/library_crate/test_wf_concurrent_pipe_isolation.py` | Phase 4: two workflows with conflicting 'shared_step' pipes |
| `tests/integration/pipelex/temporal/library_crate/test_wf_multi_concept_isolation.py` | Phase 4: worst-case multi-class conflicts (Profile + Summary) |
| `tests/integration/pipelex/temporal/library_crate/conftest.py` | PipeJob fixtures with LibraryCrate for all scenarios |
| `tests/integration/pipelex/temporal/test_data.py` | Test constants for all scenarios |

## Bundle files

| Bundle | Domain | Concepts | Pipes |
|--------|--------|----------|-------|
| `native_text_sequence.mthds` | `native_text_test` | (native Text only) | native_text_sequence, step_one, step_two |
| `dynamic_concept_sequence.mthds` | `dynamic_concept_test` | Greeting(message, language) | dynamic_greeting_sequence, generate_greeting, summarize_greeting |
| `conflict_concept_alpha.mthds` | `conflict_alpha` | Result(score, label) | alpha_pipeline, alpha_generate, alpha_summarize |
| `conflict_concept_beta.mthds` | `conflict_beta` | Result(value, confidence, is_valid) | beta_pipeline, beta_generate, beta_summarize |
| `conflict_pipe_alpha.mthds` | `pipe_conflict_alpha` | (native Text only) | pipe_alpha_pipeline, shared_step, alpha_finalize |
| `conflict_pipe_beta.mthds` | `pipe_conflict_beta` | (native Text only) | pipe_beta_pipeline, shared_step, beta_finalize |
| `multi_concept_alpha.mthds` | `multi_alpha` | Profile(name, age), Summary(headline, body) | multi_alpha_pipeline, generate_profile, generate_summary, finalize |
| `multi_concept_beta.mthds` | `multi_beta` | Profile(title, department, level), Summary(content) | multi_beta_pipeline, generate_profile, generate_summary, finalize |
