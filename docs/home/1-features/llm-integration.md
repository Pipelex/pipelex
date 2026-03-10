---
title: LLM Integration
---

# LLM Integration

Deep integration with large language models for text generation, structured outputs, and vision tasks.

## Overview

<!-- TODO: Expand with LLM interaction model -->

Pipelex provides a unified interface for working with LLMs across providers. Write your prompt once, run it on any supported model.

## Structured Output Generation

<!-- TODO: Describe the two-step approach and direct JSON generation -->

Two approaches for structured outputs:

- **Two-step** — Generate text first, then parse into structure
- **Direct JSON** — Generate structured JSON directly from the LLM

See [LLM Structured Generation](../6-build-reliable-ai-workflows/llm-structured-generation-config.md).

## Vision Language Models

<!-- TODO: Describe how to include images and PDFs in prompts -->

Include images and PDFs directly in LLM prompts using `@variable` syntax. Support for single documents, multiple documents, and mixed content (text + images + PDFs).

## Prompting Styles

<!-- TODO: Describe provider-specific prompt adaptation -->

Adapt prompts for different LLM families (OpenAI, Anthropic, Mistral) to get the best results from each provider.

See [LLM Prompting Style](../6-build-reliable-ai-workflows/adapt-to-llm-prompting-style-openai-anthropic-mistral.md).

## System Prompt Inheritance

<!-- TODO: Describe domain-level system prompts -->

Define system prompts at the domain level and have them automatically inherited by all PipeLLM operators in that domain.

## Model Presets

<!-- TODO: Describe named model configurations -->

Named configurations (temperature, max tokens, etc.) for consistent model behavior. Define once, reuse across pipelines.

See [Optimize Cost & Quality](../6-build-reliable-ai-workflows/configure-ai-llm-to-optimize-methods.md).
