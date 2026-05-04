---
name: temporal-test-crate
description: "Run and diagnose the LibraryCrate integration tests for Temporal. Tests that PipeSequence controllers execute on Temporal workers via LibraryCrate propagation, including concurrent isolation tests for conflicting concepts and pipes. Use when the user says 'test temporal crate', 'run crate tests', 'isolation tests', or wants to verify LibraryCrate on Temporal works."
---

# Temporal LibraryCrate Integration Tests

Run the integration tests that verify LibraryCrate propagation and per-workflow isolation through Temporal workflows.

## How to narrate the test run

Before running the tests, print a brief schematic explanation for the user so they understand what they're about to see. Use this narration:

---

### What we're testing

These tests verify that **LibraryCrate** — the serializable snapshot of pipes, concepts, and dynamic classes — propagates correctly from the client to Temporal workers, and that concurrent workflows remain isolated from each other.

**The components and how they interact:**

```
Client (test fixture)                    Temporal Worker
─────────────────────                    ───────────────

1. Load .mthds bundle
2. Build LibraryCrate (pipes,
   concepts, fingerprint)
3. Build PipeJob with crate attached
4. Submit workflow ──────────────────►   5. WfPipeRouter.run() receives PipeJob
                                         6. load_from_crate() → registers pipes
                                            into a scoped Library (ContextVar)
                                         7. Dynamic concept classes generated
                                            into a scoped ClassRegistry (ContextVar)
                                         8. WorkingMemory hydrated (deferred)
                                         9. PipeSequence executes child pipes
                                            via get_required_pipe() from the
                                            scoped library
                                         10. PipeOutput returned to client
```

**The 5 test suites (19 tests total):**

| Suite | What it proves | Key risk if broken |
|-------|---------------|--------------------|
| **TestWfLibraryCrate** (5 tests) | Crate structure is valid, PipeSequence runs end-to-end via Temporal, both `library_dirs` and `mthds_content` loading paths work. Includes a **negative test** (`test_missing_crate_fails_pipe_resolution`) that verifies a PipeJob *without* a crate correctly fails. | Pipes can't resolve on worker |
| **TestWfDeferredHydration** (2 tests) | Dynamic concept classes (e.g. `Greeting`) are generated on the worker from crate data, WorkingMemory is hydrated after class registration, StructuredContent fields are accessible. | `KajsonDecoderError: Class not found` |
| **TestWfConcurrentConceptIsolation** (4 tests) | Two workflows define conflicting `Result` concepts (different fields) and run simultaneously on one worker. Per-workflow ClassRegistry scoping keeps them isolated. Repeated 5x to catch races. | Silent data corruption — wrong fields |
| **TestWfConcurrentPipeIsolation** (4 tests) | Two workflows define conflicting `shared_step` pipes (different prompts) and run simultaneously. Per-workflow Library scoping ensures each resolves its own pipe. Repeated 5x. | Wrong pipe executed silently |
| **TestWfMultiConceptIsolation** (4 tests) | Worst case: two workflows each define `Profile` AND `Summary` with incompatible structures. 6 concurrent workflows stress-test ContextVar scoping. | Multiple classes cross-contaminate |

---

After running the tests, report results with a summary table showing pass/fail per suite.

## Run the tests

### Step 1: Dry run (default)

Always start with dry mode — fast, no API calls:

```bash
.venv/bin/pytest -x -v -s tests/integration/pipelex/temporal/library_crate/ -m temporal
```

To run only the isolation tests:

```bash
.venv/bin/pytest -x -v -s tests/integration/pipelex/temporal/library_crate/ -m temporal -k "Concurrent or Multi"
```

### Step 2: Live run (optional)

After a successful dry run, ask the user if they want to run in **live mode**. Live mode makes real LLM API calls and exercises realistic concurrency timing — it's the closest thing to production behavior:

```bash
.venv/bin/pytest -x -v -s tests/integration/pipelex/temporal/library_crate/ -m temporal --pipe-run-mode live
```

When reporting live-mode results, show:
- Pass/fail per test with the test name
- For passing tests, confirm that structured outputs had the expected fields (e.g. "Alpha Result had score + label", "Beta Result had value + confidence + is_valid")
- For concurrent tests, confirm that both workflows returned correct results simultaneously
- Total wall-clock time (live mode is slower due to real API calls)

## Expected warnings in test output

`test_missing_crate_fails_pipe_resolution` is a **negative test** — it intentionally submits a PipeJob *without* a LibraryCrate and asserts that `WorkflowFailureError` is raised. During this test, Temporal logs a `WARNING Failed activation on workflow` with a full traceback ending in `RuntimeError: No current library set`. **This is expected behavior, not a failure.** The test passes (PASSED) because the expected error was correctly raised.

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

For tmux-based 3-terminal debugging (server + worker + submitter), use the `/temporal-e2e-validate` skill (Mode 2) instead.

## Test files

| File | Purpose |
|------|---------|
| `tests/integration/pipelex/temporal/library_crate/test_wf_library_crate.py` | Single-workflow crate propagation (native Text concepts) |
| `tests/integration/pipelex/temporal/library_crate/test_wf_deferred_hydration.py` | Deferred hydration with dynamic concept (Greeting) |
| `tests/integration/pipelex/temporal/library_crate/test_wf_concurrent_concept_isolation.py` | Two workflows with conflicting 'Result' concepts |
| `tests/integration/pipelex/temporal/library_crate/test_wf_concurrent_pipe_isolation.py` | Two workflows with conflicting 'shared_step' pipes |
| `tests/integration/pipelex/temporal/library_crate/test_wf_multi_concept_isolation.py` | Worst-case multi-class conflicts (Profile + Summary) |
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
