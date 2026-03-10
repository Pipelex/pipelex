---
title: Document Extraction
---

# Document Extraction

Multi-provider OCR and document processing with a unified interface.

## Overview

<!-- TODO: Expand with the extraction philosophy -->

From simple text extraction to advanced document understanding — Pipelex handles it all. Basic PDF text extraction works out of the box (via pypdfium2), but real documents demand more: OCR for scanned pages, layout analysis for complex structures, image extraction, and VLM-powered understanding.

Unlike LLM APIs (partly standardized around OpenAI's completions API), the OCR landscape is fragmented. Pipelex solves this with a unified interface: swap providers by changing your PipeExtract config, no code changes required.

## Supported Providers

| Provider | Description |
|----------|-------------|
| **Mistral OCR** | Industry-leading document understanding for media, text, tables, and equations |
| **Azure Document Intelligence** | Enterprise-grade OCR with high accuracy for complex layouts, tables, and handwriting |
| **docling** | IBM's open-source extraction library with local CPU processing and optional GPU acceleration |
| **Deepseek-OCR** | Open-source model optimized for markdown extraction from images |

## Key Capabilities

<!-- TODO: Expand each capability with examples -->

- **Page view generation** — High-fidelity image rendering of extracted pages
- **Embedded image extraction** — Capture images found within documents
- **Layout analysis** — Structured extraction of complex document layouts
- **Table recognition** — Automatic table detection and extraction
- **Handwriting support** — Via providers that support handwriting recognition
- **Multi-page processing** — Batch processing of document pages

## Documents in LLM Prompts

<!-- TODO: Describe the @variable syntax for including documents in prompts -->

Include PDFs directly in your prompts using `@variable` syntax. Single documents, multiple documents, mixed with text and images.
