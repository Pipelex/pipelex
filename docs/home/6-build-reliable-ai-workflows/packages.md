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

Dependencies are declared in the `[dependencies]` section using an alias-as-key format:

```toml
[dependencies]
scoring_lib = { address = "github.com/acme/scoring-lib", version = "^2.0.0" }
nlp_utils   = { address = "github.com/acme/nlp-utils", version = ">=1.0.0, <3.0.0" }
```

- The **alias** (left-hand key) must be `snake_case`. It is used when making cross-package pipe references with the `->` syntax (e.g. `scoring_lib->scoring.compute_weighted_score`).
- The **address** follows the same hostname/path pattern as the package address.
- The **version** field accepts standard version constraint syntax:

| Syntax | Meaning | Example |
|--------|---------|---------|
| `1.0.0` | Exact version | `1.0.0` |
| `^1.0.0` | Compatible release (same major) | `^2.0.0` |
| `~1.0.0` | Approximately compatible (same major.minor) | `~1.2.0` |
| `>=`, `<=`, `>`, `<` | Comparison operators | `>=1.0.0` |
| `==`, `!=` | Equality / inequality | `!=1.3.0` |
| Comma-separated | Compound constraints | `>=1.0.0, <2.0.0` |
| `*`, `1.*`, `1.0.*` | Wildcards | `2.*` |

!!! note
    Each dependency alias must be unique within the manifest.

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

**Scaffold a manifest** from your existing bundles:

```bash
pipelex pkg init
```

This scans all `.mthds` files in the current directory, discovers domains and pipes, and generates a skeleton `METHODS.toml` with placeholder values. Edit the generated file to set the correct address and tune your exports.

**Inspect the current manifest:**

```bash
pipelex pkg list
```

This displays the package metadata, dependencies, and exports in formatted tables.

See the [Pkg CLI reference](../9-tools/cli/pkg.md) for full command details.

## Related Documentation

- [Domain](./domain.md) — How domains organize concepts and pipes
- [Libraries](./libraries.md) — How libraries load and validate bundles
- [Pipelex Bundle Specification](./pipelex-bundle-specification.md) — The `.mthds` file format
- [Pkg CLI](../9-tools/cli/pkg.md) — CLI commands for package management
