---
description: "Refresh the kit-managed files of a Pipelex install — keep the model deck (`1_llm_deck.toml` and friends) and `backends/internal.toml` in sync with the kit shipped by your installed pipelex version, while preserving your `x_custom_*.toml` overrides and your own backend files."
---

# Update Command

Refresh the files Pipelex manages in your install, the model deck and `backends/internal.toml`, so they match the kit shipped with your current `pipelex` version.

```bash
pipelex update [OPTIONS]
pipelex update --local [OPTIONS]
```

When a new `pipelex` release ships changes to the model deck — new models, new aliases, retired entries — your previously installed deck under `~/.pipelex/inference/deck/` will fall behind. The same goes for `~/.pipelex/inference/backends/internal.toml`, which declares the software-only models open Pipelex ships, such as the built-in document engine `reportlab-pdf`: an install made before a release added a model does not declare it. `pipelex update` brings both up to date without nuking your overrides. `pipelex init` is no substitute: it is a full reset that rewrites every configuration file the kit ships, the backend files and the kit's `x_custom_*.toml` deck files included, so this command is how an install catches up without losing its settings.

## When to run it

Pipelex prints a one-line yellow advisory on most CLI invocations when it detects that the installed deck is older than the running package, or when no deck manifest is present yet (it is suppressed for `init`, `doctor`, `update`, `migrate`, and `which`):

```text
⚠ Pipelex model deck may be out of date — run pipelex update to refresh
```

Run `pipelex update` to clear the warning. To silence it permanently for a session or environment:

```bash
export PIPELEX_NO_DECK_NOTICE=1
```

A `PipeDocGen` step that prints on `reportlab-pdf` in an install whose `internal.toml` predates it is refused when its method loads, with an error that says to run `pipelex update`.

## What it does

Pipelex manages two areas of an install, each tracked by its own small JSON manifest, `.kit_manifest.json`, in its own directory:

- the model deck, `~/.pipelex/inference/deck/` (or `.pipelex/inference/deck/` for a project-local install);
- the backends directory, `~/.pipelex/inference/backends/` (or `.pipelex/inference/backends/`), where only `internal.toml` is managed.

Each area is found the way the runtime finds it: a project's `.pipelex/` directory wins when it has one, and the home configuration directory (`~/.pipelex/`, or `PIPELEX_HOME`; see [Configuration](../../configuration/index.md#the-home-configuration-directory-pipelex_home)) is used otherwise, so the command refreshes the files your runs actually read. A manifest stores the kit version that produced the install and a SHA-256 of each managed file at install time.

On `update`, Pipelex compares three states for each area — what the kit ships, what is on disk, what the manifest recorded — and produces a per-file plan:

| Status | Meaning | Action |
|---|---|---|
| `up-to-date` | Installed file matches the kit | none |
| `new` | Kit ships a new managed file not yet installed | install from kit |
| `behind` | Installed file unchanged from manifest, kit has newer content | overwrite from kit |
| `locally modified` | Installed file was edited after install — kit version differs | back up + overwrite |
| `removed upstream` | Kit no longer ships this file | back up + remove |

Locally-modified files are preserved as `<file>.bak.<UTC-timestamp>` before the kit version is written in their place, unless you pass `--no-backup`. Removed files get the same backup treatment before deletion. After the run, Pipelex writes a fresh manifest, stamped with the new kit version, for each area it updated.

## Managed files vs. user files

Pipelex draws a sharp line between the files it owns and the files you own.

- **Managed (pipelex-owned)** — the numbered deck files, `1_llm_deck.toml`, `2_img_gen_deck.toml`, `3_extract_deck.toml`, `4_search_deck.toml`, `5_doc_gen_deck.toml` and `6_judgment_deck.toml`, and `backends/internal.toml`. These are refreshed by `pipelex update`. Local edits are preserved with a `.bak.<timestamp>` backup but will not survive future updates.
- **User overrides** — any file in the deck directory whose name starts with `x_custom_` (e.g. `x_custom_llm_deck.toml`, `x_custom_extract_deck.toml`). `pipelex update` never tracks, hashes, copies, or removes these, while `pipelex init`, a full reset, rewrites the two the kit ships. Add new ones whenever you need to override aliases, presets, or default choices for a backend.
- **Every other backend file** — `openai.toml`, `anthropic.toml`, a backend of your own, and the rest of `backends/`. `pipelex update` never touches them; `pipelex init`, a full reset, rewrites the ones the kit ships, such as `openai.toml`, and leaves a backend of your own in place. Declare models of your own in a backend of your own rather than in `internal.toml`.

The deck loader merges all `*.toml` files under the deck directory in alphabetical order via deep-merge, so your `x_custom_*.toml` always wins over the numbered defaults.

## Options

| Flag | Description |
|---|---|
| `--local` / `-l` | Update the project-local `.pipelex/` files instead of the ones the layered resolution picks |
| `--yes` / `-y` | Apply updates non-interactively (skip the confirmation prompt) |
| `--dry-run` | Show the plan without modifying any file |
| `--no-backup` | Do not create `.bak` files for locally-modified managed files |

## Examples

```bash
# Preview what would change
pipelex update --dry-run

# Interactive update of the global deck and internal.toml
pipelex update

# Non-interactive update — useful for CI or scripts
pipelex update --yes

# Project-local files only
pipelex update --local --yes

# Skip the .bak backups (advanced — your edits will be lost permanently)
pipelex update --yes --no-backup
```

## Migration: existing installs without a manifest

If your deck was installed before the `update` command existed, there will be no `.kit_manifest.json` next to your deck files, and an install made before `pipelex update` managed `internal.toml` has none in its backends directory. The first `pipelex update` run reports each managed file that differs from the kit as `locally modified` (no provenance proof) and asks before overwriting. Two ways to migrate cleanly:

1. **Trust the kit** — run `pipelex update --yes` to take the upstream version of every managed file. Anything you want to keep can be moved into an `x_custom_*.toml`, or for a model into a backend of your own, afterwards using the `.bak.<timestamp>` files as a reference.
2. **Move overrides first** — copy any custom aliases, presets, or defaults from your numbered files into a new `x_custom_<area>_deck.toml`, and any model you added to `internal.toml` into a backend of your own, then run `pipelex update --yes`. Your customizations will live in files Pipelex never touches.

After either path, subsequent updates land cleanly without prompting on the unchanged files.

## Diagnostics

`pipelex doctor` includes a **Model Deck** section that reports the same per-file status as `update`, for the deck and for `backends/internal.toml`. Run `pipelex doctor --fix` to be offered an interactive `pipelex update` as part of the standard fix flow.

## Related

- [Init Commands](init.md) — first-time setup that materializes the deck, the backend files and their manifests
- [LLM Providers & Models Configuration](../../configuration/config-technical/inference-backend-config.md) — what the deck files and backend files actually configure
