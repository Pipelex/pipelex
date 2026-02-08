---
name: check
description: Check Pipelex workflow bundles for issues. Use when validating a .plx file, user asks "does this workflow make sense?", wants review without automatic fixes. Reports issues only - does not modify files.
---

# Check Pipelex Workflow

Validate and review Pipelex workflow bundles without making changes.

## Workflow

**Prerequisite**: Check CLI availability:
1. Try `pipelex-agent --version`
2. If not found, try `uv run pipelex-agent --version`
3. If neither works, guide install: `pip install pipelex` or `uv add pipelex`

Use whichever method works for all subsequent commands.

1. **Read the .plx file** — Load and parse the workflow

2. **Run CLI validation**:
   ```bash
   pipelex-agent validate <file>.plx
   ```

   **Success output:**
   ```json
   {
     "success": true,
     "bundle_path": "my_bundle.plx",
     "validated_pipes": [
       {"pipe_code": "main_workflow", "status": "SUCCESS"},
       {"pipe_code": "summarize", "status": "SUCCESS"}
     ],
     "total_pipes": 2
   }
   ```

   **Validation failure output:**
   ```json
   {
     "error": true,
     "error_type": "ValidateBundleError",
     "message": "Bundle validation failed",
     "hint": "Check the 'validation_errors' array for specific issues to fix",
     "validation_errors": [
       {
         "error_type": "missing_input_variable",
         "pipe_code": "summarize_document",
         "message": "Missing input variable(s): context."
       }
     ]
   }
   ```

   **Model error output:**
   ```json
   {
     "error": true,
     "error_type": "PipeOperatorModelChoiceError",
     "message": "No model found for preset '$writing-creative'",
     "hint": "Run 'pipelex-agent doctor' to check available models and routing configuration",
     "pipe_code": "summarize",
     "model_type": "llm",
     "model_choice": "$writing-creative"
   }
   ```

3. **Parse the JSON output**:
   - If `success: true` — all pipes validated, report clean status
   - If `error_type: "ValidateBundleError"` — iterate through `validation_errors` array
   - If `error_type: "PipeOperatorModelChoiceError"` or `"PipeOperatorModelAvailabilityError"` — model/config issue, suggest `pipelex-agent doctor`

4. **Cross-domain validation** — when the bundle references pipes from other domains:
   ```bash
   pipelex-agent validate <file>.plx --library-dir path/to/bundles/
   ```

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

## Validation Error Types

| Error Type | Meaning |
|------------|---------|
| `missing_input_variable` | Pipe prompt references a variable not in `inputs` |
| `extraneous_input_variable` | Pipe declares an input never used |
| `input_stuff_spec_mismatch` | Input concept type doesn't match sub-pipe expectation |
| `inadequate_output_concept` | Output concept doesn't match connected pipes |
| `inadequate_output_multiplicity` | Output single/list mismatch |
| `circular_dependency_error` | Pipe references form a cycle |
| `llm_output_cannot_be_image` | PipeLLM cannot output Image directly |
| `img_gen_input_not_text_compatible` | PipeImgGen needs text-compatible input |
| `invalid_pipe_code_syntax` | Pipe code doesn't follow snake_case |
| `unknown_concept` | Referenced concept not defined in bundle |

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
- Model preset resolution (dry run)

## Reference

- [Pipelex Agent Guide](../shared/pipelex-agent-guide.md) for CLI philosophy and error type reference
- [Pipelex Language Reference](../shared/pipelex-reference.md) for complete syntax documentation
