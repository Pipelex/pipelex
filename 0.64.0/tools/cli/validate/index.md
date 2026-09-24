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

- `NAME` - The name of the installed method to validate, a method address (`github.com/owner/repo[/name][@tag]`), or a GitHub URL — see [Run a Method by Address](run-by-address.md)

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

## Suggested Fixes

When a validation error has a deterministic safe fix, the error output includes a `💡 Suggested fix:` line describing the change, and the report ends with the exact command to apply every suggested fix automatically:

```text
💡 1 of these errors can be fixed automatically — run: pipelex fix bundle my_pipeline.mthds
```

See [Fix Commands](fix.md) for `pipelex fix bundle`, including the `--diff` preview.

## Advisory Warnings

A bundle can be valid and still be worth commenting on. When it is, `pipelex validate bundle` and `pipelex validate --all` print one yellow `Warning:` line per finding — advisory only: a warning never changes the verdict or the exit code. The lines come out ahead of the success message, and ahead of the strict pending-signature gate too, so a method still holding an unimplemented `PipeSignature` placeholder shows its warnings even though the command exits non-zero. Three families are reported, always in this order:

- `optional_force_redundant` — a `!` (force) input whose slot is guaranteed present in every analyzed flow, so the assertion can never fire.
- `input_presence_vacuous` — a method input (an input of the bundle's declared `main_pipe`) that must be supplied, but whose concept declares no required field: the empty object satisfies it, so a caller cannot tell what to fill in.
- `hint_unknown_key`, `hint_unknown_intent`, `hint_inapplicable_intent` — the [intent-hint](../../building-methods/concepts/intent-hints.md) lints. Hints are non-normative, so the entry is preserved and only named.

The same findings ride the `warnings` array of the [agent CLI](agent-cli.md)'s JSON envelope and of the validation report, built from one composition point, so the surfaces cannot disagree. See [Understanding Optionality](../../building-methods/pipes/understanding-optionality.md) for what each one means for your method.

## What Validation Checks

All validation commands check:

- Syntax correctness of `.mthds` files
- Concept and pipe definitions are valid
- Input/output connections are correct
- All referenced pipes and concepts exist
- Dry-run execution succeeds without errors, which implies the logic is correct and the pipe can be run

## Related Configuration

- [Dry Run Configuration](../../configuration/config-pipeline-validation/dry-run-config.md)
