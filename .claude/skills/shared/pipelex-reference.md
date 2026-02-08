# Pipelex Language Reference

Complete reference for the Pipelex workflow language.

## Bundle Structure

```toml
domain = "domain_code"
description = "Domain description"  # Optional
main_pipe = "pipe_code"             # Optional - default pipe to run

[concept]
ConceptName = "Description"

[concept.StructuredConcept]
description = "Concept with fields"

[concept.StructuredConcept.structure]
field_name = "Field description"  # Simple text field (optional)
typed_field = { type = "text", description = "...", required = true }

[pipe.pipe_code]
type = "PipeLLM"
description = "What this pipe does"
inputs = { input_name = "ConceptName" }
output = "OutputConcept"
prompt = """
Your prompt here with @block_var and $inline_var
"""
```

## Naming Conventions

- **Domain**: `snake_case` (e.g., `invoice_processing`)
- **Concepts**: `PascalCase`, singular, no circumstantial adjectives (e.g., `Invoice` not `Invoices` or `LargeInvoice`)
- **Pipes**: `snake_case` (e.g., `extract_invoice`)

## Native Concepts

Use directly without defining: `Text`, `Image`, `Document`, `TextAndImages`, `Number`, `Page`, `JSON`, `ImgGenPrompt`, `Html`, `Anything`, `Dynamic`

> **Note**: `Document` is the native concept for any document (PDF, Word, etc.). `Image` is for any image format (JPEG, PNG, etc.). File formats like "PDF" or "JPEG" are not concepts.

## Concept Definitions

### Simple Concept (refines native)

```toml
[concept.Landscape]
description = "A scenic outdoor photograph"
refines = "Image"
```

### Inline Structure (recommended)

```toml
[concept.Invoice]
description = "A commercial invoice"

[concept.Invoice.structure]
invoice_number = "The unique identifier"  # Optional text field
issue_date = { type = "date", description = "Issue date", required = true }
total_amount = { type = "number", description = "Total", required = true }
line_items = { type = "list", item_type = "text", description = "Items" }
```

**Field types**: `text`, `integer`, `boolean`, `number`, `date`, `list`, `dict`, `concept`

**Choices (enum-like values)**:
```toml
[concept.Order.structure]
status = { choices = ["pending", "processing", "shipped", "delivered"], description = "Order status" }
priority = { choices = ["low", "medium", "high"], required = true, description = "Priority level" }
```
This generates Python `Literal` types (e.g., `Literal["pending", "processing", "shipped", "delivered"]`), providing type-safe constrained string values.

**Concept references**:
```toml
customer = { type = "concept", concept_ref = "myapp.Customer", description = "..." }
items = { type = "list", item_type = "concept", item_concept_ref = "myapp.LineItem", description = "..." }
```

## Pipe Types

### PipeLLM - Generate text/objects with LLMs

```toml
[pipe.summarize]
type = "PipeLLM"
description = "Summarize text"
inputs = { text = "Text" }
output = "Summary"
prompt = """
Summarize this text:

@text
"""
```

**With system prompt and model settings**:
```toml
[pipe.expert_analysis]
type = "PipeLLM"
description = "Expert analysis"
inputs = { document = "Document" }
output = "Analysis"
system_prompt = "You are a financial analyst expert."
model = { model = "gpt-4o", temperature = 0.2 }
prompt = """
Analyze this document:

@document
"""
```

**Multiple outputs**:
- `output = "Idea[3]"` - exactly 3 items
- `output = "Idea[]"` - variable number

**Vision (images)**:
```toml
[pipe.analyze_image]
type = "PipeLLM"
inputs = { image = "Image" }
output = "ImageAnalysis"
prompt = "Describe this image: $image"
```

### PipeSequence - Chain pipes sequentially

```toml
[pipe.process_document]
type = "PipeSequence"
description = "Extract, summarize, translate"
inputs = { document = "Document" }
output = "FrenchSummary"
steps = [
    { pipe = "extract_text", result = "extracted" },
    { pipe = "summarize", result = "summary" },
    { pipe = "translate_french", result = "french" }
]
```

**Batch processing** (parallel over list):
```toml
steps = [
    { pipe = "process_item", batch_over = "items", batch_as = "item", result = "processed" }
]
```

### PipeCondition - Conditional branching

```toml
[pipe.route_by_category]
type = "PipeCondition"
description = "Route based on category"
inputs = { input_data = "CategorizedInput" }
output = "Text"
expression = "input_data.category"
default_outcome = "process_medium"

[pipe.route_by_category.outcomes]
small = "process_small"
medium = "process_medium"
large = "process_large"
```

Use `default_outcome = "fail"` for strict matching.

### PipeBatch - Map operation over a list

Applies the same pipe to each item in a list. Like a `map` operation: list in, list out, each item transformed by the same pipe.

```toml
[pipe.process_all_documents]
type = "PipeBatch"
description = "Process each document in the list"
inputs = { documents = "Document[]", context = "Context" }
output = "Summary[]"
input_list_name = "documents"
input_item_name = "document"
branch_pipe_code = "summarize_document"
```

**Required fields:**
- `branch_pipe_code` - The pipe to apply to each item (use simple name, no domain prefix)
- `input_list_name` - The input list to iterate over (must be in inputs with `[]`)
- `input_item_name` - The variable name for each item (used by the branch pipe)

**Multiplicity for non-batched inputs**: Use singular types for inputs passed to the branch pipe. Since the branch pipe receives individual items (not lists), non-batched inputs must match what the branch pipe declares.

```toml
# If branch pipe declares: inputs = { item = "Item", context = "Context" }
# Then PipeBatch should use singular for context:
inputs = { items = "Item[]", context = "Context" }  # NOT "Context[]"
```

Items are processed in parallel for efficiency. Output list preserves input order.

### PipeParallel - Run multiple pipes concurrently

Execute multiple independent pipes in parallel on the same inputs. Each branch runs in isolation with a deep copy of working memory.

**Required**: Must set either `add_each_output = true` OR `combined_output` (or both).

**With separate outputs** (each branch adds to working memory):
```toml
[pipe.analyze_all_aspects]
type = "PipeParallel"
description = "Run multiple analyses in parallel"
inputs = { document = "Document" }
output = "Text"
add_each_output = true
parallels = [
    { pipe = "analyze_sentiment", result = "sentiment" },
    { pipe = "extract_topics", result = "topics" },
    { pipe = "generate_summary", result = "summary" }
]
```

**With combined output** (merge branch results into single concept):
```toml
[pipe.analyze_all_aspects]
type = "PipeParallel"
description = "Run multiple analyses in parallel"
inputs = { document = "Document" }
output = "FullAnalysis"
add_each_output = true
combined_output = "FullAnalysis"
parallels = [
    { pipe = "analyze_sentiment", result = "sentiment" },
    { pipe = "extract_topics", result = "topics" }
]
```

**Parameters**:
- `parallels`: Array of `{ pipe = "pipe_code", result = "result_name" }` entries
- `add_each_output`: If `true`, adds each branch result to working memory individually
- `combined_output`: Concept name to bundle all results into (fields must match result names)

### PipeExtract - Extract text/images from Document/Image

```toml
[pipe.extract_document]
type = "PipeExtract"
description = "Extract content from document"
inputs = { document = "Document" }
output = "Page[]"
model = "@default-text-from-pdf"
```

Output is `Page[]` (a list of pages with `text_and_images` and `page_view`).

> **Note**: Use `Document` for PDFs and other document formats, `Image` for images. "PDF" is a file format, not a native concept.

### PipeCompose - Template composition

```toml
[pipe.compose_email]
type = "PipeCompose"
description = "Compose email from template"
inputs = { customer = "Customer", deal = "Deal" }
output = "Text"
template = """
Hi $customer.name,

Following up on $deal.product_name...

@deal.details
"""
```

**Construct mode** (build structured objects):
```toml
[pipe.build_invoice]
type = "PipeCompose"
inputs = { order = "Order", customer = "Customer" }
output = "Invoice"

[pipe.build_invoice.construct]
invoice_number = { template = "INV-$order.id" }
customer_name = { from = "customer.name" }
total = { from = "order.total" }
```

**Construct field methods:**
| Method | Syntax | Use case |
|--------|--------|----------|
| `template` | `{ template = "text $var" }` | String interpolation |
| `from` | `{ from = "input.field" }` | Reference input or nested field |
| Direct value | `"string"` or `123` or `[...]` | Static/fixed values |

**Static values in construct** - assign directly without wrapping:
```toml
[pipe.build_config.construct]
name = { template = "$input.name Config" }    # Dynamic from input
source = { from = "input.source" }            # Reference input field
version = "1.0"                               # Static string
count = 5                                     # Static number
tags = ["tag1", "tag2", "tag3"]               # Static list
enabled = true                                # Static boolean
```

**Common mistake:** Do NOT use `{ value = [...] }` - just assign the value directly.

### PipeImgGen - Generate images

```toml
[pipe.generate_image]
type = "PipeImgGen"
description = "Generate image"
inputs = { img_prompt = "ImgGenPrompt" }
output = "Image"
prompt = "$img_prompt"
model = "$gen-image"
aspect_ratio = "landscape_16_9"
```

**Required fields:**
- `prompt` - Must reference the input variable (e.g., `"$img_prompt"`)
- `model` - Model preset (e.g., `"$gen-image"`, `"@default-premium"`)

**Aspect ratio values** (use enum names, not ratios):
`square`, `landscape_4_3`, `landscape_3_2`, `landscape_16_9`, `landscape_21_9`, `portrait_3_4`, `portrait_2_3`, `portrait_9_16`, `portrait_9_21`

**Common mistake:** The `prompt` field is required separately from inputs - you must explicitly reference the input variable.

### PipeFunc - Custom Python functions

```toml
[pipe.process_data]
type = "PipeFunc"
description = "Custom processing"
inputs = { data = "InputData" }
output = "ProcessedData"
function_name = "my_registered_function"
```

Function must be registered in `func_registry` and accept `working_memory: WorkingMemory`.

## Prompt Variable Syntax

- `@variable` - Block insertion (multi-line, with delimiters). Put alone on its own line.
- `$variable` - Inline insertion (short text). Use within sentences.

**Structured content is auto-expanded**: When you use `@structured_var`, Pipelex automatically formats ALL fields of the structured concept. No need to manually enumerate fields.

```toml
# GOOD - concise, auto-expands all fields
prompt = """
Based on this theme configuration, create a prompt template:

@theme
"""

# BAD - verbose, manually listing fields (unnecessary)
prompt = """
Based on this theme:
- Primary: $theme.palette.primary
- Secondary: $theme.palette.secondary
...
"""
```

Use `$var.field` only when you need a specific field inline within a sentence.

## Input Multiplicity

```toml
inputs = { doc = "Text" }        # Single item
inputs = { docs = "Text[]" }     # Variable list
inputs = { pair = "Image[2]" }   # Exactly 2 items
```

## Cross-Domain References

### Concepts use domain prefix
Same domain (no prefix): `inputs = { invoice = "Invoice" }`
Different domain (prefix required): `inputs = { invoice = "finance.Invoice" }`

### Pipes use flat namespace (NO domain prefix)
**Critical**: Pipe references in `branch_pipe_code`, `pipe`, and sequence steps use simple names only. All pipes loaded into a library share a flat namespace.

```toml
# WRONG - will fail validation
branch_pipe_code = "pipe_design.detail_pipe_spec"
steps = [{ pipe = "builder.design_pipe_signatures", result = "sigs" }]

# CORRECT - use simple pipe names
branch_pipe_code = "detail_pipe_spec"
steps = [{ pipe = "design_pipe_signatures", result = "sigs" }]
```

### Validating cross-domain bundles
When a bundle references pipes/concepts from other domains, use `--library-dir` to load all related .plx files:

```bash
# Single file won't resolve cross-domain references
pipelex-agent validate my_bundle.plx  # May fail

# Load entire directory to resolve references
pipelex-agent validate my_bundle.plx --library-dir path/to/bundles/
```

## Model Configuration

**Direct model**:
```toml
model = { model = "gpt-4o", temperature = 0.7 }
```

**Preset** (defined in deck):
```toml
model = "$writing-creative"
```

## CLI Commands

**Before running commands**, check CLI availability:
1. Try `pipelex-agent --version`
2. If not found, try `uv run pipelex-agent --version`
3. If neither works: "Pipelex CLI not found. Install with `pip install pipelex` or `uv add pipelex`"

Use whichever method works. Prefix all subsequent commands the same way.

Agents must use `pipelex-agent` exclusively. It outputs structured JSON (stdout=success, stderr=error). There is also a `pipelex` CLI for human use — agents should not call it themselves, but can suggest it to the user (e.g., `pipelex doctor` for interactive config diagnostics, `pipelex show <name>` to visually inspect a pipe or concept).

```bash
# Validate a bundle
pipelex-agent validate my_bundle.plx
pipelex-agent validate my_bundle.plx --library-dir path/to/bundles/

# Generate example input JSON
pipelex-agent inputs my_bundle.plx
pipelex-agent inputs my_bundle.plx --pipe specific_pipe

# Run with inputs (file path or inline JSON)
pipelex-agent run my_bundle.plx --inputs inputs.json
pipelex-agent run my_bundle.plx --inputs '{"theme": {"concept": "native.Text", "content": {"text": "nature"}}}'
pipelex-agent run my_bundle.plx --pipe specific_pipe --inputs inputs.json

# Dry run (no API calls, validates logic)
pipelex-agent run my_bundle.plx --dry-run --mock-inputs

# Run with execution graph generation
pipelex-agent run my_bundle.plx --inputs data.json --graph

# Build a pipeline from a prompt
pipelex-agent build "Given a theme, write a Haiku"

# Render a graphspec.json to HTML visualizations
pipelex-agent graph graphspec.json
pipelex-agent graph graphspec.json --format mermaidflow -o ./output/

# Structure concepts and pipes from JSON specs
pipelex-agent concept --spec '{"the_concept_code": "Summary", "description": "A text summary", "refines": "Text"}'
pipelex-agent pipe --type PipeLLM --spec '{"pipe_code": "summarize", "description": "Summarize text", "inputs": {"text": "Text"}, "output": "Summary", "llm_talent": "creative-writer", "prompt": "@text"}'

# Assemble a bundle from TOML parts
pipelex-agent assemble --domain my_domain --main-pipe main_workflow --output bundle.plx --concepts concepts.toml --pipes pipes.toml

# Check configuration health
pipelex-agent doctor
```

The `--inputs` flag accepts both file paths and inline JSON. If the value starts with `{`, it is parsed as JSON directly — no file creation needed for simple inputs.

## Common Errors

**`missing_input_variable`**: Add the missing input to the parent pipe's `inputs`. PipeSequence/PipeCondition must declare ALL inputs used by sub-pipes (except intermediate results).

**Inputs must be on one line**:
```toml
# WRONG
inputs = {
    a = "A",
    b = "B"
}

# CORRECT
inputs = { a = "A", b = "B" }
```

## Pipe Ordering

**Put controller pipes before the pipes they reference.** Place the main pipe first, then sub-pipes in execution order. This makes the workflow easier to read top-down.

## Complete Example

```toml
domain = "document_processing"
description = "Document processing workflows"
main_pipe = "process_invoice"

[concept.InvoiceData]
description = "Extracted invoice information"

[concept.InvoiceData.structure]
vendor = { type = "text", description = "Vendor name", required = true }
total = { type = "number", description = "Total amount", required = true }
items = { type = "list", item_type = "text", description = "Line items" }

# Main pipe first (controller)
[pipe.process_invoice]
type = "PipeSequence"
description = "Full invoice processing pipeline"
inputs = { document = "Document" }
output = "InvoiceData"
steps = [
    { pipe = "extract_from_pdf", result = "pages" },
    { pipe = "analyze_invoice", result = "invoice_data" }
]

# Then sub-pipes in execution order
[pipe.extract_from_document]
type = "PipeExtract"
description = "Extract content from document"
inputs = { document = "Document" }
output = "Page[]"
model = "@default-text-from-pdf"

[pipe.analyze_invoice]
type = "PipeLLM"
description = "Extract invoice data from text"
inputs = { page = "Page" }
output = "InvoiceData"
prompt = """
Extract invoice information from this document:

@page
"""
```
