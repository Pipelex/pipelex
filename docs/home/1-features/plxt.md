---
title: plxt Formatter & Linter
---

# plxt Formatter & Linter

A Rust-based formatter and linter for TOML that supports schema-based validation, customized for the MTHDS language.

## Overview

`plxt` is a fast, Rust-based TOML formatter and linter with schema-based validation support. It has been customized to understand the MTHDS language, providing formatting and linting tailored to `.mthds` and `.plx` files. It is distributed as part of the `pipelex-tools` package.

## Formatting

- **TOML files** — Standard TOML formatting
- **MTHDS files** — Schema-aware formatting for method definitions
- **PLX files** — Pipelex configuration formatting
- **Alignment options** — Configurable alignment for entries and comments
- **Per-file-type rules** — Different formatting rules for different file types

## Linting

Schema-based validation that catches structural and semantic issues beyond basic syntax checking. Detects invalid keys, missing required fields, type mismatches, and MTHDS-specific violations such as unknown pipe operators or invalid concept references.

## CI Integration

Use `--check` mode for validation without modification — perfect for CI pipelines. The command exits with a non-zero code if any file would be reformatted or has linting errors, making it easy to enforce formatting standards in automated workflows.

For details, see the [plxt reference](../9-tools/plxt.md).
