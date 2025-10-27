# Observer Data Extraction

The Observer system in Pipelex automatically collects execution data from your pipes for later analysis. This data extraction feature is currently a work in progress but provides valuable insights into pipeline performance, usage patterns, and debugging information.

## Data Collection Points

The observer extracts data at three critical moments during pipe execution:

### 1. Before Pipe Execution
- **When**: Just before a pipe starts running
- **Data Collected**: Initial working memory state, pipe configuration, input parameters... [WIP]
- **Purpose**: Capture the starting conditions and context for analysis

### 2. After Successful Execution
- **When**: When a pipe completes successfully
- **Data Collected**: Final working memory, outputs, execution metadata, performance metrics... [WIP]
- **Purpose**: Track successful operations and measure performance

### 3. After Failed Execution
- **When**: When a pipe encounters an error or exception
- **Data Collected**: Error context, partial results, failure metadata... [WIP]
- **Purpose**: Debug issues and analyze failure patterns

## Where Data is Stored

The data extraction location depends on your observer implementation:

### LocalObserver (Default)

- **Location**: Local filesystem in JSONL format
- **Default Directory**: Configured in your Pipelex settings under `observer_config.observer_dir`
- **Files Created**:

- `before_run.jsonl` - Pre-execution snapshots
- `successful_run.jsonl` - Success events and results
- `failing_run.jsonl` - Failure events and error context

### Custom Observers
You can implement custom data extraction to:

- **Databases**: PostgreSQL, MongoDB, InfluxDB for structured analysis
- **Cloud Storage**: S3, GCS for large-scale data retention
- **Streaming Systems**: Kafka, Redis for real-time processing
- **Monitoring Tools**: DataDog, New Relic for operational insights

## Current Status: Work in Progress

See [Observer Provider Injection](../advanced-customization/observer-provider-injection.md) for implementation details.