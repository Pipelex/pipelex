# Packages

A **package** is a self-contained collection of `.mthds` bundles with a `METHODS.toml` manifest at the root. The manifest gives your project an identity, declares dependencies on other packages, and controls which pipes are visible to the outside world.

## What is a Package?

A package groups related bundles under a single manifest that provides:

- **Identity** — a unique address and semantic version for your project
- **Dependency declarations** — references to other packages your pipes rely on
- **Visibility control** — fine-grained exports that determine which pipes other domains can reference

!!! info "Backward Compatibility"
    If your project has no `METHODS.toml`, everything works exactly as before — all pipes are treated as public. The manifest is entirely opt-in.

## The Package Manifest: `METHODS.toml`

Place a `METHODS.toml` file at the root of your project (next to your `.mthds` files or their parent directories). Here is a fully annotated example:

```toml
[package]
address = "github.com/acme/legal-tools"
version = "1.0.0"
description = "Legal document analysis and contract review methods."
authors = ["Acme Corp"]
license = "MIT"
mthds_version = ">=0.5.0"

[dependencies]
scoring_lib = { address = "github.com/acme/scoring-lib", version = "^2.0.0" }

[exports.legal.contracts]
pipes = ["extract_clause", "analyze_contract"]

[exports.scoring]
pipes = ["compute_weighted_score"]
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `address` | Yes | Package address following a hostname/path pattern (e.g. `github.com/org/repo`) |
| `version` | Yes | Semantic version (e.g. `1.0.0`, `2.1.3-beta.1`) |
| `description` | Yes | Human-readable package description (must not be empty) |
| `authors` | No | List of author names |
| `license` | No | SPDX license identifier (e.g. `MIT`, `Apache-2.0`) |
| <nobr>`mthds_version`</nobr> | No | Required MTHDS runtime version constraint |

## Dependencies

Dependencies are declared in the `[dependencies]` section using an alias-as-key format.

### Declaring Dependencies

Each dependency entry maps a **snake_case alias** to a package address and version constraint:

```toml
[dependencies]
scoring_lib = { address = "github.com/acme/scoring-lib", version = "^2.0.0" }
nlp_utils   = { address = "github.com/acme/nlp-utils", version = ">=1.0.0, <3.0.0" }
```

- The **alias** (left-hand key) must be `snake_case`. It is used when making cross-package references with the `->` syntax (e.g. `scoring_lib->scoring.compute_weighted_score`).
- The **address** follows the same hostname/path pattern as the package address.
- Each dependency alias must be unique within the manifest.

### Version Constraints

The **version** field accepts standard version constraint syntax:

| Syntax | Meaning | Example |
|--------|---------|---------|
| `1.0.0` | Exact version | `1.0.0` |
| `^1.0.0` | Compatible release (same major) | `^2.0.0` |
| `~1.0.0` | Approximately compatible (same major.minor) | `~1.2.0` |
| `>=`, `<=`, `>`, `<` | Comparison operators | `>=1.0.0` |
| `==`, `!=` | Equality / inequality | `!=1.3.0` |
| Comma-separated | Compound constraints | `>=1.0.0, <2.0.0` |
| `*`, `1.*`, `1.0.*` | Wildcards | `2.*` |

### Local Path Dependencies

For development or when you maintain related packages side by side, declare a dependency with a `path` field pointing to a local directory:

```toml
[dependencies]
scoring_lib = { address = "github.com/acme/scoring-lib", version = "2.0.0", path = "../scoring-lib" }
```

When a `path` is present:

- The local directory is used directly — no VCS fetch occurs.
- The dependency is **excluded from the lock file** (`methods.lock`).
- Cross-package references work identically to remote dependencies.

!!! tip "Development Workflow"
    Local path dependencies are ideal during active development of multiple packages. Point to a sibling checkout, iterate on both packages together, and remove the `path` field when you are ready to publish.

### Remote Dependencies

Dependencies without a `path` field are resolved via Git. Pipelex maps the package address to a clone URL (e.g. `github.com/acme/scoring-lib` becomes `https://github.com/acme/scoring-lib.git`), lists the remote version tags, selects the best match for the version constraint, and caches the result locally.

See [Dependency Workflow](#dependency-workflow) below for the full lock → install → update lifecycle.

## Cross-Package References

Once a dependency is declared in `METHODS.toml`, you can reference its exported pipes and concepts from your `.mthds` bundles using the **`->`** syntax.

### The `->` Syntax

A cross-package reference has the form:

```
alias->domain.code
```

| Part | Description |
|------|-------------|
| `alias` | The dependency alias declared in `[dependencies]` |
| `->` | Cross-package reference operator |
| `domain` | The dot-separated domain path inside the dependency package |
| `code` | The pipe code (`snake_case`) or concept code (`PascalCase`) |

### Referencing Pipes Across Packages

To call a pipe from a dependency inside a `PipeSequence` step, use the `->` syntax in the `pipe` field.

**Dependency package** (`scoring-lib`):

```toml title="METHODS.toml"
[package]
address = "github.com/acme/scoring-lib"
version = "2.0.0"
description = "Scoring utilities for weighted analysis."

[exports.scoring]
pipes = ["compute_weighted_score"]
```

```toml title="scoring.mthds"
domain = "scoring"

[concept.WeightedScore]
description = "A weighted score result"

[pipe.compute_weighted_score]
type = "PipeLLM"
description = "Compute a weighted score"
output = "WeightedScore"
prompt = "Compute a weighted score for: {{ item }}"
```

**Consumer package**:

```toml title="METHODS.toml"
[package]
address = "github.com/acme/analysis-app"
version = "1.0.0"
description = "Analysis application using the scoring library."

[dependencies]
scoring_lib = { address = "github.com/acme/scoring-lib", version = "^2.0.0" }

[exports.analysis]
pipes = ["analyze_item"]
```

```toml title="analysis.mthds"
domain = "analysis"
main_pipe = "analyze_item"

[pipe.analyze_item]
type = "PipeSequence"
description = "Analyze an item using the scoring dependency"
output = "AnalysisResult"
steps = [
    { pipe = "scoring_lib->scoring.compute_weighted_score" },
    { pipe = "summarize" },
]
```

The first step calls `compute_weighted_score` from the `scoring` domain of the `scoring_lib` dependency. The second step calls a local pipe.

!!! important
    The referenced pipe must be listed in the dependency's `[exports]` section (or be a bundle's `main_pipe`, which is auto-exported). Referencing a non-exported pipe raises a visibility error at load time.

### Referencing Concepts Across Packages

Concepts from a dependency can be used in pipe inputs and outputs using the same `->` syntax:

```toml
[pipe.display_score]
type = "PipeLLM"
description = "Format a score for display"
inputs = { score = "scoring_lib->scoring.WeightedScore" }
output = "Text"
prompt = "Format this score for display: {{ score }}"
```

### Cross-Package Concept Refinement

You can refine a concept from a dependency — creating a more specialized version that inherits its structure:

```toml
[concept.DetailedScore]
description = "An extended score with additional detail"
refines = "scoring_lib->scoring.WeightedScore"
```

The refined concept inherits the structure of `WeightedScore` from the `scoring_lib` dependency's `scoring` domain. The base concept must be exported by the dependency.

For a complete guide on concept refinement, see [Refining Concepts](./concepts/refining-concepts.md#cross-package-refinement).

## Dependency Workflow

Managing dependencies follows a **lock → install → update** lifecycle, similar to other package managers.

### Lock File (`methods.lock`)

Running `pipelex pkg lock` generates a `methods.lock` file next to your `METHODS.toml`. The lock file records the exact resolved version, an integrity hash, and the source URL for every remote dependency:

```toml
["github.com/acme/scoring-lib"]
version = "2.0.0"
hash = "sha256:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
source = "https://github.com/acme/scoring-lib"

["github.com/acme/nlp-utils"]
version = "1.3.0"
hash = "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
source = "https://github.com/acme/nlp-utils"
```

| Field | Description |
|-------|-------------|
| Table key | The package address |
| `version` | Exact resolved version (semantic version) |
| `hash` | SHA-256 integrity hash of all files in the package (excluding `.git/`) |
| `source` | HTTPS URL to the package source |

!!! note "Commit to Version Control"
    You should commit `methods.lock` to your repository. This ensures that every collaborator and CI run installs the exact same dependency versions.

Local path dependencies are **not** recorded in the lock file — they are always resolved from the filesystem directly.

### Resolving and Locking (`pkg lock`)

```bash
pipelex pkg lock
```

This command:

1. Reads your `METHODS.toml` dependencies
2. Resolves each remote dependency via Git (listing tags, selecting the best version match)
3. Resolves transitive dependencies (dependencies of your dependencies)
4. Computes SHA-256 integrity hashes
5. Writes the `methods.lock` file

See the [Pkg Lock CLI reference](../tools/cli/pkg.md#pkg-lock) for details.

### Installing Dependencies (`pkg install`)

```bash
pipelex pkg install
```

This command:

1. Reads the `methods.lock` file
2. Fetches any packages not already present in the local cache
3. Verifies SHA-256 integrity of all cached packages against the lock file

If a hash mismatch is detected, the command fails with an integrity error.

See the [Pkg Install CLI reference](../tools/cli/pkg.md#pkg-install) for details.

### Updating Dependencies (`pkg update`)

```bash
pipelex pkg update
```

This command performs a **fresh resolve** — it ignores the existing lock file, re-resolves all dependencies from scratch, and rewrites `methods.lock`. It displays a diff showing added, removed, and updated packages.

!!! tip
    Use `pkg update` after changing version constraints in `METHODS.toml`. For day-to-day reproducible builds, use `pkg install` instead.

See the [Pkg Update CLI reference](../tools/cli/pkg.md#pkg-update) for details.

### Transitive Dependencies

Pipelex resolves transitive dependencies automatically. If your dependency `A` depends on package `B`, then `B` is resolved and locked as well.

**Minimum Version Selection (MVS):** When multiple dependency paths request different versions of the same package (a "diamond dependency"), Pipelex selects the minimum version that satisfies all constraints simultaneously. This provides deterministic, reproducible builds.

**Cycle detection:** Circular dependencies (A depends on B, B depends on A) are detected during resolution and raise an error immediately.

**Local path dependencies are not recursed:** If a dependency has a `path` field, its own sub-dependencies are not resolved transitively. Only remote dependencies participate in transitive resolution.

### Package Cache

Fetched remote packages are stored in a local cache at:

```
~/.mthds/packages/{address}/{version}/
```

For example:

```
~/.mthds/packages/github.com/acme/scoring-lib/2.0.0/
```

- The `.git/` directory is stripped from cached copies to save space.
- Writes use a staging directory with atomic rename for safety.
- The cache is shared across all your projects — a package fetched for one project is available to all others.

## Exports and Visibility

The `[exports]` section controls which pipes are visible to other domains. This is the core access-control mechanism of the package system.

### Default Behavior

- **Without `METHODS.toml`**: all pipes are public. Any domain can reference any pipe.
- **With `METHODS.toml`**: pipes are **private by default**. Only pipes listed in `[exports]` (and `main_pipe` entries) are accessible from other domains.

### Declaring Exports

Exports are organized by domain path. Each entry lists the pipes that domain exposes:

```toml
[exports.legal.contracts]
pipes = ["extract_clause", "analyze_contract"]

[exports.scoring]
pipes = ["compute_weighted_score"]
```

In this example, the `legal.contracts` domain exports two pipes, and the `scoring` domain exports one.

### Visibility Rules

| Reference Type | Visibility Check |
|----------------|-----------------|
| Bare reference (no domain prefix) | Always allowed |
| Same-domain reference | Always allowed |
| Cross-domain to exported pipe | Allowed |
| Cross-domain to `main_pipe` | Allowed (auto-exported) |
| Cross-domain to non-exported pipe | **Blocked** |

!!! important
    A bundle's `main_pipe` is **automatically exported** — it is always accessible from other domains, even if it is not listed in the `[exports]` section.

!!! note "Actionable Error Messages"
    Visibility violations are detected at load time. When a pipe reference is blocked, the error message tells you exactly which pipe is inaccessible and suggests adding it to the appropriate `[exports]` section in `METHODS.toml`.

### Example

Given two bundles:

```toml
# contracts.mthds
domain = "legal.contracts"
main_pipe = "review_contract"

[pipe.extract_clause]
# ...

[pipe.analyze_contract]
# ...

[pipe.internal_helper]
# ...
```

```toml
# scoring.mthds
domain = "scoring"

[pipe.compute_weighted_score]
# ...
```

And this manifest:

```toml
[exports.legal.contracts]
pipes = ["extract_clause", "analyze_contract"]
```

Then from a different domain (e.g. `reporting`):

- `legal.contracts.extract_clause` — allowed (exported)
- `legal.contracts.analyze_contract` — allowed (exported)
- `legal.contracts.review_contract` — allowed (auto-exported as `main_pipe`)
- `legal.contracts.internal_helper` — **blocked** (not exported)

## Package Directory Structure

A typical package layout:

```
your-project/
├── METHODS.toml                  # Package manifest
├── methods.lock                  # Lock file (commit to VCS)
├── my_project/
│   ├── finance/
│   │   ├── services.py
│   │   ├── invoices.mthds
│   │   └── invoices_struct.py
│   └── legal/
│       ├── contracts.mthds
│       ├── contracts_struct.py
│       └── services.py
├── .pipelex/
│   └── pipelex.toml
└── requirements.txt
```

The `METHODS.toml` sits at the project root. Pipelex discovers it by walking up from any `.mthds` file until it finds the manifest (stopping at a `.git` boundary or filesystem root).

## Quick Start

**1. Scaffold a manifest** from your existing bundles:

```bash
pipelex pkg init
```

This scans all `.mthds` files in the current directory, discovers domains and pipes, and generates a skeleton `METHODS.toml` with placeholder values. Edit the generated file to set the correct address and tune your exports.

**2. Add a dependency:**

```bash
pipelex pkg add github.com/acme/scoring-lib --version "^2.0.0"
```

This appends a dependency entry to your `METHODS.toml`. The alias is auto-derived from the address (`scoring_lib`), or you can specify one with `--alias`.

**3. Lock your dependencies:**

```bash
pipelex pkg lock
```

This resolves all remote dependencies (including transitive ones), computes integrity hashes, and writes `methods.lock`.

**4. Install dependencies:**

```bash
pipelex pkg install
```

This fetches any packages not already cached and verifies their integrity.

**5. Inspect the current manifest:**

```bash
pipelex pkg list
```

This displays the package metadata, dependencies, and exports in formatted tables.

See the [Pkg CLI reference](../tools/cli/pkg.md) for full command details.

## Related Documentation

- [Domain](./domain.md) — How domains organize concepts and pipes
- [Libraries](./libraries.md) — How libraries load and validate bundles
- [Pipelex Bundle Specification](./pipelex-bundle-specification.md) — The `.mthds` file format
- [Refining Concepts](./concepts/refining-concepts.md) — How to specialize concepts, including cross-package refinement
- [Pkg CLI](../tools/cli/pkg.md) — CLI commands for package management
