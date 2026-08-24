# S1 — Survival table: what each authored input fact becomes at each hop

**Status:** measured 2026-08-21 from the probe captures under [`probe/`](probe/) (regenerate with `.venv/bin/pipelex-dev trace-input-semantics tests/data/input_semantics/probe_bundle.mthds -o wip/input-semantics/probe`); **re-measured 2026-08-23 on `feature/Enrich` after the S2 closures** — rows an S2 entry changed carry a "**closed by S2**" note stating the before → after, with the new behavior visible in the regenerated captures. The probe bundle is the committed fixture `tests/data/input_semantics/probe_bundle.mthds`; the deliberately-rejected constructs live in `tests/data/input_semantics/rejected/` (extension `.mthds_invalid`, the repo convention that keeps them out of `plxt lint`). This table is evidence, not classification — Phase 3 marks each loss engine-side or language-side.

## The hops

1. **Parse** — `hop1_bundle_blueprints.json`: TOML → `PipelexBundleBlueprint` (`ConceptBlueprint` / `ConceptStructureBlueprint`).
2. **Generate** — `hop2_generated_sources/`: blueprint → generated structure-class source (`StructureGenerator`).
3. **Pydantic** — `hop3_raw_pydantic_schemas/`: generated class → raw `model_json_schema()`.
4. **Render** — `hop4_schema_renders/`: the SCHEMA render per pipe input (`{"concept", "content"}` envelope; array wrap when multiple). Measured: for a single input, `content` is byte-identical to hop 3 — the render adds the envelope and the array wrap, nothing else.
5. **Contract** — `hop5_pipe_io_contracts.json`: `PipeInputContract { concept_ref, presence, multiplicity, item_count, json_schema }` where `json_schema` is hop 4's `content` verbatim (S1 measured the pre-reshape `{ concept_ref, optional, json_schema }`; E5/E9 reshaped it).

## Structure-field facts

| Authored fact | Hop 1 parse | Hop 2 generate | Hop 3 pydantic | Hop 4/5 wire | Verdict |
|---|---|---|---|---|---|
| Field `description` | survived | survived (`Field(description=…)`) | survived (property `description`) | survived | **survives** |
| Concept's own `description` | survived | survived (class docstring) | survived (schema top-level `description`) | survived | **survives** (except class-backed concepts, below) |
| `required = true` | survived | survived (`Field(...)`, no `\| None`) | survived (in `required`, no null arm) | survived | **survives** |
| `required` omitted / `false` (table form) | survived (`required=False` default) | transformed: `X \| None` + `default=None` | `anyOf: [X, null]` + `default: null`, absent from `required` | survived | **survives, transformed** — this is the shape behind the app's flatten-then-repair round trip |
| Shorthand string field (`field = "desc"`) | transformed: text + `required=True` | survived | survived | survived | **survives** (shorthand implies required text) |
| `default_value` (text, integer, boolean, number) | survived | survived (`Field(default=…)`) | survived (`default`) | survived | **survives** |
| `default_value` (date / datetime / time) | survived (TOML temporal literals parse to real `date`/`datetime`/`time`) | survived (`date.fromisoformat("…")` etc.) | survived (`default` as ISO string) | survived | **survives** |
| `default_value` (list, dict) | survived | survived | survived | survived | **survives** |
| `required = true` **and** `default_value` together | **closed by S2 (E3): rejected at hop 1** — the blueprint validator refuses the pair as contradictory, and the generator's silent tiebreak became an explicit invariant | — | — | — | S1 measured: both survived hop 1, then **`required` silently dropped at hop 2**. Now an authoring error; the construct moved to `rejected/required_with_default.mthds_invalid` |
| `type = "date"` / `"datetime"` / `"time"` format | survived | survived (`date`/`datetime`/`time` annotations) | survived (`format: date` / `date-time` / `time`) | survived | **survives** |
| `choices` (multi) | survived | transformed: `Literal[…]` | `enum: […]` with `type: string` | survived | **survives** |
| `choices` single entry | survived | `Literal["x"]` | **`const: "x"`**, not `enum` | survived | **survives, shape shifts** — consumers must read both `enum` and `const` |
| `type` + `choices` together | both survived on the blueprint | transformed: choices win, `type` ignored (`resolved_fields.py:124`) | as choices | survived | `type` is **redundant/dropped** when choices present |
| `type = "dict"` with `key_type`/`value_type` | survived | `dict[str, X]` | `additionalProperties: {…value type…}`; `key_type` implicit (JSON keys are strings) | survived | **survives** (value type faithful, incl. `format` on `date` values) |
| `type = "list"`, `item_type` scalar | survived | `list[X]` | `items: {…}` | survived | **survives** |
| Nested list (`item_type = "list"`) | survived | `list[list[Any]]` with imprecision marker | `items: {items: {}}` — inner shape empty | survived | inner item type **not expressible** → empty schema |
| `type = "concept"` field | survived (`concept_ref`) | forward ref to qualified class name | inlined via `$refs` into `$defs` keyed by the **class-name spelling** (`input_semantics_probe__Gadget`) | survived | shape survives; **concept identity (its ref) is not recoverable** — only the mangled class name |
| List of concepts (`item_concept_ref`) | survived | `list["Domain__Code"]` | `items: {$ref: #/$defs/…}` | survived | same identity loss as above |
| Native concept field (`concept_ref = "native.Image"`) | survived | import of `ImageContent` | `$defs.ImageContent` | survived | shape survives; identity only as the content-class name |
| Two-level nesting (Widget → Gadget → Trinket) | survived | forward refs | both levels inlined into `$defs` | survived | **survives** structurally |
| Unknown keys on a field (`minimum`, `maximum`, `examples`, `unit`) | **closed by S2 (E7): rejected at hop 1, loudly** — `ConceptStructureBlueprint` is `extra="forbid"` | — | — | — | S1 measured: **died at hop 1, silently**. Now a validation error; the construct lives in `rejected/unknown_structure_field_key.mthds_invalid` |

## Concept-declaration facts

| Authored fact | Result on the wire | Verdict |
|---|---|---|
| Description-only concept (`PlainNote`), string-shorthand concept (`StringNote`) | generated `TextContent` subclass: schema is `{text: string}` with the concept description as top-level `description` | description **survives**; the implicit text-refinement is visible only as the `text` property |
| `refines = "native.Document"` (`RefinedDoc`) | schema = `DocumentContent`'s fields, title is the refining class name, concept description on top | **the refinement link itself leaves no trace** in the schema — nothing says "this is a Document" except the inherited field shapes |
| Custom refinement chain (`BaseEntity` ← `SpecialEntity` ← `ExtraSpecialEntity`) | each link's schema = inherited fields + own description; chain not represented | same: **`refines` dies between hop 2 and hop 3** (only inheritance side-effects survive) |
| `structure = "TextContent"` (class-backed, `ClassBacked`) | **closed by S2 (E1+E6):** the render injects `title` = the concept ref and `description` = the concept's authored description | S1 measured: raw `TextContent` schema with the class-name title and **no description**. Now the authored facts ride every render (visible on `hop4_schema_renders/input_semantics_probe.probe_refined.classbacked.json`) |
| Native concepts as direct inputs (`Text`, `Image`, `Document`, `Page`, `Number`, `Date`, `Time`, `Html`, `YesNo`) | **closed by S2 (E1+E6):** top-level `title` is the native concept ref (`native.Text`), `description` is the pinned native blueprint's; the native content classes also gained docstrings, so the instructor-side schema carries them too | S1 measured: class-name title, most natives with **no top-level description**. Nested concept identity (`$defs` keyed by class-name spelling) stays descriptor-only, per the E1 ruling |

## Pipe-input framing facts

| Authored fact | Result on the wire | Verdict |
|---|---|---|
| Bare vs qualified concept ref (`Widget` vs `input_semantics_probe.Gadget`) | both resolve to the same qualified `concept_ref` on the contract | **survives, normalized** |
| `?` optional marker | **reshaped by S2 (E5):** `presence: "optional"` on the contract (the two-valued `optional` flag is gone from inputs); the `json_schema` itself is unchanged | **survives**, now three-valued |
| `[]` list marker | `json_schema` wrapped as `{type: array, items: <hop-3 schema>}` at the hop-4 render, no bounds; the contract states `multiplicity: "variable"` (E9) and the memo key carries the real multiplicity | **survives** as array wrapping + a stated contract fact |
| `[N]` fixed count (`Gadget[2]`) | **closed by S2 (E4+E9):** the render emits `minItems: N` / `maxItems: N` on the array wrap, and the contract states `multiplicity: "fixed"` + `item_count: N` (`[1]` stays single) | S1 measured: **count dropped at hop 4** (`is_multiple()` collapse). Now visible on `hop4_schema_renders/input_semantics_probe.probe_markers.two.json` and hop 5's `two` entry |
| `!` force marker | **closed by S2 (E5):** the contract reports `presence: "force"` — the authored assertion reaches lint and graph surfaces | S1 measured: **force/plain distinction dropped at hop 5**. Output presence stays two-valued (`!` is rejected on outputs) |
| Per-input-slot description | **cannot be authored** — `inputs` values are ref strings only (`pipe_blueprint.py:186`); the table form is rejected (see `rejected/per_input_description.mthds_invalid`) | language ceiling |

## Constructs the language rejects (ceiling evidence, `rejected/`)

- `default_value` on a `concept`-typed field — refused (`concept_structure_blueprint.py:111`).
- Non-string `choices` (`[1, 2, 3]`) — refused (`choices: list[str]`, pydantic does not coerce).
- A per-input description table in `inputs` — refused (`inputs: dict[str, str]`).
- `refines` together with `structure` — refused (`concept_blueprint.py:95`).
- Multiple `refines` (`["a", "b"]`) — refused (`refines: str | None`; the TODO at `concept_blueprint.py:19` records the restriction).
- Unknown keys in a structure-field table — refused since S2 (E7, `extra="forbid"`); see `rejected/unknown_structure_field_key.mthds_invalid`.
- `required = true` together with `default_value` — refused since S2 (E3); see `rejected/required_with_default.mthds_invalid`.

## Measurement surprises worth carrying into Phase 3

All four fed S2 and the first three are closed there (the fourth was the good news that scoped it):

- **Unknown structure-field keys vanish silently at parse.** ~~`ConceptStructureBlueprint` ignores extras~~ — closed by E7 (`extra="forbid"`).
- **`required` + `default_value` together: the default wins and the required-ness is dropped** by the generator's parameter ordering — closed by E3 (the pair is rejected at validation; the generator branch is now an explicit invariant).
- **`is_multiple()` collapses `[N]` to a bare bool** before the render — closed by E4 (real multiplicity threaded through the render and the memo key).
- **The SCHEMA render is otherwise lossless**: hop 3 → hop 5 is verbatim (measured equality), so every gap is upstream of the render — in the language, the blueprint, or the generator. This is what made S2 an upstream-only worklist.
