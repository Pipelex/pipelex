---
description: "Set up API keys for OpenAI, Anthropic, Mistral, and other providers to power your Pipelex executable AI methods — or use the gateway for instant access."
---

# Configure AI Providers

## Configure API Access

To run pipelines with LLMs, you need to configure API access. **You have three options** - choose what works best for you:

### Option 1: Pipelex Gateway — Easiest and most Powerful for Getting Started

Get **free credits** for testing and development with a single API key for LLMs, document extraction, and image generation across all major providers (OpenAI, Anthropic, Google, Azure, open-source, and more). New models added constantly.

**Benefits:**

- No credit card required
- Access to OpenAI, Anthropic Claude, Google Gemini, xAI Grok, and more
- New models added constantly
- Perfect for development and testing
- Single API key for all models

**Setup:**

1. Get your API key at [app.pipelex.com](https://app.pipelex.com/)

2. Create a `.env` file in your project root:

    ```env
    PIPELEX_GATEWAY_API_KEY=your-key-here
    ```

3. Run `pipelex init` and accept the Gateway terms of service when prompted.

That's it! Your pipelines can now access any supported LLM. See [Gateway Available Models](../setup/gateway-models.md) for the full list.

!!! info "Terms of Service & Telemetry"
    When using Pipelex Gateway, you'll be prompted to accept our terms of service. By using the Gateway, identified telemetry is automatically enabled (tied to your hashed API key) to help us monitor service quality and enforce fair usage.

    **We collect only technical data** (model names, token counts, latency, error rates). We do **NOT** collect your prompts, completions, or business data. See [Telemetry](../setup/telemetry.md) for details and trade-offs, and our [Privacy Policy](https://go.pipelex.com/privacy-policy) for more.

### Option 2: Bring Your Own API Keys

Use your existing API keys from LLM providers. This is ideal if you:

- Already have API keys from providers
- Need to use specific accounts for billing
- Have negotiated rates or enterprise agreements
- Prefer not to send any telemetry to Pipelex servers

**Setup:**

Create a `.env` file in your project root with your provider keys:

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Google
GOOGLE_API_KEY=...

# Mistral
MISTRAL_API_KEY=...

# FAL (for image generation)
FAL_API_KEY=...

# XAI
XAI_API_KEY=...

# Azure OpenAI
AZURE_API_KEY=...
AZURE_API_BASE=...
AZURE_API_VERSION=...

# Amazon Bedrock
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=...
```

You only need to add keys for the providers you plan to use.

**Enable Your Providers:**

When using your own keys, enable the corresponding backends:

1. Initialize configuration:

    ```bash
    pipelex init config
    ```

2. Edit `.pipelex/inference/backends.toml`:

    ```toml
    [google]
    enabled = true

    [openai]
    enabled = true

    # Enable any providers you have keys for
    ```

See [Inference Backend Configuration](../configuration/config-technical/inference-backend-config.md) for all options.

### Option 3: Local AI (No API Keys Required)

Run AI models locally without any API keys. This is perfect if you:

- Want complete privacy and control
- Have capable hardware (GPU recommended)
- Need offline capabilities
- Want to avoid API costs

**Supported Local Options:**

**Ollama** (Recommended):

1. Install [Ollama](https://ollama.ai/)
2. Pull a model: `ollama pull llama2`
3. No API key needed! Configure Ollama backend in `.pipelex/inference/backends.toml`

**Other Local Providers:**

- **vLLM**: High-performance inference server
- **LM Studio**: User-friendly local model interface
- **llama.cpp**: Lightweight C++ inference

Configure these in `.pipelex/inference/backends.toml`. See our [Inference Backend Configuration](../configuration/config-technical/inference-backend-config.md) for details.

---

## Backend Configuration Files

To set up Pipelex configuration files, run:

```bash
pipelex init config
```

This creates a `.pipelex/` directory with:

```
.pipelex/
├── pipelex.toml              # Feature flags, logging, cost reporting
├── telemetry.toml            # Custom telemetry configuration
└── inference/                # LLM configuration and model presets
    ├── backends.toml         # Enable/disable model providers
    ├── deck/
    │   ├── 1_llm_deck.toml           # LLM presets and aliases
    │   ├── 2_img_gen_deck.toml       # Image generation config
    │   ├── 3_extract_deck.toml       # Document extraction config
    │   └── x_custom_llm_deck.toml    # Custom waterfalls/overrides
    └── routing_profiles.toml # Model routing configuration
```

Learn more in our [Inference Backend Configuration](../configuration/config-technical/inference-backend-config.md) guide.

---

## Next Steps

Now that you have your backend configured:

1. **Learn the concepts**: [Getting Started Tutorial](./index.md)
2. **Explore examples**: [Cookbook Repository](https://github.com/Pipelex/pipelex-cookbook/tree/main)
3. **Deep dive**: [Build Reliable AI Methods](../building-methods/kick-off-a-methods-project.md)

!!! tip "Advanced Configuration"
    For detailed backend configuration options, see [Inference Backend Configuration](../configuration/config-technical/inference-backend-config.md).
