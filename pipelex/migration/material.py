"""The material an entry is about, and where a document keeps it.

An `unsafe` entry is *questioned* before it is reported: the engine asks whether this file still
carries the material the entry is about, so that a user whose file is already fine is never warned.
Two things make that question harder than looking up the entry's own paths.

- **An entry with no operations has no paths to look up.** That shape is the contract's own form
  for "a change only a human can make" — a tightened numeric bound above all — and it is the only
  remedy the coverage gate offers for a narrowing no operation can repair. Such an entry declares
  the paths whose value domain narrowed, and the declaration is what gets looked up.
- **Later entries move the material.** An `unsafe` entry is never applied, so a file it blocks
  keeps the old spelling — while a *later* `safe` entry goes on renaming the tables around it, and
  a file that has been migrated past this entry spells the same material differently. Questioning
  only the entry's own spelling makes an entry that reported on the first run go silent on the
  second, with the file still broken. So the material is traced forward through every later `safe`
  entry, and the document is questioned at every spelling it has ever had — then *reported* at the
  one the end of the replay leaves, because the file the user is sent to check is the one the run
  wrote and the later entries have renamed the material by then.

**Everything here is ledger arithmetic.** No fingerprint, no model, no filesystem — an operation
says which path it moves where, and that is all this module reads. That is what lets the engine
use it while staying the text-in, text-out function the gates replay.

**A rehearsal may guess; an application may not.** Forward tracing is applied to `unsafe` entries
only, because their operations are rehearsed against a copy and thrown away: the worst a wrong
guess costs is one report too many. Extending it to `safe` entries would mean *writing* at a
spelling the entry's author never wrote, which is a different promise and wants its own decision.

See `docs/migration-ledger.md` → "What an `unsafe` entry promises".
"""

from collections.abc import Sequence

from pipelex.migration.fingerprint import PATH_SEPARATOR
from pipelex.migration.ledger import MigrationEntry, MigrationLedger, MigrationSafety
from pipelex.migration.walk import op_source_path
from pipelex.suggested_fix import DeleteKeyOp, DeleteTableOp, MigrationOp, MoveKeyOp, RemapValueOp, RenameTableKeyOp


def unsafe_op_variants(*, ledger: MigrationLedger, entry: MigrationEntry) -> list[list[MigrationOp]]:
    """Every spelling of an entry's operations the engine should rehearse against a document.

    The entry's own operations come first and are what nearly every ledger ever needs: a further
    variant appears only when a later `safe` entry renames or moves an ancestor of something this
    entry addresses. Operations whose material a later entry *deletes* drop out of that variant —
    a file migrated far enough for the material to be gone has nothing for the entry to say.

    Only the operation's **source** is respelled. The rehearsal asks whether the entry would do
    something, and only the source decides that: a move whose destination is occupied is reported
    as a conflict, which counts as "would do something" exactly like an application does.
    """
    variants = [list(entry.ops)]
    current = list(entry.ops)
    for later in ledger.migration:
        if later.to_schema_version <= entry.to_schema_version:
            continue
        if later.safety is MigrationSafety.UNSAFE:
            # An unsafe entry is never applied, so it never gave anything a new spelling.
            continue
        respelled = _ops_through_ops(ops=current, later_ops=later.ops)
        if respelled == current:
            continue
        current = respelled
        if current and current not in variants:
            variants.append(current)
    return [variant for variant in variants if variant]


def declared_path_spellings(*, ledger: MigrationLedger, entry: MigrationEntry) -> list[str]:
    """Every spelling a document might use for the paths an entry declares narrowed.

    Three sources, in the order a reader would think of them: the declaration itself, which is
    spelled as the fingerprint at the entry's own version records it; that path traced *back*
    through the entry's own operations, because an `unsafe` entry is never applied and a file it
    blocks therefore keeps the previous version's spelling; and the path traced *forward* through
    every later `safe` entry, for a file that has been migrated past this one.
    """
    spellings: list[str] = []
    for declared in entry.declared_narrowed_paths:
        for spelling in _spellings_of_one_declared_path(ledger=ledger, entry=entry, declared=declared):
            if spelling not in spellings:
                spellings.append(spelling)
    return spellings


def spelling_after_replay(*, ledger: MigrationLedger, entry: MigrationEntry, spelling: str) -> str:
    """The last spelling the material has once the rest of the replay has run.

    `declared_path_spellings` answers "which spellings should I look for"; this answers "what will
    the file the user is sent to check call it". The two differ whenever a later `safe` entry
    renames the material, because an `unsafe` entry is questioned against the text as it stands
    when the replay reaches it and those later entries then rename it out from under the report.

    Where a later entry *retires* the material there is no later spelling, and the one the file
    carries now is the last there was — the same stop `_spellings_of_one_declared_path` makes when
    it traces forward.
    """
    current = spelling
    for later in ledger.migration:
        if later.to_schema_version <= entry.to_schema_version or later.safety is MigrationSafety.UNSAFE:
            continue
        moved = _path_through_ops(path=current, ops=later.ops)
        if moved is None:
            break
        current = moved
    return current


def _spellings_of_one_declared_path(*, ledger: MigrationLedger, entry: MigrationEntry, declared: str) -> list[str]:
    spellings = [declared]

    before_entry = declared
    for op in reversed(entry.ops):
        before_entry = _path_before_op(path=before_entry, op=op)
    if before_entry not in spellings:
        spellings.append(before_entry)

    current = declared
    for later in ledger.migration:
        if later.to_schema_version <= entry.to_schema_version or later.safety is MigrationSafety.UNSAFE:
            continue
        moved = _path_through_ops(path=current, ops=later.ops)
        if moved is None:
            # A later entry retires the material. A file migrated that far no longer carries it,
            # and every earlier spelling stays in the list for the files that have not.
            break
        current = moved
        if current not in spellings:
            spellings.append(current)
    return spellings


def _ops_through_ops(*, ops: Sequence[MigrationOp], later_ops: Sequence[MigrationOp]) -> list[MigrationOp]:
    respelled: list[MigrationOp] = []
    for op in ops:
        moved = _op_through_ops(op=op, later_ops=later_ops)
        if moved is not None:
            respelled.append(moved)
    return respelled


def _op_through_ops(*, op: MigrationOp, later_ops: Sequence[MigrationOp]) -> MigrationOp | None:
    source = op_source_path(op=op)
    moved = _path_through_ops(path=source, ops=later_ops)
    if moved is None:
        return None
    if moved == source:
        return op
    return _with_source_path(op=op, source_path=moved)


def _path_through_ops(*, path: str, ops: Sequence[MigrationOp]) -> str | None:
    current = path
    for op in ops:
        stepped = _path_through_op(path=current, op=op)
        if stepped is None:
            return None
        current = stepped
    return current


def _path_through_op(*, path: str, op: MigrationOp) -> str | None:
    """Where `path` is after `op` ran: unchanged, respelled, or `None` when the op retires it."""
    match op:
        case RemapValueOp():
            return path
        case DeleteKeyOp() | DeleteTableOp():
            return None if _is_at_or_under(path=path, ancestor=op_source_path(op=op)) else path
        case RenameTableKeyOp():
            return _respelled(path=path, source=op_source_path(op=op), destination=_joined(segments=[*op.table_path, op.new_key]))
        case MoveKeyOp():
            return _respelled(path=path, source=op_source_path(op=op), destination=_joined(segments=[*op.new_table_path, op.new_key]))


def _path_before_op(*, path: str, op: MigrationOp) -> str:
    """Where `path` was before `op` ran — the inverse of a rename or a move, and nothing else.

    A delete has no inverse and needs none: this walks back from a path the fingerprint at the
    entry's own version records, so nothing the entry deleted can be on the way.
    """
    match op:
        case RemapValueOp() | DeleteKeyOp() | DeleteTableOp():
            return path
        case RenameTableKeyOp():
            return _respelled(path=path, source=_joined(segments=[*op.table_path, op.new_key]), destination=op_source_path(op=op))
        case MoveKeyOp():
            return _respelled(path=path, source=_joined(segments=[*op.new_table_path, op.new_key]), destination=op_source_path(op=op))


def _with_source_path(*, op: MigrationOp, source_path: str) -> MigrationOp:
    """The same operation, addressing `source_path` instead of what it addressed.

    Built with `model_copy` rather than by revalidation on purpose: the result is a rehearsal
    object derived from an already-legal operation by substituting one path for another, and it is
    never written to a ledger, never serialized, and never applied to a file.
    """
    segments = source_path.split(PATH_SEPARATOR)
    match op:
        case DeleteTableOp():
            return op.model_copy(update={"table_path": segments})
        case DeleteKeyOp() | RenameTableKeyOp() | MoveKeyOp() | RemapValueOp():
            return op.model_copy(update={"table_path": segments[:-1], "key": segments[-1]})


def _respelled(*, path: str, source: str, destination: str) -> str:
    if path == source:
        return destination
    prefix = source + PATH_SEPARATOR
    if path.startswith(prefix):
        return destination + PATH_SEPARATOR + path[len(prefix) :]
    return path


def _is_at_or_under(*, path: str, ancestor: str) -> bool:
    return path == ancestor or path.startswith(ancestor + PATH_SEPARATOR)


def _joined(*, segments: Sequence[str]) -> str:
    return PATH_SEPARATOR.join(segments)
