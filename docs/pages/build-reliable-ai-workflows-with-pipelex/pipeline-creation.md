# Pipeline Creation

Pipelex provides powerful tools to automatically generate complete, working pipelines from natural language requirements. This feature leverages AI to translate your ideas into fully functional pipeline code, dramatically speeding up development.

## Overview

The pipeline creation system can generate pipelines in different modes depending on your needs - from quick one-shot generation to validated, production-ready pipelines that have been automatically tested and fixed.

## Core Commands

### Build Pipe (Recommended)

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

### Build One-Shot (Fast)

Generate a pipeline quickly without validation:

```bash
pipelex build one-shot "BRIEF IN NATURAL LANGUAGE" [OPTIONS]
```

This command generates the pipeline in a single pass without validation. It's faster but may produce pipelines that need manual fixes.

**Example:**

```bash
pipelex build one-shot "Extract invoice data from PDF documents" \
  -o results/invoice_extractor.plx
```

**Use when:** You want to quickly iterate on ideas or plan to manually review/modify the pipeline.

### Build Partial (Debug)

Generate a partial pipeline specification as JSON for debugging:

```bash
pipelex build partial "BRIEF IN NATURAL LANGUAGE" [OPTIONS]
```

This outputs the internal pipeline specification in JSON format, useful for debugging and understanding how Pipelex interprets your requirements.

**Example:**

```bash
pipelex build partial "Analyze sentiment from customer reviews" \
  -o results/debug_spec.json
```

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

