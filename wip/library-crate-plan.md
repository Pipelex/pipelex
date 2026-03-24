# LibraryCrate Implementation Plan

## Context

Library loading currently goes directly from parsed `.mthds` files (`PipelexBundleBlueprint`) to a live `Library` with no stable intermediate representation. This couples parsing, merging, qualifying, and instantiating. The `LibraryCrate` introduces a clean three-stage pipeline:

```
Bundles (files)  →  LibraryCrate (data)  →  Library (live)
```

The crate is a pure-data Pydantic model holding fully qualified, merged blueprints — the single gateway between sourcing and instantiation.

---

## Implementation Steps

### Step 1: Create `LibraryCrate` model + `LibraryCrateError` exception

**New file:** `pipelex/libraries/library_crate.py`

- `LibraryCrate(BaseModel)` with:
  - `concepts: dict[str, ConceptBlueprint]` — keyed by `concept_ref` (domain.ConceptCode)
  - `pipes: dict[str, PipeBlueprintUnion]` — keyed by `pipe_ref` (domain.pipe_code)
  - `domains: dict[str, DomainBlueprint]` — keyed by `domain_code`, first-write-wins
  - `source_map: dict[str, str]` — maps concept_ref/pipe_ref to source file path (for error reporting)
  - `fingerprint: str` — SHA-256 of deterministic JSON serialization
- Flat dicts, no domain nesting. Domain is encoded in keys.
- String-described concepts already normalized to `ConceptBlueprint`.
- Includes all metadata and source details so validation errors can report where things came from.

**New file:** `pipelex/libraries/library_crate_exceptions.py`

- `LibraryCrateError(Exception)` — raised on ref collisions during crate building

### Step 2: Write unit tests for LibraryCrate model and factory (TDD — RED)

**New file:** `tests/unit/pipelex/libraries/test_library_crate.py`
**New file:** `tests/unit/pipelex/libraries/test_library_crate_data.py`

`TestLibraryCrate` class — write all tests first, expect them to fail:
1. JSON round-trip
2. `make_from_blueprints` merges correctly (same domain, different concepts/pipes)
3. `make_from_blueprints` merges across domains
4. String concept normalization
5. Concept collision raises `LibraryCrateError`
6. Pipe collision raises `LibraryCrateError`
7. Fingerprint determinism (same input → same hash, different input → different hash)
8. Empty blueprints
9. Source map populated correctly

### Step 3: Create `LibraryCrateFactory` (TDD — GREEN)

**New file:** `pipelex/libraries/library_crate_factory.py`

- `LibraryCrateFactory.make_from_blueprints(blueprints: list[PipelexBundleBlueprint]) -> LibraryCrate`
- Algorithm:
  1. For each blueprint, qualify concept codes and pipe codes with `blueprint.domain`
  2. Normalize `str` concept values to `ConceptBlueprint(description=value)`
  3. Collect domain metadata (first-write-wins per domain code)
  4. Track source file for each concept_ref and pipe_ref
  5. Detect duplicate concept_refs and pipe_refs across bundles → raise `LibraryCrateError`
  6. Compute SHA-256 fingerprint via `model_dump_json()`

Run unit tests → all should pass.

### Step 4: Write integration test for `load_from_crate` (TDD — RED)

**New file:** `tests/integration/pipelex/libraries/test_load_from_crate.py`

`TestLoadFromCrate` class — write test first, expect it to fail:
1. Equivalence test: load `.mthds` files via `load_from_blueprints()`, then separately build crate + `load_from_crate()`. Assert both libraries have same concept_refs, pipe_refs, domain codes.

### Step 5: Add `load_from_crate()` + `_load_concepts_from_crate()` to LibraryManager (TDD — GREEN)

**Modify:** `pipelex/libraries/library_manager.py`

New method `load_from_crate(library_id, crate) -> list[PipeAbstract]`:
1. Create `Domain` objects from `crate.domains`
2. Load concepts from `crate.concepts` via new `_load_concepts_from_crate()` (topo-sort, factory calls)
3. Rebuild forward refs, detect cycles
4. Load pipes from `crate.pipes` — **filter `concept_codes_from_the_same_domain` to only concepts in the pipe's domain** (fixes current bug where all concept codes are passed regardless of domain, line 409)
5. Validate library, return all pipes

No separate `domain_metadata` parameter needed — domain metadata lives in the crate itself.

New private method `_load_concepts_from_crate(concepts: dict[str, ConceptBlueprint]) -> list[Concept]`:
- Same topo-sort logic as `_load_concepts_from_blueprints` but iterating over flat `dict[concept_ref, ConceptBlueprint]`
- No duplicate detection needed (already done by `LibraryCrateFactory`)
- Keeps original `_load_concepts_from_blueprints` working for `load_concepts_only_from_blueprints()`

**Also modify:** `pipelex/libraries/library_manager_abstract.py` — add `load_from_crate()` abstract method

### Step 6: Refactor `load_from_blueprints()` to delegate through crate

**Modify:** `pipelex/libraries/library_manager.py`

Refactored `load_from_blueprints()`:
1. Call `_load_address_based_dependencies()` (unchanged)
2. Build crate via `LibraryCrateFactory.make_from_blueprints()`
3. Call `load_from_crate(library_id, crate)`
4. Build `_pipe_source_map` from `crate.source_map` (pipe_ref entries only)

`load_concepts_only_from_blueprints()` remains as-is for Phase 1.

### Step 7: Lint and test

- `make agent-check`
- `make agent-test`

---

## Domain filtering fix (concept_codes_from_the_same_domain)

The current `load_from_blueprints()` at line 409 passes ALL concept codes to `PipeFactory.make_from_blueprint()`:
```python
concept_codes_from_the_same_domain=[the_concept.code for the_concept in all_concepts],
```

This is incorrect — the parameter name says "from the same domain" but all concepts are passed. In `load_from_crate()`, we fix this by filtering:
```python
concept_codes_for_domain = [
    QualifiedRef.parse_concept_ref(ref).local_code
    for ref in crate.concepts
    if ref.startswith(f"{domain_code}.")
]
```

This is a behavioral fix included in this PR.

---

## Files to Create/Modify

| File | Action |
|------|--------|
| `pipelex/libraries/library_crate.py` | **New** |
| `pipelex/libraries/library_crate_factory.py` | **New** |
| `pipelex/libraries/library_crate_exceptions.py` | **New** |
| `pipelex/libraries/library_manager.py` | **Modify** |
| `pipelex/libraries/library_manager_abstract.py` | **Modify** |
| `tests/unit/pipelex/libraries/test_library_crate.py` | **New** |
| `tests/unit/pipelex/libraries/test_library_crate_data.py` | **New** |
| `tests/integration/pipelex/libraries/test_load_from_crate.py` | **New** |

## Key Existing Code to Reuse

| What | Where |
|------|-------|
| `PipeFactory[PipeAbstract].make_from_blueprint()` | `pipelex/core/pipes/pipe_factory.py` |
| `ConceptFactory.make_from_blueprint()` | `pipelex/core/concepts/concept_factory.py` |
| `ConceptFactory.make_concept_ref_with_domain()` | `pipelex/core/concepts/concept_factory.py` |
| `DomainFactory.make_from_blueprint()` | `pipelex/core/domains/domain_factory.py` |
| `QualifiedRef.parse_concept_ref()` / `parse_pipe_ref()` | `pipelex/core/qualified_ref.py` |
| Topological sort logic | `pipelex/libraries/library_manager.py:472-569` |
| `_rebuild_models_with_forward_refs()` | `pipelex/libraries/library_manager.py` |
| `_detect_concept_cycles()` | `pipelex/libraries/library_manager.py` |

## Verification

1. `make agent-check` — all linting passes
2. `make agent-test` — all existing + new tests pass
3. Integration equivalence test confirms crate path produces identical library content
