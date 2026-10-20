"""Resolve a method into a normalized library crate, for a host (presentation-free core).

``resolve_crate_from_method_dir`` is the host-facing sibling of the CLI's directory-based crate loader
(`pipelex.cli.commands.crate_loading.load_normalized_crate`). It resolves a method's tree a host received and wrote out,
such as the tree the API server's crate routes write from a request's `files` map or fetch for a `method_ref`: the
directory is loaded as the caller's own, the way ``validate_bundle`` loads a ``method_dir``, so its other files are the
ones its steps read, and, while the host holds the tree in ``WRITTEN_METHOD_TREES``, its bundles are named by their tree
paths.

It resolves statically from what the caller sent: a package the method calls by its address is loaded only from the
packages shipped with it, and one nothing shipped is refused with ``unshipped_address_dependency_message``, never looked
up among the methods installed on the host or fetched.

Same engine, same verdict vocabulary: an invalid library raises the one shared
``ValidateBundleError`` (carrying the structured ``validation_errors`` items every surface
renders), so a resolve verdict cannot drift from a validate verdict.

Resolution is static (parse → load → ``validate_library()`` → normalize): it deliberately runs
no dry-run sweep, matching `pipelex resolve` — the crate is emitted from a loaded **and
validated** library (D6), and runnability is `validate`'s vocabulary, not resolution's.
"""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Sequence

from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION

from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.methods.address_dependencies import AddressDependencySources
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle_translation import translate_to_validate_bundle_error


def resolve_crate_from_method_dir(*, method_dir: Path, methods_dirs: Sequence[Path] | None = None) -> LibraryCrate:
    """Load, validate, and normalize the library crate of a method's tree written out to a directory.

    The directory is loaded alone, as the caller's own library directory, exactly as ``validate_bundle`` loads a
    ``method_dir``: every bundle of the tree is loaded as a member of it, every other file is one a step may read, such
    as a ``PipeDocGen`` template, and ``methods_dirs``, laid out like ``.mthds/methods/``, hold the packages the caller
    ships with the method, the only place an address-based reference is looked up: one they do not answer is refused,
    since a static resolution reads no method installed on the host and fetches nothing. A tree the host holds in
    ``WRITTEN_METHOD_TREES`` (``pipelex.libraries.written_trees``) has its bundles named by their tree paths, so the
    diagnostics and the crate's ``source_map`` never name a path on the host. Resolution is static: no dry run.

    It honours ``validate_bundle``'s **loaded-on-success contract**: on success the library is left loaded and current,
    so the host can read live pipes from it, and the host owns its teardown (``clear_current_library()`` and
    ``library_manager.teardown(library_id=...)``); on failure it is torn down here and the caller's prior current library
    is restored.

    Args:
        method_dir: The directory of the method's tree, written as the tree holds it.
        methods_dirs: Directories laid out like ``.mthds/methods/``, holding the packages the method ships.

    Returns:
        The normalized library crate (fully qualified, natives materialized, fingerprint set).

    Raises:
        ValidateBundleError: the produced negative verdict — the method holds no bundle, calls a package by its address
            that nothing shipped, or its library could not be parsed, loaded, or validated; carries the structured
            validation-error items.
        CrateNormalizationError: internal invariant violation in the normalization pass — deliberately not translated.
    """
    library_manager = get_library_manager()
    with _resolving_library() as library_id:
        with translate_to_validate_bundle_error():
            library_manager.load_libraries(
                library_id=library_id,
                library_dirs=[method_dir],
                methods_dirs=list(methods_dirs) if methods_dirs is not None else None,
                address_dependency_sources=AddressDependencySources.SHIPPED,
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
