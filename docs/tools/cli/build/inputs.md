---
description: "Generate an example inputs template (JSON or TOML) for any pipe — see the expected input structure based on the pipe's declared input types in .mthds files."
---

# Build Inputs

Generate an example inputs template for a pipe, showing the expected input structure based on the pipe's input types. The template is emitted as JSON by default, or as TOML with `--format toml`.

By default the template is the **light** shape — the values themselves, matching the pipe's declared signature (a bare string for a `Text`-refining input, a bare number for a `Number`-refining one, an object for a structured concept). This is exactly what [`pipelex run`](../run.md) accepts, so a template you generate and fill in runs as-is. Pass `--explicit` to emit the ceremonial `{concept, content}` envelope form instead. See [Providing Inputs](../../../building-methods/pipes/provide-inputs.md) for the full model.

## Usage

### By pipe code

```bash
pipelex build inputs pipe <PIPE_CODE> [OPTIONS]
```

**Arguments:**

- `PIPE_CODE` - The pipe code (e.g. `my_domain.my_pipe`)

**Options:**

- `--library-dir`, `-L` - Directory to search for pipe definitions. Can be specified multiple times.
- `--output`, `-o` - Path to save the generated inputs file (defaults to `results/`, filename `inputs.json` or `inputs.toml` depending on `--format`)
- `--format` - Template format: `json` (default) or `toml`
- `--explicit` - Emit the ceremonial `{concept, content}` envelope form instead of the light values

### From a bundle

```bash
pipelex build inputs bundle <PATH> [OPTIONS]
```

**Arguments:**

- `PATH` - Path to a `.mthds` bundle file or a pipeline directory

**Options:**

- `--pipe` - Pipe code to use (can be omitted if the bundle declares a `main_pipe`)
- `--library-dir`, `-L` - Directory to search for pipe definitions. Can be specified multiple times.
- `--output`, `-o` - Path to save the generated inputs file (defaults to the bundle's directory, filename `inputs.json` or `inputs.toml` depending on `--format`)
- `--format` - Template format: `json` (default) or `toml`
- `--explicit` - Emit the ceremonial `{concept, content}` envelope form instead of the light values

### From an installed method

```bash
pipelex build inputs method <NAME> [OPTIONS]
```

**Arguments:**

- `NAME` - Name of the installed method

**Options:**

- `--pipe` - Pipe code (overrides method's `main_pipe`)
- `--library-dir`, `-L` - Directory to search for pipe definitions. Can be specified multiple times.
- `--output`, `-o` - Path to save the generated inputs file (filename `inputs.json` or `inputs.toml` depending on `--format`)
- `--format` - Template format: `json` (default) or `toml`
- `--explicit` - Emit the ceremonial `{concept, content}` envelope form instead of the light values

## Examples

**Generate inputs for a pipe by code:**

```bash
pipelex build inputs pipe my_domain.my_pipe
```

**Generate inputs from a bundle (uses main_pipe):**

```bash
pipelex build inputs bundle my_bundle.mthds
```

**Generate inputs from a pipeline directory:**

```bash
pipelex build inputs bundle pipeline_01/
```

**Specify which pipe to use from a bundle:**

```bash
pipelex build inputs bundle my_bundle.mthds --pipe my_pipe
```

**Generate inputs for a pipe using a library directory:**

```bash
pipelex build inputs pipe my_domain.my_pipe -L ./my_library/
```

**Custom output path:**

```bash
pipelex build inputs bundle my_bundle.mthds --output custom_inputs.json
```

**Generate a TOML template instead of JSON:**

```bash
pipelex build inputs bundle my_bundle.mthds --format toml
```

When `--format toml` is selected and no explicit `--output` is given, the default filename becomes `inputs.toml` (instead of `inputs.json`).

**Generate the explicit envelope form instead of the light values:**

```bash
pipelex build inputs bundle my_bundle.mthds --explicit
```

## Output Format

The generated file contains all inputs required by the pipe, with example values based on each input's concept type. Both formats carry the same structure — [`pipelex run`](../run.md#input-file-formats) accepts either.

### Light form (default)

The default template is the light shape: each value is what the pipe's signature expects, with no `{concept, content}` envelope. For a pipe declaring a `Text`-refining `question`, a `Number`-refining `priority`, a structured `invoice`, and a `Text`-refining list `tags = "Tag[]"`:

**JSON (`--format json`, default):**

```json
{
  "question": "text_value",
  "priority": 1,
  "invoice": {
    "invoice_number": "invoice_number_value",
    "amount": 0.0
  },
  "tags": ["text_value"]
}
```

**TOML (`--format toml`):** the light TOML template uses inline tables so top-level scalars and structured values coexist, and carries the declared concept for each key as a comment (a declared-multiple input is tagged `[]`):

```toml
# concept: my_domain.Question
question = "text_value"
# concept: my_domain.Priority
priority = 1
# concept: my_domain.Invoice
invoice = {invoice_number = "invoice_number_value", amount = 0.0}
# concept: my_domain.Tag[]
tags = ["text_value"]
```

### Explicit envelope form (`--explicit`)

Pass `--explicit` to reproduce the ceremonial `{concept, content}` envelope for every input — useful when you want the concept written out inline (JSON has no comments), or when authoring an input meant for the explicit escape hatch:

```json
{
  "question": {
    "concept": "my_domain.Question",
    "content": {"text": "text_value"}
  },
  "priority": {
    "concept": "my_domain.Priority",
    "content": {"number": 1}
  },
  "invoice": {
    "concept": "my_domain.Invoice",
    "content": {"invoice_number": "invoice_number_value", "amount": 0.0}
  },
  "tags": {
    "concept": "my_domain.Tag",
    "content": [{"text": "text_value"}]
  }
}
```

In TOML, `--explicit` renders the all-tables layout; a multiple input keeps a single `[key]` envelope whose `content` is an array-of-tables (`[[key.content]]`):

```toml
[question]
concept = "my_domain.Question"

[question.content]
text = "text_value"

# ... priority and invoice tables omitted ...

[tags]
concept = "my_domain.Tag"

[[tags.content]]
text = "text_value"
```

### Multiplicity

When an input is declared multiple (`Tag[]`), the light form wraps the example value in a list (`["text_value"]`); the explicit form keeps a single `{concept, content}` envelope whose `content` is the list (not an array of separate envelopes). Either way, [`pipelex run`](../run.md) accepts the filled-in template.

## Use Cases

- **Understanding pipe requirements** - Quickly see what inputs a pipe expects
- **Creating input templates** - Generate a starting point for your input JSON files
- **API integration** - Know the exact structure to send when calling pipes programmatically

## Related Documentation

- [Build Output](output.md) - Generate example output JSON for a pipe
- [Build Runner](runner.md) - Generate Python code to run a pipe
- [Provide Inputs](../../../building-methods/pipes/provide-inputs.md) - Learn about input formats
