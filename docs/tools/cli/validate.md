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

## An Invalid Bundle Is a Verdict

Every refusal of your method raised while it is loaded or validated is reported as an invalid bundle: the grouped `❌ Bundle validation failed` output naming each error's pipe, domain, field and file, with exit code `1`. Exit code `2` is kept for the cases where no verdict could be produced — bad arguments, a target that does not resolve, or a failure of Pipelex or its environment. This holds on every subcommand: `validate pipe` and `validate --all` render a pipe whose dry run fails the same way `validate bundle` does, where they used to print a traceback. A failing dry run is listed under `Dry Run Errors:` with one entry per failing pipe, naming the innermost pipe that failed and is not allowed to fail rather than every controller around it, and every error found while parsing gets its own entry, so a misspelled field is reported beside the other errors instead of after they are fixed. A few refusals raised while a pipe is built do not classify themselves as a fault of your method yet, and those still stop validation without a verdict.

A pipe that names a model your model deck does not define is the most common case. It is reported as an `Unknown Model` error on that pipe, with the path of the field that names it (`pipe.<code>.model`, or `pipe.<code>.model_to_structure` for the model a `PipeLLM` structures its output with) and the deck's close matches:

```text
Pipe Validation Errors:

1. Unknown Model
   Pipe: write_tide_note
   Domain: tide_tables
   Field: model
   → Pipe 'write_tide_note' (PipeLLM), field 'model': Alias 'best-sonet' was not found in the model deck

Did you mean: @best-gpt
   💡 Suggested fix: Replace model '@best-sonet' of pipe 'write_tide_note' with '@best-gpt', its one close match in the model deck
   └─ Path: pipe.write_tide_note.model
```

When the deck offers exactly one close match, as here, the error carries a suggested fix naming it. The fix is marked unsafe and `pipelex fix bundle` does not apply it on its own: the match is a guess from the spelling, and a close name can be a different model, with its own provider, cost and behaviour, so check it before you write it. With several matches, choosing among them is yours; `pipelex-agent check-model <name> -t <type>` and `pipelex-agent models -t <type>` list what the deck defines.

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
- Every model a pipe names is defined in your model deck
- Input/output connections are correct
- All referenced pipes and concepts exist
- Dry-run execution succeeds without errors, which implies the logic is correct and the pipe can be run

## Related Configuration

- [Dry Run Configuration](../../configuration/config-pipeline-validation/dry-run-config.md)
