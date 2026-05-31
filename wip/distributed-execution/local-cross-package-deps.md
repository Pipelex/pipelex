# Local Cross-Package Dependencies in the Crate

> Part of the [distributed-execution plan](README.md) (P2); a step toward [crate-first-architecture.md](crate-first-architecture.md).

## Why

Today, cross-package dependencies (`alias->domain.ConceptCode`, `alias::domain.pipe_code`) resolve through child library lookups at loading time. The `LibraryCrate` shipped to Temporal workers does NOT include dependency content — only the main package's blueprints. This means workers must have all dependency packages pre-installed on PIPELEXPATH. The goal is to remove this requirement: the crate becomes truly self-contained, so workers can execute cross-package pipelines without the dependency packages installed.

## Key changes

1. **Extract blueprint collector from `_load_single_dependency`**: Split the current method into two parts:
   - **Collect**: resolve the dependency, parse its `.mthds` files into blueprints, determine exports.
   - **Load**: create child Library, load domains/concepts/pipes, register aliases.

   The collector produces blueprints that accumulate into `_blueprints[library_id]` alongside the main package's blueprints, so `get_crate()` produces a crate that includes dependency content.

2. **Resolve cross-package aliases in the flattened crate**: Cross-package refs use alias-based syntax (`alias->domain.ConceptCode`). In a flattened crate, there are no child libraries. Options:
   - Resolve aliases during crate building (replace `alias->domain.ConceptCode` with `domain.ConceptCode` in all blueprints).
   - Carry alias mappings in the crate (`aliases: dict[str, str]`) for runtime resolution.

   Decision TBD when starting implementation.

3. **Update `load_from_crate()`**: Handle dependency content in the flat crate — register domains, concepts, and pipes from deps.

## Acceptance

A PipeSequence referencing a cross-package concept/pipe executes on a Temporal worker that does **not** have the dependency package on PIPELEXPATH.
