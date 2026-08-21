# S1 — The input-semantics audit: plan

**Status:** plan written 2026-08-21, companion to [`audit.md`](audit.md) (the brief — read it first; this document schedules the audit, it does not re-argue it). Progress is tracked here with checkboxes. The deliverable is `findings.md`, written beside this file when Phase 4 completes. Per the brief: audit only — no fixes, no descriptor design, no wire changes.

## The method, in one sentence

Author a probe bundle that exercises every construct the language accepts, capture what each hop of the emission chain does to every authored fact, and let the diff — not the code — say what survives to the wire.

## The harness is a keeper, not a scratch script

Decision (Louis, 2026-08-21): the capture harness is built as a durable internal tool, not throwaway scaffolding. It lands as a `pipelex-dev` command (home: `pipelex/cli/dev_cli/commands/`, like `generate-mthds-schema` and friends) — call it `trace-input-semantics`: given a bundle, it dumps one artifact per hop of the chain below into an output directory. The probe bundle rides along as a committed fixture the audit (and any future re-run) points the tool at. Scope discipline: build exactly what this audit needs — per-hop captures for a given bundle — and nothing more generic; if another project needs more, it evolves the tool then. When the audit closes, the tool stays, with a short entry in the repo docs so it is findable. The survival *table* stays audit-side (built from the captures), so the tool stays a tracer, not a report generator.

## The chain under audit

Five hops, end to end in this repo. Every probe capture happens at each hop so a lost fact is localized to exactly one:

1. **Parse:** `.mthds` structure syntax → `ConceptStructureBlueprint` (`pipelex/core/concepts/concept_structure_blueprint.py`; the parser that builds it lives in `pipelex/mthds_parsing/` — exact site pinned in Phase 0).
2. **Resolve + generate:** blueprint → generated structure class source (`pipelex/core/concepts/resolved_fields.py` → `pipelex/core/concepts/structure_generation/generator.py`, which threads `description` and `default_value` into the emitted `Field(...)` and renders `choices` as a `Literal`).
3. **Schema:** generated class → `model_json_schema()` via the SCHEMA representation (`pipelex/core/concepts/concept_representation_generator.py`, `ConceptRepresentationFormat.SCHEMA`) — including whatever wrapping or stripping that render path applies after pydantic.
4. **Contract:** schema → `PipeInputContract { concept_ref, optional, json_schema }` in `build_pipe_io_contracts` (`pipelex/pipeline/pipe_io_contracts.py`) — note the memo key is `(concept_ref, is_multiple())`, so multiplicity changes the rendered schema.
5. **Wire framing:** what the pipe's `inputs = { … }` declaration itself contributes — concept ref, `?` optional, `[]` multiplicity — and nothing else.

## Facts to verify by measurement, not settle by reading

Candidates gathered from the brief and a first pass over the chain code. Each is a question the survival table must answer; none is a conclusion yet:

- Does a field's `description` survive to the schema property's `description`?
- Does the *concept's* own description become the schema's top-level `description` (it is emitted as the generated class docstring — does pydantic carry a docstring into the schema, and does the SCHEMA render keep it)?
- Does `default_value` appear as the schema's `default` — for every type it can be authored on (text, integer, boolean, number, date, datetime, time, list, dict, choice)?
- Do `date` / `datetime` / `time` fields emit their JSON-Schema `format`?
- Does `choices` arrive as `enum` — and what does a single-entry choice list become (pydantic renders one-member `Literal` as `const`)?
- What does a non-`required` field look like on the wire — `anyOf: [X, null]` plus `default: null`? This is the shape behind the app's flatten-then-repair round trip; the audit should state it precisely.
- What survives of a **concept-typed field** (`type = "concept"`): does the nested structure inline via `$defs`, what are the `$defs` keys, and is the nested concept's *identity* (its concept ref) recoverable from the schema or only its shape?
- What survives of **`refines`**: does the refinement chain (e.g. a refinement of `native.Document`) leave any trace in the emitted schema beyond inherited fields?
- What do **native concepts as direct inputs** render as — `Text`, `Image`, `Document`, `PDF`, `Page`, and friends — and is anything in those schemas concept-identifying beyond the top-level `concept_ref`?
- How does `[]` multiplicity change the emitted `json_schema` (array wrapping? at which hop?), given the memo keys on `is_multiple()`?
- Do the dict constraints (`key_type` restricted to text, `value_type`) render faithfully (`additionalProperties`)?
- Does anything in the SCHEMA render path strip or rewrite what pydantic emitted (title, `$defs`, metadata fields)?

## Phase 0 — Rig the audit

- [x] Read the direction doc and the roadmap (`../wip/devx/input-form-projection.md`, `../wip/devx/input-form-roadmap.md`) and the chain files named above.
- [ ] Pin the parse hop: find the exact code where TOML structure syntax becomes `ConceptStructureBlueprint` (both the explicit table syntax and any inline/shorthand forms), and record what the parser accepts — this, not the brief's paragraph, is the authority for the language ceiling.
- [ ] Pin the schema hop: trace `render_stuff_spec` → `ConceptRepresentationFormat.SCHEMA` and note every transform applied after `model_json_schema()`.
- [ ] Build the capture harness as the `pipelex-dev trace-input-semantics` command (see "The harness is a keeper" above): it loads a bundle through the validation library and, inside the validation window, dumps one JSON artifact per hop — blueprint dump, generated class source, raw `model_json_schema()`, the SCHEMA render, and the final `PipeInputContract` — into a given output directory. Give it the tests a kept tool deserves (a unit test per hop capture on a small fixture), per the repo's testing discipline.
- [ ] Enumerate the probe matrix **from the parsing layer**: every field type, `choices` (multi and single), `default_value` on each type that allows one, `required` both ways, concept refs (native and custom, bare and qualified), `refines` (of a native, of a custom concept, and a chain of two), lists of scalars and of concepts, dicts, nesting at least two levels deep, concept descriptions, `?` and `[]` on pipe inputs, and native concepts as direct inputs.

## Phase 1 — The probe bundle

- [ ] Author the probe `.mthds` bundle(s) covering the full matrix, committed as a fixture beside the tool's tests (exact spot decided when the tool lands — somewhere under `tests/data/`, per repo convention). Every authored fact carries a distinctive sentinel string (e.g. `PROBE_desc_field_price`) so its survival — or its absence — is greppable in every capture.
- [ ] Confirm the bundle validates cleanly; where a construct is *rejected*, keep it in a separate deliberately-failing file and record the rejection as evidence of the language ceiling.

## Phase 2 — Measure

- [ ] Run `pipelex-dev trace-input-semantics` on the probe bundle; store the per-hop captures under `wip/input-semantics/probe/` (the captures are audit evidence, not part of the tool).
- [ ] Build the survival table: one row per authored fact, one column per hop, each cell `survived` / `transformed (how)` / `dropped`. This table is the evidence backbone of every findings entry.

**Checkpoint CP1 — measurements in hand.** Natural handoff point: the probe bundle, harness, and survival table exist; classification has not started. If the session breaks here, update this plan with any surprises the measurement produced (constructs that failed to author, hops that behaved unexpectedly) so the next session classifies without re-running anything.

## Phase 3 — Classify and place the wrinkles

- [ ] Mark every gap **engine-side** or **language-side** using the brief's test: could a `.mthds` author write it today, in any syntax the parser accepts? Evidence as `path/file.py:line` for every engine-side claim.
- [ ] Confirm and complete the language-side ceiling from the Phase 0 parser findings — the brief's candidate list (no numeric ranges, no string lengths or patterns, no examples, no units, no per-input-slot description on a pipe) verified against what the parser actually accepts, plus anything the brief missed (e.g. non-string choice values, labeled choices).
- [ ] Catalogue the engine-authored descriptions on the native content classes (`TextContent`, `DocumentContent`, `ImageContent`, and friends): which are contracts-in-disguise. Verify the known one — the app's upload dropzone keying on the "pipelex storage url" / "document url" wording of `DocumentContent.url` — read-only in `pipelex-app`, and sweep for others of the same kind.
- [ ] Settle the two meaning questions with evidence, not guesses: what `default_value` *means* today (find where the generated default is actually consumed at runtime — is it applied on absence during execution, is it "prefill the form", or both?), and how `required` (structure-field level) relates to `?` (pipe-input level) — two levels, two wire routes, both documented precisely.
- [ ] Fill the downstream column: pin each of the direction doc's `pipelex-app` workarounds (hardcoded native ref sets, object-shape sniffing, description-substring matching, prose-vs-label by nesting depth) to the specific gap it compensates for. Worked-around gaps rank first.

## Phase 4 — Write the findings and close the milestone

- [ ] Write `findings.md` beside this file: the two lists, every entry carrying *where authored*, *where lost* (the exact hop), and *who guesses today* — at most one sentence of recommendation per entry, no design sections.
- [ ] Phrase the engine-side list so S2 can be scoped directly from it (each entry a closable work item), and the language-side list so the MTHDS design session (Track H) can read it without this repo's context.
- [ ] Place the native-description catalogue and the two meaning answers in `findings.md` as their own sections — they are inputs to S2's blast-radius planning and to D1's slot semantics respectively.

**Checkpoint CP2 — milestone gate.** When `findings.md` is written:

- [ ] Keep the tool: document `pipelex-dev trace-input-semantics` in the repo docs (a short page or a section in the dev-CLI docs, same register as `generate-mthds-schema`), and note it in the changelog's Unreleased section.
- [ ] Update this plan's checkboxes and record decisions taken and surprises found.
- [ ] Update `../wip/devx/input-form-roadmap.md` per its checkpoint protocol — S1 closed, the D1 freeze is waiting on the news, and S2 takes the engine-side list as its worklist.
