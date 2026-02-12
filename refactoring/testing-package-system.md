# Package System — Manual Testing Guide

This guide walks through manually testing the package system (METHODS.toml, exports/visibility, `pkg` CLI) both locally and with cross-package references.

## Prerequisites

- A working Pipelex install with the virtual environment activated
- The test fixtures in `refactoring/test-package-fixtures/`
- All commands below assume you are in the **project root** (where `.pipelex/` lives)

**Important**: `pipelex validate --all` requires a full Pipelex setup (the `.pipelex/` config directory). Use `--library-dir` to point it at the fixture files while running from the project root. The `pkg list` and `pkg init` commands only need a `METHODS.toml` in the current directory, so for those you `cd` into the fixtures.

## A. Local Testing (single repo, visibility enforcement)

### 1. Verify the fixture structure

```
refactoring/test-package-fixtures/
├── METHODS.toml
├── legal/
│   └── contracts.mthds
├── scoring/
│   └── scoring.mthds
└── reporting/
    └── summary.mthds
```

### 2. Inspect the manifest with `pkg list`

```bash
cd refactoring/test-package-fixtures
pipelex pkg list
cd ../..
```

**Expected**: Three Rich tables showing:

- **Package** table — address `github.com/acme/contract-analysis`, version `1.0.0`
- **Dependencies** table — alias `shared_scoring`, address `github.com/acme/scoring-methods`, version `^2.0.0`
- **Exports** table — two rows:
  - `legal.contracts` → `extract_clause, analyze_contract`
  - `scoring` → `compute_weighted_score`

### 3. Run validate — expect visibility failure

From the project root:

```bash
pipelex validate --all --library-dir refactoring/test-package-fixtures
```

**Expected**: A `LibraryLoadingError` with a visibility violation:

```
Pipe 'scoring.internal_score_normalizer' referenced in
pipe.generate_report.steps[2].pipe (domain 'reporting') is not exported by
domain 'scoring'. Add it to [exports.scoring] pipes in METHODS.toml.
```

This is because `reporting/summary.mthds` references `scoring.internal_score_normalizer`, which is **not** listed in `[exports.scoring]`.

### 4. Fix the violation and re-validate

Edit `refactoring/test-package-fixtures/reporting/summary.mthds` — remove the offending step:

```toml
steps = [
    { pipe = "legal.contracts.extract_clause", result = "clause" },
    { pipe = "scoring.compute_weighted_score", result = "score" },
]
```

Re-run:

```bash
pipelex validate --all --library-dir refactoring/test-package-fixtures
```

**Expected**: Validation passes (no visibility errors).

After testing, restore the original step so the fixture remains useful for future tests:

```toml
steps = [
    { pipe = "legal.contracts.extract_clause", result = "clause" },
    { pipe = "scoring.compute_weighted_score", result = "score" },
    { pipe = "scoring.internal_score_normalizer", result = "normalized" },
]
```

### 5. Alternative fix — export the pipe

Instead of removing the reference, you can export the pipe. Edit `refactoring/test-package-fixtures/METHODS.toml`:

```toml
[exports.scoring]
pipes = ["compute_weighted_score", "internal_score_normalizer"]
```

Re-run `pipelex validate --all --library-dir refactoring/test-package-fixtures`. **Expected**: passes. Remember to restore the original exports afterward.

### 6. Test `pkg init` scaffolding

Copy just the `.mthds` files (no METHODS.toml) to a temp directory:

```bash
mkdir -p /tmp/pkg-init-test
cp -r refactoring/test-package-fixtures/legal /tmp/pkg-init-test/
cp -r refactoring/test-package-fixtures/scoring /tmp/pkg-init-test/
cd /tmp/pkg-init-test
pipelex pkg init
```

**Expected**: A new `METHODS.toml` is created with:

- A placeholder address derived from the directory name
- `[exports]` sections for all discovered domains and pipes
- Version `0.1.0`

Inspect it:

```bash
pipelex pkg list
```

Return to the project root when done:

```bash
cd /path/to/project
```

### 7. Test backward compatibility — no METHODS.toml

Copy fixtures without the manifest:

```bash
cp -r refactoring/test-package-fixtures /tmp/pkg-no-manifest
rm /tmp/pkg-no-manifest/METHODS.toml
pipelex validate --all --library-dir /tmp/pkg-no-manifest
```

**Expected**: Validation passes. Without a manifest, all pipes are treated as public (backward-compatible behavior).

### 8. Test `main_pipe` auto-export

In the fixture files, `legal/contracts.mthds` declares `main_pipe = "extract_clause"`. This pipe is automatically exported even if you remove it from `[exports.legal.contracts]`.

Copy the fixtures and edit the copy:

```bash
cp -r refactoring/test-package-fixtures /tmp/pkg-main-pipe-test
```

Edit `/tmp/pkg-main-pipe-test/METHODS.toml` to remove `extract_clause` from the exports:

```toml
[exports.legal.contracts]
pipes = ["analyze_contract"]
```

Also edit `/tmp/pkg-main-pipe-test/reporting/summary.mthds` to remove the blocked step (`internal_score_normalizer`), then run:

```bash
pipelex validate --all --library-dir /tmp/pkg-main-pipe-test
```

**Expected**: Passes. The reference to `legal.contracts.extract_clause` is still valid because it is the `main_pipe` of its domain.

## B. Remote Testing (cross-package, GitHub)

Cross-package references use the `->` syntax: `alias->domain.pipe_code`, where the alias is declared in `[dependencies]`.

### Current state

Cross-package reference **parsing and alias validation** are implemented in `PackageVisibilityChecker.validate_cross_package_references()` (`pipelex/core/packages/visibility.py:128`). However, this method is **not yet wired** into the `pipelex validate --all` pipeline — `check_visibility_for_blueprints()` only calls `validate_all_pipe_references()`, not `validate_cross_package_references()`. This means `->` references are currently validated only by unit tests, not at CLI level.

Full cross-package **resolution** (fetching and loading remote packages) is also not yet implemented.

### 1. Test cross-package ref parsing (unit test level)

The `->` syntax is validated by unit tests in `tests/unit/pipelex/core/packages/test_cross_package_refs.py`. Run them:

```bash
make tp TEST=TestCrossPackageRefs
```

**Expected**: All 4 tests pass:

- `test_has_cross_package_prefix` — detects `->` in ref strings
- `test_split_cross_package_ref` — splits `alias->domain.pipe` correctly
- `test_known_alias_emits_warning_not_error` — known alias produces no error (warning via log)
- `test_unknown_alias_produces_error` — unknown alias produces a `VisibilityError`

### 2. What the `->` syntax looks like in practice

In a `.mthds` file, a cross-package reference uses the alias from `[dependencies]`:

```toml
[pipe.call_remote_scoring]
type = "PipeSequence"
description = "Call a pipe from the shared_scoring remote package"
inputs = { data = "Text" }
output = "Text"
steps = [
    { pipe = "shared_scoring->scoring.compute_score", result = "remote_score" },
]
```

Where `shared_scoring` matches the dependency declared in METHODS.toml:

```toml
[dependencies]
shared_scoring = { address = "github.com/acme/scoring-methods", version = "^2.0.0" }
```

### 3. What will change with full cross-package resolution

Once cross-package validation is wired into the CLI pipeline and resolution is implemented:

- `validate_cross_package_references()` will be called alongside `validate_all_pipe_references()` during `pipelex validate --all`
- Known alias `->` references will emit warnings (then eventually resolve to actual pipes)
- Unknown alias `->` references will produce hard errors
- `pipelex` will download/cache the remote package based on the address and version constraint
- The remote package's METHODS.toml will be read to check its exports

### Creating a test GitHub repo (for future use)

When cross-package resolution is implemented, you can test it end-to-end:

1. Create a GitHub repo (e.g. `acme-scoring-methods`) containing:
   - `METHODS.toml` with `[exports.scoring]` listing the public pipes
   - `scoring/scoring.mthds` with the actual pipe definitions
2. In your consumer project, add it as a dependency:
   ```toml
   [dependencies]
   shared_scoring = { address = "github.com/yourorg/acme-scoring-methods", version = "^1.0.0" }
   ```
3. Reference it with `shared_scoring->scoring.compute_score` in a step
4. Run `pipelex validate --all`

## Fixture File Reference

| File | Domain | Exports | Private pipes |
|------|--------|---------|---------------|
| `legal/contracts.mthds` | `legal.contracts` | `extract_clause` (also main_pipe), `analyze_contract` | `internal_clause_helper` |
| `scoring/scoring.mthds` | `scoring` | `compute_weighted_score` (also main_pipe) | `internal_score_normalizer` |
| `reporting/summary.mthds` | `reporting` | (none declared) | `generate_report` |

The `reporting/summary.mthds` bundle is the key testing tool — its `generate_report` pipe references:

- `legal.contracts.extract_clause` — **valid** (exported)
- `scoring.compute_weighted_score` — **valid** (exported)
- `scoring.internal_score_normalizer` — **blocked** (not exported) — toggle this line to test pass/fail
