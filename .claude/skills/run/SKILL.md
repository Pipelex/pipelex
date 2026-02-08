---
name: run
description: Run Pipelex workflows and interpret results. Use when executing a pipeline, user says "run this workflow", "execute the pipeline", "test this .plx file", or wants to see pipeline output.
---

# Run Pipelex Workflow

Execute Pipelex pipelines and interpret their JSON output.

## Workflow

**Prerequisite**: Check CLI availability:
1. Try `pipelex-agent --version`
2. If not found, try `uv run pipelex-agent --version`
3. If neither works, guide install: `pip install pipelex` or `uv add pipelex`

Use whichever method works for all subsequent commands.

### Step 1: Identify the Target

Determine what to run:

| Target | Command |
|--------|---------|
| Bundle file (main pipe) | `pipelex-agent run bundle.plx` |
| Specific pipe in a bundle | `pipelex-agent run bundle.plx --pipe my_pipe` |
| Pipe by code from library | `pipelex-agent run my_pipe` |
| Pipe from a library directory | `pipelex-agent run my_pipe -L ./my_pipes/` |

### Step 2: Prepare Inputs

Get the input schema for the target:

```bash
pipelex-agent inputs bundle.plx
```

**Output:**
```json
{
  "success": true,
  "pipe_code": "process_document",
  "inputs": {
    "document": {
      "concept": "native.Document",
      "content": {"url": "url_value"}
    },
    "context": {
      "concept": "native.Text",
      "content": {"text": "text_value"}
    }
  }
}
```

Fill in the `content` fields with actual values. For complex inputs, use the /synthesize-inputs skill.

### Step 3: Choose Run Mode

| Mode | Command | Use When |
|------|---------|----------|
| **Dry run + mock inputs** | `pipelex-agent run bundle.plx --dry-run --mock-inputs` | Quick structural validation, no real data needed |
| **Dry run with real inputs** | `pipelex-agent run bundle.plx --dry-run --inputs data.json` | Validate input shapes without making API calls |
| **Full run from file** | `pipelex-agent run bundle.plx --inputs data.json` | Production execution with inputs from a file |
| **Full run inline** | `pipelex-agent run bundle.plx --inputs '{"theme": ...}'` | Quick execution without creating an input file |
| **Full run + graph** | `pipelex-agent run bundle.plx --inputs data.json --graph` | Execute and generate execution graph HTML visualizations |

**Cross-domain runs** — when the bundle references pipes from other bundles:
```bash
pipelex-agent run bundle.plx --inputs data.json -L ./shared_pipes/
```

### Inline JSON for Inputs

The `--inputs` flag accepts both file paths and inline JSON. The CLI auto-detects: if the value starts with `{`, it is parsed as JSON directly. This is the fastest path — no file creation needed for simple inputs.

```bash
# Inline JSON
pipelex-agent run bundle.plx --inputs '{"theme": {"concept": "native.Text", "content": {"text": "nature"}}}'

# File path
pipelex-agent run bundle.plx --inputs pipelex-wip/inputs/data.json
```

### Step 4: Interpret Output

**Success output:**
```json
{
  "success": true,
  "pipe_code": "process_document",
  "dry_run": false,
  "main_stuff": {
    "json": { ... },
    "markdown": "...",
    "html": "..."
  },
  "working_memory": { ... }
}
```

Key fields:
- `main_stuff.json` — the pipeline's final output as structured JSON (best for programmatic use)
- `main_stuff.markdown` — human-readable markdown rendering of the output
- `main_stuff.html` — HTML rendering of the output
- `working_memory` — full state of all intermediate variables (useful for debugging)

### Step 5: Handle Errors

**Error output:**
```json
{
  "error": true,
  "error_type": "PipelineExecutionError",
  "message": "Pipeline failed at pipe 'analyze_document'",
  "pipe_code": "analyze_document",
  "pipe_stack": ["process_all", "analyze_document"]
}
```

| Error Type | Recovery |
|------------|----------|
| `ValidateBundleError` | Fix the .plx file — use /fix skill, check `validation_errors` array |
| `PipeOperatorModelChoiceError` | Run `pipelex-agent doctor` — model preset doesn't resolve |
| `PipeOperatorModelAvailabilityError` | Run `pipelex-agent doctor` — API key or service issue |
| `PipelineExecutionError` | Check `pipe_code` and `pipe_stack` for which pipe failed |
| `FileNotFoundError` | Check that the bundle file and input file paths are correct |
| `JSONDecodeError` | Fix the JSON syntax in your inline inputs or input file |
| `ArgumentError` | Check command flags — e.g., `--mock-inputs` requires `--dry-run` |

For model/config issues, always try `pipelex-agent doctor` first.

### Execution Graphs

Add `--graph` to generate visual execution graphs alongside the run output:

```bash
pipelex-agent run bundle.plx --inputs data.json --graph
```

When `--graph` is set, the success JSON includes a `graph_files` field with paths to the generated files:

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

To re-render an existing `graphspec.json` later (e.g., with different format options):

```bash
pipelex-agent graph graphspec.json
pipelex-agent graph graphspec.json --format mermaidflow -o ./output/
```

## Reference

- [Pipelex Agent Guide](../shared/pipelex-agent-guide.md) for CLI philosophy and error type reference
- [Pipelex Language Reference](../shared/pipelex-reference.md) for .plx syntax documentation
