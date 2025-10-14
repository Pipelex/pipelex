# Pipelex CLI Documentation

The Pipelex CLI provides a command-line interface for managing and interacting with your Pipelex projects. This document outlines all available commands and their usage.

## Available Commands

### Init group

Initialize project configuration.

```bash
pipelex init config [--reset/-r]
```

### Validate group

Validate configuration and pipelines.

```bash
pipelex validate all
pipelex validate pipe PIPE_CODE
```

### Show group

Inspect configuration and pipes.

```bash
pipelex show config
pipelex show pipes
pipelex show pipe PIPE_CODE
```

## Usage Tips

1. Always run `pipelex validate all` after making changes to your configuration or pipelines
2. Use `pipelex show config` to debug configuration issues
3. Use `pipelex show pipes` to see all discovered pipelines
4. When initializing a new project:
   - Run `pipelex init config` to create configuration files
   - Create your `.plx` pipeline files anywhere in your project
   - Validate your setup with `pipelex validate all`
