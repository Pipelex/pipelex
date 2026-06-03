# Remote Dependencies from GitHub

> Part of the [distributed-execution plan](README.md) (P3); a step toward [crate-first-architecture.md](crate-first-architecture.md). Builds on the blueprint collector from [local-cross-package-deps.md](local-cross-package-deps.md).

The goal: dependencies can be fetched from remote addresses (e.g. `github.com/org/repo/package`), so the crate becomes fully self-contained for cloud-native execution where workers are stateless.

## Key changes

1. **Remote resolution strategy**: Add a `REMOTE` resolution strategy to the blueprint collector. Remote fetch clones/downloads the package from GitHub, parses its `.mthds` files into blueprints, and includes them in the collection.

2. **Dependency address format**: Define the address format for remote deps (e.g., `github.com/org/repo@version/path/to/package`). The address goes in the package manifest.

3. **Caching**: Cache fetched packages locally (content-addressed by address + version) to avoid redundant clones.

4. **Transitive deps**: Remote packages may themselves have dependencies (local or remote). The collector recurses.

## Acceptance

A pipeline with a remote GitHub dependency executes on a Temporal worker that does **not** have the dependency pre-installed.
