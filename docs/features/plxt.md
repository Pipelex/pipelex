---
title: plxt Formatter & Linter
description: "Format and lint .mthds files with plxt, a fast Rust-based tool with schema validation. Catch structural errors in declarative AI workflows before runtime."
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

Schema-based validation that catches structural issues beyond basic syntax checking. Detects invalid keys, missing required fields, type mismatches, and MTHDS-specific violations such as unknown pipe operators. Cross-reference checks, such as resolving concept references, are handled by `pipelex validate`, not `plxt lint`.

## CI Integration

Use `plxt fmt --check` to validate formatting without modifying files, and run `plxt lint` separately for schema-based checks. Both commands exit with a non-zero code on errors, making them easy to enforce in automated workflows.

For details, see the [plxt reference](../tools/plxt.md).
