---
title: Validation & Dry Run
description: "Catch errors before they cost time and money. Validate .mthds files statically and dry-run pipelines with mocked LLM responses — no API calls required."
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

List specific pipe codes in `pipelex.dry_run_config.allowed_to_fail_pipes` so dry-run validation can tolerate expected failures without failing the overall validation pass.

## CLI Usage

- `pipelex validate` — Static validation
- `pipelex run pipe my_pipe --dry-run` — Dry run execution
- `pipelex run pipe my_pipe --dry-run --mock-inputs` — Generate synthetic inputs

For configuration details, see [Dry Run Configuration](../configuration/config-pipeline-validation/dry-run-config.md).

Dry run is one of two run modes (live, dry run), each of which works in-process or distributed on a durable backend — see [Run Modes & Backends](../building-methods/pipes/run-modes-and-backends.md) for the full matrix.
