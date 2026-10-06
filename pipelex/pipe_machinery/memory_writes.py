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

from typing import NamedTuple

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


class StoredSpec(BaseModel):
    """One of the values a name may hold once a step returns, and what stores it, as a message names it."""

    model_config = ConfigDict(frozen=True)

    # What stores the value, written to precede "as 'X'", e.g. "outcome 'stash_parcel' of pipe 'stash_by_mode'".
    stored_by: str
    stuff_spec: StuffSpec
    # Whether a pipe step's run stored the value, so that a step reading it takes the concept of a value stored as `Anything`
    # or `Dynamic` to be the one it reads, which only the run knows. A condition's outcomes are pipe stores. The value a name
    # held before a step that may leave it is not one when the sequence's caller passed it under a declared input or a binding
    # step stored it (`FlowSlot.is_stored_by_pipe_step`): a step reading it is held to its spec, as to any other declaration.
    is_stored_by_pipe_step: bool = True


class SpecDisagreement(BaseModel):
    """Why a name has no spec before the run although every value it may hold has one: the values have different specs.

    That is a condition whose outcomes store the name under different specs, or one whose outcomes store a value of another
    spec than the one an outcome storing nothing leaves. Unlike a value a pipe that does not resolve stores, which nothing
    can type before the run, the disagreement is seen at validation, so a binding reading the name is refused there.
    """

    model_config = ConfigDict(frozen=True)

    stored_specs: tuple[StoredSpec, ...]

    def describe(self, *, relative_to_domain: str) -> str:
        """Each value and what stores it, e.g. "outcome 'stash_crate' of pipe 'stash_by_mode' as 'Crate'; outcome ... as 'Parcel'"."""
        return "; ".join(
            f"{stored_spec.stored_by} as '{stored_spec.stuff_spec.to_bundle_representation(relative_to_domain=relative_to_domain)}'"
            for stored_spec in self.stored_specs
        )


class MemoryWrite(BaseModel):
    """What a pipe stores under one name of the memory it runs on, besides its result."""

    model_config = ConfigDict(frozen=True)

    # The spec of the value stored, `None` when it cannot be typed: a pipe that does not resolve stored it, or the values the
    # name may hold have different specs, which `disagreement` then says.
    stuff_spec: StuffSpec | None
    # Set only when `stuff_spec` is `None` because the values the name may hold have different specs.
    disagreement: SpecDisagreement | None = None
    # Why the name may hold an absence once the pipe returns, `None` when it always holds a value; a list never holds one.
    absence: SlotTaint | None = None
    # Whether every run of the pipe that returns stores the name. A run that does not, a condition's outcome that stores
    # nothing under it, its `continue` outcome included, leaves the caller's value in place. A pipe skipped for an absent
    # plain input still stores what it always stores, as an absence or an empty list (`PipeAbstract.lifted_companion_slots`).
    is_always_written: bool = True


def possible_values(
    *, stored_by: str, stuff_spec: StuffSpec | None, disagreement: SpecDisagreement | None, is_stored_by_pipe_step: bool
) -> tuple[StoredSpec, ...] | None:
    """The values one side may leave under a name, as a disagreement lists them: the one value of a typed side, which `stored_by`
    names, or each value the side's own disagreement lists, with what stored it. `None` for a side nothing could type before
    the run, a pipe that does not resolve having stored it.
    """
    if stuff_spec is not None:
        return (StoredSpec(stored_by=stored_by, stuff_spec=stuff_spec, is_stored_by_pipe_step=is_stored_by_pipe_step),)
    if disagreement is not None:
        return disagreement.stored_specs
    return None


def is_same_value_spec(*, first_spec: StuffSpec | None, second_spec: StuffSpec | None) -> bool:
    """Whether two specs type the same value: the same concept and multiplicity. Presence aside, which an absence carries."""
    if first_spec is None or second_spec is None:
        return False
    return first_spec.concept == second_spec.concept and first_spec.multiplicity == second_spec.multiplicity


class AlternativeWrites(NamedTuple):
    """What one alternative stores, and how a message names it, e.g. "outcome 'stash_parcel' of pipe 'stash_by_mode'"."""

    label: str
    writes: dict[str, MemoryWrite]


def merge_alternative_writes(*, alternatives: list[AlternativeWrites]) -> dict[str, MemoryWrite]:
    """What a pipe stores when exactly one of several alternatives runs, as a condition runs one of its outcomes.

    A name is always written only if every alternative always writes it. It may hold an absence if any alternative may leave
    one. It keeps a spec only if every alternative storing it stores the same value spec; an alternative that does not store
    it leaves the caller's value, which the caller merges with what the name held before (`is_always_written` is then false).
    A name left untyped records why when it is seen before the run (`SpecDisagreement`), listing every value an alternative
    may leave: the alternatives typing it store it under different specs, or one of them stores it with a disagreement of its
    own. Otherwise an alternative that could not type it, a pipe that does not resolve having stored it, leaves it untyped
    with no disagreement.
    """
    merged_writes: dict[str, MemoryWrite] = {}
    for alternative in alternatives:
        for written_name in alternative.writes:
            if written_name in merged_writes:
                continue
            name_writes = [other.writes.get(written_name) for other in alternatives]
            labeled_writes = [(other.label, other.writes[written_name]) for other in alternatives if written_name in other.writes]
            stored_writes = [name_write for _, name_write in labeled_writes]
            first_spec = stored_writes[0].stuff_spec
            is_typed = all(is_same_value_spec(first_spec=first_spec, second_spec=name_write.stuff_spec) for name_write in stored_writes)
            absences = [name_write.absence for name_write in stored_writes if name_write.absence is not None]
            merged_writes[written_name] = MemoryWrite(
                stuff_spec=first_spec if is_typed else None,
                disagreement=None if is_typed else _alternatives_disagreement(labeled_writes=labeled_writes),
                absence=absences[0] if absences else None,
                is_always_written=all(name_write is not None and name_write.is_always_written for name_write in name_writes),
            )
    return merged_writes


def _alternatives_disagreement(*, labeled_writes: list[tuple[str, MemoryWrite]]) -> SpecDisagreement | None:
    """Why the alternatives storing a name leave it untyped, when it is seen before the run: the specs they store disagree, or
    one of them stores the name with a disagreement of its own. The disagreement lists every value an alternative may leave,
    those its own disagreement lists included, so that a step reading the name is checked against each. An alternative nothing
    could type, a pipe that does not resolve having stored the name, lists none. `None` when the values listed agree.
    """
    stored_specs: list[StoredSpec] = []
    for label, name_write in labeled_writes:
        alternative_values = possible_values(
            stored_by=label, stuff_spec=name_write.stuff_spec, disagreement=name_write.disagreement, is_stored_by_pipe_step=True
        )
        if alternative_values is not None:
            stored_specs.extend(alternative_values)
    first_spec = stored_specs[0].stuff_spec if stored_specs else None
    if any(not is_same_value_spec(first_spec=first_spec, second_spec=stored_spec.stuff_spec) for stored_spec in stored_specs):
        return SpecDisagreement(stored_specs=tuple(stored_specs))
    return None


def taint_after_write(*, prior_taint: SlotTaint | None, memory_write: MemoryWrite) -> SlotTaint | None:
    """Why a name may hold an absence once a pipe stored it: the write's own reason, or, when the pipe may leave the name as
    it was, the reason it had before.
    """
    if memory_write.absence is not None:
        return memory_write.absence
    if memory_write.is_always_written:
        return None
    return prior_taint
