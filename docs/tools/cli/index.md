---
title: "CLI Reference"
description: "Master the `pipelex` runtime CLI and understand where the `mthds` CLI fits for package manifest management."
---

# Pipelex CLI Documentation

The `pipelex` CLI is the runtime and project-configuration CLI for Pipelex. Use it to initialize config, validate methods, run pipes, inspect the runtime state, and generate supporting files.

## Overview

The Pipelex CLI is organized into several command groups:

| Command | Description |
|---------|-------------|
| [**init**](init.md) | Initialize Pipelex configuration |
| [**validate**](validate.md) | Validate configuration and pipelines |
| [**show**](show.md) | Inspect configuration, pipes, and AI models |
| [**run**](run.md) | Execute pipelines |
| [**build**](build/index.md) | Generate pipelines, runners, and structures |

## Related CLI Surface

Package manifest management currently lives in the `mthds` CLI:

- [**package**](pkg.md) — `mthds package init`, `mthds package list`, and `mthds package validate`

## Usage Tips

1. **Initial Setup**

    - Run `pipelex init` to create configuration files and select your backends
    - Configure your AI providers in `.pipelex/inference/backends.toml`

2. **Development Workflow**

    - Write or generate pipelines in `.mthds` files
    - Validate with `pipelex validate pipe your_pipe_code` or `pipelex validate bundle your_bundle.mthds` during development
    - Run `pipelex validate pipe --all` before committing changes

3. **Running Pipelines**

    - Use `pipelex show pipe --all` to see available pipes
    - Use `pipelex show pipe pipe_code` to inspect pipe details
    - Run with `pipelex run pipe pipe_code`, add the required inputs using `--inputs`

4. **Configuration Management**

    - Use `pipelex show config` to verify current settings
    - Use `pipelex show backends` to check inference backend setup
    - Use `pipelex show models backend_name` to see available models

## Related Documentation

- [Configure AI Providers](../../get-started/configure-ai-providers.md) - Set up LLM backends
- [Design and Run Pipelines](../../building-methods/pipes/index.md) - Pipeline development guide
- [Packages](../../building-methods/packages.md) - `METHODS.toml` manifests and exports

