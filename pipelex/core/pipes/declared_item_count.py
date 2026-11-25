"""The maximum number of items one slot may hold, the dry run's budget of mock items, and their refusals.

A method declares a fixed number of items with `Concept[N]` on an input or an output, or with `nb_output = N` on a
controller step, and a run may ask for one with `output_multiplicity`. A dry run builds one mock item per item, so
without a bound a few lines of a method make a validation build millions of them. One maximum covers every spelling.

**The maximum is the runtime's, not the language's.** A method declaring 5,000 items is valid MTHDS; a runtime, or a
plan on the hosted plane, may refuse to load it. The deployment's maximum is `[interpreter.method_limits]
max_declared_item_count`, 1,000 by default.

**A request may raise the maximum, never lower it.** A host states a request's own maximum, such as the hosted plane from
the caller's plan, and a scope opened with `scoped_max_declared_item_count` (`pipelex.core.pipes.declared_item_count_scope`)
carries it: the validation (`validate_bundles_in_process`), the run setup (`pipeline_run_setup`) and every pipe run,
which reads it from its `RunMetadata`, so a worker in another process applies it too, and a dry leaf run in an activity
with no scope reads it from its job's metadata (:func:`dry_leaf_limits`). The maximum in force is the larger of that
maximum and the deployment's (:func:`get_max_declared_item_count`), so a request stating a lower one changes nothing: a
host's own library pipes, which load beside the caller's method, are never refused for what the caller states. A scope
opened with ``None`` changes nothing either, so a nested run whose metadata carries no maximum keeps the one around it.

**A request's maximum is held to the deployment's ceiling.** It arrives in public JSON, so a caller could raise its own
limit: :func:`validate_requested_max_declared_item_count` refuses one past `max_declared_item_count_ceiling`, which a
deployment raises only behind a trusted front that sets each request's maximum itself.

**Three lines of defence per slot.** The library load refuses a method declaring a count past the maximum before it
builds anything (`pipelex.libraries.declared_item_counts`), a dry-run mock builder asked for a fixed count past it
refuses too (:func:`ensure_mock_item_count_allowed`), so a path that skipped the load check cannot build them, and the
parser refuses a count written with more digits than any maximum could allow (`pipelex.core.pipes.declared_count_bounds`).
A length the dry run chooses itself for a variable list, `Concept[]`, is no declared count: it is shortened to the
maximum rather than refused (:func:`capped_synthetic_mock_count`).

**One budget for the whole dry run.** The per-slot maximum leaves the sum and the products of the slots unbounded, so
every mock builder also adds what it builds to one tally per validation or per run (:func:`spend_dry_run_mock_items`),
refused past `[interpreter.method_limits] max_dry_run_mock_items` with
:class:`~pipelex.core.pipes.exceptions.DryRunMockBudgetError`.
"""

from collections.abc import Generator
from contextlib import contextmanager
from enum import StrEnum

from pipelex.config import get_config
from pipelex.core.pipes.declared_item_count_scope import (
    get_scoped_dry_run_mock_tally,
    get_scoped_max_declared_item_count,
    scoped_dry_run_mock_budget,
    scoped_max_declared_item_count,
    validate_max_declared_item_count,
)
from pipelex.core.pipes.exceptions import DeclaredItemCountLimitError, DryRunMockBudgetError
from pipelex.system.exceptions import RunParameterError


class ItemCountSource(StrEnum):
    """Who asks for the items a refusal counts, which its first sentence names."""

    METHOD = "method"
    DRY_RUN = "dry_run"
    RUN = "run"

    def asks_for(self, *, count: int, slot: str) -> str:
        """The refusal's first clause: who asks for `count` items for `slot`."""
        match self:
            case ItemCountSource.METHOD:
                return f"The method declares {count} items for {slot}"
            case ItemCountSource.DRY_RUN:
                return f"A dry run would build {count} items for {slot}"
            case ItemCountSource.RUN:
                return f"The run asks for {count} items for {slot}"


def get_deployment_max_declared_item_count() -> int:
    """The deployment's own maximum, `[interpreter.method_limits] max_declared_item_count`, whatever scope is open."""
    return get_config().interpreter.method_limits.max_declared_item_count


def get_max_declared_item_count() -> int:
    """The maximum number of items one slot may hold, in this context: the deployment's, raised by a request's own.

    A request's maximum, the one a scope opened, only ever raises the deployment's: the larger of the two is in force.
    """
    deployment_maximum = get_deployment_max_declared_item_count()
    scoped = get_scoped_max_declared_item_count()
    if scoped is None:
        return deployment_maximum
    return max(scoped, deployment_maximum)


def validate_requested_max_declared_item_count(*, value: int) -> int:
    """Refuse a maximum a request states past the deployment's ceiling, or one no runtime may set.

    A request's maximum is read from public JSON, so the deployment's ceiling,
    `[interpreter.method_limits] max_declared_item_count_ceiling`, bounds what a caller may raise its own limit to. A
    maximum at or below it is accepted; one below the deployment's own maximum is accepted too, and lowers nothing,
    since the larger of the two is in force (:func:`get_max_declared_item_count`).

    Raises:
        RunParameterError: The value is not a whole number from one to the ceiling. It is a `ValueError`, so a pydantic
            validator calling this function refuses the field naming it.
    """
    validate_max_declared_item_count(value=value)
    ceiling = get_config().interpreter.method_limits.max_declared_item_count_ceiling
    if value > ceiling:
        msg = f"A request's max_declared_item_count may be at most {ceiling}, this deployment's max_declared_item_count_ceiling, got {value}."
        raise RunParameterError(msg)
    return value


def ensure_declared_item_count_allowed(*, count: int, slot: str, maximum: int, source: ItemCountSource) -> None:
    """Refuse `count` items for `slot` when it passes `maximum`.

    Args:
        count: The count asked for.
        slot: Where it is asked for, as a caller reads it, such as "the input 'items' of the pipe 'summarize'".
        maximum: The maximum in force.
        source: Who asks for it: the method's declaration, the dry run's builder or the run's request.

    Raises:
        DeclaredItemCountLimitError: The count passes the maximum.
    """
    if count <= maximum:
        return
    msg = (
        f"{source.asks_for(count=count, slot=slot)}, more than the {maximum} this runtime allows for one slot. Ask for "
        "fewer, or raise the limit: a request's maximum, a higher plan on the hosted plane, or `max_declared_item_count` "
        "under `[interpreter.method_limits]` in `.pipelex/pipelex.toml`."
    )
    raise DeclaredItemCountLimitError(msg, slot=slot, count=count, limit=maximum)


def ensure_mock_item_count_allowed(*, count: int, slot: str) -> None:
    """Refuse to build a fixed count of mock items past the maximum in force, the dry run's second line behind the load.

    For a count the method or the run fixed: a declared `Concept[N]`, an `nb_items` or `nb_images` set from a step's
    `nb_output`, or a run's `output_multiplicity`. The load refuses a method declaring more, so a request reaching here
    names a path that skipped that check. Such a mock cannot be shortened, since the run holds a fixed slot's value to
    its length, so the builder refuses rather than build fewer. A length the dry run chooses itself goes through
    :func:`capped_synthetic_mock_count` instead.

    Raises:
        DeclaredItemCountLimitError: The count passes the maximum in force.
    """
    ensure_declared_item_count_allowed(count=count, slot=slot, maximum=get_max_declared_item_count(), source=ItemCountSource.DRY_RUN)


def ensure_run_item_count_allowed(*, count: int, slot: str) -> None:
    """Refuse a count a run asks for itself, such as its `output_multiplicity`, past the maximum in force.

    Raises:
        DeclaredItemCountLimitError: The count passes the maximum in force.
    """
    ensure_declared_item_count_allowed(count=count, slot=slot, maximum=get_max_declared_item_count(), source=ItemCountSource.RUN)


def capped_synthetic_mock_count(*, default: int) -> int:
    """The length of a list the dry run chooses itself, such as a variable `Concept[]`'s: `default`, shortened to the maximum.

    Nothing declared that length, so it is no count to refuse: a method declaring no count stays valid under a maximum
    below the dry run's default lengths, `inference.dry_run.nb_list_items` and the like.
    """
    return min(default, get_max_declared_item_count())


def get_max_dry_run_mock_items() -> int:
    """The most mock items one dry run builds in all, `[interpreter.method_limits] max_dry_run_mock_items`."""
    return get_config().interpreter.method_limits.max_dry_run_mock_items


def spend_dry_run_mock_items(*, count: int, slot: str) -> None:
    """Add `count` mock items about to be built for `slot` to the dry run's tally, refused when it would pass the budget.

    Every dry-run mock builder calls it before it builds. Inside a budget scope (`scoped_dry_run_mock_budget`) the items
    add to the scope's one tally, shared by the whole validation or run; outside every scope, such as a builder called on
    its own, the call is a budget of its own.

    Raises:
        DryRunMockBudgetError: The tally would pass `max_dry_run_mock_items`; nothing is added.
    """
    budget = get_max_dry_run_mock_items()
    tally = get_scoped_dry_run_mock_tally()
    already_built = tally.built if tally is not None else 0
    is_within = tally.add_within(count=count, budget=budget) if tally is not None else count <= budget
    if is_within:
        return
    msg = (
        f"A dry run would build {count} more mock items for {slot}, after {already_built} already built, past the "
        f"{budget} this runtime builds for one dry run. Declare fewer items across the method, or raise "
        "`max_dry_run_mock_items` under `[interpreter.method_limits]` in `.pipelex/pipelex.toml`."
    )
    raise DryRunMockBudgetError(msg, slot=slot, budget=budget)


@contextmanager
def dry_leaf_limits(*, run_max_declared_item_count: int | None) -> Generator[None, None, None]:
    """Bound a dry content-generation leaf by its run's limits, also where it runs with no scope open, as in a worker's activity.

    In process, the pipe run around the leaf already opened both scopes, and this keeps them. A worker's activity runs
    the leaf with neither, so the leaf reads the maximum from its job's `RunMetadata`, else the worker's configuration,
    and counts its mock items against a budget of its own, the activity being all of the dry run that process sees.

    Args:
        run_max_declared_item_count: The maximum the leaf's job metadata carries, `None` when its host stated none.
    """
    maximum = run_max_declared_item_count if get_scoped_max_declared_item_count() is None else None
    with scoped_max_declared_item_count(maximum=maximum), scoped_dry_run_mock_budget():
        yield
