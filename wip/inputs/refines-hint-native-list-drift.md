# Deferred: `refines` authoring-hint native-concept list drifts from `NativeConceptCode`

**Status:** deferred follow-up — no code change in the YesNo track. Surfaced during the final gstack `/review` of PR #1028 (native `YesNo`), 2026-07-07.

## What

`pipelex/builder/concept/concept_spec.py` — the `ConceptSpec.refines` field hardcodes a list of native concepts in two places:

- the field `description` (~line 250): `"(Text, Html, Image, Document, Number, Page, TextAndImages, JSON, Anything, Dynamic)"`
- the field `examples` (~line 253): `["Text", "Html", "Image", "Document", "Number", "Page", "TextAndImages", "JSON"]`

Both lists are **already non-exhaustive** against `NativeConceptCode`: they omit `SearchResult` and `Composite` today, and now also omit the new `YesNo`.

## Why it does not block the YesNo PR

This is the builder **spec** layer — a convenience authoring format surfaced to LLM agents, explicitly *not* the MTHDS language (see `pipelex/builder/CLAUDE.md`). The list is an LLM-facing authoring hint only. Runtime is unaffected: `refines = "YesNo"` validates and resolves `YesNoContent` (proven by `tests/unit/pipelex/core/concepts/concept_factory/test_yes_no_refinement.py`). Because pyright can't see string literals, the exhaustive-`match/case` discipline that guarantees every other new-native-code site was updated does not reach this hardcoded string.

## Why defer rather than spot-patch

Appending just `"YesNo"` would be a partial fix that leaves `SearchResult` and `Composite` still missing — it papers over a systemic drift rather than resolving it, and picking which subset to add is a judgment call, not a clear-cut fix. This is the same class of authoring-guidance surface (skills, editor completion lists) the YesNo plan already defers to the shared release-wave sweep.

## The real fix (release-wave / Smart Inputs authoring-guidance sweep)

Either complete the list (`YesNo`, `SearchResult`, `Composite`) **or** — better — derive it from `NativeConceptCode` at model-definition time so it can never drift again. Do this once, in the release-wave sweep, alongside the other authoring-guidance surfaces (`mthds-plugins` skills, `vscode-pipelex` completion lists), not as a per-native-concept patch.
