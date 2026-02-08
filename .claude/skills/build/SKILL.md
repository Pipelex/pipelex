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

## Automated Alternative

Before starting the manual 9-phase process, consider the automated build:

```bash
pipelex-agent build "Given a theme, write a Haiku"
```

**JSON output on success:**
```json
{
  "output_dir": "pipelex-wip/pipeline_01",
  "plx_file": "pipelex-wip/pipeline_01/bundle.plx",
  "main_pipe_code": "write_haiku",
  "domain": "haiku_writing",
  "pipe_inputs": {"theme": "Text"},
  "pipe_output": "Haiku"
}
```

Key output fields:
- `plx_file` — path to the generated .plx bundle
- `pipe_inputs` — maps input variable names to their concept types
- `pipe_output` — the output concept type

**When to use which:**
- **Automated** — simple to moderate workflows, fast iteration, starting point for refinement
- **Manual (below)** — complex workflows, custom controller logic, precise prompt engineering, full control

Recommended approach: start with `pipelex-agent build`, then refine with /edit and /fix skills.

### Build Error Handling

**JSON output on error:**
```json
{
  "error": true,
  "error_type": "BuildPipeError",
  "error_domain": "runtime",
  "message": "Build failed: ...",
  "hint": "Check 'failure_memory_path' for builder loop failure diagnostics if present",
  "failure_memory_path": "pipelex-wip/pipeline_01/failure_memory.json",
  "cause_type": "PipelineExecutionError",
  "cause_message": "Pipeline execution failed in pipe 'pipe_builder'"
}
```

**Error recovery:**

| Error Type | Domain | Action |
|------------|--------|--------|
| `BuildPipeError` | runtime | Read `failure_memory_path` if present for diagnostics; check `cause_type`/`cause_message` for root cause |
| `ValidateBundleError` | input | Check `validation_errors` array; fix .plx issues then re-validate |
| `PipeOperatorModelAvailabilityError` | config | Run `pipelex-agent doctor`; check `fallback_list` for models that were tried |
| `PipeOperatorModelChoiceError` | config | Run `pipelex-agent doctor`; check model routing configuration |

When `failure_memory_path` is present, read that file to understand the builder loop's last state and what went wrong.

---

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
`Text`, `Image`, `Document`, `TextAndImages`, `Number`, `Page`, `JSON`, `ImgGenPrompt`, `Html`, `Anything`, `Dynamic`

> **Note**: `Document` is the native concept for any document (PDF, Word, etc.). `Image` is for any image format (JPEG, PNG, etc.). File formats like "PDF" or "JPEG" are not concepts.

**Concept naming rules**:
- No adjectives: `Article` not `LongArticle`
- No circumstances: `Argument` not `CounterArgument`
- Always singular: `Employee` not `Employees`

**Output**: Concepts draft (markdown)

---

## Phase 4: Structure Concepts

**Goal**: Convert concept drafts to validated TOML using the CLI.

Prepare JSON specs for all concepts, then convert them **in parallel** by making multiple concurrent tool calls:

**Important**: Call all `pipelex-agent concept` commands in a single response using parallel tool calls. Do not wait for one to complete before starting the next.

**Example** (3 concepts converted in parallel):
```bash
# Call all three in parallel (single response, multiple tool calls):
pipelex-agent concept --spec '{"the_concept_code": "Invoice", "description": "A commercial invoice document", "structure": {"invoice_number": "The unique identifier", "vendor_name": {"type": "text", "description": "Vendor name", "required": true}, "total_amount": {"type": "number", "description": "Total amount", "required": true}}}'
pipelex-agent concept --spec '{"the_concept_code": "LineItem", "description": "A single line item on an invoice", "structure": {"description": "Item description", "quantity": {"type": "integer", "required": true}, "unit_price": {"type": "number", "required": true}}}'
pipelex-agent concept --spec '{"the_concept_code": "Summary", "description": "A text summary of content", "refines": "Text"}'
```

**Field types**: `text`, `integer`, `boolean`, `number`, `date`, `concept`, `list`

**Choices (enum-like constrained values)**:
```toml
# Use choices instead of type when the field has a fixed set of allowed values
status = {choices = ["pending", "processing", "completed"], description = "Order status", required = true}
priority = {choices = ["low", "medium", "high"], description = "Priority level"}
```

This generates type-safe `Literal` types in Python. Use choices when:
- A field should only accept specific string values
- You want to route with PipeCondition based on the field value
- Input validation should reject invalid values

**Nested concept references** in structures:
```toml
# Single concept reference - needs full domain path
field = {type = "concept", concept_ref = "my_domain.OtherConcept", description = "...", required = true}

# List of concepts - different syntax
field = {type = "list", item_type = "concept", item_concept_ref = "my_domain.OtherConcept", description = "...", required = true}
```

**Output**: Validated concept TOML fragments

> **Partial failures**: If some concept commands fail while others succeed, fix the failing specs using the error JSON (`error_domain: "input"` means the spec is wrong; `error_domain: "config"` means a model/config issue). Re-run only the failed commands.

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

> **Note**: `Page[]` outputs from PipeExtract automatically convert to text when inserted into prompts using `@variable`. No explicit conversion step is needed when passing extracted pages to PipeLLM.

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

Prepare JSON specs for all pipes, then convert them **in parallel** by making multiple concurrent tool calls:

**Important**: Call all `pipelex-agent pipe` commands in a single response using parallel tool calls. Do not wait for one to complete before starting the next.

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
  "inputs": {"document": "Document"},
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

PipeCompose has **two modes** - use the CLI for template mode only, write directly for construct mode:

**Template mode** (via CLI) - generates Text or Html:
```bash
pipelex-agent pipe --type PipeCompose --spec '{
  "pipe_code": "format_report",
  "description": "Format final report",
  "inputs": {"summary": "Summary", "details": "Details"},
  "output": "Text",
  "target_format": "markdown",
  "template": "# Report\n\n$summary\n\n## Details\n\n@details"
}'
```

**Construct mode** (write directly to .plx) - builds structured objects:
```toml
[pipe.build_output]
type = "PipeCompose"
description = "Assemble final output"
inputs = {analysis = "Analysis", items = "Item[]"}
output = "FinalOutput"

[pipe.build_output.construct]
summary = {from = "analysis.summary"}
score = {from = "analysis.score"}
items = {from = "items"}
label = {template = "Analysis for $analysis.name"}
version = "1.0"  # Static value
```

**Construct field methods:**
- `{from = "variable.path"}` - Reference input or nested field
- `{template = "text with $var"}` - String interpolation
- `"value"` or `123` - Static/fixed values

### PipeParallel

Run multiple pipes concurrently on the same inputs:
```bash
pipelex-agent pipe --type PipeParallel --spec '{
  "pipe_code": "analyze_all",
  "description": "Run analyses in parallel",
  "inputs": {"document": "Document"},
  "output": "CombinedAnalysis",
  "parallels": [
    {"pipe": "analyze_sentiment", "result": "sentiment"},
    {"pipe": "extract_topics", "result": "topics"}
  ],
  "add_each_output": true,
  "combined_output": "CombinedAnalysis"
}'
```

**Required**: Must set either `add_each_output: true` OR `combined_output` (or both).

---

### Talents vs Model Presets

The agent CLI uses human-friendly "talent" names that map to model presets. This shields you from needing to know specific model names.

**LLM Talents** (CLI) → **Model Presets** (.plx):
| Talent | Model Preset |
|--------|--------------|
| `data-retrieval` | `$retrieval` |
| `hr-expert` | `$writing-factual` |
| `accounting-expert` | `$writing-factual` |
| `creative-writer` | `$writing-creative` |
| `engineer` | `$engineering-structured` |
| `coder` | `$engineering-code` |
| `code-analyzer` | `$engineering-codebase-analysis` |
| `vision-language-model` | `$vision` |
| `visual-designer` | `$img-gen-prompting` |

**Extract Talents** → **Model Presets**:
| Talent | Model Preset |
|--------|--------------|
| `pdf-basic-text-extractor` | `@default-text-from-pdf` |
| `image-text-extractor` | `@default-extract-image` |
| `full-document-extractor` | `@default-extract-document` |

**Image Generation Talents** → **Model Presets**:
| Talent | Model Preset |
|--------|--------------|
| `gen-image` | `$gen-image` |
| `gen-image-fast` | `$gen-image-fast` |
| `gen-image-high-quality` | `$gen-image-high-quality` |

**Parallel Conversion Example** (converting 4 pipes at once):
```bash
# Call all pipe commands in parallel (single response, multiple tool calls):
pipelex-agent pipe --type PipeLLM --spec '{"pipe_code": "summarize", "description": "Summarize document", "inputs": {"document": "Document"}, "output": "Summary", "llm_talent": "creative-writer", "prompt": "Summarize:\n\n@document"}'
pipelex-agent pipe --type PipeExtract --spec '{"pipe_code": "extract_pages", "description": "Extract text from document", "inputs": {"document": "Document"}, "output": "Page[]", "extract_talent": "pdf-basic-text-extractor"}'
pipelex-agent pipe --type PipeLLM --spec '{"pipe_code": "analyze", "description": "Analyze content", "inputs": {"pages": "Page[]"}, "output": "Analysis", "llm_talent": "engineer", "prompt": "Analyze:\n\n@pages"}'
pipelex-agent pipe --type PipeSequence --spec '{"pipe_code": "main_workflow", "description": "Main orchestration", "inputs": {"document": "Document"}, "output": "Analysis", "steps": [{"pipe": "extract_pages", "result": "pages"}, {"pipe": "analyze", "result": "analysis"}]}'
```

**Output**: Validated pipe TOML fragments

> **Partial failures**: If some pipe commands fail while others succeed, fix the failing specs using the error JSON (`error_domain: "input"` means the spec is wrong; `error_domain: "config"` means a model/config issue). Re-run only the failed commands.

---

## Phase 8: Assemble Bundle

**Goal**: Combine all parts into a complete .plx file.

**Save location**: Always save workflow bundles to `pipelex-wip/`. Do not ask the user for the save location.

Save concept and pipe TOML to temporary files, then:

```bash
pipelex-agent assemble \
  --domain my_domain \
  --main-pipe main_workflow \
  --description "Description of the workflow" \
  --concepts concepts.toml \
  --pipes pipes.toml \
  --output pipelex-wip/bundle.plx
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
model = "$engineering-structured"
prompt = "@input"
```

> **Note**: In .plx files, use `model` with preset references (e.g., `$writing-factual`). The agent CLI uses `llm_talent` names which it converts to model presets automatically.

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

- [Pipelex Agent Guide](../shared/pipelex-agent-guide.md) for CLI philosophy and error type reference
- [Pipelex Language Reference](../shared/pipelex-reference.md) for complete syntax documentation
