"""Read-side helper shared by every configuration surface.

A **configuration surface** is one family of user-owned TOML files with one schema and one
migration ledger — today `pipelex.toml` and its tiers, `telemetry.toml`, and
`pipelex_service.toml`. What they share on the read path is the reserved `[meta]` table, and
this module is the one place that knows about it.

The strip lives here and deliberately **not** in the generic TOML reader
(`pipelex.tools.misc.toml_utils`), which also reads `.mthds` files, backend definitions and the
kit index — none of which reserve that key, and all of which should keep rejecting it.

See `docs/migration-ledger.md` → "Schema versions, and why every run replays everything".
"""

from typing import Any, cast

# The reserved in-file table and key. Every configuration-surface reader tolerates them and
# strips them before validation; **nothing writes them**. The reason not to write is team skew
# on tracked files: a project's `.pipelex/pipelex.toml` is shared through git, so one developer
# on a newer pipelex stamping the key would break a teammate on last week's build the same
# afternoon.
RESERVED_META_TABLE = "meta"
RESERVED_SCHEMA_VERSION_KEY = "schema_version"


def strip_reserved_meta(*, config_dict: dict[str, Any]) -> None:
    """Remove the reserved `[meta] schema_version` from a loaded configuration, in place.

    Only that one key is removed, and `[meta]` itself only when nothing else is left in it — a
    `[meta]` table carrying anything else is not reserved and must keep failing validation
    loudly under `extra="forbid"`, rather than being quietly swallowed along with it.
    """
    meta_table = config_dict.get(RESERVED_META_TABLE)
    if not isinstance(meta_table, dict):
        return
    typed_meta_table = cast("dict[str, Any]", meta_table)
    if RESERVED_SCHEMA_VERSION_KEY not in typed_meta_table:
        return
    del typed_meta_table[RESERVED_SCHEMA_VERSION_KEY]
    if not typed_meta_table:
        del config_dict[RESERVED_META_TABLE]
