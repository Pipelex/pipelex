# Flaky under full suite: `test_transported_run_generates_concept_structures`

`tests/unit/pipelex/pipe_operators/pipe_func/test_direct_executor_workdir.py::TestDirectExecutorWorkdir::test_transported_run_generates_concept_structures` failed in three of four full-suite runs on `feature/Engine-hints` (both checkpoint `make test` runs and the final `make test`; the Phase 5 `make agent-test` run passed) with:

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for PipeFunc
function_name: Value error, Function 'greet_it' not found in registry
  (raised from pipelex/pipe_operators/func/pipe_func_factory.py:28, during load_libraries)
```

It passes in isolation and when its whole module runs alone (16/16). Evidence that this is a pre-existing order-dependent flake, not an Engine-hints regression:

- The test sets `get_config().interpreter.pipe_func.execution_mode = "local_sandbox"` (the mode whose loader tolerates a yet-unregistered function) immediately before `load_libraries`, restoring it in `finally`. The observed failure means the loader read a non-tolerant mode — i.e. under xdist the config object the factory reads was not the one the test mutated, which is a test-isolation problem around the shared `get_config()` singleton, not a hints problem.
- The hints diff touches concept/pipe blueprints, crate normalization, the input-form deriver and an advisory lint. It does not touch config plumbing, PipeFunc, the func registry, or execution modes.
- The test file was last modified by the ruff 0.16.4 move (`6214a7b4f`), before this branch existed.

Suggested fix direction (deferred, not done here to avoid scope creep on the hints PR): make the test independent of the live config singleton — e.g. patch `execution_mode` via `mocker.patch.object` on the exact config instance the loader reads, or give the loader an explicit mode parameter for tests.
