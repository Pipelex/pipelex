"""Submitter-side rehydration of PipeOutput received from a Temporal workflow.

The workflow side (`WfPipeRouter`) dehydrates `PipeOutput.working_memory` into
`working_memory_raw` for transit. The submitter must rebuild the typed
`WorkingMemory` after the workflow returns.

When the submitter has loaded the bundle locally (via `PIPELEXPATH` or by
explicit setup), the dynamic concept classes live in the global class registry
and a plain `hydrate_working_memory(...)` call works. But when the submitter is
a remote API client that built the `PipeJob` from a serialized `LibraryCrate`
without loading it into the global registry, hydration would fail (or worse,
silently degrade) on dynamic concept fields.

`rehydrate_pipe_output_with_crate` mirrors what `WfPipeRouter` does on the
worker side: open a per-call scoped Library, pre-seed a scoped `ClassRegistry`
from the global, load the crate into it, hydrate inside the scope, then tear
down — leaving the submitter's global registry untouched.
"""

import uuid
from typing import TYPE_CHECKING

from kajson.class_registry import ClassRegistry
from kajson.kajson_manager import KajsonManager

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.hub import clear_current_library, get_current_library, get_library_manager, set_current_library
from pipelex.temporal.tprl_pipe.hydration import hydrate_working_memory

if TYPE_CHECKING:
    from pipelex.libraries.library_crate import LibraryCrate


def rehydrate_pipe_output_with_crate(
    pipe_output: PipeOutput,
    library_crate: "LibraryCrate | None",
) -> PipeOutput:
    """Rehydrate `pipe_output.working_memory_raw` into a typed WorkingMemory.

    When `library_crate` is provided, opens a fresh per-call scoped Library,
    loads the crate into it, hydrates inside the scope, and tears down — so
    callers that did not load the bundle into their global registry still get
    a correct typed WorkingMemory. When `library_crate` is None, falls back to
    the active class registry (built-ins + whatever PIPELEXPATH loaded).

    Mutates `pipe_output` in place: sets `working_memory`, clears
    `working_memory_raw`. Returns the same instance for call-chain ergonomics.
    """
    if pipe_output.working_memory_raw is None:
        return pipe_output

    if library_crate is None:
        pipe_output.working_memory = hydrate_working_memory(pipe_output.working_memory_raw)
        pipe_output.working_memory_raw = None
        return pipe_output

    library_manager = get_library_manager()
    rehydration_library_id = f"rehydrate_{uuid.uuid4().hex[:8]}"
    prev_library_id = _get_current_library_id_or_none()
    library_opened = False
    library_set_as_current = False
    try:
        _lib_id, rehydration_library = library_manager.open_library(library_id=rehydration_library_id)
        library_opened = True

        global_registry = KajsonManager.get_class_registry()
        scoped_registry = ClassRegistry()
        scoped_registry.register_classes_dict(global_registry.get_classes_dict())
        rehydration_library.set_class_registry(scoped_registry)

        set_current_library(library_id=rehydration_library_id)
        library_set_as_current = True
        library_manager.load_from_crate(library_id=rehydration_library_id, crate=library_crate)
        pipe_output.working_memory = hydrate_working_memory(pipe_output.working_memory_raw)
        pipe_output.working_memory_raw = None
    finally:
        try:
            if library_opened:
                library_manager.teardown(library_id=rehydration_library_id)
        finally:
            if library_set_as_current:
                if prev_library_id is not None:
                    set_current_library(library_id=prev_library_id)
                else:
                    clear_current_library()

    return pipe_output


def _get_current_library_id_or_none() -> str | None:
    """Get the current library_id without raising if none is set."""
    try:
        return get_current_library()
    except RuntimeError:
        return None
