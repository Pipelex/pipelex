---
title: Validation & Dry Run
---

# Validation & Dry Run

Test your pipelines without making API calls.

## Overview

Pipelex provides multiple layers of validation to catch issues before they cost time and money. From static syntax checking to full dry-run execution with mocked responses, you can verify your methods at every stage of development.

## Pipeline Validation

Check pipeline syntax, structure, and compatibility without execution:

- **Syntax validation** — Catch MTHDS language errors via plxt linting
- **Structure validation** — Verify concept compatibility between pipes, ensuring inputs and outputs match
- **Input validation** — Ensure required inputs are provided and correctly typed

## Dry Run Mode

Execute pipelines with mocked LLM responses to test pipeline logic, data flow, and orchestration without making API calls.

- **Mock generation** — Format-compliant mock values for constrained fields, including structured outputs
- **Configurable mock behavior** — Control mock list sizes, template handling, and response formats
- **Full pipeline execution** — Working memory, controllers, and data flow all work as in production

## Allowed-to-Fail Pipes

Mark specific pipes as `allowed_to_fail` so they can fail without stopping the entire pipeline execution. When an allowed-to-fail pipe encounters an error, the pipeline continues and downstream pipes receive an empty result.

## CLI Usage

- `pipelex validate` — Static validation
- `pipelex run --dry-run` — Dry run execution
- `pipelex run --mock-inputs` — Generate synthetic inputs

For configuration details, see [Dry Run Configuration](../7-configuration/config-pipeline-validation/dry-run-config.md).
