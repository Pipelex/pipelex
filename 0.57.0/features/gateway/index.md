# Pipelex Gateway & Model Access

Access AI models through the Pipelex Gateway or bring your own API keys.

## Pipelex Gateway

A fully managed infrastructure providing unified access to AI models through a single API key. The Gateway eliminates the need to manage multiple provider configurations.

- **Single API key** for all supported models
- **Remote model catalog** — always access the latest models without updating Pipelex
- **Enterprise-grade architecture** — built for reliability and scale
- **Extensive provider support** — OpenAI, Google, Anthropic, Mistral, xAI, and more

Browse all supported models in the [Gateway Models](../setup/gateway-models.md) reference.

Get your Gateway API key at [app.pipelex.com](https://app.pipelex.com/) or [join the waitlist](https://go.pipelex.com/waitlist).

## Bring Your Own Keys

Direct integration with major providers using your own API keys:

- **OpenAI** — GPT-4o, GPT-4.1, o1, o3, o4-mini, etc.
- **Anthropic** — Claude Sonnet 4, Claude Haiku, etc.
- **Google** — Gemini 2.5 Pro, Gemini 2.5 Flash, etc.
- **Mistral** — Mistral Large, Mistral Medium, etc.
- **Azure OpenAI** — Azure-hosted OpenAI models
- **Amazon Bedrock** — AWS-hosted models
- **Vertex AI** — Google Cloud-hosted models
- **xAI** — Grok models
- **Portkey** — AI gateway for routing and observability
- **OpenRouter** — Multi-provider aggregator
- **BlackboxAI** — Blackbox-hosted models
- **fal** — Image generation models

## Open-Source Models

Run open-source models through dedicated providers:

- **Ollama** — Run open-source LLMs locally (Llama, Mistral, Qwen, etc.)
- **Hugging Face Inference** — including qwen-image for text-to-image
- **Scaleway** — Deepseek R1, Llama 3.3, Qwen3, GPT-OSS
- **Groq** — Llama-4, Kimi-K2-Instruct

## Routing Profiles

Routing profiles control which backend handles each model. Define pattern-based routes, defaults, and fallback orders in `routing_profiles.toml`. Switch a pipeline from one provider to another — or from Pipelex Gateway to your own keys — without changing the method definition.

See [Configure AI Providers](../get-started/configure-ai-providers.md) for setup details.

## Offline Behavior

The Gateway fetches its model catalog from a remote config service. Pipelex stays usable when that service is briefly unreachable:

- **Gateway disabled (Bring Your Own Keys)** — no remote fetch is attempted at all. Setup, validation, and dry-runs are fully offline.
- **Gateway enabled** — Pipelex primes an on-disk copy of the remote config at `~/.pipelex/cache/remote_config.json` on every successful fetch and during `pipelex init` while online. If a later fetch fails, it falls back to this cache so setup, validation, and `--dry-run` still complete. When the cache is in use, a `RemoteConfigStale` warning is emitted (the agent CLI surfaces it on the JSON `warnings` array).

Only the actual inference call needs the network at runtime — offline support covers setup and dry-run, not live model calls. If the Gateway is enabled, the fetch fails, and no cache has ever been primed, setup raises `RemoteConfigUnavailableError`: run `pipelex init` while online to prime the cache, or disable `pipelex_gateway` for permanent offline (BYOK) operation.
