---
title: "Invoice Extraction Example"
description: "Extract structured invoice data from PDF documents using a multi-step Pipelex pipeline with vision-based LLM analysis."
---

# Example: Invoice Extraction

This example processes PDF invoices through a multi-step pipeline: extract pages with views, classify the invoice type, then extract structured data using vision.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/b_basics/document_extract/extract_invoice/bundle.mthds)

## What it demonstrates

- Rich structured concept (`Invoice` with 14+ fields including nested `InvoiceDetails`)
- Nested `PipeSequence` (main pipeline batches over pages, sub-pipeline does analyze then extract)
- Vision-based extraction using page views and OCR text
- Using shared method packages for page extraction

## The Method: `bundle.mthds`

### Invoice concept

```toml
[concept.Invoice]
description = "Invoice information extracted from text, supporting both formal bills and receipts"

[concept.Invoice.structure]
invoice_id        = { type = "text", description = "Unique identifier for the invoice" }
invoice_number    = { type = "text", description = "Invoice number as shown on the document" }
date              = { type = "date", description = "Date when the invoice was issued" }
amount_incl_tax   = { type = "number", description = "Total amount including taxes" }
amount_excl_tax   = { type = "number", description = "Net amount excluding taxes" }
vendor            = { type = "text", description = "Name of the vendor/seller" }
category          = { type = "concept", concept_ref = "invoice_extraction.InvoiceDetails", description = "Category or type of expense" }
# ... and more fields
```

### Pipeline

```toml
[pipe.process_invoice]
type = "PipeSequence"
inputs = { document = "Document" }
output = "Invoice[]"
steps = [
  { pipe = "github.com/Pipelex/methods/documents->documents.extract_page_contents_and_views", result = "invoice_pages" },
  { pipe = "extract_invoice", batch_over = "invoice_pages", batch_as = "invoice_page", result = "invoice" },
]
```

Each page goes through a sub-pipeline that first classifies the invoice type (bill vs. receipt), then extracts the full structured data using both the page view and OCR text:

```toml
[pipe.extract_invoice]
type = "PipeSequence"
inputs = { invoice_page = "Page" }
output = "Invoice"
steps = [
  { pipe = "analyze_invoice", result = "invoice_details" },
  { pipe = "extract_invoice_data", result = "invoice" },
]
```

## How to run

```bash
pipelex run bundle examples/b_basics/document_extract/extract_invoice/bundle.mthds \
  -i examples/b_basics/document_extract/extract_invoice/inputs.json
```

## Related Documentation

- [PipeExtract Operator](../building-methods/pipes/pipe-operators/PipeExtract.md) - Extract text and images from documents
- [PipeLLM Operator](../building-methods/pipes/pipe-operators/PipeLLM.md) - The core operator for LLM interactions
- [PipeSequence Controller](../building-methods/pipes/pipe-controllers/PipeSequence.md) - Chain pipes into sequential workflows
- [Document Extraction](../features/document-extraction.md) - Overview of document extraction capabilities
