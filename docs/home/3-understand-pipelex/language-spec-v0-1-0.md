# Pipelex Language Spec v0.1.0

The Pipelex Language (PLX) uses a TOML-based syntax to define deterministic, repeatable AI workflows. This specification documents version 0.1.0 of the language and establishes the canonical way to declare domains, concepts, and pipes inside `.plx` bundles.

## File structure

A `.plx` file is composed of three top-level sections:

- **Metadata**: required `domain` and optional `description` fields that scope every concept and pipe in the file.
- **Concept declarations**: a `[concept]` table that maps concept codes to descriptions or structured definitions.
- **Pipe declarations**: a `[pipe]` table containing one table per pipe or controller, keyed by its snake_case code.

Use one bundle per problem domain and keep the file self-contained by declaring the concepts and pipes it needs.

## Naming conventions

- Concepts must be **PascalCase** nouns (for example `Invoice`, `CustomerProfile`).
- Pipe codes must be **snake_case** verbs (for example `extract_header`, `analyze_image`).
- Input and output variable names must be **snake_case** and describe their role (for example `invoice_pdf`, `analysis`).
- Reuse the same concept across the file when the semantic meaning is the same; avoid duplicating similar concepts with different adjectives.

## Metadata block

Every bundle starts with metadata values at the root of the file:

```plx
domain = "my_domain"
description = "Human-readable description of what the bundle does."
```

The `domain` is mandatory and establishes the namespace for all concepts and pipes defined in the file.

## Concept declarations

Concepts describe the structured or unstructured knowledge that flows through pipes. Declare them inside a single `[concept]` table.

### Simple concepts

Use a string to document simple, unstructured concepts such as `Text`, `Image`, `PDF`, `Number`, or `Page`:

```plx
[concept]
UserBrief = "A short, natural-language description of what the user wants."

[concept.InvoicePdf]
description = "A PDF that represents an invoice"
refines = "PDF"
```

### Structured concepts

Provide a structured concept using nested tables that define a description and a `structure` table of fields:

```plx
[concept.Invoice]
description = "Information extracted from an invoice"

[concept.Invoice.structure]
supplier_name = { type = "Text", description = "Name of the issuer", required = true }
invoice_date = { type = "Date", description = "ISO-8601 date", required = true }
total = { type = "Number", description = "Total amount due" }
```

Field objects support these keys:

- `name`: snake_case field code.
- `description`: plain-language explanation of the field.
- `type`: `Text`, `Number`, `Boolean`, `Date`, `Image`, `PDF`, or another concept name.
- `required`: optional boolean; omit or set to `false` when the field is optional.
- `default_value`: optional literal default.

Use structured concepts only when downstream pipes need typed fields; otherwise prefer concise textual descriptions.

## Pipe declarations

Pipes perform work and produce outputs. Each pipe is declared as its own table under `[pipe]` using the pipe code as the suffix:

```plx
[pipe.extract_invoice]
type = "PipeLLM"
description = "Extract invoice details"
inputs = { invoice_pdf = "InvoicePdf" }
output = "Invoice"
model = "llm_to_engineer"
prompt = """
Extract the supplier name, invoice_date, and total from the provided PDF.
"""
```

Common keys for all pipes include:

- `type`: required operator or controller (`PipeLLM`, `PipeExtract`, `PipeImgGen`, `PipeFunc`, `PipeSequence`, `PipeParallel`, `PipeBatch`, `PipeCondition`).
- `description`: human-readable explanation of the pipe's purpose.
- `inputs`: table mapping input variable names to concept codes; dotted paths are allowed for nested attributes (for example `page_content.page_view`).
- `output`: concept code returned by the pipe; omit when the operator is side-effect-only.

### Pipe operators

Each operator type supports additional fields:

- **PipeLLM**: `model`, `prompt`, optional `format_mode`, `temperature`, `top_p`, `max_output_tokens`, and `working_memory` hints.
- **PipeExtract**: `model`, optional `page_images`, `page_views`, `page_views_dpi`, and `page_image_captions` controls for OCR outputs.
- **PipeImgGen**: `model`, `prompt`, `image_count`, and optional image sizing controls.
- **PipeFunc**: `function_name` registered in the function registry and an `output` concept for the return value.

Place long prompts inside triple-quoted strings to preserve formatting.

### Pipe controllers

Controllers orchestrate other pipes using their `steps` or branching configuration:

- **PipeSequence** executes steps in order.
- **PipeParallel** runs multiple pipes concurrently.
- **PipeBatch** maps a single pipe over items from a list in working memory.
- **PipeCondition** dispatches to specific pipes based on an evaluated expression.

#### Sequence and parallel steps

Define the execution plan with a `steps` array of inline tables:

```plx
[pipe.process_invoice]
type = "PipeSequence"
description = "End-to-end invoice processing"
inputs = { invoice_pdf = "InvoicePdf" }
output = "Invoice"
steps = [
    { pipe = "extract_invoice", result = "extracted_invoice" },
    { pipe = "quality_check", result = "validated_invoice" }
]
```

Each step supports:

- `pipe`: referenced pipe code defined elsewhere in the file.
- `result`: variable name to store the output in working memory.
- `batch_over` and `batch_as`: for `PipeBatch`, specify the list variable to iterate over and the alias for each item.
- `inputs`: optional table to override or augment inputs for the called pipe.

#### Conditional branching

`PipeCondition` defines an `expression` evaluated against working memory and an `outcomes` map of expression results to pipe codes. Optionally add a `default` pipe when no outcomes match.

```plx
[pipe.route_document]
type = "PipeCondition"
description = "Route documents based on detected type"
inputs = { document = "Text" }
output = "Text"
expression = "document.type"
outcomes = { invoice = "extract_invoice", contract = "extract_contract" }
default = "extract_generic"
```

## Working memory

Pipe outputs are automatically added to working memory under their `result` names (or the pipe code when `result` is omitted). Later pipes can refer to any available variable, including list items produced by `PipeBatch`. Keep result names consistent and descriptive to avoid collisions.

## Validation rules

- Every pipe and concept referenced in the file must be declared in the same bundle or imported via the runtime library of native concepts.
- Controller steps must reference existing pipe codes.
- Input and output concept codes must match the declared concepts or native concepts.
- Use exhaustive `outcomes` for `PipeCondition` where possible; add a `default` handler to remain forward-compatible.

## Versioning

This document describes **Pipelex Language Spec v0.1.0**. Future versions will maintain backward compatibility whenever possible; breaking changes will increment the minor or major version and be documented in release notes.
