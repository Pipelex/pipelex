---
title: "Pipe Operators Overview"
description: "Pipe operators are the building blocks of Pipelex methods: PipeLLM, PipeExtract, PipeImgGen, PipeSearch, PipeCompose, and PipeFunc — each handling a specific type of AI processing."
---

# Pipe Operators

The workers that perform the actual processing in your pipelines.

## Overview

Pipe operators are the building blocks of Pipelex methods. Each operator performs a specific type of work: calling an LLM, extracting text from documents, generating images, searching the web, composing data, or running custom code. Operators declare their input and output concepts, and the runtime validates type compatibility at definition time.

## PipeLLM

The core operator for LLM interaction. Supports text generation, structured output generation (two-step or direct JSON), vision (images and PDFs in prompts via `@variable` syntax), system prompts, and model presets. Works with any supported LLM provider.

See [PipeLLM reference](../building-methods/pipes/pipe-operators/PipeLLM.md).

## PipeExtract

OCR and document extraction from PDFs and images. Supports multiple providers (pypdfium2, Mistral OCR, Azure Document Intelligence, docling, Deepseek-OCR), page rendering, embedded image extraction, and layout analysis. Swap providers by changing configuration, no code changes needed.

See [PipeExtract reference](../building-methods/pipes/pipe-operators/PipeExtract.md).

## PipeImgGen

Text-to-image and image-to-image generation using models like FLUX, GPT Image, Nano Banana, and others. Outputs are stored locally or in cloud storage with configurable URL signing.

See [PipeImgGen reference](../building-methods/pipes/pipe-operators/PipeImgGen.md).

## PipeSearch

Web search with structured results and source citations. Powered by Linkup or Pipelex Gateway, results come back as typed SearchResult concepts ready for downstream processing.

See [PipeSearch reference](../building-methods/pipes/pipe-operators/PipeSearch.md).

## PipeCompose

Deterministic object construction without an LLM. Compose outputs from working memory variables, fixed values, Jinja2 templates, and nested structures. Ideal for aggregating results from previous steps or building inputs for downstream pipes.

See [PipeCompose reference](../building-methods/pipes/pipe-operators/PipeCompose.md).

## PipeFunc

Execute custom Python functions within pipelines. Functions are auto-discovered via the `@pipe_func()` decorator and receive the current working memory as their input. Use PipeFunc when you need logic that goes beyond what declarative operators provide.

See [PipeFunc reference](../building-methods/pipes/pipe-operators/PipeFunc.md).
