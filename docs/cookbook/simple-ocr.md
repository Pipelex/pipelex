---
title: "Simple OCR Example"
description: "Build a basic OCR pipeline with Pipelex. Extract text from PDF pages and save the content — a fundamental building block for document processing methods."
---

# Example: Simple OCR

This example demonstrates a basic OCR (Optical Character Recognition) pipeline. It takes a PDF file as input, extracts the text from each page, and saves the content.

This is a fundamental building block for many document processing methods.

## Get the code

[**➡️ View on GitHub: examples/a_quick_start/simple_ocr.py**](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/a_quick_start/simple_ocr.py)

## The Pipeline Explained

The core of this example is a simple function that executes a pre-defined pipeline called `extract_page_contents_from_pdf`.

```python
async def simple_ocr(pdf_url: str) -> ListContent[PageContent]:
    pipe_output = await execute_pipeline(
        pipe_code="extract_page_contents_from_pdf",
        inputs={
            "document": DocumentContent(url=pdf_url),
        },
    )
    page_content_list: ListContent[PageContent] = pipe_output.main_stuff_as_list(item_type=PageContent)
    return page_content_list
```

This showcases how easy it is to kick off a complex process with just a few lines of code. The `inputs` dictionary simply maps the input name to the PDF content, and the pipeline handles the rest.

## Related Documentation

- [PipeExtract Operator](../building-methods/pipes/pipe-operators/PipeExtract.md) - Extract text and images from documents
- [Document Extraction](../features/document-extraction.md) - Overview of document extraction capabilities