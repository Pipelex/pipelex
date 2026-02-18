# Build Pipe

!!! warning "Beta Feature"
    The Pipe Builder is currently in beta and progressing fast. Expect frequent improvements and changes.

!!! tip "Built with Pipelex"
    The Pipe Builder is itself a Pipelex pipeline! This showcases the power of Pipelex: a tool that builds pipelines... using a pipeline.

The Pipe Builder is an AI-powered tool that generates Pipelex pipelines from natural language descriptions. Describe what you want to achieve, and the builder translates your requirements into a working `.mthds` file.

!!! info "Deep Dive"
    Want to understand how the Pipe Builder works under the hood? See [Pipe Builder Deep Dive](../../pipe-builder.md) for the full explanation of its multi-step generation process.

## Usage

```bash
pipelex build pipe <PROMPT> [OPTIONS]
```

**Arguments:**

- `PROMPT` - Description of what the pipeline should do (required)

**Options:**

- `--output-name`, `-o` - Base name for the generated file or directory (without extension)
- `--output-dir` - Directory where files will be generated
- `--no-output` - Skip saving the pipeline to file (useful for testing)
- `--no-extras` - Skip generating `inputs.json` and `runner.py`, only generate the MTHDS file
- `--builder-pipe` - Builder pipe to use for generating the pipeline (default: `pipe_builder`)
- `--graph` / `--no-graph` - Generate execution graphs for both build process and built pipeline
- `--graph-full-data` / `--graph-no-data` - Include or exclude full serialized data in graphs (requires `--graph`)

## Output

The resulting pipeline will be saved in a folder (e.g., `pipeline_01/`) containing:

| File | Description |
|------|-------------|
| `bundle.mthds` | The pipeline definition |
| `inputs.json` | Template for pipeline inputs |
| `run_{pipe_code}.py` | Python script to run the pipeline |
| `structures/` | Generated Pydantic models for your concepts |
| `bundle_view.html` | HTML visualization of the build process and plan |
| `bundle_view.svg` | SVG visualization of the build process and plan |
| `__init__.py` | Python package init file |

The HTML and SVG files provide a visual representation of the resulting method.

## Examples

**Basic usage:**

```bash
pipelex build pipe "Given an expense report, apply company rules"
```

**Custom output name:**

```bash
pipelex build pipe "Extract data from invoices" -o invoice_extractor
```

**Custom output directory:**

```bash
pipelex build pipe "Analyze customer feedback" --output-dir ./pipelines/
```

**Generate only the MTHDS file (no extras):**

```bash
pipelex build pipe "Summarize documents" --no-extras
```

## Example Use Cases

**Document Processing:**

```bash
pipelex build pipe "Take a CV in a PDF file and a Job offer text, and analyze if they match"
```

**Data Transformation:**

```bash
pipelex build pipe "Extract structured data from invoice images"
```

**Multi-step Methods:**

```bash
pipelex build pipe "Given an RFP PDF, build a compliance matrix"
```

## Tips for Best Results

- You can be specific in your brief about inputs, outputs, data formats, or structures if you know what you need
- If you're uncertain about the details, let the AI figure it out and see what it generates
- Include any domain-specific requirements you're aware of upfront

## Current Limitations

The Pipe Builder is in active development and currently:

- Can automatically fix input/output connection errors
- May require manual adjustments for complex conditional logic or custom functions
- Validation focuses on structural correctness, not business logic

## Next Steps

After generating your pipeline:

1. **Validate it**: `pipelex validate your_pipe.mthds` - See [Validate Commands](../validate.md)
2. **Run it**: `pipelex run your_pipe.mthds` - See [Run Command](../run.md)
3. **Generate a runner**: `pipelex build runner your_pipe.mthds` - See [Build Runner](runner.md)
4. **Generate structures**: `pipelex build structures ./` - See [Build Structures](structures.md)
5. **Generate input template**: `pipelex build inputs your_pipe.mthds` - See [Build Inputs](inputs.md)
6. **View output structure**: `pipelex build output your_pipe.mthds` - See [Build Output](output.md)

## Related Documentation

- [Pipe Builder Deep Dive](../../pipe-builder.md) - How the builder works under the hood
- [Design and Run Pipelines](../../../6-build-reliable-ai-workflows/pipes/index.md)
- [Build Inputs](inputs.md) - Generate example input JSON
- [Build Output](output.md) - Generate example output JSON
- [Pipe Operators](../../../6-build-reliable-ai-workflows/pipes/pipe-operators/index.md)
- [Pipe Controllers](../../../6-build-reliable-ai-workflows/pipes/pipe-controllers/index.md)

