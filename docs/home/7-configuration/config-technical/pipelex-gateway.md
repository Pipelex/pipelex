# Pipelex Gateway

Pipelex Gateway is a unified inference backend that provides access to all major AI providers through a single API key. This is the **recommended approach for getting started quickly** with Pipelex.

## Quick Setup

### Step 1: Initialize Pipelex Configuration

If you haven't already initialized your Pipelex configuration, run:

```bash
pipelex init
```

When prompted, select **Pipelex Gateway** as your inference backend.

### Step 2: Configure Your API Key

1. **Get your API key if you haven't already:**
   - Visit [https://app.pipelex.com](https://app.pipelex.com) to get your API key

2. **Add the key to your environment:**
```bash
# Copy the example environment file if not already done
cp .env.example .env

# Edit .env and add your Pipelex Gateway API key
PIPELEX_GATEWAY_API_KEY="your-api-key-here"
```

### Step 3: Verify Routing Configuration

Ensure your routing profile is set to `pipelex_first` in `.pipelex/inference/routing_profiles.toml`:

```toml
active = "pipelex_first"
```

This routing profile ensures all models are routed through Pipelex Gateway by default.

## Advanced Configuration

For more advanced use cases, such as:

- Using your own provider API keys alongside Pipelex Gateway
- Custom routing profiles for specific models
- Mixing Pipelex Gateway with direct provider access
- Adding new backends

See the comprehensive [Inference Backend Configuration](inference-backend-config.md) documentation.

