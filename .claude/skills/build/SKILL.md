---
name: build
description: Build new Pipelex workflow bundles (.plx files). Use when user says "create a pipeline", "build a workflow", "new .plx file", "make a method", "design a pipe", or wants to create any new Pipelex workflow from scratch. Supports both automated CLI build and guided 9-phase manual construction.
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

**When to use which:**
- **Automated** — simple to moderate workflows, fast iteration, starting point for refinement
- **Manual (below)** — complex workflows, custom controller logic, precise prompt engineering, full control

Recommended approach: start with `pipelex-agent build`, then refine with /edit and /fix skills.

For build error handling, see [Error Handling Reference](../shared/error-handling.md).

---

## Prerequisites

See [CLI Prerequisites](../shared/prerequisites.md)

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

**Show ASCII Overview** — see [Manual Build Phases](references/manual-build-phases.md#phase-2-ascii-overview-diagram) for the diagram template.

**Output**: Plan draft (markdown)

---

## Phase 3: Draft Concepts

**Goal**: Identify all data types needed in the workflow.

From the plan, identify input, intermediate, and output concepts.

For each concept, draft:
- **Name**: PascalCase, singular noun (e.g., `Invoice` not `Invoices`)
- **Description**: What it represents
- **Type**: Either `refines: NativeConcept` OR `structure: {...}`

**Native concepts** (built-in, no definition needed): See [Pipelex Reference — Native Concepts](../shared/pipelex-reference.md#native-concepts)

> **Note**: `Document` is the native concept for any document (PDF, Word, etc.). `Image` is for any image format (JPEG, PNG, etc.). File formats like "PDF" or "JPEG" are not concepts.

**Concept naming rules**:
- No adjectives: `Article` not `LongArticle`
- No circumstances: `Argument` not `CounterArgument`
- Always singular: `Employee` not `Employees`

**Output**: Concepts draft (markdown)

---

## Phase 4: Structure Concepts

**Goal**: Convert concept drafts to validated TOML using the CLI.

Prepare JSON specs for all concepts, then convert them **in parallel** by making multiple concurrent tool calls.

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
status = {choices = ["pending", "processing", "completed"], description = "Order status", required = true}
```

**Nested concept references** in structures:
```toml
field = {type = "concept", concept_ref = "my_domain.OtherConcept", description = "...", required = true}
items = {type = "list", item_type = "concept", item_concept_ref = "my_domain.OtherConcept", description = "..."}
```

**Output**: Validated concept TOML fragments

> **Partial failures**: If some commands fail, fix the failing specs using the error JSON (`error_domain: "input"` means the spec is wrong). Re-run only the failed commands.

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

> **Note**: `Page[]` outputs from PipeExtract automatically convert to text when inserted into prompts using `@variable`.

**Show detailed ASCII flow** — see [Manual Build Phases](references/manual-build-phases.md#phase-5-controller-flow-diagrams) for all controller flow diagrams.

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

Prepare JSON specs for all pipes, then convert them **in parallel** by making multiple concurrent tool calls.

For detailed CLI examples for each pipe type (PipeLLM, PipeSequence, PipeBatch, PipeCondition, PipeCompose, PipeParallel, PipeExtract, PipeImgGen), see [Manual Build Phases](references/manual-build-phases.md#phase-7-pipe-type-cli-examples).

For talent-to-model-preset mapping tables, see [Talents and Presets](references/talents-and-presets.md).

**Output**: Validated pipe TOML fragments

> **Partial failures**: Fix failing specs using the error JSON. Re-run only the failed commands.

---

## Phase 8: Assemble Bundle

**Goal**: Combine all parts into a complete .plx file.

**Save location**: Always save workflow bundles to `pipelex-wip/`. Do not ask the user for the save location.

For the assemble CLI command and direct .plx writing examples, see [Manual Build Phases](references/manual-build-phases.md#phase-8-assemble-bundle).

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

---

## Reference

- [CLI Prerequisites](../shared/prerequisites.md) — read at skill start to check CLI availability
- [Error Handling](../shared/error-handling.md) — read when CLI returns an error to determine recovery
- [Pipelex Agent Guide](../shared/pipelex-agent-guide.md) — read for CLI command syntax or output format details
- [Pipelex Language Reference](../shared/pipelex-reference.md) — read when writing or modifying .plx TOML syntax
- [Manual Build Phases](references/manual-build-phases.md) — read for detailed ASCII diagrams and CLI examples per phase
- [Talents and Presets](references/talents-and-presets.md) — read when selecting model talents for pipe structuring
