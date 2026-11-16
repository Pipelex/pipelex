"""The interpreter's memory transport: a leaf's working memory packed with the run's concepts, and typed again by them.

The kernel layer holds the seam (`pipelex.core.memory.memory_transport`); this is what `Pipelex.setup` installs on the
runtime hub. Packing dumps the memory for transport and, when a stuff needs a library to be typed again (its concept is a
bundle's, or names no content class, such as `native.Anything`, whose contents carry their own classes), attaches the
concepts and domains of the current library's crate, with none of its pipes, and the crate's fingerprint. Unpacking
hands back the memory packed in this process when there is one; otherwise it hydrates the transport form, in the run's
own library when this process holds it, in a library loaded from the concepts it carries otherwise
(`pipelex.libraries.concepts_libraries`), or against the native concepts alone when it carries none.
"""

import threading
from collections import OrderedDict
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from typing_extensions import override

from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.memory_transport import MemoryTransportProtocol, TransportedMemory
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.interpreter_hub import get_current_library_id_or_none, get_library_manager
from pipelex.libraries.concepts_libraries import typed_by_run_concepts
from pipelex.runtime_bridge.primitives.hydration import hydrate_working_memory

# How many concepts-only crates the transport keeps, the least recently packed dropped first: a worker running steps
# for a handful of methods dumps each one's concepts once.
_CONCEPTS_CRATE_CAPACITY = 8


def _needs_concepts(*, working_memory: WorkingMemory) -> bool:
    """Whether a stuff of the memory can only be typed again by a library holding the run's concepts.

    A native concept with a content class is typed by the native set, which every process holds. A concept a bundle
    declares is not, and neither are the contents of a concept naming no content class, which may be any class the run
    built.
    """
    return any(not Concept.is_native_concept(stuff.concept) or not stuff.concept.declares_a_structure_class for stuff in working_memory.root.values())


class LibraryMemoryTransport(MemoryTransportProtocol):
    """Packs a leaf's memory with the current library's concepts, and types it again in a library holding them."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # The concepts-only crate of each crate packed, as JSON, by the whole crate's fingerprint: building and dumping
        # it costs more than the step, and every LLM step of a run packs the same one.
        self._concepts_crates: OrderedDict[str, dict[str, Any]] = OrderedDict()

    @override
    def pack(self, *, working_memory: WorkingMemory) -> TransportedMemory:
        if not _needs_concepts(working_memory=working_memory):
            return TransportedMemory.make_in_process(working_memory=working_memory)
        library_id = get_current_library_id_or_none()
        crate = get_library_manager().get_crate(library_id=library_id) if library_id is not None else None
        if crate is None:
            # No crate to carry: the memory is typed again only where the run's library is current, such as in this process.
            return TransportedMemory.make_in_process(working_memory=working_memory)
        with self._lock:
            concepts_crate = self._concepts_crates.get(crate.fingerprint)
            if concepts_crate is None:
                concepts_crate = crate.concepts_only().model_dump(mode="json")
                self._concepts_crates[crate.fingerprint] = concepts_crate
                while len(self._concepts_crates) > _CONCEPTS_CRATE_CAPACITY:
                    self._concepts_crates.popitem(last=False)
            else:
                self._concepts_crates.move_to_end(crate.fingerprint)
        return TransportedMemory.make_in_process(working_memory=working_memory, crate_fingerprint=crate.fingerprint, concepts_crate=concepts_crate)

    @override
    @contextmanager
    def unpacked(self, *, transported_memory: TransportedMemory) -> Generator[WorkingMemory, None, None]:
        in_process_memory = transported_memory.in_process_memory
        if in_process_memory is not None:
            yield in_process_memory
            return
        if transported_memory.crate_fingerprint is None or transported_memory.concepts_crate is None:
            yield hydrate_working_memory(transported_memory.working_memory_raw)
            return
        with typed_by_run_concepts(crate_fingerprint=transported_memory.crate_fingerprint, concepts_crate=transported_memory.concepts_crate):
            yield hydrate_working_memory(transported_memory.working_memory_raw)
