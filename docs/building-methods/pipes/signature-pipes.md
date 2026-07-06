---
description: "Declare contract-only pipes with PipeSignature. Mock dependencies in dry-run, gate strict validation, and let agents stub a method end-to-end before implementing each step."
---

# Signature Pipes

Every pipe *has* a signature — its contract: the `inputs` it consumes, the `output` it promises, and a `description` of its purpose. A `PipeSignature` is that contract **alone**: a pipe declared by its signature with no implementation behind it. It is the placeholder you reach for when you want to design the shape of a pipeline (or one of its steps) before committing to the operator that will eventually do the work.

Because a signature is a contract rather than a way of running, it sits **outside** the executable pipe taxonomy. That taxonomy has two levels: a `PipeCategory` (`PipeOperator` or `PipeController`) and, beneath it, a concrete `PipeType` (`PipeLLM`, `PipeSequence`, and the rest). A `PipeSignature` is neither — it is not a `PipeType` like `PipeLLM` or `PipeSequence`, and it belongs to no `PipeCategory`. Its runtime form is a dry-run-only shim — it can verify inputs and mock its declared output, but it never executes live. Implementing a signature is not swapping one pipe *type* for another; it is fulfilling a contract with a concrete pipe that satisfies it.

Signatures let an agent (or a human author) build a complete, dry-runnable bundle while leaving some pipes deliberately unimplemented. Strict validation refuses any pipeline that still depends on a signature; lenient mode (`--allow-signatures`) dry-runs them as mocks, so you can keep iterating on the structure of a method before writing every step.

## When to use a `PipeSignature`

- **Sketching a pipeline top-down.** Define the controller (e.g. a `PipeSequence`) and stub each step as a `PipeSignature` so the structure dry-runs end-to-end.
- **Designing the contract first.** Capture inputs and outputs precisely — multiplicity included — before deciding whether the implementation will be a `PipeLLM`, a `PipeFunc`, or another operator.
- **Handing work between agents.** A planner agent emits signatures for the steps; an implementer agent replaces each one with a real operator.

## How a signature behaves at runtime

| Mode | Behavior |
| ---- | -------- |
| **Strict validation** (default) | Signatures are never a validation error: the bundle is valid, but a pipeline that reaches an unimplemented signature is reported as NOT yet runnable. The validation report lists the outstanding placeholders in `pending_signatures` and sets `is_runnable: false`; `validate` / `validate --all` / `validate bundle` / `validate method` then exit non-zero on that verdict (the runnability gate). In strict mode signature pipes are excluded from the dry-run sweep (not mock-run). |
| **Lenient validation** (`--allow-signatures`) | The verdict is unchanged (`pending_signatures` / `is_runnable` are still reported), but the runnability gate is tolerated (exit 0) and signature pipes are mock-run during the sweep — each mints a mock `Stuff` matching its declared `output`, multiplicity included. |
| **Live execution** | Running a pipeline that hits a signature raises `PipeSignatureNotExecutableError` — a signature has no implementation to execute. |

## MTHDS Parameters

A signature has **no `type`** — omitting the type *is* what makes a pipe a signature. A `[pipe.x]` section that declares only the contract below (and nothing else) is a signature. Adding any other field means you are describing an implementation, which must name its `type`; and writing `type = "PipeSignature"` explicitly is an error (`PipeSignature` is not a pipe type — delete the line).

| Parameter           | Type   | Description                                                                                                  | Required |
| ------------------- | ------ | ------------------------------------------------------------------------------------------------------------ | -------- |
| `description`       | string | Human-readable purpose of the contract.                                                                      | Yes      |
| `inputs`            | object | Mapping of input variable names to concept references. Multiplicity is supported (`Doc[]`, `Image[3]`).      | No       |
| `output`            | string | The concept the signature promises to produce. Multiplicity is supported.                                    | Yes      |
| `signature_for`     | string | Optional hint naming the downstream pipe type (e.g. `"PipeLLM"`) the signature stands in for. Tooling-only.  | No       |

`signature_for` cannot be set to `"PipeSignature"` — a signature standing in for a signature is nonsensical and is rejected at load time.

## Examples

### A single contract pipe

The simplest signature: a pipe that promises to summarize a document, with no implementation.

```toml
domain = "signature_demo"
main_pipe = "summarize_doc"

[concept]
SigDocument = "A document concept used for testing signatures."

[pipe.summarize_doc]
description = "Produces a summary of a document (contract only)."
inputs = { doc = "SigDocument" }
output = "Text"
```

No `type` line — that is what makes `summarize_doc` a signature. Validating this in strict mode fails (the main pipe *is* a signature). Validating it with `--allow-signatures` succeeds and dry-runs to a mock `Text`.

### A signature inside a `PipeSequence`

A common pattern: an existing operator runs first, then a signature stands in for the step that hasn't been implemented yet.

```toml
domain = "signature_mixed"
main_pipe = "process_doc"

[concept]
MixDoc = "A document concept."
MixSummary = "A summary concept."

[pipe.extract_doc]
type = "PipeLLM"
description = "Extract text from a document."
inputs = { doc = "MixDoc" }
output = "Text"
prompt = "Extract text from $doc."

[pipe.summarize_extracted]
description = "Summarize extracted text (contract only)."
inputs = { extracted = "Text" }
output = "MixSummary"

[pipe.process_doc]
type = "PipeSequence"
description = "Extract then summarize."
inputs = { doc = "MixDoc" }
output = "MixSummary"
steps = [
  { pipe = "extract_doc", result = "extracted" },
  { pipe = "summarize_extracted", result = "summary" },
]
```

Strict validation reports the dependency chain (`process_doc → summarize_extracted`) so you know exactly which controllers reach the signature. Lenient validation dry-runs the whole sequence: `extract_doc` mocks a `Text`, then `summarize_extracted` mocks a `MixSummary`.

### Multiplicity in a signature's inputs

Signatures honor the same multiplicity rules as other pipes (see [Understanding Multiplicity](understanding-multiplicity.md)).

```toml
domain = "signature_multiplicity"
main_pipe = "fuse_docs_and_images"

[concept]
FuseDoc = "A document."
FuseImage = "An image."
FuseReport = "A report."

[pipe.fuse_docs_and_images]
description = "Combine docs and exactly 3 images (contract only)."
inputs = { docs = "FuseDoc[]", images = "FuseImage[3]" }
output = "FuseReport"
```

Variable lists (`FuseDoc[]`) and fixed-length lists (`FuseImage[3]`) round-trip through the interpreter unchanged.

## Validating signatures from the CLI

Signatures interact with the [`pipelex validate`](../../tools/cli/validate.md) command via the `--allow-signatures` flag:

```bash
# Strict (default): fails if any reachable pipe is a PipeSignature
pipelex validate process_doc

# Lenient: signatures dry-run as mocks
pipelex validate process_doc --allow-signatures

# Same flag works for bundles and the --all sweep
pipelex validate bundle methods/draft_pipeline.mthds --allow-signatures
pipelex validate --all --allow-signatures
```

When `--all` runs in strict mode, signature pipes themselves are skipped during the iteration (an unreached signature is fine). Strict mode only fires when a non-signature pipe *depends on* a signature.

!!! note "Signatures and definitions can live in separate files"
    A signature and the concrete pipe that implements it do not have to sit in the same `.mthds` file. A same-domain library can be split across sibling files in one directory: a header file forward-declares pipes as `PipeSignature` (plus the concepts those contracts reference), and definition files supply the concrete pipes. Loading the set merges them — a `PipeSignature` and a concrete pipe of the same code reconcile (the concrete satisfies the header), provided their `inputs`/`output` contracts match. Order does not matter.

    On a successful lenient run, `validate bundle` reports `pending_signatures` — the headers still unimplemented across the *whole merged* library — and states explicitly whether the method is runnable (runnable once nothing remains, not yet runnable while headers are pending), so you can see exactly what is left to define. See [Validate Commands](../../tools/cli/validate.md) for the output surface. The same verdict is reported by the protocol-level `validate` (`PipelexMTHDSProtocol.validate`) as `pending_signatures` + `is_runnable` fields on its validation report, so a build driving the runtime through the MTHDS Protocol sees it too.

## Replacing a signature with a real implementation

When you are ready to implement, add a `type` to the pipe (a signature has none) and the operator-specific fields. The pipe code, `description`, `inputs`, and `output` typically carry over unchanged — that is the value of having declared the contract first.

```toml
[pipe.summarize_extracted]
type = "PipeLLM"
description = "Summarize extracted text."
inputs = { extracted = "Text" }
output = "MixSummary"
prompt = "Summarize the following text:\n\n$extracted"
```

Once every signature in the dependency graph is replaced, strict validation succeeds and the pipeline can be run live.

## Related Documentation

- [Understanding Multiplicity](understanding-multiplicity.md) — the bracket notation used for both inputs and outputs.
- [Pipe Operators](pipe-operators/index.md) — operators you can swap a signature out for.
- [Pipe Controllers](pipe-controllers/index.md) — controllers that orchestrate signatures alongside real pipes.
- [CLI Validate](../../tools/cli/validate.md) — the `--allow-signatures` flag and validation surface.
