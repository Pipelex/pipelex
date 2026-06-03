---
description: "Validate your pipeline definitions, .mthds bundles, and installed method packages for correctness before running them in Pipelex."
---

# Validate Commands

Validate your pipeline definitions and configuration for correctness.

The `validate` command has three subcommands depending on what you want to validate:

```bash
pipelex validate pipe ...      # Validate a pipe from your project's library
pipelex validate bundle ...    # Validate a bundle file or directory
pipelex validate method ...    # Validate an installed method package
```

!!! tip "Shorthand"
    `pipelex validate --all` and `pipelex validate <pipe_code>` are shortcuts that default to the `pipe` subcommand. You can omit `pipe` for convenience.

## Validate Pipe

```bash
pipelex validate pipe <PIPE_CODE>
pipelex validate pipe --all
```

Validates and dry-runs a specific pipe from your imported packages, or all pipes at once.

**Arguments:**

- `PIPE_CODE` - The pipe code to validate (omit when using `--all`)

**Options:**

- `--all`, `-a` - Validate all discovered pipes
- `--library-dir`, `-L` - Directory to search for pipe definitions. Can be specified multiple times.
- `--allow-signatures` - Accept `PipeSignature` placeholders in the dependency graph (lenient mode). See [Signature Pipes](../../building-methods/pipes/signature-pipes.md).

**Examples:**

```bash
# Validate a specific pipe
pipelex validate analyze_cv_matching
pipelex validate write_weekly_report

# Validate all pipes
pipelex validate --all

# Explicit subcommand form also works
pipelex validate pipe --all

# Validate with custom library directories
pipelex validate my_pipe -L ./pipelines
pipelex validate --all -L ./pipelines -L ./shared_pipes

# Allow PipeSignature placeholders during dry-run
pipelex validate my_draft_pipe --allow-signatures
pipelex validate --all --allow-signatures
```

## Validate Bundle

```bash
pipelex validate bundle <PATH>
```

Validates all pipes defined in a bundle file (`.mthds`) or a pipeline directory. When a directory is given, the bundle file is auto-detected inside it.

**Arguments:**

- `PATH` - Path to a `.mthds` bundle file or a directory containing one

**Options:**

- `--library-dir`, `-L` - Directory to search for additional pipe definitions. Can be specified multiple times.
- `--allow-signatures` - Accept `PipeSignature` placeholders in the dependency graph (lenient mode). See [Signature Pipes](../../building-methods/pipes/signature-pipes.md).

**Examples:**

```bash
# Validate a bundle file
pipelex validate bundle my_pipeline.mthds
pipelex validate bundle pipelines/invoice_processor.mthds

# Validate a pipeline directory (auto-detects the bundle file)
pipelex validate bundle pipelines/invoice_processor/

# Validate with additional library directories
pipelex validate bundle my_bundle.mthds -L ./shared_pipes

# Allow PipeSignature placeholders during dry-run
pipelex validate bundle methods/draft_pipeline.mthds --allow-signatures
```

!!! note
    When validating a bundle, ALL pipes in that bundle are validated, not just the main pipe.

## Validate Method

```bash
pipelex validate method <NAME>
```

Validates all pipes in an installed method package.

**Arguments:**

- `NAME` - The name of the installed method to validate

**Options:**

- `--pipe PIPE_CODE` - Validate only a specific pipe within the method
- `--library-dir`, `-L` - Directory to search for additional pipe definitions. Can be specified multiple times.

**Examples:**

```bash
# Validate an installed method
pipelex validate method invoice_extractor

# Validate a specific pipe within a method
pipelex validate method invoice_extractor --pipe extract_amounts
```

## What Validation Checks

All validation commands check:

- Syntax correctness of `.mthds` files
- Concept and pipe definitions are valid
- Input/output connections are correct
- All referenced pipes and concepts exist
- Dry-run execution succeeds without errors, which implies the logic is correct and the pipe can be run

## Related Configuration

- [Dry Run Configuration](../../configuration/config-pipeline-validation/dry-run-config.md)
