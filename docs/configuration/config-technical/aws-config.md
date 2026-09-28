---
description: "Configure AWS authentication for Pipelex — choose between environment variables or a custom secret provider for AWS service access."
---

# AWS Configuration

Configuration section: `[runtime.aws]`

## Overview

The AWS configuration controls how Pipelex authenticates with AWS services. It supports two authentication methods: environment variables or a secret provider.

## Authentication Methods

```toml
[runtime.aws]
api_key_method = "env"  # or "secret_provider"
bedrock_access_variant = "aws_access"  # or "bedrock_token"
```

`api_key_method` says where the credentials are read from, and `bedrock_access_variant` says which credentials Anthropic models on Amazon Bedrock authenticate with. The values above are the defaults.

### Environment Variables Method (`"env"`)
When using `api_key_method = "env"`, Pipelex expects the following environment variables:

- `AWS_ACCESS_KEY_ID`: Your AWS access key ID
- `AWS_SECRET_ACCESS_KEY`: Your AWS secret access key
- `AWS_REGION`: Your AWS region

Under `bedrock_access_variant = "bedrock_token"`, Anthropic models on Bedrock authenticate with `AWS_BEARER_TOKEN_BEDROCK` instead of these three (see [Bedrock Access Variant](#bedrock-access-variant)).

Example `.env` file:
```env
AWS_ACCESS_KEY_ID=your_access_key_id
AWS_SECRET_ACCESS_KEY=your_secret_access_key
AWS_REGION=us-east-1
```

### Secret Provider Method (`"secret_provider"`)
When using `api_key_method = "secret_provider"`, Pipelex will:

1. Connect to your configured secret provider

2. Look for the same keys as environment variables:
<ul>
   <li><code>AWS_ACCESS_KEY_ID</code></li>
   <li><code>AWS_SECRET_ACCESS_KEY</code></li>
   <li><code>AWS_REGION</code></li>
</ul>

!!! warning "Secret Provider Requirements"
    To use the secret provider method, you must:
    
1. Configure a secret provider in your project using the `SecretsProviderAbstract`: See more in the [Secrets](../../advanced/secrets-provider-injection.md) documentation.
2. Store your AWS credentials in your secret provider
3. Ensure your secret provider is properly authenticated

## Bedrock Access Variant

`bedrock_access_variant` chooses how the `bedrock_anthropic` SDK, which serves the Claude models of the `bedrock` backend, authenticates with Amazon Bedrock:

- **`"aws_access"`** (the default) signs every request with AWS Signature Version 4, from `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_REGION`.
- **`"bedrock_token"`** sends a Bedrock API key as a bearer token, read from `AWS_BEARER_TOKEN_BEDROCK`.

Either way, `api_key_method` decides where those values come from: the environment under `"env"`, your secret provider under `"secret_provider"`.

### The configured variant wins

`AWS_BEARER_TOKEN_BEDROCK` is the standard name for a Bedrock API key, which AWS SDKs and other tools such as Claude Code on Bedrock read, so it is often set in a shell for reasons that have nothing to do with Pipelex. Pipelex never lets it override your configuration:

- Under `"aws_access"`, every `bedrock_anthropic` request is signed with the configured access keys, and a bearer token in the environment is ignored. If the access keys are missing, Pipelex fails with an `AwsCredentialsError` rather than falling back to the token; when the environment does carry one, that error says so and names `bedrock_access_variant = "bedrock_token"` as the way to authenticate with a bearer token.
- Under `"bedrock_token"`, the token is the only credential used, and the access keys are not read.

### The other Bedrock models

The models of the `bedrock` backend whose `sdk` is not `bedrock_anthropic` do not read `[runtime.aws]`. They follow boto's own credential chain (environment variables, the shared AWS configuration files, an instance or container role) and take their region from the backend's `aws_region` setting. In that chain, a set `AWS_BEARER_TOKEN_BEDROCK` takes precedence over access keys, so for these models a bearer token in the environment is what authenticates.

## Dependency Injection

Pipelex uses dependency injection to manage AWS clients and credentials. You can:

- Inject custom AWS client implementations
- Override default credential providers
- Mock AWS services for testing

For detailed information about dependency injection, including examples and best practices, see the [Dependency Injection](../../advanced/index.md) documentation.

## Best Practices

!!! warning "Under Construction"
    This section is currently under development.

## Related Documentation

- [Cloud Storage](../../features/cloud-storage.md) - Using cloud storage with Pipelex
- [Storage Provider Injection](../../advanced/storage-provider-injection.md) - Customize storage providers with dependency injection
