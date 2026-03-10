---
title: Pipe Operators
---

# Pipe Operators

The workers that perform the actual processing in your pipelines.

## Overview

<!-- TODO: Expand with a summary of the operator model -->

Pipe operators are the building blocks of Pipelex methods. Each operator performs a specific type of work: calling an LLM, extracting text from documents, generating images, searching the web, composing data, or running custom code.

## PipeLLM

<!-- TODO: Describe PipeLLM capabilities, prompting, structured outputs, vision -->

The core operator for LLM interaction. Supports text generation, structured outputs, vision (images and PDFs in prompts), system prompts, and model presets.

See [PipeLLM reference](../6-build-reliable-ai-workflows/pipes/pipe-operators/PipeLLM.md).

## PipeExtract

<!-- TODO: Describe document extraction capabilities -->

OCR and document extraction from PDFs and images. Supports multiple providers (Mistral OCR, Azure, docling, Deepseek-OCR), page rendering, and embedded image extraction.

See [PipeExtract reference](../6-build-reliable-ai-workflows/pipes/pipe-operators/PipeExtract.md).

## PipeImgGen

<!-- TODO: Describe image generation capabilities -->

Text-to-image generation using models like FLUX, GPT Image, and others. Outputs are stored locally or in cloud storage.

See [PipeImgGen reference](../6-build-reliable-ai-workflows/pipes/pipe-operators/PipeImgGen.md).

## PipeSearch

<!-- TODO: Describe web search capabilities -->

Web search with structured results, source citations, and advanced filters.

See [PipeSearch reference](../6-build-reliable-ai-workflows/pipes/pipe-operators/PipeSearch.md).

## PipeCompose

<!-- TODO: Describe template rendering and deterministic composition -->

Deterministic object construction without an LLM. Compose outputs from working memory variables, fixed values, Jinja2 templates, and nested structures.

See [PipeCompose reference](../6-build-reliable-ai-workflows/pipes/pipe-operators/PipeCompose.md).

## PipeFunc

<!-- TODO: Describe custom Python function execution -->

Execute custom Python functions within pipelines. Functions are auto-discovered via the `@pipe_func()` decorator.

See [PipeFunc reference](../6-build-reliable-ai-workflows/pipes/pipe-operators/PipeFunc.md).
