# MTHDS Standard — Implementation Brief (v8)

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

- **Hierarchical domain validation**: domain codes accept dotted paths (e.g., `legal.contracts.shareholder`). Updated domain validation in `pipelex/core/domains/`.
- **Unified `QualifiedRef` model** (`pipelex/core/qualified_ref.py`): A single frozen Pydantic `BaseModel` that handles both concept and pipe references (fields: `domain_path: str | None`, `local_code: str`). Unified model eliminates duplication since concept and pipe references share the same parsing logic (split-on-last-dot, casing disambiguates). The `package_alias` field is omitted since cross-package references are Phase 3.
- **Split-on-last-dot parsing**: unified parsing rule for both concept and pipe references — the last segment is the `local_code`, everything before it is the `domain_path`.
- **Bundle blueprint validation**: domain-qualified pipe references validated against known domains and pipes within the current package.
- **Builder bundles migrated**: cross-domain pipe references in the builder's internal bundles now use `domain.pipe_code` syntax.

---

## Phase 2: Package Manifest + Exports / Visibility — COMPLETED

- **`MthdsPackageManifest` data model** (`pipelex/core/packages/manifest.py`): `PackageDependency`, `DomainExports`, and `MthdsPackageManifest` Pydantic models with field validators (address hostname pattern, semver, version constraint ranges using Poetry/uv-style syntax, non-empty description, snake_case aliases, valid domain paths, valid pipe codes). The `[dependencies]` format uses the alias as the TOML key — natural for the `->` syntax since the alias is the lookup key.
- **TOML parsing and serialization** (`pipelex/core/packages/manifest_parser.py`): `parse_methods_toml()` with recursive sub-table walk for `[exports]` domain path reconstruction; `serialize_manifest_to_toml()` using `tomlkit`.
- **Custom exceptions** (`pipelex/core/packages/exceptions.py`): `ManifestError`, `ManifestParseError`, `ManifestValidationError`.
- **Manifest discovery** (`pipelex/core/packages/discovery.py`): `find_package_manifest()` walks up from a bundle path, stopping at `METHODS.toml`, `.git/` boundary, or filesystem root. Returns `None` for standalone bundles.
- **Visibility checker** (`pipelex/core/packages/visibility.py`): `PackageVisibilityChecker` enforces cross-domain pipe visibility against `[exports]`. Rules: no manifest = all public; bare ref = allowed; same-domain = allowed; cross-domain requires pipe to be in `[exports]` or be `main_pipe` (auto-exported).
- **Cross-package `->` reference detection**: `QualifiedRef.has_cross_package_prefix()` and `split_cross_package_ref()`. `PackageVisibilityChecker.validate_cross_package_references()` emits warnings for known aliases, errors for unknown aliases.
- **Visibility wired into bundle loading** (`pipelex/libraries/library_manager.py`): `_check_package_visibility()` runs after blueprint parsing, before `load_from_blueprints`. Raises `LibraryLoadingError` on violations.
- **CLI commands** (`pipelex/cli/commands/pkg/`): `pipelex pkg init` scans `.mthds` files, generates skeleton `METHODS.toml`. `pipelex pkg list` displays the manifest with Rich tables.
- **Builder awareness** (`pipelex/builder/builder_loop.py`): `maybe_generate_manifest_for_output()` generates a `METHODS.toml` when an output directory contains multiple domains.

---

## Phase 3: Cross-Package References + Local Dependency Resolution — COMPLETED

- **`path` field on `PackageDependency`** (`manifest.py`): Local filesystem path (`path = "../scoring-lib"`) for development-time dependency resolution, similar to Cargo's `path` deps or Go's `replace` directives. Optional, forward-compatible with Phase 4's remote fetch.
- **Cross-package concept validation** (`pipelex/core/concepts/validation.py`): `is_concept_ref_valid()` and `is_concept_ref_or_code_valid()` accept `->` refs by stripping the alias prefix before validating.
- **Bundle-level validation skip for `->` refs** (`pipelex/core/bundles/pipelex_bundle_blueprint.py`): `validate_local_concept_references()` and `validate_local_pipe_references()` explicitly skip `->` refs via `QualifiedRef.has_cross_package_prefix()`.
- **ConceptFactory cross-package handling** (`pipelex/core/concepts/concept_factory.py`): Produces aliased domain codes like `"scoring_lib->scoring"` so that `make_concept_ref_with_domain()` reconstructs `"scoring_lib->scoring.WeightedScore"` — the key used for lookup in ConceptLibrary.
- **Cross-package pipe lookup** (`pipelex/libraries/pipe/pipe_library.py`): `get_optional_pipe()` resolves `alias->domain.pipe_code` to `alias->pipe_code` via dict lookup. `add_dependency_pipe(alias, pipe)` stores dependency pipes with aliased key.
- **Cross-package concept lookup** (`pipelex/libraries/concept/concept_library.py`): `get_required_concept()` handles `->` refs via direct dict lookup. `add_dependency_concept(alias, concept)` stores with aliased key.
- **Dependency resolver** (`pipelex/core/packages/dependency_resolver.py`): `resolve_local_dependencies()` resolves dependencies with a local `path` field: resolves relative to package root, finds `METHODS.toml` in the dependency, scans `.mthds` files, determines exported pipes from manifest exports + `main_pipe` auto-export.
- **Dependency loading in LibraryManager** (`library_manager.py`): `_load_dependency_packages()` integrated into `_load_mthds_files_into_library()`. For each resolved dependency: parses blueprints, loads concepts with aliased keys, loads only exported pipes with aliased keys.
- **Graceful handling of unresolved cross-package refs**: Three layers of safety:
  - `library.py`: skips validation for pipe controllers with unresolved cross-package dependencies
  - `pipe_sequence.py`: `needed_inputs()` uses `get_optional_pipe` for `->` refs and skips if None
  - `dry_run.py`: catches `PipeNotFoundError` and treats it as a graceful skip
- **CLI `pipelex pkg add`** (`pipelex/cli/commands/pkg/add_cmd.py`): Adds a dependency to `METHODS.toml`. Options: `address`, `--alias`, `--version`, `--path`.

---

## Phase 4A: Semver Constraint Evaluation Engine — COMPLETED

- **`pipelex/tools/misc/semver.py`**: Typed wrapper around `semantic_version` providing `parse_version` (with `v`-prefix stripping for git tags), `parse_constraint`, `version_satisfies`, `parse_version_tag`, and Go-style Minimum Version Selection via `select_minimum_version` (single constraint) and `select_minimum_version_for_multiple_constraints` (transitive case).
- `SemVerError` exception for parse failures.
- Supports all constraint operators: `^`, `~`, `>=`, `>`, `<=`, `<`, `==`, `!=`, `*`, wildcards, compound (`>=1.0.0,<2.0.0`).
- New dependency: `semantic-version>=2.10.0` in `pyproject.toml`.

---

## Phase 4B: VCS Fetch + Package Cache — COMPLETED

- **VCS resolver** (`pipelex/core/packages/vcs_resolver.py`): `address_to_clone_url()` maps addresses to HTTPS clone URLs. `list_remote_version_tags()` runs `git ls-remote --tags`. `resolve_version_from_tags()` applies MVS. `clone_at_version()` does a shallow clone. All git calls have timeouts and typed exceptions.
- **Package cache** (`pipelex/core/packages/package_cache.py`): Cache layout `~/.mthds/packages/{address}/{version}/`. `store_in_cache()` uses staging directory + atomic rename and strips `.git/`. All functions accept a `cache_root` override for testability.
- **New exceptions**: `VCSFetchError`, `VersionResolutionError`, `PackageCacheError`.
- **Dependency resolver extended** (`dependency_resolver.py`): `resolve_remote_dependency()` orchestrating clone URL → tag listing → MVS selection → cache check → clone if miss. `resolve_all_dependencies()` unifying local path + remote VCS resolution. `fetch_url_overrides` parameter enables test fixtures to substitute `file://` URLs.
- **Library manager updated**: `_load_dependency_packages()` now calls `resolve_all_dependencies()`, enabling remote deps alongside local path deps.

---

## Phase 4C: Lock File — COMPLETED

- **Lock file model and parser** (`pipelex/core/packages/lock_file.py`): `LockedPackage` frozen model (version, SHA-256 hash, source URL), `LockFile` frozen model keyed by package address. TOML parse/serialize with deterministic sorted output.
- **Hash computation** (`compute_directory_hash()`): Deterministic SHA-256 of directory contents — collects files recursively, skips `.git/`, sorts by POSIX-normalized relative path.
- **Lock file generation** (`generate_lock_file()`): Takes manifest + resolved dependencies, filters out local deps, computes hash for each remote dep.
- **Integrity verification** (`verify_locked_package()`, `verify_lock_file()`): Computes hash of cached directory, compares with lock entry hash, raises `IntegrityError` on mismatch.
- **Exceptions**: `LockFileError`, `IntegrityError`.

---

## Phase 4D: Transitive Dependencies + CLI Commands — COMPLETED

- **`DependencyResolveError`** moved to `exceptions.py` (inherits `PipelexError`). New `TransitiveDependencyError` for cycles and unsatisfiable diamond constraints.
- **`address` field on `ResolvedDependency`**: Tracks the package address through resolution, enabling lock file generation for transitive deps.
- **Transitive resolution algorithm** (`dependency_resolver.py`): `_resolve_transitive_tree()` implements DFS with cycle detection. `_resolve_with_multiple_constraints()` handles diamond dependencies via `select_minimum_version_for_multiple_constraints()`. `resolve_all_dependencies()` resolves local deps first (no recursion), then remote through the transitive tree walker.
- **Lock file generation updated**: `generate_lock_file()` uses `resolved.address` directly, naturally including transitive deps.
- **CLI `pipelex pkg lock`**: Resolves with transitive, generates lock file, writes `methods.lock`.
- **CLI `pipelex pkg install`**: Reads `methods.lock`, fetches missing packages, verifies integrity.
- **CLI `pipelex pkg update`**: Fresh resolve ignoring existing lock, generates new lock file, displays diff.

---

## Phase 4E: Per-Package Library Isolation + Concept Refinement — COMPLETED

- **Per-package Library instances** (`pipelex/libraries/library.py`): Each dependency gets its own isolated `Library` in `Library.dependency_libraries: dict[str, Library]`. `resolve_concept(concept_ref)` routes `alias->domain.Code` lookups through child libraries. `validate_concept_library_with_libraries()` validates cross-package refines targets after all deps are loaded.
- **Per-package loading in LibraryManager**: `_load_single_dependency()` creates a child `Library` per dependency. Temporary concept registration in main library during pipe construction, then removed. Aliased entries added to main library for cross-package lookups.
- **Cross-package concept refinement validation** (`pipelex/core/concepts/concept.py`): `are_concept_compatible()` gains a `concept_resolver` callback. Cross-package refines resolved through the resolver before compatibility comparison.
- **ConceptLibrary resolver wiring** (`pipelex/libraries/concept/concept_library.py`): `set_concept_resolver(resolver)` wires after dependency loading. `is_compatible()` passes the resolver to `are_concept_compatible()`.
- **ConceptFactory cross-package refines** (`pipelex/core/concepts/concept_factory.py`): `_handle_refines()` detects cross-package refines, generates a standalone `TextContent` subclass (base class not available locally). Refinement tracked in `concept.refines` for runtime validation.
- **Builder package-awareness** (`pipelex/builder/builder_loop.py`): `_fix_undeclared_concept_references()` and `_prune_unreachable_specs()` skip cross-package refs. `_extract_local_bare_code()` returns `None` for cross-package refs.

---

## Phase 5: Local Package Discovery + Know-How Graph — COMPLETED

Scoped to **local-first** (no registry server). A future phase layers a hosted registry on top.

### Phase 5A: Package Index Model + Index Builder — COMPLETED

- **Index data models** (`pipelex/core/packages/index/models.py`): Frozen Pydantic models for indexing at the blueprint level (no runtime class loading). `PipeSignature`, `ConceptEntry`, `DomainEntry`, `PackageIndexEntry` (full metadata + domains/concepts/pipes/dependency addresses), `PackageIndex` (mutable collection keyed by address).
- **Index builder** (`pipelex/core/packages/index/index_builder.py`): `build_index_entry_from_package()` parses `METHODS.toml` and scans `.mthds` files to extract pipe signatures, concept entries, and domain info — all at string level. `build_index_from_cache()` discovers cached packages. `build_index_from_project()` indexes current project plus dependencies.
- **Public utility functions**: `collect_mthds_files()` and `determine_exported_pipes()` in `dependency_resolver.py` made public for reuse.

### Phase 5B: Know-How Graph Model + Query Engine — COMPLETED

- **`dependency_aliases` on `PackageIndexEntry`**: Maps alias → address. Required for graph builder to resolve cross-package `refines` strings.
- **Graph data models** (`pipelex/core/packages/graph/models.py`): `ConceptId` (frozen, `package_address` + `concept_ref`), `EdgeKind` (StrEnum: `DATA_FLOW`, `REFINEMENT`), `PipeNode`, `ConceptNode`, `GraphEdge`, `KnowHowGraph` (mutable container with lookup methods). `NATIVE_PACKAGE_ADDRESS = "__native__"` for native concepts.
- **Graph builder** (`pipelex/core/packages/graph/graph_builder.py`): `build_know_how_graph(index)` in steps: concept nodes → native concept nodes → refines resolution (cross-package via `dependency_aliases`) → pipe nodes with resolved I/O → refinement edges → data flow edges using reverse index + refinement ancestry walk.
- **Query engine** (`pipelex/core/packages/graph/query_engine.py`): `query_what_can_i_do(concept_id)` (pipes accepting a concept), `query_what_produces(concept_id)` (pipes producing a concept), `check_compatibility(source, target)` (compatible input params), `resolve_refinement_chain(concept_id)`, `query_i_have_i_need(input_id, output_id, max_depth=3)` (BFS for multi-step pipe chains).
- **Package isolation**: Same concept code in different packages produces distinct `ConceptId`s scoped by `package_address`.

### Phase 5C: CLI Commands (index, search, inspect, graph) — COMPLETED

- **`pipelex pkg index [--cache]`**: Rich table of all indexed packages (address, version, description, counts). `--cache` indexes cached packages.
- **`pipelex pkg search <query> [--domain] [--concept] [--pipe] [--cache]`**: Case-insensitive substring search across concepts and pipes. `--domain` filters, `--concept`/`--pipe` restrict output type.
- **`pipelex pkg inspect <address> [--cache]`**: Detailed view with 4 Rich tables: Package Info, Domains, Concepts, Pipe Signatures.
- **`pipelex pkg graph [--from] [--to] [--check] [--max-depth] [--cache]`**: 4 modes: `--from` (what accepts), `--to` (what produces), `--from` + `--to` (BFS chains), `--check` (compatibility). ConceptId parsed via `::` separator.

### Phase 5D: Package Publish Validation — COMPLETED

- **`pipelex pkg publish [--tag]`**: Validates package readiness with 15 checks across 7 categories (manifest, bundle, export, visibility, dependency, lock_file, git). Errors (red) and warnings (yellow) as Rich tables with suggestions. `--tag` creates local git tag on success.
- **Core validation** (`pipelex/core/packages/publish_validation.py`): `IssueLevel` and `IssueCategory` StrEnums, `PublishValidationIssue` and `PublishValidationResult` frozen models, `validate_for_publish()` orchestrator with `check_git` flag for test isolation.

---

## Phase 6: Hardening + Guardrails — COMPLETED

### Phase 6A: Reserved Domain Enforcement — COMPLETED

- **`RESERVED_DOMAINS` frozenset + `is_reserved_domain_path()` helper** (`manifest.py`): `frozenset({"native", "mthds", "pipelex"})` — protects the namespace from collisions with user packages.
- **`DomainExports.validate_domain_path()` extended** (`manifest.py`): Pydantic field validator rejects reserved domain paths in `[exports]` keys at parse time.
- **`PackageVisibilityChecker.validate_reserved_domains()`** (`visibility.py`): Produces a `VisibilityError` for each bundle declaring a reserved domain. Wired into `check_visibility_for_blueprints()`.
- **Standalone bundle enforcement** (`library_manager.py`): `_check_package_visibility()` runs `validate_reserved_domains()` even when no manifest is found, closing the gap where a standalone `.mthds` file with `domain = "native"` would load without error.
- **`_check_reserved_domains()` in publish validation** (`publish_validation.py`): Flags reserved domain prefixes in bundle `.mthds` files as `IssueLevel.ERROR`.

### Phase 6B: `mthds_version` Enforcement — COMPLETED

- **`MTHDS_STANDARD_VERSION` constant** (`manifest.py`): `"1.0.0"` — separate from the Pipelex application version.
- **`validate_mthds_version` field validator** (`manifest.py`): Rejects invalid version constraint strings at parse time. Accepts `None` (field is optional).
- **Runtime warning** (`library_manager.py`): `_warn_if_mthds_version_unsatisfied()` checks if current `MTHDS_STANDARD_VERSION` satisfies the package's constraint. Emits `log.warning()` if unsatisfied or unparseable. Wired into `_load_mthds_files_into_library()` after manifest discovery.
- **Publish validation** (`publish_validation.py`): `_check_mthds_version()` reports `ERROR` if unparseable, `WARNING` if not satisfied by current `MTHDS_STANDARD_VERSION` (catches cases like `>=99.0.0` targeting a future version).

---

## Phase 7: Type-Aware Search + Auto-Composition CLI — COMPLETED

### Phase 7A: Type-Compatible Search in CLI — COMPLETED

- **`--accepts <concept>` and `--produces <concept>` flags** on `pipelex pkg search`: Type-aware search. `--accepts` finds pipes consuming a concept; `--produces` finds pipes outputting a concept. The `query` argument is now optional.
- **Fuzzy concept resolution** (`_resolve_concept_fuzzy()`): Case-insensitive substring matching against concept_code and concept_ref. Exact-match priority prevents `"Text"` from ambiguously matching `"TextAndImages"`.
- **Wraps existing query engine**: `_handle_accepts_search()` → `engine.query_what_can_i_do()`, `_handle_produces_search()` → `engine.query_what_produces()`.
- **Validation**: Requires at least one of query/accepts/produces. Type search takes precedence over text search.

### Phase 7B: Auto-Composition Suggestions — COMPLETED

- **`--compose` flag** on `pipelex pkg graph`: Meaningful only with `--from` + `--to`. Prints a human-readable MTHDS pipe sequence template showing chain steps, I/O wiring, and cross-package references. Advisory output — not executable generation (that is builder territory).
- **`chain_formatter.py`** (`pipelex/core/packages/graph/`): `format_chain_as_mthds_snippet()` produces a composition template. Shows concept flow header, numbered steps with package/domain/I-O, cross-package notes.
- **CLI integration**: Multiple chains prefixed with "Chain N of M:".

---

## Phase 8: Builder Package Awareness

- **Dependency signature catalog**: The builder gains a catalog constructed from the package index holding exported pipe signatures and public concepts from declared dependencies.
- **`build_and_fix()` accepts dependency context**: LLM prompt includes available dependency pipe signatures, enabling cross-package references valid by construction.
- **Fix loop validates cross-package references**: `alias->domain.pipe_code` references validated against the catalog rather than silently skipped.
- **`_fix_undeclared_concept_references()` checks dependency concepts first**: Before creating a new concept definition, checks whether the concept exists in a dependency's public concepts — generates a cross-package reference instead of a duplicate.
- Addresses changes doc §5.5: "builder needs awareness of available packages and their exported pipes/concepts."

---

## Phase 9: Registry Specification + Integration Guide

The registry is built by a separate team in a separate project (not Python-based). Phase 9 produces a **normative specification document** for that team.

### Phase 9A: Registry API Specification

- HTTP API contract: package listing, detail, text search, type-compatible search, graph chain queries.
- Request/response schemas (JSON) derived from existing models.
- Authentication model, pagination, rate limiting, error format, API versioning (`/v1/`).

### Phase 9B: Crawling + Indexing Specification

- How the registry discovers and indexes packages: address → git clone → parse manifest + scan bundles → `PackageIndexEntry`.
- Index refresh strategy: webhooks, polling, manual trigger.
- Know-How Graph construction rules (mirroring `build_know_how_graph()` logic).

### Phase 9C: Type-Aware Search + Graph Query Specification

- Refinement chain walking, concept compatibility rules.
- Graph query semantics: "what can I do with X", "what produces Y", "I have X, I need Y".
- Cross-package concept resolution via `dependency_aliases`.

### Phase 9D: Distribution Protocol Specification

- Proxy/mirror protocol (like Go's `GOPROXY`).
- Signed manifests: signature format, verification, trust store.
- Social signals: install counts, stars, endorsements.
- Multi-tier deployment guide: Local, Project, Organization, Community.

### Phase 9E: CLI Integration Points

- **`--registry <url>` option** for `pipelex pkg search`, `index`, `inspect`: queries remote registry API.
- **CLI client code**: Thin HTTP client in `registry_client.py`.
- **`pipelex pkg publish` extended**: Registers with remote registry after local validation.

**Deliverable format:** A standalone specification document (`mthds-registry-specification_v1.md`) in `refactoring/`, language-agnostic and self-contained.

---

## What NOT to Do

- **Do NOT implement the registry server in Python.** Phase 9 produces a normative specification. Pipelex only contains the CLI client (Phase 9E).
- **Phases 5–8 are local-first.** Remote registry integration comes in Phase 9E.
- **Do NOT rename the manifest** to anything other than `METHODS.toml`.
- **Do NOT rename Python classes or internal Pipelex types.** The standard is MTHDS; the implementation is Pipelex.

---

## Note on Client Project Brief

`mthds-client-project-update-brief.md` reflects all completed phases (0–7B). Client projects can now:
- Use `.mthds` file extension and "method" terminology (Phase 0)
- Use hierarchical domains and domain-qualified pipe references (Phase 1)
- Create `METHODS.toml` manifests with `pipelex pkg init`, inspect with `pipelex pkg list` (Phase 2)
- Declare local path dependencies with `pipelex pkg add` and use `alias->domain.pipe_code` cross-package references (Phase 3)
- Use remote dependencies with semver constraints, lock files, and transitive resolution via `pipelex pkg lock/install/update` (Phase 4A–4D)
- Depend on multiple packages without concept name collisions thanks to per-package library isolation (Phase 4E)
- Discover and search packages locally with `pipelex pkg index/search/inspect` (Phase 5A–5C)
- Query the know-how graph with `pipelex pkg graph` (Phase 5B–5C)
- Validate package readiness with `pipelex pkg publish` (Phase 5D)
- Trust that reserved domains (`native`, `mthds`, `pipelex`) are protected (Phase 6A)
- Get runtime warnings when a dependency requires a newer MTHDS standard version (Phase 6B)
- Search for pipes by input/output concept types with `--accepts`/`--produces` (Phase 7A)
- Get auto-composition suggestions with `--compose` (Phase 7B)

Future phases:
- Builder generates cross-package references automatically (Phase 8)
- Remote registry with `--registry <url>` (Phase 9E)

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
| Phase 4 — remote resolution | `pipelex-package-system-design_v*.md` | §7 Dependency Management |
| Phase 5 — registry/discovery | `pipelex-package-system-design_v*.md` | §8 Distribution Architecture, §9 Know-How Graph |
| Phase 6 — reserved domains | `pipelex-package-system-design_v*.md` | §2 Reserved domains, §4 Manifest validation |
| Phase 6 — mthds_version | `pipelex-package-system-design_v*.md` | §4 `mthds_version` field |
| Phase 7 — type-aware search | `pipelex-package-system-design_v*.md` | §9 Know-How Graph (type-compatible search) |
| Phase 7 — auto-composition | `pipelex-package-system-design_v*.md` | §9 Auto-composition suggestions |
| Phase 8 — builder awareness | `pipelex-package-system-changes_v*.md` | §5.5 Builder |
| Phase 9 — registry | `pipelex-package-system-design_v*.md` | §7, §8 |
| Design rationale | `Proposal -The Pipelex Package System.md` | §2, §4 |
