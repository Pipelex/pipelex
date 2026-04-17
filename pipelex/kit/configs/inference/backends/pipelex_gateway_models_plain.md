# Pipelex Gateway — Available Models (Plain Text)

This file lists the LLMs, document extraction models, and image generation models currently available through Pipelex Gateway.
For configuration details, see the [documentation](https://docs.pipelex.com/latest/setup/configure-ai-providers/#option-1-pipelex-gateway-easiest-and-most-powerful-for-getting-started).

**Note:** This is the plain-text readable version. See `pipelex_gateway_models.md` for the HTML-styled version.

## Language Models (LLM)

- **claude-4-opus**
  - inputs: text, images, pdf
  - outputs: text, structured
- **claude-4-sonnet**
  - inputs: text, images, pdf
  - outputs: text, structured
- **claude-4.1-opus**
  - inputs: text, images, pdf
  - outputs: text, structured
- **claude-4.5-haiku**
  - inputs: text, images, pdf
  - outputs: text, structured
- **claude-4.5-opus**
  - inputs: text, images, pdf
  - outputs: text, structured
- **claude-4.5-sonnet**
  - inputs: text, images, pdf
  - outputs: text, structured
- **claude-4.6-opus**
  - inputs: text, images, pdf
  - outputs: text, structured
- **claude-4.6-sonnet**
  - inputs: text, images, pdf
  - outputs: text, structured
- **claude-4.7-opus**
  - inputs: text, images, pdf
  - outputs: text, structured
- **deepseek-v3.2**
  - inputs: text
  - outputs: text, structured
- **gemini-2.5-flash**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gemini-2.5-flash-lite**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gemini-2.5-pro**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gemini-3.0-flash-preview**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gemini-3.0-pro**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gemini-3.1-flash-lite-preview**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gemini-flash-latest**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gemini-flash-lite-latest**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gemini-pro-latest**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gpt-4.1**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gpt-4.1-mini**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gpt-4.1-nano**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gpt-4o**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gpt-4o-mini**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gpt-5**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gpt-5-chat**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gpt-5-mini**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gpt-5-nano**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gpt-5.1**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gpt-5.1-chat**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gpt-5.1-codex**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gpt-5.2**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gpt-5.2-chat**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gpt-5.2-codex**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gpt-5.3-codex**
  - inputs: text, images, pdf
  - outputs: text, structured
- **gpt-5.4**
  - inputs: text, images
  - outputs: text, structured
- **gpt-5.4-mini**
  - inputs: text, images
  - outputs: text, structured
- **gpt-5.4-nano**
  - inputs: text, images
  - outputs: text, structured
- **gpt-5.4-pro**
  - inputs: text, images
  - outputs: text, structured
- **gpt-oss-120b**
  - inputs: text
  - outputs: text, structured
- **gpt-oss-20b**
  - inputs: text
  - outputs: text, structured
- **grok-3**
  - inputs: text
  - outputs: text
- **grok-3-mini**
  - inputs: text
  - outputs: text
- **grok-4**
  - inputs: text
  - outputs: text, structured
- **grok-4-fast-non-reasoning**
  - inputs: text, images
  - outputs: text, structured
- **grok-4-fast-reasoning**
  - inputs: text, images
  - outputs: text, structured
- **kimi-k2-thinking**
  - inputs: text
  - outputs: text, structured
- **mistral-large**
  - inputs: text, images, pdf
  - outputs: text, structured
- **o1**
  - inputs: text, images, pdf
  - outputs: text, structured
- **o1-mini**
  - inputs: text, images
  - outputs: text, structured
- **o3**
  - inputs: text, images, pdf
  - outputs: text, structured
- **o3-mini**
  - inputs: text
  - outputs: text, structured
- **o4-mini**
  - inputs: text
  - outputs: text, structured
- **phi-4**
  - inputs: text
  - outputs: text
- **phi-4-multimodal**
  - inputs: text, images
  - outputs: text
- **qwen3-vl-235b-a22b**
  - inputs: text, images
  - outputs: text, structured

## Document Extraction Models

- **azure-document-intelligence**
  - inputs: image, pdf
  - outputs: pages, captions
- **deepseek-ocr**
  - inputs: image
  - outputs: pages
- **linkup-fetch**
  - inputs: web_page
  - outputs: pages


**About extracted pages:** Each page contains Markdown text (based on AI-interpreted layout) and optional extracted images. A single image input is treated as one page. Pipelex also wraps the `pypdfium2` library for raw text (without any AI interpretation) and images extraction and page views rendering. All these elements can be used as inputs into downstream pipes, including LLM prompts.

## Image Generation Models

- **gpt-image-1**
  - inputs: text, images
  - outputs: image
- **gpt-image-1-mini**
  - inputs: text
  - outputs: image
- **gpt-image-1.5**
  - inputs: text, images
  - outputs: image
- **nano-banana**
  - inputs: text, images
  - outputs: image
- **nano-banana-2**
  - inputs: text, images
  - outputs: image
- **nano-banana-pro**
  - inputs: text, images
  - outputs: image


> **AUTO-GENERATED FILE** - Do not edit manually.
> Last updated: 2026-04-17T12:23:17Z
>
> Run `pipelex-dev update-gateway-models` or `make ugm` to regenerate.