# Pipe Operators

Pipe operators are the core processing units in Pipelex. Each operator type specializes in a specific kind of task, from LLM interactions to data transformations.

## Overview

Pipelex provides the following pipe operators:
- `PipeLLM`: For LLM-based text generation and processing
- `PipeCondition`: For conditional execution based on input validation
- `PipeSequence`: For chaining multiple pipes in sequence
- `PipeOcr`: For optical character recognition and document processing
- `PipeFunc`: For executing custom functions
- `PipeImgGen`: For image generation and manipulation

## PipeLLM

Core operator for LLM-based text generation and processing.

### Key Features
- Text generation
- Structured output generation
- Multiple output modes
- System prompt customization
- LLM configuration

## PipeCondition

Enables conditional execution based on input validation.

### Key Features
- Expression-based routing
- Default fallback paths
- Jinja2 template support
- Input validation
- Error handling

## PipeSequence

Chains multiple pipes together in sequence.

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
