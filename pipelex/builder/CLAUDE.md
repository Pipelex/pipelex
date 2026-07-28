# Builder

Provides the spec layer for authoring Pipelex pipeline bundles (`.mthds` files). Specs are a convenience authoring format for AI agents — they compile down to blueprints via `to_blueprint()`.

## Core Flow

```
PipelexBundleSpec  →  to_blueprint()  →  PipelexBundleBlueprint  →  MTHDS file
```

## Code Layout

```
exceptions.py                  # Exception types
conventions.py                 # File naming defaults (bundle.mthds, inputs.json)
bundle_spec.py                 # PipelexBundleSpec — top-level spec model
bundle_header_spec.py          # Bundle header info
runner_code.py                 # Code generation utilities
concept/
  concept_spec.py              # ConceptSpec, ConceptStructureSpec, field types
pipe/
  pipe_spec.py                 # PipeSpec base class (pipe_code, type, inputs, output)
  pipe_spec_union.py           # PipeSpecUnion — discriminated union of all pipe types
  pipe_signature_spec.py       # Pipe signature information
  sub_pipe_spec.py             # SubPipeSpec — references to pipes inside controllers
  pipe_spec_map.py             # Pipe spec mapping
  pipe_llm_spec.py             # PipeLLM — LLM operator
  pipe_func_spec.py            # PipeFunc — Python function operator
  pipe_img_gen_spec.py         # PipeImgGen — image generation operator
  pipe_extract_spec.py         # PipeExtract — OCR/text extraction operator
  pipe_search_spec.py          # PipeSearch — web search operator
  pipe_compose_spec.py         # PipeCompose — template/construct operator
  pipe_sequence_spec.py        # PipeSequence — sequential controller
  pipe_parallel_spec.py        # PipeParallel — concurrent controller
  pipe_condition_spec.py       # PipeCondition — branching controller
  pipe_batch_spec.py           # PipeBatch — map-over-list controller
operations/
  concept_ops.py               # Parse/serialize concepts to TOML
  inputs_ops.py                # Generate example input JSON
  models_ops.py                # Model preset listing and markdown formatting
  output_ops.py                # Generate output JSON representations
  pipe_ops.py                  # Parse/serialize pipes to TOML
  runner_code_ops.py           # Code generation utilities
  validate_ops.py              # Validation operations
```

## Spec Architecture

All specs are Pydantic models (`StructuredContent` base). Two categories of pipes:

**Operators** (data transformation): `PipeLLM`, `PipeFunc`, `PipeImgGen`, `PipeExtract`, `PipeSearch`, `PipeCompose`

**Controllers** (execution flow): `PipeSequence`, `PipeParallel`, `PipeCondition`, `PipeBatch`

Each spec has `to_blueprint()` which converts it to the core framework's blueprint type. This separation keeps user-facing specs independent from internal execution types.

## Critical: PipeSpecs and ConceptSpecs Are NOT the MTHDS Language

PipeSpec and ConceptSpec subclasses in this directory are a **convenience authoring format** for AI agents and builders. They are NOT the ground truth of the MTHDS standard.

The ground truth is the **blueprint** layer:

- **Blueprints** (`pipelex/pipe_operators/`, `pipelex/pipe_controllers/`, `pipelex/pipe_machinery/`, `pipelex/mthds_parsing/`, `pipelex/core/`) define the actual MTHDS language. They are what `.mthds` files parse into via `MthdsParser.make_pipelex_bundle_blueprint()`. The base `PipeBlueprint` is in `pipe_machinery/pipe_blueprint.py`, the `PipelexBundleBlueprint` the parser produces is in `mthds_parsing/pipelex_bundle_blueprint.py`, and the concept/domain blueprints are in `core/`.
- **Specs** are transformed into blueprints via `to_blueprint()` and then discarded. Spec-level fields (e.g., `PipeComposeSpec.target_format`) may not exist on the corresponding blueprint (e.g., `PipeComposeBlueprint` uses `TemplateBlueprint` with `category` + `templating_style` instead).

When reviewing or modifying code: do not assume that a validation rule on a PipeSpec subclass reflects a rule of the MTHDS language. Check the corresponding blueprint class.

`PipeSpecUnion` is a `Field(discriminator="type")` union of all pipe spec types.

## Multiplicity Notation

Pipe inputs and outputs use multiplicity suffixes on concept names:

- `Text` — single item
- `Text[]` — variable-length list
- `Text[N]` — exactly N items

