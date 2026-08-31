---
status: active
item: L-260830-2c75b3
---

# Make the projection-corpus divergence gate see every engine/projection difference

The corpus generator (`pipelex/cli/dev_cli/commands/generate_projection_corpus_cmd.py`) promises that every difference between the reference projection and the engine's own renderer lands in a declared divergence class, and that an undeclared one fails the command. `_DivergenceCollector.compare` does not uphold that promise: engine-only keys are never walked at all, and the classification heuristics work by value shape alone, so a real projection regression is absorbed into an existing declared class and committed into `mthds-js` and `mthds-python` as contract bytes. A third, lesser defect in the same file: a pipe with no inputs crashes the whole capture, because the engine's renderer raises `NoInputsRequiredError` where the projection legitimately renders `{}`.

The ledger item carries the full evidence, including the fabricated-regression table showing which mutations the collector absorbs. Everything below was re-verified against the code on `dev` after the fix in pipelex#1168 merged.

## Non-goals

- Whether each compact template actually runs through `InputShaper` — that is L-260830-216378.
- The projection's own remaining unshapeable slots — L-260830-8695ba.
- Threading descriptor kind, presence and multiplicity through the entire walk. The item explicitly rejects that redesign; the fixes below stay local to the collector plus one precomputed lookup.

## Phase 0 — setup

Claim the item (`ledger claim L-260830-2c75b3`), branch `fix/Projection-divergence-gate` off `dev`.

## Phase 1 — red tests first

Extend `tests/unit/pipelex/cli/dev_cli/test_generate_projection_corpus.py` with collector-level tests in the shape of the item's mutation table, written before the fixes so each one is seen red:

- **Engine-only key.** A dict pair where the engine renders a key the projection lacks → `declared()` raises rather than the walk silently skipping.
- **File-leaf regression.** Engine `{"url": <mock>, "width": …}` against projected `{"url": "WRONG"}` → reported, not absorbed into `file-leaf-not-expanded` (nor re-absorbed into `text-named-url` by the leaf heuristics).
- **Fixed-count regressions.** At a slot declared `[2]`: projected renders the wrong number of elements → reported. At a variable `[]` slot: projected renders more than one element → reported, not misattributed to `fixed-count-honoured`. An honoured `[2]` (engine one element, projection two) → still classified `fixed-count-honoured`.
- **No-input pipe.** Generation over a throwaway bundle containing a no-input pipe succeeds: the projected fixtures are written, no engine files exist for that pipe, and the manifest still lists it.

## Phase 2 — the collector fixes

All in `generate_projection_corpus_cmd.py`.

1. **Engine-only keys.** In the dict/dict arm, walk `engine_fields` keys absent from `projected_fields` and record them under `engine-only-field` — deliberately *not* added to `DIVERGENCE_REASONS`, mirroring the existing `unknown-empty-object` pattern, so `declared()` refuses if it ever fires. Verified to fire at zero sites on the current corpus, so generation stays green today.
2. **`file-leaf-not-expanded` arm.** After recording the divergence, strict-compare the shared keys; any mismatch goes straight to `unclassified`, bypassing the leaf heuristics — plain recursion would hand a regressed URL placeholder to the `text-named-url` arm, which would absorb it. Safe today: both sides derive the same `https://mock.invalid/url` (engine via `concept_representation_generator.py`'s `https://mock.invalid/{field_name}`, projection via `MOCK_URL_PREFIX + FILE_CONTENT_KEY`).
3. **`fixed-count-honoured` gate.** Give the walk a lookup precomputed from the pipe's descriptor — normalized path → declared `item_count` — and classify `fixed-count-honoured` only when the engine renders one element and the projected length equals the declared count; any other length mismatch lands in `unclassified`. To settle at implementation: whether a nested authored list field can carry a fixed count (`pipelex/pipeline/input_form.py`, the nested `ListField` construction) — that decides whether the lookup is per-slot-name or a real path map with numeric index segments stripped.
4. **No-input pipe.** In `_capture_pipe`, when `descriptor.fields` is empty, write the projected templates and skip the engine renders and the compare. The projection is the contract and `PipeInputFormDescriptor` documents the empty form as valid; only the engine's `build_inputs_template` refuses it.

## Phase 3 — prove zero impact on the committed corpus

Regenerate over the corpus bundles (`tests/data/input_semantics/{hinted,probe,scaffold}_bundle.mthds`, in the order the corpus README records) into scratch and diff against the committed capture in `mthds-js/tests/fixtures/protocol/` and `mthds-python/tests/fixtures/protocol/`. Expected: byte-identical fixtures, same divergence classes and counts. Any moved count means the old gate was absorbing a live regression — stop and investigate rather than re-declare.

> **Checkpoint — reached.** The fixes are in, the mutation tests are green, and the corpus is proven byte-identical.

**The fixed-count lookup is an exact path map, not a per-slot-name one.** The open question resolved against nested counts: `item_count` is passed at exactly one site, `InputFormDeriver.derive_slot` (`pipelex/pipeline/input_form.py:209`), and both nested `ListField` constructions leave it at its `None` default — the reflected one at `input_form.py:492` and the structure-field `LIST` arm at `input_form.py:568`. So a nested authored list can never carry a fixed count, and the map holds one entry per fixed top-level slot at the exact path its list occupies in each shape: `(pipe_ref, "explicit", name, "content")` always, and `(pipe_ref, "compact", name)` unless `keeps_envelope` puts it under `content` there too. `register_fixed_counts` is a public method on the collector, called once per pipe from `_capture_pipe`. A nested list matches no entry, which is the safe direction: a length mismatch there is unclassified rather than absorbed.

Two smaller shapes the implementation settled. The collector lost its leading underscore — it is `DivergenceCollector` now, because the gate's guarantee is stated as unit tests against it and a tested unit is not private. And the envelope's two keys got one declaration, `ENVELOPE_CONCEPT_KEY` / `ENVELOPE_CONTENT_KEY` in `projection_reference.py`, since the path map and the projection must agree on where a wrapped slot's list sits.

**No divergence-count surprise.** Regenerating over the three corpus bundles produces bytes identical to the committed capture in both `mthds-js/tests/fixtures/protocol/` and `mthds-python/tests/fixtures/protocol/`, with the same five classes at the same counts (`optional-field-included` 163, `file-leaf-not-expanded` 6, `fixed-count-honoured` 4, `text-named-url` 4, `object-native-keeps-envelope` 1) and the engine renderings unchanged too. `engine-only-field` fires at zero sites, as the item predicted.

**Re-measuring the item's fabricated-regression table** through the fixed collector, against the real engine output: six of nine mutations are now caught (the item's baseline caught one of eight). Newly caught are the dropped required field — via the undeclared `engine-only-field`, which makes `declared()` refuse — the regressed file-leaf URL, a structured slot collapsing to a lone wrong `url` key, a `[2]` slot rendering four elements, and a variable `[]` slot rendering two.

**Three shapes remain absorbed, and all three are the redesign this item rejects.** A projection inventing a field still reads as `optional-field-included`; a garbled placeholder at a url-named text field still reads as `text-named-url`; a structure collapsing to a bare scalar still reads as `object-native-keeps-envelope`. Each is a *wrong value at a site that already carries a class*, which shape alone cannot separate from the right one — telling them apart needs each node's kind and presence carried through the whole walk. The limit is written down where a reader meets it: `DivergenceCollector`'s docstring and the "What the gate can and cannot separate" section of `docs/contribute/generate-projection-corpus.md`. Deliberately not filed as a ledger item — the parent item names that redesign as out of scope, and the two shipped projections are pinned against the committed bytes regardless.

## Phase 4 — wrap

- `make agent-check`, `make agent-test`.
- Update the module and `_DivergenceCollector` docstrings only if the guarantee's wording needs it — the point of the fix is that the stated guarantee becomes true as written.
- Touch `docs/contribute/generate-projection-corpus.md` if it describes the gate.
- Changelog under `[Unreleased]`.
- PR to `dev` with `Closes L-260830-2c75b3` in the body.
