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

- **`MthdsPackageManifest` data model** (`pipelex/core/packages/manifest.py`): `PackageDependency`, `DomainExports`, and `MthdsPackageManifest` Pydantic models with field validators (address hostname pattern, semver for package version, version constraint ranges for dependency versions, non-empty description, snake_case aliases, unique aliases, valid domain paths, valid pipe codes).
- **TOML parsing and serialization** (`pipelex/core/packages/manifest_parser.py`): `parse_methods_toml()` with recursive sub-table walk for `[exports]` domain path reconstruction; `serialize_manifest_to_toml()` using `tomlkit` for human-readable output.
- **Custom exceptions** (`pipelex/core/packages/exceptions.py`): `ManifestError`, `ManifestParseError`, `ManifestValidationError`.
- **Manifest discovery** (`pipelex/core/packages/discovery.py`): `find_package_manifest()` walks up from a bundle path, stopping at `METHODS.toml`, `.git/` boundary, or filesystem root. Returns `None` for standalone bundles.
- **Visibility checker** (`pipelex/core/packages/visibility.py`): `PackageVisibilityChecker` enforces cross-domain pipe visibility against `[exports]`. Rules: no manifest = all public; bare ref = allowed; same-domain = allowed; cross-domain requires pipe to be in `[exports]` or be `main_pipe` (auto-exported). Error messages include `[exports]` hint.
- **Cross-package `->` reference detection**: `QualifiedRef.has_cross_package_prefix()` and `split_cross_package_ref()` static methods. `PackageVisibilityChecker.validate_cross_package_references()` emits warnings for known aliases, errors for unknown aliases.
- **Visibility wired into bundle loading** (`pipelex/libraries/library_manager.py`): `_check_package_visibility()` runs after blueprint parsing, before `load_from_blueprints`. Raises `LibraryLoadingError` on violations.
- **CLI commands** (`pipelex/cli/commands/pkg/`): `pipelex pkg init` scans `.mthds` files, generates skeleton `METHODS.toml` with auto-discovered domains and all pipes exported. `pipelex pkg list` finds and displays the manifest with Rich tables (package info, dependencies, exports).
- **Builder awareness** (`pipelex/builder/builder_loop.py`): `maybe_generate_manifest_for_output()` checks if an output directory contains multiple domains and generates a `METHODS.toml` if so. Hooked into both `pipe_cmd.py` and `build_core.py`.
- **Physical test data** (`tests/data/packages/`): `legal_tools/` (full manifest + multi-domain bundles), `minimal_package/` (minimal manifest), `standalone_bundle/` (no manifest), `invalid_manifests/` (6 negative test files).
- **Comprehensive tests**: 45+ new tests across 10 test files covering manifest model validation, TOML parsing, discovery, visibility, cross-package refs, CLI commands, and builder manifest generation. All domain/pipe names prefixed with `pkg_test_` to avoid collisions with the existing e2e test suite.

### Adaptations from the original brief

1. **Model name `MthdsPackageManifest`** (not `MethodsPackageManifest`): consistent with existing `MthdsFactory`, `MthdsDecodeError` naming.

2. **Dependencies TOML format uses alias as key**: the brief shows `[dependencies]\n"github.com/..." = { version = "^1.0.0", alias = "docproc" }` (address as key, alias inline). The implementation uses `[dependencies]\nscoring_lib = { address = "...", version = "2.0.0" }` (alias as key, address inline). This is more natural for the `->` syntax since the alias is the lookup key when resolving cross-package references.

3. **`collect_pipe_references()` made public**: renamed from `_collect_pipe_references()` on `PipelexBundleBlueprint` because the `PackageVisibilityChecker` (an external class) needs to call it. This is a minimal API change.

4. **`pkg_app` in `app.py` not `__init__.py`**: Ruff RUF067 prohibits logic in `__init__.py` files. Followed the existing `build/app.py` pattern: `__init__.py` is empty, `app.py` defines the Typer sub-group.

5. **Visibility check hooked into `library_manager.py` only**: the brief suggested hooking into both `library_manager.py` and `validate_bundle.py`. The library manager hook covers the main bundle loading path, which is sufficient. `validate_bundle.py` was left unchanged to keep the change surface minimal.

6. **Cross-package `validate_cross_package_references()` defined but not wired into runtime**: the method exists and is unit-tested, but `check_visibility_for_blueprints()` (the convenience function called by the library manager) only invokes `validate_all_pipe_references()`. This is intentional: `->` refs would already fail at the per-bundle level (the pipe wouldn't be found locally), so the cross-package checker is a preparatory API for Phase 3 when it will produce better error messages.

7. **Dependency version supports range syntax**: `PackageDependency.version` validates against Poetry/uv-style version constraint syntax (`^1.0.0`, `~1.0.0`, `>=1.0.0, <2.0.0`, wildcards). The package's own `MthdsPackageManifest.version` remains strict semver since it represents a concrete version, not a constraint.

---

## Phase 3: Cross-Package References + Local Dependency Resolution

### Goal

Implement the `alias->domain_path.name` syntax for cross-package references. Resolve dependencies locally (fetch from local paths or VCS). Wire `validate_cross_package_references()` into the runtime for better error messages.

This phase does NOT implement remote registry browsing or the Know-How Graph.

---

## What NOT to Do

- **Do NOT implement remote registry or Know-How Graph browsing.** That is Phase 5.
- **Do NOT rename the manifest** to anything other than `METHODS.toml`. The design docs are explicit about this name.
- **Do NOT rename Python classes or internal Pipelex types.** The standard is MTHDS; the implementation is Pipelex. Keep existing class names.

---

## Note on Client Project Brief

`mthds-client-project-update-brief.md` exists in the `implementation/` directory for propagating changes to cookbooks, tutorials, and client-facing documentation. After Phase 2 lands, that brief should be updated to reflect:
- The existence of `METHODS.toml` and what it means for project setup.
- The new `pipelex pkg init` and `pipelex pkg list` commands.
- The visibility model and its impact on how bundles are organized.
- Any changes to the builder output format.

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
| Design rationale | `Proposal -The Pipelex Package System.md` | §2, §4 |
