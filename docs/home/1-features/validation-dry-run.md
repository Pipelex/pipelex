---
title: Validation & Dry Run
---

# Validation & Dry Run

Test your pipelines without making API calls.

## Overview

<!-- TODO: Expand with validation philosophy -->

Pipelex provides multiple layers of validation to catch issues before they cost time and money. From static syntax checking to full dry-run execution with mocked responses.

## Pipeline Validation

<!-- TODO: Describe static validation capabilities -->

Check pipeline syntax, structure, and compatibility without execution:

- **Syntax validation** — Catch MTHDS language errors
- **Structure validation** — Verify concept compatibility between pipes
- **Input validation** — Ensure required inputs are provided and correctly typed

## Dry Run Mode

<!-- TODO: Describe dry run execution -->

Execute pipelines with mocked LLM responses to test pipeline logic, data flow, and orchestration without making API calls.

- **Mock generation** — Format-compliant mock values for constrained fields
- **Configurable mock behavior** — Control mock list sizes, template handling, and response formats
- **Full pipeline execution** — Working memory, controllers, and data flow all work as in production

## Allowed-to-Fail Pipes

<!-- TODO: Describe error tolerance configuration -->

Mark specific pipes that can fail without stopping the entire pipeline execution.

## CLI Usage

- `pipelex validate` — Static validation
- `pipelex run --dry-run` — Dry run execution
- `pipelex run --mock-inputs` — Generate synthetic inputs

For configuration details, see [Dry Run Configuration](../7-configuration/config-pipeline-validation/dry-run-config.md).
