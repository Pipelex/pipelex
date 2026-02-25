# Run Command

Execute a pipeline with optional inputs and outputs.

## Run a Pipeline

```bash
pipelex run [TARGET] [OPTIONS]
```

Executes a pipeline, either from a standalone bundle (.mthds) file or from your project's pipe library.

**Arguments:**

- `TARGET` - Either a pipe code or a bundle file path, auto-detected according to presence of the .mthds file extension

**Options:**

- `--pipe` - Pipe code to run (alternative to positional argument)
- `--bundle` - Bundle file path (alternative to positional argument)
- `--inputs`, `-i` - Path to JSON file containing inputs
- `--output`, `-o` - Path to save output JSON (defaults to `results/run_{pipe_code}.json`)
- `--no-output` - Skip saving output to file
- `--no-pretty-print` - Skip pretty printing the main output
- `--library-dir`, `-L` - Directory to search for pipe definitions (.mthds files). Can be specified multiple times.

**Examples:**

```bash
# Run a pipe by code
pipelex run hello_world

# Run with inputs from JSON file
pipelex run write_weekly_report --inputs weekly_report_data.json

# Run a bundle file (uses its main_pipe)
pipelex run my_bundle.mthds

# Run a specific pipe from a bundle
pipelex run my_bundle.mthds --pipe extract_invoice

# Run with explicit options
pipelex run --pipe hello_world --output my_output.json

# Run without saving or pretty printing
pipelex run my_pipe --no-output --no-pretty-print

# Run with custom library directories
pipelex run my_pipe -L ./pipelines -L ./shared_pipes
```

## Input JSON Format

The input JSON file should contain a dictionary where keys are input variable names:

```json
{
  "input_variable": "simple string value",
  "another_input": {
    "concept": "domain_code.ConceptName",
    "content": { "field": "value" }
  }
}
```

## Output Format

The output JSON contains the complete working memory after pipeline execution, including all intermediate results and the final output.

## Related Documentation

- [Executing Pipelines](../../6-build-reliable-ai-workflows/pipes/executing-pipelines.md)
- [Providing Inputs to Pipelines](../../6-build-reliable-ai-workflows/pipes/provide-inputs.md)
- [Design and Run Pipelines](../../6-build-reliable-ai-workflows/pipes/index.md)

