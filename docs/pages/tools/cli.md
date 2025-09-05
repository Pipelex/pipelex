# Pipelex CLI Documentation

The Pipelex CLI provides a command-line interface for managing and interacting with your Pipelex projects. This document outlines all available commands and their usage.

## Available Commands

### Init group

Initialize project assets.

```bash
pipelex init libraries [DIRECTORY] [--overwrite/-o]
pipelex init config [--reset/-r]
```

### Validate group

Validate configuration and pipelines.

```bash
pipelex validate all [-c/--config-folder-path PATH]
pipelex validate pipe PIPE_CODE [-c/--config-folder-path PATH]
```

### Show group

Inspect configuration and pipes.

```bash
pipelex show config
pipelex show pipes [-c/--config-folder-path PATH]
pipelex show pipe PIPE_CODE [-c/--config-folder-path PATH]
```

### Migrate group

Migrate TOML files to the new syntax.

```bash
pipelex migrate run [-p/--path PATH] [--dry-run] [--backups/--no-backups]
```

## Usage Tips

1. Always run `pipelex validate all -c path/to/your/pipelex/config/folder` after making changes to your configuration or pipelines
2. Use `pipelex show config` to debug configuration issues
3. When initializing a new project:
   - Start with `pipelex init config`
   - Then run `pipelex init libraries`
   - Finally, validate your setup with `pipelex validate all -c path/to/your/pipelex/config/folder`
