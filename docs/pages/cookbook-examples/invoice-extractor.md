# Example: Invoice Extractor

This example provides a comprehensive pipeline for processing invoices. It takes a PDF invoice, extracts key information, and returns a structured `Invoice` object. It also demonstrates how to generate reports and track pipeline execution.

## Get the code

[**➡️ View on GitHub: examples/invoice_extractor.py**](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/invoice_extractor.py)

## The Pipeline Explained

The `process_invoice` pipeline is a complete workflow for invoice processing.

```python
async def process_invoice(pdf_url: str) -> ListContent[Invoice]:
    pipe_output = await execute_pipeline(
        pipe_code="process_invoice",
        input_memory={
            "document": PDFContent(url=pdf_url),
        },
    )

    return pipe_output.main_stuff_as_list(item_type=Invoice)
```

This example also showcases some of the powerful observer features of Pipelex. After the pipeline runs, it generates a cost report and a flowchart of the execution.

```python
# Print the cost reporting
get_report_delegate().generate_report()

# Print the flowchart url of the pipeline.
get_pipeline_tracker().output_flowchart()
```
This is invaluable for understanding the cost and the execution flow of your pipelines.

## The Data Structure: `Invoice` Model

The pipeline's output is a structured `Invoice` object. This is defined using Pydantic's `BaseModel`, which allows for clear, typed, and validated data.

```python
class Invoice(StructuredContent):
    """Invoice information extracted from text, supporting both formal bills and receipts"""

    invoice_id: Optional[str] = Field(None, description="Unique identifier for the invoice")
    invoice_number: Optional[str] = Field(None, description="Invoice number as shown on the document")
    date: Optional[datetime] = Field(None, description="Date when the invoice was issued")
    
    amount_incl_tax: Optional[float] = Field(None, description="Total amount including taxes")
    
    vendor: Optional[str] = Field(None, description="Name of the vendor/seller")
    
    # ... other fields
```

## The Pipeline Definition: `invoice.plx`

The entire workflow is defined in a PLX file. This declarative approach makes the pipeline easy to understand and modify. Here's a snippet from `invoice.plx`:

```plx
[pipe.process_invoice]
type = "PipeSequence"
description = "Process relevant information from an invoice"
inputs = { document = "PDF" }
output = "Invoice"
steps = [
    { pipe = "extract_text_from_image", result = "invoice_pages" },
    { pipe = "extract_invoice", batch_over = "invoice_pages", batch_as = "invoice_page", result = "invoice" },
]

[pipe.extract_text_from_image]
type = "PipeExtract"
description = "Extract page contents from an image"
inputs = { document = "PDF" }
output = "Page"
page_views = true
model = "base_extract_mistral"

[pipe.extract_invoice_data]
type = "PipeLLM"
description = "Extract invoice information from an invoice text transcript"
inputs = { "invoice_page.page_view" = "Image", invoice_details = "InvoiceDetails", invoice_page = "Page" }
output = "Invoice"
model = "llm_to_extract_invoice"
prompt = """
Extract invoice information from this invoice:

The category of this invoice is: $invoice_details.category.

@invoice_page.text_and_images.text.text
"""
```

This shows how a complex workflow, including text extraction with `PipeExtract` and LLM calls, can be defined in a simple, readable format. The `model = "llm_to_extract_invoice"` line is particularly powerful, as it tells the LLM to structure its output according to the `Invoice` model. 

## The Pipeline Flowchart

```mermaid
---
config:
  layout: dagre
  theme: base
---
flowchart LR
    subgraph "extract_invoice"
    direction LR
        ZynbH-branch-0["invoice_page:<br>**Page**"]
        RRYZF["invoice_details:<br>**Invoice details**"]
        RzjEzwGpkk5dXnrK3HXQJx-branch-0["invoice:<br>**Invoice**"]
        ZynbH["invoice_pages:<br>**List of [Page]**"]
        5SXqJ["invoice:<br>**List of [Invoice]**"]
    end
class extract_invoice sub_a;

    classDef sub_a fill:#e6f5ff,color:#333,stroke:#333;

    classDef sub_b fill:#fff5f7,color:#333,stroke:#333;

    classDef sub_c fill:#f0fff0,color:#333,stroke:#333;
    ZynbH-branch-0 -- "Analyze invoice" ----> RRYZF
    ZynbH-branch-0 -- "Extract invoice data" ----> RzjEzwGpkk5dXnrK3HXQJx-branch-0
    RRYZF -- "Extract invoice data" ----> RzjEzwGpkk5dXnrK3HXQJx-branch-0
    RzjEzwGpkk5dXnrK3HXQJx-branch-0 -...- 5SXqJ
    ZynbH -...- ZynbH-branch-0
```