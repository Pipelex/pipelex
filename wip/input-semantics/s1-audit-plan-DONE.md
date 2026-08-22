# S1 — The input-semantics audit: plan (✅ done — S1 closed 2026-08-21)

**Status:** ✅ **Done.** Every phase below is complete and both checkpoints were reached; the milestone closed on 2026-08-21 with the deliverable in [`findings.md`](findings.md). This file is kept as the as-built record of how the audit was run — plan written 2026-08-21, companion to [`audit.md`](audit.md) (the brief — read it first; this document schedules the audit, it does not re-argue it). Progress is tracked here with checkboxes. The deliverable is `findings.md`, written beside this file when Phase 4 completes. Per the brief: audit only — no fixes, no descriptor design, no wire changes.

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
- [x] Pin the parse hop: TOML structure syntax lands on `PipelexBundleBlueprint.concept: dict[str, ConceptBlueprint | str]` (`pipelex/mthds_parsing/pipelex_bundle_blueprint.py:100`); a concept's `structure` is `str | dict[str, str | ConceptStructureBlueprint]` (`pipelex/core/concepts/concept_blueprint.py:18`), and the shorthand string field normalizes to a required text field in `normalize_structure_blueprint` (`pipelex/core/concepts/helpers.py:70`). The full per-field ceiling is `ConceptStructureBlueprint`'s field list (`concept_structure_blueprint.py:50-64`); the five declaration shapes are `ConceptDeclarationType` (`concept_factory.py:47-86`). ⚠ `ConceptStructureBlueprint` does NOT forbid extras — unknown keys on a field are silently dropped at parse.
- [x] Pin the schema hop: `StuffSpec.render_stuff_spec` (`pipelex/core/pipes/stuff_spec/stuff_spec.py:42`) → `Concept.render_concept_representation` → `_render_schema_representation` (`pipelex/core/concepts/concept.py:193-214`): raw `model_json_schema()`, wrapped `{type: array, items: …}` when `is_multiple()`, inside a `{"concept", "content"}` envelope — no other transform, measured byte-identical hop 3 → hop 5.
- [x] Build the capture harness as the `pipelex-dev trace-input-semantics` command: `pipelex/cli/dev_cli/commands/trace_input_semantics_cmd.py`, registered in `_dev_cli.py`. Dumps hop1 blueprint JSON, hop2 regenerated class sources (as `.py.txt` so captures stay inert to linters), hop3 raw pydantic schemas, hop4 SCHEMA renders per pipe input, hop5 contracts, plus `trace_manifest.json` with per-input wire framing (authored spec string, resolved ref, multiplicity, presence). Tests: `tests/integration/pipelex/cli/test_trace_input_semantics_cmd.py` (per-hop assertions on a small bundle + a run over the committed probe).
- [x] Probe matrix enumerated from the parsing layer and encoded directly in the probe bundle (see Phase 1).

## Phase 1 — The probe bundle

- [x] Probe bundle authored at `tests/data/input_semantics/probe_bundle.mthds` with `PROBE_` sentinels on every authored fact: all field types, choices (multi/single/typed), defaults on every type that allows one, required both ways and required+default together, shorthand fields, dicts (text/number/date values), lists (scalar/concept/nested), two-level concept nesting, a native concept field, refines of a native and a two-link custom chain, class-backed structure, string/basic concept declarations, and pipes covering `?`, `[]`, `[2]`, `!`, bare vs qualified refs, and native concepts as direct inputs.
- [x] The bundle validates cleanly (pinned by a test). Rejected constructs live in `tests/data/input_semantics/rejected/*.mthds_invalid` (repo convention for deliberately-invalid fixtures): default on a concept field, non-string choices, per-input-slot description, refines+structure, multiple refines — each refusal verified against the real validator.

## Phase 2 — Measure

- [x] Trace run on the probe bundle; captures under `wip/input-semantics/probe/`. Regenerate with `.venv/bin/pipelex-dev trace-input-semantics tests/data/input_semantics/probe_bundle.mthds -o wip/input-semantics/probe`.
- [x] Survival table written at [`survival-table.md`](survival-table.md): one row per authored fact, per-hop verdicts, plus the rejected-constructs ceiling evidence and the measurement surprises.

**Checkpoint CP1 — measurements in hand. ✅ Reached 2026-08-21.** The probe bundle, harness, and survival table exist; classification (Phase 3) has not started. Surprises the measurement produced, so the next session classifies without re-running anything:

- **Unknown keys on a structure field are silently dropped at parse** (`ConceptStructureBlueprint` has no `extra="forbid"`): `minimum`/`maximum`/`examples`/`unit` authored fine, validated green, and were absent from the hop-1 blueprint dump. The MTHDS lint hook's generated schema flags some of these, the runtime never does.
- **`required = true` plus `default_value` drops the required-ness at hop 2**: the generator emits `default=…` instead of `...` (`generator.py:308-311`), so the field leaves pydantic's `required` list.
- **`[N]` fixed count dies at the render**: `stuff_spec.is_multiple()` collapses multiplicity to a bool before rendering, so `Gadget[2]` emits a plain `array` with no `minItems`/`maxItems`; the contract memo key `(concept_ref, is_multiple())` (`pipe_io_contracts.py:104`) makes the count structurally unreachable there.
- **`!` force marker dies at the contract**: `optional=presence.is_optional` (`pipe_io_contracts.py:123`) maps force and plain to the same `optional: false`.
- **Hop 3 → hop 5 is lossless** (measured equality of the widget schema at both hops): every gap is upstream — language, blueprint, or generator — never the render or contract plumbing.
- **Class-backed concepts (`structure = "ClassName"`) lose their concept description entirely**: the pre-existing class carries no docstring from the concept, so the schema has no top-level `description` (measured on `ClassBacked` → `TextContent`).
- **The stale check-mthds hook schema false-positives on `structure = "TextContent"`** (known issue — trust `make plxt-lint` / the real validator).
- Sigil constraint worth knowing when authoring probes: `@var` must sit alone on its own line in prompts; inline use is a validation error (use `$var` inline).

## Phase 3 — Classify and place the wrinkles

- [x] Mark every gap **engine-side** or **language-side** using the brief's test: could a `.mthds` author write it today, in any syntax the parser accepts? Evidence as `path/file.py:line` for every engine-side claim. Result: ten engine-side entries (E1–E10 in `findings.md` §A), each a closable work item.
- [x] Confirm and complete the language-side ceiling from the Phase 0 parser findings — thirteen entries (`findings.md` §B), including three the brief missed: choice labels, inner types of nested lists, and refine-and-extend (`refines` XOR `structure` means a refinement can never add fields, `concept_blueprint.py:95`).
- [x] Catalogue the engine-authored descriptions on the native content classes (`findings.md` §D). The known contract-in-disguise was verified read-only in `pipelex-app` — and found *already half-drifted*: the app's matcher checks `"pipelex storage url"` and `"document url"`, but the current `DocumentContent.url` wording ("a storage URI") only matches the second. Two more contract families surfaced: `DocumentContent`'s field *names* (a value-sniff set in the app) and `TextContent`'s `{text}` wrapper shape.
- [x] Settle the two meaning questions (`findings.md` §C). `default_value` is an execution-level default applied on absence at the one input-ingestion seam (`stuff_content_factory.py:35`) and for LLM structured output; the inputs template deliberately omits defaulted fields; dry-run mocks ignore defaults. `required` (payload-level, travels inside the schema) and `?` (slot-level, travels as the contract flag) never interact; `!` is a use-site assertion flattened into plain at the contract.
- [x] Fill the downstream column — every one of the direction doc's four workaround families pinned to file:line in `pipelex-app`, plus finds the direction doc missed: `const` (single-entry choices) unhandled anywhere in the app, multiplicity rebuilt from `type: "array"` in three independent places (one documented gating bug), and the pydantic `title` discarded/overwritten because it is the class name.

## Phase 4 — Write the findings and close the milestone

- [x] `findings.md` written beside this file: the two lists with *where authored* / *where lost* / *who guesses today* per entry, one sentence of recommendation each, no design sections.
- [x] Engine-side list phrased as S2 work items with a ranking section (§E, worked-around gaps first); language-side list written repo-context-free for Track H.
- [x] Native-description catalogue (§D) and the two meaning answers (§C) placed as their own sections.

**Checkpoint CP2 — milestone gate. ✅ Reached 2026-08-21, S1 closed.**

- [x] Tool kept and documented: `docs/contribute/trace-input-semantics.md` (in both mkdocs navs), a `trace-input-semantics` bullet in the kit agent-rules templates (`commands.md` / `codex_commands.md`, regenerated via `make rules`), and a changelog entry under Unreleased.
- [x] Plan checkboxes updated; decisions and surprises recorded below.
- [x] `../wip/devx/input-form-roadmap.md` updated per its checkpoint protocol — S1 marked closed with what D1, S2, H1, and K1/M1 each need from the findings.

**Decisions taken and surprises found in Phases 3–4** (beyond the CP1 list, which still stands):

- **A live authoring-path data-loss bug surfaced during the `default_value` trace** (findings E8): the builder's TOML writer emits the key `default` instead of `default_value` (`pipelex/builder/operations/concept_ops.py:115-116`), and because `ConceptStructureBlueprint` ignores extras, a builder-emitted default validates green and evaporates on re-load. Per the brief, not fixed here — it is on the S2 list, and E7's `extra="forbid"` would have caught it.
- **The app's description-substring contract has already half-broken in the wild**: the `"pipelex storage url"` branch of `document-url-widget.tsx:130-136` matches nothing against the current `DocumentContent.url` wording — the drift the brief warned about had already happened, silently. `ImageContent.url` matches neither substring, so image inputs never get the RJSF dropzone by that route.
- **The parse-layer extras asymmetry is the ceiling's enforcement gap**: `ConceptBlueprint` forbids unknown keys, `ConceptStructureBlueprint` silently drops them — so almost the whole language-side ceiling fails silently at the field level. Classified engine-side (E7) because the silence, not the ceiling, is the engine's.
- **Classification judgment call:** `[]` multiplicity was given an engine-side entry (E9) even though it "survives" as array wrapping, because the contract carries no structured multiplicity field and the app rebuilds it from schema shape in three places — the brief's who-guesses test decided it.
- **Scope discipline held:** no fixes, no descriptor design; the only repo changes besides `wip/` documents are the tool docs, the kit-template bullets, and the changelog entry required by this gate.
