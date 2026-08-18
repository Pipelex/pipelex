"""What the `.pipelex` ↔ `pipelex/kit/configs` comparison is told to look past.

`pipelex/kit/configs/` holds the templates a project's `.pipelex/` is initialised from, and this
repository's own `.pipelex/` dogfoods them — so `check-config-sync` holds the two directories to the
same contents and `sync-kit-configs` mirrors one onto the other. A configuration directory in *use*
also holds things the kit has no counterpart for, and every one of them has to be declared here or
the check reports a project that has simply been used as out of sync.

**Why the two commands share one declaration.** `check-config-sync` reports and `sync-kit-configs`
acts, and its report names the sync as the remedy. If the check saw a file the sync would not touch,
it would send a developer to run a command that cannot make it pass; if the sync saw one the check
does not, it would quietly copy a local artifact into the shipped kit. Both read these constants.

**Why they live under the dev CLI rather than beside the kit paths.** Deriving the backup patterns
from the namer means importing `pipelex.migration`, which reaches the pipeline layer — and
`pipelex.kit.paths` is inside the kernel boot closure, which `tests/unit/pipelex/
test_kernel_layer_import_closure.py` keeps free of exactly that. These two commands are the only
consumers, and `pipelex-dev` is above the boundary, so the declaration belongs on this side of it.
See `docs/contribute/hub-layering.md`.
"""

from pipelex.kit.paths import GIT_IGNORED_CONFIG_FILES
from pipelex.migration.backup import BACKUP_INFIX, BACKUP_STAMP_GLOB, RESCUE_INFIX
from pipelex.migration.gitignore import CONFIG_DIR_GITIGNORE_NAME

# Files excluded from config sync checks but still copied during `pipelex init config`.
# Extends GIT_IGNORED_CONFIG_FILES with files that intentionally differ between the two sides:
# - telemetry.toml: the kit's holds the active global template, while the pipelex repo's
#   `.pipelex/telemetry.toml` dogfoods the commented-out project template.
# - plxt.toml: the repo's `.pipelex/plxt.toml` adds a `[rule.schema]` override pointing at the
#   locally generated `derived/mthds_schema.json` (this repo is the source of truth for the MTHDS
#   language); the kit template must not reference that repo-internal artifact — plxt hard-fails
#   on every .mthds file when the configured schema path does not exist.
# - .gitignore: written into a configuration directory by `ensure_config_dir_gitignore`, at init and
#   at migrate. It is a runtime artifact of the directory, never a kit template — the kit has no
#   copy to be in sync with, and giving it one would put two mechanisms in charge of one file.
CONFIG_SYNC_EXCLUDED_FILES: frozenset[str] = GIT_IGNORED_CONFIG_FILES | {"telemetry.toml", "plxt.toml", CONFIG_DIR_GITIGNORE_NAME}

# Name patterns excluded from config sync checks, for the artifacts no fixed name can name: every
# one of them carries the timestamp of the run that wrote it.
# - `<file>.bak.<stamp>`: the copy `pipelex migrate` takes before it rewrites a file. Migrating in a
#   checkout is a thing a developer does, and the run's own `.gitignore` already keeps these out of
#   `git status`; a sync check that went red on them would put the dirtied-repository problem that
#   `.gitignore` solves straight back, one gate over.
# - `<file>.rescue.<stamp>`: the copy kept when a write could not be vouched for. It is deliberately
#   NOT git-ignored, because turning up in `git status` is how the user is told to go and get it —
#   and that reminder is untouched by this. What excluding it here avoids is a sync check answering
#   a transient artifact with "run make up-kit-configs", which would vendor the copy into the kit.
#
# Built from the same infixes and stamp shape `backup_path_for` and `rescue_path_for` actually
# write, so renaming an infix or restamping cannot leave a pattern that silently matches nothing.
CONFIG_SYNC_EXCLUDED_PATTERNS: frozenset[str] = frozenset(
    {
        f"*{BACKUP_INFIX}{BACKUP_STAMP_GLOB}",
        f"*{RESCUE_INFIX}{BACKUP_STAMP_GLOB}",
    }
)
