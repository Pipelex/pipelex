# Observer Provider Injection

The Observer system in Pipelex allows you to monitor and collect data about pipe executions. This guide explains how to implement your own observer by following the dependency injection pattern and the ObserverProtocol.

## Overview

The Observer system is designed to collect execution data at three key moments:

- **Before running a pipe**: Capture initial state and inputs
- **After successful execution**: Record outputs and success metrics
- **After failed execution**: Log errors and failure context

This data collection is designed for later analysis and is still a work in progress.

## Observer Protocol

All observers must implement the `ObserverProtocol`:

```python
from typing import Any, Protocol

PayloadType = dict[str, Any]

class ObserverProtocol(Protocol):
    async def observe_before_run(self, payload: PayloadType) -> None:
        """Process and store the payload before the run"""
        ...

    async def observe_after_successful_run(self, payload: PayloadType) -> None:
        """Process and store the payload after the run is successful"""
        ...

    async def observe_after_failing_run(self, payload: PayloadType) -> None:
        """Process and store the payload after the run fails"""
        ...
```

## Payload Structure

The payload contains different information depending on the execution phase:

### Before Run
```python
payload = {
    "pipeline_run_id": str,  # Identifier of the pipeline run
    "pipe_job": PipeJob,  # Contains pipe metadata and working memory
}
```

### Successful Run
```python
payload = {
    "pipeline_run_id": str,  # Identifier of the pipeline run
    "pipe_job": PipeJob,     # Initial job information
    "pipe_output": PipeOutput, # Results and final working memory
}
```

### Failing Run
```python
payload = {
    "pipeline_run_id": str,  # Identifier of the pipeline run
    "pipe_job": PipeJob,  # Initial job information
    "error": Exception,   # The exception that caused the failure
}
```

## Implementing a Custom Observer

### Step 1: Create Your Observer Class

```python
import os
from typing import Optional
from pipelex.observer.observer_protocol import ObserverProtocol, PayloadType

class MyCustomObserver(ObserverProtocol):
    def __init__(self, config_param: str = "default_value"):
        self.config_param = config_param
        # Initialize your storage/logging mechanism here

    async def observe_before_run(self, payload: PayloadType) -> None:
        pipe_job = payload["pipe_job"]
        # Process pipe_job data before execution
        # Example: Log pipe code, inputs, parameters
        print(f"Starting pipe: {pipe_job.pipe.code}")

    async def observe_after_successful_run(self, payload: PayloadType) -> None:
        pipe_job = payload["pipe_job"]
        pipe_output = payload["pipe_output"]
        # Process successful execution data
        # Example: Log execution time, output size, tokens used
        print(f"Completed pipe: {pipe_job.pipe.code}")

    async def observe_after_failing_run(self, payload: PayloadType) -> None:
        pipe_job = payload["pipe_job"]
        # Process failure data
        # Example: Log error context, partial results
        print(f"Failed pipe: {pipe_job.pipe.code}")
```

### Step 2: Register Your Observer at Boot

Observers are injected at boot, through `Pipelex.make()`. Pass a dict keyed by a name of your choosing — Pipelex wraps the whole dict in a `MultiObserver` and hands it to the pipe router, so every observer you register is notified:

```python
from pipelex.pipelex import Pipelex

# Create your observer instance
my_observer = MyCustomObserver(config_param="production")

# Inject it at boot
Pipelex.make(observers={"my_observer": my_observer})
```

!!! warning "Observers must be registered at boot"
    Passing `observers` to `Pipelex.make()` is the only way to register one. The router receives its observer when it is constructed during setup, so there is no supported way to swap an observer on a already-running instance.

Registering your own `observers` dict **replaces** the defaults (a no-op observer and the telemetry observer). Include the built-ins explicitly if you want to keep them alongside your own.

### Step 3: Ensure Proper Integration

The observer is automatically called by the PipeRouterProtocol during pipe execution:

1. `observe_before_run()` is called before any pipe execution
2. `observe_after_successful_run()` is called after successful completion
3. `observe_after_failing_run()` is called when an exception occurs

## Built-in LocalObserver Example

Pipelex includes a `LocalObserver` that writes data to JSONL files:

```python
from pipelex.observer.local_observer import LocalObserver

# Uses default observer directory from config
local_observer = LocalObserver()

# Or specify custom directory
local_observer = LocalObserver(storage_dir="/path/to/custom/dir")

# Inject the observer
Pipelex.make(observers={"local": local_observer})
```

The LocalObserver creates separate JSONL files for each event type:

- `before_run.jsonl` - Pre-execution data
- `after_successful_run.jsonl` - Success events
- `after_failing_run.jsonl` - Failure events

## Advanced Use Cases

### Database Observer
```python
import asyncio
import aiohttp
from pipelex.observer.observer_protocol import ObserverProtocol, PayloadType

class DatabaseObserver(ObserverProtocol):
    def __init__(self, db_connection_string: str):
        self.db_connection = db_connection_string
        # Initialize database connection

    async def observe_before_run(self, payload: PayloadType) -> None:
        # Store in database
        await self._store_event("before_run", payload)

    async def observe_after_successful_run(self, payload: PayloadType) -> None:
        await self._store_event("after_successful_run", payload)

    async def observe_after_failing_run(self, payload: PayloadType) -> None:
        await self._store_event("after_failing_run", payload)

    async def _store_event(self, event_type: str, payload: PayloadType):
        # Your database storage logic here
        pass
```

### Metrics Observer
```python
class MetricsObserver(ObserverProtocol):
    def __init__(self, metrics_client):
        self.metrics = metrics_client

    async def observe_before_run(self, payload: PayloadType) -> None:
        pipe_job = payload["pipe_job"]
        self.metrics.increment(f"pipe.{pipe_job.pipe.code}.started")

    async def observe_after_successful_run(self, payload: PayloadType) -> None:
        pipe_job = payload["pipe_job"]
        self.metrics.increment(f"pipe.{pipe_job.pipe.code}.success")

    async def observe_after_failing_run(self, payload: PayloadType) -> None:
        pipe_job = payload["pipe_job"]
        self.metrics.increment(f"pipe.{pipe_job.pipe.code}.failed")
```

## Best Practices

1. **Keep observers lightweight**: Avoid blocking operations in observer methods
2. **Handle errors gracefully**: Observer failures shouldn't break pipe execution
3. **Use async/await properly**: All observer methods are async
4. **Consider storage performance**: High-frequency pipes generate lots of data
5. **Structure your data**: Plan how you'll query and analyze the collected data later

## Integration with Pipelex Initialization

For automatic observer setup, integrate with your Pipelex initialization:

```python
from pipelex.pipelex import Pipelex

from my_project.observers import MyCustomObserver

def setup_pipelex():
    # Initialize Pipelex with the observer wired in from the start
    return Pipelex.make(observers={"my_observer": MyCustomObserver()})
```

The observer system provides powerful insights into your pipeline execution patterns and is essential for monitoring, debugging, and optimizing your Pipelex methods.