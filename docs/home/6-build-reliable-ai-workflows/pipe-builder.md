# Pipe Builder

Pipelex provides powerful tools to automatically generate complete, working pipelines from natural language requirements. This feature leverages AI to translate your ideas into fully functional pipeline code, dramatically speeding up development.

!!! tip "Pipe Builder Requirements"
    For now, the pipe builder requires access to **Claude 4.5 Sonnet**, either through Pipelex Inference, or using your own key through Anthropic, Amazon Bedrock or BlackboxAI. Don't hesitate to join our [Discord](https://go.pipelex.com/discord) to get a key or see [Configure AI Providers](../../home/5-setup/configure-ai-providers.md) for details. Otherwise, you can also create the workflows yourself, following our [documentation guide](./kick-off-a-pipelex-workflow-project.md).

## Overview

The pipeline creation system can generate pipelines in different modes depending on your needs - from quick one-shot generation to validated, production-ready pipelines that have been automatically tested and fixed.

## Build Pipe

Generate a validated pipeline with automatic fixing of deterministic issues:

```bash
pipelex build pipe "BRIEF IN NATURAL LANGUAGE" [OPTIONS]
```

This command runs a validation/fix loop to ensure the generated pipeline is correct and runnable. It automatically detects and corrects common issues.

**What Gets Generated:**

The build command creates two essential files:

1. **`.plx` file** - Your complete pipeline definition with concepts and pipes
2. **`inputs.json` template** - A pre-filled template showing the inputs your pipeline expects

After generation, you can fill in the `inputs.json` template with your actual data and run the pipeline. For detailed guidance on preparing and formatting inputs, see [Providing Inputs to Pipelines](./pipes/provide-inputs.md).

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

## How It Works

The Pipe Builder is itself a Pipelex pipeline (`builder.pipe_builder`) that transforms your natural language brief into a complete, validated pipeline through a multi-stage process, demonstrating the power and flexibility of the framework. Here's what happens under the hood:

### 1. Draft the Plan

The builder analyzes your brief and creates a pseudo-code plan describing:
- The sequence of pipes needed
- Input and output variables for each step
- Where structured outputs are needed
- Which orchestration controllers to use (Sequence, Batch, Parallel, Condition)

### 2. Define Concepts

From the plan, the builder identifies and defines the concepts (data types) needed:
- Analyzes what inputs and outputs are required
- Creates concept definitions with clear descriptions
- Determines which concepts need structure vs. simple text
- Reuses concepts where possible (e.g., "Article" instead of "LongArticle", "ShortArticle")

### 3. Structure Concepts

For concepts that need structure, the builder:
- Designs field definitions with appropriate types (text, integer, boolean, number, date, list, dict)
- Determines which fields are required vs. optional
- Creates inline structures or Python classes as needed

### 4. Draft and Review Flow

The builder designs the complete flow architecture:
- Maps out pipe controllers (PipeSequence, PipeBatch, PipeParallel, PipeCondition)
- Assigns pipe operators (PipeLLM, PipeExtract, PipeImgGen) to specific tasks
- Ensures variables flow correctly through the memory system
- Reviews the flow for consistency and fixes any issues

### 5. Design Pipe Signatures

Creates the contracts for each pipe:
- Assigns unique pipe codes (snake_case, verb-based)
- Defines inputs and outputs with proper concept types
- Handles multiplicity (single items, lists, fixed-size arrays)
- Identifies pipe dependencies

### 6. Detail Pipe Specifications

For each pipe signature, generates the complete specification:
- **PipeLLM**: Creates prompts and configures LLM settings
- **PipeExtract**: Sets up document/image extraction
- **PipeImgGen**: Configures image generation from prompts
- **PipeSequence**: Defines step-by-step execution
- **PipeBatch**: Sets up concurrent processing over lists
- **PipeParallel**: Orchestrates concurrent different pipes
- **PipeCondition**: Creates conditional branching logic

### 7. Create Domain and Assemble

Finally, the builder:
- Names the domain based on your brief
- Assembles all concepts and pipes into a complete bundle
- Generates the `.plx` file with proper syntax
- Creates Python structure files (`*_struct.py`) when needed
- Validates the pipeline and fixes deterministic issues

## Explore the Source

Want to see how the Pipe Builder works internally? Check out the source code:

- **Main pipeline**: [`pipelex/builder/builder.plx`](https://github.com/pipelex/pipelex/tree/main/pipelex/builder/builder.plx)
- **Pipe design**: [`pipelex/builder/pipe/pipe_design.plx`](https://github.com/pipelex/pipelex/tree/main/pipelex/builder/pipe/pipe_design.plx)
- **Concept building**: [`pipelex/builder/concept/concept.plx`](https://github.com/pipelex/pipelex/tree/main/pipelex/builder/concept/concept.plx)

The Pipe Builder is a great example of a complex, multi-stage Pipelex pipeline in action.

