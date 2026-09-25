# Example: Extract Markdown from Document

This example extracts text from a PDF document and composes the pages into a single clean markdown output. It leverages the shared `documents` method package for page extraction.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/b_basics/document_extract/extract_markdown/bundle.mthds)

## What it demonstrates

- Using shared method packages (`github.com/Pipelex/methods/documents`)
- `PipeCompose` with Jinja2 templates to concatenate page text
- Simple two-step document-to-markdown pipeline

## The Method: `bundle.mthds`

The pipeline uses a shared extraction pipe and then composes all pages into a single text:

```toml
domain      = "extract_markdown"
main_pipe   = "extract_markdown_from_document"

[pipe.extract_markdown_from_document]
type = "PipeSequence"
description = "Extract markdown from a document"
inputs = { document = "Document" }
output = "Text"
steps = [
  { pipe = "github.com/Pipelex/methods/documents->documents.extract_markdown_pages", result = "pages" },
  { pipe = "write_markdown_from_pages", result = "markdown" },
]

[pipe.write_markdown_from_pages]
type = "PipeCompose"
description = "Write markdown from pages"
inputs = { pages = "Page[]" }
output = "Text"
template = """
{% for page in pages %}
{{ page.text_and_images.text }}
{% endfor %}
"""
```

## How to run

```bash
pipelex run bundle examples/b_basics/document_extract/extract_markdown/bundle.mthds \
  -i examples/b_basics/document_extract/extract_markdown/inputs.json
```

## Related Documentation

- [PipeExtract Operator](../building-methods/pipes/pipe-operators/PipeExtract.md) - Extract text and images from documents
- [PipeCompose Operator](../building-methods/pipes/pipe-operators/PipeCompose.md) - Template-based data composition
- [Packages](../building-methods/packages.md) - Using shared method packages
