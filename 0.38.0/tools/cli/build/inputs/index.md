# Build Inputs

Generate an example inputs template for a pipe, showing the expected input structure based on the pipe's input types. The template is emitted as JSON by default, or as TOML with `--format toml`.

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

## Output Format

The generated file contains all inputs required by the pipe, with example values based on each input's concept type. Both formats carry the same structure — [`pipelex run`](../run.md#input-file-formats) accepts either.

**JSON (`--format json`, default):**

```json
{
  "text_input": {
    "concept": "native.Text",
    "content": {
      "text": "text_value"
    }
  },
  "document_input": {
    "concept": "native.Document",
    "content": {
      "url": "url_value"
    }
  }
}
```

**TOML (`--format toml`):**

```toml
[text_input]
concept = "native.Text"

[text_input.content]
text = "text_value"

[document_input]
concept = "native.Document"

[document_input.content]
url = "url_value"
```

### Multiplicity Support

When an input has multiplicity (accepts multiple items), the content is wrapped in a list:

```json
{
  "documents": {
    "concept": "native.Document",
    "content": [
      {
        "url": "url_value"
      }
    ]
  }
}
```

In TOML, the same list of items uses the array-of-tables syntax:

```toml
[documents]
concept = "native.Document"

[[documents.content]]
url = "url_value"
```

## Use Cases

- **Understanding pipe requirements** - Quickly see what inputs a pipe expects
- **Creating input templates** - Generate a starting point for your input JSON files
- **API integration** - Know the exact structure to send when calling pipes programmatically

## Related Documentation

- [Build Output](output.md) - Generate example output JSON for a pipe
- [Build Runner](runner.md) - Generate Python code to run a pipe
- [Provide Inputs](../../../building-methods/pipes/provide-inputs.md) - Learn about input formats
