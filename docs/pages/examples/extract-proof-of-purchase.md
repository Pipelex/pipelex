# Example: Proof of Purchase Extraction

This example demonstrates a pipeline designed to extract structured data from a proof of purchase, such as a receipt or an invoice.

## Get the code

[**➡️ View on GitHub: examples/extract_proof_of_purchase.py**](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/extract_proof_of_purchase.py)

## The Pipeline Explained

The pipeline `power_extractor_proof_of_purchase` is specifically designed to handle receipts and invoices. It extracts key information and returns a structured `ProofOfPurchase` object.

```python
async def extract_proof_of_purchase(pdf_url: str) -> ProofOfPurchase:
    working_memory = WorkingMemoryFactory.make_from_pdf(
        pdf_url=pdf_url,
        concept_str="PDF",
        name="pdf",
    )
    pipe_output, _ = await execute_pipeline(
        pipe_code="power_extractor_proof_of_purchase",
        working_memory=working_memory,
    )
    working_memory = pipe_output.working_memory
    proof_of_purchase: ProofOfPurchase = working_memory.get_list_stuff_first_item_as(name="proof_of_purchase", item_type=ProofOfPurchase)
    return proof_of_purchase
```

This is a great starting point for building more complex expense processing or accounting automation pipelines. 