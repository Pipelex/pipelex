# Testing Workflows

## Quick-test script

The fastest way to verify a workflow works end-to-end. No test files, no conftest, no pytest:

```bash
python .agents/skills/workflows/scripts/test_workflow.py src/workflows/my_workflow.py \
  --input '{"key": "value"}' \
  --timeout 30
```

For interactive workflows that use `wait_for_input()`, provide `--interactions`:

```bash
python .agents/skills/workflows/scripts/test_workflow.py src/workflows/my_workflow.py \
  --input '{}' \
  --interactions '[{"choice": "WFL"}]' \
  --timeout 60
```

The script:
1. Discovers the workflow class in the given file
2. Starts a real worker in-process via `run_worker(detach=True)` — worker logs stream to stderr
3. Waits for the workflow to be registered on the Workflows API
4. Executes the workflow via `WorkflowsClient`
5. For interactive workflows: polls `__get_pending_inputs` and submits each `--interactions` entry in order
6. Waits for completion, prints PASSED + result JSON, or FAILED + traceback
7. On timeout: terminates the execution via the API and shuts down the worker
8. Exit code 0/1 for CI integration

Options:
- `--input` (required): JSON input for the workflow
- `--timeout` (default 30): max seconds before the workflow is killed
- `--workflow-name`: select a specific workflow if the file contains multiple
- `--interactions`: JSON array of responses for interactive workflows

Because the script uses a real worker, you get full worker logs (activity errors, retries, HTTP failures) in real time on stderr. No time-skipping — activities execute with real network calls.

## Writing pytest tests

For more control (multiple assertions, signal/query testing, spot-checks against external APIs), write pytest tests using `create_test_worker`.

### Setup

**conftest.py:**
```python
from mistralai.workflows.testing.fixtures import (
    clear_dependency_cache,   # noqa: F401
    event_loop,               # noqa: F401
    mock_upsert_search_attributes,  # noqa: F401
    setup_test_config,        # noqa: F401
    temporal_env,             # noqa: F401
)
```

**pyproject.toml:**
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"

[dependency-groups]
dev = ["pytest-asyncio>=0.25.3"]
```

### Basic test pattern

```python
from datetime import timedelta
import asyncio
from mistralai.workflows.testing import create_test_worker

# Keep timeouts aggressive for a tight feedback loop.
# Increase only when the workflow is known to be long-running.
WORKFLOW_EXECUTION_TIMEOUT = timedelta(seconds=10)

async def test_my_workflow(self, temporal_env) -> None:
    async with create_test_worker(
        temporal_env,
        workflows=[MyWorkflow],
        activities=[my_activity],
    ):
        handle = await temporal_env.client.start_workflow(
            "my-workflow",
            {"key": "value"},
            id="test-my-workflow",
            task_queue="test-task-queue",
            execution_timeout=WORKFLOW_EXECUTION_TIMEOUT,
        )
        result = await asyncio.wait_for(handle.result(), timeout=15)
        assert result["key"] == "expected"
```

## Preventing hangs

Temporal retries failed workflow tasks indefinitely by default. If your workflow has a bug that crashes during task processing (not activity execution), the test will hang forever.

Two guards prevent this:

1. **`execution_timeout`** on `start_workflow()` — Temporal kills the workflow after this duration. The time-skipping test server fast-forwards retry delays, so the timeout triggers in ~1 real second.

2. **`asyncio.wait_for(handle.result(), timeout=N)`** — client-side fallback in case the execution timeout doesn't propagate cleanly.

Always use both.

## Common pitfalls

### `start_to_close_timeout` must be a `timedelta`

```python
# WRONG — causes infinite retry loop
@activity(start_to_close_timeout=60)

# RIGHT
@activity(start_to_close_timeout=timedelta(seconds=60))
```

### Sandbox blocks third-party imports (v3+)

Determinism enforcement is enabled by default in v3. If your workflow file imports a library like `httpx` at the top level, the sandbox will block it.

Fix: wrap non-deterministic imports with `workflow.unsafe.imports_passed_through()`:

```python
from mistralai.workflows import workflow

with workflow.unsafe.imports_passed_through():
    import httpx
```

Or disable enforcement per-workflow: `@workflow.define("name", enforce_determinism=False)`

### Search attribute errors in test env

The in-memory test environment doesn't have custom search attributes (e.g. `OtelTraceId`). The `mock_upsert_search_attributes` fixture from `mistralai.workflows.testing.fixtures` handles this. Make sure your conftest imports it.

### Results are dicts, not Pydantic models

Temporal returns raw dicts. Access fields directly: `result["message"]`, not `result.message`.

### Don't add `_emit_*` activities manually

`create_test_worker` already registers all workflow-lifecycle event activities. Adding them again causes duplicate-activity registration errors.
