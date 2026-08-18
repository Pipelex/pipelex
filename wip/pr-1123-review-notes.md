# PR #1123 review follow-up — the one backup the config-directory `.gitignore` cannot reach

**Status:** Deferred from the v0.46.2 release review (2026-08-18). Not a regression — the gap arrives with the feature, and the feature is still a strict improvement over having no rule at all. What is deferred is the *remedy*, because every version of it is a design reversal rather than a fix.

**Reported by:** Codex (thread `PRRT_kwDOOwmMFc6aHHck`) and cubic (thread `PRRT_kwDOOwmMFc6aHLr8`), both against `pipelex/migration/run.py:69-71`. Both threads were left open on purpose.

## What is true

`migrate_config_directories` ensures a `.gitignore` in each *walked* configuration directory — `~/.pipelex/` and the project `.pipelex/`. But `migrate_file` resolves symlinks before it snapshots the file (`pipelex/migration/runner.py:42`, `read_file_snapshot(file_path.resolve())`), deliberately and with a comment saying so: an atomic replace of the link path would delete the link and leave the real file unmigrated. The backup is then named from the *resolved* path, so for a dotfiles setup — `.pipelex/pipelex.toml` symlinked to `~/dotfiles/pipelex.toml` — the `.bak.<stamp>` copy lands in `~/dotfiles/`, which the rule in `.pipelex/` cannot match. If that directory is itself a git repository, migrating dirties it, which is the exact workflow the feature exists to fix.

The behavior is covered by an existing test (`tests/unit/pipelex/migration/test_runner.py:602`), so this is a known, intended resolution — not an accident.

## Why nothing was changed

Two remedies present themselves, and both cost more than the gap:

- **Ensure a `.gitignore` beside the resolved backup too.** That means creating or relying on a `.gitignore` at the root of the user's dotfiles repository — a file they maintain for their whole project, which the design of this feature explicitly refuses to touch (`pipelex/migration/gitignore.py`, "never reaches into a file the user maintains for their whole project"). Writing there to hide one transient copy is a much larger liberty than the copy is worth.
- **Write the backup beside the link instead of the target.** That reverses a documented and tested decision about where a copy of a file belongs, and it would put the backup in a directory that is not the one holding the file it copies.

A third possibility exists and is the reason this is written down rather than closed: **do neither, and instead not back up through a symlink at all when the target is outside the walked directory** — reporting the file as one the migration will not rewrite on its own. That is a real behavior change with a real cost (a dotfiles user loses in-place migration), so it is a call for a human, not for a review pass on a release branch.

## What was done instead

The overclaim was removed. Both `pipelex/migration/gitignore.py`'s module docstring and `docs/migration-ledger.md` asserted that *every* backup a migration can write inside a repository is under a directory pipelex owns. That sentence is false under a symlink, and it is now replaced by an explicit statement of the exception and why the rule does not follow it.

## The open question

For a user whose `.pipelex/` configuration files are symlinks into a git-tracked dotfiles directory, should `pipelex migrate`:

1. keep today's behavior and accept that the backup dirties the target's repository (with the docs saying so, which is the current state);
2. leave the backup beside the link rather than the target;
3. decline to migrate through a symlink whose target is outside the walked directory, and report the file as one the user must handle; or
4. something else — e.g. name the escaped backup path in the migration report, so the user is told where the copy went rather than finding it in `git status`?

Option 4 is the cheapest and is worth considering on its own even if the answer to 1–3 is "keep today's behavior": the report already names paths, and a user who is told is not a user who is surprised.
