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
from pipelex.hub import get_library_manager, scoped_current_library
from pipelex.runtime_bridge.primitives.hydration import hydrate_working_memory

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
    rehydration_library_id = f"rehydrate_{uuid.uuid4().hex}"
    # open_library + set_class_registry live inside the try so a throw before the yield
    # still tears the library down. scoped_current_library captures and restores the
    # prior current-library ContextVar, so this rehydration doesn't clobber the caller's
    # context. Mirrors bridge._scoped_library_for_crate.
    library_opened = False
    try:
        _opened_library_id, rehydration_library = library_manager.open_library(library_id=rehydration_library_id)
        library_opened = True

        global_registry = KajsonManager.get_class_registry()
        scoped_registry = ClassRegistry()
        scoped_registry.register_classes_dict(global_registry.get_classes_dict())
        rehydration_library.set_class_registry(scoped_registry)

        with scoped_current_library(library_id=rehydration_library_id):
            library_manager.load_from_crate(library_id=rehydration_library_id, crate=library_crate)
            pipe_output.working_memory = hydrate_working_memory(pipe_output.working_memory_raw)
            pipe_output.working_memory_raw = None
    finally:
        if library_opened:
            library_manager.teardown(library_id=rehydration_library_id)

    return pipe_output
