"""A working memory as it crosses into a leaf: dumped for transport, with the concepts that type it again on the far side.

A step that hands part of its memory to a content-generation leaf, such as the context an LLM prompt renders against
(`pipelex.cogt.llm.unrendered_llm_prompt`), hands it on a host runtime across an activity boundary, into a worker that
may never have loaded the run's method. A typed `WorkingMemory` does not cross that boundary: a stuff whose concept a
bundle declares holds an instance of a class the run's library built (`exec`'d into `builtins`), which no other process
can decode. So the memory crosses the way a pipe's output already does, as `WorkingMemory.dump_for_transport`, beside
what the far side needs to type it again: the concepts and domains of the run's crate, with none of its pipes, and the
whole crate's fingerprint, by which a process holding the run's own library types it there.

Packing and unpacking need the run's library, which lives in the interpreter layer, so the kernel layer holds only this
seam: `TransportedMemory`, `MemoryTransportProtocol`, and the in-process transport the runtime hub serves until the
interpreter installs its own (`pipelex.runtime_bridge.primitives.memory_transport`) when it boots. A packed memory also
keeps the typed memory it was packed from, never serialized, so the leaf of an in-process run renders against the
operator's own stuffs and loads their stored values onto them, as it always did.
"""

from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager
from typing import Any, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr
from typing_extensions import override

from pipelex.core.memory.exceptions import MemoryTransportError
from pipelex.core.memory.working_memory import WorkingMemory


class TransportedMemory(BaseModel):
    """A working memory in its transport form, with the run's concepts when a stuff needs them to be typed again.

    Attributes:
        working_memory_raw: The memory, as `WorkingMemory.dump_for_transport` writes it.
        crate_fingerprint: The fingerprint of the run's whole crate, by which a process holding the run's library types
            the memory in it. ``None`` when the memory holds only native stuffs, or when the run's library has no crate.
        concepts_crate: The concepts and domains of the run's crate, with none of its pipes, as JSON, which type the
            memory in a process that does not hold the run's library. ``None`` exactly when `crate_fingerprint` is.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    working_memory_raw: dict[str, Any] = Field(default_factory=dict)
    crate_fingerprint: str | None = None
    concepts_crate: dict[str, Any] | None = None

    # The typed memory this was packed from, in the process that packed it. A private attribute is never serialized, so
    # a copy decoded on the far side of a boundary holds none and is typed again from its transport form.
    _in_process_memory: WorkingMemory | None = PrivateAttr(default=None)

    @classmethod
    def make_in_process(
        cls,
        *,
        working_memory: WorkingMemory,
        crate_fingerprint: str | None = None,
        concepts_crate: dict[str, Any] | None = None,
    ) -> Self:
        """The memory packed in this process, keeping the typed memory for a leaf that runs in the same process."""
        transported = cls(working_memory_raw=working_memory.dump_for_transport(), crate_fingerprint=crate_fingerprint, concepts_crate=concepts_crate)
        transported._in_process_memory = working_memory
        return transported

    @property
    def in_process_memory(self) -> WorkingMemory | None:
        """The typed memory this was packed from, when this process packed it; ``None`` once it crossed a boundary."""
        return self._in_process_memory


class MemoryTransportProtocol(Protocol):
    """Packs a working memory for a leaf, and types it again where the leaf runs."""

    def pack(self, *, working_memory: WorkingMemory) -> TransportedMemory:
        """The memory in its transport form, with the run's concepts when one of its stuffs needs them."""
        ...

    def unpacked(self, *, transported_memory: TransportedMemory) -> AbstractContextManager[WorkingMemory]:
        """The typed memory, for the block: the one packed in this process, or one typed again from the transport form.

        A memory typed again from its concepts is typed in a library holding them, current for the block, so what renders
        against it inside the block resolves the run's concepts.
        """
        ...


class InProcessMemoryTransport(MemoryTransportProtocol):
    """The transport of a process booted with the kernel layer alone: its leaves run where their memory was packed.

    It packs no concepts, which only a loaded library holds, and unpacks only a memory packed in this process.
    """

    @override
    def pack(self, *, working_memory: WorkingMemory) -> TransportedMemory:
        return TransportedMemory.make_in_process(working_memory=working_memory)

    @override
    @contextmanager
    def unpacked(self, *, transported_memory: TransportedMemory) -> Generator[WorkingMemory, None, None]:
        in_process_memory = transported_memory.in_process_memory
        if in_process_memory is not None:
            yield in_process_memory
            return
        if not transported_memory.working_memory_raw.get("root"):
            yield WorkingMemory()
            return
        msg = (
            "A working memory that crossed a process boundary cannot be typed again in a process booted with the kernel layer alone: "
            "typing it needs the interpreter's memory transport"
        )
        raise MemoryTransportError(msg)


#: The transport the runtime hub serves until the interpreter installs its own.
IN_PROCESS_MEMORY_TRANSPORT = InProcessMemoryTransport()
