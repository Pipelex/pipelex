# Phase 6a — Local Cross-Package Dependencies in Crate

> **Status**: Not started
> **Goal**: Dependency blueprints are included in the crate. Workers can execute pipelines with cross-package deps without having the dependency packages installed on PIPELEXPATH.
> **Predecessor**: Phase 2 (crate propagation, shipped — see `00-master-plan.md`, workspace `docs/history/distributed-execution/`).
> **Related**: [02-master-plan.md](02-master-plan.md), [future-crate-first-architecture.md](crate-architecture/future-crate-first-architecture.md).

---

## Why

Today, cross-package dependencies (`alias->domain.ConceptCode`, `alias::domain.pipe_code`) resolve through child library lookups at loading time. The `LibraryCrate` shipped to Temporal workers does NOT include dependency content — only the main package's blueprints. This means workers must have all dependency packages pre-installed on PIPELEXPATH. Phase 6 removes this requirement: the crate becomes truly self-contained.

## Key changes

1. **Extract blueprint collector from `_load_single_dependency`**: Split the current method into two parts:
   - **Collect**: resolve the dependency, parse its `.mthds` files into blueprints, determine exports.
   - **Load**: create child Library, load domains/concepts/pipes, register aliases.

   The collector produces blueprints that accumulate into `_blueprints[library_id]` alongside the main package's blueprints.

2. **Resolve cross-package aliases in the flattened crate**: Cross-package refs use alias-based syntax (`alias->domain.ConceptCode`). In a flattened crate, there are no child libraries. Options:
   - Resolve aliases during crate building (replace `alias->domain.ConceptCode` with `domain.ConceptCode` in all blueprints).
   - Carry alias mappings in the crate (`aliases: dict[str, str]`) for runtime resolution.

   Decision TBD when starting implementation.

3. **Update `load_from_crate()`**: Handle dependency content in the flat crate — register domains, concepts, and pipes from deps.

## Done when

- [ ] `_load_single_dependency` split into collect + load
- [ ] Dependency blueprints accumulate into `_blueprints[library_id]`
- [ ] `get_crate()` produces a crate that includes dependency content
- [ ] Cross-package aliases resolved (either at crate build time or via alias map)
- [ ] `load_from_crate()` handles dependency content correctly
- [ ] Integration test: PipeSequence referencing a cross-package concept/pipe, executed on Temporal worker without the dependency package on PIPELEXPATH
- [ ] `make agent-check` passes
- [ ] `make agent-test` passes
