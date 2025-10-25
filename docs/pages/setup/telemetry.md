# Telemetry

## What is Telemetry?

Pipelex collects optional, anonymous usage data to help improve the product. This helps us understand how Pipelex is being used and identify areas for improvement.

## First Run Experience

When you run most Pipelex commands for the first time (after running `pipelex init`), you'll be prompted to configure your telemetry preferences:

```
======================================================================
Telemetry Configuration
======================================================================

Pipelex can collect anonymous usage data to help improve the product.

Please choose your telemetry preference:
  [1]  off          - No telemetry data collected
  [2]  anonymous    - Anonymous usage data only
  [3]  identified   - Usage data with user identification
  [q]  quit         - Exit without configuring

Enter your choice:
```

## Telemetry Modes

### Off

No telemetry data is collected. Pipelex will not send any data to our servers.

### Anonymous

Anonymous usage data only. This includes:

- Command usage (which commands are run)
- Pipeline execution statistics (success/failure rates, performance metrics)
- Feature usage patterns

This mode does **not** include:

- Personal identification
- Your prompts or system prompts
- LLM responses
- File paths or URLs
- Any sensitive information

### Identified

Same as anonymous mode, but includes a user identifier. This helps us provide better support and understand user journeys across sessions.

If you choose this mode, you can optionally provide a `user_id` in the configuration file.

## DO_NOT_TRACK Support

Pipelex respects the `DO_NOT_TRACK` environment variable. If you have `DO_NOT_TRACK` set in your environment (to any value except `false` or `0`), telemetry will be automatically disabled regardless of your configuration settings.

```bash
# Disable telemetry via environment variable
export DO_NOT_TRACK=1
```

## Changing Your Settings

You can change your telemetry settings at any time:

1. **Via configuration file**: Edit `.pipelex/telemetry.toml` directly (see [Telemetry Configuration](../configuration/config-practical/telemetry-config.md))
2. **Trigger the prompt again**: Delete `.pipelex/telemetry.toml`, and the prompt will appear next time you run a command

## Privacy

We take your privacy seriously:

- Sensitive data (prompts, responses, file paths, URLs) is automatically redacted
- You have full control over what level of telemetry you're comfortable with
- All telemetry can be completely disabled
- Our telemetry infrastructure uses PostHog, hosted in the EU

For detailed configuration options, see [Telemetry Configuration](../configuration/config-practical/telemetry-config.md).

