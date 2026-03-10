---
title: Pipeline Orchestration
---

# Pipeline Orchestration

Controllers for building complex workflows from simple building blocks.

## Overview

<!-- TODO: Expand with orchestration philosophy -->

Pipeline controllers define how pipes are assembled and executed. They handle sequencing, parallelism, iteration, and conditional branching — all declaratively in `.mthds` files.

## PipeSequence

<!-- TODO: Describe sequential execution and data passing -->

Run pipes one after another, passing data through working memory. The most common controller for multi-step methods.

See [PipeSequence reference](../6-build-reliable-ai-workflows/pipes/pipe-controllers/PipeSequence.md).

## PipeParallel

<!-- TODO: Describe concurrent execution -->

Execute multiple independent pipes concurrently for faster throughput.

See [PipeParallel reference](../6-build-reliable-ai-workflows/pipes/pipe-controllers/PipeParallel.md).

## PipeBatch

<!-- TODO: Describe batch/map operations -->

Apply the same pipe to every item in a list — the map operation for pipelines.

See [PipeBatch reference](../6-build-reliable-ai-workflows/pipes/pipe-controllers/PipeBatch.md).

## PipeCondition

<!-- TODO: Describe conditional branching -->

Conditional branching based on Jinja2 expressions evaluated against working memory.

See [PipeCondition reference](../6-build-reliable-ai-workflows/pipes/pipe-controllers/PipeCondition.md).

## Working Memory

<!-- TODO: Describe working memory model, variable scoping -->

Temporary storage for data flowing between pipes within a single execution. Variables are typed by concepts and scoped to the pipeline.

See [Working Memory](../6-build-reliable-ai-workflows/pipes/working-memory.md).

## Multiplicity

<!-- TODO: Describe single vs variable vs fixed-count multiplicity -->

Control how many items pipes accept and produce: single values, variable-length lists (`[]`), or fixed-count lists (`[N]`).

See [Understanding Multiplicity](../6-build-reliable-ai-workflows/pipes/understanding-multiplicity.md).
