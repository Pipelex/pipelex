# Builder

Transforms high-level specifications into valid, executable Pipelex pipeline bundles (`.mthds` files). The builder is a spec-to-MTHDS compiler with built-in iterative repair.

## Core Flow

```
PipelexBundleSpec  →  to_blueprint()  →  PipelexBundleBlueprint  →  MTHDS file
      ↑                                         |
      |                                    validate_bundle()
      |                                         |
      └──── fix (up to N attempts) ─────── errors? ──→ done
```

`BuilderLoop.build_and_fix()` orchestrates: build → validate → fix → re-validate loop.

## Code Layout

```
builder.py                     # reconstruct_bundle_with_pipe_fixes() helper
builder_loop.py                # BuilderLoop — the main orchestration class
builder_errors.py              # Error types
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
  pipe_signature.py            # Pipe signature information
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
talents/
  llm_talent.py                # LLMTalent enum + preset mapping
  extract_talent.py            # ExtractTalent enum + preset mapping
  img_gen_talent.py            # ImgGenTalent enum + preset mapping
  search_talent.py             # SearchTalent enum + preset mapping
```

## Spec Architecture

All specs are Pydantic models (`StructuredContent` base). Two categories of pipes:

**Operators** (data transformation): `PipeLLM`, `PipeFunc`, `PipeImgGen`, `PipeExtract`, `PipeSearch`, `PipeCompose`

**Controllers** (execution flow): `PipeSequence`, `PipeParallel`, `PipeCondition`, `PipeBatch`

Each spec has `to_blueprint()` which converts it to the core framework's blueprint type. This separation keeps user-facing specs independent from internal execution types.

`PipeSpecUnion` is a `Field(discriminator="type")` union of all pipe spec types.

## Multiplicity Notation

Pipe inputs and outputs use multiplicity suffixes on concept names:

- `Text` — single item
- `Text[]` — variable-length list
- `Text[N]` — exactly N items

## BuilderLoop Fix Strategies

The loop applies these fixes automatically when validation fails:

| Problem | Fix |
|---------|-----|
| Undeclared concept | Generate via LLM ("generate_missing_concepts" pipeline), or remove from PipeParallel.combined_output |
| UNKNOWN_CONCEPT | Create concept that refines Text |
| INPUT_STUFF_SPEC_MISMATCH | Rewrite inputs from pipe.needed_inputs() |
| MISSING/EXTRANEOUS_INPUT_VARIABLE | Sync inputs with pipe.needed_inputs() |
| INADEQUATE_OUTPUT_CONCEPT (Sequence) | Set output = last step's output |
| INADEQUATE_OUTPUT_CONCEPT (Condition) | Set output = common output or native.Anything |
| INADEQUATE_OUTPUT_MULTIPLICITY | Match last step's output multiplicity |
| Compose multiplicity mismatch | Add `[]` to input concept, change field to list type |

After fixing, `_prune_unreachable_specs()` removes pipes unreachable from `main_pipe` and their unused concepts.

## Talent System

Talents are abstract capability labels mapped to concrete model presets. Each talent enum (in `talents/`) maps to a `$preset` code used in MTHDS files. When modifying talents, update both the enum and its preset mapping dict.
