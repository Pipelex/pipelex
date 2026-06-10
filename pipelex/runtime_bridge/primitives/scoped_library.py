"""Per-call scoped library for crate-based execution/hydration outside Temporal workers."""

import uuid
from collections.abc import Generator
from contextlib import contextmanager

from kajson.class_registry import ClassRegistry
from kajson.kajson_manager import KajsonManager

from pipelex.hub import get_library_manager, scoped_current_library
from pipelex.libraries.library_crate import LibraryCrate


@contextmanager
def scoped_library_for_crate(library_crate: LibraryCrate | None, library_id_prefix: str) -> Generator[str | None, None, None]:
    """Open a per-call scoped library loaded from ``library_crate`` for the duration of the block.

    When ``library_crate`` is None this is a no-op (yields None): callers fall back to the
    library that was loaded into the active class registry at boot. Otherwise: opens a
    fresh library under a uuid-suffixed id, attaches a scoped ``ClassRegistry`` pre-seeded
    from the global one (so classes generated from the crate's inline structured concepts
    register into the scoped registry — discarded on teardown — rather than leaking into
    or colliding in the global Kajson registry), sets it as the current library, loads the
    crate, and tears everything down on the way out.

    The per-call uuid keying makes leaked-predecessor collisions structurally impossible,
    so plain ``open_library`` is correct here — ``open_fresh_library`` is only needed on
    the Temporal worker path, whose library ids are deterministic per run. This helper is
    deliberately NOT used by ``WfPipeRouter``: its teardown sequencing relative to the
    flush await IS the eviction-safety fix (H2), and folding it into a context manager
    would fight that ordering.
    """
    if library_crate is None:
        yield None
        return

    library_manager = get_library_manager()
    library_id = f"{library_id_prefix}_{uuid.uuid4().hex}"
    # open_library + set_class_registry live inside the try so a throw between opening
    # the library and reaching the yield still tears it down (the entry is registered in
    # the manager the moment open_library returns). scoped_current_library captures and
    # restores the prior current-library ContextVar, so a call made from within an
    # already-scoped library doesn't clobber the caller's context.
    library_opened = False
    try:
        _opened_library_id, library = library_manager.open_library(library_id=library_id)
        library_opened = True
        global_registry = KajsonManager.get_class_registry()
        scoped_registry = ClassRegistry()
        scoped_registry.register_classes_dict(global_registry.get_classes_dict())
        library.set_class_registry(scoped_registry)
        with scoped_current_library(library_id=library_id):
            library_manager.load_from_crate(library_id=library_id, crate=library_crate)
            yield library_id
    finally:
        if library_opened:
            library_manager.teardown(library_id=library_id)
