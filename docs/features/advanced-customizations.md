---
title: Advanced Customizations
description: "Customize Pipelex with dependency injection — plug in your own secrets, storage, reporting, and content generation providers without modifying the framework."
---

# Advanced Customizations

A dependency injection framework for extending and customizing Pipelex behavior.

## Overview

Pipelex provides well-defined injection points that let you replace or extend core behaviors without modifying the framework itself. Each injection point follows a strict protocol contract, making implementations testable and swappable. Register custom providers at initialization time and the runtime uses them throughout execution.

## Injection Points

| Injection Point | Purpose |
|-----------------|---------|
| **[Secrets Provider](../advanced/secrets-provider-injection.md)** | Custom secret management (environment, vaults, etc.) |
| **[Storage Provider](../advanced/storage-provider-injection.md)** | Custom cloud storage backends |
| **[Observer](../advanced/observer-provider-injection.md)** | Custom execution data capture |
| **[Reporting Delegate](../advanced/reporting-delegate-injection.md)** | Custom cost reporting |
| **[Content Generator](../advanced/content-generator-injection.md)** | Override LLM output generation |
| **[Pipe Router](../advanced/pipe-router-injection.md)** | Dynamic routing of pipes to implementations |

## Built-in Defaults

Some injection points provide safe built-in defaults or no-op implementations, so you only need to implement the ones relevant to your use case.

For detailed documentation, see [Advanced Customizations](../advanced/index.md).
