"""Build package index entries by scanning METHODS.toml and .mthds files.

Operates at blueprint level (string-based signatures) — no runtime class loading,
no side effects. Pure file scanning.
"""

from pathlib import Path

from pipelex import log
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.core.packages.dependency_resolver import collect_mthds_files, determine_exported_pipes
from pipelex.core.packages.discovery import MANIFEST_FILENAME
from pipelex.core.packages.exceptions import IndexBuildError
from pipelex.core.packages.index.models import (
    ConceptEntry,
    DomainEntry,
    PackageIndex,
    PackageIndexEntry,
    PipeSignature,
)
from pipelex.core.packages.manifest import MthdsPackageManifest
from pipelex.core.packages.manifest_parser import parse_methods_toml
from pipelex.core.packages.package_cache import get_default_cache_root


def build_index_entry_from_package(package_root: Path) -> PackageIndexEntry:
    """Build a PackageIndexEntry by parsing METHODS.toml and .mthds files.

    Args:
        package_root: Root directory of the package

    Returns:
        A PackageIndexEntry with all metadata, domains, concepts, and pipe signatures

    Raises:
        IndexBuildError: If the package cannot be indexed
    """
    manifest = _load_manifest(package_root)
    if manifest is None:
        msg = f"No METHODS.toml found in {package_root}"
        raise IndexBuildError(msg)

    mthds_files = collect_mthds_files(package_root)
    if not mthds_files:
        msg = f"No .mthds files found in {package_root}"
        raise IndexBuildError(msg)

    exported_pipe_codes = determine_exported_pipes(manifest)
    domains: dict[str, DomainEntry] = {}
    concepts: list[ConceptEntry] = []
    pipes: list[PipeSignature] = []
    errors: list[str] = []

    for mthds_file in mthds_files:
        try:
            blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=mthds_file)
        except Exception as exc:
            errors.append(f"{mthds_file}: {exc}")
            continue

        domain_code = blueprint.domain
        if domain_code not in domains:
            domains[domain_code] = DomainEntry(
                domain_code=domain_code,
                description=blueprint.description,
            )

        if blueprint.concept:
            for concept_code, concept_blueprint in blueprint.concept.items():
                concepts.append(_build_concept_entry(concept_code, domain_code, concept_blueprint))

        if blueprint.pipe:
            for pipe_code, pipe_blueprint in blueprint.pipe.items():
                is_exported = _is_pipe_exported(pipe_code, exported_pipe_codes, blueprint.main_pipe)
                pipes.append(
                    PipeSignature(
                        pipe_code=pipe_code,
                        pipe_type=pipe_blueprint.type,
                        domain_code=domain_code,
                        description=pipe_blueprint.description,
                        input_specs=dict(pipe_blueprint.inputs) if pipe_blueprint.inputs else {},
                        output_spec=pipe_blueprint.output,
                        is_exported=is_exported,
                    )
                )

    if errors:
        log.warning(f"Errors while indexing {package_root}: {errors}")

    dependency_addresses = [dep.address for dep in manifest.dependencies]
    dependency_aliases = {dep.alias: dep.address for dep in manifest.dependencies}

    return PackageIndexEntry(
        address=manifest.address,
        display_name=manifest.display_name,
        version=manifest.version,
        description=manifest.description,
        authors=list(manifest.authors),
        license=manifest.license,
        domains=sorted(domains.values(), key=lambda dom: dom.domain_code),
        concepts=concepts,
        pipes=pipes,
        dependencies=dependency_addresses,
        dependency_aliases=dependency_aliases,
    )


def build_index_from_cache(cache_root: Path | None = None) -> PackageIndex:
    """Build a PackageIndex by scanning all packages in the cache.

    The cache layout is ``cache_root/{address}/{version}/`` where address
    can have multiple path segments (e.g. ``github.com/org/repo``). We find
    package directories by scanning for ``METHODS.toml`` files recursively.

    Args:
        cache_root: Override for cache root directory (default: ~/.mthds/packages)

    Returns:
        A PackageIndex with entries for all cached packages
    """
    root = cache_root or get_default_cache_root()
    index = PackageIndex()

    if not root.is_dir():
        return index

    for manifest_path in sorted(root.rglob(MANIFEST_FILENAME)):
        package_dir = manifest_path.parent
        try:
            entry = build_index_entry_from_package(package_dir)
            index.add_entry(entry)
        except IndexBuildError as exc:
            log.warning(f"Skipping cached package {package_dir}: {exc}")

    return index


def build_index_from_project(project_root: Path) -> PackageIndex:
    """Build a PackageIndex from the current project and its resolved dependencies.

    Indexes the project itself (if it has METHODS.toml) plus any dependency
    packages found in the cache.

    Args:
        project_root: Root directory of the project

    Returns:
        A PackageIndex with the project and its dependencies
    """
    index = PackageIndex()

    manifest = _load_manifest(project_root)
    if manifest is None:
        return index

    mthds_files = collect_mthds_files(project_root)
    if mthds_files:
        try:
            entry = build_index_entry_from_package(project_root)
            index.add_entry(entry)
        except IndexBuildError as exc:
            log.warning(f"Could not index project: {exc}")

    # Index cached dependencies
    for dep in manifest.dependencies:
        if dep.path:
            # Local path dependency — index from the path
            dep_path = (project_root / dep.path).resolve()
            if dep_path.is_dir():
                try:
                    entry = build_index_entry_from_package(dep_path)
                    index.add_entry(entry)
                except IndexBuildError as exc:
                    log.warning(f"Could not index local dependency {dep.alias}: {exc}")
        else:
            # Remote dependency — look in cache
            _index_cached_dependency(index, dep.address)

    return index


def _load_manifest(package_root: Path) -> MthdsPackageManifest | None:
    """Load METHODS.toml from a package root, or return None."""
    manifest_path = package_root / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return None
    content = manifest_path.read_text(encoding="utf-8")
    return parse_methods_toml(content)


def _build_concept_entry(
    concept_code: str,
    domain_code: str,
    concept_blueprint: ConceptBlueprint | str,
) -> ConceptEntry:
    """Build a ConceptEntry from a concept blueprint."""
    if isinstance(concept_blueprint, str):
        return ConceptEntry(
            concept_code=concept_code,
            domain_code=domain_code,
            concept_ref=f"{domain_code}.{concept_code}",
            description=concept_blueprint,
        )

    structure_fields: list[str] = []
    if isinstance(concept_blueprint.structure, dict):
        for field_name, field_blueprint in concept_blueprint.structure.items():
            if isinstance(field_blueprint, ConceptStructureBlueprint):
                structure_fields.append(field_name)
            else:
                structure_fields.append(field_name)

    return ConceptEntry(
        concept_code=concept_code,
        domain_code=domain_code,
        concept_ref=f"{domain_code}.{concept_code}",
        description=concept_blueprint.description,
        refines=concept_blueprint.refines,
        structure_fields=structure_fields,
    )


def _is_pipe_exported(
    pipe_code: str,
    exported_pipe_codes: set[str] | None,
    main_pipe: str | None,
) -> bool:
    """Determine if a pipe is exported.

    A pipe is exported if:
    - exported_pipe_codes is None (no manifest = all public)
    - pipe_code is in the exported set
    - pipe_code is the main_pipe (auto-exported)
    """
    if exported_pipe_codes is None:
        return True
    return pipe_code in exported_pipe_codes or pipe_code == main_pipe


def _index_cached_dependency(index: PackageIndex, address: str) -> None:
    """Try to index a remote dependency from the cache."""
    cache_root = get_default_cache_root()
    address_dir = cache_root / address
    if not address_dir.is_dir():
        return

    # Index the latest version found in cache
    version_dirs = sorted(address_dir.iterdir(), reverse=True)
    for version_dir in version_dirs:
        if version_dir.is_dir():
            try:
                entry = build_index_entry_from_package(version_dir)
                index.add_entry(entry)
                return
            except IndexBuildError:
                continue
