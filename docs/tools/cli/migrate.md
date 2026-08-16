---
title: "CLI Migrate"
description: "Bring the Pipelex configuration files on your machine up to the schema the installed version expects."
---

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

Within each, it looks at the configuration files themselves — `pipelex.toml` and its `pipelex_*.toml` tiers, `telemetry.toml` and its tiers, `pipelex_service.toml`. It does not descend into subdirectories, so your inference backends and model deck are never rewritten by it.

## What it does to a file

Every file it changes is copied first, beside itself, as `<file>.bak.<UTC timestamp>` — with the original file's permissions, not your umask. The copy is on disk before the file is replaced, and the replacement is atomic: there is never a moment when your configuration is half-written.

Running it twice is the same as running it once. Nothing is skipped on the basis of a version record, because there is no version record; every run replays the whole history and leaves alone whatever is already current. A file that is already up to date comes back byte for byte identical.

## When it cannot do the whole job

Some changes cannot be made for you. A setting whose accepted values narrowed, for instance, needs someone who knows what the value was *meant* to be — so Pipelex names the key and leaves it to you rather than guessing. The report says which file, which key, and what to look at. Everything it *can* do is still done, and one file it cannot process never stops the others.

The command exits non-zero when it leaves something for you to look at.

## Running it when nothing else runs

`pipelex migrate` does not boot Pipelex. That is the point: a configuration that cannot load is exactly when you need it, so it uses the migration history, the file editor and the filesystem, and nothing else. It works with no credentials, no model deck and no network.

## For agents

`pipelex-agent migrate` is the machine-facing counterpart. It writes only when passed `--yes`, since it cannot ask, and answers with a structured plan — `--format json` for the contract, `--format markdown` to read. Branch on the `needs_attention` field, never on the exit code.

## See also

- [`pipelex doctor`](index.md) — check configuration health
- [`pipelex init`](init.md) — create configuration files from scratch
