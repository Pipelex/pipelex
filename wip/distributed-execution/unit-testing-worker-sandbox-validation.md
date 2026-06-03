# Follow-up: worker can't boot under `--is-unit-testing` (test workflows fail sandbox validation)

Deferred bug, found 2026-06-02 on `feature/Validate-with-signatures-4-fix-dry-run` while re-running the `/temporal-e2e-validate` Step 9 battery. Surfaced by the Scenario F sanity-check (`references/queue-options-battery.md`); orthogonal to the queue-options surface that battery validates. Not investigated beyond what's recorded here.

## Symptom

Starting a standalone Temporal worker in unit-test mode **with the sandbox enabled** fails to boot:

```bash
.venv/bin/python -m pipelex.temporal.worker_cli --task-queue temporal_task_queue --is-unit-testing
# ... passes config load + the task-queue validator ...
# RuntimeError: Failed validating workflow <a test-only workflow>
```

The `--task-queue` validator (`worker_cli.py:75`) runs **earlier** and is unaffected — this failure happens later, during `Worker(...)` construction. So it does **not** block the queue-options/routing work; it blocks a sandboxed unit-testing worker from coming up at all.

## What fires

`--is-unit-testing` (`worker_cli.py:50`) sets `RunMode.UNIT_TEST` and registers the test workflows from `pipelex/temporal/test_extras/temporal_test_tasks.py` (`temporal_task_manager.py:175-184`): `TEMPORAL_TEST_WORKFLOWS` = `WfTestContentGeneratorChild`, `WfTestContentGeneratorPdfPageViews`, `WfTestStructuredOutputCrossProcess`. temporalio then validates each registered workflow against the default `SandboxedWorkflowRunner`, and at least one fails.

The failing workflow is **non-deterministic across the set** (validation order). Observed on two separate runs:

- `Failed validating workflow wf_test_content_generator_child`
- `Failed validating workflow wf_test_structured_output_cross_process`

Concrete sandbox-restriction causes captured:

- `temporalio.worker.workflow_sandbox._restrictions.RestrictedWorkflowAccessError: Cannot access random.getrandbits.__class__ from inside a workflow. If this is code from a module not used in a workflow or known to only be used deterministically from a workflow, mark the import as pass through.`
- `ImportError: cannot import name 'Style' from partially initialized module 'rich.style' (most likely due to a circular import)` — `rich` pulled in at validation time inside the sandbox.

## Why it matters / scope

The failure requires the **sandboxed** runner (the default). The battery's real workers are all started with `--is-not-sandboxed`, which swaps in the unsandboxed runner and skips this validation — so the bug is latent for those. The Scenario F sanity-check is the path that exercised `--is-unit-testing` *without* `--is-not-sandboxed`, exposing it.

Two things worth resolving:

1. **Can a unit-testing worker run sandboxed at all?** If `--is-unit-testing` is only ever meant to pair with `--is-not-sandboxed`, that pairing should be enforced/documented. If not, the test workflows must be sandbox-safe.
2. **The test workflows are not sandbox-clean.** Non-deterministic access (`random.getrandbits`) and non-passthrough imports (`rich`) inside a workflow body are exactly what the sandbox is meant to catch — so even setting aside the boot failure, these test workflows would mask real non-determinism if anything depended on them running sandboxed.

## Likely fix locus

- The sandbox passthrough-modules list in `pipelex/temporal/temporal_task_manager.py` (`SandboxRestrictions.default.with_passthrough_modules(...)`, ~lines 103-119) is missing the test-extras modules and their transitive imports (`rich`, the in-memory storage provider used by `WfTestStructuredOutputCrossProcess`). Adding them is the narrow fix.
- Alternatively, wrap the offending imports/calls in the test workflow modules with `workflow.unsafe.imports_passed_through()` so they're not sandbox-validated.
- Or, if unit-testing workers are never meant to be sandboxed, have `--is-unit-testing` imply the unsandboxed runner (and say so).

## Repro

```bash
# sandbox ENABLED (default) → fails on a test workflow
.venv/bin/python -m pipelex.temporal.worker_cli --task-queue temporal_task_queue --is-unit-testing 2>&1 | grep -E "RestrictedWorkflowAccessError|Failed validating workflow"

# sandbox DISABLED → confirmed: gets past validation, boots, and polls (kill via timeout)
timeout 25 .venv/bin/python -m pipelex.temporal.worker_cli --task-queue temporal_task_queue --is-unit-testing --is-not-sandboxed 2>&1 | grep -E "Temporal Worker started|Failed validating workflow"
# observed: no "Failed validating workflow"; exits rc=124 from the timeout (worker was polling)
```
