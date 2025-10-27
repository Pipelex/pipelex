# Pipeline Creation using the Pipe Builder

Pipelex provides powerful tools to automatically generate complete, working pipelines from natural language requirements. This feature leverages AI to translate your ideas into fully functional pipeline code, dramatically speeding up development.

!!! tip "Pipe Builder Requirements"
    For now, the pipe builder requires access to **Claude 4.5 Sonnet**, either through Pipelex Inference, or using your own key through Anthropic, Amazon Bedrock or BlackboxAI. Don't hesitate to join our [Discord](https://go.pipelex.com/discord) to get a key or see [Configure AI Providers](../setup/configure-ai-providers.md) for details. Otherwise, you can also create the workflows yourself, following our [documentation guide](kick-off-a-pipelex-workflow-project.md).

## Overview

The pipeline creation system can generate pipelines in different modes depending on your needs - from quick one-shot generation to validated, production-ready pipelines that have been automatically tested and fixed.

## Build Pipe

Generate a validated pipeline with automatic fixing of deterministic issues:

```bash
pipelex build pipe "BRIEF IN NATURAL LANGUAGE" [OPTIONS]
```

This command runs a validation/fix loop to ensure the generated pipeline is correct and runnable. It automatically detects and corrects common issues.

**Example:**

```bash
pipelex build pipe "Take a photo as input, and render the opposite of the photo" \
  -o results/photo_inverter.plx
```

**Options:**

- `--output, -o`: Output path for generated PLX file
- `--no-output`: Skip saving the pipeline to file

## Quick Start Example

The simplest way to create a pipeline is to use the `build pipe` command with a clear description:

```bash
pipelex build pipe "Given an expense report, apply company rules and validate compliance"
```

This will:

1. Analyze your requirements
2. Generate a complete pipeline with appropriate concepts and pipes
3. Validate the pipeline for correctness
4. Fix any deterministic issues automatically
5. Save the working pipeline

## Best Practices

When creating pipelines with natural language:

**Be Specific About Inputs and Outputs:**

- ✅ Good: "Take a PDF invoice as input and extract the total amount, vendor name, and date"
- ❌ Vague: "Process invoices"

**Describe the Transformation:**

- ✅ Good: "Analyze sentiment of customer reviews and categorize as positive, negative, or neutral"
- ❌ Vague: "Do something with reviews"

**Mention Data Types When Relevant:**

- ✅ Good: "Extract text from a PDF, then summarize it into 3 bullet points"
- ❌ Unclear: "Summarize documents"

## What Gets Generated

When you run a build command, Pipelex automatically creates:

- **Domain definition**: The namespace for your pipeline
- **Concepts**: Structured data types for inputs and outputs
- **Pipes**: The processing steps and LLM operations
- **Python structures**: When structured output is needed (saved alongside the `.plx` file with `_struct.py` suffix)

All generated pipelines follow Pipelex best practices and conventions automatically.

## Next Steps

After generating your pipeline:

1. **Review the generated `.plx` file** to understand the structure
2. **Test the pipeline** using the generated example code
3. **Iterate if needed** by modifying the natural language description and regenerating
4. **Customize** the pipeline by editing the `.plx` file directly for fine-tuning

