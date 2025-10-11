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
        concept_string="PDF",
        name="pdf",
    )
    pipe_output = await execute_pipeline(
        pipe_code="power_extractor_proof_of_purchase",
        working_memory=working_memory,
    )
    working_memory = pipe_output.working_memory
    proof_of_purchase: ProofOfPurchase = working_memory.get_list_stuff_first_item_as(name="proof_of_purchase", item_type=ProofOfPurchase)
    return proof_of_purchase
```

This is a great starting point for building more complex expense processing or accounting automation pipelines.

## The Data Structure: `ProofOfPurchase` Model

The pipeline is designed to extract a `ProofOfPurchase` object, which is a structured model that includes a list of `Products`.

```python
class Products(StructuredContent):
    name: Optional[str] = None
    quantity: Optional[int] = None
    unit_price: Optional[float] = None
    total_price: Optional[float] = None


class ProofOfPurchase(StructuredContent):
    date_of_purchase: Optional[datetime] = None
    amount_paid: Optional[float] = None
    currency: Optional[str] = None
    payment_method: Optional[str] = None
    purchase_number: Optional[str] = None
    products: Optional[List[Products]] = None
```
This demonstrates how you can create nested data structures to accurately model your data.

## The Pipeline Definition: `extract_proof_of_purchase.plx`

The pipeline uses a powerful `PipeLLM` to extract the structured data from the document. The prompt is carefully engineered to guide the LLM.

```plx
[pipe.write_markdown_from_page_content_proof_of_purchase]
type = "PipeLLM"
description = "Write markdown from page content"
inputs = { "page_content.page_view" = "Page" } # The LLM receives the image of the page
output = "ProofOfPurchase" # The LLM is forced to output a ProofOfPurchase object
llm = "llm_for_img_to_text"
structuring_method = "preliminary_text"
system_prompt = """You are a multimodal LLM, expert at converting images into perfect markdown."""
prompt_template = """
You are given an image of a proof of purchase.
Your role is to convert the image into perfect markdown.

To help you do so, you are given the text extracted from the page by an OCR model.
@page_content.text_and_images.text.text

- Ensure you collect every title, number, and currency from the proof of purchase.
- Pay attention to the text alignment, it might have been misaligned by the OCR.
- The OCR extraction may be highly incomplete. It is your job to complete the text and add the missing information using the image.
- Output only the markdown, nothing else. No need for "```markdown" or "```".
- You can use HTML if it helps you.
- You can use tables if it is relevant.
"""
```
The combination of a detailed prompt, the OCR text, and the document image allows the LLM to accurately extract the required information and structure it as a `ProofOfPurchase` object. 
