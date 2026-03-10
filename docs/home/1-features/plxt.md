---
title: plxt Formatter & Linter
---

# plxt Formatter & Linter

A Rust-based formatter and linter for TOML that supports schema-based validation, customized for the MTHDS language.

## Overview

<!-- TODO: Expand with plxt capabilities -->

`plxt` is a fast, Rust-based TOML formatter and linter with schema-based validation support. It has been customized to understand the MTHDS language, providing formatting and linting tailored to `.mthds` and `.plx` files.

## Formatting

<!-- TODO: Describe formatting capabilities -->

- **TOML files** — Standard TOML formatting
- **MTHDS files** — Schema-aware formatting for method definitions
- **PLX files** — Pipelex configuration formatting
- **Alignment options** — Configurable alignment for entries and comments
- **Per-file-type rules** — Different formatting rules for different file types

## Linting

<!-- TODO: Describe linting rules -->

Schema-based validation that catches structural and semantic issues beyond basic syntax checking.

## CI Integration

<!-- TODO: Describe --check mode -->

Use `--check` mode for validation without modification — perfect for CI pipelines.

For details, see the [plxt reference](../9-tools/plxt.md).
