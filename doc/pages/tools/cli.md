# Pipelex CLI Documentation

The Pipelex CLI provides a command-line interface for managing and interacting with your Pipelex projects. This document outlines all available commands and their usage.

## Available Commands

### `pipelex init-libraries`

Initialize Pipelex libraries in the current directory.

```bash
pipelex init-libraries [--overwrite/-o]
```

**Options:**
- `--overwrite`, `-o`: If set, existing library files will be overwritten. Otherwise, only missing files will be created.

### `pipelex init-config`

Initialize Pipelex configuration in the current directory.

```bash
pipelex init-config [--reset/-r]
```

**Options:**
- `--reset`, `-r`: If set, existing configuration file (pipelex.toml) will be overwritten. Otherwise, the command will warn if the file already exists.

### `pipelex validate`

Run the setup sequence to validate your Pipelex configuration and pipelines.

```bash
pipelex validate
```

This command:

1. Exports libraries
2. Validates the configuration
3. Ensures all pipelines are properly set up

### `pipelex show-config`

Display the current Pipelex configuration.

```bash
pipelex show-config
```

Shows the complete configuration for your project, including all settings and parameters.
See more in our [Configuration documentation](../configuration/index.md)

### `pipelex list-pipes`

List all available pipes in your project.

```bash
pipelex list-pipes
```

Displays a table of pipes organized by domain, showing:

- Code: The unique identifier for each pipe
- Definition: Description of the pipe's purpose
- Input: Required input parameters and their concept codes
- Output: The output concept code

The output is formatted as tables grouped by domain, with concept codes simplified when they belong to the current domain.

## Usage Tips

1. Always run `pipelex validate` after making changes to your configuration or pipelines
2. Use `pipelex show-config` to debug configuration issues
3. When initializing a new project:

   - Start with `pipelex init-config`
   - Then run `pipelex init-libraries`
   - Finally, validate your setup with `pipelex validate`
