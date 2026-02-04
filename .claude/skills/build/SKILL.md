---
name: build
description: Build new Pipelex workflow bundles (.plx files). Use when creating a new workflow, user says "create a pipeline", "build a method", "new workflow", "build a .plx file". Supports interactive requirements gathering and direct creation.
---

# Build Pipelex Workflow (Agentic)

Create new Pipelex workflow bundles through an adaptive, phase-based approach. This skill guides you through drafting (markdown), structuring (CLI/JSON), and assembling complete .plx bundles.

## Philosophy

1. **Drafting phases**: Generate human-readable markdown documents
2. **Structuring phases**: Use agent CLI commands for JSON-to-TOML conversion
3. **Visualization**: Present ASCII graphs at overview and detail levels
4. **Iterative**: Refine at each phase before proceeding

## Prerequisites

Check CLI availability:
1. Try `pipelex-agent --version`
2. If not found, try `uv run pipelex-agent --version`
3. Use whichever works for all subsequent commands

---

## Phase 1: Understand Requirements

**Goal**: Gather complete information before planning.

Ask the user:
- What are the workflow's inputs? (documents, images, text, structured data)
- What outputs should it produce?
- What transformations are needed?
- Are there conditional branches or parallel operations?
- Should items be processed in batches?

**Output**: Requirements summary (keep in context)

---

## Phase 2: Draft the Plan

**Goal**: Create a pseudo-code narrative of the workflow.

Draft a plan in markdown that describes:
- The overall flow from inputs to outputs
- Each processing step with its purpose
- Variable names (snake_case) for inputs and outputs of each step
- Where structured data or lists are involved

**Rules**:
- Name variables consistently across steps
- Use plural names for lists (e.g., `documents`), singular for items (e.g., `document`)
- Don't detail types yet - focus on the flow

**Show ASCII Overview**:
```
┌─────────────────────────────────────────────────────┐
│                   workflow_name                      │
│  Domain: my_domain                                   │
├─────────────────────────────────────────────────────┤
│                                                      │
│   [Input1]  ──────►  ┌──────────────┐               │
│   [Input2]  ──────►  │  main_pipe   │  ──────►  [Output]
│                      │  (Sequence)  │               │
│                      └──────────────┘               │
│                                                      │
└─────────────────────────────────────────────────────┘
```

**Output**: Plan draft (markdown)

---

## Phase 3: Draft Concepts

**Goal**: Identify all data types needed in the workflow.

From the plan, identify:
- Input concepts
- Intermediate concepts
- Output concepts

For each concept, draft:
- **Name**: PascalCase, singular noun (e.g., `Invoice` not `Invoices`)
- **Description**: What it represents
- **Type**: Either `refines: NativeConcept` OR `structure: {...}`

**Native concepts** (use directly without defining):
`Text`, `Image`, `PDF`, `Document`, `TextAndImages`, `Number`, `Page`, `JSON`, `ImgGenPrompt`, `Html`

**Concept naming rules**:
- No adjectives: `Article` not `LongArticle`
- No circumstances: `Argument` not `CounterArgument`
- Always singular: `Employee` not `Employees`

**Output**: Concepts draft (markdown)

---

## Phase 4: Structure Concepts

**Goal**: Convert concept drafts to validated TOML using the CLI.

For each concept, prepare a JSON spec and call:

```bash
pipelex-agent concept --spec '{
  "the_concept_code": "Invoice",
  "description": "A commercial invoice document",
  "structure": {
    "invoice_number": "The unique identifier",
    "vendor_name": {"type": "text", "description": "Vendor name", "required": true},
    "total_amount": {"type": "number", "description": "Total amount", "required": true}
  }
}'
```

Or for refined concepts:
```bash
pipelex-agent concept --spec '{
  "the_concept_code": "Summary",
  "description": "A text summary of content",
  "refines": "Text"
}'
```

**Field types**: `text`, `integer`, `boolean`, `number`, `date`, `concept`

**Output**: Validated concept TOML fragments

---

## Phase 5: Draft the Flow

**Goal**: Design the complete pipeline structure with controller selection.

### Controller Selection Guide

| Controller | Use When | Key Pattern |
|------------|----------|-------------|
| **PipeSequence** | Steps must execute in order | step1 → step2 → step3 |
| **PipeBatch** | Same operation on each list item | map(items, transform) |
| **PipeParallel** | Independent operations run together | fork → join |
| **PipeCondition** | Route based on data values | if-then-else |

### Operator Selection Guide

| Operator | Use When |
|----------|----------|
| **PipeLLM** | Generate text or structured objects with AI |
| **PipeExtract** | Extract content from PDF/Image → Page[] |
| **PipeCompose** | Template text or construct objects |
| **PipeImgGen** | Generate images from text prompts |
| **PipeFunc** | Custom Python logic |

**Show detailed ASCII flow**:

**Sequence Flow**:
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Step 1    │────►│   Step 2    │────►│   Step 3    │
│  (PipeLLM)  │     │  (PipeLLM)  │     │ (Compose)   │
└─────────────┘     └─────────────┘     └─────────────┘
     │                   │                   │
     ▼                   ▼                   ▼
 [analysis]         [refined]           [output]
```

**Batch Flow** (map operation):
```
                ┌─────────────────────────┐
                │       PipeBatch         │
                │   input_list: items     │
                │   branch: process_item  │
                └───────────┬─────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         ▼                  ▼                  ▼
    ┌─────────┐        ┌─────────┐        ┌─────────┐
    │ item[0] │        │ item[1] │        │ item[2] │
    │ branch  │        │ branch  │        │ branch  │
    └────┬────┘        └────┬────┘        └────┬────┘
         │                  │                  │
         └──────────────────┼──────────────────┘
                            ▼
                      [results[]]
```

**Parallel Flow**:
```
                    ┌─────────────┐
               ┌───►│  Branch A   │───┐
               │    └─────────────┘   │
┌─────────┐    │    ┌─────────────┐   │    ┌─────────┐
│  Input  │────┼───►│  Branch B   │───┼───►│ Combined│
└─────────┘    │    └─────────────┘   │    └─────────┘
               │    ┌─────────────┐   │
               └───►│  Branch C   │───┘
                    └─────────────┘
```

**Condition Flow**:
```
                         ┌─────────────┐
                    ┌───►│  Case: "A"  │
                    │    └─────────────┘
┌─────────┐    ┌────┴────┐
│  Input  │───►│ expr=?  │───►  Case: "B"
└─────────┘    └────┬────┘
                    │    ┌─────────────┐
                    └───►│  default    │
                         └─────────────┘
```

**Output**: Flow draft with pipe contracts (markdown)

---

## Phase 6: Review & Refine

**Goal**: Validate consistency before structuring.

Check:
- [ ] Main pipe is clearly identified and handles workflow inputs
- [ ] Variable names are consistent across all pipes
- [ ] Input/output types match between connected pipes
- [ ] PipeBatch branches receive singular items, not lists
- [ ] PipeImgGen inputs are text (add PipeLLM if needed to generate prompt)
- [ ] No circular dependencies

**Confirm with user** before proceeding to structuring.

---

## Phase 7: Structure Pipes

**Goal**: Convert pipe drafts to validated TOML using the CLI.

For each pipe, call the appropriate command based on type:

### PipeLLM
```bash
pipelex-agent pipe --type PipeLLM --spec '{
  "pipe_code": "summarize_document",
  "description": "Summarize document content",
  "inputs": {"document": "Document"},
  "output": "Summary",
  "llm_talent": "CREATIVE_WRITER",
  "prompt": "Summarize this document:\n\n@document"
}'
```

### PipeSequence
```bash
pipelex-agent pipe --type PipeSequence --spec '{
  "pipe_code": "process_invoice",
  "description": "Full invoice processing",
  "inputs": {"document": "PDF"},
  "output": "InvoiceData",
  "steps": [
    {"pipe": "extract_text", "result": "pages"},
    {"pipe": "analyze_invoice", "result": "invoice_data"}
  ]
}'
```

### PipeBatch
```bash
pipelex-agent pipe --type PipeBatch --spec '{
  "pipe_code": "process_all_items",
  "description": "Process each item in list",
  "inputs": {"items": "Item[]", "context": "Context"},
  "output": "Result[]",
  "branch_pipe_code": "process_single_item",
  "input_list_name": "items",
  "input_item_name": "item"
}'
```

### PipeCondition
```bash
pipelex-agent pipe --type PipeCondition --spec '{
  "pipe_code": "route_by_type",
  "description": "Route based on document type",
  "inputs": {"document": "ClassifiedDocument"},
  "output": "ProcessedDocument",
  "expression": "document.doc_type",
  "outcomes": {"invoice": "process_invoice", "receipt": "process_receipt"},
  "default_outcome": "process_generic"
}'
```

### PipeCompose
```bash
pipelex-agent pipe --type PipeCompose --spec '{
  "pipe_code": "format_report",
  "description": "Format final report",
  "inputs": {"summary": "Summary", "details": "Details"},
  "output": "Report",
  "target_format": "markdown",
  "template": "# Report\n\n$summary\n\n## Details\n\n@details"
}'
```

**LLM Talents**: `data-retrieval`, `hr-expert`, `accounting-expert`, `creative-writer`, `engineer`, `coder`, `code-analyzer`, `vision-language-model`, `visual-designer`

**Output**: Validated pipe TOML fragments

---

## Phase 8: Assemble Bundle

**Goal**: Combine all parts into a complete .plx file.

Save concept and pipe TOML to temporary files, then:

```bash
pipelex-agent assemble \
  --domain my_domain \
  --main-pipe main_workflow \
  --description "Description of the workflow" \
  --concepts concepts.toml \
  --pipes pipes.toml \
  --output bundle.plx
```

Or write the .plx file directly following this structure:

```toml
domain = "my_domain"
description = "What this workflow does"
main_pipe = "main_workflow"

[concept]
MyInput = "Description of input"
MyOutput = "Description of output"

[concept.StructuredConcept]
description = "A concept with fields"

[concept.StructuredConcept.structure]
field_name = "Field description"
typed_field = { type = "number", description = "...", required = true }

[pipe.main_workflow]
type = "PipeSequence"
description = "Main orchestration"
inputs = { input = "MyInput" }
output = "MyOutput"
steps = [
    { pipe = "step_one", result = "intermediate" },
    { pipe = "step_two", result = "final" }
]

[pipe.step_one]
type = "PipeLLM"
description = "First step"
inputs = { input = "MyInput" }
output = "Intermediate"
llm_talent = "ENGINEER"
prompt = "@input"
```

---

## Phase 9: Validate & Test

**Goal**: Ensure the bundle is valid and works correctly.

```bash
# Validate the bundle
pipelex-agent validate bundle.plx

# Generate example inputs
pipelex-agent inputs bundle.plx

# Dry run (no API calls)
pipelex-agent run bundle.plx --dry-run --mock-inputs
```

Fix any validation errors and re-validate.

---

## Quick Reference

### Multiplicity Notation
- `Text` - single item
- `Text[]` - variable-length list
- `Text[3]` - exactly 3 items

### Prompt Variables
- `@variable` - Block insertion (multi-line, with delimiters)
- `$variable` - Inline insertion (short text)
- `$var.field` - Access nested field

### Naming Conventions
- **Domain**: `snake_case`
- **Concepts**: `PascalCase`, singular
- **Pipes**: `snake_case`
- **Variables**: `snake_case`

### Common Errors

**`missing_input_variable`**: Add missing input to parent pipe's `inputs`.

**Inputs on one line**:
```toml
# CORRECT
inputs = { a = "A", b = "B" }

# WRONG
inputs = {
    a = "A",
    b = "B"
}
```

---

## Reference

See [Pipelex Language Reference](../shared/pipelex-reference.md) for complete syntax documentation.
