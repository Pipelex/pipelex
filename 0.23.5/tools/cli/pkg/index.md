# Package Commands

Package manifest management is currently exposed through the `mthds` CLI, not the `pipelex` CLI.

Use these commands when you need to create, inspect, or validate a `METHODS.toml` file for a method package.

## Overview

```bash
mthds package init
mthds package list
mthds package validate
```

All three commands also accept `-C, --package-dir <path>` to target a package directory other than the current one.

## `mthds package init`

```bash
mthds package init
mthds package init -C ./my-package
```

Create a new `METHODS.toml` manifest interactively.

The command prompts for:

- package `address`
- `version`
- `description`
- optional `authors`
- optional `license`

It writes a manifest with package metadata and an empty `[exports]` section. If `METHODS.toml` already exists, the CLI asks whether to overwrite it.

## `mthds package list`

```bash
mthds package list
mthds package list -C ./my-package
```

Read and display the current `METHODS.toml` manifest from the target directory.

The output includes:

- package address, version, and description
- optional display name, authors, and license
- declared exports by domain

If no `METHODS.toml` exists in the target directory, the command reports an error and suggests running `mthds package init`.

## `mthds package validate`

```bash
mthds package validate
mthds package validate -C ./my-package
```

Validate the `METHODS.toml` manifest in the target directory.

This checks manifest syntax and package metadata fields, then reports the parsed manifest back on success.

## Current Scope

The public package-management commands currently documented in this repo are:

- `mthds package init`
- `mthds package list`
- `mthds package validate`

Older `pipelex pkg ...` examples and dependency-management commands such as `add`, `lock`, `install`, and `update` are not part of the current Python `pipelex` CLI surface and should not be used here.

## Related Documentation

- [Packages](../../building-methods/packages.md) — Package manifest concepts and `METHODS.toml` structure
- [CLI](index.md) — Runtime CLI vs `mthds` CLI overview
