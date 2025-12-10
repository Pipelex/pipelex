# Build Pipe

!!! warning "Beta Feature"
    The Pipe Builder is currently in beta and progressing fast. Expect frequent improvements and changes.

!!! tip "Built with Pipelex"
    The Pipe Builder is itself a Pipelex pipeline! This showcases the power of Pipelex: a tool that builds pipelines... using a pipeline.

The Pipe Builder is an AI-powered tool that generates Pipelex pipelines from natural language descriptions. Describe what you want to achieve, and the builder translates your requirements into a working `.plx` file.

!!! info "Deep Dive"
    Want to understand how the Pipe Builder works under the hood? See [Pipe Builder Deep Dive](../../pipe-builder.md) for the full explanation of its multi-step generation process.

## Usage

```bash
pipelex build pipe "Brief description of what the pipeline should do"
```

The resulting pipeline will be saved in a folder `pipeline_01/` (with increasing number) containing:

| File | Description |
|------|-------------|
| `bundle.plx` | The pipeline definition |
| `inputs.json` | Template for pipeline inputs |
| `run_{pipe_code}.py` | Python script to run the pipeline |
| `structures/` | Generated Pydantic models for your concepts |
| `bundle_view.html` | HTML visualization of the build process and plan |
| `bundle_view.svg` | SVG visualization of the build process and plan |
| `__init__.py` | Python package init file |

The HTML and SVG files provide a visual representation of what happened during the build: the analysis, the plan the AI took, and the resulting structure.

**Example:**

```bash
pipelex build pipe "Given an expense report, apply company rules" -o results/expense_pipeline.plx
```

## Options

- `--output`, `-o`: Path to save the generated `.plx` file
- `--no-output`: Skip saving the file (useful for testing)

## Example Use Cases

**Document Processing:**

```bash
pipelex build pipe "Take a CV in a PDF file and a Job offer text, and analyze if they match"
```

**Data Transformation:**

```bash
pipelex build pipe "Extract structured data from invoice images"
```

**Multi-step Workflows:**

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

## Iterating on Generated Pipelines

After generating a pipeline, you can continue refining it using any Software Engineering (SWE) agent. The generated `.plx` file can be iteratively improved through natural language instructions.

Pipelex provides specialized agent rules that guide AI assistants in working with pipelines. Install them with:

```bash
pipelex kit rules
```

See [Kit Commands](../kit.md) for details on supported AI assistants.

## Next Steps

After generating your pipeline:

1. **Validate it**: `pipelex validate your_pipe.plx` - See [Validate Commands](../validate.md)
2. **Run it**: `pipelex run your_pipe.plx` - See [Run Command](../run.md)
3. **Generate a runner**: `pipelex build runner your_pipe.plx` - See [Build Runner](runner.md)
4. **Generate structures**: `pipelex build structures ./` - See [Build Structures](structures.md)

## Related Documentation

- [Pipe Builder Deep Dive](../../pipe-builder.md) - How the builder works under the hood
- [Design and Run Pipelines](../../../6-build-reliable-ai-workflows/pipes/index.md)
- [Pipe Operators](../../../6-build-reliable-ai-workflows/pipes/pipe-operators/index.md)
- [Pipe Controllers](../../../6-build-reliable-ai-workflows/pipes/pipe-controllers/index.md)

