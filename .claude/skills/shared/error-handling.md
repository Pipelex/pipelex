# Error Handling Reference

Canonical reference for all `pipelex-agent` error types, recovery strategies, and error classification.

## Error Output Format

On failure, `pipelex-agent` prints JSON to **stderr** and exits with code 1:

```json
{
  "error": true,
  "error_type": "ValidateBundleError",
  "message": "Human-readable error description",
  "hint": "Suggested recovery action",
  "error_domain": "input",
  "retryable": false
}
```

Fields:
- `error_type` — error class name for programmatic matching
- `message` — human-readable description
- `hint` — (optional) suggested recovery action, auto-added for known error types
- `error_domain` — classifies the error source (see Error Domains below)
- `retryable` — (optional, boolean) when `true`, the error may succeed on retry without changes (e.g., transient network issues)
- Additional fields vary by error type (e.g., `validation_errors`, `pipe_code`, `model_handle`, `fallback_list`, `pipe_stack`)

## Error Domains

| Domain | Meaning | Who Fixes |
|--------|---------|-----------|
| `input` | Bad .plx, wrong CLI args, bad JSON | Agent can fix directly |
| `config` | Missing API keys, wrong model routing, environment issues | Environment/config changes needed |
| `runtime` | Pipeline execution failure, transient errors | Depends on cause |

## Validation Errors

When `pipelex-agent validate` reports a `ValidateBundleError`, the JSON includes a `validation_errors` array:

```json
{
  "error": true,
  "error_type": "ValidateBundleError",
  "message": "Bundle validation failed",
  "hint": "Check the 'validation_errors' array for specific issues to fix",
  "error_domain": "input",
  "validation_errors": [
    {
      "error_type": "missing_input_variable",
      "pipe_code": "summarize_document",
      "message": "Missing input variable(s): context."
    }
  ]
}
```

### Validation Error Types

| Error Type | Meaning | Fix Strategy |
|------------|---------|--------------|
| `missing_input_variable` | Pipe prompt references a variable not in `inputs` | Add the missing variable to the pipe's `inputs` line |
| `extraneous_input_variable` | Pipe declares an input never used | Remove the unused variable from `inputs` |
| `input_stuff_spec_mismatch` | Input concept type doesn't match sub-pipe expectation | Correct the concept type in `inputs` |
| `inadequate_output_concept` | Output concept doesn't match connected pipes | Fix the `output` field to the correct concept |
| `inadequate_output_multiplicity` | Output single/list mismatch | Add or remove `[]` from the output concept |
| `circular_dependency_error` | Pipe references form a cycle | Restructure the workflow to break the cycle |
| `llm_output_cannot_be_image` | PipeLLM cannot output Image directly | Use PipeImgGen for image generation instead |
| `img_gen_input_not_text_compatible` | PipeImgGen needs text-compatible input | Ensure input is text-based (use `ImgGenPrompt`) |
| `invalid_pipe_code_syntax` | Pipe code doesn't follow snake_case | Rename the pipe to valid snake_case |
| `unknown_concept` | Referenced concept not defined in bundle | Add the concept definition, or fix the typo |
| `unknown_validation_error` | Uncategorized validation issue | Read the `message` field for details |

## Model & Config Errors

These indicate environment issues, not .plx file problems. **Cannot be fixed by editing the .plx file.**

| Error Type | Meaning | Recovery |
|------------|---------|----------|
| `PipeOperatorModelChoiceError` | Model preset doesn't resolve to an available model | Run `pipelex-agent doctor` — check routing configuration |
| `PipeOperatorModelAvailabilityError` | Model is configured but not reachable (missing API key, service down) | Run `pipelex-agent doctor` — verify API keys and model availability |

Example output:
```json
{
  "error": true,
  "error_type": "PipeOperatorModelChoiceError",
  "error_domain": "config",
  "message": "No model found for preset '$writing-creative'",
  "hint": "Run 'pipelex-agent doctor' to check available models and routing configuration",
  "pipe_code": "summarize",
  "model_type": "llm",
  "model_choice": "$writing-creative"
}
```

## Runtime Errors

| Error Type | Meaning | Recovery |
|------------|---------|----------|
| `PipelineExecutionError` | Pipeline failed during execution | Check `pipe_code` and `pipe_stack` in the error JSON |
| `BuildPipeError` | Automated build failed | Check `failure_memory_path` in error JSON for debugging details |
| `FileNotFoundError` | Bundle file or input file not found | Check file paths are correct |
| `JSONDecodeError` | Invalid JSON in inputs | Fix JSON syntax |
| `ArgumentError` | Invalid CLI flag combination | Check command flags (e.g., `--mock-inputs` requires `--dry-run`) |

## Cross-Domain Validation

When a bundle references pipes/concepts from other domains, single-file validation may fail with `unknown_concept` errors. Use `--library-dir` to load all related .plx files:

```bash
# Single file won't resolve cross-domain references
pipelex-agent validate my_bundle.plx  # May fail

# Load entire directory to resolve references
pipelex-agent validate my_bundle.plx --library-dir path/to/bundles/

# Also works with run
pipelex-agent run my_bundle.plx --inputs data.json -L ./shared_pipes/
```
