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

## Known Limitations (Deferred to Phase 4+)

1. **Per-package Library isolation**: Dependency pipes and concepts are stored with aliased keys (`alias->pipe_code`, `alias->domain.ConceptCode`) in the same flat library dicts as the main package. This avoids creating separate Library instances per package but means concept name conflicts between a dependency and the local package log a warning and skip native-key registration (the aliased key still works for cross-package refs). Proper per-package Library isolation is planned for Phase 4.

2. **Cross-package concept refinement validation**: `refines = "alias->domain.Concept"` parses and stores correctly, but the compatibility checker (`are_concept_compatible()`) doesn't resolve across package boundaries yet. This requires the refines chain to traverse aliased concept keys — planned for Phase 4.

3. **Transitive dependency resolution**: Phase 3 handles direct dependencies only. If Package A depends on Package B which depends on Package C, Package C is not automatically available to Package A. Recursive resolution with cycle detection is planned for Phase 4.

---

## Phase 4: Remote Dependency Resolution + Lock File — PLANNED

Deliverables:

- **VCS clone from addresses**: New `pipelex/core/packages/vcs_resolver.py` — clone packages from their addresses (the address IS the fetch URL: `github.com/acme/...` maps to `https://github.com/acme/...`).
- **Version tag resolution**: Minimum version selection (Go's approach) — match version constraints against git tags. If Package A requires `>=1.0.0` of B and Package C requires `>=1.2.0` of B, resolve to `1.2.0`.
- **Lock file `methods.lock`**: New `pipelex/core/packages/lock_file.py` — TOML format recording resolved version + SHA-256 hash + source URL for every dependency. Auto-generated, committed to version control.
- **Package cache**: `~/.mthds/packages/` (global) or `.mthds/packages/` (project-local) — stores fetched package contents, organized by address and version.
- **Transitive dependency resolution**: Extend `resolve_local_dependencies()` in `pipelex/core/packages/dependency_resolver.py` with recursive resolution + cycle detection.
- **Cross-package concept refinement validation**: Extend `are_concept_compatible()` in concept validation to traverse aliased concept keys across package boundaries.
- **Per-package Library isolation**: Replace flat aliased-key storage with per-package Library instances — refactor `_load_dependency_packages()` in `pipelex/libraries/library_manager.py`.
- **Builder package-awareness**: Builder knows available packages' exported pipes/concepts, enabling cross-package pipe references during method generation.
- **CLI commands**: `pipelex pkg install` (fetch and cache all deps from lock file), `pipelex pkg update` (update to latest compatible versions), `pipelex pkg lock` (regenerate lock file) — new commands in `pipelex/cli/commands/pkg/`.
- **Layer 3 tests**: Local bare git repos with `file://` protocol, as designed in `testing-package-system.md`.

Key files to modify:

- `pipelex/core/packages/dependency_resolver.py` — extend for remote + transitive resolution
- `pipelex/libraries/library_manager.py` — per-package isolation refactor
- `pipelex/core/packages/manifest.py` — potential additions for lock file model
- `pipelex/cli/commands/pkg/` — new `install_cmd.py`, `update_cmd.py`, `lock_cmd.py`

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
- **Do NOT implement remote VCS fetch or lock file generation.** That is Phase 4. Phase 3 only supports local `path` dependencies.
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
