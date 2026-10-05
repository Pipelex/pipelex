"""What a pipe stores in the working memory it runs on besides its own result, as the static analyses of its caller read it.

A PipeSequence runs its steps on its caller's memory, a PipeCondition runs its chosen outcome there, and a PipeParallel with
`add_each_output` adds each branch's result to it, so each stores names there that its caller's step never named. A calling
PipeSequence has three static analyses, and all three read those names from this one model, `MemoryWrite`, computed by the
pipe's `memory_writes`: the typed flow takes the spec a name holds, the needed inputs count a name always written as stored,
and the absence-taint walk takes why the name may hold an absence. A batched step and a PipeBatch run their pipe on copies
of the memory, so they store nothing beyond their result.

`SlotTaint` lives here, beside the model that carries it, so that `PipeAbstract` can declare `memory_writes`; the rest of
the absence-taint pass is in `pipelex.pipe_controllers.absence_taint`.
"""

from pydantic import BaseModel, ConfigDict
from pydantic.dataclasses import dataclass

from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec


@dataclass(frozen=True)
class SlotTaint:
    """A maybe-absent slot: where the absence originates and how it propagated here."""

    source: str
    origin_slot_name: str
    chain: tuple[str, ...] = ()

    def describe(self) -> str:
        description = f"Absence origin: {self.source}."
        if self.chain:
            description += f" Propagation: {' → '.join(self.chain)}."
        return description


class MemoryWrite(BaseModel):
    """What a pipe stores under one name of the memory it runs on, besides its result."""

    model_config = ConfigDict(frozen=True)

    # The spec of the value stored, `None` when it cannot be typed: a pipe that does not resolve stored it, or the outcomes
    # of a condition store it under different specs.
    stuff_spec: StuffSpec | None
    # Why the name may hold an absence once the pipe returns, `None` when it always holds a value; a list never holds one.
    absence: SlotTaint | None = None
    # Whether every run of the pipe that returns stores the name. A run that does not, a condition's outcome that stores
    # nothing under it, its `continue` outcome included, leaves the caller's value in place. A pipe skipped for an absent
    # plain input still stores what it always stores, as an absence or an empty list (`PipeAbstract.lifted_companion_slots`).
    is_always_written: bool = True


def is_same_value_spec(*, first_spec: StuffSpec | None, second_spec: StuffSpec | None) -> bool:
    """Whether two specs type the same value: the same concept and multiplicity. Presence aside, which an absence carries."""
    if first_spec is None or second_spec is None:
        return False
    return first_spec.concept == second_spec.concept and first_spec.multiplicity == second_spec.multiplicity


def merge_alternative_writes(*, alternatives: list[dict[str, MemoryWrite]]) -> dict[str, MemoryWrite]:
    """What a pipe stores when exactly one of several alternatives runs, as a condition runs one of its outcomes.

    A name is always written only if every alternative always writes it. It may hold an absence if any alternative may leave
    one. It keeps a spec only if every alternative storing it stores the same value spec; an alternative that does not store
    it leaves the caller's value, which the caller merges with what the name held before (`is_always_written` is then false).
    """
    merged_writes: dict[str, MemoryWrite] = {}
    for alternative_writes in alternatives:
        for written_name in alternative_writes:
            if written_name in merged_writes:
                continue
            name_writes = [other_writes.get(written_name) for other_writes in alternatives]
            stored_writes = [name_write for name_write in name_writes if name_write is not None]
            first_spec = stored_writes[0].stuff_spec
            is_typed = all(is_same_value_spec(first_spec=first_spec, second_spec=name_write.stuff_spec) for name_write in stored_writes)
            absences = [name_write.absence for name_write in stored_writes if name_write.absence is not None]
            merged_writes[written_name] = MemoryWrite(
                stuff_spec=first_spec if is_typed else None,
                absence=absences[0] if absences else None,
                is_always_written=all(name_write is not None and name_write.is_always_written for name_write in name_writes),
            )
    return merged_writes


def taint_after_write(*, prior_taint: SlotTaint | None, memory_write: MemoryWrite) -> SlotTaint | None:
    """Why a name may hold an absence once a pipe stored it: the write's own reason, or, when the pipe may leave the name as
    it was, the reason it had before.
    """
    if memory_write.absence is not None:
        return memory_write.absence
    if memory_write.is_always_written:
        return None
    return prior_taint
