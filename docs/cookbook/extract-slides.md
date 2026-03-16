---
title: "Extract Slides from Presentation"
description: "Extract slide content and descriptions from presentation documents using vision-based LLM analysis with Pipelex."
---

# Example: Extract Slides from Presentation

This example extracts structured slide information from a presentation document — including titles, content as markdown, and visual descriptions of each slide layout.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/b_basics/document_extract/extract_slides/bundle.mthds)

## What it demonstrates

- Custom `Slide` concept with inline structure (title, text, description)
- Vision-based slide analysis using `PipeLLM` with page views
- Batching over extracted pages to process each slide individually
- `PipeCompose` for assembling structured output into formatted text

## The Method: `bundle.mthds`

### Slide concept

```toml
[concept.Slide]
description = "A slide from a presentation"

[concept.Slide.structure]
title         = { type = "text", description = "The title of the slide" }
text_markdown = { type = "text", description = "The content of the slide as markdown" }
description   = { type = "text", description = "A description of the slide: layout of the text, description of the graphics" }
```

### Pipeline

The pipeline extracts pages with views, describes each slide using a vision model, then concatenates the descriptions:

```toml
[pipe.extract_slides]
type = "PipeSequence"
description = "Extract markdown from a document"
inputs = { document = "Document" }
output = "Text"
steps = [
  { pipe = "extract_markdown_and_views_from_document", result = "pages" },
  { pipe = "describe_slide", batch_over = "pages", batch_as = "page", result = "slides" },
  { pipe = "concatenate_slide_descriptions", result = "slides_description" },
]
```

## How to run

```bash
pipelex run bundle examples/b_basics/document_extract/extract_slides/bundle.mthds \
  -i examples/b_basics/document_extract/extract_slides/inputs.json
```

## Related Documentation

- [PipeLLM Operator](../building-methods/pipes/pipe-operators/PipeLLM.md) - The core operator for LLM interactions
- [PipeExtract Operator](../building-methods/pipes/pipe-operators/PipeExtract.md) - Extract text and images from documents
- [PipeCompose Operator](../building-methods/pipes/pipe-operators/PipeCompose.md) - Template-based data composition
