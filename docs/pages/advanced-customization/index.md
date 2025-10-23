# Dependency Injection

## Overview

Pipelex uses dependency injection to manage service dependencies and make components more modular and testable. The system allows you to customize and extend Pipelex's functionality by injecting your own implementations of various services.

## Injection Methods

There are two main ways to inject custom implementations:

### 1. During Initialization

```python
from pipelex import Pipelex

pipelex = Pipelex.make(
    template_provider=MyTemplateProvider(),
    pipeline_tracker=MyPipelineTracker(),
    activity_manager=MyActivityManager(),
    reporting_delegate=MyReportingDelegate(),
    secrets_provider=MySecretsProvider(),
    content_generator=MyContentGenerator(),
    pipe_router=MyPipeRouter()
)
```

### 2. Through the Hub

```python
from pipelex.hub import PipelexHub

hub = PipelexHub()
hub.set_template_provider(MyTemplateProvider())
# ... and so on for other components
```

## NoOp Implementations

Some components have "NoOp" (No Operation) implementations that are used when the feature is disabled:

- `ReportingNoOp`: Used when reporting is disabled
- `PipelineTrackerNoOp`: Used when pipeline tracking is disabled
- `ActivityManagerNoOp`: Used when activity tracking is disabled

These NoOp implementations implement the same protocol but do nothing, allowing the system to function without the specific feature.

## Protocol Compliance

All custom implementations MUST:

1. Implement ALL methods defined in their respective protocols
2. Match the exact method signatures (parameter names and types)
3. Follow the protocol's documented behavior
4. Handle errors appropriately
5. Clean up resources when needed

## Feature Flags

Some components are controlled by feature flags in the configuration:

- `is_reporting_enabled`: Controls Reporting system
- `is_pipeline_tracking_enabled`: Controls Pipeline Tracking

When a feature is disabled, the corresponding NoOp implementation is used automatically.

## Available Injectable Components

Pipelex supports injection of the following components:

1. **Template Provider** (`TemplateLibrary`)

    - Protocol: `TemplateProviderAbstract`
    - Default: `TemplateLibrary`
    - [Details](template-provider-injection.md)

2. **Reporting Delegate** (`ReportingManager`)

    - Protocol: `ReportingProtocol`
    - Default: `ReportingManager` or `ReportingNoOp` if disabled
    - [Details](reporting-delegate-injection.md)

3. **Pipeline Tracker** (`PipelineTracker`)

    - Protocol: `PipelineTrackerProtocol`
    - Default: `PipelineTracker` or `PipelineTrackerNoOp` if disabled
    - [Details](pipeline-tracker-injection.md)

4. **Activity Manager** (`ActivityManager`)

    - Protocol: `ActivityManagerProtocol`
    - Default: `ActivityManager` or `ActivityManagerNoOp` if disabled
    - [Details](activity-manager-injection.md)

5. **Secrets Provider** (`EnvSecretsProvider`)

    - Protocol: `SecretsProviderAbstract`
    - Default: `EnvSecretsProvider`
    - [Details](secrets-provider-injection.md)

6. **Content Generator** (`ContentGenerator`)

    - Protocol: `ContentGeneratorProtocol`
    - Default: `ContentGenerator`
    - [Details](content-generator-injection.md)

7. **Pipe Router** (`PipeRouter`)

    - Protocol: `PipeRouterProtocol`
    - Default: `PipeRouter`
    - [Details](pipe-router-injection.md)

