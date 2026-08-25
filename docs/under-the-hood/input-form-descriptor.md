# Input-Form Descriptor

Every valid `validate` report carries, beside `pipe_io_contracts`, an **input-form descriptor** per pipe: an ordered list of field descriptors a renderer can turn into a fill-in form with no schema heuristics, no hardcoded concept tables, and no description matching. The wire contract is the MTHDS spec `docs/specs/mthds-input-form-descriptor.md` at the workspace root; this page documents Pipelex's reference derivation of it.

The descriptor exists because the emitted `json_schema` is a *payload* contract, and the projection that produces it loses facts a form needs: which concept a node is, what it refines, whether `!` or plain was authored, a fixed `[N]` count, an authored default, a one-member choice list. The descriptor reports those facts from where they still exist — the authored blueprints — and leaves the payload shape to the schema. It is presentation; it never changes what a caller submits.

## Where it lives

- `pipelex/pipeline/input_form.py` — the wire models (`FieldKind`, `InputFormField`, `PipeInputFormDescriptor`), the one public derivation `build_input_form(pipes)`, and the `InputFormDeriver` behind it.
- `PipelexValidationReport.input_form` (`pipelex/pipeline/validation_report.py`) — a **required** field, keyed exactly like `pipe_io_contracts`. `build_validation_report` requires it as a keyword: the shared-assembly rule says a report field is populated on every backend or none, so a backend that forgets it fails loudly instead of shipping an empty view.
- `pipelex/pipeline/validate_in_process.py` — the in-process assembly derives it inside the validation library's window, right beside `build_pipe_io_contracts`.
- `pipelex/codegen/native_expansion.py` — `reflect_structure_class`, the faithful-or-absent reflection of a registered structure class into blueprint form, shared with the native consistency probe.

The report always carries the field. Whether it travels on the HTTP wire is the route's decision (absent unless a caller opts in), which belongs to the API.

## Fact sources

The derivation reads two things and nothing else:

- **Slot facts** from the loaded pipes' `StuffSpec`s: the authored input order, the three-valued presence marker (`plain` / `optional` / `force`), and the multiplicity including a fixed `[N]` count. Iterating the same loaded pipes as `build_pipe_io_contracts` — `PipeSignature` placeholders included — is what makes the two key sets equal by construction.
- **Concept facts** from the *qualified* library crate built from the parsed blueprints: descriptions, refinement links, structure fields with their defaults, choices, required-ness and nested concept refs. Qualified, not normalized: normalization flattens in-crate refinement, and the descriptor must report the `refines` chain as a list. Native concepts contribute their pinned blueprints; class-backed concepts (`structure = "ClassName"`) are reflected from the class registry, which is why the derivation must run while the validation library is still loaded.

The derivation is total. A node it cannot map honestly reports `kind: "unknown"`, the renderer's raw escape hatch against the sibling `json_schema`; nothing raises.

## Kind assignment

Kinds are decided by chain membership and declared types — never by sniffing a schema shape. Per node, in precedence order:

1. A concept with authored structure fields anywhere along its refinement chain is an `object`; its fields are the merged structures along the chain, base fields first, a refining concept overriding its parents'.
2. Otherwise, the first `structure = "ClassName"` on the chain decides: a native class name (`TextContent`, `ImageContent`, …) maps by identity to that native's row; any other registered class is reflected field by field into an `object`; an unregistered or unmappable class is `unknown`.
3. Otherwise, a chain bottoming at a native concept takes that native's row, keeping the concept's own `concept_ref`, description and `refines`.
4. Otherwise — a description-only or string-described concept — `prose` with `refines` ending in `native.Text`: this engine backs such a concept with a `TextContent` subclass, so that is a stated fact, not shape invention.

The crate the deriver reads is the current library's accumulated one, which holds the validated bundle and every `library_dirs` bundle loaded beside it — so a concept from a library dir, or a local concept refining one, follows the same rules as a local concept. A concept absent from that crate altogether is `unknown`.

The table and rules above ARE the no-hint kind assignment — stated rules, not heuristics: with no applicable intent hint, a node's kind is exactly what they produce. An applicable authored `intent` (spec: MTHDS `intent-hints.md`) *feeds* that assignment, never competes with it: on a **text-valued** node — one whose site is a `text` field, a `native.Text`-chained or description-only concept, judged per item on plural sites — an effective `intent = "prose"` yields `kind: "prose"` and `intent = "label"` yields `kind: "text"`; an absent, unknown, or inapplicable intent leaves the no-hint kind untouched. On a **number-valued** node, `rating` and `quantity` never change `kind` (both are `number`; the union has no finer kind) — they ride the `hints` slot for the renderer to honor. A time-formatted `text` node and an `Html`-backed `prose` node are *not* text-valued sites, so no intent word applies to them.

| Native concept | Kind |
|---|---|
| `Text`, `Html` | `prose` |
| `Number` | `number` with `integer: false` |
| `YesNo` | `boolean` |
| `Date` | `date` with `datetime: false` |
| `Time` | `text` with `format: "time"` |
| `Document` | `document` |
| `Image` | `image` |
| `Page`, `TextAndImages`, `SearchResult` | `object` over the pinned blueprint's fields |
| `Dynamic`, `Anything`, `JSON` | `unknown` |

Nested structure fields map by their declared type: `text` → `text`; `integer` → `number` with `integer: true`; `number` → `number`; `boolean` → `boolean`; `date` → `date`; `datetime` → `date` with `datetime: true`; `time` → `text` with `format: "time"`; a field with `choices` → `enum` (choices win over `type`, matching the structure generator); `concept` → the concept's node, carrying its namespaced `concept_ref`; `list` → `list` whose `item` comes from `item_type` / `item_concept_ref` (a nested list's inner item is inexpressible and reports `unknown`); `dict` → `unknown`. The shorthand `field = "description"` form is a required `text`. Nested fields take the blueprint field's description and `required` over the concept's; a scalar flattened at the top level keeps the concept's description.

Constraint slots (`minimum`, `exclusive_minimum`, `min_length`, `pattern`, …) come only from reflected classes: the language cannot author constraint keys (an authored `minimum = 0` is rejected as an unknown structure-field key), whereas a registered class's `Field(gt=0, max_length=8, pattern=...)` is read from the pydantic field metadata and stamped on the matching `number` or `text` node. A pydantic default on a reflected class is an authored fact: `field_info.is_required()` decides the node's `required` and a non-`None` default is reported as its `default_value` — a defaulted field is never required, the same invariant blueprint validation enforces by rejecting the `required = true` + `default_value` pair. (Authored `hints` are a parsed blueprint field with its own leniency rules; see below.)

## Hints

Every node carries an optional `hints` slot: the node's **effective** MTHDS intent hints — the key-by-key merge of the concept's refinement chain (nearer declaration winning) with the site's own hints (a field's or a slot's, the site layer winning). Everything well-formed rides it, unknown keys and words included (the advisory validation lint has already warned about them; the descriptor preserves them for consumers that know more than this version does). On a plural node the merged hints appear on the `list` node *and* its `item` — the `concept_ref` duplication precedent: applicability is judged per item, and a renderer reading either node finds the same answer. A node with no effective hints has no `hints` member, so hint-free methods produce byte-identical descriptors to before hints existed. The slot is flat `string → string` by contract.

## Required, presence and gating

On a top-level field, `required` is `presence != "optional"`, and `gating` — whether the run is blocked until the caller provides content — is `required` and not a variable-multiplicity list. A plain `Concept[]` slot is therefore `required: true, gating: false`: its empty form is the legitimate value `[]`. A fixed-count `Concept[N]` slot is a `list` with `item_count: N` that gates like any scalar. `Concept[1]` is a single node, because the runtime takes one value there (`StuffSpec.is_multiple()` is `count > 1`), and the descriptor says what the runtime accepts. Nested fields carry neither `presence` nor `gating`; their `required` is the payload fact.

`gating` is also what the **vacuous-presence lint** is stated on. When a gating slot of an entry pipe names an `object` node whose `fields` carry no `required: true`, validation reports the advisory `input_presence_vacuous` warning: the caller is told the slot must be supplied, but the empty object satisfies it, so nothing is actually demanded. Keying the lint on `gating` rather than on `presence` is deliberate — `gating` is the fact a renderer blocks Run on, so the lint and the form cannot disagree about which slots demand content, and the variable-multiplicity exclusion falls out of the rule above instead of being restated. See [Understanding Optionality](../building-methods/pipes/understanding-optionality.md) for the author-facing description and its two remedies.

## Wire shape

Inapplicable slots are absent, never JSON `null`: the report's valid arm is dumped without `exclude_none`, so `InputFormField` owns its wire shape through a serializer that drops `None` values and writes the `date` kind's flag under its spec name `datetime`. Applicable falsy values (`required: false`, `integer: false`, `gating: false`) are kept. Per-kind validators keep a node honest at construction (`enum` needs `choices`, `object` needs `fields`, `list` needs `item`, `number` needs `integer`, `date` needs `datetime`).

## Seeing it

`pipelex-dev trace-input-semantics` captures the descriptors as `hop5_input_form.json` beside `hop5_pipe_io_contracts.json`, so an authored fact can be checked on both projections at once — see [Tracing Input Semantics](../contribute/trace-input-semantics.md). The assignment table is pinned by `tests/integration/pipelex/pipeline/test_input_form.py` over the committed probe bundle (and the hints behavior over its hinted sibling, `hinted_bundle.mthds`), the wire models by `tests/unit/pipelex/pipeline/test_input_form_models.py`, the hint merges and kind-feeding by `tests/unit/pipelex/pipeline/test_input_form_hints.py`, and the escape hatches the library loader keeps unreachable (concept cycles, unregistered classes) by `tests/unit/pipelex/pipeline/test_input_form_deriver.py`.
