"""Backups — the copy taken before a user's configuration file is rewritten.

Always, before writing. Exactly **one** backup per file: a successful run replaces the previous
one, so a directory does not accumulate a decade of copies of a file whose durable history is
already in git. For the untracked files — and for the moment between two commits — this copy is
the whole safety net.

Three rules make that safety net worth the name, and each is a policy this module owns:

- **A run never overwrites or removes a copy it did not make.** The stamp resolves to the second,
  so two runs can address the same name; the second reserves the name atomically, finds it taken,
  and keeps what is there. It is the older copy that holds the original.
- **A copy the run cannot vouch for leaves the rotation.** When a write fails in a state the
  transaction cannot describe, the backup is renamed out of the `.bak.` family into `.rescue.`,
  which pruning never matches — otherwise the next successful run would delete the very copy the
  report told the user to go and get. Removing a rescue copy is the user's call, never the tool's.
  A copy that cannot be moved — another run's, or one whose rescue name is taken — stays where it
  is and says so, so the report can ask the user to take it now rather than promise it will keep.
- **The copy is durable before the file it copies changes.** Its bytes are `fsync`-ed by the
  staged write and its name by an `fsync` of the directory, so "back up first, replace second"
  survives a power loss and not only a process exit.

The mode is inherited from the source rather than left to the process umask, and that is the one
deliberate exception to "no value read from a user's file is ever rendered": a backup contains the
user's values by definition, so a `0600` configuration must not become a world-readable `0644`
copy sitting beside it. Ownership and extended attributes are **not** carried across — an atomic
replace cannot preserve what the running process has no right to set, and the security-relevant
bit of a configuration file is its mode.

See `docs/migration-ledger.md` → "Backups".
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from pipelex.pipeline.fixes.file_transaction import FileSnapshot, write_staged_file

BACKUP_INFIX = ".bak."
"""What marks a file as one of our backups. Appended to the whole file name, extension included,
so `pipelex.toml` backs up to `pipelex.toml.bak.<stamp>` and never shadows a real `.toml`."""

RESCUE_INFIX = ".rescue."
"""What marks a copy that has left the rotation. Deliberately outside the `.bak.` family so that
`existing_backups_of` cannot see it and pruning can never take it."""

BACKUP_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
"""A UTC stamp with no separators a filesystem dislikes — no colons, which Windows refuses."""

_BACKUP_STAMP_PATTERN = re.compile(r"\d{8}T\d{6}Z")
"""The stamp, as the shape `BACKUP_STAMP_FORMAT` renders — what tells one of our backups from a
file the user named `<file>.bak.notes` themselves."""

BACKUP_STAMP_GLOB = f"{'[0-9]' * 8}T{'[0-9]' * 6}Z"
"""The same shape again, in the only vocabulary a `.gitignore` rule or an `fnmatch` filter has.

It lives beside the regex rather than wherever a glob happens to be needed, so the two spellings
of one stamp cannot drift apart, and so a change to `BACKUP_STAMP_FORMAT` has one obvious list of
things to change with it.

A glob has no repetition count, so the eight-digit date and the six-digit time are spelled out
rather than abbreviated to a `[0-9]*` run. The run looks equivalent and is not: its `*` accepts
anything at all, so it also matches `pipelex.toml.bak.1-notesZ` — a name `existing_backups_of`
reads as the user's own and refuses to prune. Anything that declines to manage a file should not
be hiding it either.

Nothing translates the strftime string into this, on purpose: a parser for format directives is
more machinery than one constant is worth. What holds the two together is the test matching this
pattern against a name `backup_path_for` actually produced, which goes red if the stamp restamps.
"""


class WrittenBackup(NamedTuple):
    """Where this file's backup is, and whether this run is the one that put it there.

    The second half is what keeps a failed run from deleting somebody else's copy: only a run that
    created a backup may discard it.
    """

    path: Path
    was_created: bool


class RescuedBackup(NamedTuple):
    """Where the pre-migration copy is after a write nobody could vouch for, and whether it is safe there.

    The second half is what the report needs. A copy this run could not move — because another run
    made it, because the rescue name was taken, or because the rename would not go — is still under
    a `.bak.<stamp>` name, which the next successful run of the same file prunes. Naming it is
    right; promising it will be waiting is not.
    """

    path: Path
    was_rescued: bool


def backup_stamp(*, moment: datetime) -> str:
    """Render a moment as the stamp a backup file name carries.

    The moment is a parameter rather than read here, so that a caller stamps every file of one
    run identically and a test can assert on a name it chose.
    """
    return moment.strftime(BACKUP_STAMP_FORMAT)


def backup_path_for(*, path: Path, moment: datetime) -> Path:
    return path.with_name(f"{path.name}{BACKUP_INFIX}{backup_stamp(moment=moment)}")


def rescue_path_for(*, path: Path, moment: datetime) -> Path:
    return path.with_name(f"{path.name}{RESCUE_INFIX}{backup_stamp(moment=moment)}")


def existing_backups_of(*, path: Path) -> list[Path]:
    """Every backup of one file currently on disk, oldest name first.

    Matched by name rather than by a recorded list: the backups are the user's files too, and a
    side record of which ones we wrote would be one more piece of untracked state to go stale.
    Matched by the *whole* name we write, stamp included, because a directory can also hold a
    copy the user made by hand under a name that merely starts the same way — and pruning must
    never take one of those.
    """
    # Matched by string prefix rather than by glob, so a file name carrying a glob metacharacter
    # (`telemetry_[eu].toml`, say) can never match a sibling's backups and have them pruned.
    prefix = f"{path.name}{BACKUP_INFIX}"
    return sorted(
        candidate
        for candidate in path.parent.iterdir()
        if candidate.name.startswith(prefix) and _BACKUP_STAMP_PATTERN.fullmatch(candidate.name[len(prefix) :])
    )


def write_backup(*, snapshot: FileSnapshot, moment: datetime) -> WrittenBackup:
    """Write the pre-migration copy of one file and return where it landed, and by whose hand.

    Staged and atomically renamed like any other write in this codebase, which also gets the mode
    right for free: the staged temp file is created `0600` and `fchmod`-ed to the source's mode
    before it is ever visible under its final name. A rename that fails takes the staged copy with
    it — the user's directory is not where a half-made backup gets left.

    The final name is **reserved** before the rename rather than simply overwritten, so a run that
    finds the name already taken leaves that copy alone and says so. Two runs inside one UTC second
    address the same name, and the one already there is a copy of an older state of the file: the
    original, if anything is. Clobbering it would destroy the only thing a backup is for.
    """
    destination = backup_path_for(path=snapshot.path, moment=moment)
    staged_path = write_staged_file(snapshot=snapshot, content=snapshot.content, label="backup")
    try:
        if not _reserve_name(path=destination):
            return WrittenBackup(path=destination, was_created=False)
        try:
            staged_path.replace(destination)
        except OSError:
            destination.unlink(missing_ok=True)
            raise
    finally:
        # A no-op once the rename succeeded, which is the point of `missing_ok`.
        staged_path.unlink(missing_ok=True)
    _make_directory_durable(directory=destination.parent)
    return WrittenBackup(path=destination, was_created=True)


def keep_backup_for_rescue(*, path: Path, backup_path: Path, moment: datetime) -> RescuedBackup:
    """Move a backup out of the `.bak.` rotation and report where it now lives, and whether it moved.

    Called when a write failed in a state the transaction could not describe. The copy is then the
    only one whose provenance is certain, and the report names it to the user — so the next
    successful run of the same file must not prune it away, which is exactly what it would do to
    anything still named `.bak.<stamp>`.

    Returns the path the copy is actually at, rather than the one it was headed for: a rename that
    will not go, or a rescue name another run has already taken, leaves the copy where it is rather
    than losing it to a tidier name. It leaves it inside the rotation too, and `was_rescued` is how
    the report knows to tell the user to take it now rather than later.

    "Where it is" is answered as of this call. The stamp resolves to the second and nothing here
    locks, so a third run of the same file that commits in between can prune the copy out from
    under an unrescued name — the one case in which the returned path names a file that has since
    gone. Closing it means coordinating pruning across processes, which is more machinery than a
    module with no command driving it yet has earned.
    """
    rescue_path = rescue_path_for(path=path, moment=moment)
    try:
        if not _reserve_name(path=rescue_path):
            return RescuedBackup(path=backup_path, was_rescued=False)
    except OSError:
        return RescuedBackup(path=backup_path, was_rescued=False)
    try:
        backup_path.replace(rescue_path)
    except OSError:
        # The reservation is this call's own empty file, and a rename that would not go leaves it
        # standing in for a copy that is still under its old name.
        rescue_path.unlink(missing_ok=True)
        return RescuedBackup(path=backup_path, was_rescued=False)
    _make_directory_durable(directory=rescue_path.parent)
    return RescuedBackup(path=rescue_path, was_rescued=True)


def prune_backups_except(*, path: Path, keep: Path) -> list[Path]:
    """Delete every backup of `path` other than `keep`, returning the ones removed.

    Called only after the new file is committed: pruning first would leave a window with no
    backup at all, which is the one state this helper exists to prevent. A rescue copy is not a
    backup by this name and is never a candidate.
    """
    pruned: list[Path] = []
    for candidate in existing_backups_of(path=path):
        if candidate == keep:
            continue
        candidate.unlink(missing_ok=True)
        pruned.append(candidate)
    return pruned


def _reserve_name(*, path: Path) -> bool:
    """Claim a file name atomically, reporting whether this call is the one that got it.

    An exclusive create rather than a `path.exists()` test, because the question only means
    anything if asking it and answering it are one operation: between a check and a rename another
    process can place its own copy, and the rename would silently take it away.
    """
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    os.close(descriptor)
    return True


def _make_directory_durable(*, directory: Path) -> None:
    """`fsync` a directory, so a copy's *name* survives a crash and not only its bytes.

    `write_staged_file` already `fsync`-s the contents; a rename is durable only once the directory
    holding the new entry is. Doing it here — after the backup lands, before the target is replaced
    — is what makes the migration's ordering a guarantee across a power loss rather than only
    across a process exit. The target's own replacement is deliberately not synced: a migration
    lost to a crash is replayed by the next run, while a lost backup is lost.

    Directories cannot be opened for reading on Windows, so the call is skipped there; a failure to
    sync is a weaker guarantee, never a reason to fail a backup that is already written.
    """
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        return
    finally:
        os.close(descriptor)
