# plxt (Formatter & Linter)

## Overview

`plxt` is a fast formatting and linting tool for TOML, MTHDS, and PLX files in Pipelex projects. It ensures consistent style across all configuration and pipeline definition files, powered by the [taplo](https://taplo.tamasfe.dev/) engine.

## Installation

`plxt` is included as a Pipelex development dependency. It is automatically installed into your virtual environment when you run:

```bash
make install
```

You can verify the installation with:

```bash
.venv/bin/plxt --help
```

## Configuration

`plxt` reads its configuration from `.pipelex/plxt.toml` at the root of your project. This file controls file discovery, formatting rules, and per-file-type overrides.

### File Discovery

The `include` and `exclude` top-level keys control which files `plxt` processes:

```toml
include = ["**/*.toml", "**/*.mthds", "**/*.plx"]

exclude = [
  ".venv/**",
  ".mypy_cache/**",
  ".ruff_cache/**",
  ".pytest_cache/**",
  "__pycache__/**",
  "target/**",
  "node_modules/**",
  ".git/**",
  "*.lock",
]
```

### Supported File Types

| Extension | Description |
|-----------|-------------|
| `.mthds` | Method definitions |
| `.plx` | Method definitions (legacy extension) |
| `.toml` | Standard TOML configuration files |

### Key Formatting Options

The `[formatting]` section in `plxt.toml` controls the global formatting behavior. Each option can be overridden per file type using `[[rule]]` sections.

| Option | Default | Description |
|--------|---------|-------------|
| `align_entries` | `false` | Align consecutive `key = value` entries so `=` signs line up |
| `align_comments` | `true` | Align end-of-line comments on consecutive lines |
| `array_trailing_comma` | `true` | Add a trailing comma after the last element in multiline arrays |
| `array_auto_expand` | `true` | Expand arrays to multiple lines when exceeding `column_width` |
| `column_width` | `80` | Target maximum line width used for auto-expand/collapse |
| `compact_arrays` | `true` | Omit spaces inside single-line array brackets |
| `trailing_newline` | `true` | Ensure files end with a newline character |
| `reorder_keys` | `false` | Sort top-level keys alphabetically |

For the full list of options, see the comments in `.pipelex/plxt.toml`.

### Per-File-Type Rules

You can define `[[rule]]` sections to apply different formatting settings to different file types. For example, the default configuration includes separate rules for `.toml` files and for `.mthds`/`.plx` files:

```toml
[[rule]]
include = ["**/*.toml"]
[rule.formatting]
# TOML-specific overrides here

[[rule]]
include = ["**/*.mthds", "**/*.plx"]
[rule.formatting]
align_entries = true
# ... more MTHDS/PLX-specific overrides
```

## Usage

### Command Line

Format all discovered files in place:

```bash
.venv/bin/plxt fmt
```

Check formatting without modifying files (useful for CI):

```bash
.venv/bin/plxt fmt --check
```

Lint all discovered files:

```bash
.venv/bin/plxt lint
```

### Make Targets

The following Make targets are available for convenience:

| Target | Description |
|--------|-------------|
| `make plxt-format` | Format all MTHDS/TOML/PLX files |
| `make plxt-lint` | Lint all MTHDS/TOML/PLX files |
| `make merge-check-plxt-format` | Check formatting without modifying files |
| `make merge-check-plxt-lint` | Run lint check |

`plxt` is also included in the composite check targets:

- `make c` (check) runs `plxt-format` and `plxt-lint` alongside ruff, pyright, and mypy
- `make agent-check` includes `plxt-format` and `plxt-lint` in the full quality pipeline
