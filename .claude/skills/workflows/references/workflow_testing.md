# Workflow Registration Testing

Ensure all workflow classes are properly registered in workers to prevent production errors.

## Overview

A common production issue is creating a new workflow class but forgetting to register it in the worker. 

## Test All Decorated Classes Are Registered

The most comprehensive test - scans the codebase for all `@workflow.define` decorators:

```python
import ast
from pathlib import Path

from pytest_mock import MockerFixture

from core.workflows.worker import get_workflows

# Root directory for scanning
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


def _find_workflow_decorated_classes() -> dict[str, str]:
    """Scan codebase for all classes decorated with @workflows.workflow.define.

    Returns:
        Dict mapping class names to their file paths.
    """
    decorated_classes: dict[str, str] = {}

    # Directories containing workflow definitions
    scan_dirs = [
        PROJECT_ROOT / "core",
        PROJECT_ROOT / "plugins",
        PROJECT_ROOT / "workflows",
    ]

    def is_workflow_decorator(node: ast.expr) -> bool:
        """Check if decorator matches @workflows.workflow.define pattern."""
        # Handle @workflows.workflow.define(...)
        if isinstance(node, ast.Call):
            node = node.func

        # Matches `import mistralai.workflows as workflows` → workflows.workflow.define
        if isinstance(node, ast.Attribute) and node.attr == "define":
            if isinstance(node.value, ast.Attribute) and node.value.attr == "workflow":
                if isinstance(node.value.value, ast.Name):
                    return node.value.value.id == "workflows"
        return False

    def scan_file(file_path: Path) -> None:
        """Parse a Python file and extract workflow-decorated class names."""
        try:
            source = file_path.read_text()
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for decorator in node.decorator_list:
                    if is_workflow_decorator(decorator):
                        relative_path = str(file_path.relative_to(PROJECT_ROOT))
                        decorated_classes[node.name] = relative_path
                        break

    for scan_path in scan_dirs:
        if scan_path.is_file():
            scan_file(scan_path)
        elif scan_path.is_dir():
            for py_file in scan_path.rglob("*.py"):
                # Skip test files
                if "/tests/" in str(py_file) or py_file.name.startswith("test_"):
                    continue
                scan_file(py_file)

    return decorated_classes


def test_all_workflow_decorated_classes_are_registered(mocker: MockerFixture) -> None:
    """Ensure all @workflow.define classes are registered in get_workflows().

    This prevents the common error where a workflow is created but not
    added to the worker registration.
    """
    # Get workflows for dev mode
    dev_workflows = get_workflows(dev_only=True)

    # Get dev environment workflows
    mocker.patch("core.workflows.worker.settings.environment", "dev")
    dev_env_workflows = get_workflows(dev_only=False)

    # Get production environment workflows
    mocker.patch("core.workflows.worker.settings.environment", "production")
    prod_env_workflows = get_workflows(dev_only=False)

    # Combine all registered workflows
    registered_workflows = set(dev_workflows + dev_env_workflows + prod_env_workflows)
    registered_names = {cls.__name__ for cls in registered_workflows}

    # Find all decorated classes in codebase
    decorated_classes = _find_workflow_decorated_classes()

    # Check for missing registrations
    missing = {
        name: path
        for name, path in decorated_classes.items()
        if name not in registered_names
    }

    if missing:
        missing_details = "\n".join(
            f"  - {name} (defined in {path})"
            for name, path in sorted(missing.items())
        )
        raise AssertionError(
            f"The following workflow classes are decorated with @workflow.define "
            f"but are NOT registered in get_workflows():\n{missing_details}\n\n"
            f"Please add them to core/workflows/worker.py"
        )
```

## Unit Testing with `create_test_worker`

The SDK provides `create_test_worker` in `mistralai.workflows.testing` for running workflows against an in-memory Temporal environment. It handles DI scoping, sandbox setup, and pre-registers event-emitting activities.

### Fixtures

Import the SDK fixtures in your `conftest.py`:

```python
# conftest.py
from mistralai.workflows.testing.fixtures import *  # noqa: F401,F403
```

This provides `temporal_env` (in-memory Temporal with time-skipping) and auto-use fixtures for test config, DI cache clearing, and search attribute mocking.

### Example

```python
from mistralai.workflows.testing import create_test_worker

async def test_my_workflow(temporal_env):
    async with create_test_worker(temporal_env, [MyWorkflow], [my_activity]) as worker:
        handle = await temporal_env.client.start_workflow(
            "my-workflow",
            {"input_field": "value"},
            id="test-id",
            task_queue="test-task-queue",
        )
        result = await handle.result()
        assert result == {"output_field": "expected"}
```

## CI Integration

Add to your CI pipeline:

```yaml
# .github/workflows/test.yml
- name: Run workflow registration tests
  run: pytest tests/core/workflows/test_worker.py -v
```

## Best Practices

1. **Run tests in CI**: Catch missing registrations before deployment
2. **Test all environments**: Both dev and production workflow lists
3. **Skip test files**: Don't flag test workflow classes as missing
4. **Clear error messages**: Include file paths to help locate unregistered classes
6. **Mock environment settings**: Test both dev and production code paths
