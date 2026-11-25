"""The maximum number of items a method may declare for one slot, and the refusal of a count past it.

A method declares a fixed number of items with `Concept[N]` on an input or an output, or with `nb_output = N` on a
controller step, and a dry run builds one mock item per declared item, so without a bound a few lines of a method make
a validation build millions of them. One maximum covers the three spellings.

**The maximum is the runtime's, not the language's.** A method declaring 5,000 items is valid MTHDS; a runtime, or a
plan on the hosted plane, may refuse to load it. The maximum in force is, in order:

- the one a scope opened with `scoped_max_declared_item_count` (`pipelex.core.pipes.declared_item_count_scope`), which a
  host opens from a request's own maximum: the validation (`validate_bundles_in_process`), the run setup
  (`pipeline_run_setup`) and every pipe run, which reads it from its `RunMetadata`, so a worker in another process
  applies the request's maximum too;
- otherwise `[interpreter.method_limits] max_declared_item_count`, 1,000 by default.

A scope opened with ``None`` changes nothing, so a nested run whose metadata carries no maximum keeps the one around it.

**Two lines of defence.** The library load refuses a method declaring a count past the maximum before it builds
anything (`pipelex.libraries.declared_item_counts`), and the dry-run mock builders refuse to build more items than the
maximum (:func:`ensure_mock_item_count_allowed`), so a path that skipped the load check cannot build them either. Both
raise :class:`~pipelex.core.pipes.exceptions.DeclaredItemCountLimitError`. A third, fixed bound holds whatever the
maximum: the parser refuses a count written with more digits than any maximum could allow
(`pipelex.core.pipes.declared_count_bounds`).
"""

from pipelex.config import get_config
from pipelex.core.pipes.declared_item_count_scope import get_scoped_max_declared_item_count
from pipelex.core.pipes.exceptions import DeclaredItemCountLimitError
from pipelex.tools.misc.string_utils import pluralize


def get_max_declared_item_count() -> int:
    """The maximum number of items a method may declare for one slot, in this context."""
    scoped = get_scoped_max_declared_item_count()
    if scoped is not None:
        return scoped
    return get_config().interpreter.method_limits.max_declared_item_count


def ensure_declared_item_count_allowed(*, count: int, slot: str, maximum: int) -> None:
    """Refuse a count a method declares for `slot` when it passes `maximum`.

    Args:
        count: The declared count.
        slot: Where it is declared, as a caller reads it, such as "the input 'items' of the pipe 'summarize'".
        maximum: The maximum in force.

    Raises:
        DeclaredItemCountLimitError: The count passes the maximum.
    """
    if count <= maximum:
        return
    msg = (
        f"The method declares {count} items for {slot}, and this runtime allows at most {maximum} "
        f"{pluralize(count=maximum, singular='item')} for one slot. Declare fewer, or raise the limit: "
        "a request's maximum, a higher plan on the hosted plane, or `max_declared_item_count` under "
        "`[interpreter.method_limits]` in `.pipelex/pipelex.toml`."
    )
    raise DeclaredItemCountLimitError(msg, slot=slot, count=count, limit=maximum)


def ensure_mock_item_count_allowed(*, count: int, slot: str) -> None:
    """Refuse to build more mock items than the maximum in force, the dry run's second line behind the load check.

    The load refuses a method declaring more, so a request reaching here names a path that skipped that check. A mock
    cannot be shortened, since the run holds a fixed slot's value to its declared length, so the builder refuses rather
    than build fewer.

    Raises:
        DeclaredItemCountLimitError: The count passes the maximum in force.
    """
    ensure_declared_item_count_allowed(count=count, slot=slot, maximum=get_max_declared_item_count())
