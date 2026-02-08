# Manual Build Phases — Detailed Examples

Detailed examples, ASCII diagrams, and CLI commands for each phase of the manual 9-phase build process. See `build/SKILL.md` for the concise workflow.

## Phase 2: ASCII Overview Diagram

```
┌─────────────────────────────────────────────────────┐
│                   workflow_name                     │
│  Domain: my_domain                                  │
├─────────────────────────────────────────────────────┤
│                                                     │
│   [Input1]  ──────►  ┌──────────────┐               │
│   [Input2]  ──────►  │  main_pipe   │  ──────►  [Output]
│                      │  (Sequence)  │               │
│                      └──────────────┘               │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Phase 5: Controller Flow Diagrams

### Sequence Flow
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Step 1    │────►│   Step 2    │────►│   Step 3    │
│  (PipeLLM)  │     │  (PipeLLM)  │     │ (Compose)   │
└─────────────┘     └─────────────┘     └─────────────┘
     │                   │                   │
     ▼                   ▼                   ▼
 [analysis]         [refined]           [output]
```

### Batch Flow (map operation)
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

### Parallel Flow
```
                    ┌─────────────┐
               ┌───►│  Branch A   │───┐
               │    └─────────────┘   │
┌─────────┐    │    ┌─────────────┐   │    ┌──────────┐
│  Input  │────┼───►│  Branch B   │───┼───►│ Combined │
└─────────┘    │    └─────────────┘   │    └──────────┘
               │    ┌─────────────┐   │
               └───►│  Branch C   │───┘
                    └─────────────┘
```

### Condition Flow
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

## Phase 7: Pipe Type CLI Examples

### PipeLLM
```bash
pipelex-agent pipe --type PipeLLM --spec '{
  "pipe_code": "summarize_document",
  "description": "Summarize document content",
  "inputs": {"document": "Document"},
  "output": "Summary",
  "llm_talent": "creative-writer",
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

### PipeCompose — Template mode (via CLI)
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

### PipeCompose — Construct mode (write directly to .plx)
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
- `{from = "variable.path"}` — Reference input or nested field
- `{template = "text with $var"}` — String interpolation
- `"value"` or `123` — Static/fixed values

### PipeParallel
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

### PipeExtract
```bash
pipelex-agent pipe --type PipeExtract --spec '{
  "pipe_code": "extract_pages",
  "description": "Extract text from document",
  "inputs": {"document": "Document"},
  "output": "Page[]",
  "extract_talent": "pdf-basic-text-extractor"
}'
```

### PipeImgGen
```bash
pipelex-agent pipe --type PipeImgGen --spec '{
  "pipe_code": "generate_image",
  "description": "Generate image from prompt",
  "inputs": {"img_prompt": "ImgGenPrompt"},
  "output": "Image",
  "img_gen_talent": "gen-image",
  "prompt": "$img_prompt"
}'
```

### Parallel Conversion Example (multiple pipes at once)
```bash
# Call all pipe commands in parallel (single response, multiple tool calls):
pipelex-agent pipe --type PipeLLM --spec '{"pipe_code": "summarize", "description": "Summarize document", "inputs": {"document": "Document"}, "output": "Summary", "llm_talent": "creative-writer", "prompt": "Summarize:\n\n@document"}'
pipelex-agent pipe --type PipeExtract --spec '{"pipe_code": "extract_pages", "description": "Extract text from document", "inputs": {"document": "Document"}, "output": "Page[]", "extract_talent": "pdf-basic-text-extractor"}'
pipelex-agent pipe --type PipeLLM --spec '{"pipe_code": "analyze", "description": "Analyze content", "inputs": {"pages": "Page[]"}, "output": "Analysis", "llm_talent": "engineer", "prompt": "Analyze:\n\n@pages"}'
pipelex-agent pipe --type PipeSequence --spec '{"pipe_code": "main_workflow", "description": "Main orchestration", "inputs": {"document": "Document"}, "output": "Analysis", "steps": [{"pipe": "extract_pages", "result": "pages"}, {"pipe": "analyze", "result": "analysis"}]}'
```

## Phase 8: Assemble Bundle

Save concept and pipe TOML to temporary files, then assemble:

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
