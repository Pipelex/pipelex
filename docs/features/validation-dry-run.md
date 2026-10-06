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
- **Structure validation** — Resolve pipe and concept references in the loaded library, refuse concepts whose structures form a cycle or whose fields name a concept that cannot be found, and verify each pipe's declared inputs against the concepts that operator accepts — plus a controller's declared output against what it actually produces (for a `PipeSequence`, its last step's output concept and multiplicity)
- **Input validation** — Ensure required inputs are provided and correctly typed, and that every variable a step reads is bound by the time that step runs
- **What each sequence step reads** — Follow each `PipeSequence` step by step and check every step against the concept and multiplicity of each name it reads, whichever declared input or earlier step stored it (`input_stuff_spec_mismatch`): a step reading a single `Page` where an extraction stored `Page[]` is refused before anything runs
- **Declared inputs are read** — For `PipeLLM`, `PipeCompose`, `PipeSearch` and `PipeImgGen`, every variable a template reads must be declared in `inputs` (`missing_input_variable`), and every declared input must be read by one of the pipe's templates (`extraneous_input_variable`): the prompt and system prompt of a `PipeLLM`, the template or the construct of a `PipeCompose`, the prompt of a `PipeSearch`, the prompt and negative prompt of a `PipeImgGen`. An unread input is refused on the pipe that declares it, before any controller above it is asked to supply it. A `PipeJudge` is the exception on that second rule: every input it declares is material for its model, so only the variables its `question` reads must be declared. A name the template sets with `{% set %}` is its own, not an input, from that statement on: after an `{% if %}` it stays set only when every branch sets it, the `{% else %}` included, so a name only some branches set is read from the input of that name on the other paths; and a loop, a macro or a block keeps what it sets to its own body.

A pipe that references a sub-pipe from a package that isn't loaded is reported as **skipped** rather than validated, so a passing run is not proof that every cross-package dependency resolves.

!!! note "Steps read from working memory, not from the previous step"
    A `PipeSequence` step resolves its inputs by name from working memory. They may come from the pipeline's inputs or from any earlier step — not necessarily the one immediately before it. Validation therefore follows each name through the sequence rather than matching one step's output to the next step's input: it checks that each name is bound when the step runs, and that the value last stored under it has the concept and multiplicity the step reads. A refined concept satisfies a step reading its parent, a batched step always stores a list, and a name a pipe that does not resolve at validation stored is assumed to hold what the step reads. See [PipeSequence](../building-methods/pipes/pipe-controllers/PipeSequence.md#what-each-step-reads).

## Dry Run Mode

Execute pipelines with mocked LLM responses to test pipeline logic, data flow, and orchestration without making API calls.

- **Mock generation** — Format-compliant mock values for constrained fields, including structured outputs
- **Configurable mock behavior** — Control mock list sizes, template handling, and response formats
- **Full pipeline execution** — Working memory, controllers, and data flow all work as in production
- **No credentials needed** — A dry run boots without inference credentials, on both `pipelex run --dry-run` and `pipelex-agent run --dry-run`. A backend whose API key is missing is skipped rather than fatal, so a dry run executes on a machine that holds no key at all. The one limit: a model handle that lives on a skipped backend cannot be resolved there, so a pipe pinning a bare handle such as `model = "gpt-4o-mini"` reports it as not found in the model deck; presets and the default model are unaffected

## Allowed-to-Fail Pipes

List specific pipe codes in `inference.dry_run.allowed_to_fail_pipes` so dry-run validation can tolerate expected failures without failing the overall validation pass.

## CLI Usage

- `pipelex validate` — Static validation
- `pipelex run pipe my_pipe --dry-run` — Dry run execution
- `pipelex run pipe my_pipe --dry-run --mock-inputs` — Generate synthetic inputs

For configuration details, see [Dry Run Configuration](../configuration/config-pipeline-validation/dry-run-config.md).

Dry run is one of two run modes (live, dry run), each of which works in-process or distributed on a durable backend — see [Run Modes & Backends](../building-methods/pipes/run-modes-and-backends.md) for the full matrix.
