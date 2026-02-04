---
name: fix
description: Fix issues in Pipelex workflow bundles. Use when user wants to fix validation errors, asks "fix this workflow", or after /check identified issues. Automatically fixes issues and re-validates.
---

# Fix Pipelex Workflow

Automatically fix issues in Pipelex workflow bundles.

## Workflow

**Prerequisite**: Check CLI availability:
1. Try `pipelex --version`
2. If not found, try `uv run pipelex --version`
3. If neither works, guide install: `pip install pipelex` or `uv add pipelex`

Use whichever method works. Always add `--no-logo` to commands.

1. **Read the .plx file and validate**:
   - Run `pipelex --no-logo validate <file>.plx`
   - Identify all errors and warnings

2. **Apply fixes for common issues**:
   - **missing_input_variable**: Add missing input to parent pipe's `inputs`
   - **Multi-line inputs**: Reformat to single line
   - **Undefined concept references**: Create concept definition or fix typo
   - **Invalid pipe ordering**: Reorder pipes (controllers first)
   - **Missing required fields**: Add with sensible defaults
   - **Naming convention violations**: Rename to follow conventions

3. **Re-validate after each fix**:
   - Run validation again
   - Continue fixing until no errors remain

4. **Report what was fixed**:
   - List all changes made
   - Show any remaining warnings or suggestions
   - Confirm validation passes

5. **Iterate if needed**:
   - Some fixes may reveal new issues
   - Continue until validation passes completely

## Native Concepts

These are built-in and do NOT need definitions:
`Text`, `Image`, `PDF`, `Document`, `TextAndImages`, `Number`, `Page`, `JSON`, `ImgGenPrompt`, `Html`

## Common Fixes

| Error | Fix |
|-------|-----|
| `missing_input_variable` | Add variable to parent pipe's inputs |
| Multi-line inputs block | Reformat to `inputs = { a = "A", b = "B" }` |
| Undefined concept | Create definition or fix reference (unless it's a native concept) |
| Missing description | Add descriptive text |
| Wrong pipe order | Move controller pipes before sub-pipes |

## Reference

See [Pipelex Language Reference](../shared/pipelex-reference.md) for complete syntax documentation.
