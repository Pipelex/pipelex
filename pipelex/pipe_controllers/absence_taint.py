"""Carriers and helpers for the static absence-taint pass (optionals design D6).

The taint pass runs over a controller's dataflow at validation time, computing per-slot presence:
`guaranteed` or `maybe-absent`. A slot is maybe-absent (tainted) when it is fed by an optional
(`?`) input of the controller, by a pipe declaring an optional output, or by a pipe that would be
lifted (skipped) because one of its plain inputs is fed a maybe-absent slot. Presence markers on
a consuming pipe's own input declarations decide how taint propagates (D3 trichotomy): plain →
the pipe lifts and its output is tainted; `?` → absorbed, taint terminates; `!` → asserted at
run time, taint terminates.

Plural slots are never tainted (D4): a skipped plural output normalizes to an empty list and a
batched step compacts absent branch results, so a list slot is always guaranteed (possibly empty).

The walk logic itself lives on the controllers (`PipeSequence.analyze_taint`,
`PipeParallel.analyze_branch_taint`); this module holds the shared value objects and the
presence-resolution helper so the pipeline layer (liftable-pipe inventory) can consume the
same shapes without importing controller internals.
"""

from typing import NamedTuple

from pydantic.dataclasses import dataclass

from pipelex.core.pipes.inputs.input_stuff_specs import NamedStuffSpec
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.variable_multiplicity import PresenceMarker, VariableMultiplicity


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


@dataclass(frozen=True)
class LiftableStepInfo:
    """One pipe that may be lifted (skipped) within a controller's flow."""

    within_pipe_ref: str
    pipe_ref: str
    trigger_variable_names: tuple[str, ...]
    absence_source: str


@dataclass(frozen=True)
class SequenceTaintAnalysis:
    """Result of the taint walk over a PipeSequence's steps."""

    liftable_steps: tuple[LiftableStepInfo, ...]
    output_taint: SlotTaint | None


@dataclass(frozen=True)
class ParallelTaintAnalysis:
    """Result of the taint walk over a PipeParallel's branches."""

    branch_taints: dict[str, SlotTaint]
    liftable_steps: tuple[LiftableStepInfo, ...]


class TaintTriggerScan(NamedTuple):
    """How a pipe consumes the currently tainted slots: the plain-consumed (lift-trigger)
    variable names and the first trigger's taint (for provenance chaining).
    """

    trigger_names: tuple[str, ...]
    trigger_taint: SlotTaint | None


def scan_taint_triggers(pipe: PipeAbstract, *, slot_taints: dict[str, SlotTaint]) -> TaintTriggerScan:
    """Apply the D3 trichotomy to a pipe's needed inputs against the given taint map.

    A tainted slot consumed PLAIN is a lift trigger; consumed `?` (absorb) or `!` (assert),
    the taint terminates at that consumption.
    """
    trigger_names: list[str] = []
    trigger_taint: SlotTaint | None = None
    for named_stuff_spec in pipe.needed_inputs().named_stuff_specs:
        incoming_taint = slot_taints.get(named_stuff_spec.variable_name)
        if incoming_taint is None:
            continue
        match effective_consumption_presence(pipe, named_stuff_spec=named_stuff_spec):
            case PresenceMarker.PLAIN:
                trigger_names.append(named_stuff_spec.variable_name)
                if trigger_taint is None:
                    trigger_taint = incoming_taint
            case PresenceMarker.OPTIONAL | PresenceMarker.FORCE:
                continue
    return TaintTriggerScan(trigger_names=tuple(trigger_names), trigger_taint=trigger_taint)


def is_plural_step_result(
    pipe: PipeAbstract,
    *,
    step_output_multiplicity: VariableMultiplicity | None,
    has_batch_params: bool,
) -> bool:
    """Whether a step's result slot is plural — a plural result is never tainted (D4:
    a lifted plural output is the empty list; a batched step compacts).
    """
    return has_batch_params or step_output_multiplicity is not None or pipe.output.multiplicity is not None


def effective_consumption_presence(pipe: PipeAbstract, *, named_stuff_spec: NamedStuffSpec) -> PresenceMarker:
    """The presence marker governing how `pipe` consumes the given needed input.

    The pipe's OWN input declaration wins when it exists — that is the boundary contract
    (D5: boundaries explicit); a controller's aggregated needs carry its children's markers,
    which must not override the declared boundary. Mirrors the runtime `_scan_input_presence`.
    """
    declared_stuff_spec = pipe.inputs.root.get(named_stuff_spec.variable_name)
    if declared_stuff_spec is not None:
        return declared_stuff_spec.presence
    return named_stuff_spec.presence
