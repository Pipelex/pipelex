# Pipelex Gateway — Available Models (Plain Text)

This file lists the LLMs, document extraction models, and image generation models currently available through Pipelex Gateway.
For configuration details, see the [documentation](https://docs.pipelex.com/latest/home/5-setup/configure-ai-providers/#option-1-pipelex-gateway-easiest-for-getting-started).

**Note:** This is the plain-text readable version. See `pipelex_gateway_models.md` for the HTML-styled version.

## Language Models (LLM)

| Model | in:text | in:images | in:pdf | out:text | out:structured |
| --- | :---: | :---: | :---: | :---: | :---: |
| claude-3-haiku | ✅ | ✅ | ❌ | ✅ | ✅ |
| claude-3.7-sonnet | ✅ | ✅ | ✅ | ✅ | ✅ |
| claude-4-opus | ✅ | ✅ | ✅ | ✅ | ✅ |
| claude-4-sonnet | ✅ | ✅ | ✅ | ✅ | ✅ |
| claude-4.1-opus | ✅ | ✅ | ✅ | ✅ | ✅ |
| claude-4.5-haiku | ✅ | ✅ | ✅ | ✅ | ✅ |
| claude-4.5-opus | ✅ | ✅ | ✅ | ✅ | ✅ |
| claude-4.5-sonnet | ✅ | ✅ | ✅ | ✅ | ✅ |
| deepseek-v3.1 | ✅ | ❌ | ❌ | ✅ | ✅ |
| deepseek-v3.2 | ✅ | ❌ | ❌ | ✅ | ✅ |
| deepseek-v3.2-speciale | ✅ | ❌ | ❌ | ✅ | ✅ |
| gemini-2.0-flash | ✅ | ✅ | ✅ | ✅ | ✅ |
| gemini-2.5-flash | ✅ | ✅ | ✅ | ✅ | ✅ |
| gemini-2.5-flash-lite | ✅ | ✅ | ✅ | ✅ | ✅ |
| gemini-2.5-pro | ✅ | ✅ | ✅ | ✅ | ✅ |
| gemini-3.0-flash-preview | ✅ | ✅ | ✅ | ✅ | ✅ |
| gemini-3.0-pro | ✅ | ✅ | ✅ | ✅ | ✅ |
| gpt-4.1 | ✅ | ✅ | ✅ | ✅ | ✅ |
| gpt-4.1-mini | ✅ | ✅ | ✅ | ✅ | ✅ |
| gpt-4.1-nano | ✅ | ✅ | ✅ | ✅ | ✅ |
| gpt-4o | ✅ | ✅ | ✅ | ✅ | ✅ |
| gpt-4o-mini | ✅ | ✅ | ✅ | ✅ | ✅ |
| gpt-5 | ✅ | ✅ | ✅ | ✅ | ✅ |
| gpt-5-chat | ✅ | ✅ | ✅ | ✅ | ✅ |
| gpt-5-mini | ✅ | ✅ | ✅ | ✅ | ✅ |
| gpt-5-nano | ✅ | ✅ | ✅ | ✅ | ✅ |
| gpt-5.1 | ✅ | ✅ | ✅ | ✅ | ✅ |
| gpt-5.1-chat | ✅ | ✅ | ✅ | ✅ | ✅ |
| gpt-5.1-codex | ✅ | ✅ | ✅ | ✅ | ✅ |
| gpt-5.2 | ✅ | ✅ | ✅ | ✅ | ✅ |
| gpt-5.2-chat | ✅ | ✅ | ✅ | ✅ | ✅ |
| gpt-5.2-codex | ✅ | ✅ | ✅ | ✅ | ✅ |
| gpt-oss-120b | ✅ | ❌ | ❌ | ✅ | ✅ |
| gpt-oss-20b | ✅ | ❌ | ❌ | ✅ | ✅ |
| grok-3 | ✅ | ❌ | ❌ | ✅ | ❌ |
| grok-3-mini | ✅ | ❌ | ❌ | ✅ | ❌ |
| grok-4 | ✅ | ❌ | ❌ | ✅ | ✅ |
| grok-4-fast-non-reasoning | ✅ | ✅ | ❌ | ✅ | ✅ |
| grok-4-fast-reasoning | ✅ | ✅ | ❌ | ✅ | ✅ |
| kimi-k2-thinking | ✅ | ❌ | ❌ | ✅ | ✅ |
| mistral-large-3 | ✅ | ✅ | ✅ | ✅ | ✅ |
| o1 | ✅ | ✅ | ✅ | ✅ | ✅ |
| o1-mini | ✅ | ✅ | ❌ | ✅ | ✅ |
| o3 | ✅ | ✅ | ✅ | ✅ | ✅ |
| o3-mini | ✅ | ❌ | ❌ | ✅ | ✅ |
| o4-mini | ✅ | ❌ | ❌ | ✅ | ✅ |
| phi-4 | ✅ | ❌ | ❌ | ✅ | ❌ |
| phi-4-multimodal | ✅ | ✅ | ❌ | ✅ | ❌ |
| qwen3-vl-235b-a22b | ✅ | ✅ | ❌ | ✅ | ✅ |

## Document Extraction Models

| Model | in:image | in:pdf | out:pages | out:captions |
| --- | :---: | :---: | :---: | :---: |
| azure-document-intelligence | ✅ | ✅ | ✅ | ✅ |
| deepseek-ocr | ✅ | ❌ | ✅ | ❌ |
| mistral-document-ai-2505 | ✅ | ✅ | ✅ | ❌ |


**About extracted pages:** Each page contains Markdown text (based on AI-interpreted layout) and optional extracted images. A single image input is treated as one page. Pipelex also wraps the `pypdfium2` library for raw text (without any AI interpretation) and images extraction and page views rendering. All these elements can be used as inputs into downstream pipes, including LLM prompts.

## Image Generation Models

| Model | in:text | out:image |
| --- | :---: | :---: |
| flux-2-pro | ✅ | ✅ |
| gpt-image-1 | ✅ | ✅ |
| gpt-image-1-mini | ✅ | ✅ |
| gpt-image-1.5 | ✅ | ✅ |
| nano-banana | ✅ | ✅ |
| nano-banana-pro | ✅ | ✅ |


> **AUTO-GENERATED FILE** - Do not edit manually.
> Last updated: 2026-01-26T16:36:40Z
>
> Run `pipelex-dev update-gateway-models` or `make ugm` to regenerate.