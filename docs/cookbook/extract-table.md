---
title: "Table Extraction from Image"
description: "Turn table images into structured HTML with Pipelex — using an extract-and-review self-correction pattern."
---

# Example: Table Extraction from Image

This example extracts a table from an image and converts it into structured HTML. It uses a two-step "extract and review" pattern where the first pipe does the initial extraction and the second pipe reviews the result against the original image to correct errors.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/b_basics/document_extract/extract_table/bundle.mthds)

## What it demonstrates

- Self-correction pattern: extract then review against the original image
- Custom structured concept (`HtmlTable` with title and HTML content)
- Vision-based extraction using `$vision-table` model
- Multi-modal inputs (image + structured data) in a single pipe

## The Method: `bundle.mthds`

### Pipeline

```toml
[pipe.extract_html_table_and_review]
type = "PipeSequence"
description = "Get an HTML table and review it"
inputs = { table_screenshot = "TableScreenshot" }
output = "HtmlTable"
steps = [
    { pipe = "extract_html_table_from_image", result = "html_table" },
    { pipe = "review_html_table", result = "reviewed_html_table" },
]

[pipe.review_html_table]
type = "PipeLLM"
description = "Review an HTML table"
inputs = { table_screenshot = "TableScreenshot", html_table = "HtmlTable" }
output = "HtmlTable"
prompt = """
Your role is to correct an html_table to make sure that it matches the one in the provided image: $table_screenshot

@html_table

Pay attention to the text and formatting (color, borders, ...).
Rewrite the entire html table with your potential corrections.
Make sure you do not forget any text.
"""
```

This self-correction pattern is a key technique for building robust AI methods — the first step provides a draft, and the second step verifies and corrects it against the source.

## How to run

```bash
pipelex run bundle examples/b_basics/document_extract/extract_table/bundle.mthds \
  -i examples/b_basics/document_extract/extract_table/inputs.json
```

## Related Documentation

- [PipeLLM Operator](../building-methods/pipes/pipe-operators/PipeLLM.md) - The core operator for LLM interactions
- [PipeSequence Controller](../building-methods/pipes/pipe-controllers/PipeSequence.md) - Chain pipes into sequential workflows
