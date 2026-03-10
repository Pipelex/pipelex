---
title: Pipeline Orchestration
---

# Pipeline Orchestration

Controllers for building complex workflows from simple building blocks.

## Overview

Pipeline controllers define how pipes are assembled and executed. They handle sequencing, parallelism, iteration, and conditional branching — all declaratively in `.mthds` files. Controllers are themselves pipes, so they can be nested to build arbitrarily complex workflows.

## PipeSequence

Run pipes one after another, passing data through working memory. The most common controller for multi-step methods. Each step can read variables written by previous steps, enabling progressive data enrichment.

See [PipeSequence reference](../6-build-reliable-ai-workflows/pipes/pipe-controllers/PipeSequence.md).

## PipeParallel

Execute multiple independent pipes concurrently for faster throughput. All branches share the same input working memory, and their outputs are merged back when all branches complete.

See [PipeParallel reference](../6-build-reliable-ai-workflows/pipes/pipe-controllers/PipeParallel.md).

## PipeBatch

Apply the same pipe to every item in a list — the map operation for pipelines. Takes a list input and produces a list output, processing each item independently.

See [PipeBatch reference](../6-build-reliable-ai-workflows/pipes/pipe-controllers/PipeBatch.md).

## PipeCondition

Conditional branching based on Jinja2 expressions evaluated against working memory. Route execution to different pipes depending on runtime data, enabling dynamic method behavior.

See [PipeCondition reference](../6-build-reliable-ai-workflows/pipes/pipe-controllers/PipeCondition.md).

## Working Memory

Temporary storage for data flowing between pipes within a single execution. Variables are typed by concepts and scoped to the pipeline. Each pipe reads from and writes to working memory, creating a shared data context across the method.

See [Working Memory](../6-build-reliable-ai-workflows/pipes/working-memory.md).

## Multiplicity

Control how many items pipes accept and produce: single values, variable-length lists (`[]`), or fixed-count lists (`[N]`). Multiplicity is declared in the pipe definition and validated at definition time.

See [Understanding Multiplicity](../6-build-reliable-ai-workflows/pipes/understanding-multiplicity.md).
