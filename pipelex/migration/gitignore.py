"""The `.gitignore` pipelex keeps inside the configuration directory it owns.

Two kinds of file in that directory are not the project's to commit, and the file carries a rule
for each.

The first is a personal override: `pipelex_override.toml` and its siblings, and the two inference
overrides `inference/backends_override.toml` and `inference/routing_profiles_override.toml`. Each
is read on top of a tracked file and carries only the keys it sets, so a developer runs on the
backend of their choice, or reports telemetry where they like, without editing the file the project
ships — provided the override never reaches the commit. Listing them here is what makes a fresh
`pipelex init` project safe by default; a project set up before a rule existed keeps its own file
and adds the line itself, because this file is never rewritten (see below).

The second is a backup. A migration copies every file before it rewrites it, and that copy lands
beside the original — inside `.pipelex/`, which in a real project is inside a git repository.
Without a rule, one `pipelex migrate` puts a dozen untracked `.bak.<stamp>` files into the user's
`git status`, and the user is left to work out which of them are ours and write the pattern
themselves. Each of them writes a slightly different one, or forgets, and a tool that dirties a
repository every time it runs stops getting run.

**Why the rule lives here and not in the user's root `.gitignore`.** The walk is the global
`~/.pipelex/` and the project `.pipelex/`, and nothing else (see `run.py`), so a backup written
under a directory pipelex already owns is answered by a `.gitignore` *in* that directory — one that
needs no knowledge of where the repository root is, survives the directory being moved or vendored,
and never reaches into a file the user maintains for their whole project.

**The one backup this does not reach, and why it is left.** A configuration file that is a symlink
is migrated through to the file it names, and its backup lands beside *that* file (see
`runner.migrate_file`) — in a dotfiles directory, which is the user's and not ours. The rule
deliberately does not follow it there: writing into the `.gitignore` of somebody's whole dotfiles
repository is a larger liberty than the one untracked copy it would hide.

**The pattern is derived from the namer, not retyped.** `BACKUP_INFIX` and
`BACKUP_STAMP_GLOB` are what `backup_path_for` actually writes; spelling `*.bak.…` again here would
let a rename of the infix — or a restamp — leave a rule that silently matches nothing.

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

from pipelex.migration.backup import BACKUP_INFIX, BACKUP_STAMP_GLOB

CONFIG_DIR_GITIGNORE_NAME = ".gitignore"
"""What the file is called inside `~/.pipelex/` or a project's `.pipelex/`."""

BACKUP_IGNORE_PATTERN = f"*{BACKUP_INFIX}{BACKUP_STAMP_GLOB}"
"""The backup rule: any name ending in the infix followed by exactly the stamp.

Exactly the stamp, rather than something stamp-shaped, is what keeps `pipelex.toml.bak.notes` — and
every other copy the user named themselves — visible in their own `git status`.
"""

PERSONAL_OVERRIDE_IGNORE_PATTERNS: tuple[str, ...] = (
    "pipelex_override.toml",
    "pipelex_temporary_override.toml",
    "telemetry_override.toml",
    "inference/backends_override.toml",
    "inference/routing_profiles_override.toml",
)
"""The personal override files pipelex layers over the tracked ones, one rule each.

Each carries only the keys it sets, on top of a file the project tracks — which is the whole point
of it: a developer's own choices (their observability, the backend they run on) stay theirs, and a
project's defaults ship as the project wrote them. The two inference overrides are named with their
subdirectory, because a rule with a slash in it is anchored to this directory rather than matched at
any depth. What is *not* here: `pipelex_local.toml` and the `pipelex_{{environment}}.toml` tier, which
are part of a project's tracked configuration, and `pipelex_service.toml`, which is not an override.
"""

_GITIGNORE_CONTENT = f"""\
# Written by pipelex when it set this directory up. Yours from here on — pipelex reads this file
# never, and rewrites it never. Delete a line and it stays deleted.
#
# The personal override files pipelex layers over the tracked ones. Each carries only the keys it
# sets, so what a machine chooses for itself stays out of what the project commits.
{chr(10).join(PERSONAL_OVERRIDE_IGNORE_PATTERNS)}
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
        try:
            path.unlink(missing_ok=True)
        except OSError:
            # `missing_ok` covers a file that is gone, not a filesystem that says no — and the one
            # that just refused the write is exactly the one that can refuse the removal. Letting
            # that escape would turn a missing convenience rule into a failed migration, which is
            # the outcome every other branch of this function exists to avoid.
            pass
        return False
    return True
