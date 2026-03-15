---
title: "Proof of Purchase Extraction"
description: "Extract structured data from receipts and invoices using vision-based AI — including products, amounts, and payment details."
---

# Example: Proof of Purchase Extraction

This example extracts structured data from receipts and invoices. It defines nested data concepts (`Product` inside `ProofOfPurchase`) and uses vision-based extraction to capture all details from the document.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/b_basics/document_extract/extract_proof_of_purchase/bundle.mthds)

## What it demonstrates

- Nested structured concepts (`Product` referenced inside `ProofOfPurchase`)
- Vision-based extraction with `$vision` model and `structuring_method = "preliminary_text"`
- Using shared method packages for page extraction
- Batching over pages to process each independently

## The Method: `bundle.mthds`

### Concepts

```toml
[concept.Product]
description = "A product in a proof of purchase"

[concept.Product.structure]
name        = { type = "text", description = "Name of the product" }
quantity    = { type = "integer", description = "Quantity purchased" }
unit_price  = { type = "number", description = "Unit price of the product" }
total_price = { type = "number", description = "Total price for this product" }

[concept.ProofOfPurchase]
description = "Elements from a proof of purchase"

[concept.ProofOfPurchase.structure]
date_of_purchase = { type = "date", description = "Date of the purchase" }
amount_paid      = { type = "number", description = "Total amount paid" }
currency         = { type = "text", description = "Currency used for the purchase" }
payment_method   = { type = "text", description = "Method of payment used" }
purchase_number  = { type = "text", description = "Purchase or receipt number" }
products         = { type = "list", item_type = "concept",
                     item_concept_ref = "extract_proof_of_purchase.Product",
                     description = "List of products purchased" }
```

### Pipeline

```toml
[pipe.power_extractor_proof_of_purchase]
type = "PipeSequence"
inputs = { document = "Document" }
output = "ProofOfPurchase[]"
steps = [
  { pipe = "github.com/Pipelex/methods/documents->documents.extract_page_contents_and_views",
    result = "page_contents" },
  { pipe = "write_markdown_from_page_content_proof_of_purchase",
    batch_over = "page_contents", batch_as = "page_content",
    result = "proof_of_purchase" },
]
```

## How to run

```bash
pipelex run bundle examples/b_basics/document_extract/extract_proof_of_purchase/bundle.mthds \
  -i examples/b_basics/document_extract/extract_proof_of_purchase/inputs.json
```

## Related Documentation

- [PipeLLM Operator](../building-methods/pipes/pipe-operators/PipeLLM.md) - The core operator for LLM interactions
- [Document Extraction](../features/document-extraction.md) - Overview of document extraction capabilities
