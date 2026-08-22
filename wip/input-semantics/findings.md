# S1 — Input-semantics audit: findings

**Status:** written 2026-08-21, closing milestone S1 of the input-form roadmap. Evidence base: the measured survival table ([`survival-table.md`](survival-table.md), captures under [`probe/`](probe/), regenerable with `.venv/bin/pipelex-dev trace-input-semantics tests/data/input_semantics/probe_bundle.mthds -o wip/input-semantics/probe`), a read-only sweep of `pipelex-app`'s two input-form stacks, and a trace of where `default_value` is actually consumed at runtime. Per the brief: facts only — at most one sentence of recommendation per entry, no design.

The hop numbering used throughout: **hop 1** parse (TOML → blueprint), **hop 2** generate (blueprint → structure-class source), **hop 3** pydantic (`model_json_schema()`), **hop 4** render (SCHEMA representation), **hop 5** contract (`PipeInputContract`). Measured once and worth repeating: **hop 3 → hop 5 is lossless** (byte-identical for a single input; the render only adds the envelope and the array wrap), so every loss below sits in the language, the parse, or the generator — never in the render or contract plumbing.

---

## A. Engine-side gaps — the S2 worklist

The language can say it; the emission drops or mangles it. Each entry is phrased as a closable work item.

### E1. Concept identity of a field is not recoverable from the schema

- **Authored:** `type = "concept"`, `concept_ref = "domain.Gadget"` (or `item_concept_ref` on lists) on a structure field — `pipelex/core/concepts/concept_structure_blueprint.py:59-60`.
- **Lost:** hop 2/3 — the generator emits a forward ref to the mangled class name, so the schema inlines the shape under `$defs` keyed by the class-name spelling (`input_semantics_probe__Gadget`); native fields appear as bare content-class names (`ImageContent`). Nothing in the schema states the concept ref.
- **Who guesses:** the app's primary field dispatch is seven hardcoded native-ref sets (`pipelex-app/src/lib/run-form/field-model.ts:133-139`), with a second *drifted* copy (`src/lib/input-format.ts:27-30` — missing `native.Date`/`native.HTML`, so the two stacks disagree on text wrapping) and a third for the wire wrapper (`src/lib/run-form/run-values.ts:35-48`). The app also deliberately discards `schema.title` because it is "the pydantic model name … and would mask the stuff name" (`field-model.ts:210-215`).
- **Recommendation:** carry the concept ref for every concept-typed node (top-level and nested) on the descriptor or schema.

### E2. The refinement chain leaves no trace

- **Authored:** `refines = "native.Document"` (or a custom chain) — `pipelex/core/concepts/concept_blueprint.py:20`.
- **Lost:** between hop 2 and hop 3 — the generated class *inherits* from the refined class, so only inherited field shapes survive; the link itself is gone. Measured on `RefinedDoc` and the `BaseEntity ← SpecialEntity ← ExtraSpecialEntity` chain.
- **Who guesses:** "does this refine Document" is answered by object-shape sniffing on one surface — `isDocumentObject` is `Boolean(schema.properties?.url)` "and nothing more" (`pipelex-app/src/lib/run-form/field-model.ts:186-197`) — and by description-substring matching on the other (`src/components/method/document-url-widget.tsx:130-136`, matching lowercased `"pipelex storage url"` / `"document url"`). A value-side twin hardcodes `DocumentContent`'s field names as a sniff set (`src/lib/input-format.ts:176-182`).
- **Measured drift, worth flagging in S2's blast radius:** the current `DocumentContent.url` description is "The document URL: a storage URI, an HTTP(S) URL, or a base64 data URL" (`pipelex/core/stuffs/document_content.py:16`) — the `"pipelex storage url"` branch of the app's matcher **already matches nothing** (the app's own test fixture pins the older wording); only `"document url"` still fires. `ImageContent.url` ("The image URL: …", `image_content.py:20`) matches neither substring, so image URL fields never get the RJSF dropzone by this route.
- **Recommendation:** expose the refinement chain (at least "refines `native.X`") as a fact on the wire. The half-dead matcher is filed app-side as `../wip/inbox/2026-08-21-pipelex-app-document-dropzone-matcher-half-dead.md`.

### E3. `required = true` plus `default_value` silently drops the required-ness

- **Authored:** both keys on one field — legal, validated green (probe field `titled_default`).
- **Lost:** hop 2 — the generator's parameter ordering emits `default=…` and never the `...` sentinel when a default is present (`pipelex/core/concepts/structure_generation/generator.py:307-313`), so the field leaves pydantic's `required` list.
- **Who guesses:** nobody compensates; the authored intent is just gone. (At runtime the two are genuinely conflicting instructions — see the meaning note in §C — but today the conflict is resolved silently instead of being rejected or honored.)
- **Recommendation:** decide the combination's meaning (likely: reject it at validation) rather than resolving it by accident of parameter ordering.

### E4. `[N]` fixed multiplicity dies at the render

- **Authored:** `inputs = { gadgets = "Gadget[2]" }` — parsed to `multiplicity: 2` (`pipelex/core/pipes/variable_multiplicity.py:169-171`).
- **Lost:** hop 4 — `StuffSpec.is_multiple()` collapses multiplicity to a bool before rendering (`pipelex/core/pipes/stuff_spec/stuff_spec.py:58`), so the schema is a plain `array` with no `minItems`/`maxItems`; the contract memo key `(concept_ref, is_multiple())` (`pipelex/pipeline/pipe_io_contracts.py:104`) makes the count structurally unreachable there.
- **Who guesses:** nobody — a form cannot enforce "exactly 2" because the wire never says it.
- **Recommendation:** thread the real multiplicity through the render and memo key, emitting `minItems`/`maxItems`.

### E5. `!` (force) is indistinguishable from plain on the contract

- **Authored:** `inputs = { doc = "Document!" }` — parsed to `presence: force` (`variable_multiplicity.py:26`).
- **Lost:** hop 5 — `optional=stuff_spec.presence.is_optional` maps force and plain both to `optional: false` (`pipe_io_contracts.py:123`).
- **Who guesses:** nobody today — for a top-level run form the two are equivalent (the caller must supply the value either way), but the contract cannot express the distinction for any consumer that would care (e.g. a lint or graph surface showing where assertions live).
- **Recommendation:** a presence enum (or a `force` flag) on the contract if any consumer materializes; low urgency.

### E6. Class-backed concepts lose their description; most native inputs never had one

- **Authored:** the concept's `description` beside `structure = "TextContent"` (probe concept `ClassBacked`).
- **Lost:** hop 2 — a pre-existing class receives no docstring from the concept, so the schema has no top-level `description` at all. Related, measured on native concepts as direct inputs: only `DateContent` and `TimeContent` carry class docstrings; `Text`, `Image`, `Document`, `Page`, `Number`, `Html`, `YesNo` render schemas with **no top-level description**.
- **Who guesses:** the RJSF stack *overwrites* the top-level description with the concept ref as a label stand-in (`pipelex-app/src/lib/run-form/run-gate.ts:44-48`), which is also why its dropzone matcher can only ever match nested property descriptions.
- **Recommendation:** inject the concept description into class-backed and native renders (top-level `description`), same as generated classes already get.

### E7. Unknown keys on a structure field vanish silently at parse

- **Authored:** anything hopeful — `minimum = 0`, `maximum = 10`, `examples = […]`, `unit = "kg"` all author fine and validate green.
- **Lost:** hop 1 — `ConceptStructureBlueprint` has no `extra="forbid"` (`concept_structure_blueprint.py:50`), so extras are dropped before the blueprint dump; measured absent. The asymmetry is stark: `ConceptBlueprint` itself *does* forbid extras (`concept_blueprint.py:13`), so a typo on a concept fails loudly while a typo (or a hopeful constraint) on a field dies silently.
- **Who guesses:** the author, who believes they expressed something. Only the (stale) MTHDS lint-hook schema even warns.
- **Recommendation:** `extra="forbid"` on `ConceptStructureBlueprint` — this also makes the language ceiling (§B) enforceable instead of silent.

### E8. The builder writes `default` instead of `default_value` — the default is silently dropped on re-load

- **Authored:** via the builder / agent-CLI `concept` command — `structure_field_to_dict` emits the TOML key `default` (`pipelex/builder/operations/concept_ops.py:115-116`).
- **Lost:** hop 1 on the round trip — `ConceptStructureBlueprint` has no alias for `default`, and extras are ignored (E7), so a builder-emitted default validates green and reaches nothing (verified by direct `model_validate`). Docs and fixtures agree the authored spelling is `default_value`; only this writer disagrees.
- **Who guesses:** any agent or user authoring through the builder — their default evaporates without a signal.
- **Recommendation:** one-line fix in `concept_ops.py` (write `default_value`); E7's `extra="forbid"` would have caught this as a hard failure. Filed as `../wip/inbox/2026-08-21-pipelex-builder-default-key-dropped.md` so it need not wait for the whole S2 milestone.

### E9. Multiplicity survives only as schema shape, never as a contract field

- **Authored:** the `[]` suffix on the input ref.
- **Lost:** not lost exactly — transformed at hop 4 into `{type: "array", items: …}` — but the contract's `concept_ref` comes back *without* the suffix and no structured multiplicity field exists, so array-ness is only recoverable by inspecting the schema.
- **Who guesses:** the app rebuilds `[]` from `json_schema.type === "array"` in three independent places (`pipelex-app/src/lib/input-format.ts:270-284`, `src/lib/pipe-io-contracts.ts:42-44`, `src/lib/run-form/field-model.ts:142-146`), and the divergence between two of those rules produced a real gating bug the app documents at `field-model.ts:398-409`.
- **Recommendation:** a structured multiplicity field on the contract (which E4's fix would need anyway).

### E10. Single-entry `choices` emit `const`, not `enum` — and the main consumer doesn't read `const`

- **Authored:** `choices = ["only_option"]`.
- **Transformed:** hop 3 — pydantic renders a one-member `Literal` as `const: "x"` with no `enum` array. Not a loss, but a wire-shape hazard.
- **Who guesses:** the app branches on `Array.isArray(schema.enum)` only (`field-model.ts:235-238`); `const` is unhandled anywhere in its `src/`, so a single-choice field renders as free text the user can fill wrongly.
- **Recommendation:** either normalize `const` to a one-member `enum` at the render, or document `const` as part of the contract consumers must read.

---

## B. Language-side ceiling — input to the MTHDS design session (Track H)

MTHDS cannot express these today, in any syntax the parser accepts. The complete authoring surface, for context: a concept carries `description`, `structure` XOR `refines`, and optional `source` (`ConceptBlueprint`, extras forbidden); a structure field carries `description`, `type`, `key_type`/`value_type`, `item_type`, `concept_ref`/`item_concept_ref`, `choices` (strings only), `default_value`, `required` (`ConceptStructureBlueprint` — extras silently ignored, see E7); a pipe's `inputs` values are ref strings whose entire grammar is `concept ref + [] / [N] + ? / !` (`pipelex/pipe_machinery/pipe_blueprint.py:186`; `variable_multiplicity.py:16`). Everything below falls outside that surface:

- **Numeric ranges** (`minimum` / `maximum` / exclusive bounds) — no syntax; note the engine grants *itself* this power (`ImageContent.width` is `gt=0`, `pipelex/core/stuffs/image_content.py:27`), so the schema vocabulary is proven, only the language lacks it. This is the direction doc's slider example.
- **String constraints** — no length bounds, no pattern.
- **Examples** — none, at field, concept, or input-slot level. (The inputs template synthesizes placeholders from the *type* instead — `concept_representation_generator.py:143`.)
- **Units** — no way to say a number is kilograms or euros.
- **Per-input-slot description on a pipe** — `inputs` values are ref strings only; the table form is rejected (fixture `rejected/per_input_description.mthds_invalid`). A pipe cannot say what *this use* of a concept means.
- **Per-slot defaults or examples** — same ceiling as above.
- **Non-string choices** — `choices: list[str]`; `[1, 2, 3]` is rejected.
- **Choice labels** — a choice is a bare string; no display label or per-choice description.
- **Inner type of nested lists** — `item_type = "list"` has no syntax for the inner item type; emitted as `list[list[Any]]`, so the wire schema's inner `items` is empty.
- **Multiple refinement** — `refines` is a single ref (`concept_blueprint.py:20`, TODO recorded at line 19).
- **Refine-and-extend** — `refines` and `structure` are mutually exclusive (`concept_blueprint.py:95`): a refinement of `native.Document` cannot add fields. Any "Invoice is a Document plus an amount" concept is inexpressible.
- **Defaults on concept-typed fields** — rejected by design (`concept_structure_blueprint.py:111`); listed for completeness, arguably a correct ceiling.
- **Rendering intent** (prose vs label, rating, quantity…) — nothing expressible; today the app decides prose-vs-label by nesting depth with a `maxLength > 120` magic number (`field-model.ts:283-289`). This is Layer 3 territory (intent vocabulary), listed here because the *absence* is a language fact.

One asymmetry worth the design session's attention: because of E7, most of this ceiling fails *silently* — an author who writes `minimum = 0` today is told nothing.

---

## C. The two meaning questions, settled by evidence

### What `default_value` means today

It is an **execution-level default applied on absence**, not a form-prefill hint:

- The one runtime ingestion seam for pipe inputs ends at `StuffContentFactory.make_content_from_value` → `stuff_content_subclass.model_validate(obj=value)` (`pipelex/core/stuffs/stuff_content_factory.py:35`), a plain validate — an omitted field with a default gets the default on the instantiated object.
- The same applies to **LLM structured output**: workers hand the live generated class to instructor as the response model (e.g. `pipelex/providers/google/google_llm_worker.py:268`), so a field the LLM omits is filled by the default too.
- The **inputs template deliberately omits defaulted fields** rather than prefilling them: the JSON representation is generated with `include_optional=False` (`pipelex/core/concepts/concept.py:183-184`) and the generator skips every non-required field (`concept_representation_generator.py:136-138`) — and a defaulted field is non-required (E3). The template never reads `field_info.default`.
- The default **is exposed on the wire** (`"default": X` in the hop-3 schema, surviving verbatim to hop 5), so a form *may* render it as a prefill — but that is a consumer's choice layered on the real semantic.
- Under **dry-run mocks** the default is ignored: polyfactory builds with `__use_defaults__` unset (default `False`), so every field gets a random value (`pipelex/core/memory/working_memory_factory.py:219-225`).

Consequence for D1: the slot's honest name is "value used when the caller omits the field" — prefill is a safe *rendering* of that, but the two are not the same slot. And authoring a default currently *implies* optionality on the wire (E3), which D1 should treat as an engine accident, not a semantic.

### `required` versus `?` — two levels, two routes

They govern different things and travel independently:

- **`required` (structure-field level):** whether a field must be present *within the concept's payload*. Travels inside the `json_schema` as membership in pydantic's `required` array; a non-required field becomes `X | null` with `default: null` (the shape behind the app's flatten-then-repair round trip — `prepareSchemaForRjsf` collapsing the null arm, then `pruneEmptyOptionals` un-blocking untouched optional fields, `pipelex-app/src/lib/input-format.ts:388-421`).
- **`?` (pipe-slot level):** whether the whole input slot may hold no value. Travels as the `optional: true` flag on the contract (`pipe_io_contracts.py:123`); the `json_schema` itself is unchanged. This is the gating rule — the app stamps its Run gate from the contract flag (`field-model.ts:345-351`).
- **`!` (pipe-slot level):** a *use-site assertion* that a maybe-absent slot is present at run time — meaningless on outputs (rejected, `pipe_blueprint.py:335`), linted as redundant when every flow guarantees the slot (`pipelex/pipeline/optionality_warnings.py`). On the contract it is flattened into plain (E5).

The two levels never interact in the emission: `?` on a slot does not touch the payload schema, and a field's `required` never bubbles up to the slot.

---

## D. Engine-authored semantics on native content classes — the catalogue

Descriptions and field names written in this repo, not by method authors. The ones marked ⚠ are **contracts-in-disguise**: a downstream surface keys on them today, so changing them is S2 work with a blast radius.

| Class / field | Engine-authored text or shape | Downstream coupling |
|---|---|---|
| `DocumentContent.url` (`document_content.py:16`) | "The document URL: a storage URI, an HTTP(S) URL, or a base64 data URL" | ⚠ Matched by substring (lowercased `"document url"`) to assign the upload dropzone (`pipelex-app/src/components/method/document-url-widget.tsx:130-136`). The matcher's other branch, `"pipelex storage url"`, **already matches nothing** — the wording drifted and half the contract is dead. Renaming away "document url" silently removes every dropzone in the MethodViewer panel. |
| `DocumentContent` field names (`url`, `public_url`, `mime_type`, `filename`, `title`, `snippet`) | the model's shape | ⚠ Hardcoded as a value-sniff set (`pipelex-app/src/lib/input-format.ts:176-182`) and `properties.url` alone makes any concept a document with a dropzone (`field-model.ts:186-197`, also `:362-365` for run-gating readiness). Renaming `url` breaks document detection, upload, and gating in both stacks. |
| `TextContent.text` (`text_content.py:17`) | "The text" + the single-field `{text}` shape | ⚠ The `{text: "…"}` wrapper shape is assumed by the app's wrapping sets (`run-values.ts:35-48`, applied at `:129`), the deflate/inflate rules (`input-format.ts:78-136`), and `healStringWrappers` (`input-format.ts:312-369`). Renaming `text` breaks text round-tripping everywhere. |
| `ImageContent.url` (`image_content.py:20`) | "The image URL: a storage URI, an HTTP(S) URL, or a base64 data URL" | Matches neither dropzone substring (measured) — image upload in the runner stack works only via the hardcoded concept sets (E1); shape-wise, `properties.url` makes images sniff as documents. |
| `ImageContent.width` / `.height` (`image_content.py:27-28`) | `gt=0` constraints + descriptions | Proof the engine can emit numeric bounds the language cannot author (§B). |
| `DateContent` / `TimeContent` docstrings (`date_content.py:17`, `time_content.py:16`) | the only two native classes whose schemas carry a top-level description | `DateContent.time` (optional, `format: time`) is the app's canonical flatten-then-repair casualty, cited in `pruneEmptyOptionals`' docstring (`input-format.ts:371-386`). |
| `PageContent.text_and_images` / `.page_view` (`page_content.py:14-15`) | extraction-oriented descriptions | No known coupling; `native.Page` is folded into the app's document branch by concept set, not by these. |
| `NumberContent.number`, `HtmlContent.inner_html`/`.css_class`, `YesNoContent.yes_no`, `TextAndImagesContent.*` | plain descriptive prose | No known coupling beyond the generic wrapper handling. |

Sweep method note: couplings were found by searching `pipelex-app` for description substrings, field-name sniff sets, and wrapper-shape assumptions; `base_64` / `source_prompt` sniffing was explicitly checked for and does not exist — those shapes fall through to the raw-JSON field, i.e. they are uncompensated gaps, not contracts.

---

## E. Ranking for S2

Worked-around gaps first, per the brief:

1. **E1 + E2** (concept identity, refinement chain) — compensated by three drifted hardcoded ref-set copies, two shape sniffs, and a half-dead description matcher; every one of the app's heaviest heuristics traces to these two.
2. **E6** (missing top-level descriptions) — compensated by clobbering description with the concept ref.
3. **E9** (multiplicity as shape only) — compensated three times, with one documented gating bug.
4. **E7 + E8** (silent extras; builder `default` key) — nobody *can* work around silent loss; E8 is a live data-loss bug in the authoring path.
5. **E3** (`required` + `default_value`) — silent semantic rewrite, uncompensated.
6. **E10** (`const` unread) — a real form-correctness hole, one-line-ish on either side.
7. **E4, E5** (`[N]`, `!`) — uncompensated and currently consequence-free; close them when touching the adjacent code (E4 rides E9's contract change).
