---
description: "Automatically fix validation errors in your .mthds bundles with deterministic, safe fixes — preview with --diff or apply in place."
---

# Fix Commands

Apply deterministic, safe fixes to a bundle and re-validate until it is valid.

```bash
pipelex fix bundle ...    # Fix a bundle file or directory in place
```

When `pipelex validate` reports errors that have a deterministic fix, each one carries a `💡 Suggested fix:` line and the output ends with the exact `pipelex fix bundle` command to run. The fix command runs a validate → apply safe fixes → re-validate loop until the bundle is valid, out of fixes, or the iteration cap is reached — and names every change it makes.

## Fix Bundle

```bash
pipelex fix bundle <PATH>
```

Fixes a bundle file (`.mthds`) or a pipeline directory in place. When a directory is given, the bundle file is auto-detected inside it — exactly the same resolution as `pipelex validate bundle`, so fix patches exactly what validate judged.

**Arguments:**

- `PATH` - Path to a `.mthds` bundle file or a directory containing one

**Options:**

- `--library-dir`, `-L` - Directory to search for additional pipe definitions. Can be specified multiple times. Files under these directories are inside the fix write scope; files loaded any other way are never written.
- `--diff` - Preview: show the changes as a unified diff without writing any file. Exit codes keep the same verdict semantics, so `--diff` answers "would it converge?"
- `--select` - Only apply the named fix rule code (repeatable)
- `--ignore` - Skip the named fix rule code (repeatable; mutually exclusive with `--select`)
- `--max-iterations` - Maximum fix-apply rounds before reporting non-convergence
- `--allow-signatures` - Accept `PipeSignature` placeholders in the dependency graph (lenient mode). See [Signature Pipes](../../building-methods/pipes/signature-pipes.md).

**Examples:**

```bash
# Fix a bundle file in place
pipelex fix bundle my_pipeline.mthds

# Preview the changes without writing anything
pipelex fix bundle my_pipeline.mthds --diff

# Fix a pipeline directory (auto-detects the bundle file)
pipelex fix bundle pipelines/invoice_processor/

# Fix with additional library directories (also widens the write scope)
pipelex fix bundle my_bundle.mthds -L ./shared_pipes

# Only apply one fix rule
pipelex fix bundle my_bundle.mthds --select match-sequence-output
```

## Exit Codes

- `0` - The bundle is valid after the run (fixed, or already valid)
- `1` - Negative verdict: the bundle is still invalid, or valid but not runnable (pending `PipeSignature` placeholders without `--allow-signatures`)
- `2` - No verdict: bad path, ambiguous bundle directory, invalid rule filter, or an unexpected failure

## What Gets Fixed

Only fixes classified as SAFE are applied — deterministic corrections derived from the structured validation errors, never from guesswork. Errors without a safe deterministic fix are left in place and reported as remaining errors. The available fix rule codes (for `--select`/`--ignore`) are listed in the error message when you pass an unknown code.

## Related Documentation

- [Validate Commands](validate.md) - Where suggested fixes are surfaced
