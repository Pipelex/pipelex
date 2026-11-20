"""Process-global access to the orchestrator workflow code the current call runs in, if any.

A distributed orchestrator such as Temporal runs a controller pipe inline in its *workflow code*, which it
re-executes from the start whenever it replays the workflow: after the workflow is evicted from a worker's
cache, or moved to another worker after a restart. A pipe span opened there would be opened again on every
replay, with a fresh random id and a new wall-clock start, and exported again at its end. What makes the span
replay-safe is knowledge only the orchestrator has: whether the code is replaying, the workflow's own clock and
its deterministic random. This module holds the seam through which the orchestrator lends that knowledge to
pipelex's telemetry (``pipelex.system.telemetry.replay_safe_spans``).

A boot-orchestrator plugin whose runtime replays its workflow code claims ``HubSlot.WORKFLOW_EXECUTION_PROBE``
with a thunk that returns a probe: a callable answering, for the current call, the
``WorkflowExecutionProtocol`` of the workflow code it runs in, or ``None`` outside workflow code (in an
activity, or in a process that runs no workflow at all). Unclaimed, the probe always answers ``None``: the
in-process orchestrator never replays, and every span keeps its random id and its wall-clock times.

The module sits *below* both hubs and imports nothing from ``pipelex``, like
``pipelex.system.registries.class_registry_access``, because its readers cannot import ``runtime_hub``:
``pipe_machinery.pipe_abstract`` reads it when a pipe span starts and ends, and the tracer's id generator is
built inside ``runtime_hub``'s own import closure. ``RuntimeBoot`` installs the claimed probe at its boot
apply-point and resets the slot on both teardown paths.
"""

from collections.abc import Callable
from random import Random
from typing import Protocol


class WorkflowExecutionProtocol(Protocol):
    """The deterministic sources of the workflow code the current call runs in, as its orchestrator answers them.

    Every answer must be the same on a replay of the workflow as on its live execution at the same point of
    its history, which is what lets a span opened in workflow code be recomputed identically on a replay and
    exported once, by the live execution, at its end.
    """

    def is_replaying(self) -> bool:
        """Whether the workflow code is re-executing history that a previous execution already ran.

        A span that ends while this is true already ended in that previous execution, which exported it then.
        For Temporal, this is ``workflow.unsafe.is_replaying_history_events()``.
        """
        ...

    def time_ns(self) -> int:
        """The workflow's own clock, in nanoseconds since the epoch, which a replay reproduces.

        For Temporal, ``workflow.time_ns()``: the time of the workflow task being processed.
        """
        ...

    def random(self) -> Random:
        """A random generator seeded by the workflow, which a replay reproduces draw for draw.

        Pipe span ids, and no other span's, are drawn from it, so it should be dedicated to them: drawing from the
        workflow's main generator would shift every later draw of the workflow's own code depending on whether a tracer
        exists, which is configuration, not history. For Temporal, ``workflow.new_random("<a name>")`` kept on
        the workflow instance, so that it is created once per execution and reseeds with the workflow.
        """
        ...

    def is_unwinding(self, *, error: BaseException) -> bool:
        """Whether ``error`` leaves the workflow running, so the pipes it crosses run again in a later execution.

        Only these unwind the workflow code without ending the workflow:

        - **the orchestrator tearing the code down**, on the eviction of a cached workflow, with an exception of its own,
          ``GeneratorExit`` included, or with a cancellation it raises into the code while it evicts;
        - **an error that fails the workflow task rather than the workflow**, which the orchestrator retries by
          replaying the workflow, so the pipe reaches its end again in a later execution.

        Anything else is the pipe's real end, and its span is exported with the failure: an error that fails the
        workflow, at whatever depth it is raised, and a cancellation of the workflow or of the run, which ends the
        workflow as cancelled. Answer from the orchestrator's own classification and state, never from the error's
        type alone: a cancellation is unwinding only while the orchestrator evicts.

        For Temporal: true when the workflow is being evicted, for ``GeneratorExit`` and the SDK's eviction error, and
        for an error that ``workflow.is_failure_exception`` does not recognise and that is not an
        ``asyncio.CancelledError``, which the SDK turns into the workflow's cancellation or failure at its top level.
        ``is_failure_exception`` tests the worker's ``workflow_failure_exception_types`` by ``isinstance`` wherever the
        error is raised, so a worker that lists ``PipelexError`` there fails the workflow on a pipe's failure at any
        depth, and a nested pipe's span is exported with it.
        """
        ...


WorkflowExecutionProbe = Callable[[], WorkflowExecutionProtocol | None]


def _never_in_workflow_code() -> WorkflowExecutionProtocol | None:
    """Core default probe: the in-process orchestrator runs no replayable workflow code."""
    return None


class WorkflowExecutionSlot:
    """Process-global slot holding the probe a boot-orchestrator plugin claimed, or the core default.

    A defaulted callable that the boot replaces, never an unset attribute, so a process that never booted an
    orchestrator, such as most unit tests, reads ``None`` instead of raising.
    """

    def __init__(self) -> None:
        self._probe: WorkflowExecutionProbe = _never_in_workflow_code

    def install(self, *, probe: WorkflowExecutionProbe) -> None:
        self._probe = probe

    def reset(self) -> None:
        self._probe = _never_in_workflow_code

    def current(self) -> WorkflowExecutionProtocol | None:
        return self._probe()


workflow_execution_slot = WorkflowExecutionSlot()


def get_workflow_execution() -> WorkflowExecutionProtocol | None:
    """The workflow code the current call runs in, or ``None`` outside workflow code."""
    return workflow_execution_slot.current()
