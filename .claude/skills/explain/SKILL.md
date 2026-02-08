---
name: explain
description: >
  Explain and document Pipelex workflows. Use when user says "what does this pipeline do?",
  "explain this workflow", "walk me through this .plx file", "describe the flow",
  "document this pipeline", "how does this work?", or wants to understand an existing
  Pipelex workflow bundle.
---

# Explain Pipelex Workflow

Analyze and explain existing Pipelex workflow bundles in plain language.

## Workflow

**Prerequisite**: See [CLI Prerequisites](../shared/prerequisites.md)

### Step 1: Read the .plx File

Read the entire bundle file to understand its structure.

### Step 2: Identify Components

List all components found in the bundle:
- **Domain**: the `[domain]` declaration
- **Concepts**: all `[concept.*]` blocks — note which are custom vs references to native concepts
- **Pipes**: all `[pipe.*]` blocks — identify the main pipe and sub-pipes
- **Main pipe**: declared in `[bundle]` section

### Step 3: Trace Execution Flow

Starting from the main pipe, trace the execution path:
1. For **PipeSequence**: follow the `steps` array in order
2. For **PipeBatch**: identify `batch_over` and `batch_as`, then the inner pipe
3. For **PipeParallel**: list all branches
4. For **PipeCondition**: map condition → pipe for each branch
5. For **PipeLLM / PipeExtract / PipeImgGen / PipeFunc**: these are leaf operations

### Step 4: Present Explanation

Structure the explanation as:

1. **Purpose**: one-sentence summary of what the workflow does
2. **Inputs**: list each input with its concept type and expected content
3. **Output**: the final output concept and what it contains
4. **Step-by-step flow**: walk through execution in order, explaining what each pipe does
5. **Key concepts**: explain any custom concepts defined in the bundle

### Step 5: Generate Flow Diagram

Create an ASCII diagram showing the execution flow:

```
[input_a, input_b]
        |
   main_sequence
   ├── step_one (PipeLLM) → intermediate_result
   └── step_two (PipeExtract) → final_output
```

Adapt the diagram style to the workflow structure (linear, branching, batched).

### Step 6: Optional — Validate

If the user wants to confirm the workflow is valid:
```bash
pipelex-agent validate <file>.plx
```

### Step 7: Optional — Visual Graph

Suggest generating an interactive visual graph for complex workflows:
```bash
pipelex-agent run <file>.plx --dry-run --mock-inputs --graph
```

This produces HTML visualizations in `pipelex-wip/` without running the actual pipeline.

## Reference

- [CLI Prerequisites](../shared/prerequisites.md) — read at skill start to check CLI availability
- [Error Handling](../shared/error-handling.md) — read when CLI returns an error to determine recovery
- [Pipelex Agent Guide](../shared/pipelex-agent-guide.md) — read for CLI command syntax or output format details
- [Pipelex Language Reference](../shared/pipelex-reference.md) — read for concept definitions and syntax
