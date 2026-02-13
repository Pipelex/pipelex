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

## Known Limitations (current implementation)

These are tracked as deliverables in the Phase 4 sub-phases above:

1. **Per-package Library isolation** (Phase 4E): Dependency pipes/concepts stored with aliased keys in flat library dicts. Concept name conflicts log a warning and skip native-key registration.
2. **Cross-package concept refinement validation** (Phase 4E): `refines = "alias->domain.Concept"` parses correctly, but `are_concept_compatible()` doesn't traverse across package boundaries yet.
3. **Transitive dependency resolution** (Phase 4D): Only direct dependencies resolved. Recursive resolution with cycle detection pending.

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

## Phase 4D: Transitive Dependencies + CLI Commands — PLANNED

Deliverables:

- **Transitive resolution**: Extend `dependency_resolver.py` with recursive resolution + cycle detection. Diamond dependency handling via `select_minimum_version_for_multiple_constraints` from Phase 4A.
- **`TransitiveDependencyError`** in `exceptions.py`: Cycle detection, missing transitive deps.
- **CLI `pipelex pkg lock`** (`pipelex/cli/commands/pkg/lock_cmd.py`): Scan `METHODS.toml`, resolve all deps (local + remote), write `methods.lock`.
- **CLI `pipelex pkg install`** (`pipelex/cli/commands/pkg/install_cmd.py`): Read `methods.lock`, fetch any missing deps into cache, verify integrity.
- **CLI `pipelex pkg update`** (`pipelex/cli/commands/pkg/update_cmd.py`): Re-resolve to latest compatible versions, update `methods.lock`.
- **Tests**: Transitive resolution (A→B→C), cycle detection (A→B→A), diamond deps (A→B, A→C, both→D), CLI command tests.

Key files to create:

| File | Purpose |
|------|---------|
| `pipelex/cli/commands/pkg/lock_cmd.py` | `pipelex pkg lock` |
| `pipelex/cli/commands/pkg/install_cmd.py` | `pipelex pkg install` |
| `pipelex/cli/commands/pkg/update_cmd.py` | `pipelex pkg update` |

Key files to modify:

| File | Change |
|------|--------|
| `pipelex/core/packages/dependency_resolver.py` | Transitive resolution + cycle detection |
| `pipelex/core/packages/exceptions.py` | Add `TransitiveDependencyError` |
| `pipelex/cli/commands/pkg/app.py` | Register new commands |

---

## Phase 4E: Per-Package Library Isolation + Concept Refinement — PLANNED

Deliverables:

- **Per-package Library instances**: Refactor `library_manager.py` — each package gets its own `ConceptLibrary` + `PipeLibrary`. Main package accesses dependency libraries via alias. Eliminates concept name conflicts between packages.
- **Cross-package concept refinement validation**: Extend `are_concept_compatible()` to traverse aliased concept keys across package boundaries. Validate at both install-time and load-time.
- **Builder package-awareness**: Builder knows available packages' exported pipes/concepts for cross-package pipe references during method generation.
- **Tests**: Concept name collision scenarios, refinement chain across packages, builder cross-package generation.

Key files to modify:

| File | Change |
|------|--------|
| `pipelex/libraries/library_manager.py` | Per-package Library isolation refactor |
| `pipelex/core/concepts/validation.py` | Cross-package refinement traversal |
| `pipelex/builder/builder_loop.py` | Package-aware generation |

---

## Phase 5: Registry + Know-How Graph Discovery — PLANNED

Deliverables:

- **Registry index service**: Crawl known package addresses, parse `METHODS.toml` for metadata, parse `.mthds` files for concept definitions and pipe signatures, build a searchable index. No duplication — all data derived from the source files.
- **Type-aware search**: "I have X, I need Y" queries leveraging typed pipe signatures and concept refinement hierarchies — a capability that text-based discovery (like Agent Skills) cannot support.
- **`pipelex pkg publish` CLI command**: Validate and prepare a package for distribution, register with a registry.
- **Know-How Graph browsing + auto-composition**: Navigate the refinement hierarchy, explore pipe signatures, find chains through the graph when no single pipe goes from X to Y.
- **Multi-tier deployment**: Local (single `.mthds` file) / Project (package in a repo) / Organization (internal registry/proxy) / Community (public Git repos + public registries).

---

## What NOT to Do

- **Do NOT implement remote registry or Know-How Graph browsing.** That is Phase 5.
- **Phase 4 is in progress (4A + 4B complete).** Implement sub-phases in order — do not skip ahead to later sub-phases without completing prerequisites.
- **Do NOT rename the manifest** to anything other than `METHODS.toml`. The design docs are explicit about this name.
- **Do NOT rename Python classes or internal Pipelex types.** The standard is MTHDS; the implementation is Pipelex. Keep existing class names.

---

## Note on Client Project Brief

`mthds-client-project-update-brief.md` has been updated to reflect all completed phases (0–3). Client projects can now:
- Use `.mthds` file extension and "method" terminology (Phase 0)
- Use hierarchical domains and domain-qualified pipe references (Phase 1)
- Create `METHODS.toml` manifests with `pipelex pkg init`, inspect with `pipelex pkg list` (Phase 2)
- Declare local path dependencies with `pipelex pkg add` and use `alias->domain.pipe_code` cross-package references (Phase 3)

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
| Design rationale | `Proposal -The Pipelex Package System.md` | §2, §4 |
