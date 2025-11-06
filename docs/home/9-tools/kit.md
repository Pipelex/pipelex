# Pipelex Kit Commands

The Pipelex Kit provides commands for managing agent rules and migration instructions. These commands help you integrate Pipelex guidelines into your AI coding assistants and keep track of breaking changes across versions.

## Available Commands

### Install Agent Rules

Install Pipelex agent rules for AI coding assistants:

```bash
pipelex kit rules
```

This command:

1. Exports agent markdown files to Cursor `.mdc` files with YAML front-matter in `.cursor/rules`
2. Builds merged agent documentation and updates target files for other AI assistants

**Supported AI Assistants:**

- **Cursor** (`.cursor/rules/`)
- **Claude Code** (`CLAUDE.md`)
- **OpenAI Codex** (`AGENTS.md`)
- **GitHub Copilot** (`.github/copilot-instructions.md`)
- **Windsurf** (`.windsurfrules.md`)
- **Blackbox AI** (`BLACKBOX_RULES.md`)

**Options:**

- `--repo-root PATH`: Repository root directory (default: current directory)
- `--cursor/--no-cursor`: Export Cursor rules (default: enabled)
- `--single-files/--no-single-files`: Update single-file agent documentation targets (default: enabled)
- `--dry-run`: Show what would be done without making changes
- `--diff`: Show unified diff of changes
- `--backup SUFFIX`: Create backups with the specified suffix (e.g., `.bak`)

**Examples:**

```bash
# Install rules for all supported AI assistants
pipelex kit rules

# Preview changes without applying them
pipelex kit rules --dry-run --diff

# Install only Cursor rules
pipelex kit rules --no-single-files

# Create backups before updating
pipelex kit rules --backup .bak
```

### Remove Agent Rules

Remove Pipelex agent rules from your project:

```bash
pipelex kit remove-rules
```

This command:

1. Deletes agent markdown files from Cursor `.mdc` files in `.cursor/rules`
2. Removes marked sections from target files (or deletes entire files with `--delete-files`)

**Options:**

- `--repo-root PATH`: Repository root directory (default: current directory)
- `--cursor/--no-cursor`: Remove Cursor rules (default: enabled)
- `--single-files/--no-single-files`: Remove agent documentation from target files (default: enabled)
- `--delete-files`: Delete entire target files instead of just removing marked sections
- `--dry-run`: Show what would be done without making changes
- `--diff`: Show unified diff of changes
- `--backup SUFFIX`: Create backups with the specified suffix (e.g., `.bak`)

**Examples:**

```bash
# Remove all agent rules
pipelex kit remove-rules

# Preview what would be removed
pipelex kit remove-rules --dry-run

# Remove only Cursor rules
pipelex kit remove-rules --no-single-files

# Delete entire target files
pipelex kit remove-rules --delete-files
```

### Sync Migration Instructions

Sync migration instructions from the Pipelex kit to your project:

```bash
pipelex kit migrations
```

This command copies migration documentation files from the `pipelex.kit` package to your project's `.pipelex/migrations` directory. These files provide detailed instructions for migrating between Pipelex versions.

**Options:**

- `--repo-root PATH`: Repository root directory (default: current directory)
- `--dry-run`: Show what would be done without making changes

**Examples:**

```bash
# Sync migration instructions
pipelex kit migrations

# Preview what would be copied
pipelex kit migrations --dry-run
```

## Agent Rules Overview

The agent rules installed by `pipelex kit rules` include:

- **`write_pipelex.md`**: Guidelines for writing Pipelex pipelines, including syntax, best practices, and common patterns
- **`run_pipelex.md`**: Guidelines for running and testing Pipelex pipelines
- **`llms.md`**: LLM configuration and usage guidelines
- **`python_standards.md`**: Python coding standards and best practices
- **`docs.md`**: Guidelines for writing documentation
- **`pytest_standards.md`**: Guidelines for writing unit tests
- **`tdd.md`**: Test-driven development guidelines

These rules are configured in `pipelex/kit/index.toml`.

## Related Documentation

- [Pipe Builder](pipe-builder.md) - Generate pipelines from natural language
- [CLI Commands](cli.md) - General Pipelex CLI documentation

