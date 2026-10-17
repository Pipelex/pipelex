---
description: "Automatically fix validation errors in your .mthds bundles with deterministic, safe fixes — preview with --diff or apply in place."
---

# Fix Commands

Apply deterministic, safe fixes to a bundle and re-validate until it is valid, or migrate a method's `PipeFunc` function names to import paths.

```bash
pipelex fix bundle ...            # Fix a bundle file or directory in place
pipelex fix function-names ...    # Rewrite a method's flat PipeFunc function names as import paths
```

When `pipelex validate` reports errors that have a deterministic safe fix, each one carries a `💡 Suggested fix:` line and the output ends with the exact `pipelex fix bundle` command to run. The fix command runs a validate → apply safe fixes → re-validate loop until the bundle is valid, out of fixes, or the iteration cap is reached — and names every change it makes.

## Fix Bundle

```bash
pipelex fix bundle <PATH>
```

Fixes a bundle file (`.mthds`) or a method's folder in place. A folder is read as its [method tree](../../building-methods/method-trees.md) and judged whole, every bundle of it, exactly as `pipelex validate bundle` judges it, so fix patches exactly what validate judged; it needs no pipe to start at, so a folder whose bundles declare several `main_pipe`s, or none, is fixed like any other. The folder joins the library directories, so every file of it is inside the fix write scope, and a fix lands in the file its error names.

**Arguments:**

- `PATH` - Path to a `.mthds` bundle file or a method's folder

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

# Fix a method's folder (every bundle of its method tree)
pipelex fix bundle pipelines/invoice_processor/

# Fix with additional library directories (also widens the write scope)
pipelex fix bundle my_bundle.mthds -L ./shared_pipes

# Only apply one fix rule
pipelex fix bundle my_bundle.mthds --select match-sequence-output
```

## Exit Codes

- `0` - The bundle is valid after the run (fixed, or already valid)
- `1` - Negative verdict: the bundle is still invalid, or valid but not runnable (pending `PipeSignature` placeholders without `--allow-signatures`)
- `2` - No verdict: bad path, a folder holding no `.mthds` bundle, invalid rule filter, or an unexpected failure

## What Gets Fixed

Only fixes classified as SAFE are applied — deterministic corrections derived from the structured validation errors, never from guesswork. Errors without a safe deterministic fix are left in place and reported as remaining errors. An unsafe fix, such as `rename-model` for a model name the deck only nearly matches, still shows on its error, labelled `💡 Suggested fix (unsafe, confirm before applying):`, for you to check and apply by hand, and is not a code `--select` or `--ignore` accepts. One rule is safe on some errors and unsafe on others: `delete-redundant-dotted-input` deletes a dotted input key such as `"page.page_view" = "Image"` whose root `page` is declared beside it, and it is safe when the root keeps its presence marker and multiplicity. When the key, declared after its root, carries another presence marker or multiplicity than the root, as `"data.text" = "Text!"` after `data = "Text?"` does, deleting it would change what a run requires, so that fix is unsafe and names only what differs, the multiplicity, the presence marker or both, with the edit that carries it onto the root; `--select` accepts the code and applies only its safe fixes. The available fix rule codes (for `--select`/`--ignore`) are listed in the error message when you pass an unknown code.

## Fix Function Names

```bash
pipelex fix function-names <PATH>
```

Rewrites every flat `PipeFunc` `function_name` of a method as the function's import path from the method's folder. A `PipeFunc` step names its function by import path, such as `funcs.totals.compute_totals` for the function `compute_totals` of `funcs/totals.py`, and a flat name, the key of the retired function registry, is refused as the bundle is read (see [PipeFunc](../../building-methods/pipes/pipe-operators/PipeFunc.md#migrating-flat-function-names)).

For each step whose `function_name` holds no dot, the command finds the `@pipe_func` function of the method's tree that the flat name registered, its own name or the one its `@pipe_func(name=...)` marker gave it, and writes its import path; then it drops the argument of every `@pipe_func(name=...)` marker, since the marker takes none. It reads the method's files as text and syntax trees: nothing is imported, Pipelex does not boot, and every comment and alignment of the files is kept. A flat name that no module of the tree registers, or that two register, is left as it is and reported for you to decide, and so is the argument of each marker registering it, the only record left of which function the step meant. A marker whose name is not a string literal, such as `@pipe_func(name=NAME)`, is left and reported too, since its name cannot be read without running the module.

**Arguments:**

- `PATH` - The method's folder, the tree holding its bundles and its Python

**Options:**

- `--dry-run` - Show what would change without writing any file

**Examples:**

```bash
# Migrate a method in place
pipelex fix function-names invoicing/

# Preview the migration
pipelex fix function-names invoicing/ --dry-run
```

**Exit codes:** `0` when every flat name was rewritten (or there was none), `1` when a flat name or a marker's argument was left unresolved, `2` when the folder cannot be listed as a method tree or a file cannot be read or written.

## Related Documentation

- [Validate Commands](validate.md) - Where suggested fixes are surfaced
- [Error Model — suggested fixes](../../under-the-hood/error-model.md#suggested_fix-structured-deterministic-fixes) - The `SuggestedFix` wire model, the fix planner, and the patch-op vocabulary
