# Build Inputs

Generate example input JSON for a pipe, showing the expected input structure based on the pipe's input types.

## Usage

### By pipe code

```bash
pipelex build inputs pipe <PIPE_CODE> [OPTIONS]
```

**Arguments:**

- `PIPE_CODE` - The pipe code (e.g. `my_domain.my_pipe`)

**Options:**

- `--library-dir`, `-L` - Directory to search for pipe definitions. Can be specified multiple times.
- `--output`, `-o` - Path to save the generated JSON file (defaults to `results/`)

### From a bundle

```bash
pipelex build inputs bundle <PATH> [OPTIONS]
```

**Arguments:**

- `PATH` - Path to a `.mthds` bundle file or a pipeline directory

**Options:**

- `--pipe` - Pipe code to use (can be omitted if the bundle declares a `main_pipe`)
- `--library-dir`, `-L` - Directory to search for pipe definitions. Can be specified multiple times.
- `--output`, `-o` - Path to save the generated JSON file (defaults to bundle's directory)

### From an installed method

```bash
pipelex build inputs method <NAME> [OPTIONS]
```

**Arguments:**

- `NAME` - Name of the installed method

**Options:**

- `--pipe` - Pipe code (overrides method's `main_pipe`)
- `--library-dir`, `-L` - Directory to search for pipe definitions. Can be specified multiple times.
- `--output`, `-o` - Path to save the generated JSON file

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

## Output Format

The generated JSON file contains all inputs required by the pipe, with example values based on each input's concept type:

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

## Use Cases

- **Understanding pipe requirements** - Quickly see what inputs a pipe expects
- **Creating input templates** - Generate a starting point for your input JSON files
- **API integration** - Know the exact structure to send when calling pipes programmatically

## Related Documentation

- [Build Output](output.md) - Generate example output JSON for a pipe
- [Build Runner](runner.md) - Generate Python code to run a pipe
- [Provide Inputs](../../../6-build-reliable-ai-workflows/pipes/provide-inputs.md) - Learn about input formats
