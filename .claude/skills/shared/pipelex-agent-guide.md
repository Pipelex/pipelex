# Pipelex Agent Guide

Strategy and reference for agents working with Pipelex programmatically.

## Agent CLI

Agents must use `pipelex-agent` exclusively. It outputs structured JSON (stdout=success, stderr=error with exit code 1).

**Prerequisite**: See [CLI Prerequisites](prerequisites.md)

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

### Error Handling

For all error types, recovery strategies, and error domains, see [Error Handling Reference](error-handling.md).

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
