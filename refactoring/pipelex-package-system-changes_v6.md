# MTHDS Package System — Evolution from Current Pipelex Architecture

This document maps the proposed MTHDS package system back to the current Pipelex codebase, identifying what changes, what's new, and the implementation roadmap.

**Context**: MTHDS is the open standard (language, file format, packaging). Pipelex is the reference implementation (runtime, CLI, builder). This document describes the changes needed in Pipelex to implement the MTHDS standard.

**Operational detail** for the current phases lives in the latest `mthds-implementation-brief_v*.md`.

---

## 1. Summary of Changes

| Category | Nature | Description |
|----------|--------|-------------|
| File extension | **Done** | `.mthds` (renamed from `.plx` in Phase 0) |
| Terminology | **Done** | "method" terminology throughout docs and UI (renamed from "workflow" in Phase 0) |
| Hierarchical domains | **Done** | Domains support `.`-separated hierarchy (e.g., `legal.contracts`) |
| Pipe namespacing | **Done** | Pipes gain `domain_path.pipe_code` references, symmetric with concepts |
| Package manifest | **Done** | `METHODS.toml` — identity, dependencies (parsed only), exports |
| Visibility model | **Done** | Pipes are private by default when manifest exists, exported via `[exports]` |
| CLI `pipelex pkg` | **Done** | `pipelex pkg init` (scaffold manifest), `pipelex pkg list` (display manifest) |
| Lock file | **New artifact** | `methods.lock` — resolved dependency versions and checksums |
| Dependency resolver | **Done (local)** | Resolves local `path` dependencies; fetches/caches/version-resolves from VCS in Phase 4 |
| Cross-package references | **Done** | `alias->domain_path.pipe_code` and `alias->domain_path.ConceptCode` — parsing, validation, loading, runtime lookup |
| CLI `pipelex pkg add` | **Done** | Add dependency to `METHODS.toml` with address, alias, version, optional path |
| Bundle loading | **Done (local deps)** | Dependency packages loaded via local path; full package-aware resolver in Phase 4 |

---

## 2. The Standard/Implementation Split

The MTHDS standard defines:

- The `.mthds` file format (TOML-based bundle definition)
- The `METHODS.toml` manifest format
- The `methods.lock` lock file format
- Namespace resolution rules (bare, domain-qualified, package-qualified with `->`)
- The package addressing scheme
- The distribution model

Pipelex implements:

- The runtime that loads, validates, and executes `.mthds` bundles
- The CLI (`pipelex`) that exposes standard operations
- The builder that generates `.mthds` files
- The agent CLI (`pipelex-agent`) for machine-driven building

The standard docs should never reference Pipelex. The implementation docs reference both.

---

## 3. What Changes in the File Format

### 3.1 Extension Rename — COMPLETED (Phase 0)

All bundle files now use the `.mthds` extension. The TOML structure inside is unchanged.

### 3.2 Hierarchical Domains

**Current state**: Domain names are single `snake_case` identifiers (e.g., `recruitment`, `scoring`).

**New state**: Domains support `.`-separated hierarchies using `snake_case` segments.

```toml
# Current (still valid)
domain = "legal"

# New (hierarchical)
domain = "legal.contracts"
domain = "legal.contracts.shareholder"
```

The hierarchy is purely organizational — no implicit scope or inheritance between parent and child domains. `legal.contracts` does not automatically have access to concepts from `legal`.

**Impact**: Domain validation must accept dotted paths. Domain storage and lookup must handle multi-segment keys.

### 3.3 Pipe References Gain Domain Namespacing

**Current state**: Pipes are referenced by bare `snake_case` names everywhere.

```toml
# Current
steps = [
    { pipe = "extract_documents", result = "extracted_documents" },
    { pipe = "analyze_cv", result = "cv_analysis" },
]
branch_pipe_code = "process_single_cv"
outcomes = { "high" = "deep_analysis", "low" = "quick_analysis" }
```

**New state**: Pipe references support three forms — bare (local), domain-qualified, and package-qualified. With hierarchical domains, the domain path can be multi-segment.

```toml
# Within same bundle (unchanged)
steps = [
    { pipe = "extract_documents", result = "extracted_documents" },
]

# Cross-bundle, same package (single-segment domain)
steps = [
    { pipe = "scoring.compute_weighted_score", result = "score" },
]

# Cross-bundle, same package (hierarchical domain)
steps = [
    { pipe = "legal.contracts.extract_clause", result = "clause" },
]

# Cross-package
steps = [
    { pipe = "docproc->extraction.extract_text", result = "pages" },
]
```

**Parsing rule**: Split on the **last `.`** to separate the domain path from the name. Casing of the last segment disambiguates: `snake_case` = pipe code, `PascalCase` = concept code.

**All pipe reference locations affected:**

| Field | Example |
|-------|---------|
| `steps[].pipe` (PipeSequence) | `"legal.contracts.extract_clause"` |
| `parallels[].pipe` (PipeParallel) | `"docproc->extraction.extract_text"` |
| `branch_pipe_code` (PipeBatch) | `"legal.contracts.process_nda"` |
| `outcomes` values (PipeCondition) | `"scoring.deep_analysis"` |
| `default_outcome` (PipeCondition) | `"scoring.fallback"` |

**Not affected**: `main_pipe` (always local), pipe definition keys (`[pipe.my_pipe]` — always local).

### 3.4 Concept References Gain Package Qualification

**Current state**: Concepts support bare names and `domain.ConceptCode`.

```toml
# Current — both forms already work
inputs = { profile = "CandidateProfile" }
inputs = { profile = "recruitment.CandidateProfile" }
refines = "base_domain.Person"
```

**New state**: Adds package-qualified form and supports hierarchical domain paths.

```toml
# Hierarchical domain concept reference (same package)
inputs = { clause = "legal.contracts.NonCompeteClause" }

# Cross-package concept reference
inputs = { profile = "acme_hr->recruitment.CandidateProfile" }
refines = "acme_legal->legal.contracts.NonDisclosureAgreement"
```

### 3.5 The Bundle Header — Domain Now Supports Hierarchy

The top-level bundle fields remain structurally the same, but `domain` now accepts dotted paths:

```toml
domain = "legal.contracts"
description = "Contract analysis and clause extraction"
main_pipe = "extract_clause"
```

No new required fields in the `.mthds` file itself. The package relationship is established by the manifest, not by the bundle.

---

## 4. New Artifacts

### 4.1 Package Manifest: `METHODS.toml` — IMPLEMENTED (Phase 2, extended Phase 3)

Parsed and validated. Declares package identity, dependencies, and exports. Dependencies with a `path` field are resolved and loaded at runtime (Phase 3). The `path` field is resolved relative to the manifest's directory.

Exports use TOML sub-tables, one per domain. The domain path maps directly to the TOML table path — `legal.contracts` becomes `[exports.legal.contracts]`.

```toml
[package]
address = "github.com/acme/legal-tools"
version = "0.3.0"
description = "Legal document analysis and contract review methods."
mthds_version = ">=0.2.0"

[dependencies]
docproc = { address = "github.com/mthds/document-processing", version = "1.0.0" }
scoring_lib = { address = "github.com/mthds/scoring-lib", version = "0.5.0" }

[exports.legal]
pipes = ["classify_document"]

[exports.legal.contracts]
pipes = ["extract_clause", "analyze_nda", "compare_contracts"]

[exports.scoring]
pipes = ["compute_weighted_score"]
```

**Implementation note**: The `[dependencies]` format uses the alias as the TOML key and the address as an inline field — this is more natural for `->` syntax since the alias is the lookup key when resolving cross-package references. Dependency versions support Poetry/uv-style range syntax (`^1.0.0`, `~1.0.0`, `>=1.0.0, <2.0.0`, wildcards) — validated at parse time. Dependencies with a `path` field are resolved and loaded at runtime (Phase 3). Version resolution against VCS tags is deferred to Phase 4. The `description` field is required and must be non-empty.

**Impact**: New parser (`manifest_parser.py`), new model class (`MthdsPackageManifest`), new validation rules, new discovery function, new visibility checker. See `pipelex/core/packages/`.

### 4.2 Lock File: `methods.lock`

Auto-generated by the dependency resolver. Committed to version control.

```toml
["github.com/mthds/document-processing"]
version = "1.2.3"
hash = "sha256:a1b2c3d4..."
source = "https://github.com/mthds/document-processing"

["github.com/mthds/scoring-lib"]
version = "0.5.1"
hash = "sha256:e5f6g7h8..."
source = "https://github.com/mthds/scoring-lib"
```

**Impact**: New generation/verification code, new CLI commands.

### 4.3 Package Cache Directory

`~/.mthds/packages/` (global) or `.mthds/packages/` (project-local). Stores fetched package contents, organized by address and version.

---

## 5. Impact on Existing Pipelex Subsystems

### 5.1 Pipe Code Validation (`pipelex/core/pipes/`)

**Current**: `is_pipe_code_valid()` accepts only `snake_case` identifiers.

**Change**: Must distinguish between pipe *definitions* (always bare `snake_case`) and pipe *references* (three forms: bare, `domain_path.pipe_code`, `alias->domain_path.pipe_code`). **Done in Phase 1**: implemented as the unified `QualifiedRef` model in `pipelex/core/qualified_ref.py`, handling both concept and pipe references with the "split on last dot" rule. **Extended in Phase 2**: `has_cross_package_prefix()` and `split_cross_package_ref()` static methods added for `->` syntax detection.

### 5.2 Bundle Blueprint (`pipelex/core/bundles/`)

**Current**: Validates pipe keys and concept references in isolation.

**Changes**:
- `validate_pipe_keys()`: unchanged (definitions are still bare names)
- `validate_local_concept_references()`: **Done in Phase 3** — explicitly skips `->` refs with `QualifiedRef.has_cross_package_prefix()` check (validated at package level instead)
- `validate_local_pipe_references()`: **Done in Phase 3** — same explicit skip for `->` refs
- `collect_pipe_references()`: **Done in Phase 2** — made public (was `_collect_pipe_references`) so the `PackageVisibilityChecker` can call it

### 5.3 Interpreter (`pipelex/core/interpreter/`)

**Current**: Loads `.mthds` files.

**Change**: No structural change to the interpreter itself, but it needs to be called within the context of a package-aware loader that reads the manifest, resolves dependencies, and loads bundles in order.

### 5.4 Domain Validation (`pipelex/core/domains/`)

**Current**: Validates domain code syntax (single `snake_case` segment).

**Change**: Must accept `.`-separated hierarchical domain paths where each segment is `snake_case`. Must also handle package-qualified domain references (`alias->domain_path`).

### 5.5 Builder (`pipelex/builder/`)

**Current**: Generates `.mthds` bundles.

**Changes — Done in Phase 2**:
- `maybe_generate_manifest_for_output()` in `builder_loop.py` generates `METHODS.toml` alongside `.mthds` files when the output directory contains multiple domains
- Hooked into `pipe_cmd.py` (CLI build) and `build_core.py` (agent CLI build)

**Still pending (Phase 4+)**:
- When building a method that depends on external packages, the builder needs awareness of available packages and their exported pipes/concepts
- Pipe signature design needs to account for cross-package pipe references

### 5.6 CLI (`pipelex/cli/`)

**New command group — Done in Phase 2**: `pipelex pkg` with `init` and `list` subcommands.

| Command | Status | Does |
|---------|--------|------|
| `pipelex pkg init` | **Done** | Create a `METHODS.toml` in the current directory |
| `pipelex pkg list` | **Done** | Show package info, dependencies, and exported pipes from the manifest |
| `pipelex pkg add <address>` | **Done** | Add a dependency to the manifest (address, alias, version, optional path) |
| `pipelex pkg install` | Phase 4 | Fetch and cache all dependencies from lock file |
| `pipelex pkg update` | Phase 4 | Update dependencies to latest compatible versions |
| `pipelex pkg lock` | Phase 4 | Regenerate the lock file |
| `pipelex pkg publish` | Phase 5 | Validate and prepare a package for distribution |

**Existing commands impacted**:
- `pipelex validate`: **Done (Phase 3)** — resolves local path dependencies and validates cross-package references during library loading. Unresolved cross-package refs (missing deps) are handled gracefully.
- `pipelex run`: **Done (Phase 3)** — dependency packages are loaded into the runtime via `_load_dependency_packages()` in `library_manager.py`. Cross-package pipes and concepts are accessible at runtime.
- `pipelex-agent build`: Phase 4+ — should be package-aware for cross-package pipe references

### 5.7 Pipe Blueprints (All Pipe Types)

Every pipe type that holds references to other pipes needs its validation/resolution updated:

| Pipe Type | Fields Holding Pipe References |
|-----------|-------------------------------|
| `PipeSequenceBlueprint` | `steps[].pipe` |
| `PipeParallelBlueprint` | `parallels[].pipe` |
| `PipeBatchBlueprint` | `branch_pipe_code` |
| `PipeConditionBlueprint` | `outcomes` values, `default_outcome` |

Each of these must accept and parse the three-scope pipe reference format. Look in `pipelex/pipe_controllers/`.

### 5.8 Library Manager (`pipelex/libraries/`) — Phase 2 + Phase 3

**Phase 2**: `_check_package_visibility()` added to `library_manager.py`. After parsing all blueprints from `.mthds` files, it:
1. Finds the nearest `METHODS.toml` manifest via walk-up discovery
2. If found, runs the `PackageVisibilityChecker` against all blueprints (including cross-package reference validation)
3. Raises `LibraryLoadingError` if cross-domain pipe references violate visibility

**Phase 3**: `_load_dependency_packages()` added. The loading flow is now:
1. Parse main package blueprints from `.mthds` files
2. Find manifest via `find_package_manifest()`
3. If manifest has dependencies with `path`: resolve local dependencies, for each resolved dependency:
   - Parse dependency blueprints
   - Load dependency concepts into library (aliased keys `alias->concept_ref` for cross-package lookup + native keys for internal resolution, skip on conflict)
   - Load only exported pipes with aliased keys (`alias->pipe_code`)
4. Check visibility (pipe visibility + cross-package reference validation)
5. `load_from_blueprints()` for main package

Also added `_find_package_root()` to walk up from `.mthds` files to find the directory containing `METHODS.toml`.

**Validation safety** (Phase 3): `library.py` skips full validation for pipe controllers with unresolved cross-package dependencies. `pipe_sequence.py` handles unresolved `->` refs gracefully in `needed_inputs()` and `validate_output_with_library()`. `dry_run.py` catches `PipeNotFoundError` for graceful skip during dry-run.

---

## 6. Implementation Roadmap

Each phase gets its own implementation brief with decisions, grammar, acceptance criteria, and codebase pointers. See the latest `mthds-implementation-brief_v*.md` for the current phases.

| Phase | Goal | Depends on |
|-------|------|-----------|
| **0** | ~~Extension rename + terminology update~~ | **COMPLETED** |
| **1** | ~~Hierarchical domains + pipe namespacing: `domain_path.pipe_code` references, split-on-last-dot parsing for concepts and pipes~~ | **COMPLETED** |
| **2** | ~~Package manifest (`METHODS.toml`) + exports / visibility model~~ | **COMPLETED** |
| **3** | ~~Cross-package references (`alias->domain_path.name`) + local dependency resolution~~ | **COMPLETED** |
| **4** | Remote dependency resolution: VCS clone from addresses, version tag resolution (minimum version selection), lock file (`methods.lock`), package cache (`~/.mthds/packages/`), transitive dependency resolution, per-package Library isolation, cross-package concept refinement validation, CLI `pkg install`/`update`/`lock` | Phase 3 |
| **5** | Registry index service (crawl, parse, index), type-aware search ("I have X, I need Y"), `pkg publish` CLI, Know-How Graph browsing + auto-composition, multi-tier deployment (Local / Project / Org / Community) | Phase 4 |

---

## 7. Migration Guide for Existing Bundles

### What Stays the Same

- Bundle file format is still TOML
- `domain`, `description`, `main_pipe` fields unchanged
- `[concept]` and `[pipe]` sections unchanged
- Bare pipe references (`"extract_documents"`) still work within a bundle
- Concept `domain.ConceptCode` references unchanged
- Native concepts (`Text`, `Image`, etc.) unchanged

### What Changes

- ~~File extension is now `.mthds`~~ (done in Phase 0)
- ~~Terminology is now "method"~~ (done in Phase 0)
- Domains can now be hierarchical: `legal.contracts.shareholder` (optional, for organization)
- Pipe references can now be `domain_path.pipe_code` (optional, for cross-bundle clarity)
- Packages with a `METHODS.toml` get dependency management and export controls
- Cross-package references use `alias->domain_path.name` syntax

### Migration Steps for an Existing Project

1. **To adopt packages**: run `pipelex pkg init` in your project directory. This creates a `METHODS.toml` with your bundles auto-discovered.
2. **To use cross-bundle pipes**: change bare pipe references to `domain_path.pipe_code` where you reference pipes from a different bundle in the same project.
3. **To depend on external packages**: add `[dependencies]` to your `METHODS.toml`, use `alias->domain_path.name` in your `.mthds` files.

### Breaking Changes

| Change | Impact | Migration |
|--------|--------|-----------|
| `.mthds` extension | Done (Phase 0) | — |
| Pipe reference parser accepts `.` and `->` | Low — new syntax, old syntax still works | None needed |
| `main_pipe` auto-exported | Low — only affects packages with manifest | Intentional; remove from `[exports]` if you want to override |
| Pipes private by default with manifest | Medium — only affects packages with `METHODS.toml` | Run `pipelex pkg init` to auto-export all pipes, then trim |

---

*This document tracks the delta between current Pipelex and the MTHDS standard implementation. It will be updated as phases are implemented.*
