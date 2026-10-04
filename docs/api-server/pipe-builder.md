# Pipe Builder (`/v1/build/*`) — REMOVED

**The five build routes are gone from this server**: `POST /v1/build/inputs`, `POST /v1/build/output`, `POST /v1/build/runner`, `POST /v1/build/concept` and `POST /v1/build/pipe-spec` now answer `404`. Nothing in the runtime changed; only the HTTP routes were removed.

## What replaces each one

- **An inputs template (`/v1/build/inputs`)** is projected by the client from the input form that [`POST /v1/pipe-io`](pipe-io.md) returns. `@pipelex/sdk`'s `prepareInputs`, `pipelex-sdk`'s `prepare_inputs` and `mthds-agent inputs` already do so, and `pipelex build inputs` writes the same template locally.
- **A pipe's declared output (`/v1/build/output`)** is described by the `output_form` and the pipe I/O contract that [`POST /v1/pipe-io`](pipe-io.md) returns. The rendered output example has no HTTP replacement; `pipelex build output` renders it locally.
- **The typed structures a runner script imported (`/v1/build/runner`)** are the `python-structures` target of [`POST /v1/codegen`](codegen.md). The runner script itself has no HTTP replacement.
- **The concept and pipe spec conversions (`/v1/build/concept`, `/v1/build/pipe-spec`)** have no replacement: a method is written as MTHDS directly and checked with [`POST /v1/validate`](pipe-validate.md).
