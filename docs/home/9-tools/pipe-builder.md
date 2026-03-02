# Pipe Builder

!!! warning "Beta Feature"
    The Pipe Builder is currently in beta and progressing fast. Expect frequent improvements and changes.

The Pipe Builder is an AI-powered tool that generates complete Pipelex pipelines from natural language descriptions. Describe what you want to achieve, and the builder creates a production-ready `.mthds` file with concepts, pipes, and all the necessary structure.

## What It Does

The Pipe Builder takes a brief description like:

> "Take a CV and Job offer in PDF, analyze if they match and generate 5 questions for the interview"

And generates:

- **Domain concepts** - Data structures for your method (e.g., `CVAnalysis`, `InterviewQuestion`)
- **Pipe operators** - LLM calls, extractions, image generation steps
- **Pipe controllers** - Sequences, batches, parallel branches, conditions to orchestrate the flow
- **A complete bundle** - Ready to validate and run

## How It Works

!!! tip "Built with Pipelex"
    The Pipe Builder is itself a Pipelex pipeline! This showcases the power of Pipelex: a tool that builds pipelines... using a pipeline.

The builder follows a multi-step process:

### 1. Draft the Plan

First, the AI analyzes your brief and creates a narrative plan describing:

- The sequence of steps needed
- Inputs and outputs for each step
- Where structured data or lists are needed
- Which orchestration patterns to use (sequence, batch, parallel, condition)

### 2. Draft the Concepts

Based on the plan, it identifies and defines the concepts needed:

- What data structures are required
- Which fields each concept needs
- How concepts relate to each other
- Which native concepts to reuse (Text, Image, PDF, etc.)

### 3. Structure the Concepts

The concept drafts are formalized into proper Pipelex concept specifications with:

- Field names and types
- Descriptions
- Required/optional flags
- Default values

### 4. Design the Flow

The plan is translated into a structured flow with:

- Pipe operators (PipeLLM, PipeExtract, PipeImgGen, PipeSearch)
- Pipe controllers (PipeSequence, PipeBatch, PipeParallel, PipeCondition)
- Input/output contracts for each pipe
- Memory flow between steps

### 5. Review and Refine

The flow is reviewed for consistency:

- Are inputs and outputs properly connected?
- Is the main pipe correctly identified?
- Are batches and lists handled properly?

### 6. Generate Pipe Signatures

Each pipe gets a formal signature with:

- Unique pipe code
- Description
- Input/output types with multiplicity
- Dependencies on other pipes

### 7. Assemble the Bundle

Finally, everything is assembled into a complete Pipelex bundle:

- Domain header with name and description
- All concept definitions
- All pipe definitions
- Main pipe identification

## The Builder Pipeline

The Pipe Builder is defined in [`pipelex/builder/builder.mthds`](https://github.com/Pipelex/pipelex/blob/main/pipelex/builder/builder.mthds). The main orchestrator is a `PipeSequence` called `pipe_builder` that chains together:

```
draft_the_plan → draft_the_concepts → structure_concepts → draft_flow → review_flow → design_pipe_signatures → write_bundle_header → detail_pipe_spec (batched) → assemble_pipelex_bundle_spec
```

Each step uses `PipeLLM` with carefully crafted prompts to guide the AI through the generation process.

## Using the Pipe Builder

To use the Pipe Builder, use the CLI command:

```bash
pipelex build pipe "Your description here"
```

See the [Build Pipe CLI documentation](cli/build/pipe.md) for:

- Command options
- Generated file structure
- Example use cases
- Tips for best results

## Related Documentation

- [Build Pipe CLI](cli/build/pipe.md) - Command reference and options
- [Design and Run Pipelines](../6-build-reliable-ai-workflows/pipes/index.md) - Pipeline concepts
- [Concepts](../6-build-reliable-ai-workflows/concepts/define_your_concepts.md) - Understanding concept definitions

