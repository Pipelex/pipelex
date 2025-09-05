# AWS Configuration

Configuration section: `[pipelex.aws_config]`

## Overview

The AWS configuration controls how Pipelex authenticates with AWS services. It supports two authentication methods: environment variables or a secret provider.

## Authentication Methods

```toml
[pipelex.aws_config]
api_key_method = "env"  # or "secret_provider"
```

### Environment Variables Method (`"env"`)
When using `api_key_method = "env"`, Pipelex expects the following environment variables:
- `AWS_ACCESS_KEY_ID`: Your AWS access key ID
- `AWS_SECRET_ACCESS_KEY`: Your AWS secret access key
- `AWS_REGION`: Your AWS region

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
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_REGION`

⚠️ **Important**: To use the secret provider method, you must:
1. Configure a secret provider in your project using the `SecretsProviderAbstract`: See more in the [Secrets](../../advanced-customization/secrets-provider-injection.md) documentation.
2. Store your AWS credentials in your secret provider
3. Ensure your secret provider is properly authenticated

## Dependency Injection

Pipelex uses dependency injection to manage AWS clients and credentials. You can:

- Inject custom AWS client implementations
- Override default credential providers
- Mock AWS services for testing

For detailed information about dependency injection, including examples and best practices, see the [Dependency Injection](../../advanced-customization/index.md) documentation.

## Best Practices

⚠️ Under construction
