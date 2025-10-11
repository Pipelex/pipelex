# Pipe Operators

Pipe operators are the fundamental building blocks in Pipelex, representing a single, focused task. They are the "verbs" of your pipeline that perform the actual work.

Each operator specializes in a specific kind of action, from interacting with Large Language Models to executing custom Python code. You combine these operators using [Pipe Controllers](../pipe-controllers/index.md) to create complex workflows.

## Core Operators

Here are the primary pipe operators available in Pipelex:

-   [**`PipeLLM`**](./PipeLLM.md): The core operator for all interactions with Large Language Models (LLMs), including text generation, structured data extraction, and vision tasks.
-   [**`PipeOcr`**](./PipeOcr.md): Performs Optical Character Recognition (OCR) on images and PDF documents to extract text and embedded images.
-   [**`PipeImgGen`**](./PipeImgGen.md): Generates images from a text prompt using models like GPT Image, Flux, or other image generation models.
-   [**`PipeFunc`**](./PipeFunc.md): An escape hatch that allows you to execute any custom Python function, giving you maximum flexibility.
-   [**`PipeCompose`**](./PipeCompose.md): Renders a Jinja2 template using data from the working memory, perfect for creating formatted reports or complex prompts.

## Overview

Pipelex provides the following pipe operators:

- `PipeLLM`: For LLM-based text generation and processing
- `PipeOcr`: For optical character recognition and document processing
- `PipeFunc`: For executing custom functions
- `PipeImgGen`: For AI-powered image generation

## PipeLLM

Core operator for LLM-based text generation and processing.

### Key Features

- Text generation
- Structured output generation
- Multiple output modes
- System prompt customization
- LLM configuration

### Key Features

- Sequential execution
- Working memory management
- Sub-pipe handling
- Pipeline composition

## PipeOcr

Processes images and PDFs using Optical Character Recognition.

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
