---
title: "Image Generation"
description: "Generate images from text prompts using FLUX, GPT Image, and other providers. PipeImgGen integrates text-to-image generation directly into your Pipelex pipelines."
---

# Image Generation

Text-to-image generation integrated directly into your pipelines.

## Overview

PipeImgGen generates images from text prompts using state-of-the-art models. Generated images can be stored locally or in cloud storage with public or signed URLs. Image generation supports both text-to-image and image-to-image workflows.

## Supported Models

Via **Pipelex Gateway**:

- **GPT-Image-2 / GPT-Image-1.5 / GPT-Image-1 / GPT-Image-1-mini** — OpenAI image generation models
- **Nano Banana / Nano Banana Pro / Nano Banana 2 / Nano Banana 2 Lite** — Google Gemini-based image generation

Via **direct provider SDKs**:

- **OpenAI** — Direct OpenAI API for GPT Image models
- **Google Gemini** — Native Google image generation
- **fal** — FLUX models (Black Forest Labs) and others via the fal platform
- **Hugging Face Inference** — Open-source models like qwen-image
- **BlackboxAI** — Via completions-based image generation
- **Azure REST** — Azure-hosted image generation
- **OpenRouter** — Multi-provider image generation access

## Cloud Storage Integration

Generated images can be automatically uploaded to AWS S3 or Google Cloud Storage with configurable URL signing. See [Cloud Storage](cloud-storage.md) for details.

## Usage in Pipelines

Use PipeImgGen in your `.mthds` files to generate images as part of a pipeline. The operator takes a `prompt` string template and outputs an `Image` concept. Declared inputs are injected into the template — `Text` variables as interpolated text, and `Image` variables as reference images for image-to-image generation. Model presets let you configure quality levels and default models in `2_img_gen_deck.toml`.

See [PipeImgGen reference](../building-methods/pipes/pipe-operators/PipeImgGen.md).
