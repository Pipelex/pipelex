# Pkg Commands

Manage package manifests for your Pipelex project.

## Pkg Init

```bash
pipelex pkg init
pipelex pkg init --force
```

Scans `.mthds` files in the current directory, discovers domains and pipes, and generates a skeleton `METHODS.toml` manifest.

The generated manifest includes:

- A placeholder `address` (edit this to your actual package address)
- Version set to `0.1.0`
- All discovered domains listed in the `[exports]` section with their pipes

**Options:**

| Option | Description |
|--------|-------------|
| `--force`, `-f` | Overwrite an existing `METHODS.toml` |

**Examples:**

```bash
# Generate a manifest from .mthds files
pipelex pkg init

# Overwrite an existing manifest
pipelex pkg init --force
```

!!! note
    The command refuses to overwrite an existing `METHODS.toml` unless `--force` is specified. If no `.mthds` files are found in the current directory, the command exits with an error.

## Pkg List

```bash
pipelex pkg list
```

Finds the nearest `METHODS.toml` by walking up from the current directory and displays its contents in Rich-formatted tables:

- **Package** — address, version, description, authors, license, MTHDS version
- **Dependencies** — alias, address, and version constraint for each dependency
- **Exports** — domain path and exported pipe names

**Examples:**

```bash
# Display the package manifest
pipelex pkg list
```

!!! note
    If no `METHODS.toml` is found in the current directory or any parent directory (up to the `.git` boundary), the command exits with an error and suggests running `pipelex pkg init`.

## Related Documentation

- [Packages](../../6-build-reliable-ai-workflows/packages.md) — Package system concepts and manifest reference
- [Validate](validate.md) — Validating pipelines and configuration
