"""The downgrade diagnosis — naming what the migration cannot explain.

Always-replay carries files *older* than the running pipelex. The same branch switch that motivates
it also produces files *newer* than it: an override migrated on one branch, then an older branch
checked out or the package downgraded. The older model rejects the newer key and the replay finds
nothing to do, because every operation's source is absent. Under the no-backward-compatibility
principle that is not repaired — but "nothing to do" beside a dead boot is precisely the failure
this project exists to kill, so it is **named**.

**This is the one part of a migration that needs the model.** The engine is deliberately model-free
— text in, text out — which is what lets the gates replay it over documents nobody writes. Asking
whether a path is one the current schema knows cannot be answered from a ledger, so the question is
put to the surface's *fingerprint*: the same projection the coverage gate diffs, computed from the
model the surface names. The diagnosis therefore lives here, beside the runner that has a surface,
rather than inside the engine that has only text.

Four rules make the answer trustworthy rather than merely computable.

- **The document diagnosed is the one the run leaves behind**, not the one it found. Everything the
  ledger explains has been carried forward by then, so what is left over is genuinely left over. On
  a dry run that document exists only in memory, which is why the diagnosis belongs to the run and
  not to a later pass over the file.
- **A blocked entry answers for its own material.** An `unsafe` entry is never applied, so the old
  shape it is about is still in the file — reported already, by name, with the entry's guidance.
  Reporting it a second time as unexplained would contradict the first report and send the user
  looking for a typo in a key the tool has just told them about.
- **A key the user chose is reported as the schema spells it.** Beneath an open mapping the schema
  says `levels.*` where the file says `levels.my_package`, and a typo *inside* such an entry is
  reported at `queues.*.retries`. The unknown segment is named, because naming it is the whole
  point; the user's own key beside it is not.
- **A key the surface admits by shape is not unexplained.** One surface has a key class that is legal
  without being named by any model: a backend file's per-model request headers, legal because they are
  shaped like headers. The surface is asked (`Surface.admits_unnamed_key`), and the answer is
  deliberately narrow — a key with no hyphen is still a typo, and still reported.

See `docs/migration-ledger.md` → "The downgrade direction".
"""

import copy
from collections.abc import Sequence
from typing import Any, cast

from pipelex.migration.documents import path_is_at_or_under_pattern
from pipelex.migration.fingerprint import PATH_SEPARATOR, TABLE_TYPE, PathFingerprint, SurfaceFingerprint
from pipelex.migration.ledger import MigrationEntry, MigrationLedger
from pipelex.migration.material import spelling_after_replay
from pipelex.migration.plan import BlockedEntry, UnexplainedPath
from pipelex.migration.surfaces import Surface
from pipelex.migration.walk import op_source_path
from pipelex.suggested_fix import WILDCARD_SEGMENT, RemapValueOp
from pipelex.system.configuration.config_surface import strip_reserved_meta

UNEXPLAINED_NOTE = (
    "the current schema has no setting there, and no ledger entry retires it — either the name is a typo, or this file was "
    "written by a newer pipelex than the one running, so check whether you are on an older branch or an older build"
)
"""The two readings, and nothing else.

They share one note because the remedy differs and the diagnosis genuinely cannot tell them apart:
a misspelling and a key from next month's release look identical to a schema that knows neither.
Guessing would send half the users to the wrong fix, and the two questions are cheap for a human to
tell apart once they are asked.
"""


def diagnose_unexplained_paths(
    *,
    surface: Surface,
    fingerprint: SurfaceFingerprint,
    document: dict[str, Any],
    ledger: MigrationLedger,
    blocked: Sequence[BlockedEntry],
) -> list[UnexplainedPath]:
    """Every path in a migrated document that neither the current schema nor the ledger explains.

    The document must be the one the run leaves behind. Passing the pre-migration document would
    report every stale key the ledger is about to repair, which is the opposite of the diagnosis.

    The surface is here for the fourth rule, which the other three did not need: **a key the surface
    itself admits by shape rather than by name is not unexplained.** A backend file's per-model
    request headers are the case — see `Surface.admits_unnamed_key`. It is asked of the surface and
    not read off the fingerprint because it is a live rule about a key's spelling, and because the
    coarser answer a snapshot could carry ("this node takes extras") would silence exactly the key
    class the ledger is there to repair.
    """
    # A deep copy, because the strip below edits the nested `[meta]` table in place and this
    # function only ever reads what it was handed.
    diagnosed = copy.deepcopy(document)
    # Exactly what boot does before validating: the reserved key is tolerated there, so a document
    # carrying it must not be reported here either. A `[meta]` holding anything else is not
    # reserved, is left in place, and is diagnosed like any other unknown table.
    strip_reserved_meta(config_dict=diagnosed)
    accounted = _paths_a_blocked_entry_answers_for(ledger=ledger, blocked=blocked)
    unexplained: list[UnexplainedPath] = []
    _diagnose_table(
        table=diagnosed,
        document_prefix=(),
        schema_prefix=(),
        surface=surface,
        fingerprint=fingerprint,
        accounted=accounted,
        unexplained=unexplained,
    )
    return sorted(unexplained, key=lambda found: found.path)


def _diagnose_table(
    *,
    table: dict[str, Any],
    document_prefix: tuple[str, ...],
    schema_prefix: tuple[str, ...],
    surface: Surface,
    fingerprint: SurfaceFingerprint,
    accounted: list[str],
    unexplained: list[UnexplainedPath],
) -> None:
    """Walk one table of the document against the schema, reporting the shallowest unknown paths.

    A tree walk rather than a comparison of two flat path sets, and that is what buys the two
    properties a flat diff cannot have: an unknown table is reported once instead of once per key
    inside it, and the schema spelling of every ancestor is known by the time a child is reported.
    """
    for key, value in table.items():
        document_path = (*document_prefix, str(key))
        resolved = _resolve_against_schema(schema_prefix=schema_prefix, key=str(key), fingerprint=fingerprint)
        if resolved is None:
            if not _is_accounted_for(path=document_path, accounted=accounted) and not surface.admits_unnamed_key(
                node_path=schema_prefix, key=str(key)
            ):
                unexplained.append(UnexplainedPath(path=PATH_SEPARATOR.join((*schema_prefix, str(key))), note=UNEXPLAINED_NOTE))
            # Never descended into: an unknown table's contents are unknown because it is, and
            # listing every key inside it buries the one name the user has to fix.
            continue
        schema_path, record = resolved
        if not isinstance(value, dict):
            continue
        if record.value_type != TABLE_TYPE and not record.open_node:
            # A table where the schema wants a scalar is a *type* error, and the model reports it
            # far better than a path walk could. Descending would invent unknown paths beneath a
            # path the schema knows perfectly well.
            continue
        _diagnose_table(
            table=cast("dict[str, Any]", value),
            document_prefix=document_path,
            schema_prefix=schema_path,
            surface=surface,
            fingerprint=fingerprint,
            accounted=accounted,
            unexplained=unexplained,
        )


def _resolve_against_schema(
    *,
    schema_prefix: tuple[str, ...],
    key: str,
    fingerprint: SurfaceFingerprint,
) -> tuple[tuple[str, ...], PathFingerprint] | None:
    """The schema path and record for one document key, or `None` when the schema has neither.

    The exact name is tried first and the `*` child second, in that order, because the `*` child
    exists only beneath an open mapping and an open mapping has no named children — so the two
    lookups can never both succeed and the order costs nothing but reads in the right one.
    """
    named = (*schema_prefix, key)
    record = fingerprint.paths.get(PATH_SEPARATOR.join(named))
    if record is not None:
        return named, record
    under_open_node = (*schema_prefix, WILDCARD_SEGMENT)
    record = fingerprint.paths.get(PATH_SEPARATOR.join(under_open_node))
    if record is not None:
        return under_open_node, record
    return None


def _is_accounted_for(*, path: tuple[str, ...], accounted: list[str]) -> bool:
    document_path = PATH_SEPARATOR.join(path)
    return any(path_is_at_or_under_pattern(path=document_path, pattern=pattern) for pattern in accounted)


def _paths_a_blocked_entry_answers_for(*, ledger: MigrationLedger, blocked: Sequence[BlockedEntry]) -> list[str]:
    """The material every blocked entry is about, at every spelling a file could be carrying it under.

    A blocked entry is the *reason* its material is still in the file, and the report already names
    it — with the entry's own guidance, which is worth more than this diagnosis has to offer. So
    the paths it addresses are subtracted here rather than reported twice with two different
    stories.

    Over-covering is the safe direction and is chosen deliberately: every path subtracted is one the
    same report names in `blocked[]`, so the worst a wide answer costs is a second sentence about a
    key the user has already been told about — where a narrow one would contradict the first.
    """
    accounted: list[str] = []
    for blocked_entry in blocked:
        entry = ledger.entry_for_version(schema_version=blocked_entry.to_schema_version)
        if entry is None:
            continue
        for pattern in _paths_one_entry_answers_for(ledger=ledger, entry=entry):
            if pattern not in accounted:
                accounted.append(pattern)
    return accounted


def _paths_one_entry_answers_for(*, ledger: MigrationLedger, entry: MigrationEntry) -> list[str]:
    """One entry's material: what its operations address and what it declares removed, traced forward.

    A `remap_value` contributes nothing. It changes a value and leaves the path exactly where it
    was, so the path it addresses is one the current schema still has — never an unexplained one,
    and subtracting it would silence a genuine typo that happens to sit at a remapped key.

    The forward trace is there because a later `safe` entry may have renamed the material around a
    blocked one, exactly as it does for the report an `unsafe` entry produces: the file this run
    leaves behind spells the material the way the end of the replay does.
    """
    sources = [op_source_path(op=op) for op in entry.ops if not isinstance(op, RemapValueOp)]
    sources.extend(entry.declared_removed_paths)
    spellings: list[str] = []
    for source in sources:
        for spelling in (source, spelling_after_replay(ledger=ledger, entry=entry, spelling=source)):
            if spelling not in spellings:
                spellings.append(spelling)
    return spellings
