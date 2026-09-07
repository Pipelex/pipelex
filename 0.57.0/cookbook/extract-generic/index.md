# Example: Generic Document Extraction

This example demonstrates a generic pipeline for extracting content from complex PDF documents. It extracts pages with views, then converts each page to markdown using a vision-capable LLM that combines OCR text with the page image.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/b_basics/document_extract/extract_generic/bundle.mthds)

## What it demonstrates

- Vision-based page-to-markdown conversion using `PipeLLM` with `$vision` model
- Using shared method packages for page extraction
- Batching over pages to process each one independently
- Combining OCR text with page images for accurate extraction

## The Method: `bundle.mthds`

```toml
domain    = "extract_generic"
main_pipe = "power_extractor"

[pipe.power_extractor]
type = "PipeSequence"
description = "Update page content with markdown"
inputs = { document = "Document" }
output = "Text[]"
steps = [
  { pipe = "github.com/Pipelex/methods/documents->documents.extract_page_contents_and_views",
    result = "page_contents" },
  { pipe = "write_markdown_from_page_content",
    batch_over = "page_contents", batch_as = "page_content",
    result = "markdowns" },
]

[pipe.write_markdown_from_page_content]
type = "PipeLLM"
description = "Write markdown from page content"
inputs = { "page_content.page_view" = "Image", page_content = "Page" }
output = "Text"
model = "$vision"
system_prompt = "You are a multimodal LLM, expert at converting images into perfect markdown."
prompt = """
You are given an image which is a view of a document page: $page_content.page_view
You are also given the text extracted from the page by an OCR model.
Your task is to output the perfect markdown of the page.

Here is the text extracted from the page:
{{ page_content.text_and_images.text.text|tag("ocr_text") }}

- Ensure you do not miss any information from the page.
- Output only the markdown, nothing else.
"""
```

## How to run

```bash
pipelex run bundle examples/b_basics/document_extract/extract_generic/bundle.mthds \
  -i examples/b_basics/document_extract/extract_generic/inputs.json
```

## Related Documentation

- [PipeExtract Operator](../building-methods/pipes/pipe-operators/PipeExtract.md) - Extract text and images from documents
- [PipeLLM Operator](../building-methods/pipes/pipe-operators/PipeLLM.md) - The core operator for LLM interactions
- [Document Extraction](../features/document-extraction.md) - Overview of document extraction capabilities
