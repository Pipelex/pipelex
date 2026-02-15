# MTHDS Standard — Implementation Brief (v6)

## Context

Read these two design documents first:
- Latest `pipelex-package-system-design_v*.md` — The MTHDS standard specification
- Latest `pipelex-package-system-changes_v*.md` — The evolution plan from current Pipelex

**MTHDS** is the new name for the open standard. **Pipelex** remains the reference implementation. Internal Pipelex class names (e.g., `PipelexBundleBlueprint`, `PipelexInterpreter`) do NOT rename — Pipelex is the implementation brand.

---

## Phase 0: Extension Rename — COMPLETED

File extension renamed from `.plx` to `.mthds` across the entire codebase. User-facing terminology updated from "workflow" to "method". Hard switch, no backward-compatible `.plx` loading.

---

## Phase 1: Hierarchical Domains + Pipe Namespacing — COMPLETED

Delivered:
- **Hierarchical domain validation**: domain codes accept dotted paths (e.g., `legal.contracts.shareholder`). Updated domain validation in `pipelex/core/domains/`.
- **Unified `QualifiedRef` model**: a single frozen Pydantic `BaseModel` in `pipelex/core/qualified_ref.py` that handles both concept and pipe references (fields: `domain_path: str | None`, `local_code: str`). This replaced the brief's suggestion of a separate `PipeReference` class in `pipelex/core/pipes/` — the unified model eliminates duplication since concept and pipe references share the same parsing logic (split-on-last-dot, casing disambiguates). The `package_alias` field is omitted since cross-package references are Phase 3; adding it later is trivial.
- **Split-on-last-dot parsing**: unified parsing rule for both concept and pipe references — the last segment is the `local_code` (casing disambiguates pipe vs. concept), everything before it is the `domain_path`.
- **Bundle blueprint validation**: domain-qualified pipe references are validated against known domains and pipes within the current package, mirroring the existing concept reference validation pattern.
- **Builder bundles migrated**: cross-domain pipe references in the builder's internal bundles (`agentic_builder.mthds`, `builder.mthds`) now use `domain.pipe_code` syntax.
- **New tests**: positive tests for domain-qualified pipe references in sequences, and negative tests for references to non-existent domains/pipes.

---

## Phase 2: Package Manifest + Exports / Visibility — COMPLETED

Delivered:

- **`MthdsPackageManifest` data model** (`pipelex/core/packages/manifest.py`): `PackageDependency`, `DomainExports`, and `MthdsPackageManifest` Pydantic models with field validators (address hostname pattern, semver for package version, version constraint ranges for dependency versions using Poetry/uv-style syntax, non-empty description, snake_case aliases, unique aliases, valid domain paths, valid pipe codes). The `[dependencies]` format uses the alias as the TOML key and the address as an inline field — this is more natural for the `->` syntax since the alias is the lookup key when resolving cross-package references.
- **TOML parsing and serialization** (`pipelex/core/packages/manifest_parser.py`): `parse_methods_toml()` with recursive sub-table walk for `[exports]` domain path reconstruction; `serialize_manifest_to_toml()` using `tomlkit` for human-readable output.
- **Custom exceptions** (`pipelex/core/packages/exceptions.py`): `ManifestError`, `ManifestParseError`, `ManifestValidationError`.
- **Manifest discovery** (`pipelex/core/packages/discovery.py`): `find_package_manifest()` walks up from a bundle path, stopping at `METHODS.toml`, `.git/` boundary, or filesystem root. Returns `None` for standalone bundles.
- **Visibility checker** (`pipelex/core/packages/visibility.py`): `PackageVisibilityChecker` enforces cross-domain pipe visibility against `[exports]`. Rules: no manifest = all public; bare ref = allowed; same-domain = allowed; cross-domain requires pipe to be in `[exports]` or be `main_pipe` (auto-exported). Error messages include `[exports]` hint.
- **Cross-package `->` reference detection**: `QualifiedRef.has_cross_package_prefix()` and `split_cross_package_ref()` static methods. `PackageVisibilityChecker.validate_cross_package_references()` emits warnings for known aliases, errors for unknown aliases.
- **Visibility wired into bundle loading** (`pipelex/libraries/library_manager.py`): `_check_package_visibility()` runs after blueprint parsing, before `load_from_blueprints`. Raises `LibraryLoadingError` on violations.
- **CLI commands** (`pipelex/cli/commands/pkg/`): `pipelex pkg init` scans `.mthds` files, generates skeleton `METHODS.toml` with auto-discovered domains and all pipes exported. `pipelex pkg list` finds and displays the manifest with Rich tables (package info, dependencies, exports).
- **Builder awareness** (`pipelex/builder/builder_loop.py`): `maybe_generate_manifest_for_output()` checks if an output directory contains multiple domains and generates a `METHODS.toml` if so. Hooked into both `pipe_cmd.py` and `build_core.py`.
- **Physical test data** (`tests/data/packages/`): `legal_tools/` (full manifest + multi-domain bundles), `minimal_package/` (minimal manifest), `standalone_bundle/` (no manifest), `invalid_manifests/` (6 negative test files).
- **Comprehensive tests**: 55+ new tests across 7 test files covering manifest model validation, TOML parsing, discovery, visibility, cross-package refs, CLI commands, and builder manifest generation. All domain/pipe names prefixed with `pkg_test_` to avoid collisions with the existing e2e test suite.

---

## Phase 3: Cross-Package References + Local Dependency Resolution — COMPLETED

Delivered:

- **`path` field on `PackageDependency`** (`pipelex/core/packages/manifest.py`): Dependencies can now declare a local filesystem path (`path = "../scoring-lib"`) for development-time dependency resolution, similar to Cargo's `path` deps or Go's `replace` directives. The field is optional and forward-compatible with Phase 4's remote fetch.
- **Cross-package concept validation** (`pipelex/core/concepts/validation.py`): `is_concept_ref_valid()` and `is_concept_ref_or_code_valid()` now accept `->` refs by stripping the alias prefix before validating the remainder.
- **Bundle-level validation skip for `->` refs** (`pipelex/core/bundles/pipelex_bundle_blueprint.py`): Both `validate_local_concept_references()` and `validate_local_pipe_references()` explicitly skip `->` refs with a `QualifiedRef.has_cross_package_prefix()` check. Previously these were skipped by accident (the `->` in the domain path didn't match any known domain); the explicit check is cleaner and prevents edge cases.
- **ConceptFactory cross-package handling** (`pipelex/core/concepts/concept_factory.py`): `make_domain_and_concept_code_from_concept_ref_or_code()` handles `->` refs, producing aliased domain codes like `"scoring_lib->scoring"` so that `make_concept_ref_with_domain()` reconstructs `"scoring_lib->scoring.WeightedScore"` — the key used for lookup in ConceptLibrary. `make_refine()` passes through cross-package refs unchanged.
- **Cross-package pipe lookup** (`pipelex/libraries/pipe/pipe_library.py`): `get_optional_pipe()` resolves `alias->domain.pipe_code` to `alias->pipe_code` via dict lookup. New `add_dependency_pipe(alias, pipe)` method stores dependency pipes with key `alias->pipe.code`.
- **Cross-package concept lookup** (`pipelex/libraries/concept/concept_library.py`): `get_required_concept()` handles `->` refs via direct dict lookup, bypassing format validation. New `add_dependency_concept(alias, concept)` method stores with key `alias->concept.concept_ref`.
- **Dependency resolver** (`pipelex/core/packages/dependency_resolver.py`): New module. `resolve_local_dependencies()` resolves dependencies that have a local `path` field: resolves the path relative to package root, finds `METHODS.toml` in the dependency (optional — standalone bundles work), scans for `.mthds` files, determines exported pipes from manifest exports + `main_pipe` auto-export.
- **Dependency loading in LibraryManager** (`pipelex/libraries/library_manager.py`): New `_load_dependency_packages()` method integrated into `_load_mthds_files_into_library()`. For each resolved dependency: parses blueprints, loads concepts with aliased keys (`alias->concept_ref`) and native keys (for internal resolution, skip on conflict), loads only exported pipes with aliased keys (`alias->pipe_code`).
- **Cross-package validation wired into runtime** (`pipelex/core/packages/visibility.py`): `check_visibility_for_blueprints()` now also calls `validate_cross_package_references()`. Known aliases produce info-level logs (no error); unknown aliases produce errors.
- **Graceful handling of unresolved cross-package refs**: Three layers of safety for pipes that reference cross-package deps not loaded in the current context:
  - `library.py`: skips validation for pipe controllers with unresolved cross-package dependencies
  - `pipe_sequence.py`: `needed_inputs()` uses `get_optional_pipe` for `->` refs and skips if None; `validate_output_with_library()` skips if last step is unresolved
  - `dry_run.py`: catches `PipeNotFoundError` and treats it as a graceful skip (SUCCESS with info message)
- **CLI `pipelex pkg add`** (`pipelex/cli/commands/pkg/add_cmd.py`): Adds a dependency to `METHODS.toml`. Options: `address` (required), `--alias` (auto-derived from address if omitted), `--version` (required), `--path` (optional local path). Validates alias uniqueness, serializes manifest back.
- **Test fixtures** (`tests/data/packages/`): `scoring_dep/` (dependency package with exports) and `consumer_package/` (consumer with cross-package `->` refs and `path` dependency).
- **Comprehensive tests**: 40+ new tests across 6 test files covering dependency resolution, cross-package loading/lookup, concept validation, integration loading, CLI `pkg add`, and updated cross-package ref validation.

---

## Phase 4A: Semver Constraint Evaluation Engine — COMPLETED

- `pipelex/tools/misc/semver.py`: Typed wrapper around `semantic_version` providing `parse_version` (with `v`-prefix stripping for git tags), `parse_constraint`, `version_satisfies`, `parse_version_tag`, and Go-style Minimum Version Selection via `select_minimum_version` (single constraint) and `select_minimum_version_for_multiple_constraints` (transitive case).
- `SemVerError` exception for parse failures.
- Supports all constraint operators: `^`, `~`, `>=`, `>`, `<=`, `<`, `==`, `!=`, `*`, wildcards, compound (`>=1.0.0,<2.0.0`).
- New dependency: `semantic-version>=2.10.0` in `pyproject.toml`.
- 58 parametrized unit tests in `tests/unit/pipelex/tools/misc/test_semver.py`.

---

## Phase 4B: VCS Fetch + Package Cache — COMPLETED

Delivered:

- **VCS resolver** (`pipelex/core/packages/vcs_resolver.py`): `address_to_clone_url()` maps package addresses to HTTPS clone URLs (appends `.git`). `list_remote_version_tags()` runs `git ls-remote --tags`, parses output through `parse_version_tag`, skips dereferenced `^{}` entries. `resolve_version_from_tags()` applies MVS via `select_minimum_version` from Phase 4A. `clone_at_version()` does a shallow clone (`--depth 1 --branch <tag>`) into a destination directory. All git subprocess calls have timeouts and convert errors to typed exceptions.
- **Package cache** (`pipelex/core/packages/package_cache.py`): Cache layout `~/.mthds/packages/{address}/{version}/`. `get_cached_package_path()` computes paths, `is_cached()` checks existence + non-emptiness, `store_in_cache()` uses staging directory + atomic rename and strips `.git/` from cached copies, `remove_cached_package()` for cleanup. All functions accept a `cache_root` override for testability.
- **New exceptions** in `exceptions.py`: `VCSFetchError`, `VersionResolutionError`, `PackageCacheError` — all inheriting from `PipelexError`.
- **Dependency resolver extended** (`dependency_resolver.py`): New `resolve_remote_dependency()` orchestrating clone URL → tag listing → MVS selection → cache check → clone if miss → `ResolvedDependency`. New `resolve_all_dependencies()` unifying local path (Phase 3) + remote VCS resolution. Refactored existing local resolution into `_resolve_local_dependency()` for reuse. `fetch_url_overrides` parameter enables test fixtures to substitute `file://` URLs.
- **Library manager updated** (`library_manager.py`): `_load_dependency_packages()` now calls `resolve_all_dependencies()` instead of `resolve_local_dependencies()`, enabling remote deps to be loaded transparently alongside local path deps.
- **Layer 3 test fixtures** (`tests/integration/pipelex/core/packages/conftest.py`): `bare_git_repo` fixture creates a temporary bare git repo with two tagged versions (v1.0.0, v1.1.0) containing METHODS.toml and .mthds bundles, accessible via `file://` protocol — no network I/O required. Test data constants in `test_vcs_data.py`.
- **Unit tests** (`tests/unit/pipelex/core/packages/`): 6 tests for `address_to_clone_url`, `resolve_version_from_tags` (MVS selection, no-match, empty tags). 7 tests for package cache (path layout, store/retrieve, `.git` removal, content preservation, remove).
- **Integration tests** (`tests/integration/pipelex/core/packages/test_vcs_resolver_integration.py`): 7 tests covering tag listing, clone at version, MVS selection via `resolve_remote_dependency`, higher constraint, no-match error, cache hit on second resolve, and mixed local + remote resolution via `resolve_all_dependencies`.

---

## Phase 4C: Lock File — COMPLETED

Delivered:

- **Lock file model and parser** (`pipelex/core/packages/lock_file.py`): `LockedPackage` frozen model (version validated with `is_valid_semver`, SHA-256 hash validated with regex, source validated with `https://` prefix), `LockFile` frozen model with `dict[str, LockedPackage]` keyed by package address. TOML parse/serialize using `tomli` + `tomlkit`, with deterministic sorted output. Format per design spec:
  ```toml
  ["github.com/mthds/scoring-lib"]
  version = "0.5.1"
  hash = "sha256:e5f6g7h8..."
  source = "https://github.com/mthds/scoring-lib"
  ```
- **Hash computation** (`compute_directory_hash()`): Deterministic SHA-256 of directory contents — collects all regular files recursively, skips `.git/` paths, sorts by POSIX-normalized relative path, feeds relative path string (UTF-8) + raw bytes into a single hasher. Binary-mode reads only.
- **Lock file generation** (`generate_lock_file()`): Standalone function taking `MthdsPackageManifest` + `list[ResolvedDependency]` — filters out local deps (those with `path` set), computes hash from `package_root` for each remote dep. `dependency_resolver.py` intentionally unchanged; the caller (future CLI in Phase 4D) chains: resolve -> generate lock -> write to disk.
- **Integrity verification** (`verify_locked_package()`, `verify_lock_file()`): Computes hash of cached directory via `get_cached_package_path()`, compares with lock entry hash, raises `IntegrityError` on mismatch or missing cache.
- **Lock file exceptions** in `exceptions.py`: `LockFileError`, `IntegrityError` — both inheriting from `PipelexError`.
- **18 unit tests** in `tests/unit/pipelex/core/packages/test_lock_file.py`: Single `TestLockFile` class covering parsing (2-entry TOML, empty, invalid TOML, invalid hash), serialization (structure, roundtrip, deterministic order), hash computation (deterministic, content-sensitive, path-sensitive, `.git/` exclusion, nonexistent dir), verification (success, mismatch, missing cache), generation (remote-only filtering, empty with no remote deps), and model immutability.

---

## Phase 4D: Transitive Dependencies + CLI Commands — COMPLETED

Delivered:

- **Exception infrastructure** (`pipelex/core/packages/exceptions.py`): `DependencyResolveError` moved from `dependency_resolver.py` (was plain `Exception`, now inherits `PipelexError`). New `TransitiveDependencyError(PipelexError)` for cycles and unsatisfiable diamond constraints. All import sites updated (`library_manager.py`, unit tests, integration tests).
- **`address` field on `ResolvedDependency`** (`dependency_resolver.py`): Tracks the package address through resolution, enabling lock file generation for transitive deps without requiring them to exist in the root manifest. All construction sites updated: `_resolve_local_dependency()`, `resolve_remote_dependency()`, `_build_resolved_from_dir()`, `resolve_local_dependencies()`, plus test files.
- **Transitive resolution algorithm** (`dependency_resolver.py`): `_resolve_transitive_tree()` implements DFS with a stack set for cycle detection. Per dependency: cycle check → constraint tracking → dedup check (existing version satisfies new constraint?) → diamond re-resolution if needed → normal resolve → recurse into sub-deps. `_resolve_with_multiple_constraints()` handles diamond dependencies by fetching/caching the tag list, parsing all constraints, and calling `select_minimum_version_for_multiple_constraints()` from Phase 4A. `resolve_all_dependencies()` refactored: resolves local path deps first (no recursion), then passes remote deps through the transitive tree walker.
- **Lock file generation updated** (`lock_file.py`): `generate_lock_file()` refactored to use `resolved.address` directly instead of alias-based lookup against root manifest. This naturally includes transitive deps while still excluding local path overrides. Backward-compatible: direct remote deps still lock identically.
- **CLI `pipelex pkg lock`** (`pipelex/cli/commands/pkg/lock_cmd.py`): Parses `METHODS.toml`, calls `resolve_all_dependencies()` (now with transitive), generates lock file, writes `methods.lock`. Reports package count.
- **CLI `pipelex pkg install`** (`pipelex/cli/commands/pkg/install_cmd.py`): Reads `methods.lock`, fetches missing packages via `resolve_remote_dependency()` with exact version constraint, verifies integrity via `verify_lock_file()`. Reports fetched/cached counts.
- **CLI `pipelex pkg update`** (`pipelex/cli/commands/pkg/update_cmd.py`): Fresh resolve ignoring existing lock, generates new lock file, displays diff (added/removed/updated packages) via `_display_lock_diff()`.
- **6 unit tests** for transitive resolution (`tests/unit/pipelex/core/packages/test_transitive_resolver.py`): linear chain (A→B→C), cycle detection (A→B→A), diamond resolved (compatible constraints), diamond unsatisfiable (conflicting constraints), local deps not recursed, dedup same address.
- **2 integration tests** (`tests/integration/pipelex/core/packages/test_transitive_integration.py`): transitive chain resolves using local bare git repos (`dependent-pkg` → `vcs-fixture`), lock file includes both direct and transitive addresses. New `bare_git_repo_dependent` fixture and `DependentFixtureData` constants.
- **7 CLI command tests** (`tests/unit/pipelex/cli/`): `test_pkg_lock.py` (3 tests: no manifest exits, creates empty lock, local dep excluded), `test_pkg_install.py` (2 tests: no lock exits, empty lock succeeds), `test_pkg_update.py` (2 tests: no manifest exits, creates fresh lock).

---

## Phase 4E: Per-Package Library Isolation + Concept Refinement — COMPLETED

Delivered:

- **Per-package Library instances** (`pipelex/libraries/library.py`): Each dependency package gets its own isolated `Library` instance held in `Library.dependency_libraries: dict[str, Library]` (alias → child library). `get_dependency_library(alias)` retrieves child libraries. `resolve_concept(concept_ref)` routes `alias->domain.Code` lookups through the child library by splitting on `->`, resolving the alias to the child, then looking up the local key. `validate_concept_library_with_libraries()` validates cross-package refines targets exist after all dependencies are loaded. `teardown()` cleans up child libraries. This eliminates the previous flat-namespace workaround where concepts were registered with both aliased keys and native keys (with skip-on-conflict for name collisions).
- **Per-package loading in LibraryManager** (`pipelex/libraries/library_manager.py`): `_load_single_dependency()` creates a child `Library` per dependency. Domains, concepts, and exported pipes are loaded into the child library in isolation. Temporary concept registration in the main library during pipe construction (needed for pipe validation), then removed. Aliased entries (`alias->concept_ref`, `alias->pipe_code`) added to the main library for backward-compatible cross-package lookups. Calls `library.concept_library.set_concept_resolver(library.resolve_concept)` after all dependency loading completes.
- **Cross-package concept refinement validation** (`pipelex/core/concepts/concept.py`): `are_concept_compatible()` gains a `concept_resolver: Callable[[str], Concept | None] | None` parameter. Cross-package refines (`alias->domain.Concept`) are resolved through the resolver callback before compatibility comparison. Handles sibling concepts (both refining the same cross-package concept) by comparing resolved refines by `concept_ref`.
- **ConceptLibrary resolver wiring** (`pipelex/libraries/concept/concept_library.py`): `_concept_resolver` field stores the resolver callback. `set_concept_resolver(resolver)` wires it after dependency loading. `is_compatible()` passes the resolver to `are_concept_compatible()`. `validation_static` skips cross-package refines (validated later via `validate_concept_library_with_libraries()`).
- **ConceptFactory cross-package refines** (`pipelex/core/concepts/concept_factory.py`): `_handle_refines()` detects cross-package refines via `QualifiedRef.has_cross_package_prefix()`. For cross-package refines, generates a standalone `TextContent` subclass (base class not available locally). Refinement relationship tracked in `concept.refines` field for runtime validation.
- **Builder package-awareness** (`pipelex/builder/builder_loop.py`): `_fix_undeclared_concept_references()` skips cross-package refs when collecting undeclared concepts. `_prune_unreachable_specs()` skips cross-package refs when collecting local concept refs. New `_extract_local_bare_code()` helper returns `None` for cross-package refs, used by `_collect_concept_refs_from_pipe_spec()` and `_collect_concept_refs_from_concept_spec()`. Ensures fix/prune operations only operate on local concepts, not dependency concepts.
- **Physical test data** (`tests/data/packages/`): `analytics_dep/` (second dependency with same concept code as `scoring_dep` for collision testing), `multi_dep_consumer/` (consumer depending on both scoring and analytics deps), `refining_consumer/` (consumer with concept refining a cross-package concept).
- **Comprehensive tests**: 30 tests across 4 test files covering library isolation (child registration, retrieval, concept isolation, cross-package lookups, name collision with two deps, teardown), cross-package concept refinement (resolver-based compatibility, sibling concepts, local refines unaffected), concept validation (skip cross-package refines in static validation, catch missing targets, pass with loaded deps), and integration loading (end-to-end with isolated deps, cross-package pipe lookups, collision prevention, refinement chains, resolver wiring).

---

## Phase 5: Local Package Discovery + Know-How Graph — COMPLETED

Scoped to **local-first** (no registry server). A future phase layers a hosted registry on top. Sub-phases:

### Phase 5A: Package Index Model + Index Builder — COMPLETED

Delivered:

- **Index data models** (`pipelex/core/packages/index/models.py`): Frozen Pydantic models for indexing packages at the blueprint level (no runtime class loading, no side effects). `PipeSignature` stores pipe code, type, domain, description, input/output specs as strings, and export status. `ConceptEntry` stores concept code, domain, concept_ref, description, refines chain, and structure field names. `DomainEntry` stores domain code and description. `PackageIndexEntry` stores full package metadata (address, version, description, authors, license) plus lists of domains, concepts, pipes, and dependency addresses. `PackageIndex` is a mutable collection keyed by address with `add_entry()`, `get_entry()`, `remove_entry()`, `all_concepts()`, `all_pipes()`.
- **Index builder** (`pipelex/core/packages/index/index_builder.py`): `build_index_entry_from_package(package_root)` parses `METHODS.toml` for metadata and scans `.mthds` files via `PipelexInterpreter.make_pipelex_bundle_blueprint()` to extract pipe signatures, concept entries, and domain info — all at string level. Determines export status from manifest `[exports]` + `main_pipe` auto-export. `build_index_from_cache(cache_root)` discovers all cached packages by recursively scanning for `METHODS.toml` files. `build_index_from_project(project_root)` indexes the current project plus its local and cached dependencies.
- **Public utility functions**: `collect_mthds_files()` and `determine_exported_pipes()` in `dependency_resolver.py` made public (removed `_` prefix) for reuse by the index builder.
- **`IndexBuildError`** exception in `exceptions.py`.
- **34 tests** across 2 test files: `test_index_models.py` (15 tests: model construction, immutability, add/get/remove/replace on PackageIndex, all_concepts/all_pipes aggregation) and `test_index_builder.py` (19 tests: build from legal_tools/scoring_dep/minimal_package/refining_consumer, domain/concept/pipe extraction, input/output specs, export status, main_pipe auto-export, concept refines, dependency aliases population, error cases, cache scanning, project indexing).

### Phase 5B: Know-How Graph Model + Query Engine — COMPLETED

Delivered:

- **Pre-requisite: `dependency_aliases` on `PackageIndexEntry`** (`pipelex/core/packages/index/models.py`): Added `dependency_aliases: dict[str, str]` field mapping dependency alias to address. Builder populates it from `manifest.dependencies`. Required for graph builder to resolve cross-package `refines` strings like `"scoring_dep->pkg_test_scoring_dep.PkgTestWeightedScore"`.
- **`GraphBuildError`** exception in `exceptions.py`.
- **Graph data models** (`pipelex/core/packages/graph/models.py`): `ConceptId` (frozen, `package_address` + `concept_ref`, with `node_key`, `concept_code`, `is_native` properties), `EdgeKind` (StrEnum: `DATA_FLOW`, `REFINEMENT`), `PipeNode` (frozen, resolved input/output `ConceptId`s), `ConceptNode` (frozen, with optional `refines: ConceptId`), `GraphEdge` (frozen, discriminated by `EdgeKind`), `KnowHowGraph` (mutable container with pipe/concept nodes, data flow/refinement edges, lookup methods). `NATIVE_PACKAGE_ADDRESS = "__native__"` for native concepts.
- **Graph builder** (`pipelex/core/packages/graph/graph_builder.py`): `build_know_how_graph(index: PackageIndex) -> KnowHowGraph` in 5 steps: (1) build concept nodes + package-scoped lookup table, (2) build native concept nodes for all `NativeConceptCode` values, (3) resolve `refines` targets (cross-package via `dependency_aliases`, local by code/ref lookup), (4) build pipe nodes with resolved input/output `ConceptId`s (native detection via `NativeConceptCode.is_native_concept_ref_or_code()`), (5) build refinement edges, (6) build data flow edges using reverse index + refinement ancestry walk for compatibility.
- **Query engine** (`pipelex/core/packages/graph/query_engine.py`): `KnowHowQueryEngine(graph)` with: `query_what_can_i_do(concept_id)` finds pipes accepting a concept (walks refinement chain for compatibility), `query_what_produces(concept_id)` finds pipes producing a concept (including refinements), `check_compatibility(source_pipe_key, target_pipe_key)` returns compatible input param names, `resolve_refinement_chain(concept_id)` walks up refines links with cycle detection, `query_i_have_i_need(input_id, output_id, max_depth=3)` BFS for multi-step pipe chains. Shared `_concepts_are_compatible()` helper for refinement-aware concept matching.
- **Package isolation**: Same concept code in different packages (e.g., `PkgTestWeightedScore` in `scoring-lib` vs `analytics-lib`) produces distinct `ConceptId`s scoped by `package_address`, preventing cross-package collisions.
- **47 tests** across 3 test files + shared test data: `test_graph_models.py` (17 tests: ConceptId key/frozen/native/equality, PipeNode key/frozen, ConceptNode with/without refines, GraphEdge fields, EdgeKind enum, KnowHowGraph lookups/outgoing/incoming), `test_graph_builder.py` (13 tests: concept/native/pipe node creation, output/input concept resolution, refinement edge creation, cross-package refines resolution, data flow edges exact/native/refinement, no self-loops, no cross-package collision, empty index), `test_query_engine.py` (17 tests: what_can_i_do with native/specific/refined concepts, what_produces with text/specific/base-includes-refinements, check_compatibility match/refinement/incompatible/no-collision, resolve_refinement_chain with/without refines, i_have_i_need direct/two-step/no-path/max-depth/sorted). Test data in `test_data.py` builds a 4-package index with scoring-lib, refining-app (cross-package refinement), legal-tools, and analytics-lib (same concept code collision test).

### Phase 5C: CLI Commands (index, search, inspect, graph) — COMPLETED

Delivered:

- **`pipelex pkg index [--cache]`** (`pipelex/cli/commands/pkg/index_cmd.py`): Builds and displays a Rich table of all indexed packages (Address, Version, Description, Domains/Concepts/Pipes counts). `--cache` flag indexes cached packages instead of the current project. Uses `build_index_from_project()` or `build_index_from_cache()` from Phase 5A. Exits 1 with yellow warning if no packages found.
- **`pipelex pkg search <query> [--domain] [--concept] [--pipe] [--cache]`** (`pipelex/cli/commands/pkg/search_cmd.py`): Case-insensitive substring search across concept codes/descriptions/refs and pipe codes/descriptions/output specs. `--domain` filters to a specific domain. `--concept` / `--pipe` flags restrict output to concepts-only or pipes-only. Displays matching concepts and pipes in separate Rich tables. No-results prints a yellow informational message (no exit 1). Exits 1 only if no packages exist to search.
- **`pipelex pkg inspect <address> [--cache]`** (`pipelex/cli/commands/pkg/inspect_cmd.py`): Detailed view of a single package with 4 Rich tables: Package Info (field/value pairs including authors, license, dependencies), Domains (code + description), Concepts (code, domain, description, refines, structure fields), Pipe Signatures (code, type, domain, description, inputs, output, exported status). Unknown address prints available addresses as hint and exits 1.
- **`pipelex pkg graph [--from] [--to] [--check] [--max-depth] [--cache]`** (`pipelex/cli/commands/pkg/graph_cmd.py`): Know-how graph queries with 4 modes: `--from` calls `query_what_can_i_do()` (pipes accepting a concept), `--to` calls `query_what_produces()` (pipes producing a concept), `--from` + `--to` together calls `query_i_have_i_need()` (BFS pipe chains), `--check` calls `check_compatibility()` (pipe output→input compatibility). ConceptId parsing via `_parse_concept_id()` splits on `::` (e.g. `__native__::native.Text`). Exits 1 if no options given or on invalid concept format.
- **Command registration** (`pipelex/cli/commands/pkg/app.py`): 4 new commands registered with `Annotated` type hints following the existing pattern of the 6 prior `pkg` commands.
- **17 tests** across 4 test files: `test_pkg_index.py` (3 tests: project with manifest, empty project exits, empty cache exits via monkeypatch), `test_pkg_search.py` (5 tests: find concept, find pipe, no results, domain filter, empty project exits), `test_pkg_inspect.py` (3 tests: existing package, unknown address exits, empty project exits), `test_pkg_graph.py` (6 tests: no options exits, `--from` finds pipes, `--to` finds pipes, `--check` compatible, `--check` incompatible, invalid concept format exits). Graph tests monkeypatch `build_index_from_project` to return `make_test_package_index()` from Phase 5B's test data.

### Phase 5D: Package Publish Validation — COMPLETED

- **`pipelex pkg publish [--tag]`** (`pipelex/cli/commands/pkg/publish_cmd.py`): Validates package readiness for distribution with 15 checks across 7 categories (manifest, bundle, export, visibility, dependency, lock_file, git). Displays errors (red) and warnings (yellow) as Rich tables with suggestions. Exits 1 on errors. `--tag` creates local git tag `v{version}` on success.
- **Core validation** (`pipelex/core/packages/publish_validation.py`): `IssueLevel` and `IssueCategory` StrEnums, `PublishValidationIssue` and `PublishValidationResult` frozen models, `validate_for_publish()` orchestrator with `check_git` flag for test isolation. Reuses `parse_methods_toml()`, `collect_mthds_files()`, `scan_bundles_for_domain_info()`, `check_visibility_for_blueprints()`, `parse_lock_file()`.
- **`PublishValidationError`** added to `pipelex/core/packages/exceptions.py`.
- **14 tests** across 2 test files: `test_publish_validation.py` (10 tests: valid package, no manifest, no bundles, missing authors/license warnings, phantom export, lock file missing/not required, wildcard version, git checks disabled) and `test_pkg_publish.py` (4 tests: no manifest exits, valid package succeeds, tag creation, warnings still succeed).

---

## Phase 6: Hardening + Guardrails — COMPLETED

### Phase 6A: Reserved Domain Enforcement — COMPLETED

Delivered:

- **`RESERVED_DOMAINS` frozenset + `is_reserved_domain_path()` helper** (`manifest.py`): `frozenset({"native", "mthds", "pipelex"})` constant and a helper that checks if a domain path's first segment is reserved. Protects the namespace so that standard-defined concepts and future standard domains don't collide with user packages.
- **`DomainExports.validate_domain_path()` extended** (`manifest.py`): Pydantic field validator rejects reserved domain paths in `[exports]` keys at parse time. Raises `ValueError` matching "reserved domain" with a clear message naming the reserved domain and listing all reserved domains.
- **`PackageVisibilityChecker.validate_reserved_domains()`** (`visibility.py`): New method iterates bundles and produces a `VisibilityError` for each bundle declaring a domain starting with a reserved segment. Wired into `check_visibility_for_blueprints()` before pipe reference and cross-package checks.
- **`_check_reserved_domains()` in publish validation** (`publish_validation.py`): Iterates bundle-scanned domain paths and flags any starting with a reserved prefix as `IssueLevel.ERROR` in `IssueCategory.MANIFEST` with a suggestion to rename. Wired into `validate_for_publish()` after bundle scanning, before exports check. Reserved domains in `[exports]` are caught at parse time by the Pydantic validator; this function catches reserved domains declared in bundle `.mthds` files.
- **7 new tests** (some parametrized, covering all 3 reserved domains): 3 in `test_manifest.py` (exact reserved rejected, hierarchical prefix rejected, non-reserved accepted), 1 in `test_manifest_parser.py` (parser raises on reserved domain in exports), 2 in `test_visibility.py` (reserved domain produces error, non-reserved passes), 1 in `test_publish_validation.py` (reserved domain in bundle file produces MANIFEST ERROR).
- Files: `manifest.py`, `visibility.py`, `publish_validation.py`, `test_data.py`, `test_manifest.py`, `test_manifest_parser.py`, `test_visibility.py`, `test_publish_validation.py`

### Phase 6B: `mthds_version` Enforcement — COMPLETED

Delivered:

- **`MTHDS_STANDARD_VERSION` constant** (`manifest.py`): `"1.0.0"` — separate from the Pipelex application version, the MTHDS standard may evolve independently.
- **`validate_mthds_version` field validator** (`manifest.py`): Pydantic `field_validator` on `MthdsPackageManifest.mthds_version` that rejects invalid version constraint strings at parse time using `is_valid_version_constraint()`. Accepts `None` (field is optional).
- **Runtime warning in `library_manager.py`**: `_warn_if_mthds_version_unsatisfied()` method checks if the current `MTHDS_STANDARD_VERSION` satisfies the package's `mthds_version` constraint using `parse_constraint()`, `parse_version()`, and `version_satisfies()` from Phase 4A. Emits `log.warning()` if unsatisfied or if the constraint is unparseable. Wired into `_load_mthds_files_into_library()` after manifest discovery and before dependency loading.
- **Publish validation check** (`publish_validation.py`): `_check_mthds_version()` verifies the `mthds_version` constraint is parseable by the semver engine via `parse_constraint()`. Reports `IssueLevel.ERROR` in `IssueCategory.MANIFEST` if unparseable. Wired into `validate_for_publish()` after manifest field checks.
- **8 new test methods** (14 test items with parametrization) across 3 test files: `test_manifest.py` (3 methods: valid constraints parametrized with 5 values, invalid constraints parametrized with 3 values, None accepted), `test_publish_validation.py` (2 methods: valid mthds_version no errors, absent mthds_version no errors), `test_mthds_version_warning.py` (3 methods: warning emitted when unsatisfied, no warning when satisfied, warning on unparseable constraint).
- Files: `manifest.py`, `library_manager.py`, `publish_validation.py`, `test_manifest.py`, `test_publish_validation.py`, new `test_mthds_version_warning.py`

---

## Phase 7: Type-Aware Search + Auto-Composition CLI — COMPLETED

### Phase 7A: Type-Compatible Search in CLI — COMPLETED

Delivered:

- **`--accepts <concept>` and `--produces <concept>` flags** on `pipelex pkg search`: Enable type-aware search from the command line. `--accepts` finds pipes that can consume a given concept; `--produces` finds pipes that output a given concept. The `query` argument is now optional — users can run `pipelex pkg search --accepts Text` without a positional query.
- **Fuzzy concept resolution** (`_resolve_concept_fuzzy()`): Collects candidates from native concepts (`NativeConceptCode` enum) and indexed concepts (`index.all_concepts()`), performs case-insensitive substring matching against concept_code and concept_ref. Exact-match priority: if any candidate's code or ref matches exactly (case-insensitive), only exact matches are returned — prevents `"Text"` from ambiguously matching `"TextAndImages"`. Returns list of `(ConceptId, concept_code)` tuples.
- **Ambiguous concept display** (`_display_ambiguous_concepts()`): Rich table with Package, Concept Code, Concept Ref columns plus a hint to refine the query. Exits 1 when ambiguous.
- **Wraps existing query engine**: `_handle_accepts_search()` calls `engine.query_what_can_i_do()` and `_handle_produces_search()` calls `engine.query_what_produces()` from Phase 5B's `KnowHowQueryEngine`. `_do_type_search()` builds the graph and creates the engine.
- **Display** (`_display_type_search_pipes()`): Results appear in the same Rich table format as existing search output (Package, Pipe, Type, Domain, Description, Exported).
- **Validation**: `do_pkg_search()` requires at least one of query/accepts/produces, else exits 1. Type search mode (accepts/produces) takes precedence over text search mode.
- **7 new tests** monkeypatching `build_index_from_project` to return `make_test_package_index()` from Phase 5B's test data: accepts finds pipes (Text→all pipes), produces finds pipes (PkgTestContractClause→extract_clause), ambiguous concept exits (Score→3 matches), no concept found (nonexistent→message), no pipes produce (Dynamic→message), no args exits, exact match preferred (Text≠TextAndImages).
- Files: `search_cmd.py`, `app.py`, `test_pkg_search.py`

### Phase 7B: Auto-Composition Suggestions — COMPLETED

- **`--compose` flag** on `pipelex pkg graph`: Meaningful only with `--from` + `--to` (the "I have X, I need Y" query). When set, the command prints a human-readable MTHDS pipe sequence template showing the discovered chain steps, input/output wiring, and cross-package references. Validates that both `--from` and `--to` are provided when `--compose` is set, exits 1 otherwise.
- **New `chain_formatter.py`** in `pipelex/core/packages/graph/`: `format_chain_as_mthds_snippet(chain_pipes, from_concept, to_concept)` takes a list of resolved `PipeNode`s and produces a readable composition template. Helpers: `_format_concept_ref()`, `_format_step()`, `_is_cross_package_chain()`. Advisory output only — not executable generation (that is builder territory).
- **Output format**: A "Composition:" header showing the concept flow (from -> intermediates -> to), followed by numbered steps listing each pipe's package address, domain, input concept(s), and output concept. When chains span multiple packages, appends a cross-package note about `alias->domain.pipe_code` syntax.
- **CLI integration**: `do_pkg_graph()` gains `compose: bool` param; `_handle_from_to()` expanded with `graph` and `compose` args; new `_print_compose_output()` resolves node_keys to PipeNodes and formats each chain. Multiple chains are prefixed with "Chain N of M:".
- Files: new `chain_formatter.py`, `graph_cmd.py`, `app.py`, new `test_chain_formatter.py`, `test_pkg_graph.py`
- **7 new tests**: 5 in `test_chain_formatter.py` (single step, two-step same-package, cross-package, empty chain, header concept flow) + 2 in `test_pkg_graph.py` (compose without from/to exits, compose with from/to succeeds)

---

## Phase 8: Builder Package Awareness

- **Dependency signature catalog**: The builder gains a "dependency signature catalog" constructed from the package index. This catalog holds exported pipe signatures (code, type, input/output specs) and public concepts from all declared dependencies.
- **`build_and_fix()` accepts dependency context**: `BuilderLoop.build_and_fix()` accepts an optional dependency context (the catalog) so the LLM prompt can include available dependency pipe signatures. This lets generated specs reference `alias->domain.pipe` without the builder treating them as undeclared.
- **LLM prompt context**: The builder's prompt template includes a section listing available dependency pipe signatures, enabling the LLM to generate cross-package references that are valid by construction.
- **Fix loop validates cross-package references**: During the fix loop, cross-package `alias->domain.pipe_code` references are validated against the catalog rather than being silently skipped.
- **`_fix_undeclared_concept_references()` checks dependency concepts first**: Before creating a new concept definition, the fix loop checks whether the concept exists in a dependency's public concepts. If so, it generates a cross-package reference instead of a duplicate local concept.
- **Addresses changes doc §5.5**: "builder needs awareness of available packages and their exported pipes/concepts."
- Files: `builder_loop.py`, new catalog helper in `pipelex/core/packages/index/`, `pipe_cmd.py`, `build_cmd.py`, tests
- ~8–10 tests

---

## Phase 9: Registry Specification + Integration Guide

The registry is built by a separate team in a separate project (not Python-based). Phase 9 produces a **normative specification document** so that team has everything they need to build a conformant registry, regardless of language or framework.

### Phase 9A: Registry API Specification

- Normative document defining the HTTP API contract the registry must implement.
- **Endpoints**: package listing, package detail, text search, type-compatible search (accepts/produces), graph chain queries.
- **Request/response schemas** (JSON) derived from existing `PackageIndex`, `PackageIndexEntry`, `PipeSignature`, `ConceptEntry` models.
- **Authentication model**: API keys, OAuth — options with recommendations.
- **Pagination, rate limiting, error response format**.
- **Versioning strategy** for the API itself (`/v1/`).

### Phase 9B: Crawling + Indexing Specification

- Normative rules for how the registry discovers and indexes packages.
- **Input**: package address → git clone → find `METHODS.toml` → parse manifest + scan `.mthds` bundles.
- **Output**: `PackageIndexEntry` equivalent (exact JSON schema).
- **Index refresh strategy**: webhooks, polling, manual trigger.
- **Extraction rules**: How to extract pipe signatures, concept entries, domain info, export status, and dependency aliases at the blueprint level (mirroring `build_index_entry_from_package()` logic).
- **Know-How Graph construction**: How to build the Know-How Graph from the index (mirroring `build_know_how_graph()` logic): concept nodes, native concepts, refinement resolution, pipe nodes, data flow edges, refinement edges.

### Phase 9C: Type-Aware Search + Graph Query Specification

- Normative rules for type-compatible search: refinement chain walking, concept compatibility.
- **Graph query semantics**: "what can I do with X", "what produces Y", "I have X, I need Y" (BFS chain discovery).
- **Compatibility check logic** between pipe signatures.
- **Cross-package concept resolution** via `dependency_aliases`.

### Phase 9D: Distribution Protocol Specification

- **Proxy/mirror protocol**: How a proxy intercepts fetch requests, caches packages, serves them (like Go's `GOPROXY`).
- **Signed manifests**: Signature format, verification algorithm, trust store model.
- **Social signals**: Install counts, stars, endorsements — data model and API endpoints.
- **Multi-tier deployment guide**: Local (no registry), Project (package in repo), Organization (internal registry/proxy), Community (public registry).

### Phase 9E: CLI Integration Points

- **`--registry <url>` option** for `pipelex pkg search`, `pipelex pkg index`, `pipelex pkg inspect`: Queries the remote registry API instead of (or in addition to) local data.
- **CLI client code**: Thin HTTP client in Pipelex conforming to the API spec from 9A. New `registry_client.py` module.
- **`pipelex pkg publish` extended**: Registers a package with a remote registry (POST endpoint) after local validation passes.
- Files: `search_cmd.py`, `index_cmd.py`, `inspect_cmd.py`, `publish_cmd.py`, new `registry_client.py`
- ~8–12 tests

**Deliverable format:** A standalone specification document (e.g., `mthds-registry-specification_v1.md`) in `refactoring/`, structured as a normative guide with JSON schemas, endpoint definitions, algorithm descriptions, and conformance requirements. The spec must be language-agnostic and self-contained.

---

## What NOT to Do

- **Do NOT implement the registry server in Python.** Phase 9 produces a normative specification for the separate registry project (built by another team in a different language). The Pipelex codebase only contains the CLI client (Phase 9E) that talks to the registry API.
- **Phases 5–8 are local-first.** All index, search, graph, publish, and builder operations run as CLI tools on local data. Remote registry integration comes in Phase 9E.
- **Do NOT rename the manifest** to anything other than `METHODS.toml`. The design docs are explicit about this name.
- **Do NOT rename Python classes or internal Pipelex types.** The standard is MTHDS; the implementation is Pipelex. Keep existing class names.

---

## Note on Client Project Brief

`mthds-client-project-update-brief.md` has been updated to reflect all completed phases (0–7B). Client projects can now:
- Use `.mthds` file extension and "method" terminology (Phase 0)
- Use hierarchical domains and domain-qualified pipe references (Phase 1)
- Create `METHODS.toml` manifests with `pipelex pkg init`, inspect with `pipelex pkg list` (Phase 2)
- Declare local path dependencies with `pipelex pkg add` and use `alias->domain.pipe_code` cross-package references (Phase 3)
- Use remote dependencies with semver constraints, lock files, and transitive resolution via `pipelex pkg lock/install/update` (Phase 4A–4D)
- Depend on multiple packages without concept name collisions thanks to per-package library isolation (Phase 4E)
- Discover and search packages locally with `pipelex pkg index/search/inspect` (Phase 5A–5C)
- Query the know-how graph for concept/pipe relationships with `pipelex pkg graph` (Phase 5B–5C)
- Validate package readiness for distribution with `pipelex pkg publish` (Phase 5D)
- Trust that reserved domains (`native`, `mthds`, `pipelex`) are protected from accidental collision (Phase 6A)
- Get runtime warnings when a dependency requires a newer MTHDS standard version (Phase 6B)
- Search for pipes by input/output concept types with `pipelex pkg search --accepts/--produces` (Phase 7A)
- Get auto-composition suggestions showing how to chain pipes across packages with `pipelex pkg graph --compose` (Phase 7B)

Once future phases are completed, client projects will additionally be able to:
- Have the builder generate cross-package references to dependency pipes/concepts automatically (Phase 8)
- Discover, search, and publish packages via a remote registry with `--registry <url>` (Phase 9E)

---

## Source Documents

| Section | Source document | Relevant sections |
|---------|----------------|-------------------|
| Manifest format | `pipelex-package-system-design_v*.md` | §3 Package Structure, §4 Package Manifest |
| Visibility model | `pipelex-package-system-design_v*.md` | §4 `[exports]` rules, §5 Namespace Resolution |
| Manifest data model | `pipelex-package-system-changes_v*.md` | §4.1 Package Manifest |
| CLI commands | `pipelex-package-system-changes_v*.md` | §5.6 CLI |
| Builder impact | `pipelex-package-system-changes_v*.md` | §5.5 Builder |
| Roadmap position | `pipelex-package-system-changes_v*.md` | §6 Roadmap table |
| Phase 4 — remote resolution | `pipelex-package-system-design_v*.md` | §7 Dependency Management (fetching, lock file, version resolution) |
| Phase 4 — testing strategy | `testing-package-system.md` | Layer 3 (local git repos), Layer 4 (GitHub smoke test) |
| Phase 5 — registry/discovery | `pipelex-package-system-design_v*.md` | §8 Distribution Architecture, §9 Know-How Graph Integration |
| Phase 6 — reserved domains | `pipelex-package-system-design_v*.md` | §2 Reserved domains, §4 Manifest validation |
| Phase 6 — mthds_version | `pipelex-package-system-design_v*.md` | §4 `mthds_version` field |
| Phase 7 — type-aware search | `pipelex-package-system-design_v*.md` | §9 Know-How Graph Integration (type-compatible search) |
| Phase 7 — auto-composition | `pipelex-package-system-design_v*.md` | §9 Auto-composition suggestions |
| Phase 8 — builder awareness | `pipelex-package-system-changes_v*.md` | §5.5 Builder (dependency awareness) |
| Phase 9 — proxy/signed manifests | `pipelex-package-system-design_v*.md` | §7 Proxy/mirror protocol, signed manifests |
| Phase 9 — registry/multi-tier | `pipelex-package-system-design_v*.md` | §8 Distribution Architecture, multi-tier deployment |
| Design rationale | `Proposal -The Pipelex Package System.md` | §2, §4 |
