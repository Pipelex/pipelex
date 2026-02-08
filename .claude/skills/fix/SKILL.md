---
name: fix
description: Fix issues in Pipelex workflow bundles. Use when user wants to fix validation errors, asks "fix this workflow", or after /check identified issues. Automatically fixes issues and re-validates.
---

# Fix Pipelex Workflow

Automatically fix issues in Pipelex workflow bundles.

## Workflow

**Prerequisite**: Check CLI availability:
1. Try `pipelex-agent --version`
2. If not found, try `uv run pipelex-agent --version`
3. If neither works, guide install: `pip install pipelex` or `uv add pipelex`

Use whichever method works for all subsequent commands.

### Step 1: Validate and Identify Errors

```bash
pipelex-agent validate <file>.plx
```

Parse the JSON output:
- If `success: true` — nothing to fix, report clean status
- If `error_type: "ValidateBundleError"` — iterate through `validation_errors` array and fix each
- If `error_type: "PipeOperatorModelChoiceError"` or `"PipeOperatorModelAvailabilityError"` — this is a model/config issue, not a .plx fix (see "Model & Config Errors" below)

### Step 2: Fix .plx Validation Errors

Use the `error_type` field from each validation error to determine the fix:

| Error Type | Fix Strategy |
|------------|-------------|
| `missing_input_variable` | Add the missing variable(s) to the parent pipe's `inputs` line. The `message` field names the variables. |
| `extraneous_input_variable` | Remove the unused variable(s) from the pipe's `inputs` line. |
| `input_stuff_spec_mismatch` | Correct the concept type in `inputs` to match what the sub-pipe expects. |
| `inadequate_output_concept` | Change the `output` field to the correct concept type. |
| `inadequate_output_multiplicity` | Add or remove `[]` from the output concept (e.g., `Text` vs `Text[]`). |
| `circular_dependency_error` | Restructure the workflow to break the cycle — usually requires rethinking the pipe graph. |
| `llm_output_cannot_be_image` | Use PipeImgGen instead of PipeLLM for image generation. |
| `img_gen_input_not_text_compatible` | Ensure PipeImgGen input is text-based (use `ImgGenPrompt`). |
| `invalid_pipe_code_syntax` | Rename the pipe to valid snake_case. |
| `unknown_concept` | Add the concept definition to the bundle, or fix the typo in the reference. |

### Step 3: Fix TOML Formatting Issues

These aren't always reported by validation but cause problems:

**Multi-line inputs** — must be on a single line:
```toml
# WRONG
inputs = {
    a = "A",
    b = "B"
}

# CORRECT
inputs = { a = "A", b = "B" }
```

**Pipe ordering** — controllers before sub-pipes:
```toml
# CORRECT: main pipe first, then sub-pipes in execution order
[pipe.main_workflow]
type = "PipeSequence"
steps = [
    { pipe = "step_one", result = "intermediate" },
    { pipe = "step_two", result = "final" }
]

[pipe.step_one]
...

[pipe.step_two]
...
```

**Missing required fields** — add with sensible defaults:
- `description` on every pipe and concept
- `type` on every pipe
- `output` on every pipe

### Step 4: Re-validate

After applying fixes, re-validate:

```bash
pipelex-agent validate <file>.plx
```

Continue the fix-validate loop until `success: true` is returned. Some fixes reveal new issues — for example, fixing a `missing_input_variable` may expose an `input_stuff_spec_mismatch` on the newly added input.

### Step 5: Report Results

- List all changes made (which pipes were modified and how)
- Show the final validation result
- Flag any remaining warnings or suggestions

## Model & Config Errors

These errors indicate issues with the Pipelex configuration, not the .plx file itself:

| Error Type | What To Do |
|------------|-----------|
| `PipeOperatorModelChoiceError` | The model preset (e.g., `$writing-creative`) doesn't resolve. Run `pipelex-agent doctor` to check routing configuration. |
| `PipeOperatorModelAvailabilityError` | The model is configured but not reachable (missing API key, service down). Run `pipelex-agent doctor` to verify API keys. |

These cannot be fixed by editing the .plx file. Run `pipelex-agent doctor` which will auto-fix configuration issues when possible.

## Cross-Domain Validation

When the bundle references pipes/concepts from other domains:
```bash
pipelex-agent validate <file>.plx --library-dir path/to/bundles/
```

If validation fails with "unknown concept" errors for concepts that exist in other bundles, the `--library-dir` flag is missing.

## Native Concepts

These are built-in and do NOT need definitions:
`Text`, `Image`, `PDF`, `Document`, `TextAndImages`, `Number`, `Page`, `JSON`, `ImgGenPrompt`, `Html`

## Reference

- [Pipelex Agent Guide](../shared/pipelex-agent-guide.md) for CLI philosophy and error type reference
- [Pipelex Language Reference](../shared/pipelex-reference.md) for complete syntax documentation
