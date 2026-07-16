---
description: "Pipe controllers orchestrate execution flow in Pipelex. Sequence, parallelize, batch, or branch your pipes for structured AI workflows."
---

# Pipe Controllers

!!! tip "MTHDS Standard Reference"
    Pipe controllers are part of the MTHDS open standard. For the authoritative language specification, see [Pipes & Controllers](https://mthds.ai/latest/language/pipes-controllers/) on mthds.ai. This page documents Pipelex-specific behavior and usage.

Pipe controllers are the orchestrators of a Pipelex pipeline. While [Pipe Operators](../pipe-operators/index.md) perform the work, pipe controllers define the method and manage the execution logic. They allow you to run other pipes in sequence, in parallel, or conditionally.

## Core Controllers

Here are the primary pipe controllers available in Pipelex:

-   [**`PipeSequence`**](./PipeSequence.md): The most fundamental controller. It runs a series of pipes one after another, passing the results from one step to the next.
-   [**`PipeParallel`**](./PipeParallel.md): Executes multiple independent pipes at the same time, significantly speeding up methods where tasks don't depend on each other.
-   [**`PipeBatch`**](./PipeBatch.md): Performs a "map" operation. It takes a list of items and runs the same pipe on every single item in parallel.
-   [**`PipeCondition`**](./PipeCondition.md): Adds branching logic (`if/else`) to your pipeline. It evaluates an expression and chooses which pipe to run next based on the result.

## Overview

Pipelex provides the following pipe controllers:

- `PipeSequence`: For chaining multiple pipes in sequence
- `PipeParallel`: For running different pipes in parallel
- `PipeBatch`: For running one pipe over a batch of inputs
- `PipeCondition`: For conditional execution based on an evaluated expression

## PipeSequence

Run multiple pipes in sequence.

### Key Features

- Sequential execution
- Working memory management
- Sub-pipe handling
- Pipeline composition

## PipeCondition

Enables conditional execution based on an evaluated expression.

### Key Features

- Expression-based routing
- Default fallback paths
- Jinja2 template support
- Error handling
