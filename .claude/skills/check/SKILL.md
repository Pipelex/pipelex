---
name: check
description: Check Pipelex workflow bundles for issues. Use when validating a .plx file, user asks "does this workflow make sense?", wants review without automatic fixes. Reports issues only - does not modify files.
---

# Check Pipelex Workflow

Validate and review Pipelex workflow bundles without making changes.

## Workflow

**Prerequisite**: Check CLI availability:
1. Try `pipelex --version`
2. If not found, try `uv run pipelex --version`
3. If neither works, guide install: `pip install pipelex` or `uv add pipelex`

Use whichever method works. Always add `--no-logo` to commands.

1. **Read the .plx file** - Load and parse the workflow

2. **Run CLI validation**:
   - Execute `pipelex --no-logo validate <file>.plx`
   - Capture all validation errors

3. **Analyze for additional issues**:
   - Unused concepts (defined but never referenced)
   - Unreachable pipes (not in main_pipe execution path)
   - Missing descriptions on pipes or concepts
   - Inconsistent naming conventions
   - Potential prompt issues (missing variables, unclear instructions)

4. **Report findings by severity**:
   - **Errors**: Validation failures that prevent execution
   - **Warnings**: Issues that may cause problems
   - **Suggestions**: Improvements for maintainability

5. **Do NOT make changes** - This skill is read-only

## Native Concepts

These are built-in and should NOT be flagged as undefined:
`Text`, `Image`, `PDF`, `Document`, `TextAndImages`, `Number`, `Page`, `JSON`, `ImgGenPrompt`, `Html`

## What Gets Checked

- TOML syntax validity
- Concept definitions and references (excluding native concepts above)
- Pipe type configurations
- Input/output type matching
- Variable references in prompts
- Cross-domain references
- Naming convention compliance

## Reference

See [Pipelex Language Reference](../shared/pipelex-reference.md) for complete syntax documentation.
