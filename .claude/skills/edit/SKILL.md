---
name: edit
description: Edit existing Pipelex workflow bundles (.plx files). Use when modifying an existing .plx file, adding/removing/changing pipes or concepts, refactoring workflow structure.
---

# Edit Pipelex Workflow

Modify existing Pipelex workflow bundles.

## Workflow

**Prerequisite**: Check CLI availability:
1. Try `pipelex --version`
2. If not found, try `uv run pipelex --version`
3. If neither works, guide install: `pip install pipelex` or `uv add pipelex`

Use whichever method works. Always add `--no-logo` to commands.

1. **Read the existing .plx file** - Understand current structure before making changes

2. **Understand requested changes**:
   - What pipes need to be added, removed, or modified?
   - What concepts need to change?
   - Does the workflow structure need refactoring?

3. **Apply changes**:
   - Maintain proper pipe ordering (controllers before sub-pipes)
   - Keep TOML formatting consistent
   - Preserve cross-references between pipes
   - Keep inputs on a single line
   - Maintain POSIX standard (empty line at end, no trailing whitespace)

4. **Validate after editing**:
   - Run `pipelex --no-logo validate <file>.plx`
   - Fix any errors introduced by changes

5. **Regenerate inputs if needed**:
   - If inputs changed, run `pipelex --no-logo build inputs <file>.plx`
   - Update existing inputs.json if present

## Native Concepts

These are built-in and do NOT need definitions:
`Text`, `Image`, `PDF`, `Document`, `TextAndImages`, `Number`, `Page`, `JSON`, `ImgGenPrompt`, `Html`

## Common Edit Operations

- **Add a pipe**: Define concept if needed (unless using native concepts above), add pipe in correct order
- **Modify a prompt**: Update prompt text, check variable references
- **Change inputs/outputs**: Update type, regenerate inputs
- **Add batch processing**: Add `batch_over` and `batch_as` to step
- **Refactor to sequence**: Wrap multiple pipes in PipeSequence

## Reference

See [Pipelex Language Reference](../shared/pipelex-reference.md) for complete syntax documentation.
