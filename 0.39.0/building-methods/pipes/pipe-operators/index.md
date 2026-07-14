# Pipe Operators

!!! tip "MTHDS Standard Reference"
    Pipe operators are part of the MTHDS open standard. For the authoritative language specification, see [Pipes & Operators](https://mthds.ai/latest/language/pipes-operators/) on mthds.ai. This page documents Pipelex-specific behavior and usage.

Pipe operators are the fundamental building blocks in Pipelex, representing a single, focused task. They are the "verbs" of your pipeline that perform the actual work.

Each operator specializes in a specific kind of action, from interacting with Large Language Models to executing custom Python code. You combine these operators using [Pipe Controllers](../pipe-controllers/index.md) to create complex methods.

## Core Operators

Here are the primary pipe operators available in Pipelex:

-   [**`PipeLLM`**](./PipeLLM.md): The core operator for all interactions with Large Language Models (LLMs), including text generation, structured data extraction, and vision tasks.
-   [**`PipeStructure`**](./PipeStructure.md): Turns free-form text into structured, typed data via a single LLM call — ideal when the text comes from an upstream extraction, search, or generation step.
-   [**`PipeExtract`**](./PipeExtract.md): Performs Optical Character Recognition (OCR) on images and PDF documents to extract text and embedded images, and fetches and extracts content from web pages.
-   [**`PipeImgGen`**](./PipeImgGen.md): Generates images from a text prompt using models like GPT Image, Flux, or other image generation models.
-   [**`PipeSearch`**](./PipeSearch.md): Searches the web using a configurable search provider and returns structured results with an answer and source citations.
-   [**`PipeFunc`**](./PipeFunc.md): An escape hatch that allows you to execute any custom Python function, giving you maximum flexibility.
-   [**`PipeCompose`**](./PipeCompose.md): Renders a Jinja2 template using data from the working memory, perfect for creating formatted reports or complex prompts.

## Overview

Pipelex provides the following pipe operators:

- `PipeLLM`: For LLM-based text generation and processing
- `PipeCompose`: For rendering Jinja2 templates from working memory data
- `PipeExtract`: For optical character recognition and document processing
- `PipeFunc`: For executing custom functions
- `PipeImgGen`: For AI-powered image generation
- `PipeSearch`: For web search with structured results
- `PipeStructure`: For turning free-form text into structured data

## PipeLLM

Core operator for LLM-based text generation and processing.

### Key Features

- Text generation
- Structured output generation
- Multiple output modes
- System prompt customization
- LLM configuration

## PipeExtract

Processes images and PDFs using Optical Character Recognition, and fetches and extracts content from web pages.

### Key Features

- PDF processing
- Image processing
- Text extraction
- Image extraction
- Page view generation

## PipeFunc

Executes custom functions within the pipeline.

### Key Features

- Custom function execution
- Working memory integration
- Multiple output types
- Function registry integration

## PipeImgGen

Generates and manipulates images.

### Key Features

- Image generation
- Quality control
- Multiple output formats
- Batch processing
- Parameter customization

## PipeSearch

Searches the web and returns structured results with sources.

### Key Features

- Web search via configurable providers
- Structured results with answer and source citations
- Dynamic prompt templates with `$variable` syntax
- Standard and deep search models
