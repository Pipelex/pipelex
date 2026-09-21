# Deck variants

A deck variant is a complete set of the numbered model deck files (`1_llm_deck.toml`, `2_img_gen_deck.toml`, `3_extract_deck.toml`, `4_search_deck.toml`) kept as an alternative edition of the deck that the kit ships in `pipelex/kit/configs/inference/deck/`. Nothing loads a variant: `pipelex init` does not copy it, `pipelex update` and `pipelex doctor` do not diff against it, and the deck manifest does not know it exists. It is source code that is kept correct, not configuration that is applied.

`multi_provider/` is the deck Pipelex shipped before the default moved to the models the Pipelex Gateway serves from Azure. It resolves the default aliases and presets to Anthropic, Google and OpenAI models, and it still defines the three provider-named aliases (`best-claude`, `best-gemini`, `best-mistral`) that the shipped deck no longer carries.

The files keep their header comment about being managed by `pipelex update`, because they are byte-identical copies of what was shipped. That sentence is true of an installed deck, not of this parked copy.

## What keeps a variant from rotting

`tests/unit/pipelex/kit/test_deck_variants.py` loads every variant through the same loader the runtime uses and holds it to the shipped deck two ways.

The first is the vocabulary: the variant must define exactly the same alias, preset and waterfall names, per model family, as the shipped deck. The only differences it tolerates are the names the shipped deck deliberately dropped, which the test lists explicitly, so a stale entry in that list fails too. Adding a preset to the shipped deck and not to a variant turns the test red.

The second is the handles: every model handle a variant names and the shipped deck does not must still be declared by one of the kit's backend files. This is how a parked deck actually goes stale — pipelex v0.61.0 retired the GPT-4.1, o-series and GPT-5 to 5.2 generations, and a variant naming one of those would otherwise pass the vocabulary check forever. The check is scoped to the handles only the variant names, because a handle the shipped deck names too is already exercised at boot, and some of those are gateway-served with no backend section of their own.

## Re-enabling a variant

Copy its numbered files over the ones in `pipelex/kit/configs/inference/deck/`, then mirror the kit into this repository's own `.pipelex/` with `pipelex update --local`. Nothing else is wired to a variant, so there is no switch to flip.

## Where a variant must not live

A variant directory must never sit under a directory named `deck/`, and must never sit anywhere under `pipelex/kit/configs/`.

- The deck loader collects `*.toml` recursively from the installed deck directory, so a variant nested inside `deck/` would be merged into the live deck at boot.
- Everything under `configs/` is treated as a template: `ensure_global_config_exists` copies the whole tree into a new `~/.pipelex/`, and the `check-config-sync` gate holds this repository's `.pipelex/` to the same contents, so a variant there would be installed for every user and demand a mirrored copy.
