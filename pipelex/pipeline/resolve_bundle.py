"""Resolve a method into a normalized library crate, for a host (presentation-free core).

Two entry points, the host-facing siblings of the CLI's directory-based crate loader
(`pipelex.cli.commands.crate_loading.load_normalized_crate`):

- ``resolve_crate_from_method_dir`` resolves a method's tree a host received and wrote out, such as the tree the API
  server's crate routes write from a request's `files` map: the directory is loaded as the caller's own, the way
  ``validate_bundle`` loads a ``method_dir``, so its other files are the ones its steps read, and, while the host holds
  the tree in ``WRITTEN_METHOD_TREES``, its bundles are named by their tree paths.
- ``resolve_crate_from_contents`` resolves bundle contents held as strings, without touching the filesystem.

Same engine, same verdict vocabulary: an invalid library raises the one shared
``ValidateBundleError`` (carrying the structured ``validation_errors`` items every surface
renders), so a resolve verdict cannot drift from a validate verdict.

Resolution is static (parse → load → ``validate_library()`` → normalize): it deliberately runs
no dry-run sweep, matching `pipelex resolve` — the crate is emitted from a loaded **and
validated** library (D6), and runnability is `validate`'s vocabulary, not resolution's.
"""

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Sequence

from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.core.method_trees.file_references import BundleFileOrigin
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library
from pipelex.libraries.bundle_resources import check_submitted_files
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.pipe.exceptions import PipeLibraryError
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle_translation import translate_to_validate_bundle_error


def resolve_crate_from_contents(
    *,
    mthds_contents: list[str],
    mthds_sources: Sequence[str | None] | None = None,
    submitted_files: Mapping[str, bytes] | None = None,
) -> LibraryCrate:
    """Assemble, validate, and normalize a library crate from in-memory MTHDS contents.

    Mirrors ``validate_bundle``'s in-memory arm and its **loaded-on-success contract**: on
    success the freshly opened library is left loaded and current so the host can read live
    pipes from it (input templates, runner scaffolds) — the host then owns its teardown
    (``clear_current_library()`` + ``library_manager.teardown(library_id=...)``). On failure the
    library is torn down here and the caller's prior current-library is restored.

    Args:
        mthds_contents: MTHDS bundle contents (at least one) forming the closure to resolve.
        mthds_sources: Optional per-content logical sources (e.g. relative file paths), threaded
            onto each blueprint so diagnostics carry a real ``source``; a ``None`` entry leaves
            that content source-less. Must match ``mthds_contents`` in length when provided — a
            mismatch is a host-wiring bug.
        submitted_files: The files submitted with the contents that their steps read, such as a ``PipeDocGen``
            step's ``template_file``, keyed by canonical bundle-relative path. The load resolves the steps' references
            among them; the normalized crate, a standard artifact, carries neither them nor their tree.

    Returns:
        The normalized library crate (fully qualified, natives materialized, fingerprint set).

    Raises:
        ValidateBundleError: the produced negative verdict — the library could not be parsed,
            loaded, or validated; carries the structured validation-error items.
        PipelexUnexpectedError: host-wiring bug (empty contents, sources length mismatch).
        CrateNormalizationError: internal invariant violation in the normalization pass —
            deliberately not translated, it must surface as a server fault.
    """
    if not mthds_contents:
        msg = "mthds_contents must not be empty: provide at least one MTHDS content to resolve"
        raise PipelexUnexpectedError(msg)
    if mthds_sources is not None and len(mthds_sources) != len(mthds_contents):
        msg = "mthds_sources, when provided, must be a per-item source list matching mthds_contents in length"
        raise PipelexUnexpectedError(msg)

    library_manager = get_library_manager()
    with _resolving_library() as library_id:
        content_sources: list[str | None] = list(mthds_sources) if mthds_sources is not None else [None] * len(mthds_contents)
        with translate_to_validate_bundle_error():
            # Contents belong to no method tree: their steps read only the files submitted with them.
            blueprints = [
                MthdsParser.make_pipelex_bundle_blueprint(mthds_content=content, mthds_source=source, file_origin=BundleFileOrigin.SUBMITTED_FILES)
                for content, source in zip(mthds_contents, content_sources, strict=True)
            ]
            _reject_address_based_dependencies(blueprints=blueprints)
            if submitted_files:
                check_submitted_files(blueprints=blueprints, submitted_files=submitted_files)
                library_manager.add_submitted_files(library_id=library_id, submitted_files=submitted_files)
            # load_from_blueprints ends in load_from_crate, whose last step is
            # library.validate_library() — so a crate read after it satisfies the D6
            # "built only from a valid library" contract.
            library_manager.load_from_blueprints(library_id=library_id, blueprints=blueprints)
        crate = library_manager.get_crate(library_id)
        if crate is None:
            # Unreachable with non-empty contents (load_from_blueprints accumulated them), so a
            # None crate is an internal invariant break, not a caller-facing verdict.
            msg = "library crate unavailable after a successful bundle load"
            raise PipelexUnexpectedError(msg)
        return normalize_crate(crate, mthds_version=MTHDS_STANDARD_VERSION)


def resolve_crate_from_method_dir(*, method_dir: Path, methods_dirs: Sequence[Path] | None = None) -> LibraryCrate:
    """Load, validate, and normalize the library crate of a method's tree written out to a directory.

    The directory is loaded alone, as the caller's own library directory, exactly as ``validate_bundle`` loads a
    ``method_dir``: every bundle of the tree is loaded as a member of it, every other file is one a step may read, such
    as a ``PipeDocGen`` template, and ``methods_dirs``, laid out like ``.mthds/methods/``, hold the packages the caller
    ships with the method, searched first for an address-based reference. A tree the host holds in
    ``WRITTEN_METHOD_TREES`` (``pipelex.libraries.written_trees``) has its bundles named by their tree paths, so the
    diagnostics and the crate's ``source_map`` never name a path on the host. Resolution is static, as for contents: no
    dry run.

    Same **loaded-on-success contract** as ``resolve_crate_from_contents``: on success the library is left loaded and
    current, and the host owns its teardown; on failure it is torn down here and the caller's prior current library is
    restored.

    Args:
        method_dir: The directory of the method's tree, written as the tree holds it.
        methods_dirs: Directories laid out like ``.mthds/methods/``, holding the packages the method ships.

    Returns:
        The normalized library crate (fully qualified, natives materialized, fingerprint set).

    Raises:
        ValidateBundleError: the produced negative verdict — the method holds no bundle, or its library could not be
            parsed, loaded, or validated; carries the structured validation-error items.
        CrateNormalizationError: internal invariant violation in the normalization pass — deliberately not translated.
    """
    library_manager = get_library_manager()
    with _resolving_library() as library_id:
        with translate_to_validate_bundle_error():
            library_manager.load_libraries(
                library_id=library_id,
                library_dirs=[method_dir],
                methods_dirs=list(methods_dirs) if methods_dirs is not None else None,
            )
        crate = library_manager.get_crate(library_id)
        if crate is None:
            # A tree without a bundle loads nothing: the caller's method, so the caller's verdict, as `validate_bundle`
            # says of a method directory with no bundle.
            msg = "The method holds no .mthds bundle, so it has no crate to resolve."
            raise ValidateBundleError(message=msg)
        return normalize_crate(crate, mthds_version=MTHDS_STANDARD_VERSION)


@contextmanager
def _resolving_library() -> Generator[str, None, None]:
    """Open a library and make it current for one resolution, which leaves it loaded on success.

    On failure the library is torn down and the caller's prior current library restored, FIRST, so the guarantee holds
    even when the teardown raises (the same ordering as ``validate_bundle``).
    """
    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    prev_library_id = get_current_library_id_or_none()
    success = False
    try:
        set_current_library(library_id=library_id)
        yield library_id
        success = True
    finally:
        if not success:
            if prev_library_id is not None:
                set_current_library(library_id=prev_library_id)
            else:
                clear_current_library()
            library_manager.teardown(library_id=library_id)


def _reject_address_based_dependencies(*, blueprints: list[PipelexBundleBlueprint]) -> None:
    """Keep contents-only resolution independent from installed methods on the host filesystem."""
    for blueprint in blueprints:
        for pipe_ref, _context in blueprint.collect_pipe_references():
            if not QualifiedRef.has_cross_package_prefix(pipe_ref):
                continue
            alias, _remainder = QualifiedRef.split_cross_package_ref(pipe_ref)
            if QualifiedRef.is_address_based_alias(alias):
                msg = (
                    f"In-memory resolve cannot load address-based dependency '{alias}' from the host filesystem; "
                    "provide the dependency contents in the request or use directory-based resolution."
                )
                raise PipeLibraryError(msg)
