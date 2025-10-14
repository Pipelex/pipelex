# Installation & Configuration

## Installation

Install Pipelex with pip:

```bash
pip install pipelex
```

Or use [uv](https://github.com/astral-sh/uv) for faster installs:

```bash
uv pip install pipelex
```

That's it! Pipelex is now installed. Continue to the [Quick-start Guide](../quick-start/index.md) to generate your first pipeline.

---

## API Configuration

To run pipelines with LLMs, you need to configure API access. **You have three options** - choose what works best for you:

### Option 1: Pipelex Inference (Easiest for Getting Started)

Get **free credits** for testing and development with a single API key that works with all major LLM providers:

**Benefits:**

- No credit card required
- Access to OpenAI, Anthropic, Google, Mistral, and more
- Perfect for development and testing
- Single API key for all models

**Setup:**

1. Join our Discord community to get your free API key:
   - Visit [https://go.pipelex.com/discord](https://go.pipelex.com/discord)
   - Request your key in the appropriate channel

2. Create a `.env` file in your project root:
   ```bash
   echo "PIPELEX_INFERENCE_API_KEY=your-key-here" > .env
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

# AWS Bedrock
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=...
```

You only need to add keys for the providers you plan to use.

**Configure the Inference Backend:**

When using your own keys, you need to tell Pipelex which backends to enable:

1. Initialize your configuration:
   ```bash
   pipelex init config
   ```

2. Edit `.pipelex/inference/backends.toml` to enable your providers

For example, to use Google models:

```toml
[google]
enabled = true
```

Learn more in our [Inference Backend Configuration](../configuration/config-technical/inference-backend-config.md) guide.

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

## Initialize Configuration

To set up Pipelex configuration files, run:

```bash
pipelex init config
```

This creates a `.pipelex/` directory with:

- `pipelex.toml`: Feature flags, logging, cost reporting
- `inference/`: LLM configuration and model presets

Learn more in our [Configuration documentation](../configuration/index.md).

---

## Project Organization

Pipelex automatically discovers `.plx` pipeline files anywhere in your project (excluding `.venv`, `.git`, `node_modules`, etc.).

**Recommended: Keep pipelines with related code**

```bash
your_project/
├── my_project/             # Your Python package
│   ├── finance/
│   │   ├── services.py
│   │   ├── invoices.plx           # Pipeline with finance code
│   │   └── invoices_struct.py     # Structure classes
│   └── legal/
│       ├── services.py
│       ├── contracts.plx          # Pipeline with legal code
│       └── contracts_struct.py
├── .pipelex/                      # Config at repo root
│   └── pipelex.toml
├── .env                           # API keys (git-ignored)
└── requirements.txt
```

**Alternative: Centralize pipelines**

```bash
your_project/
├── pipelines/
│   ├── invoices.plx
│   ├── contracts.plx
│   └── structures.py
└── .pipelex/
    └── pipelex.toml
```

Learn more in our [Project Structure documentation](../build-reliable-ai-workflows-with-pipelex/kick-off-a-knowledge-pipeline-project.md).

---

## Prerequisites

- **Python**: Version 3.10 or above
- **API Access**: One of the three options above (Pipelex Inference, your own keys, or local AI)

---

## Next Steps

Now that you have Pipelex installed and configured:

1. **Start generating pipelines**: [Quick-start Guide](../quick-start/index.md)
2. **Explore examples**: [Cookbook Repository](https://github.com/Pipelex/pipelex-cookbook)
3. **Learn the concepts**: [The Pipelex Paradigm](../pipelex-paradigm-for-repeatable-ai-workflows/index.md)
4. **Deep dive**: [Build Reliable AI Workflows](../build-reliable-ai-workflows-with-pipelex/kick-off-a-knowledge-pipeline-project.md)

💡 Need help? Check out our [Cookbook](https://github.com/Pipelex/pipelex-cookbook) for practical examples!
