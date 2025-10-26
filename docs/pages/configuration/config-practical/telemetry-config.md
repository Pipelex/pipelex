# Telemetry Configuration

## Overview

Telemetry configuration is stored in `.pipelex/telemetry.toml`, separate from the main `pipelex.toml` configuration. This file is created automatically the first time you run a Pipelex command (after `pipelex init config`) and are prompted to choose your telemetry preference.

For a user-friendly introduction to telemetry, see [Telemetry Setup](../../setup/telemetry.md).

## Configuration File Location

```
.pipelex/telemetry.toml
```

This file is created in the `.pipelex` directory at your project root.

## Configuration Options

### Example Configuration

```toml
telemetry_mode = "off"
host = "https://eu.i.posthog.com"
project_api_key = "phc_HPJnNKpIXh0SxNDYyTAyUtnq9KxNNZJWQszynsWVx4Y"
respect_dnt = true
redact = ["prompt", "system_prompt", "response", "file_path", "url"]
geoip_enabled = true
dry_mode_enabled = false
verbose_enabled = false
user_id = ""
```

### Settings Reference

#### `telemetry_mode`

- **Type**: `string`
- **Default**: `"off"`
- **Allowed values**: `"off"`, `"anonymous"`, `"identified"`
- **Description**: Controls the telemetry collection mode.
  - `"off"`: No telemetry data is collected
  - `"anonymous"`: Anonymous usage data only (no user identification)
  - `"identified"`: Usage data with user identification (requires `user_id` to be set)

#### `host`

- **Type**: `string`
- **Default**: `"https://eu.i.posthog.com"`
- **Description**: The PostHog server host URL. We use the EU-hosted instance for privacy compliance.

**Note**: This is typically not changed unless you're self-hosting PostHog.

#### `project_api_key`

- **Type**: `string`
- **Default**: `"phc_HPJnNKpIXh0SxNDYyTAyUtnq9KxNNZJWQszynsWVx4Y"`
- **Description**: The PostHog project API key for the Pipelex telemetry project.

**Note**: This is typically not changed unless you're using a custom telemetry backend.

#### `respect_dnt`

- **Type**: `boolean`
- **Default**: `true`
- **Description**: When `true`, Pipelex respects the `DO_NOT_TRACK` environment variable. If `DO_NOT_TRACK` is set to any value except `false` or `0`, telemetry is automatically disabled.

#### `redact`

- **Type**: `array` of `string`
- **Default**: `["prompt", "system_prompt", "response", "file_path", "url"]`
- **Description**: List of event properties to redact from telemetry data. These sensitive fields are automatically filtered out before any data is sent.

**Privacy protection**: This ensures that your actual prompts, LLM responses, and file paths are never transmitted to telemetry servers.

#### `debug`

- **Type**: `boolean`
- **Default**: `false`
- **Description**: When `true`, telemetry events are logged locally but not actually sent to PostHog. Useful for debugging telemetry implementation.

#### `user_id`

- **Type**: `string`
- **Default**: `""`
- **Description**: User identifier for the `"identified"` telemetry mode. If `telemetry_mode` is set to `"identified"` but `user_id` is empty, telemetry falls back to anonymous mode.

**Usage**: Set this to your email, username, or any identifier you prefer when using identified mode.

## Manually Changing Settings

Edit `.pipelex/telemetry.toml` directly. Changes take effect on the next command run.

```toml
telemetry_mode = "off"         # Disable telemetry
telemetry_mode = "anonymous"   # Enable anonymous telemetry
```

### Example: Enable Identified Telemetry

```toml
telemetry_mode = "identified"
user_id = "user@example.com"
```

## Re-triggering the Configuration Prompt

If you want to see the configuration prompt again (for example, to change your choice through the interactive interface), delete the `.pipelex/telemetry.toml` file:

```bash
rm .pipelex/telemetry.toml
```

The next time you run a Pipelex command (except `pipelex init`), you'll be prompted to choose your telemetry preference.

## Environment Variable Override

The `DO_NOT_TRACK` environment variable provides a universal way to disable telemetry:

```bash
# Linux/MacOS
export DO_NOT_TRACK=1

# Windows PowerShell
$env:DO_NOT_TRACK="1"

# Windows CMD
set DO_NOT_TRACK=1
```

When `respect_dnt = true` (the default), this will disable all telemetry regardless of the `telemetry_mode` setting.

## What Data is Collected?

When telemetry is enabled (anonymous or identified mode), Pipelex collects:

- Whole pipeline execution events (start, success, failure)
- Each pipe execution events (start, success, failure)

soon to be added:
- Error types (without error messages)
- Command usage (which CLI commands are run)
- Feature usage patterns (which pipe types are used)
- Performance metrics (execution time, token usage)

**Never collected** (automatically redacted):

- Your prompts or system prompts
- LLM responses
- File paths
- URLs
- Any content from your documents or images
- Personal data (unless you explicitly set a `user_id` in identified mode)

## Privacy and Compliance

- Telemetry is **opt-in** via the first-run prompt
- All sensitive data is **automatically redacted**
- We use **PostHog** (EU-hosted) for telemetry infrastructure
- We **respect DO_NOT_TRACK** by default
- You can **completely disable** telemetry at any time
- Telemetry configuration is **stored locally** in your project

For more information about our data practices, see our [privacy policy](https://pipelex.com/privacy-policy).

