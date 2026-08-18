"""The `.gitignore` pipelex keeps inside the configuration directory it owns.

A migration copies every file before it rewrites it, and that copy lands beside the original —
inside `.pipelex/`, which in a real project is inside a git repository. Without a rule, one
`pipelex migrate` puts a dozen untracked `.bak.<stamp>` files into the user's `git status`, and
the user is left to work out which of them are ours and write the pattern themselves. Each of
them writes a slightly different one, or forgets, and a tool that dirties a repository every time
it runs stops getting run.

**Why the rule lives here and not in the user's root `.gitignore`.** The walk is the global
`~/.pipelex/` and the project `.pipelex/`, and nothing else (see `run.py`), so every backup a
migration can ever write inside a repository is under a directory pipelex already owns. That makes
a `.gitignore` *in* that directory a complete answer — it needs no knowledge of where the
repository root is, survives the directory being moved or vendored, and never reaches into a file
the user maintains for their whole project.

**The pattern is derived from the namer, not retyped.** `BACKUP_INFIX` is what
`backup_path_for` actually writes; spelling `*.bak.…` again here would let a rename of the infix
leave a rule that silently matches nothing.

Two omissions are deliberate:

- **A `.rescue.` copy is not ignored.** It exists only because a write ended in a state the
  transaction could not describe, and the report tells the user to go and get it. Turning up in
  `git status` is that reminder working; hiding it would bury the one file that needs a human.
- **A copy the user named themselves — `pipelex.toml.bak.notes` — is not ignored.** Pruning
  already refuses to touch one of those, on the grounds that it is the user's file and not ours;
  hiding it from their own `git status` would be the same mistake in the other direction.

See `docs/migration-ledger.md` → "Backups".
"""

import os
from pathlib import Path

from pipelex.migration.backup import BACKUP_INFIX

CONFIG_DIR_GITIGNORE_NAME = ".gitignore"
"""What the file is called inside `~/.pipelex/` or a project's `.pipelex/`."""

BACKUP_IGNORE_PATTERN = f"*{BACKUP_INFIX}[0-9]*Z"
"""The one rule the file carries: any name ending in the infix, a digit-led run, and the UTC `Z`.

The digit and the trailing `Z` are what `BACKUP_STAMP_FORMAT` renders and what a name the user
chose does not, which is how `pipelex.toml.bak.notes` stays visible.
"""

_GITIGNORE_CONTENT = f"""\
# Written by pipelex when it set this directory up. Yours from here on — pipelex reads this file
# never, and rewrites it never. Delete a line and it stays deleted.
#
# The timestamped copy `pipelex migrate` takes of every file before it rewrites it. It is our own
# transient artifact; the durable history of these files is your commits.
#
# A `<file>.rescue.<stamp>` copy is deliberately NOT listed. One of those exists only because a
# write could not be vouched for, and seeing it in `git status` is how you find out.
{BACKUP_IGNORE_PATTERN}
"""


def ensure_config_dir_gitignore(*, directory: Path) -> bool:
    """Put the file in a configuration directory that has none, and report whether this call did.

    Create-if-absent, and nothing else. Once a `.gitignore` is there it is a file in the user's
    repository — possibly one they wrote, possibly ours with a line taken out on purpose — and
    re-asserting our rule into it every run would be a tool arguing with its user. So an existing
    file is left byte for byte alone, which also makes this idempotent for free.

    The create is exclusive rather than an `exists()` test followed by a write, for the same reason
    `backup._reserve_name` is: between the check and the write another run can place the file, and
    the write would silently take it away.

    A directory that is not there is not created. A migration walk skips a configuration directory
    that does not exist, and ensuring a rule inside one must not be the thing that conjures it.
    """
    if not directory.is_dir():
        return False
    path = directory / CONFIG_DIR_GITIGNORE_NAME
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
    except FileExistsError:
        return False
    except OSError:
        # A read-only or otherwise unwritable configuration directory is the user's business, and
        # a missing convenience rule is never a reason to fail the migration that was asked for.
        return False
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(_GITIGNORE_CONTENT)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        path.unlink(missing_ok=True)
        return False
    return True
