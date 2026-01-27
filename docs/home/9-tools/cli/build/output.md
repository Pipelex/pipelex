# Build Output

Generate example output JSON for a pipe, showing the expected output structure based on the pipe's output concept type.

## Usage

```bash
pipelex build output <TARGET> [OPTIONS]
```

**Arguments:**

- `TARGET` - Either a pipe code or a bundle file path (`.plx`) - auto-detected

**Options:**

- `--pipe` - Pipe code to use (can be omitted if you specify a bundle that declares a `main_pipe`)
- `--library-dir`, `-L` - Directory to search for pipe definitions. Can be specified multiple times.
- `--output`, `-o` - Path to save the generated JSON file (defaults to bundle's directory if bundle provided, otherwise `results/`)

## Examples

**Generate output from a bundle (uses main_pipe):**

```bash
pipelex build output my_bundle.plx
```

**Specify which pipe to use from a bundle:**

```bash
pipelex build output my_bundle.plx --pipe my_pipe
```

**Generate output for a pipe using a library directory:**

```bash
pipelex build output my_domain.my_pipe -L ./my_library/
```

**Custom output path:**

```bash
pipelex build output my_bundle.plx --output expected_output.json
```

## Output Format

The generated JSON file shows the content structure of the pipe's output, with example values based on the output concept type:

```json
{
  "title": "title_value",
  "key_points": "key_points_value"
}
```

### Native Concepts

For native concepts like `Text`, `Image`, or `Document`:

```json
{
  "text": "text_value"
}
```

### Multiplicity Support

When a pipe's output has multiplicity (returns multiple items), the content is a list:

```json
[
  {
    "name": "name_value",
    "description": "description_value"
  }
]
```

## Use Cases

- **Understanding pipe outputs** - Quickly see what structure a pipe returns
- **API integration** - Know the exact structure to expect when calling pipes programmatically
- **Type definitions** - Use as reference for defining types in your application code
- **Testing** - Create expected output templates for validation

## Related Documentation

- [Build Inputs](inputs.md) - Generate example input JSON for a pipe
- [Build Runner](runner.md) - Generate Python code to run a pipe
- [Pipe Output](../../../6-build-reliable-ai-workflows/pipes/pipe-output.md) - Learn about pipe outputs
