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

- **Without `METHODS.toml`, or with one that declares no `[exports]`**: every pipe of the package is visible from outside
- **With an `[exports]` section**: pipes are private by default — only the pipes listed in `[exports]` (and each bundle's `main_pipe`) are visible from outside

### Declaring Exports

Exports are grouped by domain path:

```toml
[exports.legal.contracts]
pipes = ["extract_clause", "analyze_contract"]

[exports.scoring]
pipes = ["compute_weighted_score"]
```

This manifest exports two pipes from `legal.contracts` and one pipe from `scoring`. Exports are read by domain: exporting `compute_weighted_score` from `scoring` does not export a pipe of the same name declared in another domain of the package.

### Pipes Call Their Own Package

Inside a package, a pipe calls the package's own pipes, private ones included. A sequence exported by the package can call a helper the manifest does not export, and that helper is loaded with it. A private pipe that no exported pipe calls is not loaded at all, so a problem in it never stops a consumer from loading the package.

A reference written inside a package always reaches that package's pipe. If the consumer declares a pipe with the same domain and code, or another loaded package does, the package's own call is never redirected to it.

### What a Consumer Is Refused

When a consumer references a loaded package, two mistakes are refused when the consumer loads, rather than surfacing later as an unrelated error:

- **A pipe the package does not have** is refused as an unresolved pipe dependency (`unresolved_pipe_dependency`), naming the reference and the package. The same refusal names the error when the package declares the pipe but it failed to build.
- **A pipe the package does not export** is refused as an unexported pipe dependency (`unexported_pipe_dependency`). The pipe exists, so the remedy is to call one of the package's exported pipes, or to export this one in the package's manifest.

These checks apply to the consumer's references and to a package's references to its own pipes. A package's reference to one of its own dependencies is not checked when the consumer loads, because a package's dependencies are not loaded with it.

A reference by bare code, `alias->code`, ignores the package's private pipes when it also matches an exported one, so a private helper sharing an exported pipe's code in another domain does not make the reference ambiguous.

Naming a private pipe by hand, as the pipe to run at the command line or in an API request, is not a reference from inside a method, so `[exports]` does not apply to it: a loaded private pipe can be run that way by its `alias->domain.code`.

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

### Include by Address: Fetch-on-Miss

The alias can also be a **full package address**, so a bundle can reference a method from a public GitHub repository directly — the same reference grammar as [running a method by address](../tools/cli/run-by-address.md):

```toml
[pipe.summarize_report]
type = "PipeSequence"
description = "Extract a document then summarize it"
inputs = { doc = "PDF" }
output = "Summary"
steps = [
    { pipe = "github.com/Pipelex/methods/documents->documents.extract_page_contents_and_views", result = "pages" },
    { pipe = "summarize_pages" },
]
```

An address-based reference resolves against the **installed methods** — `~/.mthds/methods/` (global) and `.mthds/methods/` (project-local), matched by the manifest's `address` + `name`, case-insensitively. When no installed method matches, Pipelex **fetches on miss**: it fetches the package by address — honoring an `@<tag>` pin, through the same grammar, bounds, and tags-only rules as a direct fetch — installs it into `~/.mthds/methods/`, records the fetch provenance (address, tag, and the commit SHA of what was actually cloned) in a `.provenance.json` sidecar beside the manifest, and loads it so resolution proceeds. The next load finds the installed copy and never touches the network again.

A few behaviors worth knowing:

- **Installed wins.** Once a method is installed, it is used as-is — including when a reference pins a different `@<tag>` than what is installed (a warning tells you so). Remove the installed directory to re-fetch.
- **A miss that cannot be bridged refuses the bundle, never a silent pass.** Fetch disabled, an address this runtime cannot fetch, or a failed fetch (a repository that does not exist, a `@tag` that is not a tag, a repository holding no package at that address) refuses the load with one `unresolved_package_dependency` item per package, located on the first pipe that calls it, with the reference as written in `missing_pipe_code` and the reason and the remedy in its message. It is the same invalid verdict as any other mistake in the bundle: `pipelex validate` reports it, `POST /v1/validate` answers `200` with `is_valid: false`, and a run is refused with a `422` before any pipe runs. Every package of the bundle is tried before the refusal, so two bad references give two items.
- **Hosted parity warning.** A fetched method declaring Python structure classes runs locally but triggers the same warning as a direct CLI fetch: hosted execution accepts MTHDS concepts and sandboxed PipeFuncs, not in-process Python. On a sandbox-hosted deployment the fetch refuses such a package outright, with the same rule-naming error. The refusal is not specific to fetching: a sandbox-hosted deployment refuses every method whose Python declares structure classes, however it arrived (see [Python classes](concepts/python-classes.md)).

To **disable network fetches at load time**, set the switch in your `pipelex.toml` (or use the environment variable, which takes precedence):

```toml
[interpreter.methods]
fetch_on_miss = false
```

```bash
export PIPELEX_METHODS_FETCH_ON_MISS=0
```

With fetching disabled, a miss refuses the bundle with that item, whose message names the address and says to install the package where the runtime runs (for example with `mthds install <address>`). See [Methods Configuration](../configuration/config-practical/methods-config.md).

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
