# Example: Invoice Extractor

This example provides a comprehensive pipeline for processing invoices. It takes a PDF invoice, extracts key information, and returns a structured `Invoice` object. It also demonstrates how to generate reports and track pipeline execution.

## Get the code

[**➡️ View on GitHub: examples/invoice_extractor.py**](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/invoice_extractor.py)

## The Pipeline Explained

The `process_invoice` pipeline is a complete workflow for invoice processing.

```python
async def process_expense_report() -> ListContent[Invoice]:
    invoice_pdf_path = "assets/invoice_extractor/invoice_1.pdf"

    # Create Stuff objects
    working_memory = WorkingMemoryFactory.make_from_pdf(
        pdf_url=invoice_pdf_path,
        name="invoice_pdf",
    )
    pipe_output, _ = await execute_pipeline(
        pipe_code="process_invoice",
        working_memory=working_memory,
    )

    return pipe_output.main_stuff_as_list(item_type=Invoice)
```

This example also showcases some of the powerful observability features of Pipelex. After the pipeline runs, it generates a cost report and a flowchart of the execution.

```python
# Print the cost reporting
get_report_delegate().generate_report()

# Print the flowchart url of the pipeline.
get_pipeline_tracker().output_flowchart()
```
This is invaluable for understanding the cost and the execution flow of your pipelines. 