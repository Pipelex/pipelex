# Pipelex Gateway - Available Models

> **AUTO-GENERATED FILE** - Do not edit manually.
> Last updated: 2026-01-19T10:29:00Z
>
> Run `pipelex-dev update-gateway-models` or `make ugm` to regenerate.

This file documents models available through Pipelex Gateway.
For configuration details, see the [documentation](https://docs.pipelex.com/latest/home/5-setup/configure-ai-providers/#option-1-pipelex-gateway-easiest-for-getting-started).

## Language Models (LLM)

| Model | Inputs | Outputs | SDK | Structure Method |
|-------|--------|---------|-----|------------------|
| claude-3.7-sonnet | text, images, pdf | text, structured | gateway_completions | instructor/openai_tools |
| claude-4-opus | text, images, pdf | text, structured | gateway_completions | instructor/openai_tools |
| claude-4-sonnet | text, images, pdf | text, structured | gateway_completions | instructor/openai_tools |
| claude-4.1-opus | text, images, pdf | text, structured | gateway_completions | instructor/openai_tools |
| claude-4.5-haiku | text, images, pdf | text, structured | gateway_completions | instructor/openai_tools |
| claude-4.5-opus | text, images, pdf | text, structured | gateway_completions | instructor/openai_tools |
| claude-4.5-sonnet | text, images, pdf | text, structured | gateway_completions | instructor/openai_tools |
| deepseek-v3.1 | text | text, structured | gateway_completions | instructor/json |
| gemini-2.0-flash | text, images, pdf | text, structured | gateway_completions | instructor/openai_tools |
| gemini-2.5-flash | text, images, pdf | text, structured | gateway_completions | instructor/openai_tools |
| gemini-2.5-flash-lite | text, images, pdf | text, structured | gateway_completions | instructor/openai_tools |
| gemini-2.5-pro | text, images, pdf | text, structured | gateway_completions | instructor/openai_tools |
| gemini-3.0-flash-preview | text, images, pdf | text, structured | gateway_completions | instructor/openai_tools |
| gemini-3.0-pro | text, images, pdf | text, structured | gateway_completions | instructor/openai_tools |
| gpt-4.1 | text, images, pdf | text, structured | gateway_responses | instructor/openai_responses_tools |
| gpt-4.1-mini | text, images, pdf | text, structured | gateway_responses | instructor/openai_responses_tools |
| gpt-4.1-nano | text, images, pdf | text, structured | gateway_responses | instructor/openai_responses_tools |
| gpt-4o | text, images, pdf | text, structured | gateway_responses | instructor/openai_responses_tools |
| gpt-4o-mini | text, images, pdf | text, structured | gateway_responses | instructor/openai_responses_tools |
| gpt-5 | text, images, pdf | text, structured | gateway_responses | instructor/openai_responses_tools |
| gpt-5-chat | text, images, pdf | text, structured | gateway_responses | instructor/openai_responses_tools |
| gpt-5-mini | text, images, pdf | text, structured | gateway_responses | instructor/openai_responses_tools |
| gpt-5-nano | text, images, pdf | text, structured | gateway_responses | instructor/openai_responses_tools |
| gpt-5.1 | text, images, pdf | text, structured | gateway_responses | instructor/openai_responses_tools |
| gpt-5.1-chat | text, images, pdf | text, structured | gateway_responses | instructor/openai_responses_tools |
| gpt-5.1-codex | text, images, pdf | text, structured | gateway_responses | instructor/openai_responses_tools |
| gpt-5.2 | text, images, pdf | text, structured | gateway_responses | instructor/openai_responses_tools |
| gpt-5.2-chat | text, images, pdf | text, structured | gateway_responses | instructor/openai_responses_tools |
| gpt-5.2-codex | text, images, pdf | text, structured | gateway_responses | instructor/openai_responses_tools |
| gpt-oss-120b | text | text, structured | gateway_completions | instructor/openai_tools |
| gpt-oss-20b | text | text, structured | gateway_completions | instructor/openai_tools |
| grok-3 | text | text | gateway_completions | instructor/openai_tools |
| grok-3-mini | text | text | gateway_completions | instructor/openai_tools |
| grok-4 | text | text, structured | gateway_completions | instructor/openai_tools |
| grok-4-fast-non-reasoning | text, images | text, structured | gateway_completions | instructor/openai_tools |
| grok-4-fast-reasoning | text, images | text, structured | gateway_completions | instructor/openai_tools |
| kimi-k2-thinking | text | text, structured | gateway_completions | instructor/openai_tools |
| mistral-large-3 | text, images, pdf | text, structured | gateway_completions | instructor/mistral_tools |
| o1 | text, images, pdf | text, structured | gateway_responses | instructor/openai_responses_tools |
| o1-mini | text, images | text, structured | gateway_responses | instructor/openai_responses_tools |
| o3 | text, images, pdf | text, structured | gateway_responses | instructor/openai_responses_tools |
| o3-mini | text | text, structured | gateway_responses | instructor/openai_responses_tools |
| o4-mini | text | text, structured | gateway_responses | instructor/openai_responses_tools |
| phi-4 | text | text | gateway_completions | instructor/openai_tools |
| phi-4-multimodal | text, images | text | gateway_completions | instructor/openai_tools |
| qwen3-vl-235b-a22b | text, images | text, structured | gateway_completions | instructor/json |

## Document Extraction Models

| Model | Inputs | Outputs | SDK |
|-------|--------|---------|-----|
| azure-document-intelligence | pdf | pages | gateway_extract |
| deepseek-ocr | image | pages | gateway_extract |
| mistral-document-ai-2505 | pdf, image | pages | gateway_extract |

## Image Generation Models

| Model | Inputs | Outputs | SDK |
|-------|--------|---------|-----|
| flux-2-pro | text | image | gateway_img_gen |
| gpt-image-1 | text | image | gateway_img_gen |
| gpt-image-1-mini | text | image | gateway_img_gen |
| gpt-image-1.5 | text | image | gateway_img_gen |
| nano-banana | text | image | gateway_completions |
| nano-banana-pro | text | image | gateway_completions |
