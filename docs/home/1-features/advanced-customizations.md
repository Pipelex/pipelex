---
title: Advanced Customizations
---

# Advanced Customizations

A dependency injection framework for extending and customizing Pipelex behavior.

## Overview

Pipelex provides well-defined injection points that let you replace or extend core behaviors without modifying the framework itself. Each injection point follows a strict protocol contract, making implementations testable and swappable. Register custom providers at initialization time and the runtime uses them throughout execution.

## Injection Points

| Injection Point | Purpose |
|-----------------|---------|
| **[Secrets Provider](../10-advanced-customizations/secrets-provider-injection.md)** | Custom secret management (environment, vaults, etc.) |
| **[Storage Provider](../10-advanced-customizations/storage-provider-injection.md)** | Custom cloud storage backends |
| **[Observer](../10-advanced-customizations/observer-provider-injection.md)** | Custom execution data capture |
| **[Reporting Delegate](../10-advanced-customizations/reporting-delegate-injection.md)** | Custom cost reporting |
| **[Content Generator](../10-advanced-customizations/content-generator-injection.md)** | Override LLM output generation |
| **[Pipe Router](../10-advanced-customizations/pipe-router-injection.md)** | Dynamic routing of pipes to implementations |

## NoOp Defaults

Each injection point has a safe no-op default, so features gracefully degrade when no custom implementation is provided. You only need to implement the injection points relevant to your use case.

For detailed documentation, see [Advanced Customizations](../10-advanced-customizations/index.md).
