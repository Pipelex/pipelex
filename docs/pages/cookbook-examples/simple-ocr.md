# Example: Simple OCR

This example demonstrates a basic OCR (Optical Character Recognition) pipeline. It takes a PDF file as input, extracts the text from each page, and saves the content.

This is a fundamental building block for many document processing workflows.

## Get the code

[**➡️ View on GitHub: examples/simple_ocr.py**](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/simple_ocr.py)

## The Pipeline Explained

The core of this example is a simple function that creates a "working memory" from a PDF and then executes a pre-defined pipeline called `ocr_page_contents_from_pdf`.

```python
async def simple_ocr(pdf_url: str):
    working_memory = WorkingMemoryFactory.make_from_pdf(
        pdf_url=pdf_url,
        concept_string="PDF",
        name="pdf",
    )
    pipe_output = await execute_pipeline(
        pipe_code="ocr_page_contents_from_pdf",
        working_memory=working_memory,
    )
    page_content_list: ListContent[PageContent] = pipe_output.main_stuff_as_list(item_type=PageContent)
    return page_content_list
```

This showcases how easy it is to kick off a complex process with just a few lines of code. 