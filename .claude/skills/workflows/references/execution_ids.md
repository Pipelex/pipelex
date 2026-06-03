# Deterministic Child Workflow Execution IDs

Generate reproducible execution IDs for child workflows to enable idempotency and prevent duplicate executions.

## Overview

When executing child workflows, providing a deterministic execution ID ensures:
- **Idempotency**: Re-running the parent workflow won't create duplicate child executions
- **Traceability**: Easy to correlate parent and child workflows
- **Replay safety**: Workflow replays use the same execution IDs

## SDK Context

The SDK's `execute_workflow` accepts an optional `execution_id` parameter. When omitted:
- **Inside a workflow**: a random child workflow ID is generated
- **Outside a workflow (client calls)**: The SDK auto-generates a 64-char hex ID via `generate_two_part_id()` using uuid5

For child workflows where idempotency matters, always provide a deterministic `execution_id`.

## Implementation

```python
def get_child_workflow_execution_id(task_name: str, case_id: str) -> str:
    """Generate a deterministic execution ID for a child workflow.

    Args:
        task_name: Name/type of the task being executed
        case_id: Unique identifier for the case/entity being processed

    Returns:
        A deterministic, unique execution ID

    Example:
        >>> get_child_workflow_execution_id("validate-input", "case-123")
        "case-123-validate-input"
    """
    return f"{case_id}-{task_name}"
```

## Usage

### Basic Usage

```python
import mistralai.workflows as workflows
from .utils import get_child_workflow_execution_id

@workflows.workflow.define(name="parent-workflow")
class ParentWorkflow:

    @workflows.workflow.entrypoint
    async def run(self, params: ParentParams) -> Result:
        case_id = params.case_id

        # Execute child workflow with deterministic ID
        validation_result = await workflows.workflow.execute_workflow(
            ValidateInputWorkflow,
            ValidateParams(data=params.data),
            execution_id=get_child_workflow_execution_id(
                task_name="validate-input",
                case_id=case_id
            ),
        )

        # Another child workflow with fire-and-forget
        handle = await workflows.workflow.execute_workflow(
            ProcessDataWorkflow,
            ProcessParams(data=validation_result.data),
            execution_id=get_child_workflow_execution_id(
                task_name="process-data",
                case_id=case_id
            ),
            wait=False,  # returns ChildWorkflowHandle immediately
        )

        # Can await the handle later
        process_result = await handle

        return Result(output=process_result.output)
```

### In Pipeline Pattern

```python
async def run_task_queue(
    self,
    input_object: T,
    ctx: Context,
    steps: list[StepSpec],
    case_id: str
) -> T:
    for step in steps:
        step_label = step.task.task_type.name.lower()

        # Generate deterministic execution ID
        execution_id = get_child_workflow_execution_id(
            task_name=step_label,
            case_id=case_id
        )

        params = step.task.make_params(input_object, ctx, execution_id, self.process_type)

        input_object = await workflows.workflow.execute_workflow(
            step.task.workflow_cls,
            params,
            execution_id=execution_id
        )

    return input_object
```

## Extended Patterns

### Including Additional Context

For workflows that process items within a case:

```python
def get_child_workflow_execution_id(
    task_name: str,
    case_id: str,
    item_id: str | None = None
) -> str:
    """Generate execution ID with optional item-level granularity."""
    if item_id:
        return f"{case_id}-{task_name}-{item_id}"
    return f"{case_id}-{task_name}"
```

Usage:

```python
# Processing multiple items within a case
for item in items:
    await workflows.workflow.execute_workflow(
        ProcessItemWorkflow,
        ProcessItemParams(item=item),
        execution_id=get_child_workflow_execution_id(
            task_name="process-item",
            case_id=case_id,
            item_id=item.id,
        ),
    )
```

## `execute_workflow` Full Signature

For reference, the SDK's `execute_workflow` accepts:

```python
await workflows.workflow.execute_workflow(
    workflow=MyWorkflow,              # workflow class (decorated with @workflow.define)
    params=MyParams(...),             # Pydantic BaseModel
    execution_timeout=timedelta(hours=1),  # max runtime (default: 1h)
    execution_id="my-deterministic-id",    # optional; auto-generated if None
    wait=True,                        # True → await result; False → return ChildWorkflowHandle
    parent_close_policy=None,         # TERMINATE (wait=True) or ABANDON (wait=False) by default
)
```

## Why Deterministic IDs Matter

### Without Deterministic IDs

```python
# BAD: Random/missing execution IDs
await workflows.workflow.execute_workflow(
    ChildWorkflow,
    params,
    # No execution_id - system generates random one
)
```

Problems:
- Each replay creates new child workflow executions
- No way to correlate parent-child relationships
- Duplicate work if parent workflow is retried

### With Deterministic IDs

```python
# GOOD: Deterministic execution ID
await workflows.workflow.execute_workflow(
    ChildWorkflow,
    params,
    execution_id=get_child_workflow_execution_id("child-task", case_id),
)
```

Benefits:
- Replays reuse existing child executions
- Clear parent-child correlation in traces
- Safe retries without duplicate work

## Best Practices

1. **Always provide execution IDs** for child workflows
2. **Use consistent naming**: lowercase, hyphenated task names
3. **Include enough context**: case ID at minimum, item ID if processing collections
4. **Keep IDs readable**: they appear in logs and traces
5. **Don't include timestamps** unless you specifically want daily re-execution
6. **Use the same ID generation** across all child workflow calls in a parent
