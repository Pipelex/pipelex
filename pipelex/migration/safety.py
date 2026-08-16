"""What an entry promises the applier — the one word both the ledger and the plan need.

A module of its own, and the reason is the import graph rather than the size. `plan.py` must stay
importable from `pipelex.base_exceptions` — that is what lets a configuration validation error
carry a real `MigrationPlan` instead of a second, drifting projection of one — and `ledger.py`
cannot be in that closure, because it reaches `migration.exceptions` and from there back into
`base_exceptions`. The vocabulary the two share therefore lives below both of them.

See `docs/migration-ledger.md` → "What an entry declares".
"""

from enum import StrEnum


class MigrationSafety(StrEnum):
    """Whether the applier may act on an entry.

    Independent of `guidance`, which any entry may carry whatever its safety.
    """

    SAFE = "safe"
    """Mechanically complete; applied after one confirmation."""

    UNSAFE = "unsafe"
    """Reported and never applied — the applier cannot tell a stale value from a deliberate one."""
