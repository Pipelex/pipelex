# Pipe Controllers

Pipe controllers are the orchestrators of Pipelex pipelines.

## Overview

Pipelex provides the following pipe operators:

- `PipeSequence`: For chaining multiple pipes in sequence
- `PipeParallel`: For running different pipes in parallel
- `PipeBatch`: For running one pipe over a batch of inputs
- `PipeCondition`: For conditional execution based on input validation

## PipeSequence

Run multiple pipes in sequence.

### Key Features

- Sequential execution
- Working memory management
- Sub-pipe handling
- Pipeline composition

## PipeCondition

Enables conditional execution based on input validation.

### Key Features

- Expression-based routing
- Default fallback paths
- Jinja2 template support
- Input validation
- Error handling
