---
description: "Refresh the installed Pipelex model deck — keep `1_llm_deck.toml` and friends in sync with the kit shipped by your installed pipelex version, while preserving your `x_custom_*.toml` overrides."
---

# Update Command

Refresh the installed model deck so it matches the kit shipped with your current `pipelex` version.

```bash
pipelex update [OPTIONS]
pipelex update --local [OPTIONS]
```

When a new `pipelex` release ships changes to the model deck — new models, new aliases, retired entries — your previously installed deck under `~/.pipelex/inference/deck/` will fall behind. `pipelex update` brings it up to date without nuking your overrides.

## When to run it

Pipelex prints a one-line yellow advisory at the top of every CLI invocation when it detects that the installed deck is older than the running package, or when no deck manifest is present yet:

```text
⚠ Pipelex model deck may be out of date — run pipelex update to refresh
```

Run `pipelex update` to clear the warning. To silence it permanently for a session or environment:

```bash
export PIPELEX_NO_DECK_NOTICE=1
```

## What it does

Pipelex tracks the deck install state in a small JSON manifest at `~/.pipelex/inference/deck/.kit_manifest.json` (or `.pipelex/inference/deck/.kit_manifest.json` for project-local installs). The manifest stores the kit version that produced the install and a SHA-256 of each managed deck file at install time.

On `update`, Pipelex compares three states — what the kit ships, what is on disk, what the manifest recorded — and produces a per-file plan:

| Status | Meaning | Action |
|---|---|---|
| `up-to-date` | Installed file matches the kit | none |
| `new` | Kit ships a new managed file not yet installed | install from kit |
| `behind` | Installed file unchanged from manifest, kit has newer content | overwrite from kit |
| `locally modified` | Installed file was edited after install — kit version differs | back up + overwrite |
| `removed upstream` | Kit no longer ships this file | back up + remove |

Locally-modified files are preserved as `<file>.bak.<UTC-timestamp>` before the kit version is written in their place. Removed files get the same backup treatment before deletion. After the run, Pipelex writes a fresh manifest stamped with the new kit version.

## Managed files vs. user overrides

Pipelex draws a sharp line between deck files it owns and deck files you own.

- **Managed (pipelex-owned)** — `1_llm_deck.toml`, `2_img_gen_deck.toml`, `3_extract_deck.toml`, `4_search_deck.toml`. These are refreshed by `pipelex update`. Local edits are preserved with a `.bak.<timestamp>` backup but will not survive future updates.
- **User overrides** — any file in the deck directory whose name starts with `x_custom_` (e.g. `x_custom_llm_deck.toml`, `x_custom_extract_deck.toml`). Pipelex never tracks, hashes, copies, or removes these. Add new ones whenever you need to override aliases, presets, or default choices for a backend.

The deck loader merges all `*.toml` files under the deck directory in alphabetical order via deep-merge, so your `x_custom_*.toml` always wins over the numbered defaults.

## Options

| Flag | Description |
|---|---|
| `--local` / `-l` | Update the project-local `.pipelex/` deck instead of the global `~/.pipelex/` |
| `--yes` / `-y` | Apply updates non-interactively (skip the confirmation prompt) |
| `--dry-run` | Show the plan without modifying any file |
| `--no-backup` | Do not create `.bak` files for locally-modified deck files |

## Examples

```bash
# Preview what would change
pipelex update --dry-run

# Interactive update of the global deck
pipelex update

# Non-interactive update — useful for CI or scripts
pipelex update --yes

# Project-local deck only
pipelex update --local --yes

# Skip the .bak backups (advanced — your edits will be lost permanently)
pipelex update --yes --no-backup
```

## Migration: existing installs without a manifest

If your deck was installed before the `update` command existed, there will be no `.kit_manifest.json` next to your deck files. The first `pipelex update` run reports each managed file as `locally modified` (no provenance proof) and asks before overwriting. Two ways to migrate cleanly:

1. **Trust the kit** — run `pipelex update --yes` to take the upstream version of every managed file. Anything you want to keep can be moved into an `x_custom_*.toml` afterwards using the `.bak.<timestamp>` files as a reference.
2. **Move overrides first** — copy any custom aliases, presets, or defaults from your numbered files into a new `x_custom_<area>_deck.toml`, then run `pipelex update --yes`. Your customizations will live in the file Pipelex never touches.

After either path, subsequent updates land cleanly without prompting on the unchanged files.

## Diagnostics

`pipelex doctor` includes a **Model Deck** section that reports the same per-file status as `update`. Run `pipelex doctor --fix` to be offered an interactive `pipelex update` as part of the standard fix flow.

## Related

- [Init Commands](init.md) — first-time setup that materializes the deck and its manifest
- [LLM Providers & Models Configuration](../../configuration/config-technical/inference-backend-config.md) — what the deck files actually configure
