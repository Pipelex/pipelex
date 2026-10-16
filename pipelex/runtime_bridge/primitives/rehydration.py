from collections.abc import Mapping
from typing import Any

from mthds.method_tree.models import MethodTree

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.interpreter_hub import get_library_manager, set_current_library
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.runtime_bridge.primitives.hydration import hydrate_working_memory


def rehydrate_library_and_memory(
    *,
    library_id: str,
    crate: LibraryCrate,
    working_memory_raw: dict[str, Any] | None,
    is_crate_prevalidated: bool = False,
    written_pipe_trees: Mapping[str, MethodTree] | None = None,
) -> WorkingMemory | None:
    """Open a fresh library from a transported crate and hydrate a transported working memory.

    This is the canonical rehydration sequence for the far side of a transport boundary: any
    process that receives a ``(crate, working_memory_raw)`` payload — such as the in-sandbox
    PipeFunc entrypoint — must rebuild a live library and typed working memory this way.
    Out-of-tree orchestration backends need the same sequence; keeping it as a core primitive
    gives them one function to call instead of hand-copying the steps.

    Steps, in order (order matters):

    1. Open a fresh library under ``library_id`` and make it the current library, so the factory and
       hydrator resolve classes against it. The library arrives carrying its own ``ClassRegistry``
       pre-seeded from the process-global one (``LibraryManager.open_library`` attaches it), which is
       what keeps this run's dynamically generated concept classes out of every other library.
    2. ``load_from_crate`` — rebuilds domains/concepts/pipes and registers the dynamic classes.
    3. Hydrate the working memory (needs step 2 to have registered the classes it references).

    ``is_crate_prevalidated`` skips the pipes' validation, for a crate the sender validated where it was assembled,
    such as the one a `PipeFunc` call carries to a sandbox, whose other steps may name files of trees the sandbox
    never receives. ``written_pipe_trees`` are the trees this process wrote out for a step to run in, by that step's
    pipe ref, such as the tree of a `PipeFunc` call written for its function to import: that step, and no other, is
    built in it.

    Returns the hydrated WorkingMemory, or None when there was nothing to hydrate.
    """
    library_manager = get_library_manager()
    library_manager.open_fresh_library(library_id=library_id)
    set_current_library(library_id=library_id)

    library_manager.load_from_crate(
        library_id=library_id, crate=crate, is_crate_prevalidated=is_crate_prevalidated, written_pipe_trees=written_pipe_trees
    )

    if working_memory_raw is None:
        return None
    return hydrate_working_memory(working_memory_raw)
