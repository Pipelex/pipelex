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

from typing import TYPE_CHECKING

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.runtime_bridge.primitives.hydration import hydrate_working_memory
from pipelex.runtime_bridge.primitives.scoped_library import scoped_library_for_crate

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

    with scoped_library_for_crate(library_crate, library_id_prefix="rehydrate"):
        pipe_output.working_memory = hydrate_working_memory(pipe_output.working_memory_raw)
        pipe_output.working_memory_raw = None

    return pipe_output
