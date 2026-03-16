---
title: "Packages"
description: "Use `METHODS.toml` to give a method package an identity and define which pipes it exports. Learn the current public `mthds package` workflow."
---

# Packages

A **package** is a collection of `.mthds` bundles with a `METHODS.toml` manifest at the project root. The manifest gives the package an identity and defines which pipes are exported to the outside world.

!!! info "Opt-in packaging"
    If your project has no `METHODS.toml`, Pipelex still loads your local bundles. Packaging is optional.

## What the Manifest Does

`METHODS.toml` currently serves two main purposes:

- **Identity**: give the package an address, version, and description
- **Visibility**: declare which pipes are exported through `[exports]`

## The Package Manifest: `METHODS.toml`

Here is a representative manifest:

```toml
[package]
address = "github.com/acme/legal-tools"
version = "1.0.0"
description = "Legal document analysis and contract review methods."
authors = ["Acme Corp"]
license = "MIT"
mthds_version = ">=0.8.0"

[exports.legal.contracts]
pipes = ["extract_clause", "analyze_contract"]

[exports.scoring]
pipes = ["compute_weighted_score"]
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `address` | Yes | Package address following a hostname/path pattern such as `github.com/org/repo` |
| `version` | Yes | Semantic version such as `1.0.0` or `2.1.3-beta.1` |
| `description` | Yes | Human-readable package description |
| `name` | No | Optional short method name |
| `display_name` | No | Optional display label |
| `authors` | No | List of author names |
| `license` | No | License string such as `MIT` |
| `main_pipe` | No | Optional main pipe code |
| `mthds_version` | No | Required MTHDS version constraint |

## Exports and Visibility

The `[exports]` section controls which pipes are visible outside the package.

### Default Behavior

- **Without `METHODS.toml`**: local bundles are still available to your project
- **With `METHODS.toml`**: pipes are private by default — only pipes listed in `[exports]` (and each bundle's `main_pipe`) are visible from outside

### Declaring Exports

Exports are grouped by domain path:

```toml
[exports.legal.contracts]
pipes = ["extract_clause", "analyze_contract"]

[exports.scoring]
pipes = ["compute_weighted_score"]
```

This manifest exports two pipes from `legal.contracts` and one pipe from `scoring`.

## Cross-Package References

Pipelex can resolve cross-package references when the required packages are available to the runtime. The reference form is:

```text
alias->domain.code
```

Example:

```toml
[pipe.analyze_item]
type = "PipeSequence"
description = "Analyze an item using another package"
steps = [
    { pipe = "scoring_lib->scoring.compute_weighted_score" },
]
```

This runtime-level capability exists separately from the current public `mthds package` CLI workflow documented on this page. If you rely on cross-package references, validate them against the specific runtime setup you are using.

### Example Layout

```text
your-project/
├── METHODS.toml
├── my_project/
│   ├── finance/
│   │   ├── invoices.mthds
│   │   └── invoices_struct.py
│   └── legal/
│       ├── contracts.mthds
│       └── contracts_struct.py
├── .pipelex/
│   └── pipelex.toml
└── requirements.txt
```

The `METHODS.toml` file sits at the project root. Pipelex discovers it by walking up from bundle locations until it finds the manifest.

## Current Public CLI Workflow

The public package-management commands documented in this repo are provided by the lowercase `mthds` CLI:

```bash
mthds package init
mthds package list
mthds package validate
```

### Initialize a Manifest

```bash
mthds package init
```

This command creates `METHODS.toml` interactively. It asks for package metadata and writes a manifest with an empty `[exports]` section.

### Inspect a Manifest

```bash
mthds package list
```

This command reads the manifest from the target package directory and prints the parsed package metadata and exports.

### Validate a Manifest

```bash
mthds package validate
```

This command validates the manifest syntax and package fields.

### Target a Different Directory

All three commands accept `-C, --package-dir <path>`:

```bash
mthds package init -C ./my-package
mthds package list -C ./my-package
mthds package validate -C ./my-package
```

## Important Compatibility Note

The current public `mthds package validate` command focuses on package identity and exports. It does **not** document a public dependency-management workflow here, and it rejects a `[dependencies]` section in the current JS CLI validation path.

For this reason, this documentation only describes the stable public package-manifest workflow exposed by the current `mthds` CLI.

## Related Documentation

- [Domain](./domain.md) — How domains organize concepts and pipes
- [Libraries](./libraries.md) — How libraries load and validate bundles
- [Pipelex Bundle Specification](./pipelex-bundle-specification.md) — The `.mthds` file format
- [Package Commands](../tools/cli/pkg.md) — `mthds package` command reference
