# Package System — Testing Guide

This guide covers testing the package system (METHODS.toml, exports/visibility, `pkg` CLI, cross-package references) using a layered strategy that maximizes coverage while minimizing external dependencies.

## Testing Strategy Overview

Cross-package references are the hardest part to test because they involve two independent packages — a **provider** (exports pipes) and a **consumer** (references them via `alias->domain.pipe`). The naive approach — creating multiple GitHub accounts — is fragile, slow, and unnecessary.

Instead, we use four testing layers, each building on the previous one:

| Layer | What it tests | I/O | Runs in CI |
|-------|--------------|-----|------------|
| **1. Unit tests** | `->` syntax parsing, alias validation, manifest models | None | Yes |
| **2. Local path deps** | Full resolution pipeline with two directories on disk | Filesystem only | Yes |
| **3. Local git repos** | VCS fetch path using `file://` protocol URLs | Local git, no network | Yes |
| **4. Manual smoke test** | Real GitHub fetch + export validation | Network (GitHub) | No — manual only |

Layers 1-3 are automated and form the test suite. Layer 4 is a one-time confidence check before shipping.

**Why not two GitHub accounts?**

- GitHub ToS discourages multiple personal accounts per person.
- Credential management in CI is painful (two sets of secrets, token rotation).
- Tests become fragile: network outages, rate limits, and GitHub API changes break them.
- Slow feedback loop — every test run hits the network.
- You don't need two *accounts*, you need two *repositories*. A single account or org can own both.
- And for automated tests, you don't need GitHub at all — local git repos and local path deps cover the logic.

## Prerequisites

- A working Pipelex install with the virtual environment activated
- The test fixtures in `tests/data/packages/` (automated tests) and optionally `refactoring/test-package-fixtures/` (manual tests)
- All commands below assume you are in the **project root** (where `.pipelex/` lives)

**Important**: `pipelex validate --all` requires a full Pipelex setup (the `.pipelex/` config directory). Use `--library-dir` to point it at fixture files while running from the project root. The `pkg list` and `pkg init` commands only need a `METHODS.toml` in the current directory, so for those you `cd` into the fixtures.

---

## Layer 1: Unit Tests (parsing, validation, models)

These tests verify the low-level building blocks with no I/O at all. They already exist from Phase 2.

### 1.1 Cross-package ref parsing

The `->` syntax is validated by unit tests in `tests/unit/pipelex/core/packages/test_cross_package_refs.py`:

```bash
make tp TEST=TestCrossPackageRefs
```

**Expected**: All 4 tests pass:

- `test_has_cross_package_prefix` — detects `->` in ref strings
- `test_split_cross_package_ref` — splits `alias->domain.pipe` correctly
- `test_known_alias_emits_warning_not_error` — known alias produces no error (warning via log)
- `test_unknown_alias_produces_error` — unknown alias produces a `VisibilityError`

### 1.2 Manifest model validation

Manifest parsing, field validation, and serialization are covered by tests in `tests/unit/pipelex/core/packages/`. Run the full package unit test suite:

```bash
make tp TEST=tests/unit/pipelex/core/packages
```

### 1.3 What the `->` syntax looks like in practice

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

---

## Layer 2: Integration Tests with Local Path Dependencies

This is where 90% of the cross-package test coverage should live. Two directories on disk, each with its own `METHODS.toml`, the consumer declaring the provider as a local path dependency. This tests the full resolution pipeline — discover manifest, read exports, validate visibility — with zero network I/O.

### 2.1 Fixture layout

The test fixtures live under `tests/data/packages/` and follow this structure:

```
tests/data/packages/
├── provider_package/
│   ├── METHODS.toml          # declares [exports.scoring]
│   └── scoring/
│       └── scoring.mthds     # defines compute_weighted_score (public) + internal_score_normalizer (private)
│
├── consumer_valid/
│   ├── METHODS.toml          # [dependencies] scoring_lib = { path = "../provider_package" }
│   └── analysis/
│       └── analysis.mthds    # uses scoring_lib->scoring.compute_weighted_score (valid)
│
├── consumer_invalid/
│   ├── METHODS.toml          # same dependency declaration
│   └── analysis/
│       └── analysis.mthds    # uses scoring_lib->scoring.internal_score_normalizer (blocked — not exported)
│
└── consumer_unknown_alias/
    ├── METHODS.toml           # no [dependencies] section
    └── analysis/
        └── analysis.mthds    # uses nonexistent_lib->scoring.compute_weighted_score (unknown alias)
```

### 2.2 What the local path dependency looks like

The consumer's `METHODS.toml` uses a `path` field instead of (or alongside) an `address`:

```toml
[package]
name = "contract-analysis"
version = "1.0.0"
description = "Analyzes contracts using external scoring"

[dependencies]
scoring_lib = { path = "../provider_package", version = "^1.0.0" }
```

The `path` field is resolved relative to the `METHODS.toml` file's location. This is the same pattern used by Cargo (`path = "..."`), Go (`replace` directive), and Poetry (`path` dependencies).

### 2.3 Test cases

These are automated tests (pytest), not manual steps:

| Test case | Consumer fixture | Expected result |
|-----------|-----------------|-----------------|
| Valid cross-package ref | `consumer_valid/` | Passes — pipe is exported by provider |
| Private pipe ref | `consumer_invalid/` | Fails — `internal_score_normalizer` not in provider's `[exports]` |
| Unknown alias | `consumer_unknown_alias/` | Fails — alias not declared in `[dependencies]` |
| Provider has no manifest | (provider without METHODS.toml) | Passes — no manifest means all public |
| Provider `main_pipe` auto-export | (consumer refs provider's main_pipe not in exports) | Passes — main_pipe is auto-exported |

### 2.4 Running the tests

```bash
make tp TEST=TestCrossPackageLocalPath
```

### 2.5 Why this layer matters

Local path dependencies test the **exact same resolution logic** that remote dependencies will use — the only difference is *how* the provider package is located on disk. Once the provider's directory is found:

1. Read its `METHODS.toml`
2. Build a `PackageVisibilityChecker` from its exports
3. Validate the consumer's `->` references against the provider's exports

Steps 1-3 are identical regardless of whether the provider came from a local path, a local git clone, or a GitHub fetch. This is why local path tests give high confidence.

---

## Layer 3: Integration Tests with Local Git Repos

This layer tests the VCS fetch path — cloning a repo, checking out a version, reading its manifest — without touching the network. It uses bare git repos on the local filesystem with `file://` protocol URLs.

### 3.1 How it works

The test setup creates temporary git repos using `git init --bare`, pushes fixture content to them, and tags releases. The consumer's dependency uses a `file://` URL instead of a `github.com/...` address:

```toml
[dependencies]
scoring_lib = { address = "file:///tmp/test-repos/scoring-methods.git", version = "^1.0.0" }
```

### 3.2 Test setup (pytest fixture)

A pytest fixture handles the lifecycle:

1. Create a temp directory
2. Initialize a bare git repo: `git init --bare /tmp/test-repos/scoring-methods.git`
3. Clone it to a working copy, add the provider package files (METHODS.toml + .mthds bundles)
4. Commit and tag: `git tag v1.0.0`
5. Push to the bare repo
6. Yield the `file://` URL to the test
7. Clean up on teardown

This mirrors exactly what happens with a real GitHub repo, but runs entirely on the local filesystem.

### 3.3 Test cases

| Test case | Setup | Expected result |
|-----------|-------|-----------------|
| Clone + resolve valid ref | Provider tagged `v1.0.0`, consumer requires `^1.0.0` | Passes — version matches, pipe is exported |
| Version mismatch | Provider tagged `v1.0.0`, consumer requires `^2.0.0` | Fails — no matching version |
| Clone + visibility violation | Provider exports only `compute_weighted_score`, consumer refs private pipe | Fails — visibility error with helpful message |
| Multiple tags | Provider has `v1.0.0` and `v1.1.0`, consumer requires `^1.0.0` | Resolves to `v1.1.0` (latest matching) |

### 3.4 Running the tests

```bash
make tp TEST=TestCrossPackageGitLocal
```

### 3.5 What this adds over Layer 2

Layer 2 tests the resolution logic assuming the provider is already on disk. Layer 3 tests the **fetch** logic:

- Can we clone from a URL?
- Can we resolve version constraints against git tags?
- Can we read the manifest from the cloned repo?
- Does caching work (second resolve doesn't re-clone)?

These are the moving parts that break when the VCS integration has bugs.

---

## Layer 4: Manual Smoke Test (GitHub)

This is a one-time manual test to confirm end-to-end behavior with real GitHub repos. It is **not** part of the automated test suite. You need a single GitHub account (or org) with two public repos.

### 4.1 Setup

1. Create a GitHub repo `yourorg/scoring-methods` containing:

   ```
   METHODS.toml
   scoring/
     scoring.mthds
   ```

   Where `METHODS.toml` declares:

   ```toml
   [package]
   name = "scoring-methods"
   version = "1.0.0"
   description = "Shared scoring methods"
   address = "github.com/yourorg/scoring-methods"

   [exports.scoring]
   pipes = ["compute_weighted_score"]
   ```

   Tag a release: `git tag v1.0.0 && git push --tags`

2. Create a GitHub repo `yourorg/contract-analysis` containing:

   ```
   METHODS.toml
   analysis/
     analysis.mthds
   ```

   Where `METHODS.toml` declares:

   ```toml
   [package]
   name = "contract-analysis"
   version = "1.0.0"
   description = "Contract analysis pipeline"
   address = "github.com/yourorg/contract-analysis"

   [dependencies]
   scoring_lib = { address = "github.com/yourorg/scoring-methods", version = "^1.0.0" }

   [exports.analysis]
   pipes = ["analyze_contract"]
   ```

   And `analysis.mthds` references the remote pipe:

   ```toml
   [pipe.analyze_contract]
   type = "PipeSequence"
   description = "Analyze a contract using remote scoring"
   inputs = { data = "Text" }
   output = "Text"
   steps = [
       { pipe = "scoring_lib->scoring.compute_weighted_score", result = "score" },
   ]
   ```

### 4.2 Test it

Clone the consumer repo and run:

```bash
pipelex validate --all --library-dir .
```

**Expected**: Passes — the scoring pipe is exported and the version matches.

### 4.3 Test a visibility violation

Update `analysis.mthds` to reference a private pipe:

```toml
steps = [
    { pipe = "scoring_lib->scoring.internal_score_normalizer", result = "score" },
]
```

Re-run validation. **Expected**: Fails with a visibility error naming the pipe and suggesting to add it to `[exports.scoring]`.

### 4.4 When to run this

Run the smoke test once after implementing the GitHub fetch path, and again before releasing. It does not need to be part of CI.

---

## A. Local Testing (single package, visibility enforcement)

These are manual tests for Phase 2 functionality (single-package visibility). They remain useful for quickly verifying the visibility model without running the full pytest suite.

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

---

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

---

## Current Implementation State

Cross-package reference **parsing and alias validation** are implemented in `PackageVisibilityChecker.validate_cross_package_references()` (`pipelex/core/packages/visibility.py:128`). However, this method is **not yet wired** into the `pipelex validate --all` pipeline — `check_visibility_for_blueprints()` only calls `validate_all_pipe_references()`, not `validate_cross_package_references()`. This means `->` references are currently validated only by unit tests, not at CLI level.

Full cross-package **resolution** (fetching and loading remote packages) is also not yet implemented. The test layers described above (2, 3, 4) serve as the specification for what Phase 3 must deliver:

- **Layer 2 defines** the local path dependency format and resolution behavior.
- **Layer 3 defines** the VCS fetch, version resolution, and caching behavior.
- **Layer 4 defines** the end-user experience with real GitHub repos.

Phase 3 implementation should make these test cases pass, in order.
