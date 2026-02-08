# Pipelex Agent Guide

Strategy and reference for agents working with Pipelex programmatically.

## Agent CLI

Agents must use `pipelex-agent` exclusively. It outputs structured JSON (stdout=success, stderr=error with exit code 1).

There is also a `pipelex` CLI for human use — agents should not call it themselves, but can suggest it to the user when helpful:

- `pipelex doctor` — interactive config diagnostics (richer than `pipelex-agent doctor`)
- `pipelex show <pipe_or_concept>` — visual inspection of a pipe or concept
- `pipelex init config` — interactive first-time setup

**CLI availability check:**
1. Try `pipelex-agent --version`
2. If not found, try `uv run pipelex-agent --version`
3. Use whichever works for all subsequent commands (either bare `pipelex-agent` or `uv run pipelex-agent`)

## Two Approaches to Building

### Automated Build

Use `pipelex-agent build` to generate a complete workflow from a natural-language prompt:

```bash
pipelex-agent build "Given a theme, write a Haiku"
```

**JSON output on success:**
```json
{
  "output_dir": "pipelex-wip/pipeline_01",
  "plx_file": "pipelex-wip/pipeline_01/bundle.plx",
  "main_pipe_code": "write_haiku",
  "domain": "haiku_writing",
  "pipe_inputs": {"theme": "Text"},
  "pipe_output": "Haiku"
}
```

Key fields:
- `pipe_inputs` — maps input variable names to their concept types
- `pipe_output` — the output concept type
- `plx_file` — path to the generated .plx bundle

### Manual Build (the /build skill)

A 9-phase guided process: requirements → plan → concepts → structure → flow → review → pipes → assemble → validate. Use when you need full control over every detail.

### Recommended Approach

Start with automated build, then refine manually using /edit and /fix if the result needs adjustments.

## The Iterative Development Loop

```
                 ┌──────────────────────────────────┐
                 │                                   │
                 ▼                                   │
    ┌────────────────────┐                           │
    │  Build or Edit     │                           │
    │  (.plx file)       │                           │
    └─────────┬──────────┘                           │
              │                                      │
              ▼                                      │
    ┌────────────────────┐     ┌──────────────┐      │
    │  Validate          │────►│  Fix errors  │──────┘
    │  pipelex-agent     │ err │  /fix skill  │
    │  validate file.plx │     └──────────────┘
    └─────────┬──────────┘
              │ ok
              ▼
    ┌────────────────────┐
    │  Run               │
    │  pipelex-agent     │
    │  run file.plx      │
    └─────────┬──────────┘
              │
              ▼
    ┌────────────────────┐
    │  Inspect output    │
    │  Refine if needed  │──────────────────────────►(loop back to Edit)
    └────────────────────┘
```

## Understanding JSON Output

### Success Format

All `pipelex-agent` commands output JSON to **stdout** on success:

```json
{
  "success": true,
  "pipe_code": "my_pipe",
  ...command-specific fields...
}
```

### Error Format

On failure, JSON is printed to **stderr** and the process exits with code 1:

```json
{
  "error": true,
  "error_type": "ValidateBundleError",
  "message": "Human-readable error description",
  "hint": "Run 'pipelex-agent doctor' to check available models and routing configuration",
  ...error-specific fields...
}
```

Fields:
- `error_type` — error class name for programmatic matching
- `message` — human-readable description
- `hint` — (optional) suggested recovery action, auto-added for known error types
- Additional fields vary by error type (e.g., `validation_errors`, `pipe_code`, `model_handle`)

## Validation Error Structure

When `pipelex-agent validate` reports a `ValidateBundleError`, the JSON includes a `validation_errors` array:

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

Each item in `validation_errors` has:
- `error_type` — one of the validation error types below
- `pipe_code` — which pipe has the issue (may be null for bundle-level errors)
- `message` — description of the specific problem

## Error Type Reference

### Validation Error Types (in .plx files)

| Error Type | Meaning | Fix Strategy |
|------------|---------|--------------|
| `missing_input_variable` | A pipe's prompt references a variable not declared in its `inputs` | Add the missing variable to the pipe's `inputs` line |
| `extraneous_input_variable` | A pipe declares an input that is never referenced in its prompt or sub-pipes | Remove the unused variable from `inputs` |
| `input_stuff_spec_mismatch` | Input concept type doesn't match what the sub-pipe expects | Correct the concept type in `inputs` |
| `inadequate_output_concept` | Output concept doesn't match what connected pipes expect | Fix the `output` field to the correct concept |
| `inadequate_output_multiplicity` | Output multiplicity (single vs list) doesn't match | Add/remove `[]` from the output concept |
| `circular_dependency_error` | Pipe references create a cycle | Restructure the workflow to break the cycle |
| `llm_output_cannot_be_image` | PipeLLM cannot output Image type directly | Use PipeImgGen for image generation instead |
| `img_gen_input_not_text_compatible` | PipeImgGen input must be text-compatible | Ensure the input to PipeImgGen is text-based (use ImgGenPrompt) |
| `invalid_pipe_code_syntax` | Pipe code doesn't follow snake_case convention | Rename the pipe to valid snake_case |
| `unknown_concept` | A concept referenced in a pipe is not defined in the bundle | Add the concept definition to the bundle, or fix the typo |
| `unknown_validation_error` | Uncategorized validation issue | Read the `message` field for details |

### Runtime Error Types (when running pipelines)

| Error Type | Meaning | Fix Strategy |
|------------|---------|--------------|
| `PipeOperatorModelChoiceError` | The model preset in the pipe doesn't resolve to an available model | Run `pipelex-agent doctor` — check routing configuration |
| `PipeOperatorModelAvailabilityError` | The resolved model is not available (missing API key, service down) | Run `pipelex-agent doctor` — verify API keys and model availability |
| `PipelineExecutionError` | Pipeline failed during execution | Check `pipe_code` and `pipe_stack` in the error JSON for context |
| `BuildPipeError` | Automated build failed | Check `failure_memory_path` in error JSON for debugging details |

## Inline JSON for Inputs

The `--inputs` flag on `pipelex-agent run` accepts **both** file paths and inline JSON. The CLI auto-detects: if the value starts with `{`, it is parsed as JSON directly.

```bash
# File path
pipelex-agent run bundle.plx --inputs pipelex-wip/inputs/data.json

# Inline JSON (no file creation needed)
pipelex-agent run bundle.plx --inputs '{"theme": {"concept": "native.Text", "content": {"text": "nature"}}}'
```

Inline JSON is the fastest path for agents — skip file creation for simple inputs.

## Working Directory Convention

All generated files go into `pipelex-wip/`:

```
pipelex-wip/
  pipeline_01/          # Automated build output
    bundle.plx
  pipeline_02/
    bundle.plx
  inputs/               # Synthesized input files
    test_input.json
  test-files/           # Generated test files (images, PDFs)
    photo.jpg
```

## Using the Doctor Command

When you encounter model-related errors (`PipeOperatorModelChoiceError`, `PipeOperatorModelAvailabilityError`), run the doctor:

```bash
pipelex-agent doctor
```

The doctor checks:
- Configuration health
- Available models and routing
- API key validity

It auto-fixes issues when possible. Run it before debugging model errors manually.

## Generating Visualizations

Agents can generate execution graph visualizations for human review using two methods:

### Standalone: `pipelex-agent graph`

Render an existing `graphspec.json` (produced by a previous run) into HTML:

```bash
pipelex-agent graph graphspec.json
pipelex-agent graph graphspec.json --format mermaidflow
pipelex-agent graph graphspec.json -o ./output/ --format reactflow
```

**JSON output on success:**
```json
{
  "success": true,
  "output_dir": "path/to/dir",
  "files": {
    "mermaidflow_html": "path/to/mermaidflow.html",
    "reactflow_html": "path/to/reactflow.html"
  },
  "node_count": 5
}
```

Options:
- `--format` / `-f` — `mermaidflow`, `reactflow`, or `both` (default: `both`)
- `--out` / `-o` — output directory (default: same directory as input file)

### Inline: `pipelex-agent run --graph`

Generate graphs during a pipeline run:

```bash
pipelex-agent run bundle.plx --inputs data.json --graph
```

When `--graph` is set, the success JSON includes an additional `graph_files` field:
```json
{
  "success": true,
  "pipe_code": "main_pipe",
  "graph_files": {
    "graphspec_json": "pipelex-wip/graphspec.json",
    "mermaidflow_html": "pipelex-wip/mermaidflow.html",
    "reactflow_html": "pipelex-wip/reactflow.html"
  },
  ...
}
```

## Agent CLI Command Reference

| Command | Purpose | Example |
|---------|---------|---------|
| `build` | Generate a pipeline from a prompt | `pipelex-agent build "process invoices"` |
| `run` | Execute a pipeline | `pipelex-agent run bundle.plx --inputs data.json` |
| `validate` | Validate a bundle or pipe | `pipelex-agent validate bundle.plx` |
| `inputs` | Generate example input JSON | `pipelex-agent inputs bundle.plx` |
| `concept` | Structure a concept from JSON spec | `pipelex-agent concept --spec '{...}'` |
| `pipe` | Structure a pipe from JSON spec | `pipelex-agent pipe --type PipeLLM --spec '{...}'` |
| `assemble` | Assemble a .plx bundle from parts | `pipelex-agent assemble --domain my_domain ...` |
| `graph` | Render graphspec.json to HTML | `pipelex-agent graph graphspec.json` |
| `doctor` | Check config health and auto-fix | `pipelex-agent doctor` |
