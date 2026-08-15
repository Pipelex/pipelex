"""Backups — the copy taken before a user's configuration file is rewritten.

Always, before writing. Exactly **one** backup per file: a successful run replaces the previous
one, so a directory does not accumulate a decade of copies of a file whose durable history is
already in git. For the untracked files — and for the moment between two commits — this copy is
the whole safety net.

The mode is inherited from the source rather than left to the process umask, and that is the one
deliberate exception to "no value read from a user's file is ever rendered": a backup contains the
user's values by definition, so a `0600` configuration must not become a world-readable `0644`
copy sitting beside it.

See `docs/migration-ledger.md` → "Backups".
"""

from datetime import datetime
from pathlib import Path

from pipelex.pipeline.fixes.file_transaction import FileSnapshot, write_staged_file

BACKUP_INFIX = ".bak."
"""What marks a file as one of our backups. Appended to the whole file name, extension included,
so `pipelex.toml` backs up to `pipelex.toml.bak.<stamp>` and never shadows a real `.toml`."""

BACKUP_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
"""A UTC stamp with no separators a filesystem dislikes — no colons, which Windows refuses."""


def backup_stamp(*, moment: datetime) -> str:
    """Render a moment as the stamp a backup file name carries.

    The moment is a parameter rather than read here, so that a caller stamps every file of one
    run identically and a test can assert on a name it chose.
    """
    return moment.strftime(BACKUP_STAMP_FORMAT)


def backup_path_for(*, path: Path, moment: datetime) -> Path:
    return path.with_name(f"{path.name}{BACKUP_INFIX}{backup_stamp(moment=moment)}")


def existing_backups_of(*, path: Path) -> list[Path]:
    """Every backup of one file currently on disk, oldest name first.

    Matched by name rather than by a recorded list: the backups are the user's files too, and a
    side record of which ones we wrote would be one more piece of untracked state to go stale.
    """
    return sorted(path.parent.glob(f"{path.name}{BACKUP_INFIX}*"))


def write_backup(*, snapshot: FileSnapshot, moment: datetime) -> Path:
    """Write the pre-migration copy of one file and return where it landed.

    Staged and atomically renamed like any other write in this codebase, which also gets the mode
    right for free: the staged temp file is created `0600` and `fchmod`-ed to the source's mode
    before it is ever visible under its final name.
    """
    destination = backup_path_for(path=snapshot.path, moment=moment)
    staged_path = write_staged_file(snapshot=snapshot, content=snapshot.content, label="backup")
    staged_path.replace(destination)
    return destination


def prune_backups_except(*, path: Path, keep: Path) -> list[Path]:
    """Delete every backup of `path` other than `keep`, returning the ones removed.

    Called only after the new file is committed: pruning first would leave a window with no
    backup at all, which is the one state this helper exists to prevent.
    """
    pruned: list[Path] = []
    for candidate in existing_backups_of(path=path):
        if candidate == keep:
            continue
        candidate.unlink(missing_ok=True)
        pruned.append(candidate)
    return pruned
