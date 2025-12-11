# Pipelex CLI Documentation

The Pipelex CLI provides a command-line interface for managing and interacting with your Pipelex projects. This document outlines all available commands and their usage.

## Overview

The Pipelex CLI is organized into several command groups:

| Command | Description |
|---------|-------------|
| [**init**](init.md) | Initialize Pipelex configuration |
| [**validate**](validate.md) | Validate configuration and pipelines |
| [**show**](show.md) | Inspect configuration, pipes, and AI models |
| [**run**](run.md) | Execute pipelines |
| [**build**](build/index.md) | Generate pipelines, runners, and structures |
| [**kit**](kit.md) | Manage agent rules and migration instructions |

## Usage Tips

1. **Initial Setup**

    - Run `pipelex init` to create configuration files and select your backends
    - Configure your AI providers in `.pipelex/inference/backends.toml`
    - Install agent rules with `pipelex kit rules` if using AI assistants

2. **Development Workflow**

    - Write or generate pipelines in `.plx` files
    - Validate with `pipelex validate your_pipe_code` or `pipelex validate your_bundle.plx` during development
    - Run `pipelex validate all` before committing changes

3. **Running Pipelines**

    - Use `pipelex show pipes` to see available pipes
    - Use `pipelex show pipe pipe_code` to inspect pipe details
    - Run with `pipelex run pipe_code`, add the required inputs using `--inputs`

4. **Configuration Management**

    - Use `pipelex show config` to verify current settings
    - Use `pipelex show backends` to check inference backend setup
    - Use `pipelex show models backend_name` to see available models

## Related Documentation

- [Build Pipe](build/pipe.md) - Generate pipelines from natural language
- [Kit Commands](kit.md) - Agent rules and migration management
- [Configure AI Providers](../../5-setup/configure-ai-providers.md) - Set up LLM backends
- [Design and Run Pipelines](../../6-build-reliable-ai-workflows/pipes/index.md) - Pipeline development guide

