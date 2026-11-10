---
title: "Document Extraction"
description: "Multi-provider OCR and document processing with Mistral OCR, Azure Document Intelligence, docling, and Linkup Fetch. PDF processing, web page extraction, layout analysis, and table recognition."
---

# Document Extraction

Multi-provider OCR, document processing, and web content extraction with a unified interface.

## Overview

From simple text extraction to advanced document understanding — Pipelex handles it all. Basic PDF text extraction works out of the box (via pypdfium2), but real documents demand more: OCR for scanned pages, layout analysis for complex structures, image extraction, and VLM-powered understanding.

Unlike LLM APIs (partly standardized around OpenAI's completions API), the OCR landscape is fragmented. Pipelex solves this with a unified interface: swap providers by changing your PipeExtract config, no code changes required. For web pages, Linkup Fetch extracts content directly from URLs using the same PipeExtract pattern.

## Supported Providers

| Provider | Type | Description |
|----------|------|-------------|
| **pypdfium2** | Built-in | Basic PDF text and image extraction without AI inference — works out of the box with no API keys |
| **Mistral OCR** | Cloud API | Industry-leading document understanding for media, text, tables, and equations |
| **docling** | Local SDK | IBM's open-source extraction library with local CPU processing and optional GPU acceleration |
| **Linkup Fetch** | Cloud API | Web page content extraction — fetches and extracts text from web URLs |

## The Default Extractor

A `PipeExtract` step that names no model uses `@default-extract-document`, which tries Mistral OCR, then `pypdfium2-extract-pdf`, and takes the first one an enabled backend serves. Mistral OCR is served by the `mistral` backend with your own `MISTRAL_API_KEY`; without it, a PDF is read locally from its text layer, which needs no key but recovers no text from a scanned page, and the run logs that it fell back. `@default-extract-image` and `@default-premium` try Mistral OCR only, so they need the `mistral` backend. Name a model in the step, or point the aliases elsewhere in `x_custom_extract_deck.toml`, to choose differently.

## Formats Each Extractor Reads

Each extract model declares the file formats it reads, and a `PipeExtract` step can only extract a file in one of those formats.

| Extract model | Reads |
|---------------|-------|
| `pypdfium2-extract-pdf` | PDF |
| `docling-extract-text` | PDF, Word (`.docx`), PowerPoint (`.pptx`), Excel (`.xlsx`), HTML, Markdown (`.md`), CSV, plain text (`.txt`), WebVTT captions (`.vtt`), email messages (`.eml`) and images |
| Mistral OCR (`mistral-ocr` and its versions) | PDF and images |
| `linkup-fetch` (Linkup) | Web pages, fetched from their URL |

A file in a format the step's model does not read is refused before the run starts, with an input error that names the input, its format, the step, the model and the formats that model reads. Give the file in a format the model reads, choose a model that reads it, or, for an Office file, configure a document converter (see [Office Files and Page Views](#office-files-and-page-views)). When the step can only be reached through a condition, the run starts, and the step refuses the file the same way when it gets to it. See [File formats are checked before the run](../building-methods/concepts/native-concepts.md#file-formats-are-checked-before-the-run).

A step that asks for page views needs a PDF whatever its model reads, since page views are drawn from one: see [Page views need a PDF](../building-methods/pipes/pipe-operators/PipeExtract.md#page-views-need-a-pdf).

## Office Files and Page Views

When the runtime has a document converter (`[runtime.document_conversion]`, off by default), a `PipeExtract` step reads the PDF of a Word, Excel or PowerPoint file in two cases. A step that asks for page views reads the PDF whenever some model that may serve it reads PDFs, even one that also reads the Office format, and its extraction reads that same PDF, so the page views and the extracted pages match one for one; a step whose models read no PDF, such as `linkup-fetch`, is refused its page views as before, and nothing is converted. A step without page views reads the PDF when a model that may serve it, any member of a waterfall included, does not read the file's format while some model that may serve it reads PDFs: with `@default-extract-document`, whose models read PDF and images, a Word file is converted, while `docling-extract-text`, which reads Word itself, is given the original. Each converted file is recorded in the run's trace with the PDF's page count, which is what the extraction is billed on. See [Office File Conversion](office-file-conversion.md) for the converters, what a conversion drops and where the PDF is kept.

## Key Capabilities

- **Page view generation** — High-fidelity image rendering of the pages of a PDF via pypdfium2
- **Embedded image extraction** — Capture images found within documents
- **Layout analysis** — Structured extraction of complex document layouts
- **Table recognition** — Automatic table detection and extraction
- **Handwriting support** — Via providers that support handwriting recognition (e.g., Azure Document Intelligence)
- **Multi-page processing** — Batch processing of document pages with per-page results
- **Web page extraction** — Fetch and extract content from web page URLs via Linkup Fetch

## Documents in LLM Prompts

Include PDFs directly in your prompts using `@variable` syntax. PipeLLM automatically handles document rendering — single documents, multiple documents, and mixed content combining text, images, and PDFs are all supported. Web page content extracted via PipeExtract follows the same pattern.

## Related Documentation

- [PipeExtract](../building-methods/pipes/pipe-operators/PipeExtract.md) - Operator reference and MTHDS fields
- [Office File Conversion](office-file-conversion.md) - When a step reads an Office file as its PDF
- [Generic document extraction](https://github.com/Pipelex/pipelex-cookbook/tree/main/methods/extract_generic) - A cookbook method that returns each page of any document as Markdown, including the text inside its images and diagrams
