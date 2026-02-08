---
name: check
description: Check and validate Pipelex workflow bundles for issues. Use when user says "validate this", "check my workflow", "does this .plx make sense?", "review this pipeline", "any issues?", "is this correct?". Reports problems without modifying files. Read-only analysis.
---

# Check Pipelex Workflow

Validate and review Pipelex workflow bundles without making changes.

## Workflow

**Prerequisite**: See [CLI Prerequisites](../shared/prerequisites.md)

1. **Read the .plx file** — Load and parse the workflow

2. **Run CLI validation**:
   ```bash
   pipelex-agent validate <file>.plx
   ```

3. **Parse the JSON output**:
   - If `success: true` — all pipes validated, report clean status
   - If error — see [Error Handling Reference](../shared/error-handling.md) for error types and recovery

4. **Cross-domain validation** — when the bundle references pipes from other domains, use `--library-dir` (see [Error Handling — Cross-Domain](../shared/error-handling.md#cross-domain-validation))

5. **Analyze for additional issues** (manual review beyond CLI validation):
   - Unused concepts (defined but never referenced)
   - Unreachable pipes (not in main_pipe execution path)
   - Missing descriptions on pipes or concepts
   - Inconsistent naming conventions
   - Potential prompt issues (missing variables, unclear instructions)

6. **Report findings by severity**:
   - **Errors**: Validation failures from CLI (with `error_type` and `pipe_code`)
   - **Warnings**: Issues that may cause problems (e.g., model availability)
   - **Suggestions**: Improvements for maintainability

7. **Do NOT make changes** — This skill is read-only

## What Gets Checked

- TOML syntax validity
- Concept definitions and references
- Pipe type configurations
- Input/output type matching
- Variable references in prompts
- Cross-domain references
- Naming convention compliance
- Model preset resolution (dry run)

## Reference

- [CLI Prerequisites](../shared/prerequisites.md) — read at skill start to check CLI availability
- [Error Handling](../shared/error-handling.md) — read when CLI returns an error to determine recovery
- [Pipelex Agent Guide](../shared/pipelex-agent-guide.md) — read for CLI command syntax or output format details
- [Pipelex Language Reference](../shared/pipelex-reference.md) — read when reviewing .plx TOML syntax
