# Validate Commands

Validate your pipeline definitions and configuration for correctness.

## Validate All Pipes

```bash
pipelex validate --all
```

Performs comprehensive validation:

1. Validates all library configurations
2. Runs static validation on all discovered pipes
3. Performs dry-run execution to check pipeline logic

This is the recommended validation to run before committing changes or deploying pipelines.

**Options:**

- `--library-dir`, `-L` - Directory to search for pipe definitions. Can be specified multiple times.

**Examples:**

```bash
# Validate everything
pipelex validate --all

# Validate with custom library directories
pipelex validate --all -L ./pipelines -L ./shared_pipes
```

## Validate Single Pipe

```bash
pipelex validate PIPE_CODE
pipelex validate --pipe PIPE_CODE
```

Validates and dry-runs a specific pipe from your imported packages, useful for iterative development.

**Arguments:**

- `PIPE_CODE` - The pipe code to validate as a positional argument, or use `--pipe` option

**Options:**

- `--pipe PIPE_CODE` - Explicitly specify the pipe code to validate (alternative to positional argument)
- `--library-dir`, `-L` - Directory to search for pipe definitions. Can be specified multiple times.

**Examples:**

```bash
# Validate a specific pipe (positional argument)
pipelex validate analyze_cv_matching
pipelex validate write_weekly_report

# Validate a specific pipe (explicit option)
pipelex validate --pipe analyze_cv_matching

# Validate with custom library directories
pipelex validate my_pipe -L ./pipelines
```

## Validate Bundle

```bash
pipelex validate BUNDLE_FILE.mthds
pipelex validate --bundle BUNDLE_FILE.mthds
```

Validates all pipes defined in a bundle file. The command automatically detects `.mthds` files as bundles.

**Arguments:**

- `BUNDLE_FILE.mthds` - Path to the bundle file (auto-detected by `.mthds` extension)

**Options:**

- `--bundle BUNDLE_FILE.mthds` - Explicitly specify the bundle file path
- `--library-dir`, `-L` - Directory to search for additional pipe definitions. Can be specified multiple times.

**Examples:**

```bash
# Validate a bundle (auto-detected)
pipelex validate my_pipeline.mthds
pipelex validate pipelines/invoice_processor.mthds

# Validate a bundle (explicit option)
pipelex validate --bundle my_pipeline.mthds

# Validate a bundle with additional library directories
pipelex validate my_bundle.mthds -L ./shared_pipes
```

!!! note
    When validating a bundle, ALL pipes in that bundle are validated, not just the main pipe.

## Validate Specific Pipe in Bundle

```bash
pipelex validate --bundle BUNDLE_FILE.mthds --pipe PIPE_CODE
```

Validates all pipes in a bundle, while ensuring a specific pipe exists in that bundle. The entire bundle is validated, not just the specified pipe.

**Options:**

- `--bundle BUNDLE_FILE.mthds` - Path to the bundle file
- `--pipe PIPE_CODE` - Pipe code that must exist in the bundle

**Examples:**

```bash
# Validate bundle and ensure specific pipe exists in it
pipelex validate --bundle my_pipeline.mthds --pipe extract_invoice
pipelex validate --bundle invoice_processor.mthds --pipe validate_amounts
```

!!! important "Bundle Validation Behavior"
    The specified pipe must be defined in the bundle. This is useful when you want to validate a bundle and confirm a specific pipe is present and valid within it. However, the entire bundle will be validated regardless.

## What Validation Checks

All validation commands check:

- Syntax correctness of `.mthds` files
- Concept and pipe definitions are valid
- Input/output connections are correct
- All referenced pipes and concepts exist
- Dry-run execution succeeds without errors, which implies the logic is correct and the pipe can be run

## Related Configuration

- [Dry Run Configuration](../../7-configuration/config-pipeline-validation/dry-run-config.md)

