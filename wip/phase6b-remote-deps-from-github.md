# Phase 6b — Remote Dependencies from GitHub

> **Status**: Not started
> **Goal**: Dependencies can be fetched from remote addresses (e.g., `github.com/org/repo/package`). The crate becomes fully self-contained for cloud-native execution where workers are stateless.
> **Predecessor**: [phase6a-local-cross-package-deps.md](phase6a-local-cross-package-deps.md) — needs the blueprint collector extracted in 6a.
> **Related**: [02-master-plan.md](02-master-plan.md), [future-crate-first-architecture.md](future-crate-first-architecture.md).

---

## Key changes

1. **Remote resolution strategy**: Add a `REMOTE` resolution strategy to the blueprint collector extracted in 6a. Remote fetch clones/downloads the package from GitHub, parses its `.mthds` files into blueprints, and includes them in the collection.

2. **Dependency address format**: Define the address format for remote deps (e.g., `github.com/org/repo@version/path/to/package`). The address goes in the package manifest.

3. **Caching**: Cache fetched packages locally (content-addressed by address + version) to avoid redundant clones.

4. **Transitive deps**: Remote packages may themselves have dependencies (local or remote). The collector recurses.

## Done when

- [ ] Remote fetch strategy implemented (git clone or archive download)
- [ ] Dependency address format defined and parsed
- [ ] Remote package blueprints included in crate
- [ ] Local cache for fetched packages
- [ ] Transitive remote deps resolved
- [ ] Integration test: pipeline with remote dep from a GitHub repo, executed on Temporal worker
- [ ] `make agent-check` passes
- [ ] `make agent-test` passes
