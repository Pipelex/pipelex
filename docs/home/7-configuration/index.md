# Configuration

## Overview

Pipelex uses a TOML-based configuration system. The main configuration file `pipelex.toml` must be located at the root of your project. You can create this file by running:

```bash
pipelex init config
```

!!! important "Configuration Setup Notes"
    1. `pipelex init config` creates a **template** configuration file with sample settings. It does not include all possible configuration options - it's meant as a starting point.
    2. Using `pipelex init config --reset` will **overwrite** your existing `pipelex.toml` file without warning. Make sure to backup your configuration before using this flag.

For a complete list of all possible configuration options, refer to the configuration group documentation below.

## Configuration Structure

The configuration is organized into three main sections:

1. `[pipelex]` - Core Pipelex settings
2. `[cogt]` - Cognitive tools and LLM settings
3. `[plugins]` - Plugin-specific configurations

Each section contains multiple subsections for specific features and functionalities.

## Configuration Override System

Pipelex uses a sophisticated configuration override system that loads and merges configurations in a specific order. This allows for fine-grained control over settings in different environments and scenarios.

The exact loading sequence is:

1. Base configuration from the installed Pipelex package (`pipelex.toml`)
2. Your project's base configuration (`pipelex.toml` in your project root)
3. Local overrides (`pipelex_local.toml`)
4. Environment-specific overrides (`pipelex_{environment}.toml`)
   - Example environments: dev, staging, prod -> based on the environment variable `ENV` in your .env file
5. Run mode overrides (`pipelex_{run_mode}.toml`)
   - Example run modes: normal, unit_test
6. Super user overrides (`pipelex_super.toml`) (recommended to put in .gitignore)

Each subsequent configuration file in this sequence can override settings from the previous ones. This means:

- Settings in `pipelex_local.toml` override the base configuration
- Environment-specific settings override local settings
- Run mode settings override environment settings
- Super user settings override all previous settings

### Override File Naming

- Base config: `pipelex.toml`
- Local overrides: `pipelex_local.toml`
- Environment overrides: `pipelex_dev.toml`, `pipelex_staging.toml`, `pipelex_prod.toml`, etc.
- Run mode overrides: `pipelex_normal.toml`, `tests/pipelex_unit_test.toml`, etc.
- Super user overrides: `pipelex_super.toml`

NB: The run_mode unit_test is used for testing purposes.

### Best Practices for Overrides

1. Use the base `pipelex.toml` for default settings
2. Use `pipelex_local.toml` for machine-specific settings
3. Use environment files for environment-specific settings (dev, staging, prod)
4. Use run mode files for normal or unit_test configurations
5. Use `pipelex_super.toml` sparingly, only for temporary overrides (add to .gitignore)

## Best Practices

1. **Version Control**: Include your base `pipelex.toml` in version control
2. **Environment Overrides**: Use environment-specific files for sensitive or environment-dependent settings
3. **Documentation**: Comment any custom settings for team reference
4. **Validation**: Run `pipelex validate all` after making configuration changes
5. **Gitignore**: Add local and sensitive override files to `.gitignore`
