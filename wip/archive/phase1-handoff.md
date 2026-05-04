# LibraryCrate: Direct Execution Mode

> **Status**: Ready for implementation
> **Branch from**: `dev` (at or after commit `628e414d` — pipe_ref namespace fix)
> **Date**: 2026-03-24

---

## 1. Motivation

Library loading currently happens in a single monolithic step: `load_from_blueprints()` takes raw `PipelexBundleBlueprint` objects (the direct parse output of `.mthds` files) and produces a live `Library` with instantiated domains, concepts, and pipes. There is no stable intermediate representation between "files on disk" and "fully wired runtime objects."

This creates three problems:

1. **Tight coupling.** Parsing, merging, qualifying, and instantiating are interleaved. You cannot inspect the merged library content without instantiating every concept and pipe.
2. **Testability.** Testing the merging/qualification logic requires running the full factory stack, including `KajsonManager`, forward-reference resolution, and class registry setup.
3. **No caching boundary.** There is no fingerprint or content-addressable snapshot of what a library contains, so there is no way to detect "same content, already loaded" without re-running the full pipeline.

The fix is a clean three-stage pipeline:

```
Bundles (files)  →  LibraryCrate (data)  →  Library (live)
```

The `LibraryCrate` is a pure-data Pydantic model holding the fully qualified, merged blueprints for all concepts and pipes. It is the single gateway between sourcing and instantiation.

---

## 2. Prerequisite: Pipe Namespace Fix (Complete)

PR #780 (`628e414d`) refactored the pipe namespace so that `PipeLibrary` is keyed by `pipe_ref` (`domain.pipe_code`), symmetric with how `ConceptLibrary` uses `concept_ref` (`domain.ConceptCode`). This is required because the LibraryCrate uses qualified refs as dictionary keys.

Key changes already on `dev`:
- `PipeAbstract.pipe_ref` property: `f"{self.domain_code}.{self.code}"`
- `PipeLibrary.root` keyed by `pipe_ref`
- `DomainLibrary.add_domain()` is idempotent for multi-bundle domain merging
- Duplicate concept detection across bundles in `_load_concepts_from_blueprints()`
- Duplicate pipe detection across bundles in `load_from_blueprints()`

---

## 3. LibraryCrate Model

### New file: `pipelex/libraries/library_crate.py`

```python
class LibraryCrate(BaseModel):
    """Complete library content as qualified blueprints, ready to load into a live Library.

    The crate is a flat, domain-agnostic snapshot of all concepts and pipes.
    Domain is encoded in the dictionary keys (e.g. 'scoring.WeightedScore',
    'scoring.compute_score'), not in a structural container.
    """

    concepts: dict[str, ConceptBlueprint] = Field(default_factory=dict)
    """concept_ref (domain.ConceptCode) -> ConceptBlueprint"""

    pipes: dict[str, PipeBlueprintUnion] = Field(default_factory=dict)
    """pipe_ref (domain.pipe_code) -> PipeBlueprintUnion"""

    fingerprint: str = ""
    """SHA-256 hex digest of the serialized concepts + pipes content."""
```

### Design decisions

- **Flat dicts, not nested by domain.** Domain is a namespace prefix in the key. No `DomainCrate` wrapper — merging is trivial.
- **Blueprints, not instantiated objects.** The crate holds `ConceptBlueprint` and `PipeBlueprintUnion` — the same types that come out of `PipelexBundleBlueprint`. No factory logic, no class registry interaction, no forward-reference resolution.
- **String-described concepts are normalized.** When a bundle declares `Concept1 = "Description"` (a `str` value in `PipelexBundleBlueprint.concept`), the factory converts it to `ConceptBlueprint(description="Description")` before inserting into the crate. The crate always holds `ConceptBlueprint`, never bare strings.
- **Fingerprint** is computed over the deterministic JSON serialization of `concepts` and `pipes` (excluding the fingerprint field itself). Enables downstream caching by content identity.
- **No source paths, no package provenance.** The crate is a pure content snapshot. Source tracking (`_pipe_source_map`, `loaded_mthds_paths`) remains in `LibraryManager`, outside the crate.
- **No domain metadata.** Domain `description` and `system_prompt` are NOT stored in the crate. They are passed separately via `domain_metadata` parameter to `load_from_crate()`. See Section 7.

---

## 4. LibraryCrateFactory

### New file: `pipelex/libraries/library_crate_factory.py`

```python
class LibraryCrateFactory:
    @classmethod
    def make_from_blueprints(
        cls,
        blueprints: list[PipelexBundleBlueprint],
    ) -> LibraryCrate:
        """Build a LibraryCrate from parsed bundle blueprints.

        For each bundle:
        1. Qualify concept codes with the bundle's domain → concept_ref keys
        2. Qualify pipe codes with the bundle's domain → pipe_ref keys
        3. Normalize string-described concepts to ConceptBlueprint
        4. Merge into flat dicts (same ref twice = error)
        5. Compute SHA-256 fingerprint
        """
```

### Algorithm

```
concepts: dict[str, ConceptBlueprint] = {}
pipes: dict[str, PipeBlueprintUnion] = {}

for each blueprint in blueprints:
    domain_code = blueprint.domain

    if blueprint.concept is not None:
        for concept_code, value in blueprint.concept.items():
            concept_ref = f"{domain_code}.{concept_code}"
            if concept_ref in concepts:
                raise LibraryCrateError(f"Concept '{concept_ref}' declared twice")
            if isinstance(value, str):
                concepts[concept_ref] = ConceptBlueprint(description=value)
            else:
                concepts[concept_ref] = value

    if blueprint.pipe is not None:
        for pipe_code, pipe_blueprint in blueprint.pipe.items():
            pipe_ref = f"{domain_code}.{pipe_code}"
            if pipe_ref in pipes:
                raise LibraryCrateError(f"Pipe '{pipe_ref}' declared twice")
            pipes[pipe_ref] = pipe_blueprint

fingerprint = _compute_fingerprint(concepts, pipes)
return LibraryCrate(concepts=concepts, pipes=pipes, fingerprint=fingerprint)
```

### Fingerprint computation

Use `model_dump_json()` for deterministic serialization with `sort_keys` to ensure order-independence. SHA-256 hex digest.

### New file: `pipelex/libraries/library_crate_exceptions.py`

```python
class LibraryCrateError(Exception):
    """Raised when building a LibraryCrate fails (e.g. ref collision)."""
```

---

## 5. LibraryManager.load_from_crate()

### New method on `LibraryManager` (`pipelex/libraries/library_manager.py`)

```python
def load_from_crate(
    self,
    library_id: str,
    crate: LibraryCrate,
    domain_metadata: dict[str, DomainBlueprint] | None = None,
) -> list[PipeAbstract]:
    """Load a LibraryCrate into a live Library.

    Args:
        library_id: The library to load into
        crate: The LibraryCrate containing qualified blueprints
        domain_metadata: Optional domain metadata (description, system_prompt)
            keyed by domain_code. When absent, domains get empty descriptions.
    """
```

### Algorithm

```
1. Extract unique domain codes from refs
   domain_codes = set()
   for ref in crate.concepts:
       parsed = QualifiedRef.parse_concept_ref(ref)
       domain_codes.add(parsed.domain_path)
   for ref in crate.pipes:
       parsed = QualifiedRef.parse_pipe_ref(ref)
       domain_codes.add(parsed.domain_path)

2. Create Domain objects
   for domain_code in domain_codes:
       if domain_metadata and domain_code in domain_metadata:
           domain = DomainFactory.make_from_blueprint(domain_metadata[domain_code])
       else:
           domain = Domain(code=domain_code, description="")
       library.domain_library.add_domain(domain)

3. Load concepts (topological ordering, forward refs, cycle detection)
   Build concept entries from crate.concepts (dict[concept_ref, ConceptBlueprint])
   instead of iterating over PipelexBundleBlueprint objects.

   For each concept_ref, concept_blueprint in crate.concepts.items():
       parsed = QualifiedRef.parse_concept_ref(concept_ref)
       domain_code = parsed.domain_path
       concept_code = parsed.local_code
       # Feed into topological sorter (same logic as _load_concepts_from_blueprints)

   Load in topological order via ConceptFactory.make_from_blueprint()
   library.concept_library.add_concepts(all_concepts)

4. Resolve forward references
   self._rebuild_models_with_forward_refs(all_concepts)

5. Detect concept cycles
   self._detect_concept_cycles(all_concepts)

6. Load pipes
   For each pipe_ref, pipe_blueprint in crate.pipes.items():
       parsed = QualifiedRef.parse_pipe_ref(pipe_ref)
       domain_code = parsed.domain_path
       pipe_code = parsed.local_code

       # Collect concept codes from same domain for validation
       concept_codes_for_domain = [
           QualifiedRef.parse_concept_ref(ref).local_code
           for ref in crate.concepts
           if ref.startswith(f"{domain_code}.")
       ]

       pipe = PipeFactory[PipeAbstract].make_from_blueprint(
           domain_code=domain_code,
           pipe_code=pipe_code,
           blueprint=pipe_blueprint,
           concept_codes_from_the_same_domain=concept_codes_for_domain,
       )
   library.pipe_library.add_pipes(all_pipes)

7. Validate
   library.validate_library()

8. Return all_pipes
```

### Also add abstract method

In `pipelex/libraries/library_manager_abstract.py`, add the `load_from_crate()` abstract method.

---

## 6. Refactor load_from_blueprints()

The existing `load_from_blueprints()` becomes a two-step delegation:

```python
def load_from_blueprints(
    self,
    library_id: str,
    blueprints: list[PipelexBundleBlueprint],
) -> list[PipeAbstract]:
    # Step 0: Load address-based dependencies (unchanged)
    self._load_address_based_dependencies(library_id=library_id, blueprints=blueprints)

    # Step 1: Build domain metadata from blueprints (first-write-wins per domain)
    domain_metadata: dict[str, DomainBlueprint] = {}
    for blueprint in blueprints:
        if blueprint.domain not in domain_metadata:
            domain_metadata[blueprint.domain] = DomainBlueprint(
                source=blueprint.source,
                code=blueprint.domain,
                description=blueprint.description or "",
                system_prompt=blueprint.system_prompt,
            )

    # Step 2: Build the crate
    crate = LibraryCrateFactory.make_from_blueprints(blueprints=blueprints)

    # Step 3: Load from crate
    return self.load_from_crate(
        library_id=library_id,
        crate=crate,
        domain_metadata=domain_metadata,
    )
```

**Callers do not change.** `pipeline_run_setup()`, `_load_mthds_files_into_library()`, and the dependency loading code all call `load_from_blueprints()` and continue to work as before.

**Note on `_pipe_source_map`**: The current `load_from_blueprints()` tracks which `.mthds` file each pipe came from. After refactoring, source tracking must be preserved. Two options:
- (a) Build the source map in the refactored `load_from_blueprints()` after `load_from_crate()` returns, by iterating blueprints and matching pipe_refs.
- (b) Pass source info as an additional parameter to `load_from_crate()`.

Option (a) is simpler and keeps the crate source-agnostic.

**`load_concepts_only_from_blueprints()`** can remain as-is for Phase 1 — it's used by LSP/validation tooling and doesn't need the crate abstraction yet.

---

## 7. system_prompt and Domain Metadata

The `PipelexBundleBlueprint.system_prompt` field flows into `Domain.system_prompt` and is used as a fallback system prompt for PipeLLM pipes. There's already a TODO comment in `domain_library.py` (line 35-36) about inlining this at pipe factory time.

**For this phase:**
- Domain metadata (`description`, `system_prompt`) is NOT stored in the crate.
- Domain metadata is passed as a separate `domain_metadata` parameter to `load_from_crate()`.
- When `load_from_blueprints()` calls `load_from_crate()`, it extracts domain metadata from the blueprints and passes it along.
- The existing `DomainLibrary.add_domain()` first-write-wins behavior is preserved.

This keeps the crate focused on content. Inlining `system_prompt` into pipe blueprints is a separate optimization.

---

## 8. File Summary

| File | Action | Description |
|------|--------|-------------|
| `pipelex/libraries/library_crate.py` | **New** | `LibraryCrate` model |
| `pipelex/libraries/library_crate_factory.py` | **New** | `LibraryCrateFactory.make_from_blueprints()`, fingerprint |
| `pipelex/libraries/library_crate_exceptions.py` | **New** | `LibraryCrateError` exception |
| `pipelex/libraries/library_manager.py` | **Modify** | Add `load_from_crate()`, refactor `load_from_blueprints()` |
| `pipelex/libraries/library_manager_abstract.py` | **Modify** | Add `load_from_crate()` abstract method |
| `tests/unit/pipelex/libraries/test_library_crate.py` | **New** | Unit tests for model and factory |
| `tests/unit/pipelex/libraries/test_library_crate_data.py` | **New** | Test data |
| `tests/integration/pipelex/libraries/test_load_from_crate.py` | **New** | Integration: crate ↔ blueprints equivalence |

---

## 9. Test Plan

### Unit tests: `tests/unit/pipelex/libraries/test_library_crate.py`

One `TestLibraryCrate` class:

1. **JSON round-trip** — Create `LibraryCrate` with sample data, serialize to JSON, deserialize, assert equality.
2. **make_from_blueprints merges correctly** — Two blueprints for the same domain with different concepts and pipes. Assert all entries present with qualified refs.
3. **make_from_blueprints merges across domains** — Two blueprints with different domains. Assert refs qualified with respective domains.
4. **String concept normalization** — Blueprint with `concept = {"MyConcept": "A description"}`. Assert crate contains `ConceptBlueprint(description="A description")`.
5. **Concept collision raises** — Two blueprints declaring same `domain.ConceptCode`. Assert `LibraryCrateError`.
6. **Pipe collision raises** — Two blueprints declaring same `domain.pipe_code`. Assert `LibraryCrateError`.
7. **Fingerprint determinism** — Same blueprints → same fingerprint. Different blueprints → different fingerprint.
8. **Empty blueprints** — Blueprint with no concepts and no pipes. Assert empty dicts and valid fingerprint.

### Integration test: `tests/integration/pipelex/libraries/test_load_from_crate.py`

One `TestLoadFromCrate` class:

1. **Equivalence test** — Load `.mthds` files via `load_from_blueprints()`. Separately build a crate from the same blueprints, call `load_from_crate()`. Assert both libraries contain the same concept_refs, pipe_refs, and domain codes.

### Regression

- All existing tests pass: `make agent-test`
- All linting passes: `make agent-check`

---

## 10. Implementation Sequence

1. **Create `LibraryCrate` model** (`library_crate.py`). Pure data model. Write JSON round-trip test first (TDD).
2. **Create `LibraryCrateFactory`** (`library_crate_factory.py`). Implement `make_from_blueprints()` with string normalization, collision detection, fingerprint. Write unit tests.
3. **Add `load_from_crate()`** to `LibraryManager`. Port concept-loading logic (topological sort, forward refs, cycle detection) and pipe-loading logic to work with flat crate dicts.
4. **Refactor `load_from_blueprints()`** to delegate through the crate. Extract domain metadata, build crate, call `load_from_crate()`.
5. **Run `make agent-check` and `make agent-test`**. Fix regressions.
6. **Write integration equivalence test**.

---

## 11. Risks and Edge Cases

### String-described concepts
`PipelexBundleBlueprint.concept` values can be `ConceptBlueprint | str`. The factory normalizes `str` to `ConceptBlueprint(description=value)`. This must match what `ConceptFactory.make_from_blueprint()` expects.

### Cross-package dependencies
`load_from_blueprints()` calls `_load_address_based_dependencies()` before building the crate. These dependencies load into child libraries via separate code paths. This phase does NOT route dependency loading through a crate. The crate only covers the "main" blueprints.

### load_concepts_only_from_blueprints()
This lightweight variant (LSP/validation) loads only domains and concepts. It can remain as-is for this phase.

### Ref parsing for multi-segment domains
Use `QualifiedRef.parse_concept_ref()` and `QualifiedRef.parse_pipe_ref()` (`pipelex/core/qualified_ref.py`) for correct splitting. These use `rsplit(".", 1)` which handles multi-segment domains like `legal.contracts.NonCompeteClause` correctly.

### None concept/pipe dicts
`PipelexBundleBlueprint.concept` and `.pipe` can be `None`. The factory must guard with `if blueprint.concept is not None:`.

---

## 12. Key Existing Code to Reuse

| What | Where |
|------|-------|
| `PipeFactory[PipeAbstract].make_from_blueprint()` | `pipelex/core/pipes/pipe_factory.py` |
| `ConceptFactory.make_from_blueprint()` | `pipelex/core/concepts/concept_factory.py` |
| `DomainFactory.make_from_blueprint()` | `pipelex/core/domains/domain_factory.py` |
| `QualifiedRef.parse_concept_ref()` / `parse_pipe_ref()` | `pipelex/core/qualified_ref.py` |
| `_load_concepts_from_blueprints()` (topological sort logic) | `pipelex/libraries/library_manager.py:472` |
| `_rebuild_models_with_forward_refs()` | `pipelex/libraries/library_manager.py` |
| `_detect_concept_cycles()` | `pipelex/libraries/library_manager.py` |
| `library.validate_library()` | `pipelex/libraries/library.py` |
| `DomainLibrary.add_domain()` (idempotent) | `pipelex/libraries/domain/domain_library.py` |
