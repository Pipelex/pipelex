"""Read-side helpers shared by every configuration surface.

A **configuration surface** is one family of user-owned TOML files with one schema and one
migration ledger — today `pipelex.toml` and its tiers, `telemetry.toml`, and
`pipelex_service.toml`. Two things are the same for all three on the read path, and this module
is the one place that knows about either.

**The reserved `[meta]` table.** The strip lives here and deliberately **not** in the generic TOML
reader (`pipelex.tools.misc.toml_utils`), which also reads `.mthds` files, backend definitions and
the kit index — none of which reserve that key, and all of which should keep rejecting it.

**Boot tolerance.** A stale configuration should warn rather than stop the world, but only when
the ledger can explain it. Each surface's loader validates as it always did and, only when that
fails, asks `replay_surface_files_in_memory` for the same files carried forward — writing nothing,
because nothing writes but the explicit `migrate` command. What the loaders do *not* share is the
step between their merge and their validate: one deep-merges programmatic overrides, one
substitutes `${VAR}` placeholders, one does nothing at all. So the shared part is the failure path
alone, and each loader re-runs its own steps over what comes back.

See `docs/migration-ledger.md` → "Schema versions, and why every run replays everything" and
"Boot tolerance".
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, NamedTuple, cast

import tomlkit
from tomlkit.exceptions import TOMLKitError

from pipelex.migration.exceptions import MigrationLedgerError
from pipelex.migration.ledger import MigrationLedger, load_ledger_cached, packaged_migration_dir
from pipelex.migration.plan import MigrationPlan
from pipelex.tools.misc.json_utils import deep_update

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


def declared_schema_version(*, config_dict: dict[str, Any]) -> int | None:
    """The schema version a configuration document declares, or `None` when it declares none.

    Almost every document returns `None`: **nothing writes the key**, so one carrying it was
    hand-written or came from a tool that is not this one. That is exactly why the read is
    tolerant rather than strict — a value that is not a plain integer is a malformed declaration,
    and the same document boots fine because `strip_reserved_meta` removes the key whatever it
    holds. Reading it as "no declaration" keeps the two halves of the reserved key consistent:
    what boot ignores, migration does not act on either.

    `bool` is excluded on purpose. It is an `int` to Python and never a schema version.
    """
    meta_table = config_dict.get(RESERVED_META_TABLE)
    if not isinstance(meta_table, dict):
        return None
    declared = cast("dict[str, Any]", meta_table).get(RESERVED_SCHEMA_VERSION_KEY)
    if isinstance(declared, bool) or not isinstance(declared, int):
        return None
    return declared


def version_declared_below_the_floor(*, ledger: MigrationLedger, config_dict: dict[str, Any]) -> int | None:
    """The schema version a document declares when the ledger can no longer migrate from it, else `None`.

    The one comparison against `min_supported_schema_version` in the tree, read by both the
    migration runner (which refuses the file) and the boot-tolerance retry (which declines). The
    applier skips an absent target and reports success, so a ledger whose oldest entries were
    squashed away would run over such a file, change nothing, and call it fine — the declaration is
    the only evidence there is, and both paths must read it the same way or a boot would carry
    forward a file `pipelex migrate` then refuses.
    """
    declared = declared_schema_version(config_dict=config_dict)
    if declared is None or declared >= ledger.surface.min_supported_schema_version:
        return None
    return declared


# The surface ids, spelled once. The migration registry names the same three, and every ledger
# file's `[surface] id` must agree with them — a boot-tolerance retry that asked for a surface id
# nothing ships would raise rather than tolerate, so the constant is the seam that keeps the
# loader and the registry from drifting apart on a string literal.
PIPELEX_CONFIG_SURFACE_ID = "pipelex-config"
TELEMETRY_CONFIG_SURFACE_ID = "telemetry-config"
PIPELEX_SERVICE_CONFIG_SURFACE_ID = "pipelex-service-config"


class ReplayedSurface(NamedTuple):
    """A surface's user files as the ledger would leave them, and what it did to get there.

    The dict is a merge of the migrated documents, ready to be validated in place of the one that
    just failed. The plans are what a `pipelex migrate` over the same files would report.
    """

    config_dict: dict[str, Any]
    plans: list[MigrationPlan]


def replay_surface_files_in_memory(*, surface_id: str, paths: Sequence[Path]) -> ReplayedSurface | None:
    """Re-read a surface's files, replay its ledger over each in memory, and merge the results.

    **The boot-tolerance retry, and it writes nothing.** A stale configuration should warn rather
    than stop the world, but only when the ledger can explain it — so a loader whose validation
    just failed calls this, re-validates what comes back, and boots with a warning if that
    succeeds. Nothing writes but the explicit `migrate` command.

    `None` means the ledger has nothing to say about these files: no operation applied and no
    entry is blocked. The failure is then not staleness, and the caller's own error stands.

    Three details that are the whole reason this is not two lines:

    - **The paths are the ones the loader merged, in the same order**, packaged defaults and all.
      Replaying over our own shipped configuration is not a special case to exclude, it is a
      no-op the gates already enforce — the ledger check replays every ledger over the packaged
      document and the kit template and demands they come back byte-identical.
    - **A file that cannot be read or parsed abandons the whole retry.** Skipping it would drop a
      layer from the merge, and a re-validation that then *succeeded* would boot on a
      configuration the user does not have. That file's own error is the one to show, and the
      first load already raised it.
    - **The reserved `[meta]` strip happens here**, because this replaces the read-and-merge the
      loader did rather than running after it.

    Nothing that goes wrong *inside* the retry is allowed to become the failure the user sees. A
    ledger that will not load is a packaging bug, and `make check-ledger` and `pipelex migrate`
    are where it is loud; on a machine in the field the user has a configuration error in front of
    them, and replacing it with ours would cost them the only message that names what to fix.
    """
    # Imported here rather than at module level, and the reason is architectural: the engine's
    # applier lives under `pipelex.pipeline`, an interpreter package, while this module sits in
    # `runtime_hub`'s import closure — the kernel layer, which loads zero interpreter modules.
    # Deferring it also makes the contract's "the healthy path is untouched" literal: a boot whose
    # configuration validates never even imports the migration engine.
    from pipelex.migration.engine import replay_ledger_over_text  # noqa: PLC0415

    try:
        ledger = load_ledger_cached(migration_dir=packaged_migration_dir(), surface_id=surface_id)
    except MigrationLedgerError:
        return None
    merged: dict[str, Any] = {}
    plans: list[MigrationPlan] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        except (OSError, UnicodeDecodeError):
            return None
        try:
            if version_declared_below_the_floor(ledger=ledger, config_dict=tomlkit.loads(text).unwrap()) is not None:
                # `pipelex migrate` refuses this file; a retry that carried it forward would boot on
                # an under-migrated configuration and then name a command that declines it.
                return None
            replay = replay_ledger_over_text(ledger=ledger, text=text)
            document = tomlkit.loads(replay.text)
        except TOMLKitError:
            return None
        plans.append(MigrationPlan(surface_id=surface_id, file_path=path, steps=replay.steps, blocked=replay.blocked))
        deep_update(merged, updates=document.unwrap())
    if all(plan.is_clean for plan in plans):
        return None
    strip_reserved_meta(config_dict=merged)
    return ReplayedSurface(config_dict=merged, plans=plans)


def stale_configuration_warning(*, plans: Sequence[MigrationPlan]) -> str:
    """What a boot says when it carried a stale configuration forward in memory rather than dying.

    Names the files and the remedy, and takes everything else it says from the ledger — the same
    rule the migration report obeys, because a boot warning is read in the same places a report is
    and a value read from a user's file has no business in either.
    """
    stale = [plan for plan in plans if not plan.is_clean]
    files = ", ".join(f"'{plan.file_path}'" for plan in stale)
    carried = sorted({step.title for plan in stale for step in plan.steps})
    sentences = [f"Your configuration is out of date, and pipelex read it as if it had been migrated: {files}."]
    if carried:
        sentences.append(f"What the ledger carried forward: {'; '.join(carried)}.")
    if any(plan.blocked for plan in stale):
        sentences.append("Some of what these files need cannot be applied for you — `pipelex migrate` reports it.")
    sentences.append("Nothing was written: run `pipelex migrate` to bring the files up to date.")
    return " ".join(sentences)
