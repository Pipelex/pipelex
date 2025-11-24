# Pipelex (PLX) – Declarative AI Workflow Spec (v0.1.0)

**Build deterministic, repeatable AI workflows using declarative TOML syntax.**

The Pipelex Language (PLX) uses a TOML-based syntax to define deterministic, repeatable AI workflows. This specification documents version 0.1.0 of the language and establishes the canonical way to declare domains, concepts, and pipes inside `.plx` bundles.

---

## Core Idea

Pipelex is a workflow declaration language that gets interpreted into a runtime. Each `.plx` file represents a **domain** (named in snake_case) and declares a complete workflow. The workflow is interpreted and executed by a runtime—currently, the only available runtime is Python (see [github.com/pipelex/pipelex](https://github.com/pipelex/pipelex)).

Pipelex lets you declare **what** your AI workflow should accomplish and **how** to execute it step by step. You define:

- **Concepts** (PascalCase): the structured or unstructured data flowing through your system
- **Pipes** (snake_case): operations or orchestrators that define your workflow

Write once in `.plx` files. Run anywhere. Get the same results every time.

---

## Semantics

Pipelex workflows are **declarative and deterministic**:

- Pipes are evaluated based on their dependencies, not declaration order
- Controllers explicitly define execution flow (sequential, parallel, or conditional)

All concepts are strongly typed. All pipes declare their inputs and outputs. The runtime validates that data flowing between pipes matches the declared types before execution.

---

## Guarantees & Limits

**Guarantees:**

- Deterministic workflow execution and outputs
- Strong typing with validation before runtime
- Reproducible results across environments
- Self-contained bundles (one domain per file)

**Not supported in v0.1.0:**

- Dynamic pipe generation at runtime
- Mutable working memory (pipes produce new values, not modify existing ones)
- Cross-bundle dependencies (each `.plx` file is independent)

**More:**

- Full spec: [language-spec-v0-1-0.md](language-spec-v0-1-0.md)
- GitHub: [github.com/pipelex/pipelex](https://github.com/pipelex/pipelex)

---

## Complete Example: Invoice Processing Workflow

This workflow extracts structured data from invoice PDFs and validates the totals.

```toml
# invoice_processor.plx
domain = "invoice_processing"
description = "Extract and validate invoice data from PDFs"

# Define data types
[concept]
InvoicePdf = "A PDF file containing an invoice"

[concept.Invoice]
description = "Structured invoice data"

[concept.Invoice.structure]
supplier_name = { type = "Text", description = "Name of the supplier", required = true }
invoice_date = { type = "Date", description = "Invoice date (ISO-8601)", required = true }
line_items = { type = "Text", description = "List of line items with amounts", required = true }
total_amount = { type = "Number", description = "Total invoice amount", required = true }

[concept.ValidationReport]
description = "Invoice validation results"

[concept.ValidationReport.structure]
is_valid = { type = "Boolean", description = "Whether totals match", required = true }
discrepancy = { type = "Number", description = "Difference if any", required = false }
notes = { type = "Text", description = "Validation notes", required = false }

# Define operations
[pipe.extract_invoice_data]
type = "PipeLLM"
description = "Extract structured fields from invoice PDF"
inputs = { invoice_pdf = "InvoicePdf" }
output = "Invoice"
model = "llm_to_engineer"
prompt = """
Extract the following from the invoice:
- Supplier name
- Invoice date (ISO-8601 format)
- All line items with their amounts
- Total amount

Be precise with numbers and dates.
"""

[pipe.validate_totals]
type = "PipeLLM"
description = "Validate that line items sum to total"
inputs = { invoice = "Invoice" }
output = "ValidationReport"
model = "llm_to_engineer"
prompt = """
Check if the line items sum to the total amount.
Calculate any discrepancy and note your findings.
"""

[pipe.generate_summary_image]
type = "PipeImgGen"
description = "Create a visual summary of the validated invoice"
inputs = { invoice = "Invoice", validation = "ValidationReport" }
output = "Image"
model = "dall-e-3"
img_gen_prompt = """
Create a clean, professional invoice summary visualization showing:
- Supplier: {{ invoice.supplier_name }}
- Date: {{ invoice.invoice_date }}
- Total: ${{ invoice.total_amount }}
- Status: {{ "VALID" if validation.is_valid else "DISCREPANCY FOUND" }}
"""

# Orchestrate the workflow
[pipe.process_invoice]
type = "PipeSequence"
description = "Complete invoice processing pipeline"
inputs = { invoice_pdf = "InvoicePdf" }
output = "Image"
steps = [
    { pipe = "extract_invoice_data", result = "invoice" },
    { pipe = "validate_totals", result = "validation" },
    { pipe = "generate_summary_image", result = "summary_image" }
]
```

**What happens:**

1. **Extract** – The `PipeLLM` reads the PDF and produces structured `Invoice` data
2. **Validate** – Another `PipeLLM` checks if line items match the total and produces a `ValidationReport`
3. **Visualize** – `PipeImgGen` creates a summary image using both results
4. **Orchestrate** – `PipeSequence` runs all three steps in order, passing data through working memory

Every run with the same PDF produces the same extracted data, validation, and summary image.

