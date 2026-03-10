---
title: Pipelex Gateway & Model Access
---

# Pipelex Gateway & Model Access

Access AI models through the Pipelex Gateway or bring your own API keys.

## Pipelex Gateway

<!-- TODO: Expand this section -->

A fully managed infrastructure providing unified access to AI models through a single API key. The Gateway eliminates the need to manage multiple provider configurations.

- **Single API key** for all supported models
- **Remote model catalog** — always access the latest models without updating Pipelex
- **Enterprise-grade architecture** — built for reliability and scale
- **Extensive provider support** — OpenAI, Google, Anthropic, Mistral, and more

Browse all supported models in the [Gateway Models](../5-setup/gateway-models.md) reference.

Get your Gateway API key at [app.pipelex.com](https://app.pipelex.com/) or [join the waitlist](https://go.pipelex.com/waitlist).

## Bring Your Own Keys

Direct integration with major providers using your own API keys:

<!-- TODO: List all supported direct providers with setup links -->

- **OpenAI** — GPT-4o, GPT-4.1, o1, o3, o4-mini, etc.
- **Anthropic** — Claude Sonnet 4, Claude Haiku, etc.
- **Google** — Gemini 2.5 Pro, Gemini 2.5 Flash, etc.
- **Mistral** — Mistral Large, Mistral Medium, etc.
- **Azure OpenAI** — Azure-hosted OpenAI models
- **Amazon Bedrock** — AWS-hosted models

## Open-Source Models

<!-- TODO: Detail each open-source provider -->

- **Hugging Face Inference** — including qwen-image for text-to-image
- **Scaleway** — Deepseek R1, Llama 3.3, Qwen3, GPT-OSS
- **Groq** — Llama-4, Kimi-K2-Instruct

## Routing Profiles

<!-- TODO: Explain how routing profiles work to direct models to backends -->

Route models to different providers via routing profiles in configuration. Switch a pipeline from one provider to another without changing the method definition.
