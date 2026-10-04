---
description: "The pipelex build runner command has been removed; write the runner yourself from the executing-pipelines guide and the codegen structures."
---

# Build Runner — REMOVED

**`pipelex build runner` is gone**: `pipelex build runner bundle` and `pipelex build runner method` are no longer commands, and `pipelex build` answers `runner` as an unknown command. The `POST /v1/build/runner` route that served the same script went before it.

## What replaces it

- **The typed structures the script imported** are the `python-structures` target of the codegen engine: [`pipelex build structures`](structures.md), or `pipelex codegen types --target python-structures`, writes them under `structures/` with their `codegen.lock`.
- **The example inputs the script carried** come from [`pipelex build inputs`](inputs.md).
- **The script itself** is a few lines you write once: open Pipelex with `Pipelex.make()`, then execute the pipe with `PipelexMTHDSProtocol().execute(pipe_code=..., inputs=...)` and read its typed output, as [Executing Pipelines](../../../building-methods/pipes/executing-pipelines.md) shows. To run a method without writing any code, use [`pipelex run`](../run.md).
