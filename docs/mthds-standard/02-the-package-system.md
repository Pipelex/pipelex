# The Package System

<!-- Source document for the MTHDS docs website.
     Each "## Page:" section becomes an individual MkDocs page.

     Tone: Teaching. Clear, progressive. Start simple, build complexity.
     Every concept grounded in a concrete METHODS.toml or .mthds example first, explanation second.
     Cross-references use [text](link) format pointing to the spec and other pages.
-->

## Page: Package Structure

A **package** is the distribution unit of MTHDS. It is a directory that contains a manifest (`METHODS.toml`) and one or more bundles (`.mthds` files).

### A Minimal Package

```
my-tool/
├── METHODS.toml
└── main.mthds
```

This is the smallest distributable package: one manifest, one bundle. The manifest gives the package an identity — an address, a version, a description — turning a standalone bundle into something that other packages can depend on.

### A Full Package

```
legal-tools/
├── METHODS.toml
├── methods.lock
├── general_legal.mthds
├── contract_analysis.mthds
├── shareholder_agreements.mthds
├── scoring.mthds
├── README.md
└── LICENSE
```

This package has multiple bundles, each declaring its own domain (`legal`, `legal.contracts`, `legal.contracts.shareholder`, `scoring`). The `methods.lock` file records exact dependency versions for reproducible builds.

### Directory Layout Rules

- `METHODS.toml` must be at the directory root.
- `methods.lock` must be alongside `METHODS.toml` at the root.
- `.mthds` files can be at the root or in subdirectories. A compliant runtime discovers all `.mthds` files recursively.
- A single directory should contain one package.

### Standalone Bundles (No Package)

A `.mthds` file works without a package manifest. When used standalone:

- All pipes are treated as public (no visibility restrictions).
- No dependencies are available beyond [native concepts](01-the-language.md#native-concepts).
- The bundle is not distributable (no package address).

This preserves the "single file = working method" experience for learning, prototyping, and simple projects. When you need distribution, add a `METHODS.toml` — the rest of this section shows how.

### Progressive Enhancement

The package system follows a progressive enhancement principle:

1. **Single file** — a `.mthds` bundle works on its own. No configuration, no manifest.
2. **Package** — add a `METHODS.toml` to get exports, visibility, and a globally unique identity.
3. **Dependencies** — add `[dependencies]` to compose with other packages.
4. **Ecosystem** — publish, search, and discover through the Know-How Graph.

Each layer adds capability without breaking the previous one.

### Manifest Discovery

When loading a `.mthds` bundle, a compliant runtime discovers the manifest by walking up the directory tree:

1. Check the bundle's directory for `METHODS.toml`.
2. If not found, move to the parent directory.
3. Stop when `METHODS.toml` is found, a `.git` directory is encountered, or the filesystem root is reached.
4. If no manifest is found, the bundle is treated as a standalone bundle.

### See Also

- [Specification: Package Directory Structure](03-specification.md#package-directory-structure) — normative reference for layout rules.
- [The Manifest](#page-the-manifest) — what goes inside `METHODS.toml`.

---

## Page: The Manifest

`METHODS.toml` is the package manifest — the identity card and dependency declaration for a package. It is a TOML file at the root of the package directory.

### A First Look

```toml
[package]
address       = "github.com/acme/legal-tools"
version       = "0.3.0"
description   = "Legal document analysis and contract review methods."
authors       = ["ACME Legal Tech <legal@acme.com>"]
license       = "MIT"
mthds_version = ">=1.0.0"

[dependencies]
docproc     = { address = "github.com/mthds/document-processing", version = "^1.0.0" }
scoring_lib = { address = "github.com/mthds/scoring-lib", version = "^0.5.0" }

[exports.legal]
pipes = ["classify_document"]

[exports.legal.contracts]
pipes = ["extract_clause", "analyze_nda", "compare_contracts"]

[exports.scoring]
pipes = ["compute_weighted_score"]
```

This manifest declares a package at `github.com/acme/legal-tools`, version `0.3.0`. It depends on two other packages and exports specific pipes from three domains.

### The `[package]` Section

The `[package]` section defines the package's identity:

| Field | Required | Description |
|-------|----------|-------------|
| `address` | Yes | Globally unique identifier. Must follow the hostname/path pattern (e.g., `github.com/org/repo`). |
| `version` | Yes | [Semantic version](https://semver.org/) (`MAJOR.MINOR.PATCH`, with optional pre-release and build metadata). |
| `description` | Yes | Human-readable summary of the package's purpose. Must not be empty. |
| `authors` | No | List of author identifiers (e.g., `"Name <email>"`). Default: empty list. |
| `license` | No | [SPDX license identifier](https://spdx.org/licenses/) (e.g., `"MIT"`, `"Apache-2.0"`). |
| `mthds_version` | No | MTHDS standard version constraint. The current standard version is `1.0.0`. |

### Package Addresses

The address is the globally unique identifier for a package. It doubles as the fetch location for distribution (see [Distribution](#page-distribution)).

Addresses follow a hostname/path pattern:

```
github.com/acme/legal-tools
github.com/mthds/document-processing
gitlab.com/company/internal-methods
```

The address must start with a hostname (containing at least one dot), followed by a `/`, followed by one or more path segments.

Invalid addresses:

```
legal-tools               # No hostname
acme/legal-tools          # No dot in hostname
```

### Version Format

The `version` field must conform to [Semantic Versioning 2.0.0](https://semver.org/):

```
MAJOR.MINOR.PATCH[-pre-release][+build-metadata]
```

Examples: `1.0.0`, `0.3.0`, `2.1.3-beta.1`, `1.0.0-rc.1+build.42`

### The `[dependencies]` Section

Dependencies are covered in detail on the [Dependencies](#page-dependencies) page.

### The `[exports]` Section

Exports are covered in detail on the [Exports & Visibility](#page-exports--visibility) page.

### See Also

- [Specification: METHODS.toml Manifest Format](03-specification.md#page-methodstoml-manifest-format) — normative reference for all fields and validation rules.
- [Dependencies](#page-dependencies) — how to declare and manage dependencies.
- [Exports & Visibility](#page-exports--visibility) — how to control which pipes are public.

---

## Page: Exports & Visibility

When a bundle is part of a package, not every pipe needs to be visible to consumers. The `[exports]` section of `METHODS.toml` controls which pipes are part of the public API.

### Default Visibility Rules

Three rules govern visibility:

- **Concepts are always public.** Concepts are vocabulary — they are always accessible from outside the package.
- **Pipes are private by default.** A pipe not listed in `[exports]` is an implementation detail, invisible to consumers.
- **`main_pipe` is auto-exported.** If a bundle declares a `main_pipe` in its header, that pipe is automatically part of the public API, regardless of whether it appears in `[exports]`.

### Declaring Exports

The `[exports]` section uses nested TOML tables that mirror the domain hierarchy. The domain path maps directly to the TOML table path:

```toml
[exports.legal]
pipes = ["classify_document"]

[exports.legal.contracts]
pipes = ["extract_clause", "analyze_nda", "compare_contracts"]

[exports.scoring]
pipes = ["compute_weighted_score"]
```

Each table contains a `pipes` list — the pipe codes that are public from that domain. A domain can have both a `pipes` list and sub-domain tables (e.g., `[exports.legal]` with `pipes` and `[exports.legal.contracts]`).

### How Visibility Works in Practice

Consider a package with two domains and this manifest:

```toml
[exports.scoring]
pipes = ["compute_weighted_score"]
```

**Bundles in the `scoring` domain** can reference any pipe within `scoring` freely — same-domain references are always allowed.

**Bundles in other domains** (say, `analysis`) can reference `scoring.compute_weighted_score` because it is exported. They cannot reference `scoring.internal_helper` because it is not in the exports list.

**External packages** that depend on this package follow the same rule: only exported pipes (and `main_pipe` pipes) are accessible via [cross-package references](#page-cross-package-references).

### Intra-Package Visibility Summary

| Reference type | Allowed? |
|---------------|----------|
| Bare references (same bundle or same domain) | Always |
| Cross-domain references to exported pipes | Yes |
| Cross-domain references to `main_pipe` pipes | Yes |
| Cross-domain references to non-exported pipes | No — visibility error |

### Standalone Bundles

When no manifest is present (standalone bundle), all pipes are treated as public. Visibility restrictions only apply when a `METHODS.toml` exists.

### Reserved Domains in Exports

Domain paths in `[exports]` must not start with a reserved domain segment (`native`, `mthds`, `pipelex`). A manifest with `[exports.native]` or `[exports.pipelex.utils]` is invalid.

### See Also

- [Specification: The `[exports]` Section](03-specification.md#the-exports-section) — normative reference.
- [Namespace Resolution](01-the-language.md#page-namespace-resolution) — how visibility interacts with reference resolution.

---

## Page: Dependencies

Dependencies allow a package to build on other packages. Each dependency is declared in the `[dependencies]` section of `METHODS.toml` with an alias, an address, and a version constraint.

### Declaring Dependencies

```toml
[dependencies]
docproc     = { address = "github.com/mthds/document-processing", version = "^1.0.0" }
scoring_lib = { address = "github.com/mthds/scoring-lib", version = "^0.5.0" }
```

Each key (`docproc`, `scoring_lib`) is the **alias** — a short `snake_case` name used in [cross-package references](#page-cross-package-references) (`alias->domain.name`).

### Dependency Fields

| Field | Required | Description |
|-------|----------|-------------|
| `address` | Yes | The dependency's package address (hostname/path pattern). |
| `version` | Yes | Version constraint (see below). |
| `path` | No | Local filesystem path, for development-time workflows. |

### Aliases

The alias is the TOML key for each dependency entry. It must be `snake_case` (matching `[a-z][a-z0-9_]*`), and all aliases within a single manifest must be unique.

Aliases appear in cross-package references:

```toml
steps = [
    { pipe = "docproc->extraction.extract_text", result = "pages" },
    { pipe = "scoring_lib->scoring.compute_weighted_score", result = "score" },
]
```

Choose aliases that are short, meaningful, and easy to read in references.

### Version Constraints

Version constraints specify which versions of a dependency are acceptable:

| Form | Syntax | Example | Meaning |
|------|--------|---------|---------|
| Exact | `MAJOR.MINOR.PATCH` | `1.0.0` | Exactly this version. |
| Caret | `^MAJOR.MINOR.PATCH` | `^1.0.0` | Compatible release (same major version). |
| Tilde | `~MAJOR.MINOR.PATCH` | `~1.0.0` | Approximately compatible (same major.minor). |
| Greater-or-equal | `>=MAJOR.MINOR.PATCH` | `>=1.0.0` | This version or newer. |
| Less-than | `<MAJOR.MINOR.PATCH` | `<2.0.0` | Older than this version. |
| Compound | constraint `, ` constraint | `>=1.0.0, <2.0.0` | Both constraints must be satisfied. |
| Wildcard | `*`, `MAJOR.*` | `1.*` | Any version matching the prefix. |

Additional operators `>`, `<=`, `==`, and `!=` are also supported. Partial versions are allowed: `1.0` is equivalent to `1.0.*`.

### Local Path Dependencies

For development-time workflows where packages are co-located on disk, add a `path` field:

```toml
[dependencies]
scoring = { address = "github.com/mthds/scoring-lib", version = "^0.5.0", path = "../scoring-lib" }
```

When `path` is set, the dependency is resolved from the local filesystem instead of being fetched via VCS. The path is resolved relative to the directory containing `METHODS.toml`.

This is similar to Cargo's `path` dependencies or Go's `replace` directives.

**Important behaviors of local path dependencies:**

- They are NOT resolved transitively — only the root package's local paths are honored.
- They are excluded from the [lock file](#page-the-lock-file).
- When publishing, the `path` field is informational — consumers fetch via the `address`.

### See Also

- [Specification: The `[dependencies]` Section](03-specification.md#the-dependencies-section) — normative reference for all fields.
- [Specification: Version Constraint Syntax](03-specification.md#version-constraint-syntax) — full syntax reference.
- [Version Resolution](#page-version-resolution) — how dependency versions are selected.
- [Cross-Package References](#page-cross-package-references) — how aliases are used in `.mthds` files.

---

## Page: Cross-Package References

When your bundle needs a pipe or concept from another package, you use a **cross-package reference** — the `->` syntax that reaches into a dependency.

### The `->` Syntax

```toml
steps = [
    { pipe = "scoring_lib->scoring.compute_weighted_score", result = "score" },
]
```

This reference reads as: "from the package aliased as `scoring_lib`, get the pipe `compute_weighted_score` in the `scoring` domain."

The `->` separator was chosen for readability. It reads as natural language — "from scoring_lib, get..." — and is visually distinct from the `.` used for domain paths.

### Anatomy of a Cross-Package Reference

```
scoring_lib -> scoring.compute_weighted_score
  alias     ↑     domain   pipe code
         separator
```

1. **Alias** — the `snake_case` key from `[dependencies]` in `METHODS.toml`.
2. **`->`** — the cross-package separator.
3. **Domain-qualified name** — parsed by splitting on the last `.`: domain path `scoring`, pipe code `compute_weighted_score`.

### Referencing Pipes

Cross-package pipe references appear in all the same locations as domain-qualified pipe references:

- `steps[].pipe` in PipeSequence
- `branches[].pipe` in PipeParallel
- `outcomes` values in PipeCondition
- `default_outcome` in PipeCondition
- `branch_pipe_code` in PipeBatch

```toml
[pipe.full_analysis]
type        = "PipeSequence"
description = "Run external scoring and local summary"
inputs      = { item = "Text" }
output      = "Text"
steps = [
    { pipe = "scoring_lib->scoring.compute_weighted_score", result = "score" },
    { pipe = "summarize_score", result = "summary" },
]
```

**Visibility constraint:** The referenced pipe must be exported by the dependency package — listed in its `[exports]` section or declared as `main_pipe` in one of its bundles.

### Referencing Concepts

Cross-package concept references work the same way, appearing in `inputs`, `output`, `refines`, `concept_ref`, `item_concept_ref`, and `combined_output`:

```toml
[concept.DetailedScore]
description = "An extended score with additional analysis"
refines     = "scoring_lib->scoring.ScoreResult"
```

**Concepts are always public.** No visibility check is needed for cross-package concept references.

### A Complete Example

**Setup:** Package A depends on Package B with alias `scoring_lib`.

Package B's manifest:

```toml
[package]
address     = "github.com/mthds/scoring-lib"
version     = "0.5.0"
description = "Scoring utilities"

[exports.scoring]
pipes = ["compute_weighted_score"]
```

Package B's bundle (`scoring.mthds`):

```toml
domain    = "scoring"
main_pipe = "compute_weighted_score"

[concept.ScoreResult]
description = "A weighted score result"

[pipe.compute_weighted_score]
type        = "PipeLLM"
description = "Compute a weighted score"
inputs      = { item = "Text" }
output      = "ScoreResult"
prompt      = "Compute a weighted score for: $item"

[pipe.internal_helper]
type        = "PipeLLM"
description = "Internal helper (not exported)"
inputs      = { data = "Text" }
output      = "Text"
prompt      = "Process: $data"
```

Package A's bundle (`analysis.mthds`):

```toml
domain = "analysis"

[pipe.analyze_item]
type        = "PipeSequence"
description = "Analyze using scoring dependency"
inputs      = { item = "Text" }
output      = "Text"
steps = [
    { pipe = "scoring_lib->scoring.compute_weighted_score", result = "score" },
    { pipe = "summarize", result = "summary" },
]
```

**What works:**

- `scoring_lib->scoring.compute_weighted_score` resolves because `compute_weighted_score` is exported.
- `scoring_lib->scoring.ScoreResult` (concept reference) resolves because concepts are always public.

**What fails:**

- `scoring_lib->scoring.internal_helper` — visibility error: `internal_helper` is not in `[exports.scoring]` and is not `main_pipe`.

### See Also

- [Specification: Namespace Resolution Rules](03-specification.md#page-namespace-resolution-rules) — formal resolution algorithm.
- [Namespace Resolution](01-the-language.md#page-namespace-resolution) — the three tiers of reference resolution.
- [Exports & Visibility](#page-exports--visibility) — how exports control what is accessible.

---

## Page: The Lock File

The `methods.lock` file records the exact resolved versions and integrity hashes for all remote dependencies. It enables reproducible builds — every developer and CI system gets the same dependency versions.

### What It Looks Like

```toml
["github.com/mthds/document-processing"]
version = "1.2.3"
hash    = "sha256:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
source  = "https://github.com/mthds/document-processing"

["github.com/mthds/scoring-lib"]
version = "0.5.1"
hash    = "sha256:e5f6a7b8c9d0e5f6a7b8c9d0e5f6a7b8c9d0e5f6a7b8c9d0e5f6a7b8c9d0e5f6"
source  = "https://github.com/mthds/scoring-lib"
```

Each entry records a package address, the exact resolved version, a SHA-256 integrity hash, and the HTTPS source URL.

### File Location

The lock file must be named `methods.lock` and placed at the package root, alongside `METHODS.toml`. It should be committed to version control.

### Locked Package Fields

| Field | Description |
|-------|-------------|
| `version` | The exact resolved version (valid semver). |
| `hash` | SHA-256 integrity hash of the package contents (`sha256:` followed by 64 hex characters). |
| `source` | The HTTPS URL from which the package was fetched. |

### Which Packages Are Locked

- **Remote dependencies** (those without a `path` field) are locked, including all transitive remote dependencies.
- **Local path dependencies** are NOT locked. They are resolved from the filesystem at load time and are expected to change during development.

### How the Hash Is Computed

The integrity hash is a deterministic SHA-256 hash of the package directory:

1. Collect all regular files recursively under the package directory.
2. Exclude any path containing `.git` in its components.
3. Sort files by their POSIX-normalized relative path (for cross-platform determinism).
4. For each file in sorted order, feed into the hasher:
    - The relative path string, encoded as UTF-8.
    - The raw file bytes.
5. Format as `sha256:` followed by the 64-character lowercase hex digest.

### When the Lock File Updates

The lock file is regenerated when:

- `mthds pkg lock` is run — resolves all dependencies and writes the lock file.
- `mthds pkg update` is run — re-resolves to latest compatible versions and rewrites the lock file.
- `mthds pkg add` is run — adds a new dependency and may trigger re-resolution.

### Verification

When installing from a lock file (`mthds pkg install`), the runtime:

1. Locates the cached package directory for each entry.
2. Recomputes the SHA-256 hash using the algorithm above.
3. Compares the computed hash with the lock file's `hash` field.
4. Rejects the installation if any hash does not match.

### Deterministic Output

Lock file entries are sorted by package address (lexicographic ascending) to produce clean version control diffs.

### See Also

- [Specification: methods.lock Format](03-specification.md#page-methodslock-format) — normative reference.
- [Distribution](#page-distribution) — how packages are fetched and cached.
- [Version Resolution](#page-version-resolution) — how versions are selected.

---

## Page: Distribution

MTHDS packages are distributed using a federated model: decentralized storage with centralized discovery.

### Storage: Git Repositories

Packages live in Git repositories. The repository IS the package — no upload step, no proprietary hosting. Authors retain full control.

A repository can contain one package (at the root) or multiple packages (in subdirectories with distinct addresses).

### Addressing and Fetching

Package addresses map directly to Git clone URLs:

1. Prepend `https://`.
2. Append `.git` (if not already present).

```
github.com/acme/legal-tools → https://github.com/acme/legal-tools.git
```

The resolution chain when fetching a dependency:

1. **Local path** — if the dependency has a `path` field in `METHODS.toml`, resolve from the local filesystem.
2. **Local cache** — check `~/.mthds/packages/{address}/{version}/` for a cached copy.
3. **VCS fetch** — clone the repository at the resolved version tag using `git clone --depth 1 --branch {tag}`.

### Version Tags

Version tags in remote repositories may use a `v` prefix (e.g., `v1.0.0`). The prefix is stripped during version parsing. Both `v1.0.0` and `1.0.0` are recognized.

Tags are listed using `git ls-remote --tags`, and only those that parse as valid semantic versions are considered.

### Package Cache

Fetched packages are cached locally to avoid repeated clones:

```
~/.mthds/packages/{address}/{version}/
```

For example:

```
~/.mthds/packages/github.com/acme/legal-tools/1.0.0/
```

The `.git` directory is removed from cached copies to save space. Cache writes use a staging directory with atomic rename for safety.

### Discovery: Registry Indexes

One or more registry services index packages without owning them. A registry provides:

- **Search** — by domain, by concept, by pipe signature, by description.
- **Type-compatible search** — "find pipes that accept `Document` and produce something refining `Text`" (unique to MTHDS).
- **Metadata** — versions, descriptions, licenses, dependency graphs.
- **Concept/pipe browsing** — navigate the refinement hierarchy, explore pipe signatures.

Registries build their index by crawling known package addresses, parsing `METHODS.toml` for metadata, and parsing `.mthds` files for concept definitions and pipe signatures. No data is duplicated — everything is derived from the source files.

### Multi-Tier Deployment

MTHDS supports multiple deployment tiers, from local to community-wide:

| Tier | Scope | Typical use |
|------|-------|-------------|
| **Local** | Single `.mthds` file, no manifest | Learning, prototyping, one-off methods |
| **Project** | Package in a project repo | Team methods, versioned with the codebase |
| **Organization** | Internal registry/proxy | Company-wide approved methods, governance |
| **Community** | Public Git repos + public registries | Open-source Know-How Graph |

### See Also

- [Specification: Fetching Remote Dependencies](03-specification.md#fetching-remote-dependencies) — normative reference for the fetch algorithm.
- [Specification: Cache Layout](03-specification.md#cache-layout) — normative reference for cache paths.
- [The Lock File](#page-the-lock-file) — how fetched versions are pinned.
- [The Know-How Graph](#page-the-know-how-graph) — typed discovery across packages.

---

## Page: Version Resolution

When multiple packages depend on different versions of the same dependency, MTHDS needs a strategy to pick a single version. MTHDS uses **Minimum Version Selection** (MVS), the same approach used by Go modules.

### How MVS Works

Given a set of version constraints for a package, MVS:

1. Collects all version constraints from all dependents (direct and transitive).
2. Lists all available versions from VCS tags.
3. Sorts versions in ascending order.
4. Selects the **minimum** version that satisfies **all** constraints simultaneously.

If no version satisfies all constraints, the resolution fails with an error.

### An Example

Package A requires `>=1.0.0` of Library X. Package B requires `>=1.2.0` of Library X. Available versions of Library X: `1.0.0`, `1.1.0`, `1.2.0`, `1.3.0`, `2.0.0`.

MVS selects `1.2.0` — the minimum version that satisfies both `>=1.0.0` and `>=1.2.0`.

A maximum-version resolver would select `2.0.0`. MVS deliberately avoids this: you get the version you asked for, not the latest one.

### Why MVS?

- **Deterministic** — the same set of constraints always produces the same result, regardless of when you run the resolver.
- **Reproducible** — no dependency on a "latest" query or timestamp. The result depends only on the constraints and the available tags.
- **Simple** — no backtracking solver needed. Sort and pick the first match.
- **Conservative** — you get the minimum version that works, reducing the risk of pulling in untested changes.

### Transitive Dependencies

Dependencies are resolved transitively with these rules:

- **Remote dependencies** are resolved recursively. If Package A depends on Package B, and Package B depends on Package C, then Package C is also resolved.
- **Local path dependencies** are resolved at the root level only. They are NOT resolved transitively — only the root package's local paths are honored.
- **Cycle detection** — if a dependency is encountered while it is already being resolved, the resolver reports a cycle error.
- **Diamond dependencies** — when the same package address is required by multiple dependents with different version constraints, MVS selects the minimum version satisfying all constraints simultaneously.

### Diamond Dependencies

Diamond dependencies occur when two or more packages depend on the same third package:

```
Your Package
├── Package A (requires Library X ^1.0.0)
└── Package B (requires Library X ^1.2.0)
```

MVS handles this naturally: it collects both constraints (`^1.0.0` and `^1.2.0`), lists available versions, and picks the minimum version satisfying both. If constraints are contradictory (e.g., `^1.0.0` and `^2.0.0`), the resolver reports an error.

### See Also

- [Specification: Version Resolution Strategy](03-specification.md#version-resolution-strategy) — normative reference.
- [Specification: Transitive Dependency Resolution](03-specification.md#transitive-dependency-resolution) — normative reference for transitive resolution rules.
- [Dependencies](#page-dependencies) — how to declare version constraints.
- [The Lock File](#page-the-lock-file) — how resolved versions are recorded.

---

## Page: The Know-How Graph

The package system provides the infrastructure for something unique to MTHDS: the **Know-How Graph** — a typed, searchable network of AI methods that spans packages.

### Pipes as Typed Nodes

Every exported pipe has a typed signature — the concepts it accepts and the concept it produces:

```
extract_clause:          (ContractDocument) → NonCompeteClause
classify_document:       (Document)         → ClassifiedDocument
compute_weighted_score:  (Text)             → ScoreResult
```

These signatures, combined with the concept refinement hierarchy, form a directed graph:

- **Nodes** are pipe signatures (typed transformations).
- **Edges** are data flow connections — the output concept of one pipe type-matches the input concept of another.
- **Refinement edges** connect concept hierarchies (e.g., `NonCompeteClause` refines `ContractClause` refines `Text`).

### Type-Compatible Discovery

The type system enables queries that text-based discovery cannot support:

| Query | Example |
|-------|---------|
| "I have X, I need Y" | "I have a `Document`, I need a `NonCompeteClause`" — finds all pipes or chains that produce it. |
| "What can I do with X?" | "What pipes accept `ContractDocument` as input?" — shows downstream possibilities. |
| Compatibility check | Before installing a package, verify its pipes are type-compatible with yours. |

Because MTHDS concepts have a refinement hierarchy, type-compatible search understands that a pipe accepting `Text` also accepts `NonCompeteClause` (since `NonCompeteClause` refines `Text` through the refinement chain).

### Auto-Composition

When no single pipe transforms X into Y, the Know-How Graph can find a **chain** through intermediate concepts:

```
Document → [extract_pages] → Page[] → [analyze_content] → AnalysisResult
```

This is auto-composition — discovering multi-step pipelines by traversing the graph. The `mthds pkg graph` command supports this with the `--from` and `--to` options.

### Cross-Package Concept Refinement

Packages can extend another package's vocabulary through concept refinement:

```toml
# In your package, depending on acme_legal
[concept.EmploymentNDA]
description = "A non-disclosure agreement specific to employment contexts"
refines     = "acme_legal->legal.contracts.NonDisclosureAgreement"
```

This builds on `NonDisclosureAgreement` from the `acme_legal` dependency without merging namespaces. The refinement relationship enriches the Know-How Graph: any pipe that accepts `NonDisclosureAgreement` now also accepts `EmploymentNDA`.

### From Packages to Knowledge

The Know-How Graph emerges naturally from the package system:

1. Each package exports pipes with typed signatures.
2. Concepts define a shared vocabulary with refinement hierarchies.
3. Dependencies connect packages, enabling cross-package references.
4. Registry indexes crawl this information and make it searchable.

The result is a federated network of composable, discoverable, type-safe AI methods — where finding the right method is as precise as asking "I have X, I need Y."

### See Also

- [Concepts](01-the-language.md#page-concepts) — how concepts define typed data and refinement.
- [Exports & Visibility](#page-exports--visibility) — which pipes are visible in the graph.
- [Distribution](#page-distribution) — how registries index packages.
