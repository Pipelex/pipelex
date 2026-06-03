# Pipeline/Sequential Steps Pattern

Build multi-step workflows with declarative step definitions, conditional execution, and configurable error handling.

## Overview

The pipeline pattern provides a structured way to:
- Define ordered sequences of workflow steps
- Execute steps as child workflows with deterministic IDs
- Handle errors per-step (raise, skip, or stop)
- Conditionally skip steps based on runtime context

This pattern can be very useful to define a core workflow that can be extended by different variants.

## Core Components

### StepSpec

Declarative definition of a pipeline step:

```python
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, Type
from pydantic import BaseModel

# Error handling policies
class OnError(Enum):
    RAISE = "raise"  # Re-raise exception (default)
    SKIP = "skip"    # Log warning and continue to next step
    STOP = "stop"    # Log warning and stop pipeline (no error raised)

# Context type for passing data between steps
Context = dict[str, Any]

# Factory function signature for creating step parameters
ParamsFactory = Callable[[Any, Context, str, str], BaseModel]

@dataclass(frozen=True)
class StepSpec:
    """Declarative definition of a step in the pipeline."""
    task: "RegisteredTask"
    when: Optional[Callable[[Context, Any], bool]] = None  # Conditional execution
    on_error: OnError = OnError.RAISE
```

### RegisteredTask

Links a task type to its workflow class and parameter factory:

```python
from enum import Enum

class TaskRegistry(Enum):
    """Registry of all available task types."""
    VALIDATE_INPUT = "VALIDATE_INPUT"
    PROCESS_DATA = "PROCESS_DATA"
    GENERATE_OUTPUT = "GENERATE_OUTPUT"
    SEND_NOTIFICATION = "SEND_NOTIFICATION"

@dataclass(frozen=True)
class RegisteredTask:
    task_type: TaskRegistry
    workflow_cls: Type  # Abraxas workflow class
    make_params: ParamsFactory  # Creates Pydantic params from context
```

### Task Registry

Central mapping of task types to their implementations:

```python
BASE_TASKS = {
    TaskRegistry.VALIDATE_INPUT: RegisteredTask(
        task_type=TaskRegistry.VALIDATE_INPUT,
        workflow_cls=ValidateInputTask,
        make_params=lambda data, ctx, exec_id, process_type: ValidateParams(
            data=data,
            rules=ctx["validation_rules"],
        ),
    ),
    TaskRegistry.PROCESS_DATA: RegisteredTask(
        task_type=TaskRegistry.PROCESS_DATA,
        workflow_cls=ProcessDataTask,
        make_params=lambda data, ctx, exec_id, process_type: ProcessParams(
            data=data,
            config=ctx["processing_config"],
        ),
    ),
}
```

## Pipeline Implementation

### Base Pipeline Class

```python
import logging
from typing import Any, ClassVar, Generic, TypeVar

import mistralai.workflows as workflows

from .process_utils import Context, OnError, RegisteredTask, StepSpec
from .utils import get_child_workflow_execution_id

logger = logging.getLogger(__name__)
T = TypeVar("T")

class CoreProcess(Generic[T]):
    """Base class for declarative pipelines."""

    STEPS: ClassVar[list[StepSpec]] = []
    PROCESS_TYPE: str = "default"

    def __init__(self) -> None:
        self.steps = self.STEPS
        self.process_type = self.PROCESS_TYPE

    async def run_pipeline(self, input_object: T, ctx: Context, case_id: str) -> T:
        """Execute all steps in sequence."""
        for step in self.steps:
            step_label = step.task.task_type.name.lower()

            # Conditional execution
            if step.when and not step.when(ctx, input_object):
                logger.info(f"Skipping step {step_label}")
                continue

            reg: RegisteredTask = step.task
            execution_id = get_child_workflow_execution_id(task_name=step_label, case_id=case_id)

            logger.info(f"Running step {step_label} ...")

            try:
                params = reg.make_params(input_object, ctx, execution_id, self.process_type)
                input_object = await workflows.workflow.execute_workflow(
                    reg.workflow_cls, params, execution_id=execution_id
                )
                logger.info(f"Step {step_label} OK")

            except Exception as exc:
                logger.exception(f"Step {step_label} failed: {exc}")

                if step.on_error is OnError.RAISE:
                    raise
                if step.on_error is OnError.STOP:
                    logger.warning(f"Stopping pipeline after '{step_label}'")
                    break
                if step.on_error is OnError.SKIP:
                    logger.warning(f"Skipping failed step '{step_label}'")
                    continue

        return input_object
```

### Concrete Pipeline Definition

```python
from typing import ClassVar

class DataProcessingPipeline(CoreProcess[ProcessedData]):
    """Pipeline for processing incoming data."""

    STEPS: ClassVar[list[StepSpec]] = [
        StepSpec(task=BASE_TASKS[TaskRegistry.VALIDATE_INPUT]),
        StepSpec(task=BASE_TASKS[TaskRegistry.PROCESS_DATA], on_error=OnError.SKIP),
        StepSpec(
            task=BASE_TASKS[TaskRegistry.SEND_NOTIFICATION],
            when=lambda ctx, data: ctx.get("notify_on_complete", False),
        ),
    ]

    PROCESS_TYPE = "data_processing"

    def __init__(self, initial_data: InputData, config: Config) -> None:
        super().__init__()
        self.initial_data = initial_data
        self.config = config

    async def run(self) -> ProcessedData:
        ctx = {
            "validation_rules": self.config.rules,
            "processing_config": self.config.processing,
            "notify_on_complete": self.config.notifications_enabled,
        }
        return await self.run_pipeline(
            input_object=self.initial_data, ctx=ctx, case_id=self.initial_data.id
        )
```

## Usage Patterns

### Conditional Step Execution

```python
StepSpec(
    task=BASE_TASKS[TaskRegistry.SEND_NOTIFICATION],
    when=lambda ctx, data: data.requires_notification and ctx.get("notifications_enabled"),
)
```

### Error Handling Strategies

```python
# Fail fast (default) - pipeline stops on first error
StepSpec(task=..., on_error=OnError.RAISE)

# Skip failed steps - continue with remaining steps
StepSpec(task=..., on_error=OnError.SKIP)

# Stop gracefully - no error raised, but pipeline ends
StepSpec(task=..., on_error=OnError.STOP)
```

### Extending Pipelines for Variants

```python
class FrenchDataPipeline(DataProcessingPipeline):
    """French-specific pipeline with additional steps."""

    STEPS: ClassVar[list[StepSpec]] = [
        *DataProcessingPipeline.STEPS,
        StepSpec(task=FRENCH_TASKS[TaskRegistry.FRENCH_VALIDATION]),
    ]

    PROCESS_TYPE = "french_data_processing"
```

## Best Practices

1. **Keep steps focused**: Each step should do one thing well
2. **Use context for shared data**: Pass data between steps via the context dict
3. **Choose error policies carefully**: Use SKIP for optional steps, RAISE for critical ones
4. **Use conditional execution**: Avoid empty/no-op workflow executions
5. **Log step transitions**: Makes debugging pipeline failures easier
6. **Generate deterministic execution IDs**: Enables idempotency and replay
