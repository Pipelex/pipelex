# Dependency Injection

## Overview

Pipelex uses dependency injection to manage service dependencies and make components more modular and testable. The system allows you to customize and extend Pipelex's functionality by injecting your own implementations of various services.

## Injecting your implementation

Inject at boot, by passing your implementation to `Pipelex.make()`:

```python
from pipelex.pipelex import Pipelex

pipelex = Pipelex.make(
    reporting_delegate=MyReportingDelegate(),
    secrets_provider=MySecretsProvider(),
    content_generator=MyContentGenerator(),
    pipe_router=MyPipeRouter()
)
```

This is the supported path. `Pipelex.make()` builds the hubs, applies your overrides in the right order, and wires the results into the components that consume them.

## Reading a dependency: the two hubs

Injection happens at boot; *lookup* happens through a hub. Pipelex has two, split by lifecycle:

- `pipelex.runtime_hub` — process-scoped infrastructure: config, console, secrets, storage, telemetry, the model deck, inference workers, the content generator, the plugin registries.
- `pipelex.interpreter_hub` — library-scoped method machinery: the library manager and the concept/domain/pipe libraries, the current-library binding, the pipe router, the pipeline manager.

Read a dependency through the module-level accessor for the half that owns it:

```python
from pipelex.interpreter_hub import get_required_pipe
from pipelex.runtime_hub import get_model_deck, get_secrets_provider

secrets = get_secrets_provider()
deck = get_model_deck()
pipe = get_required_pipe(pipe_code="my_domain.my_pipe")
```

!!! warning "Don't construct a hub yourself"
    Building a `RuntimeHub()` or `InterpreterHub()` by hand and calling setters on it has no effect on a running Pipelex — the instance you build is not the one the process resolves. Inject through `Pipelex.make()` instead.

Contributors adding a new dependency should read [Hub Layering](../contribute/hub-layering.md), which specifies which half a symbol belongs on and why the boundary is enforced.

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
