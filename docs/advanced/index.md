---
description: "Extend Pipelex through dependency injection — swap in custom secrets providers, storage backends, observers, and reporting delegates."
---

# Dependency Injection

## Overview

Pipelex uses dependency injection to manage service dependencies and make components more modular and testable. The system allows you to customize and extend Pipelex's functionality by injecting your own implementations of various services.

## Injection Methods

There are two main ways to inject custom implementations:

### 1. During Initialization

```python
from pipelex import Pipelex

pipelex = Pipelex.make(
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
hub.set_report_delegate(MyReportingDelegate())
# ... and so on for other components
```

## Protocol Compliance

All custom implementations MUST:

1. Implement ALL methods defined in their respective protocols
2. Match the exact method signatures (parameter names and types)
3. Follow the protocol's documented behavior
4. Handle errors appropriately
5. Clean up resources when needed

## Available Injectable Components

Pipelex supports injection of the following components:

**Reporting Delegate** (`ReportingManager`)

- Protocol: `ReportingProtocol`
- Default: `ReportingManager`
- No-op option: inject `ReportingNoOp` to disable reporting explicitly
- [Details](reporting-delegate-injection.md)

**Secrets Provider** (`EnvSecretsProvider`)

- Protocol: `SecretsProviderAbstract`
- Default: `EnvSecretsProvider`
- [Details](secrets-provider-injection.md)

**Content Generator** (`ContentGenerator`)

- Protocol: `ContentGeneratorProtocol`
- Default: `ContentGenerator`
- [Details](content-generator-injection.md)

**Pipe Router** (`PipeRouter`)

- Protocol: `PipeRouterProtocol`
- Default: `PipeRouter`
- [Details](pipe-router-injection.md)
