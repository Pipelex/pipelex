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
from typing import Any, Dict, Protocol

PayloadType = Dict[str, Any]

class ObserverProtocol(Protocol):
    async def before_run(self, payload: PayloadType) -> None:
        """Process and store the payload before the run"""
        ...

    async def successful_run(self, payload: PayloadType) -> None:
        """Process and store the payload after the run is successful"""
        ...

    async def failing_run(self, payload: PayloadType) -> None:
        """Process and store the payload after the run fails"""
        ...
```

## Payload Structure

The payload contains different information depending on the execution phase:

### Before Run
```python
payload = {
    "pipe_job": PipeJob,  # Contains pipe metadata and working memory
}
```

### Successful Run
```python
payload = {
    "pipe_job": PipeJob,     # Initial job information
    "pipe_output": PipeOutput, # Results and final working memory
}
```

### Failing Run
```python
payload = {
    "pipe_job": PipeJob,  # Initial job information
    # Note: error details are handled separately by the pipe router
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

    async def before_run(self, payload: PayloadType) -> None:
        pipe_job = payload["pipe_job"]
        # Process pipe_job data before execution
        # Example: Log pipe code, inputs, parameters
        print(f"Starting pipe: {pipe_job.pipe_code}")

    async def successful_run(self, payload: PayloadType) -> None:
        pipe_job = payload["pipe_job"]
        pipe_output = payload["pipe_output"]
        # Process successful execution data
        # Example: Log execution time, output size, tokens used
        print(f"Completed pipe: {pipe_job.pipe_code}")

    async def failing_run(self, payload: PayloadType) -> None:
        pipe_job = payload["pipe_job"]
        # Process failure data
        # Example: Log error context, partial results
        print(f"Failed pipe: {pipe_job.pipe_code}")
```

### Step 2: Register Your Observer with Dependency Injection

The observer is injected through the PipelexHub dependency injection system:

```python
from pipelex.hub import get_pipelex_hub

# Create your observer instance
my_observer = MyCustomObserver(config_param="production")

# Inject it into the hub
hub = get_pipelex_hub()
hub.set_observer_provider(my_observer)
```

### Step 3: Ensure Proper Integration

The observer is automatically called by the PipeRouterProtocol during pipe execution:

1. `before_run()` is called before any pipe execution
2. `successful_run()` is called after successful completion
3. `failing_run()` is called when an exception occurs

## Built-in LocalObserver Example

Pipelex includes a `LocalObserver` that writes data to JSONL files:

```python
from pipelex.observer.local_observer import LocalObserver

# Uses default observer directory from config
local_observer = LocalObserver()

# Or specify custom directory
local_observer = LocalObserver(storage_dir="/path/to/custom/dir")

# Inject the observer
get_pipelex_hub().set_observer_provider(local_observer)
```

The LocalObserver creates separate JSONL files for each event type:
- `before_run.jsonl` - Pre-execution data
- `successful_run.jsonl` - Success events
- `failing_run.jsonl` - Failure events

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

    async def before_run(self, payload: PayloadType) -> None:
        # Store in database
        await self._store_event("before_run", payload)

    async def successful_run(self, payload: PayloadType) -> None:
        await self._store_event("successful_run", payload)

    async def failing_run(self, payload: PayloadType) -> None:
        await self._store_event("failing_run", payload)

    async def _store_event(self, event_type: str, payload: PayloadType):
        # Your database storage logic here
        pass
```

### Metrics Observer
```python
class MetricsObserver(ObserverProtocol):
    def __init__(self, metrics_client):
        self.metrics = metrics_client

    async def before_run(self, payload: PayloadType) -> None:
        pipe_job = payload["pipe_job"]
        self.metrics.increment(f"pipe.{pipe_job.pipe_code}.started")

    async def successful_run(self, payload: PayloadType) -> None:
        pipe_job = payload["pipe_job"]
        self.metrics.increment(f"pipe.{pipe_job.pipe_code}.success")

    async def failing_run(self, payload: PayloadType) -> None:
        pipe_job = payload["pipe_job"]
        self.metrics.increment(f"pipe.{pipe_job.pipe_code}.failed")
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
from pipelex import Pipelex
from my_project.observers import MyCustomObserver

def setup_pipelex():
    # Initialize Pipelex
    pipelex_instance = Pipelex.make()

    # Setup custom observer
    observer = MyCustomObserver()
    get_pipelex_hub().set_observer_provider(observer)

    return pipelex_instance
```

The observer system provides powerful insights into your pipeline execution patterns and is essential for monitoring, debugging, and optimizing your Pipelex workflows.