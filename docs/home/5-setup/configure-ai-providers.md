# Configure AI Providers

## Configure API Access

To run pipelines with LLMs, you need to configure API access. **You have three options** - choose what works best for you:

### Option 1: Pipelex Inference (Easiest for Getting Started)

Get **free credits** for testing and development with a single API key that works with all major LLM providers:

**Benefits:**

- No credit card required
- Access to OpenAI, Anthropic Claude, Google Gemini, and xAI Grok
- Perfect for development and testing
- Single API key for all models

**Setup:**

1. Join our Discord community to get your free API key:
   
- Visit [https://go.pipelex.com/discord](https://go.pipelex.com/discord)
- Request your key in the appropriate channel

2. Create a `.env` file in your project root:
   ```env
   PIPELEX_INFERENCE_API_KEY=your-key-here
   ```

That's it! Your pipelines can now access any supported LLM.

### Option 2: Bring Your Own API Keys

Use your existing API keys from LLM providers. This is ideal if you:

- Already have API keys from providers
- Need to use specific accounts for billing
- Have negotiated rates or enterprise agreements

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

See [Inference Backend Configuration](../../home/7-configuration/config-technical/inference-backend-config.md) for all options.

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

Configure these in `.pipelex/inference/backends.toml`. See our [Inference Backend Configuration](../../home/7-configuration/config-technical/inference-backend-config.md) for details.

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
└── inference/                # LLM configuration and model presets
    ├── backends.toml         # Enable/disable model providers
    ├── deck/
    │   └── base_deck.toml    # LLM presets and aliases
    └── routing_profiles.toml # Model routing configuration
```

Learn more in our [Inference Backend Configuration](../../home/7-configuration/config-technical/inference-backend-config.md) guide.

---

## Next Steps

Now that you have your backend configured:

1. **Organize your project**: [Project Organization](./project-organization.md)
2. **Learn the concepts**: [Writing Workflows Tutorial](../../home/2-get-started/pipe-builder.md)
3. **Explore examples**: [Cookbook Repository](https://github.com/Pipelex/pipelex-cookbook)
4. **Deep dive**: [Build Reliable AI Workflows](../../home/6-build-reliable-ai-workflows/kick-off-a-pipelex-workflow-project.md)

!!! tip "Advanced Configuration"
    For detailed backend configuration options, see [Inference Backend Configuration](../../home/7-configuration/config-technical/inference-backend-config.md).

