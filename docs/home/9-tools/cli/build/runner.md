# Build Runner

Generate Python code to run a pipe with all necessary imports and example inputs.

## Usage

```bash
pipelex build runner <TARGET> [OPTIONS]
```

**Arguments:**

- `TARGET` - Bundle file path (`.mthds`)

**Options:**

- `--pipe` - Pipe code to use (optional if the `.mthds` declares a `main_pipe`)
- `--output`, `-o` - Path to save the generated Python file (defaults to target's directory)
- `--library-dirs`, `-L` - Directories to search for pipe definitions. Can be specified multiple times.

## Examples

**Generate runner from a bundle (uses main_pipe):**

```bash
pipelex build runner my_bundle.mthds
```

**Specify which pipe to use from a bundle:**

```bash
pipelex build runner my_bundle.mthds --pipe my_pipe
```

**With additional library directories:**

```bash
pipelex build runner my_bundle.mthds -L ./shared_pipes/ -L ./common/
```

**Custom output path:**

```bash
pipelex build runner my_bundle.mthds --output custom_runner.py
```

## What Gets Generated

The generated Python file includes:

1. **All necessary imports** - Imports for Pipelex execution, content types, and any custom structures
2. **Generated Pydantic structures** - Models for your concepts (also generated separately)
3. **Input memory setup** - Example input values based on the pipe's input types
4. **Pipeline execution** - Async function that executes the pipeline
5. **Output handling** - Code to extract and display the results
6. **Main execution block** - Pipelex initialization and asyncio setup

## Input Type Handling

- **Native concepts** (Text, Image, PDF, etc.) - Automatically generates appropriate content objects
- **Custom concepts** - Recursively generates the structure with example values
- **Structured content** - Creates example data matching the concept's fields

## Using the Generated Runner

After generating the runner file:

1. Open the generated Python file
2. Review and customize the example input values
3. Run the script: `python results/run_{pipe_code}.py`
4. Iterate and adjust as needed

## Related Documentation

- [Build Pipe](pipe.md) - Generate pipelines from natural language
- [Build Structures](structures.md) - Generate Pydantic models separately
- [Build Inputs](inputs.md) - Generate example input JSON for a pipe
- [Build Output](output.md) - Generate example output JSON for a pipe
- [Run Command](../run.md) - Run pipes directly from CLI

