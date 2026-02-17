# Pkg Commands

Manage package manifests and dependencies for your Pipelex project.

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

## Pkg Add

```bash
pipelex pkg add ADDRESS [OPTIONS]
```

Adds a dependency entry to the `METHODS.toml` in the current directory.

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `ADDRESS` | Yes | Package address (e.g. `github.com/org/repo`) |

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--alias`, `-a` | Auto-derived | Dependency alias (snake_case) |
| `--version`, `-v` | `0.1.0` | Version constraint |
| `--path`, `-p` | — | Local filesystem path to the dependency |

When no `--alias` is provided, the alias is automatically derived from the last segment of the address. For example, `github.com/acme/scoring-lib` produces the alias `scoring_lib` (hyphens and dots are replaced with underscores).

**Examples:**

```bash
# Add a remote dependency (alias auto-derived as "scoring_lib")
pipelex pkg add github.com/acme/scoring-lib --version "^2.0.0"

# Add with an explicit alias
pipelex pkg add github.com/acme/scoring-lib --alias scoring --version "^2.0.0"

# Add a local development dependency
pipelex pkg add github.com/acme/scoring-lib --version "2.0.0" --path "../scoring-lib"
```

!!! note
    A `METHODS.toml` must already exist in the current directory. Run `pipelex pkg init` first if needed. The command also checks that the alias is unique — duplicate aliases are rejected.

## Pkg Lock

```bash
pipelex pkg lock
```

Resolves all remote dependencies (including transitive ones) and generates a `methods.lock` file next to `METHODS.toml`. The lock file records the exact version, SHA-256 integrity hash, and source URL for each resolved package.

Local path dependencies are skipped — they are resolved from the filesystem and do not appear in the lock file.

**Examples:**

```bash
# Resolve dependencies and write the lock file
pipelex pkg lock
```

!!! note "Commit to Version Control"
    You should commit `methods.lock` to your repository so that every collaborator and CI run installs the exact same dependency versions.

## Pkg Install

```bash
pipelex pkg install
```

Reads the `methods.lock` file and fetches any packages not already present in the local cache (`~/.mthds/packages/`). After fetching, it verifies the SHA-256 integrity of all cached packages against the lock file.

**Examples:**

```bash
# Install dependencies from the lock file
pipelex pkg install
```

!!! note
    A `methods.lock` file must exist. Run `pipelex pkg lock` first to generate one. If a cached package's hash does not match the lock file, the command fails with an integrity error.

## Pkg Update

```bash
pipelex pkg update
```

Performs a **fresh resolve** of all dependencies — the existing `methods.lock` is ignored. After resolving, it rewrites the lock file and displays a diff showing added, removed, and updated packages.

**Examples:**

```bash
# Re-resolve all dependencies and update the lock file
pipelex pkg update
```

!!! tip
    Use `pkg update` after changing version constraints in `METHODS.toml`. For day-to-day reproducible installs, use `pkg install` instead.

## Related Documentation

- [Packages](../../6-build-reliable-ai-workflows/packages.md) — Package system concepts, dependency workflow, and manifest reference
- [Validate](validate.md) — Validating pipelines and configuration
