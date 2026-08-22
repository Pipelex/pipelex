# S1 — The input-semantics audit: brief

**Status:** brief written 2026-08-21 by the workspace strategy session, for the `pipelex` session working in this worktree. This is a brief for an audit — the deliverable is a written gap list, not code. Read this, read the two workspace docs below, then conduct the audit and write its findings beside this file. The milestone is **S1** of the input-form roadmap.

**Read first, in order:**

1. `../wip/devx/input-form-projection.md` — the adopted direction. The layer this audit serves is Layer 2: *enrich the semantic layer first, before any UI vocabulary*. The diagnosis that motivates it: information that existed in the method was destroyed by projecting through Pydantic JSON Schema, and every UI downstream is guessing it back.
2. `../wip/devx/input-form-roadmap.md` — the schedule. S1 starts now, in parallel with work in other repos. Two things wait on your output, which is why this audit should be days, not weeks: **S2** (closing the engine-side gaps, here) takes your engine-side list as its worklist, and **D1** (the descriptor spec, workspace-side) freezes its slots for constraints, defaults, and examples against your list — the spec *drafts* without you, but it will not freeze until you've said what the language and engine actually know.

(Paths are relative to this worktree's root — the workspace root is one level up, same as from any sub-repo.)

## The question

For each piece of knowledge a method author writes — or would obviously want to write — about an input: **does it reach the `json_schema` emitted on `pipe_io_contracts`, and if not, where does it die?**

The chain to trace runs end to end in this repo: `.mthds` structure syntax → `ConceptStructureBlueprint` (`pipelex/core/concepts/concept_structure_blueprint.py`) → the generated structure class (`pipelex/core/concepts/structure_generation/generator.py` threads `description` and `default_value` into the emitted `Field(...)`) → Pydantic's `model_json_schema()` → `build_pipe_io_contracts` (`pipelex/pipeline/pipe_io_contracts.py`) → the wire as `PipeInputContract { concept_ref, optional, json_schema }`.

Measure, don't read: the honest way to run this audit is a probe bundle that exercises every expressible construct — every field type, choices, defaults, required and optional, `?` and `[]` markers, concept and native refinements, nesting, lists — run through validate, then a diff of what was authored against what the emitted schema says. Reading the code tells you where to look; only the emitted schema tells you what survived.

## The classification rule — the load-bearing part

Every gap you find gets one of two marks, and the two lists are the deliverable:

- **Engine-side:** the language can say it, and the emission drops or mangles it. Example candidates to verify, not conclusions: does a field's required `description` survive to the schema property? Does the *concept's* own description become the schema's top-level `description`? Does `default_value` appear as the schema's `default`? Do the `date` / `datetime` / `time` field types emit their `format`? Does `choices` arrive as `enum`?
- **Language-side:** MTHDS cannot express it at all today. The blueprint shows the ceiling: `description`, a type, `choices`, `default_value`, `required` — and nothing else. No numeric ranges, no string lengths or patterns, no examples, no units, no per-input-slot description on a pipe (the `inputs = { … }` declaration names a concept and multiplicity, nothing more). Confirm and complete that list from the parsing layer, not from this paragraph.

The distinction is what keeps the workspace honest downstream: the engine-side list is closable here with zero client changes (S2), while the language-side list feeds the MTHDS design session (Track H) so that **missing semantics get semantic homes and are never smuggled in as UI hints**. When in doubt about a fact's side, the test is: could a `.mthds` author write it today, in any syntax the parser accepts?

## What each entry should carry

For every fact, three things — evidence at `path/file.py:line` where the claim is about code:

- **Where it is authored** (or the demonstration that it cannot be).
- **Where it is lost**, if it is — the exact hop in the chain above.
- **Who guesses because of it, today.** The direction doc's evidence from `pipelex-app` is your downstream column: native concepts hardcoded as ref sets because the schema carries no concept identity beyond the top-level `concept_ref`; "is this a document" answered by object-shape sniffing on one surface and description-substring matching on another; prose-vs-label decided by nesting depth. A gap nobody downstream works around is still a gap, but the worked-around ones rank first.

Two wrinkles to place rather than force into the two-sided scheme:

- **Engine-authored semantics on native content classes.** The descriptions on `TextContent`, `DocumentContent` and friends are written in this repo, not by method authors — and at least one is load-bearing far away: the app's upload dropzone keys on the "pipelex storage url" / "document url" wording of `DocumentContent.url`'s description. Catalogue these; changing any of them is S2 work with a blast radius, and the audit should say which ones are contracts-in-disguise.
- **What a fact *means*, not just whether it travels.** `default_value` today is a structure-level default — the audit should say whether that semantic is "prefill the form with this" or something else, because the descriptor spec (D1) must not adopt a slot whose meaning it guessed. Same question for `required` versus the `?` optional marker, which live at different levels and both reach the wire by different routes.

## Out of scope

- **Fixing anything.** Even a one-line fix — an obviously droppable gap goes on the engine-side list with its evidence, and S2 closes it. The audit stays an audit so it ships fast.
- **Designing the descriptor or the hints.** D1 and H1 own those; your output is an input to both, written in facts, not proposals. Resist the pull — a sentence of recommendation per entry is fine, a design section is scope creep.
- **Wire changes of any kind.**

## The gate — S1 is done when

- The gap list is written beside this file, every entry marked engine-side or language-side, with evidence.
- The engine-side list is phrased so S2 can be scoped directly from it, and the language-side list so the MTHDS session can read it without this repo's context.
- The workspace roadmap's checkpoint protocol is honored: update `../wip/devx/input-form-roadmap.md` when the milestone closes — the D1 freeze is waiting on the news.
