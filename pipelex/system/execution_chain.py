"""Executions, their attempts, and the chain that ties a trace event to the attempts it ran under.

The hosted progress contract (`conformance/specs/pipelex-platform-api.md`, "Executions and their attempts") calls an
**execution** a part of a run that emits events and that its engine runs, and may run again, as a whole: the run's own
workflow, and every workflow it dispatches, which on every engine Pipelex runs on today is each batch item's. Each run
of an execution is an **attempt**, numbered from 1. In the runtime's direct mode the whole run is one execution,
`direct`, in its first attempt.

An execution that dispatches another hands it its own **lineage** followed by its own `{execution, attempt}`, so an
event's **chain**, its lineage followed by its own entry, runs from the run's own execution down to the one that
emitted it. A higher attempt of an execution, dispatched under the same attempts, **supersedes** the earlier one and
everything it dispatched, at any depth: an event is current when no attempt in its chain is superseded.
"""

from collections.abc import Iterable, Sequence
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

DIRECT_EXECUTION = "direct"
"""The one execution of a run in the runtime's direct mode, which runs the whole run in one process."""


class ExecutionAttempt(BaseModel):
    """One attempt of one execution: the workflow whose code emits events, and which run of it by its engine.

    Attributes:
        execution: Names the execution, the same in each of its attempts: the id of the workflow, or `direct`.
        attempt: The attempt of that execution, counting from 1.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    execution: str = Field(min_length=1)
    attempt: int = Field(ge=1)


def make_direct_chain() -> list[ExecutionAttempt]:
    """The chain of a run in the runtime's direct mode: its one execution, in its first attempt."""
    return [ExecutionAttempt(execution=DIRECT_EXECUTION, attempt=1)]


def execution_chain_key(*, chain: Sequence[ExecutionAttempt]) -> str:
    """One string naming a chain, distinct for every two chains that differ.

    Each entry reads `<execution>@<attempt>`, the execution percent-encoded so that no name holds a separator, and the
    entries are joined by `/`. The empty chain, the lineage of the run's own execution, gives the empty string.
    """
    return "/".join(f"{quote(entry.execution, safe='')}@{entry.attempt}" for entry in chain)


def current_chain_keys(*, chains: Iterable[Sequence[ExecutionAttempt]]) -> set[str]:
    """The keys of the chains, among those given, that no attempt of the run supersedes.

    An attempt in a chain is superseded when some chain of the run holds a higher attempt of the same execution after
    the same entries, that is, dispatched under the same attempts. A chain is current when no attempt in it is
    superseded, its own included. The rule compares attempt numbers within one execution and never a clock.

    Args:
        chains: The chains of every event of the run, in any order, repeats included.

    Returns:
        The `execution_chain_key` of every chain given that is current.
    """
    distinct_chains: dict[str, Sequence[ExecutionAttempt]] = {}
    for chain in chains:
        distinct_chains.setdefault(execution_chain_key(chain=chain), chain)

    # The highest attempt of each execution, per the entries it was dispatched under.
    latest_attempts: dict[tuple[str, str], int] = {}
    for chain in distinct_chains.values():
        for entry_index, entry in enumerate(chain):
            slot = (execution_chain_key(chain=chain[:entry_index]), entry.execution)
            latest_attempts[slot] = max(latest_attempts.get(slot, 0), entry.attempt)

    current_keys: set[str] = set()
    for chain_key, chain in distinct_chains.items():
        is_current = True
        for entry_index, entry in enumerate(chain):
            if entry.attempt < latest_attempts[execution_chain_key(chain=chain[:entry_index]), entry.execution]:
                is_current = False
                break
        if is_current:
            current_keys.add(chain_key)
    return current_keys
