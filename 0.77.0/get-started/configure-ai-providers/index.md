# Configure AI Providers

## Configure API Access

To run pipelines on your own machine, Pipelex needs access to AI models. **You have two options**: your own provider keys, or models running locally. Nothing reports to Pipelex either way. If you would rather hold no provider keys at all, the [Quick Start](./quick-start.md) runs methods on the hosted Pipelex API instead.

### Option 1: Bring Your Own API Keys

Use your existing API keys from LLM providers. This is ideal if you:

- Already have API keys from providers
- Need to use specific accounts for billing
- Have negotiated rates or enterprise agreements

**Setup:**

Add your provider keys to a `.env` file in your project root, or to `~/.pipelex/.env` to use them in every project:

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Google
GOOGLE_API_KEY=...

# Mistral
MISTRAL_API_KEY=...

# OpenRouter — one key for many providers' models
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

You only need to add keys for the providers you plan to use. A single OpenRouter key reaches models from many providers, but the deck's shipped defaults are OpenAI models that OpenRouter does not serve under those names: before running on OpenRouter alone, point the deck at models it serves, as [What the deck resolves to out of the box](#what-the-deck-resolves-to-out-of-the-box) describes.

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

### Option 2: Local AI (No API Keys Required)

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
    │   ├── 5_doc_gen_deck.toml        # Document engines, by format and source
    │   ├── 6_judgment_deck.toml       # Judgment config
    │   ├── x_custom_llm_deck.toml     # Custom LLM configurations
    │   └── x_custom_extract_deck.toml # Custom extract configurations
    └── routing_profiles.toml # Model routing configuration
```

To keep the configuration inside a project instead, run `pipelex init --local`: it creates the same structure in a `.pipelex/` directory at your project root, which takes precedence over the global `~/.pipelex/`.

Learn more in our [Inference Backend Configuration](../configuration/config-technical/inference-backend-config.md) guide.

### What the deck resolves to out of the box

The deck files `pipelex init` installs resolve their defaults to these models, and the default routing profile, `all_enabled_backends`, sends each model to the first enabled backend that serves it:

- **Language models** — the whole ladder is the GPT-5.6 range, served by `openai` and `azure_openai`: the premium tier and `best-gpt` are GPT-5.6 Sol, the general and large-context tiers are GPT-5.6 Terra, and the small tiers are GPT-5.6 Luna.
- **Image generation** — the general and premium tiers are GPT Image 2, the small tier is GPT Image 1 mini, both served by `openai` and `azure_openai`.
- **Document extraction** — `default-extract-document` tries Mistral OCR, which needs your Mistral key, and otherwise reads a PDF's text layer locally with pypdfium2, which needs no key but recovers no text from a scanned page. `default-extract-image` and `default-premium` are Mistral OCR only. `default-text-from-pdf` and `default-no-inference` always read the PDF locally and call no model. See [Document Extraction](../features/document-extraction.md#the-default-extractor).
- **Web search and web pages** — everything in `4_search_deck.toml`, and `default-extract-web-page` in `3_extract_deck.toml`, resolve to Linkup, so a method that searches the web or extracts from a web page needs a Linkup key.

With an OpenAI or Azure OpenAI key alone, the language and image defaults run as shipped. With any other provider, OpenRouter included, point the aliases at models it serves, as the next paragraph describes; the models each provider serves are listed under `~/.pipelex/inference/backends/`. A few presets name a model directly rather than through an alias, `retrieval-cheap`, `retrieval-premium`, `engineering-code-cheap` and `engineering-code-cheaper`, so they need overriding too. On OpenRouter, the presets that set a reasoning effort, `deep-analysis`, `quick-reasoning` and `retrieval-premium`, also need overriding without it, because its models are declared without reasoning support.

Nothing about this locks you in. The deck is a vocabulary of aliases and presets, not a provider commitment: point any of them at a model from any backend you have enabled, by editing `x_custom_llm_deck.toml`, which `pipelex update` never touches. That is also how you bring back an alias the shipped deck does not define.

---

## Next Steps

Now that you have your backend configured:

1. **Learn the concepts**: [MTHDS Language Tutorial](./mthds-language-tutorial.md)
2. **Explore examples**: [Cookbook Repository](https://github.com/Pipelex/pipelex-cookbook/tree/main)
3. **Deep dive**: [Build Reliable AI Methods](../building-methods/kick-off-a-methods-project.md)

!!! tip "Advanced Configuration"
    For detailed backend configuration options, see [Inference Backend Configuration](../configuration/config-technical/inference-backend-config.md).
