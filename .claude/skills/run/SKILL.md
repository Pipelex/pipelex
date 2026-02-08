---
name: run
description: Run Pipelex workflows and interpret results. Use when user says "run this pipeline", "execute the workflow", "test this .plx file", "try it out", "see the output", "dry run", or wants to execute any Pipelex pipeline and see its output.
---

# Run Pipelex Workflow

Execute Pipelex pipelines and interpret their JSON output.

## Workflow

**Prerequisite**: See [CLI Prerequisites](../shared/prerequisites.md)

### Step 1: Identify the Target

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

For all error types and recovery strategies, see [Error Handling Reference](../shared/error-handling.md).

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

To re-render an existing `graphspec.json` later:

```bash
pipelex-agent graph graphspec.json
pipelex-agent graph graphspec.json --format mermaidflow -o ./output/
```

## Reference

- [CLI Prerequisites](../shared/prerequisites.md) — read at skill start to check CLI availability
- [Error Handling](../shared/error-handling.md) — read when CLI returns an error to determine recovery
- [Pipelex Agent Guide](../shared/pipelex-agent-guide.md) — read for CLI command syntax or output format details
- [Pipelex Language Reference](../shared/pipelex-reference.md) — read for .plx syntax documentation
