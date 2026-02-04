---
name: build
description: Build new Pipelex workflow bundles (.plx files). Use when creating a new workflow, user says "create a pipeline", "new workflow", "build a .plx file". Supports interactive requirements gathering and direct creation.
---

# Build Pipelex Workflow

Create new Pipelex workflow bundles from scratch.

## Workflow

**Prerequisite**: Check CLI availability:
1. Try `pipelex --version`
2. If not found, try `uv run pipelex --version`
3. If neither works, guide install: `pip install pipelex` or `uv add pipelex`

Use whichever method works. Always add `--no-logo` to commands.

1. **Gather requirements** - Ask the user:
   - Interactive mode (guided) or direct creation?
   - What inputs does the workflow receive?
   - What outputs should it produce?
   - What transformations are needed?

2. **Interactive mode** (if chosen):
   - Walk through each step of the pipeline
   - Identify concepts needed (inputs, intermediates, outputs)
   - Map transformations to appropriate pipe types
   - Confirm the plan before writing

3. **Create the .plx file**:
   - Follow naming conventions (domain: snake_case, concepts: PascalCase, pipes: snake_case)
   - Define domain and description
   - Define concepts with inline structures
   - Order pipes: main/controller pipes first, then sub-pipes in execution order
   - Write file with POSIX standard (empty line at end, no trailing whitespace)

4. **Validate**:
   - Run `pipelex --no-logo build inputs <file>.plx` to generate inputs
   - Run `pipelex --no-logo validate <file>.plx`
   - Fix any validation errors

5. **Test**:
   - Offer to run `pipelex --no-logo run <file>.plx --dry-run --mock-inputs`
   - Help user prepare real inputs if needed

## Pipe Type Selection

### PipeOperators (Data Transformation)

Transform data directly. Define after the controllers that reference them.

| Type | Use When | Key Features |
|------|----------|--------------|
| **PipeLLM** | Generating text or structured objects with AI | Prompts with `@block` and `$inline` vars, system prompts, model config, multiple outputs `[N]` or `[]` |
| **PipeExtract** | Extracting content from PDF or Image | Output is always `Page` (list of pages with text/images) |
| **PipeCompose** | Building text from templates or constructing objects | `template` for text, `construct` for structured objects with `from`/`template` fields |
| **PipeImgGen** | Generating images from prompts | Requires `prompt` field referencing input, `model` preset, optional `aspect_ratio` |
| **PipeFunc** | Custom Python logic | Calls registered function, full programmatic control |

### PipeControllers (Orchestration)

Control flow and coordinate other pipes. Define them first in the .plx file.

| Type | Use When | Key Features |
|------|----------|--------------|
| **PipeSequence** | Chaining multiple steps in order | Sequential execution, intermediate results, batch processing with `batch_over` |
| **PipeCondition** | Branching based on data values | Route to different pipes based on expression, `default_outcome` for fallback |
| **PipeBatch** | Transforming each item in a list | Map operation: list in → list out, same pipe applied to each item |
| **PipeParallel** | Running multiple pipes concurrently | Separate outputs to working memory, or combined into single output |

## Other Key Decisions

- **Concept design**: Keep concepts focused and reusable
- **Input multiplicity**: Single item, list `[]`, or fixed count `[N]`

## Reference

See [Pipelex Language Reference](../shared/pipelex-reference.md) for complete syntax documentation.
