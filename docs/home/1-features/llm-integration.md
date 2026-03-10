---
title: LLM Integration
---

# LLM Integration

Deep integration with large language models for text generation, structured outputs, and vision tasks.

## Overview

Pipelex provides a unified interface for working with LLMs across providers. Write your prompt once, run it on any supported model. The runtime handles provider-specific API differences, token management, and response parsing.

## Structured Output Generation

Two approaches for structured outputs:

- **Two-step** — Generate text first, then parse into a structured concept. More reliable for complex schemas.
- **Direct JSON** — Generate structured JSON directly from the LLM using provider-native structured output features.

See [LLM Structured Generation](../6-build-reliable-ai-workflows/llm-structured-generation-config.md).

## Vision Language Models

Include images and PDFs directly in LLM prompts using `@variable` syntax. Support for single documents, multiple documents, and mixed content (text + images + PDFs). The runtime automatically handles document rendering and provider-specific vision API formats.

## Prompting Styles

Adapt prompts for different LLM families (OpenAI, Anthropic, Mistral) to get the best results from each provider. Pipelex applies provider-specific formatting, system prompt handling, and structured output instructions automatically.

See [LLM Prompting Style](../6-build-reliable-ai-workflows/adapt-to-llm-prompting-style-openai-anthropic-mistral.md).

## System Prompt Inheritance

Define system prompts at the domain level and have them automatically inherited by all PipeLLM operators in that domain. Individual pipes can override the domain-level system prompt when needed.

## Model Presets

Named configurations (temperature, max tokens, model selection, etc.) for consistent model behavior. Define presets once in the model deck, then reference them by name across all your pipelines using `$preset_name` syntax.

See [Optimize Cost & Quality](../6-build-reliable-ai-workflows/configure-ai-llm-to-optimize-methods.md).
