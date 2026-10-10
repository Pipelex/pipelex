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

- the home configuration directory (`~/.pipelex/`, or `PIPELEX_HOME`; see [Configuration](../../configuration/index.md#the-home-configuration-directory-pipelex_home))
- the project `.pipelex/`, when the current directory is inside a project that has one

Within each, it looks at the configuration files themselves — `pipelex.toml` and its `pipelex_*.toml` tiers, `telemetry.toml` and its tiers — and at the inference backend definitions in `inference/backends/`.

It goes one level deep, and only into a directory some configuration family owns. `inference/backends/` is such a directory, so every `*.toml` in it is repaired the same way a `pipelex.toml` is. `inference/deck/` is not one, and is never entered: the model deck has its own `pipelex update`. Neither is `inference/backends.toml`, which sits beside the backends directory rather than in it, nor `inference/routing_profiles.toml`: the one thing this command ever does to them is remove what a [former release](#a-configuration-a-former-release-set-up) left in them.

Within a file it repairs, it only ever undoes a change *we* made. A key you added yourself — a misspelling, or a setting from a plugin — is reported rather than removed, because the migration history describes our renames and removals and has nothing to say about your keys.

## What it does to a file

Every file it changes is copied first, beside itself, as `<file>.bak.<UTC timestamp>` — with the original file's permissions, not your umask. The copy is on disk before the file is replaced, and the replacement is atomic: there is never a moment when your configuration is half-written.

Those copies are ours, not part of your project, so the command keeps them out of your way: it writes a `.gitignore` inside the configuration directory itself, ignoring exactly the timestamped copies it makes. You will see the `.gitignore` — commit it, and your teammates get the same quiet. If you already have one there, it is left alone. You get it from any run that is allowed to write, including one that finds nothing to migrate — so a configuration directory that predates this picks the rule up on your next `pipelex migrate`, whether or not it has anything to carry forward. A `<file>.rescue.<timestamp>` copy is deliberately *not* ignored: one of those only exists because a write could not be vouched for, and seeing it is how you find out.

Running it twice is the same as running it once. Nothing is skipped on the basis of a version record, because there is no version record; every run replays the whole history and leaves alone whatever is already current. A file that is already up to date comes back byte for byte identical.

## A configuration a former release set up

Releases up to v0.72 ran models through the Pipelex Gateway. It no longer exists, and the files those releases wrote still name it. Pipelex refuses to start on some of them, and says so with one error that names this command and [`pipelex init`](init.md#a-machine-a-former-release-set-up):

- a `pipelex_gateway` backend left enabled in `inference/backends.toml`, or another backend still naming `model_specs_section`, whose model specs are no longer downloaded;
- an active routing profile that sends models to it: `all_pipelex_gateway`, which those releases made the default, or a profile routing some models there.

The cleanup of what those releases left is this command's first step, before any file is migrated. It reads the home directory and the project's together, the way Pipelex merges them when it starts, so a profile defined in one and made active from the other is cleaned up as one:

- the `pipelex_gateway` table is removed from `inference/backends.toml` and its personal override, and a `model_specs_section` key from any other backend, which stays;
- a routing profile whose default is the Gateway is removed, and so is a route that sends a model to it, from a profile that otherwise stays, a catch-all `"*"` route included;
- when a profile of your own is only pointed at the Gateway by a personal override, only that `default` is removed from the override, so your profile and its routes stay as you wrote them;
- an active routing profile that is removed, or left with nothing to route models by, is replaced in the files that name it, in either directory. In a base file it moves to `all_enabled_backends`, the profile a fresh install makes active, which routes each model to the first enabled backend that serves it; when the file does not define that profile, it is added as the current release ships it. A personal override that names it stops naming any, so the file read before it decides;
- Pipelex starting outside any project and Pipelex starting in your project read some files in common, your home's override above all, and the cleanup plans its changes so that none of them switches the other to another routing profile or stops it from starting. When your project needs a different `active` from the one outside it, your project's personal override is given one of its own. That holds when every file can be written: the files are written one by one, so if one fails after others were written, the report names it, and until you make its change by hand Pipelex may start on another profile where that file is read;
- `inference/backends/pipelex_gateway.toml`, the Gateway's model lists `inference/backends/pipelex_gateway_models*.md` and `pipelex_service.toml`, which recorded the Gateway's terms acceptance, are removed;
- the paragraph of instructions about the Pipelex Gateway those releases wrote at the head of `routing_profiles.toml` goes with them; every other comment stays, including a note of yours that mentions the Gateway.

Nothing else is touched: your other backends, your own profiles and routes, and your keys stay as they are. Pipelex Manifold, which those releases offered as a private beta, is not retired, so what they left for it — a `pipelex_manifold` table shipped disabled, `inference/backends/pipelex_manifold.toml` and the `all_pipelex_manifold` profile — stays too. Each file the cleanup rewrites or removes is copied first, exactly as a migrated file is (below), so a removed file is one rename away from being back. The dry run shows each change, file by file, and the question that follows counts the files of both steps. A file the cleanup removes is never also counted among the files to migrate, nor reported as needing a look.

Some cases end with something for you to do, and the command exits non-zero for each. A file the cleanup cannot rewrite safely is left as it is, and the report says what to change by hand, then run the command again: a routing profiles file written as one inline `profiles = { … }` table, which the cleanup cannot add a profile to without restructuring it, and a file read both outside your project and in it whose `active` would have to change for one and not the other, when your project has no personal override to hold its own. And on every run, a dry run and a run with nothing left to clean included, the command reads the files Pipelex starts on as the cleanup leaves them: if they still stop it — an active routing profile that no file defines, for instance, left by a cleanup run from another project — it says so under **Pipelex cannot start** or **After the cleanup, Pipelex still cannot start** instead of reporting success or that there is nothing to do.

`pipelex doctor` lists these files in its **Configuration Migrations** row and says when they stop Pipelex from starting, and `pipelex doctor --fix` runs the cleanup on a yes. When Pipelex would still not start once the cleanup has run, the row says so and recommends `pipelex migrate --dry-run`, which says why: that is left for you to fix, so `--fix` has nothing to write for it. Both judge that from the files Pipelex actually starts on in the current directory: a project with configuration files of its own is not told it cannot start because of what your home directory still carries, though the files are listed and the cleanup is offered. `pipelex init` finds them too, and offers the same cleanup before it asks anything else.

## When it cannot do the whole job

Some changes cannot be made for you. A setting whose accepted values narrowed, for instance, needs someone who knows what the value was *meant* to be — so Pipelex names the key and leaves it to you rather than guessing. The report says which file, which key, and what to look at. Everything it *can* do is still done, and one file it cannot process never stops the others.

The command exits non-zero when it leaves something for you to look at.

## Running it when nothing else runs

`pipelex migrate` does not boot Pipelex. That is the point: a configuration that cannot load is exactly when you need it, so it uses the migration history, the file editor and the filesystem, and nothing else. It works with no credentials, no model deck and no network.

## The warning that sends you here

You will usually meet this command through a warning rather than a crash. When a file is out of date in a way the migration history explains, Pipelex boots anyway: it carries the file forward **in memory**, tells you which files it did that for, and points at this command. That covers your inference backend definitions as well as the configuration files proper — a backend file left behind by a model-spec change boots on the models it would have loaded anyway, and the warning arrives with the rest of the model setup. Nothing is written, so the same warning appears at the next boot, and the one after — running `pipelex migrate` is what makes the change to the file and stops it. When some of what a file needs cannot be applied for you, the warning says so, and `pipelex migrate` reports those changes for you to make by hand; a file the command does not reach is yours to update where it lives, and its warning says that instead.

A file the history cannot explain is a different case, and it still fails the boot with the configuration error itself: tolerance widens what starts, never what is accepted. That error names this command too, though — beside the key it could not accept, it tells you which of your files a migration would touch, what it would carry forward, and what only you can decide.

`pipelex doctor` is the third way here, and the one to reach for when nothing has gone wrong yet. It has a **Configuration Migrations** row that is this command's own dry run: it names every file a migration would rewrite, with its full path, and separately any file carrying something the command will not do on its own. `pipelex doctor --fix` then offers to run the migration for you — the same run, after showing you what it is about to do.

That row answers for both configuration directories, the global one and the project one, even when the rest of the report is about a single directory. It is describing a command, and the command walks both — a row that named fewer files than the command touches would be the one surprise worth avoiding here.

Nothing that Pipelex tells you about an out-of-date file will ever suggest deleting it and starting over — that is what this command exists to make unnecessary.

## For agents

`pipelex-agent migrate` is the machine-facing counterpart. It writes only when passed `--yes`, since it cannot ask, and answers with a structured plan — `--format json` for the contract, `--format markdown` to read. Branch on the `needs_attention` field, never on the exit code. The cleanup of a former release is under `former_release`: each file it rewrites or removes, with its `action` (`rewrite` or `remove`), its `changes` in words, the `backup_path` once applied, and why it was left when it could not be cleaned (`needs_a_hand_edit` for an inline profiles table, a file both boots read that no change suits, or a change the cleanup cannot express, with what to change in `blocked_detail`). `former_release.still_blocking` lists what would still stop Pipelex from starting once the cleanup is done, one sentence each, on every run: after `--yes`, read off the files written, and in a dry run, off the files as they would be written; it is empty when the machine can start. Both count toward `needs_attention` and `is_clean` like the migration itself. The files the cleanup removes are never among the `plans`.

An agent whose boot fails with `FormerReleaseConfigError` runs the same loop: `pipelex-agent migrate --dry-run --format json`, show the user what would be removed, then `--yes`.

An agent usually meets this command through a failure rather than by choosing it. A configuration error carries a `migration` field when — and only when — a scan of the machine found something; its presence is the signal that the configuration is *old* rather than *wrong*. The loop from there is `pipelex-agent migrate --dry-run --format json`, show the user what would change, then `--yes` on confirmation. Never hand-edit a configuration file.

## See also

- [`pipelex doctor`](doctor.md) — check configuration health
- [`pipelex init`](init.md) — create configuration files from scratch
