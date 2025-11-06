# Pipe Builder

!!! warning "Beta Feature"
    The Pipe Builder is currently in beta and progressing fast. Expect frequent improvements and changes.

The Pipe Builder is an AI-powered tool that generates Pipelex pipelines from natural language descriptions. It helps you quickly prototype pipelines by describing what you want to achieve, and the builder translates your requirements into working `.plx` files.

## Overview

The Pipe Builder uses AI to:

- Understand your pipeline requirements from a brief description
- Generate domain concepts, pipe specifications, and complete pipeline structure
- Validate the generated pipeline for common errors
- Automatically fix certain deterministic issues

## Usage

Generate a pipeline with one validation/fix loop that automatically corrects deterministic issues:

```bash
pipelex build pipe "Brief description of what the pipeline should do" -o path/to/output.plx
```

**Example:**

```bash
pipelex build pipe "Given an expense report, apply company rules" -o results/expense_pipeline.plx
```

This command:

1. Generates a complete pipeline from your brief
2. Validates the pipeline structure
3. Attempts to automatically fix common errors
4. Saves the final pipeline to the specified path

## Options

The build command supports the following options:

- `--output`, `-o`: Path to save the generated file
- `--no-output`: Skip saving the file (useful for testing)

## How It Works

The Pipe Builder follows this process:

1. **Analysis**: Analyzes your brief to understand the domain and requirements
2. **Concept Generation**: Creates appropriate domain concepts for your workflow
3. **Pipe Generation**: Generates pipe operators and controllers to implement the logic
4. **Validation**: Validates the generated pipeline structure
5. **Automatic Fixes**: Fixes common errors like missing inputs or incorrect pipe connections

## Generate Runner Code

After creating a pipeline, you can generate Python code to run it with the `build runner` command. This creates a ready-to-use Python script with all necessary imports and example input values.

### Usage

```bash
pipelex build runner [TARGET] [OPTIONS]
```

**Arguments:**

- `TARGET` - Either a pipe code or a bundle file path, auto-detected according to presence of the .plx file extension

**Options:**

- `--pipe` - Pipe code to use (alternative to positional argument)
- `--bundle` - Bundle file path (alternative to positional argument)
- `--output`, `-o` - Path to save the generated Python file (defaults to `results/run_{pipe_code}.py`)

### Examples

**Generate runner for a pipe:**

```bash
pipelex build runner my_pipe
```

**Generate runner from a bundle file:**

```bash
pipelex build runner my_bundle.plx
```

**Specify a pipe from a bundle:**

```bash
pipelex build runner --bundle my_bundle.plx --pipe my_pipe
```

**Custom output path:**

```bash
pipelex build runner my_pipe --output custom_runner.py
```

### What Gets Generated

The generated Python file includes:

1. **All necessary imports** - Imports for Pipelex execution, content types, and any custom structures
2. **Input memory setup** - Example input values based on the pipe's input types
3. **Pipeline execution** - Async function that executes the pipeline
4. **Output handling** - Code to extract and display the results
5. **Main execution block** - Pipelex initialization and asyncio setup

### Input Type Handling

- **Native concepts** (Text, Image, PDF, etc.) - Automatically generates appropriate content objects
- **Custom concepts** - Recursively generates the structure with example values
- **Structured content** - Creates example data matching the concept's fields

### Next Steps

After generating the runner file:

1. Open the generated Python file
2. Review and customize the example input values
3. Run the script: `python results/run_{pipe_code}.py`
4. Iterate and adjust as needed

For the complete CLI reference, see [CLI Commands](cli.md).

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

## Current Limitations

The Pipe Builder is in active development and currently:

- Can automatically fix input/output connection errors
- May require manual adjustments for complex conditional logic or custom functions
- Validation focuses on structural correctness, not business logic

## Tips for Best Results

- You can be specific in your brief about inputs, outputs, data formats, or structures if you know what you need
- If you're uncertain about the details, let the AI figure it out and see what it generates
- Include any domain-specific requirements you're aware of upfront

## Iterating on Generated Pipelines

After generating a pipeline, you can continue refining it using any Software Engineering (SWE) agent. The generated `.plx` file can be iteratively improved through natural language instructions.

Pipelex provides specialized agent rules (`write_pipelex.md` and `run_pipelex.md`) that guide AI assistants in working with pipelines. You can install these rules for your preferred AI coding assistant using:

```bash
pipelex kit rules
```

This command installs the rules for:

- **Cursor**
- **Claude Code**
- **OpenAI Codex**
- **GitHub Copilot**
- **Windsurf**
- **Blackbox AI**

These rules help AI assistants understand Pipelex syntax, best practices, and common patterns, making it easier to iterate and refine your generated pipelines.

## Next Steps

After generating a pipeline:

1. Review the generated `.plx` file
2. Test it with sample inputs: `pipelex run <pipe_code> --input-memory-from-json input.json`
3. Continue iterating using your preferred SWE agent with the Pipelex agent rules
4. Adjust concepts or pipe configurations as needed

For more information on pipeline structure and customization, see:

- [Design and Run Pipelines](../../home/6-build-reliable-ai-workflows/pipes/index.md)
- [Pipe Operators](../../home/6-build-reliable-ai-workflows/pipes/pipe-operators/index.md)
- [Pipe Controllers](../../home/6-build-reliable-ai-workflows/pipes/pipe-controllers/index.md)

