# LLM Integration

Deep integration with large language models for text generation, structured outputs, and vision tasks.

## Overview

Pipelex provides a unified interface for working with LLMs across providers. Write your prompt once, run it on any supported model. The runtime handles provider-specific API differences, token management, and response parsing.

## Structured Output Generation

Two approaches for structured outputs:

- **Two-step** — Generate text first, then parse into a structured concept. More reliable for complex schemas.
- **Direct JSON** — Generate structured JSON directly from the LLM using provider-native structured output features.

See [`PipeStructure`](../building-methods/pipes/pipe-operators/PipeStructure.md) for direct text-to-structure conversion, [`PipeLLM`](../building-methods/pipes/pipe-operators/PipeLLM.md) for direct JSON generation, and [Build-time Elaboration](../under-the-hood/build-time-elaboration.md) for how `structuring_method = "preliminary_text"` is rewritten into a two-step sequence at load time.

## Vision Language Models

Include images and PDFs directly in LLM prompts using `@variable` syntax. Support for single documents, multiple documents, and mixed content (text + images + PDFs). The runtime automatically handles document rendering and provider-specific vision API formats.

## Templating Style

Choose how a pipe's inputs are tagged into its prompt — XML tags, back-tick fences, square brackets, or no tag at all. It is declared on the pipe (`templating_style`), with one runtime default for everything that declares nothing, so the same method renders the same prompt shape on every model.

See [Templating Style](../building-methods/templating-style.md).

## System Prompt Inheritance

Define system prompts at the domain level and have them automatically inherited by all PipeLLM operators in that domain. Individual pipes can override the domain-level system prompt when needed.

## Model Presets

Named configurations (temperature, max tokens, model selection, etc.) for consistent model behavior. Define presets once in the model deck, then reference them by name across all your pipelines using `$preset_name` syntax.

See [Optimize Cost & Quality](../building-methods/configure-ai-llm-to-optimize-methods.md).
