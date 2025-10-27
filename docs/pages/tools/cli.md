# Pipelex CLI Documentation

The Pipelex CLI provides a command-line interface for managing and interacting with your Pipelex projects. This document outlines all available commands and their usage.

## Overview

The Pipelex CLI is organized into several command groups:

- **init** - Initialize Pipelex configuration
- **kit** - Manage agent rules and migration instructions (see [Kit Commands](kit.md))
- **build** - Generate pipelines from natural language (see [Pipe Builder](pipe-builder.md))
- **validate** - Validate configuration and pipelines
- **run** - Execute pipelines
- **show** - Inspect configuration, pipes, and AI models

## Init Commands

Initialize project configuration files in your project's `.pipelex` directory.

### Initialize Configuration

```bash
pipelex init config [OPTIONS]
```

Creates the `.pipelex` directory structure and copies default configuration files from the Pipelex package template.

**Options:**

- `--reset`, `-r` - Overwrite existing configuration files (use with caution)

**Examples:**

```bash
# Initialize configuration for the first time
pipelex init config

# Reinitialize configuration, overwriting existing files
pipelex init config --reset
```

**What gets initialized:**

This command creates the `.pipelex/` directory with:

- The main pipelex.toml configuration file for logging, reporting, tracking, etc.
- `inference/` - AI backend and routing configuration
- `deck/` - AI model aliases and presets

**Related Configuration:**

- [Configure AI Providers](../setup/configure-ai-providers.md)
- [Inference Backend Configuration](../configuration/config-technical/inference-backend-config.md)

## Validate Commands

Validate your pipeline definitions and configuration for correctness.

### Validate All Pipes

```bash
pipelex validate all
```

Performs comprehensive validation:

1. Validates all library configurations
2. Runs static validation on all discovered pipes
3. Performs dry-run execution to check pipeline logic

This is the recommended validation to run before committing changes or deploying pipelines.

**Examples:**

```bash
# Validate everything
pipelex validate all
```

### Validate Single Pipe

```bash
pipelex validate PIPE_CODE
pipelex validate --pipe PIPE_CODE
```

Validates and dry-runs a specific pipe from your imported packages, useful for iterative development.

**Arguments:**

- `PIPE_CODE` - The pipe code to validate as a positional argument, or use `--pipe` option

**Options:**

- `--pipe PIPE_CODE` - Explicitly specify the pipe code to validate (alternative to positional argument)

**Examples:**

```bash
# Validate a specific pipe (positional argument)
pipelex validate analyze_cv_matching
pipelex validate write_weekly_report

# Validate a specific pipe (explicit option)
pipelex validate --pipe analyze_cv_matching
```

### Validate Bundle

```bash
pipelex validate BUNDLE_FILE.plx
pipelex validate --bundle BUNDLE_FILE.plx
```

Validates all pipes defined in a bundle file. The command automatically detects `.plx` files as bundles.

**Arguments:**

- `BUNDLE_FILE.plx` - Path to the bundle file (auto-detected by `.plx` extension)

**Options:**

- `--bundle BUNDLE_FILE.plx` - Explicitly specify the bundle file path

**Examples:**

```bash
# Validate a bundle (auto-detected)
pipelex validate my_pipeline.plx
pipelex validate pipelines/invoice_processor.plx

# Validate a bundle (explicit option)
pipelex validate --bundle my_pipeline.plx
```

**Note:** When validating a bundle, ALL pipes in that bundle are validated, not just the main pipe.

### Validate Specific Pipe in Bundle

```bash
pipelex validate --bundle BUNDLE_FILE.plx --pipe PIPE_CODE
```

Validates all pipes in a bundle, while ensuring a specific pipe exists in that bundle. The entire bundle is validated, not just the specified pipe.

**Options:**

- `--bundle BUNDLE_FILE.plx` - Path to the bundle file
- `--pipe PIPE_CODE` - Pipe code that must exist in the bundle

**Examples:**

```bash
# Validate bundle and ensure specific pipe exists in it
pipelex validate --bundle my_pipeline.plx --pipe extract_invoice
pipelex validate --bundle invoice_processor.plx --pipe validate_amounts
```

!!! important "Bundle Validation Behavior"
    The specified pipe must be defined in the bundle. This is useful when you want to validate a bundle and confirm a specific pipe is present and valid within it. However, the entire bundle will be validated regardless.

### What Validation Checks

All validation commands check:

- Syntax correctness of `.plx` files
- Concept and pipe definitions are valid
- Input/output connections are correct
- All referenced pipes and concepts exist
- Dry-run execution succeeds without errors, which implies the logic is correct and the pipe can be run

**Related Configuration:**

- [Static Validation Configuration](../configuration/config-pipeline-validation/static-validation-config.md)
- [Dry Run Configuration](../configuration/config-pipeline-validation/dry-run-config.md)

## Show Commands

Inspect your Pipelex configuration, pipelines, and available AI models.

### Show Configuration

```bash
pipelex show config
```

Displays the current Pipelex configuration loaded from all sources (default config overriden by user config).

**Examples:**

```bash
# Display current configuration
pipelex show config
```

**Note:** This shows the main Pipelex configuration but not the inference backend details. Use `pipelex show backends` for backend configuration.

### List All Pipes

```bash
pipelex show pipes
```

Lists all pipes discovered in your project and imported packages, showing their pipe codes and basic information.

**Examples:**

```bash
# List all available pipes
pipelex show pipes
```

This includes:

- Internal Pipelex pipes (like the pipe builder)
- Pipes from your project's `.plx` files
- Pipes that are part of imported packages

### Show Pipe Definition

```bash
pipelex show pipe PIPE_CODE
```

Displays the complete definition of a specific pipe including inputs, outputs, prompts, model settings, and all configuration.

**Arguments:**

- `PIPE_CODE` - The pipe code to inspect

**Examples:**

```bash
# Show pipe definition
pipelex show pipe analyze_cv_matching
pipelex show pipe write_weekly_report
```

### List AI Models

```bash
pipelex show models BACKEND_NAME [OPTIONS]
```

Lists all available models from a configured backend provider by querying the provider's API.

**Arguments:**

- `BACKEND_NAME` - The backend to query (e.g., `openai`, `anthropic`, `mistral`)

**Options:**

- `--flat`, `-f` - Output in flat CSV format for easy copying into other configuration files

**Examples:**

```bash
# List models
pipelex show models openai
pipelex show models mistral

# List models in flat format
pipelex show models anthropic --flat
```

**Use case:** When configuring new models in your deck, use this command to see what models are available from each provider.

**Related Configuration:**

- [Inference Backend Configuration](../configuration/config-technical/inference-backend-config.md)

### Show Backends

```bash
pipelex show backends [OPTIONS]
```

Displays all configured inference backends and the active routing profile with its routing rules.

**Options:**

- `--all`, `-a` - Show all backends including disabled ones (by default, only enabled backends are shown)

**Examples:**

```bash
# Show enabled backends and routing profile
pipelex show backends

# Show all backends including disabled ones
pipelex show backends --all
```

**What it displays:**

- Table of configured backends with status, endpoint, and model count
- Active routing profile name and description
- Default backend for the profile
- Routing rules mapping model patterns to backends

**Related Configuration:**

- [Inference Backend Configuration](../configuration/config-technical/inference-backend-config.md)
- Backend configuration files: `.pipelex/inference/backends.toml`
- Routing configuration: `.pipelex/inference/routing_profiles.toml`

## Run Command

Execute a pipeline with optional inputs and outputs.

### Run a Pipeline

```bash
pipelex run [TARGET] [OPTIONS]
```

Executes a pipeline, either from a standalone bundle (.plx) file or from your project's pipe library.

**Arguments:**

- `TARGET` - Either a pipe code or a bundle file path, auto-detected according to presence of the .plx file extension

**Options:**

- `--pipe` - Pipe code to run (alternative to positional argument)
- `--bundle` - Bundle file path (alternative to positional argument)
- `--inputs`, `-i` - Path to JSON file containing inputs
- `--output`, `-o` - Path to save output JSON (defaults to `results/run_{pipe_code}.json`)
- `--no-output` - Skip saving output to file
- `--no-pretty-print` - Skip pretty printing the main output

**Examples:**

```bash
# Run a pipe by code
pipelex run hello_world

# Run with inputs from JSON file
pipelex run write_weekly_report --inputs weekly_report_data.json

# Run a bundle file (uses its main_pipe)
pipelex run my_bundle.plx

# Run a specific pipe from a bundle
pipelex run my_bundle.plx --pipe extract_invoice

# Run with explicit options
pipelex run --pipe hello_world --output my_output.json

# Run without saving or pretty printing
pipelex run my_pipe --no-output --no-pretty-print
```

**Input JSON Format:**

The input JSON file should contain a dictionary where keys are input variable names:

```json
{
  "input_variable": "simple string value",
  "another_input": {
    "concept": "domain.ConceptName",
    "content": { "field": "value" }
  }
}
```

**Output Format:**

The output JSON contains the complete working memory after pipeline execution, including all intermediate results and the final output.

**Related Documentation:**

- [Executing Pipelines with Inputs](../build-reliable-ai-workflows-with-pipelex/executing-pipelines-with-inputs.md)
- [Design and Run Pipelines](../build-reliable-ai-workflows-with-pipelex/design_and_run_pipelines.md)

## Build Commands

Generate pipelines and runner code from natural language descriptions. See the [Pipe Builder](pipe-builder.md) documentation for comprehensive details.

### Build Pipe

```bash
pipelex build pipe "PROMPT" [OPTIONS]
```

Generates a complete pipeline from a natural language prompt with automatic validation and error correction.

**Quick Example:**

```bash
pipelex build pipe "Analyze a CV and a Job offer and determine if they match" -o cv_matching_pipeline.plx
```

For complete documentation including all options and examples, see [Pipe Builder](pipe-builder.md).

### Build Runner

```bash
pipelex build runner [TARGET] [OPTIONS]
```

Generates Python code to run a pipe with example inputs and all necessary imports.

**Quick Example:**

```bash
pipelex build runner my_pipe -o run_my_pipe.py
```

For complete documentation, see the [Generate Runner Code section in Pipe Builder](pipe-builder.md#generate-runner-code).

## Kit Commands

Manage agent rules for AI coding assistants and sync migration instructions. See the [Kit Commands](kit.md) documentation for comprehensive details.

### Quick Reference

```bash
# Install agent rules for AI assistants
pipelex kit rules

# Remove agent rules
pipelex kit remove-rules

# Install migration instructions
pipelex kit migrations
```

For complete documentation including all options and examples, see [Kit Commands](kit.md).

## Usage Tips

1. **Initial Setup**

- Run `pipelex init config` to create configuration files
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

- [Pipe Builder](pipe-builder.md) - Generate pipelines from natural language
- [Kit Commands](kit.md) - Agent rules and migration management
- [Configure AI Providers](../setup/configure-ai-providers.md) - Set up LLM backends
- [Design and Run Pipelines](../build-reliable-ai-workflows-with-pipelex/design_and_run_pipelines.md) - Pipeline development guide
