# Plugins Configuration

The Plugins Configuration manages all external service integrations in Pipelex, including various LLM providers and image generation services.

## Overview

```toml
[pipelex.plugins]
# Plugin sections
[pipelex.plugins.anthropic_config]
[pipelex.plugins.azure_openai_config]
[pipelex.plugins.bedrock_config]
[pipelex.plugins.vertexai_config]
[pipelex.plugins.mistral_config]
[pipelex.plugins.openai_config]
[pipelex.plugins.perplexity_config]
[pipelex.plugins.xai_config]
[pipelex.plugins.custom_endpoint_config]
[pipelex.plugins.fal_config]
```

## Common Authentication Methods

Most plugins support two authentication methods:

- `ENV`: Read credentials from environment variables
- `SECRET_PROVIDER`: Read credentials from a secrets provider

## Plugin-Specific Configurations

### 1. Anthropic Configuration

```toml
[pipelex.plugins.anthropic_config]
# Use 8192 for better streaming/timeout handling, or "unlimited" for full 32/64K tokens (Opus/Sonnet)
claude_4_reduced_tokens_limit = 8192
api_key_method = "env"  # or "secret_provider"
```

Environment Variables:

- `ANTHROPIC_API_KEY`: API key for Anthropic services

### 2. Azure OpenAI Configuration

```toml
[pipelex.plugins.azure_openai_config]
api_key_method = "env"  # or "secret_provider"
```

Environment Variables:

- `AZURE_OPENAI_API_KEY`: API key
- `AZURE_OPENAI_API_ENDPOINT`: API endpoint URL
- `AZURE_OPENAI_API_VERSION`: API version

### 3. AWS Bedrock Configuration

```toml
[pipelex.plugins.bedrock_config]
client_method = "aioboto3"  # or "boto3"
```

Environment Variables:

- `AWS_REGION`: AWS region for Bedrock services

### 4. Google Vertex AI Configuration

```toml
[pipelex.plugins.vertexai_config]
api_key_method = "env"  # or "secret_provider"
```

Environment Variables:

- `GCP_PROJECT_ID`: Google Cloud project ID
- `GCP_REGION`: Google Cloud region
- `GCP_CREDENTIALS_FILE_PATH`: Path to service account credentials file

Dependencies:

- Requires `google-auth-oauthlib` package (`pip install pipelex[google]`)

### 5. Mistral Configuration

```toml
[pipelex.plugins.mistral_config]
api_key_method = "env"  # or "secret_provider"
```

Environment Variables:

- `MISTRAL_API_KEY`: API key for Mistral services

### 6. OpenAI Configuration

```toml
[pipelex.plugins.openai_config]
image_output_compression = 100  # 1-100
api_key_method = "env"  # or "secret_provider"
```

Environment Variables:

- `OPENAI_API_KEY`: API key for OpenAI services

### 7. Perplexity Configuration

```toml
[pipelex.plugins.perplexity_config]
api_key_method = "env"  # or "secret_provider"
```

Environment Variables:

- `PERPLEXITY_API_KEY`: API key
- `PERPLEXITY_API_ENDPOINT`: API endpoint URL

### 8. XAI Configuration

```toml
[pipelex.plugins.xai_config]
api_key_method = "env"  # or "secret_provider"
```

Environment Variables:

- `XAI_API_KEY`: API key
- `XAI_API_ENDPOINT`: API endpoint URL

### 9. Custom Endpoint Configuration

For custom OpenAI-compatible endpoints (e.g., Ollama, LM Studio):

```toml
[pipelex.plugins.custom_endpoint_config]
api_key_method = "env"  # or "secret_provider"
```

Environment Variables:

- `CUSTOM_ENDPOINT_API_KEY`: Optional API key
- `CUSTOM_ENDPOINT_BASE_URL`: Base URL for the custom endpoint

### 10. FAL Configuration

Configuration for FAL image generation services:

```toml
[pipelex.plugins.fal_config]
# Quality to steps mapping for Flux model
flux_map_quality_to_steps = { 
    "low" = 14,
    "medium" = 28,
    "high" = 56
}

# Quality to steps mapping for SDXL Lightning model
sdxl_lightning_map_quality_to_steps = {
    "low" = 2,
    "medium" = 4,
    "high" = 8
}
```

## Error Handling

Each plugin has its own error types:

- `AnthropicCredentialsError`
- `AzureOpenAICredentialsError`
- `BedrockCredentialsError`
- `VertexAICredentialsError`
- `MistralCredentialsError`
- `OpenAICredentialsError`
- `PerplexityCredentialsError`
- `XaiCredentialsError`
- `CustomEndpointCredentialsError`

## Best Practices

1. **Credentials Management**:

    - Use environment variables for local development
    - Use secrets provider for production environments
    - Never commit credentials to version control

2. **Error Handling**:

    - Always handle credential errors appropriately
    - Implement proper fallbacks when using multiple providers
    - Check for required dependencies (especially for Google services)

3. **Configuration**:

    - Set appropriate quality levels for image generation
    - Configure retry limits and timeouts
    - Use appropriate client methods for async/sync operations

## Example Complete Configuration

```toml
[pipelex.plugins]

[pipelex.plugins.anthropic_config]
claude_4_reduced_tokens_limit = 8192  # Use "unlimited" for full 32/64K tokens
api_key_method = "env"

[pipelex.plugins.azure_openai_config]
api_key_method = "env"

[pipelex.plugins.bedrock_config]
client_method = "aioboto3"

[pipelex.plugins.vertexai_config]
api_key_method = "env"

[pipelex.plugins.mistral_config]
api_key_method = "env"

[pipelex.plugins.openai_config]
image_output_compression = 100
api_key_method = "env"

[pipelex.plugins.perplexity_config]
api_key_method = "env"

[pipelex.plugins.xai_config]
api_key_method = "env"

[pipelex.plugins.custom_endpoint_config]
api_key_method = "env"

[pipelex.plugins.fal_config]
flux_map_quality_to_steps = { "low" = 14, "medium" = 28, "high" = 56 }
sdxl_lightning_map_quality_to_steps = { "low" = 2, "medium" = 4, "high" = 8 }
```
