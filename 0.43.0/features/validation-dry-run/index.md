# Validation & Dry Run

Test your pipelines without making API calls.

## Overview

Pipelex provides multiple layers of validation to catch issues before they cost time and money. From static syntax checking to full dry-run execution with mocked responses, you can verify your methods at every stage of development.

## Pipeline Validation

Check pipeline syntax, structure, and compatibility without execution:

- **Syntax validation** — Catch MTHDS language errors via plxt linting
- **Structure validation** — Resolve pipe and concept references in the loaded library, and verify each pipe's declared inputs against the concepts that operator accepts — plus a controller's declared output against what it actually produces (for a `PipeSequence`, its last step's output concept and multiplicity)
- **Input validation** — Ensure required inputs are provided and correctly typed, and that every variable a step reads is bound by the time that step runs

A pipe that references a sub-pipe from a package that isn't loaded is reported as **skipped** rather than validated, so a passing run is not proof that every cross-package dependency resolves.

!!! note "Steps read from working memory, not from the previous step"
    A `PipeSequence` step resolves its inputs by name from working memory. They may come from the pipeline's inputs or from any earlier step — not necessarily the one immediately before it. Validation therefore checks that each name is bound when the step runs, rather than matching one step's output concept to the next step's declared input concept. There is no output-to-input chaining contract between consecutive steps to verify.

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
