---
title: "Document Extraction"
description: "Multi-provider OCR and document processing with Mistral OCR, Azure Document Intelligence, docling, Deepseek-OCR, and Linkup Fetch. PDF processing, web page extraction, layout analysis, and table recognition."
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
| **Azure Document Intelligence** | Gateway | Enterprise-grade OCR with high accuracy for complex layouts, tables, and handwriting |
| **Deepseek-OCR** | Gateway | Open-source model optimized for markdown extraction from images |
| **Linkup Fetch** | Cloud API | Web page content extraction — fetches and extracts text from web URLs |

## Key Capabilities

- **Page view generation** — High-fidelity image rendering of extracted pages via pypdfium2
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
- [Generic Document Extraction Example](../cookbook/extract-generic.md) - Extract markdown from complex PDFs using vision
