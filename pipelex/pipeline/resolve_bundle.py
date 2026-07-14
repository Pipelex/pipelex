"""Resolve in-memory MTHDS contents into a normalized library crate (presentation-free core).

This is the contents-based sibling of the CLI's directory-based crate loader
(`pipelex.cli.commands.crate_loading.load_normalized_crate`): a host that already holds the
bundle contents as strings — an HTTP API, an SDK — resolves them here without touching the
filesystem. Same engine, same verdict vocabulary: an invalid library raises the one shared
``ValidateBundleError`` (carrying the structured ``validation_errors`` items every surface
renders), so a resolve verdict cannot drift from a validate verdict.

Resolution is static (parse → load → ``validate_library()`` → normalize): it deliberately runs
no dry-run sweep, matching `pipelex resolve` — the crate is emitted from a loaded **and
validated** library (D6), and runnability is `validate`'s vocabulary, not resolution's.
"""

from typing import Sequence

from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.hub import (
    clear_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    set_current_library,
)
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.pipe.exceptions import PipeLibraryError
from pipelex.pipeline.validate_bundle import translate_to_validate_bundle_error


def resolve_crate_from_contents(*, mthds_contents: list[str], mthds_sources: Sequence[str | None] | None = None) -> LibraryCrate:
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
    library_id, _ = library_manager.open_library()
    success = False
    prev_library_id = get_current_library_id_or_none()
    try:
        set_current_library(library_id=library_id)
        content_sources: list[str | None] = list(mthds_sources) if mthds_sources is not None else [None] * len(mthds_contents)
        with translate_to_validate_bundle_error():
            blueprints = [
                PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=content, mthds_source=source)
                for content, source in zip(mthds_contents, content_sources, strict=True)
            ]
            _reject_address_based_dependencies(blueprints=blueprints)
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
        normalized = normalize_crate(crate, mthds_version=MTHDS_STANDARD_VERSION)
        success = True
        return normalized
    finally:
        if not success:
            # Restore the caller's outer current-library FIRST so the safety guarantee holds
            # even when teardown raises (same ordering rationale as validate_bundle).
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
