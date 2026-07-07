from typing import Any

from kajson.class_registry import ClassRegistry
from kajson.kajson_manager import KajsonManager

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.hub import get_library_manager, set_current_library
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.runtime_bridge.primitives.hydration import hydrate_working_memory


def rehydrate_library_and_memory(
    *,
    library_id: str,
    crate: LibraryCrate,
    working_memory_raw: dict[str, Any] | None,
) -> WorkingMemory | None:
    """Open a fresh library from a transported crate and hydrate a transported working memory.

    This is the shared rehydration sequence used on the far side of any transport boundary — the
    Temporal workflow (``wf_pipe_router``) and the in-sandbox entrypoint both need to reconstruct a
    live library + typed working memory from the same ``(crate, working_memory_raw)`` payload.
    Extracting it keeps the two in lockstep (decision 7 / DRY) instead of hand-copying the sequence.

    Steps, in order (order matters):

    1. Create a per-run ``ClassRegistry`` pre-seeded from the global one, so this run's dynamically
       generated concept classes register into an isolated registry rather than leaking globally.
    2. Open a fresh library under ``library_id`` and attach the registry; make it the current library
       so the factory and hydrator resolve classes against it.
    3. ``load_from_crate`` — rebuilds domains/concepts/pipes and registers the dynamic classes.
    4. Hydrate the working memory (needs step 3 to have registered the classes it references).

    Returns the hydrated WorkingMemory, or None when there was nothing to hydrate.
    """
    global_registry = KajsonManager.get_class_registry()
    run_registry = ClassRegistry()
    run_registry.register_classes_dict(global_registry.get_classes_dict())

    library_manager = get_library_manager()
    library = library_manager.open_fresh_library(library_id=library_id)
    library.set_class_registry(run_registry)
    set_current_library(library_id=library_id)

    library_manager.load_from_crate(library_id=library_id, crate=crate)

    if working_memory_raw is None:
        return None
    return hydrate_working_memory(working_memory_raw)
