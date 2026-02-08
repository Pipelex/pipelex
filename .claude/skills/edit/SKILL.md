---
name: edit
description: Edit existing Pipelex workflow bundles (.plx files). Use when user says "change this pipe", "update the prompt", "rename this concept", "add a step", "remove this pipe", "modify the workflow", "refactor this pipeline", or wants any modification to an existing .plx file.
---

# Edit Pipelex Workflow

Modify existing Pipelex workflow bundles.

## Workflow

**Prerequisite**: See [CLI Prerequisites](../shared/prerequisites.md)

1. **Read the existing .plx file** — Understand current structure before making changes

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
   ```bash
   pipelex-agent validate <file>.plx
   ```
   If errors, see [Error Handling Reference](../shared/error-handling.md) for recovery strategies by error domain. Use /fix skill for automatic error resolution.

5. **Regenerate inputs if needed**:
   - If inputs changed, run `pipelex-agent inputs <file>.plx`
   - Update existing inputs.json if present

## Common Edit Operations

- **Add a pipe**: Define concept if needed, add pipe in correct order
- **Modify a prompt**: Update prompt text, check variable references
- **Change inputs/outputs**: Update type, regenerate inputs
- **Add batch processing**: Add `batch_over` and `batch_as` to step
- **Refactor to sequence**: Wrap multiple pipes in PipeSequence

## Reference

- [CLI Prerequisites](../shared/prerequisites.md) — read at skill start to check CLI availability
- [Error Handling](../shared/error-handling.md) — read when CLI returns an error to determine recovery
- [Pipelex Agent Guide](../shared/pipelex-agent-guide.md) — read for CLI command syntax or output format details
- [Pipelex Language Reference](../shared/pipelex-reference.md) — read when writing or modifying .plx TOML syntax
