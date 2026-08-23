# S2 — Enrich: closing the engine-side semantics gaps (design)

**Status:** design written 2026-08-23, opening milestone S2 of the input-form roadmap (`../wip/devx/input-form-roadmap.md` → Track S), on branch `feature/Enrich`. Inputs: the S1 findings ([`../input-semantics/findings.md`](../input-semantics/findings.md) — the worklist is its §A, ranked in §E, with the blast-radius catalogue in §D), the frozen descriptor spec (`../docs/specs/mthds-input-form-descriptor.md`), the D2 deriver (`pipelex/pipeline/input_form.py`), and H2's hint machinery, all on `dev` since PRs #1147/#1148. Per the roadmap: *"Richer schemas flow through the existing wire with zero client changes, and immediately improve agent tool-calling and docs as well as forms. Gate: the audit's engine-side list is closed; enriched schemas visible on `/validate`."*

---

## 1. Where S2 stands after D2 and H2

The S1 worklist was written before the descriptor existed. D2 has since landed the reference derivation, and the descriptor already carries most of what §A's "who guesses" columns were missing: `concept_ref` on every concept-typed node (E1's form-side ask), the `refines` chain (E2's), three-valued `presence` (E5's), `item_count` for fixed `[N]` multiplicity (E4's), authored `default_value` reported faithfully beside `required` (E3's descriptor half), and normalized one-member `choices` (E10's descriptor half, pinned by the spec). M1 will delete the app-side guessing by swapping the kernel onto that descriptor.

So S2 is **not** "make the form possible" — that is done. S2 is what the roadmap always said it was, now sharpened by the descriptor's existence: make the authored facts live on the **contract channel** — the `json_schema`, the `pipe_io_contracts` shape, the runtime validation behavior, and the authoring loop — and make silent drops loud. The consumers this serves are the ones the descriptor deliberately does not: agent tool-calling, docs, ajv-style payload validation, the SDKs' structural surface, and the author who needs to know their key was read.

## 2. The doctrine that sorts every entry

The workspace's presentation-vs-contract doctrine decides where each fix goes, and it resolves every ambiguity in the worklist:

- A fact about **what the caller submits** — multiplicity, presence, payload constraints, defaults, required-ness, descriptions of payload fields — is a contract fact. It belongs in `json_schema` and on the contract's structured fields, and machine consumers must be able to read it there without the descriptor.
- A fact about **how to render** — kinds, gating, hints, flattening — is presentation. It lives on the descriptor, and S2 does not duplicate it onto the contract channel.
- Where both channels carry the same fact (a default, a fixed count), they derive from the same crate in the same window, so they cannot disagree — the D2 precedent.

One consequence stated up front: the roadmap's "zero client changes" describes the schema enrichments, which are additive inside an existing `json_schema` value. The contract reshaping (E5, E9) is a deliberate protocol change — spec-first, breaking, coordinated at the release cascade like everything else in this program. The two kinds of change are separated into their own phases below so the free half never waits on the coordinated half.

## 3. Dispositions, entry by entry

| Entry | Disposition |
|---|---|
| E1 concept identity | Schema: top-level `title` becomes the concept ref. Nested identity: ruled closed by the descriptor. |
| E2 refinement chain | Ruled closed by the descriptor. No schema change. |
| E3 required + default | **Decision:** reject the pair at validation. Language sentence to `mthds`, engine validator, spec touch-up. |
| E4 `[N]` multiplicity | Schema: `minItems`/`maxItems` on the array wrap; multiplicity threaded through render and memo key. |
| E5 `!` on the contract | Contract: three-valued `presence` replaces the input's `optional`. Protocol change. |
| E6 missing descriptions | Schema: top-level `description` is the concept's authored description, by rule; native classes gain docstrings. |
| E7 silent extras | `extra="forbid"` on `ConceptStructureBlueprint`; language sentence to `mthds`; `mthds_schema.json` regen. |
| E8 builder writes `default` | One-line fix + round-trip test; delivers the standing inbox item. |
| E9 multiplicity on contract | Contract: `multiplicity` goes three-valued (`single`/`variable`/`fixed`) with `item_count`. Protocol change, shared with E5. |
| E10 `const` vs `enum` | Descriptor half closed by D2. Schema stays pydantic-canonical; `const` documented as part of the contract. |

### E6 — the description rule (with E1's title riding along)

The rule that closes E6 for every concept species at once: **the schema's top-level `description` is the concept's authored description, injected at the render.** The injection point is `_render_schema_representation` (`pipelex/core/concepts/concept.py:193`), which already receives the resolved class and knows `self.concept_ref`. For a generated class this is a no-op (its docstring *is* the concept description); for a class-backed concept it injects the authored fact the class cannot carry (several concepts may back onto one class, so the concept's description can never live on the class); for a native concept as a direct input it injects the pinned native blueprint's description — the same source the descriptor already reads via `make_pinned_native_blueprint`.

Separately and additively, the native content classes that lack docstrings (`TextContent`, `ImageContent`, `DocumentContent`, `PageContent`, `NumberContent`, `HtmlContent`, `YesNoContent` — S1 measured only `DateContent`/`TimeContent` carrying one) **gain docstrings**. This serves the consumers the render never touches: the live class is handed to instructor as the structured-output response model, so a docstring reaches the provider-side schema on every LLM structured generation.

E1's schema half rides the same render seam: the top-level `title`, today the mangled generated-class name that the app deliberately discards (`pipelex-app/src/lib/run-form/field-model.ts:210-215`), becomes the concept ref. Nested concept identity stays descriptor-only: renaming `$defs` keys would mean rewriting every `$ref` in the emitted schema, and after M1 no consumer derives a form from the schema — the descriptor's per-node `concept_ref` is the answer to that question. Same ruling for E2: JSON Schema has no inheritance vocabulary, the descriptor's `refines` list is the fact's home, and the schema stays untouched.

### E4 — fixed multiplicity reaches the schema

`render_stuff_spec` collapses multiplicity to `is_multiple()` before the render (`pipelex/core/pipes/stuff_spec/stuff_spec.py:58`), and the contract memo key does the same (`pipelex/pipeline/pipe_io_contracts.py:104`), which is why `Gadget[2]` renders as a bare `array`. The fix threads the real multiplicity value through: `render_concept_representation` takes the multiplicity (not a boolean), the array wrap in `_render_schema_representation` emits `minItems: N` and `maxItems: N` when the count is fixed, and the memo key becomes `(concept_ref, multiplicity)` so two different counts of the same concept no longer share one cached schema. A variable `[]` slot gets neither bound — the language cannot yet say "at least one" (S1 §B), and inventing a minimum here would contradict the gating rationale the descriptor spec records.

### E5 + E9 — the contract learns presence and multiplicity (protocol change)

These are the two entries whose fix is a wire-shape change on `pipe_io_contracts`, and they land together because they touch the same models and the same spec section. The doctrine argument for doing them despite the descriptor: presence and multiplicity are facts about *what the caller submits* — contract facts. Today the app rebuilds `[]` from `json_schema.type === "array"` in three drifted places with one documented gating bug (S1 E9), and a graph or lint surface that wants to show where `!` assertions live has no channel at all (S1 E5). Non-form consumers should not need a presentation view to learn a contract fact.

Proposed shape, mirroring the descriptor's vocabulary so the two surfaces share words (the D1 naming discipline):

- `PipeInputContract`: `presence: "plain" | "optional" | "force"` **replaces** `optional` (`pipelex/pipeline/pipe_io_contracts.py:45-53`). `optional` is exactly `presence == "optional"` — keeping both would be two spellings of one fact, the drift pattern S1 catalogued in the app.
- `PipeInputContract` and `PipeOutputContract`: `multiplicity` becomes three-valued — `single` / `variable` / `fixed` — with `item_count: int` present exactly when `fixed` (today `IOMultiplicity` deliberately reports a fixed count as `variable`, per its own docstring at `pipe_io_contracts.py:34-42`; that ruling is what E4/E9 revisits). The input contract, which today has no multiplicity field at all, gains both.
- `PipeOutputContract` keeps `optional` as-is: `!` is rejected on outputs (`pipelex/pipe_machinery/pipe_blueprint.py:335`), so the output's presence is genuinely two-valued and the existing spelling is honest.

This is spec-first work: the protocol spec pins the current shape and prose (`../docs/specs/pipelex-mthds-protocol.md:48` — the `pipe_io_contracts` row — and the "Optional IO contracts and liftable pipes" section), and the conformance side is `conformance/tests/pipelex_api/test_validate_optionals.py`, already skip-gated until the pinned runtime speaks optionals — the reshaped assertions inherit that gate and arm at the cascade like everything else. Spec and conformance move in the same change (`make check-spec-links` in `conformance/`). The TS protocol types (`mthds-js/src/protocol/models.ts`) and the second engine's contract emission (`pipelex-js`, `@pipelex/runtime`) follow at the cascade — cross-repo, filed as inbox items at S2 close, listed in §8. Changelog: breaking.

### E3 — `required = true` + `default_value` is rejected (decision to ratify)

The audit measured the pair validating green and the generator silently dropping the required-ness by parameter ordering (`pipelex/core/concepts/structure_generation/generator.py:307-313`). The descriptor spec deliberately did not enshrine the accident and delegated the emission decision to engine work (spec → "Facts over emission accidents"). The two candidate rulings:

- **Reject the pair at blueprint validation** — the recommendation. `default_value`'s measured meaning is "applied on absence at validation" (S1 §C), which makes absence legal, which contradicts `required`'s "must be present in the payload". Two contradictory instructions on one field is an authoring error, and the workspace answer to an authoring error is a loud validation failure, not a silent tiebreak.
- *Define the pair* (required advertises, default fills) — rejected here: it would split what the schema advertises from what validation does, and an author wanting "prefill but make the user confirm" is asking a presentation question, which is hint/`examples` territory, not `default_value`'s.

What the ruling touches: a model validator on `ConceptStructureBlueprint` rejecting the pair; the generator's accidental branch becomes unreachable and is replaced by an explicit invariant; the mthds format spec gains the validation-rule sentence (its rules list at `mthds/docs/spec/mthds-format.md:179-188` addresses adjacent combinations but not this one) — cross-repo, via inbox; the descriptor spec's `default_value` row retires its "may carry both `required: true` and a `default_value`" sentence (the pair can no longer reach a descriptor — the row's "reporting authored intent, not the accident" framing is what made the sentence true, and rejection upstream makes it vacuous); the probe bundle's `titled_default` field (`tests/data/input_semantics/probe_bundle.mthds:30` — the only authored instance of the pair anywhere in the fixtures or corpus, measured by sweep) moves to a `rejected/` fixture. Changelog: breaking.

### E7 + E8 — the authoring loop stops lying

**E7:** `extra="forbid"` on `ConceptStructureBlueprint` (`pipelex/core/concepts/concept_structure_blueprint.py:50`), closing the asymmetry S1 called stark — a typo on a concept fails loudly while a typo on a field dies silently. H2 raised the stakes: `hints` is now a known key, so a typo'd `hint = {...}` is silently dropped authored intent today. The strictness boundary is exactly H2's: the field table's *keys* are strict; hint *content* stays lenient (unknown hint keys warn and are preserved — that rule is untouched). Knock-ons: the mthds format spec's structure-field key table (`mthds/docs/spec/mthds-format.md:148-158`) needs the sentence its input-slot twin already has ("An unknown key in an input slot table MUST be rejected", `mthds-format.md:304`) — cross-repo, via inbox, engine leading the spec by one release exactly as H2 did; `mthds_schema.json` regenerates (`make gms` — structure-field objects flip to `additionalProperties: false`), and its propagation rides the already-filed release-time sync (`../wip/inbox/2026-08-23-workspace-hints-corpus-and-schema-sync-at-release.md` — S2 ships in the same release as H2, so the filed item covers both); fixtures and corpus get swept for hopeful extras before the flip (the S1 sweep found the hopeful keys only in the probe bundle, but the sweep must be re-run at implementation time). Changelog: breaking.

**E8:** the builder writes the TOML key `default` where the language reads `default_value` (`pipelex/builder/operations/concept_ops.py:115-116` — still live, verified on `feature/Enrich`), so a builder-authored default evaporates on re-load. One-line fix plus a write-then-validate round-trip test; E7's forbid turns any recurrence of this bug class into a hard failure instead of silent loss. This delivers the standing inbox item `../wip/inbox/2026-08-21-pipelex-builder-default-key-dropped.md` — remove it from the queue at close.

### E10 — the schema stays canonical, and says so

The descriptor half is closed: D2's deriver normalizes pydantic's one-member-`Literal`-as-`const` quirk into a one-member `choices` list, pinned by the descriptor spec. For the schema channel the ruling is **no render mutation**: `const` is valid JSON Schema, ajv reads it, and rewriting pydantic's canonical output would break the measured hop-3-to-hop-5 losslessness that S1 called worth repeating — the property that makes the whole chain auditable — and would hand the second engine's schema emitters a divergence to chase. Instead the protocol spec's `pipe_io_contracts` row gains one sentence documenting that `json_schema` is pydantic-canonical, single-choice enums included (`const`, no `enum` array), so a schema consumer reads it as contract rather than discovering it as a quirk. The app's form path stops reading the schema at M1, which retires the one consumer that mishandled it.

### The D2 deferral folds in: reflected defaults are authored facts (decision to ratify)

D2 parked a decision (`../input-semantics/deferred-descriptor-reflection-and-roundtrip.md`): a reflected class field with a pydantic default (`count: int = Field(default=0)`) lands in the descriptor as `required: true` with no `default_value`, because `native_expansion` derives required-ness from the annotation only. The recommendation is to rule **a pydantic default on a reflected class is an authored fact** — the class author wrote it, validation applies it on absence exactly like a blueprint `default_value`, and the descriptor claiming `required: true` for such a field is today's actual dishonesty. With E3's rejection ruled, the two stay consistent: `field_info.is_required()` is the single source of truth for the flag, and a defaulted field is not required — the same invariant the blueprint side now enforces loudly. Mechanically it is the one-function change the deferral note describes (`_with_reflected_constraints` in `pipelex/pipeline/input_form.py`, reading `field_info.is_required()` and `field_info.default`), plus a row in the kind-assignment table's tests. The deferral note's second item (the wire model's `datetime` round-trip alias) stays parked for D4, as ruled there.

## 4. Blast radius

- **Do not touch the wording of `DocumentContent.url`'s field description in S2.** The app's dropzone matcher still keys on the `"document url"` substring (S1 §D); its retirement is M1's, and the half-dead branch is already filed app-side. All S2 description work is *top-level* (concept descriptions, class docstrings), which is safe on both app stacks: the RJSF stack overwrites the top-level description anyway, and no matcher reads it.
- **No native field renames.** Every `⚠` row in S1 §D stands; S2 adds facts, it never reshapes payloads.
- **Schema-byte captures re-baseline.** Anything that pins emitted schema bytes — the codegen/validate parity corpora, conformance captures, characterization tests — shifts under E6/E1/E4. Phase 0 inventories exactly which captures pin schema output so the re-baselines are deliberate, not discovered in CI.
- **The second engine diverges until mirrored.** `pipelex-js`'s emitters must mirror the schema enrichments and the contract reshape to keep the E-track differential green; that is a filed follow-up (§8), and the differential is precisely the instrument that will measure the gap in the meantime — failing on purpose, the E1 pattern.
- **`H2`'s fingerprint invariant is untouched.** E7's forbid changes what *parses*, not how a valid crate normalizes; hint-free crates keep byte-identical fingerprints.

## 5. Measurement and gate mechanics

S1's instrument is S2's proof. The probe bundle and the `pipelex-dev trace-input-semantics` harness are extended where a closure needs a case they lack (class-backed and native-direct-input descriptions, the title, `minItems`/`maxItems`; `titled_default` moves to `rejected/`), and the survival table is regenerated at close — each entry's closure must be visible as a before/after row change, the same evidence standard the audit set. Beside the probe: unit tests at each seam (the blueprint validator, the generator invariant, the render injections, the contract fields, the builder round trip).

The gate splits exactly as D2's did, and the roadmap closure bullet must say so: **in-engine close** is the probe-measured survival table plus green tests on `feature/Enrich`; **"enriched schemas visible on `/validate`"** on the hosted wire arrives with the release cascade (D3's sequence), where the gated conformance modules arm. In-process `/validate` (the CLI and agent-CLI surfaces) shows the enrichment immediately on merge, since all three presentations share the one validation engine.

## 6. Decisions to ratify before implementation

1. **E3:** reject `required = true` + `default_value` at validation (recommended), versus defining the pair. Carries a one-sentence mthds spec addition and a breaking changelog note.
2. **E5/E9:** reshape the contract — `presence` *replaces* the input's `optional`, `multiplicity` goes three-valued with `item_count` (recommended), versus additive-only (keeping `optional` beside `presence`). The recommendation follows the no-backward-compat principle and the single-source rule; the cost is coordinated updates to the protocol spec, conformance, `mthds-js` types, and the second engine, all of which ride the cascade anyway.
3. **Reflected defaults:** a pydantic default on a reflected class counts as an authored fact (recommended), closing the D2 deferral's first item inside S2.

## 7. Execution phases

Tracker convention: at kickoff, seed `TODOS.md` at the worktree root from this section (the D2/E1 pattern); this document stays the design and does not track live state. Each checkpoint updates the tracker with decisions taken, deviations reconciled into later phases, and enough state for a cold-start session to continue.

- **Phase 0 — ratify and sweep.** Decisions §6 confirmed by Louis. Sweeps, re-run at head: hopeful extras and the `required`+`default_value` pair across fixtures, corpus entries, and cookbook-adjacent test data; inventory of captures that pin schema bytes. Output: the fixture-fallout list for Phases 1–2.
- **Phase 1 — loudness (E7, E8).** The forbid, the builder key, the round-trip test, `make gms`, fixture fallout, delivery of the E8 inbox item. **Checkpoint 1** — natural handoff: the authoring loop is honest, nothing wire-visible has changed yet.
- **Phase 2 — schema enrichment (E6, E1-title, E4).** The render-seam injections, native docstrings, multiplicity threading, memo-key change, probe extensions. **Checkpoint 2** — the "zero client changes" half is complete and measurable.
- **Phase 3 — contract reshaping (E5, E9).** Spec-first: the protocol spec's contract row and presence section, the conformance assertions (gated), then the engine models and emission, `make check-spec-links`. **Checkpoint 3** — the protocol change is contained in one reviewable unit.
- **Phase 4 — semantics and close (E3, reflected defaults).** The blueprint validator, the generator invariant, `_with_reflected_constraints`, descriptor-spec touch-ups, survival-table regeneration, findings addendum (a short §F recording each entry's closure evidence), roadmap closure bullet, changelog, and the cross-repo filings of §8.

## 8. Cross-repo follow-ups to file at close

Each of these crosses a boundary this session must not quietly widen into; they are filed as `../wip/inbox/` items in Phase 4, with this design as their evidence base:

- **`mthds`** — two spec sentences: unknown structure-field keys MUST be rejected (the slot-table rule's twin), and a field MUST NOT declare both `required = true` and `default_value`. Engine leads by one release, the H2 precedent.
- **`pipelex-js`** — mirror the schema enrichments and the contract reshape in the second engine's emitters; the parity differential measures the gap until then.
- **`mthds-js`** — the protocol types in `src/protocol/models.ts` follow the contract reshape at the cascade (D4 regenerates SDK types against the same release).
- No new item for schema/corpus sync: the filed release-time item (`2026-08-23-workspace-hints-corpus-and-schema-sync-at-release.md`) covers the release that ships H2 and S2 both.

## 9. Out of scope

- **The language ceiling (S1 §B)** — constraints, examples, units, per-slot descriptions, choice labels, non-string choices, refine-and-extend: all language design, Track H's territory via an mthds design session. S2 makes their absence *loud* (E7) but adds no syntax. The descriptor's `examples` and constraint slots stay shaped-to-receive.
- **App-side fixes** — the drifted taxonomy copies, the dropzone matcher, the flatten-then-repair round trip: M1 deletes them by swapping the kernel onto the descriptor.
- **Corpus widening** — the input-side coverage wish-list (`../wip/inbox/2026-08-22-pipelex-corpus-input-side-concept-coverage.md`) is adjacent and stays its own pass; S2's probe bundle is the measurement fixture, not a corpus substitute.
- **E10 beyond documentation** — no `const`-to-`enum` render rewrite, per the §3 ruling.
- **The descriptor wire model's round-trip alias** — D4's, per the deferral note.
