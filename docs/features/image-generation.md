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

- **GPT-Image-1.5** — OpenAI's latest image generation model
- **GPT-Image-1** — OpenAI image generation
- **GPT-Image-1-mini** — Smaller, faster variant for quick generations
- **FLUX-2-pro** — Black Forest Labs' high-quality generation model
- **Nano Banana / Nano Banana Pro / Nano Banana 2** — Google Gemini-based image generation

Via **direct provider SDKs**:

- **OpenAI** — Direct OpenAI API for GPT Image models
- **Google Gemini** — Native Google image generation
- **fal** — FLUX and other models via the fal platform
- **Hugging Face Inference** — Open-source models like qwen-image
- **BlackboxAI** — Via completions-based image generation
- **Azure REST** — Azure-hosted image generation
- **OpenRouter** — Multi-provider image generation access

## Cloud Storage Integration

Generated images can be automatically uploaded to AWS S3 or Google Cloud Storage with configurable URL signing. See [Cloud Storage](cloud-storage.md) for details.

## Usage in Pipelines

Use PipeImgGen in your `.mthds` files to generate images as part of a pipeline. The operator accepts a text prompt (or an ImgGenPrompt concept) and outputs an Image concept. Model presets let you configure quality levels and default models in `2_img_gen_deck.toml`.

See [PipeImgGen reference](../building-methods/pipes/pipe-operators/PipeImgGen.md).
