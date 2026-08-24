# Build Output

Generate output representation for a pipe, showing the expected output structure based on the pipe's output concept type. Supports multiple output formats including JSON Schema for TypeScript/Zod integration.

## Usage

### By pipe code

```bash
pipelex build output pipe <PIPE_CODE> [OPTIONS]
```

**Arguments:**

- `PIPE_CODE` - The pipe code (e.g. `my_domain.my_pipe`)

**Options:**

- `--library-dir`, `-L` - Directory to search for pipe definitions. Can be specified multiple times.
- `--output`, `-o` - Path to save the generated file (defaults to `results/`)
- `--format`, `-f` - Output format (default: `json`):
    - `json` - JSON object with example placeholder data
    - `python` - Python class instantiation code
    - `schema` - JSON Schema definition, ideal for generating TypeScript interfaces or Zod schemas

### From a bundle

```bash
pipelex build output bundle <PATH> [OPTIONS]
```

**Arguments:**

- `PATH` - Path to a `.mthds` bundle file or a pipeline directory

**Options:**

- `--pipe` - Pipe code to use (can be omitted if the bundle declares a `main_pipe`)
- `--library-dir`, `-L` - Directory to search for pipe definitions. Can be specified multiple times.
- `--output`, `-o` - Path to save the generated file (defaults to bundle's directory)
- `--format`, `-f` - Output format (default: `json`): `json`, `python`, or `schema`

### From an installed method

```bash
pipelex build output method <NAME> [OPTIONS]
```

**Arguments:**

- `NAME` - Name of the installed method

**Options:**

- `--pipe` - Pipe code (overrides method's `main_pipe`)
- `--library-dir`, `-L` - Directory to search for pipe definitions. Can be specified multiple times.
- `--output`, `-o` - Path to save the generated file
- `--format`, `-f` - Output format (default: `json`): `json`, `python`, or `schema`

## Examples

**Generate output for a pipe by code:**

```bash
pipelex build output pipe my_domain.my_pipe
```

**Generate output from a bundle (uses main_pipe):**

```bash
pipelex build output bundle my_bundle.mthds
```

**Generate JSON Schema from a bundle for TypeScript/Zod integration:**

```bash
pipelex build output bundle my_bundle.mthds --format schema
```

**Generate output from a pipeline directory:**

```bash
pipelex build output bundle pipeline_01/
```

**Specify which pipe to use from a bundle:**

```bash
pipelex build output bundle my_bundle.mthds --pipe my_pipe
```

**Generate output for a pipe using a library directory:**

```bash
pipelex build output pipe my_domain.my_pipe -L ./my_library/
```

**Custom output path:**

```bash
pipelex build output bundle my_bundle.mthds --output expected_output.json
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
{"concept": "my_domain.MyOutputConcept", "content": 'MyOutputConcept(title="title_value", key_points="key_points_value")'}
```

### Schema Format

The schema format generates JSON Schema definitions, ideal for generating TypeScript interfaces or Zod schemas. The schema's top-level `title` is the concept ref, and its top-level `description` is the concept's authored description:

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
    "title": "my_domain.MyOutputConcept",
    "description": "The concept's description, as authored in the bundle"
  }
}
```

**Array outputs** are represented as JSON Schema arrays, with the concept identity kept on `items`. A fixed count (e.g., `MyType[5]`) additionally emits `minItems`/`maxItems` bounds; a variable-length list (`MyType[]`) carries no bounds:

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
      "title": "my_domain.Item",
      "description": "An item of the collection"
    },
    "minItems": 5,
    "maxItems": 5
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
- [Pipe Output](../../../building-methods/pipes/pipe-output.md) - Learn about pipe outputs
