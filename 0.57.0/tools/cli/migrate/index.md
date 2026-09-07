# `pipelex migrate`

Pipelex's configuration files occasionally change shape — a setting moves into a new section, a section is renamed. When that happens, the files already on your machine still hold your choices, but the installed Pipelex no longer recognizes them, and the boot fails.

`pipelex migrate` repairs those files in place. It keeps every value you set; it never replaces a file with a fresh template.

```bash
pipelex migrate            # show what would change, then ask
pipelex migrate --dry-run  # show what would change and stop
pipelex migrate --yes      # apply without asking
```

## What it touches

Two directories, and only those:

- the global `~/.pipelex/`
- the project `.pipelex/`, when the current directory is inside a project that has one

Within each, it looks at the configuration files themselves — `pipelex.toml` and its `pipelex_*.toml` tiers, `telemetry.toml` and its tiers, `pipelex_service.toml` — and at the inference backend definitions in `inference/backends/`.

It goes one level deep, and only into a directory some configuration family owns. `inference/backends/` is such a directory, so every `*.toml` in it is repaired the same way a `pipelex.toml` is. `inference/deck/` is not one, and neither is `inference/backends.toml`, which sits beside the backends directory rather than in it — neither is ever entered or rewritten by this command, and the model deck has its own `pipelex update`.

Within a file it repairs, it only ever undoes a change *we* made. A key you added yourself — a misspelling, or a setting from a plugin — is reported rather than removed, because the migration history describes our renames and removals and has nothing to say about your keys.

## What it does to a file

Every file it changes is copied first, beside itself, as `<file>.bak.<UTC timestamp>` — with the original file's permissions, not your umask. The copy is on disk before the file is replaced, and the replacement is atomic: there is never a moment when your configuration is half-written.

Those copies are ours, not part of your project, so the command keeps them out of your way: it writes a `.gitignore` inside the configuration directory itself, ignoring exactly the timestamped copies it makes. You will see the `.gitignore` — commit it, and your teammates get the same quiet. If you already have one there, it is left alone. You get it from any run that is allowed to write, including one that finds nothing to migrate — so a configuration directory that predates this picks the rule up on your next `pipelex migrate`, whether or not it has anything to carry forward. A `<file>.rescue.<timestamp>` copy is deliberately *not* ignored: one of those only exists because a write could not be vouched for, and seeing it is how you find out.

Running it twice is the same as running it once. Nothing is skipped on the basis of a version record, because there is no version record; every run replays the whole history and leaves alone whatever is already current. A file that is already up to date comes back byte for byte identical.

## When it cannot do the whole job

Some changes cannot be made for you. A setting whose accepted values narrowed, for instance, needs someone who knows what the value was *meant* to be — so Pipelex names the key and leaves it to you rather than guessing. The report says which file, which key, and what to look at. Everything it *can* do is still done, and one file it cannot process never stops the others.

The command exits non-zero when it leaves something for you to look at.

## Running it when nothing else runs

`pipelex migrate` does not boot Pipelex. That is the point: a configuration that cannot load is exactly when you need it, so it uses the migration history, the file editor and the filesystem, and nothing else. It works with no credentials, no model deck and no network.

## The warning that sends you here

You will usually meet this command through a warning rather than a crash. When a file is out of date in a way the migration history explains, Pipelex boots anyway: it carries the file forward **in memory**, tells you which files it did that for, and points at this command. That covers your inference backend definitions as well as the configuration files proper — a backend file left behind by a model-spec change boots on the models it would have loaded anyway, and the warning arrives with the rest of the model setup. Nothing is written, so the same warning appears at the next boot, and the one after — running `pipelex migrate` is what makes the change to the file and stops it.

A file the history cannot explain is a different case, and it still fails the boot with the configuration error itself: tolerance widens what starts, never what is accepted. That error names this command too, though — beside the key it could not accept, it tells you which of your files a migration would touch, what it would carry forward, and what only you can decide.

`pipelex doctor` is the third way here, and the one to reach for when nothing has gone wrong yet. It has a **Configuration Migrations** row that is this command's own dry run: it names every file a migration would rewrite, with its full path, and separately any file carrying something the command will not do on its own. `pipelex doctor --fix` then offers to run the migration for you — the same run, after showing you what it is about to do.

That row answers for both configuration directories, the global one and the project one, even when the rest of the report is about a single directory. It is describing a command, and the command walks both — a row that named fewer files than the command touches would be the one surprise worth avoiding here.

Nothing that Pipelex tells you about an out-of-date file will ever suggest deleting it and starting over — that is what this command exists to make unnecessary.

## For agents

`pipelex-agent migrate` is the machine-facing counterpart. It writes only when passed `--yes`, since it cannot ask, and answers with a structured plan — `--format json` for the contract, `--format markdown` to read. Branch on the `needs_attention` field, never on the exit code.

An agent usually meets this command through a failure rather than by choosing it. A configuration error carries a `migration` field when — and only when — a scan of the machine found something; its presence is the signal that the configuration is *old* rather than *wrong*. The loop from there is `pipelex-agent migrate --dry-run --format json`, show the user what would change, then `--yes` on confirmation. Never hand-edit a configuration file.

## See also

- [`pipelex doctor`](index.md) — check configuration health
- [`pipelex init`](init.md) — create configuration files from scratch
