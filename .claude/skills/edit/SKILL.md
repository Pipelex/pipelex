---
name: edit
description: Edit existing Pipelex workflow bundles (.plx files). Use when modifying an existing .plx file, adding/removing/changing pipes or concepts, refactoring workflow structure.
---

# Edit Pipelex Workflow

Modify existing Pipelex workflow bundles.

## Workflow

**Prerequisite**: Check CLI availability:
1. Try `pipelex-agent --version`
2. If not found, try `uv run pipelex-agent --version`
3. If neither works, guide install: `pip install pipelex` or `uv add pipelex`

Use whichever method works for all subsequent commands.

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
   - Run `pipelex-agent validate <file>.plx`
   - Fix any errors introduced by changes

   **Validation error example:**
   ```json
   {
     "error": true,
     "error_type": "ValidateBundleError",
     "error_domain": "input",
     "message": "Bundle validation failed",
     "hint": "Check the 'validation_errors' array for specific issues to fix",
     "validation_errors": [
       {"error_type": "missing_input_variable", "pipe_code": "my_pipe", "message": "..."}
     ]
   }
   ```

   **Error recovery:**

   | Error Domain | Error Types | Action |
   |-------------|-------------|--------|
   | `input` | `ValidateBundleError`, `PLXDecodeError`, `PipelexInterpreterError` | Fix the .plx file based on `validation_errors` or `message`; use /fix skill |
   | `config` | `PipeOperatorModelChoiceError`, `PipeOperatorModelAvailabilityError` | Run `pipelex-agent doctor`; this is not a .plx issue |

5. **Regenerate inputs if needed**:
   - If inputs changed, run `pipelex-agent inputs <file>.plx`
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

- [Pipelex Agent Guide](../shared/pipelex-agent-guide.md) for CLI philosophy and error type reference
- [Pipelex Language Reference](../shared/pipelex-reference.md) for complete syntax documentation
