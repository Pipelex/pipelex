# Build Output

Generate output representation for a pipe, showing the expected output structure based on the pipe's output concept type. Supports multiple output formats including JSON Schema for TypeScript/Zod integration.

## Usage

```bash
pipelex build output <TARGET> [OPTIONS]
```

**Arguments:**

- `TARGET` - Either a pipe code or a bundle file path (`.mthds`) - auto-detected

**Options:**

- `--pipe` - Pipe code to use (can be omitted if you specify a bundle that declares a `main_pipe`)
- `--library-dir`, `-L` - Directory to search for pipe definitions. Can be specified multiple times.
- `--output`, `-o` - Path to save the generated file (defaults to bundle's directory if bundle provided, otherwise `results/`)
- `--format`, `-f` - Output format (default: `json`):
    - `json` - JSON object with example placeholder data
    - `python` - Python class instantiation code
    - `schema` - JSON Schema definition, ideal for generating TypeScript interfaces or Zod schemas

## Examples

**Generate output from a bundle (uses main_pipe):**

```bash
pipelex build output my_bundle.mthds
```

**Generate JSON Schema for TypeScript/Zod integration:**

```bash
pipelex build output my_bundle.mthds --format schema
```

**Specify which pipe to use from a bundle:**

```bash
pipelex build output my_bundle.mthds --pipe my_pipe
```

**Generate output for a pipe using a library directory:**

```bash
pipelex build output my_domain.my_pipe -L ./my_library/
```

**Custom output path:**

```bash
pipelex build output my_bundle.mthds --output expected_output.json
```

## Output Formats

### JSON Format (default)

The JSON format generates example placeholder data showing the output structure:

```json
{
  "concept": "my_domain.MyOutputConcept",
  "content": {
    "title": "title_value",
    "key_points": "key_points_value"
  }
}
```

For native concepts like `Text`, `Image`, or `Document`:

```json
{
  "concept": "native.Text",
  "content": {
    "text": "text_value"
  }
}
```

When a pipe's output has multiplicity (returns multiple items), the content is a list:

```json
{
  "concept": "my_domain.Item",
  "content": [
    {
      "name": "name_value",
      "description": "description_value"
    }
  ]
}
```

### Python Format

The Python format generates class instantiation code:

```python
{
  "concept": "my_domain.MyOutputConcept",
  "content": "MyOutputConcept(title=\"title_value\", key_points=\"key_points_value\")"
}
```

### Schema Format

The schema format generates JSON Schema definitions, ideal for generating TypeScript interfaces or Zod schemas:

```json
{
  "concept": "my_domain.MyOutputConcept",
  "content": {
    "type": "object",
    "properties": {
      "title": { "type": "string", "title": "Title" },
      "key_points": { "type": "string", "title": "Key Points" }
    },
    "required": ["title", "key_points"],
    "title": "MyOutputConcept"
  }
}
```

**Array outputs** (e.g., `MyType[5]`) are properly represented as JSON Schema arrays:

```json
{
  "concept": "my_domain.Item",
  "content": {
    "type": "array",
    "items": {
      "type": "object",
      "properties": {
        "name": { "type": "string", "title": "Name" },
        "description": { "type": "string", "title": "Description" }
      },
      "required": ["name", "description"],
      "title": "Item"
    }
  }
}
```

### `native.Anything` Output

When a pipe's output is `native.Anything` (e.g., a `PipeCondition` with mapped pipes that have different output types), the command shows all possible outputs from the mapped pipes.

For JSON format:

```json
{
  "output_option_1": {
    "concept": "my_domain.Result1",
    "content": { "field1": "field1_value" }
  },
  "output_option_2": {
    "concept": "my_domain.Result2",
    "content": { "field2": "field2_value" }
  }
}
```

For schema format:

```json
{
  "schema_option_1": {
    "concept": "my_domain.Result1",
    "content": {
      "type": "object",
      "properties": { "field1": { "type": "string" } },
      "required": ["field1"]
    }
  },
  "schema_option_2": {
    "concept": "my_domain.Result2",
    "content": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": { "field2": { "type": "string" } },
        "required": ["field2"]
      }
    }
  }
}
```

This helps you understand all possible output structures that the pipe could return depending on execution path.

## Use Cases

- **Understanding pipe outputs** - Quickly see what structure a pipe returns
- **API integration** - Know the exact structure to expect when calling pipes programmatically
- **TypeScript/Zod integration** - Use `--format schema` to generate JSON Schema, then convert to TypeScript interfaces or Zod schemas for type-safe frontend integration
- **Type definitions** - Use as reference for defining types in your application code
- **Testing** - Create expected output templates for validation

## Related Documentation

- [Build Inputs](inputs.md) - Generate example input JSON for a pipe
- [Build Runner](runner.md) - Generate Python code to run a pipe
- [Pipe Output](../../../6-build-reliable-ai-workflows/pipes/pipe-output.md) - Learn about pipe outputs
