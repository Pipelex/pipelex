---
description: "Set up API keys for OpenAI, Anthropic, Mistral, OpenRouter and other providers to power your Pipelex executable AI methods — or run them on the hosted Pipelex API."
---

# Configure AI Providers

## Configure API Access

To run pipelines with LLMs, you need to configure API access. **You have three options** - choose what works best for you:

### Option 1: Bring Your Own API Keys

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

# OpenRouter — one key, many providers
OPENROUTER_API_KEY=...

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
    pipelex init
    ```

2. Edit `~/.pipelex/inference/backends.toml` (or `.pipelex/inference/backends.toml` in your project root if you have a project-local config — the project file fully overrides the global one). To run on a backend of your own choosing without touching a tracked file, write the same keys in a git-ignored `backends_override.toml` beside it instead: see [Personal overrides](../configuration/config-technical/inference-backend-config.md#personal-overrides).

    ```toml
    [google]
    enabled = true

    [openai]
    enabled = true

    # Enable any providers you have keys for
    ```

See [Inference Backend Configuration](../configuration/config-technical/inference-backend-config.md) for all options.

### Option 2: Run on the hosted Pipelex API (No provider keys of your own)

Rather than holding provider keys, sign up at [app.pipelex.com](https://app.pipelex.com/), create a Pipelex API key, and run your methods through the hosted API. This is ideal if you:

- Would rather not manage a key per provider
- Want one bill and one credential
- Are calling Pipelex from an application or an agent rather than from your own machine

**Setup:**

1. Create your Pipelex API key at [app.pipelex.com](https://app.pipelex.com/), or run `pipelex login`, which opens the browser and saves the key for you.

2. Point your client at the hosted API with that key:

    ```env
    PIPELEX_API_KEY=plx_sk_...
    ```

Your methods then run on Pipelex's infrastructure, and the inference credentials are ours rather than yours.

### Option 3: Local AI (No API Keys Required)

Run AI models locally without any API keys. This is perfect if you:

- Want complete privacy and control
- Have capable hardware (GPU recommended)
- Need offline capabilities
- Want to avoid API costs

**Supported Local Options:**

**Ollama** (Recommended):

1. Install [Ollama](https://ollama.ai/)
2. Pull a model from Pipelex's Ollama catalog: `ollama pull gemma3:4b`
3. No API key needed! Configure Ollama backend in `~/.pipelex/inference/backends.toml`

**Other Local Providers:**

- **vLLM**: High-performance inference server
- **LM Studio**: User-friendly local model interface
- **llama.cpp**: Lightweight C++ inference

Configure these in `~/.pipelex/inference/backends.toml`. See our [Inference Backend Configuration](../configuration/config-technical/inference-backend-config.md) for details.

---

## Backend Configuration Files

To set up Pipelex configuration files, run:

```bash
pipelex init
```

By default, this creates the global `~/.pipelex/` directory with:

```
~/.pipelex/
├── pipelex.toml              # Feature flags, logging, cost reporting
├── plxt.toml                 # MTHDS/TOML formatting and linting configuration
├── telemetry.toml            # AI trace destinations (PostHog, Langfuse, OTLP)
└── inference/                # LLM configuration and model presets
    ├── backends.toml         # Enable/disable model providers
    ├── backends/             # Per-provider model catalogs (anthropic.toml, openai.toml, ...)
    ├── deck/
    │   ├── 1_llm_deck.toml            # LLM presets and aliases
    │   ├── 2_img_gen_deck.toml        # Image generation config
    │   ├── 3_extract_deck.toml        # Document extraction config
    │   ├── 4_search_deck.toml         # Search config
    │   ├── x_custom_llm_deck.toml     # Custom LLM configurations
    │   └── x_custom_extract_deck.toml # Custom extract configurations
    └── routing_profiles.toml # Model routing configuration
```

To keep the configuration inside a project instead, run `pipelex init --local`: it creates the same structure in a `.pipelex/` directory at your project root, which takes precedence over the global `~/.pipelex/`.

Learn more in our [Inference Backend Configuration](../configuration/config-technical/inference-backend-config.md) guide.

### What the deck resolves to out of the box

The deck files `pipelex init` installs resolve the language, image-generation and document-extraction defaults to models served from Azure, so a fresh install runs inside one provider's scope without you choosing anything:

- **Language models** — the premium tier and `best-gpt` are GPT-6 Astra, the general and large-context tiers are GPT-5.4, and the small tiers are GPT-5.4 nano.
- **Image generation** — the general and premium tiers are GPT Image 2, the small tier is GPT Image 1 mini.
- **Document extraction** — Azure Document Intelligence. `default-text-from-pdf` and `default-no-inference` are the exception within that family: they read the PDF locally with pypdfium2 and call no model, so they need no key of any kind.

**Where the deck leaves Azure, it goes to Linkup**, and it does so in two families rather than one. Azure serves no search model, so everything in `4_search_deck.toml` resolves to Linkup; and `default-extract-web-page` in `3_extract_deck.toml` resolves to `linkup-fetch`, which pulls a web page through Linkup rather than through Azure Document Intelligence. A method that searches the web, or that extracts from a web page, needs a Linkup key.

Nothing about this locks you in. The deck is a vocabulary of aliases and presets, not a provider commitment: point any of them at a model from any backend you have enabled, by editing `x_custom_llm_deck.toml`, which `pipelex update` never touches. That is also how you bring back an alias the shipped deck does not define.

---

## Next Steps

Now that you have your backend configured:

1. **Learn the concepts**: [MTHDS Language Tutorial](./mthds-language-tutorial.md)
2. **Explore examples**: [Cookbook Repository](https://github.com/Pipelex/pipelex-cookbook/tree/main)
3. **Deep dive**: [Build Reliable AI Methods](../building-methods/kick-off-a-methods-project.md)

!!! tip "Advanced Configuration"
    For detailed backend configuration options, see [Inference Backend Configuration](../configuration/config-technical/inference-backend-config.md).
