# S1 — Survival table: what each authored input fact becomes at each hop

**Status:** measured 2026-08-21 from the probe captures under [`probe/`](probe/) (regenerate with `.venv/bin/pipelex-dev trace-input-semantics tests/data/input_semantics/probe_bundle.mthds -o wip/input-semantics/probe`). The probe bundle is the committed fixture `tests/data/input_semantics/probe_bundle.mthds`; the deliberately-rejected constructs live in `tests/data/input_semantics/rejected/` (extension `.mthds_invalid`, the repo convention that keeps them out of `plxt lint`). This table is evidence, not classification — Phase 3 marks each loss engine-side or language-side.

## The hops

1. **Parse** — `hop1_bundle_blueprints.json`: TOML → `PipelexBundleBlueprint` (`ConceptBlueprint` / `ConceptStructureBlueprint`).
2. **Generate** — `hop2_generated_sources/`: blueprint → generated structure-class source (`StructureGenerator`).
3. **Pydantic** — `hop3_raw_pydantic_schemas/`: generated class → raw `model_json_schema()`.
4. **Render** — `hop4_schema_renders/`: the SCHEMA render per pipe input (`{"concept", "content"}` envelope; array wrap when multiple). Measured: for a single input, `content` is byte-identical to hop 3 — the render adds the envelope and the array wrap, nothing else.
5. **Contract** — `hop5_pipe_io_contracts.json`: `PipeInputContract { concept_ref, optional, json_schema }` where `json_schema` is hop 4's `content` verbatim.

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
| `required = true` **and** `default_value` together | both survived on the blueprint | transformed: generator emits `default=…` and drops the `...` marker (`titled_default`) | field is **not** in `required` — the authored `required=true` is gone | same | **`required` dropped at hop 2** when a default is present |
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
| Unknown keys on a field (`minimum`, `maximum`, `examples`, `unit`) | **silently dropped at parse** — absent from the blueprint dump; validation passes | — | — | — | **dies at hop 1, silently** (`ConceptStructureBlueprint` has no `extra="forbid"`) |

## Concept-declaration facts

| Authored fact | Result on the wire | Verdict |
|---|---|---|
| Description-only concept (`PlainNote`), string-shorthand concept (`StringNote`) | generated `TextContent` subclass: schema is `{text: string}` with the concept description as top-level `description` | description **survives**; the implicit text-refinement is visible only as the `text` property |
| `refines = "native.Document"` (`RefinedDoc`) | schema = `DocumentContent`'s fields, title is the refining class name, concept description on top | **the refinement link itself leaves no trace** in the schema — nothing says "this is a Document" except the inherited field shapes |
| Custom refinement chain (`BaseEntity` ← `SpecialEntity` ← `ExtraSpecialEntity`) | each link's schema = inherited fields + own description; chain not represented | same: **`refines` dies between hop 2 and hop 3** (only inheritance side-effects survive) |
| `structure = "TextContent"` (class-backed, `ClassBacked`) | schema is raw `TextContent`: `title: "TextContent"`, **no `description` at all** | **the concept's own description is dropped** — the pre-existing class has no docstring from the concept, so nothing carries it into the schema |
| Native concepts as direct inputs (`Text`, `Image`, `Document`, `Page`, `Number`, `Date`, `Time`, `Html`, `YesNo`) | content-class schema (`title: "TextContent"` etc.); most have **no top-level description** (only `DateContent`/`TimeContent` docstrings survive); field descriptions are the engine-authored ones (e.g. `DocumentContent.url`: "The document URL: a storage URI, an HTTP(S) URL, or a base64 data URL") | concept identity beyond top-level `concept_ref` exists **only** in the `title` class-name spelling and shape-sniffable properties |

## Pipe-input framing facts

| Authored fact | Result on the wire | Verdict |
|---|---|---|
| Bare vs qualified concept ref (`Widget` vs `input_semantics_probe.Gadget`) | both resolve to the same qualified `concept_ref` on the contract | **survives, normalized** |
| `?` optional marker | `optional: true` on the contract; the `json_schema` itself is unchanged | **survives** as a contract flag |
| `[]` list marker | `json_schema` wrapped as `{type: array, items: <hop-3 schema>}` at the hop-4 render; contract memo keys on `is_multiple()` | **survives** as array wrapping |
| `[N]` fixed count (`Gadget[2]`) | parsed to `multiplicity: 2` on the loaded spec, but the render only asks `is_multiple()` → plain `array` with **no `minItems`/`maxItems`** | **count dropped at hop 4** (`stuff_spec.py:58`, `concept.py:206-212`) |
| `!` force marker | parsed to `presence: force`, but the contract reports `optional: false` — same as plain | **force/plain distinction dropped at hop 5** (`pipe_io_contracts.py:123`) |
| Per-input-slot description | **cannot be authored** — `inputs` values are ref strings only (`pipe_blueprint.py:186`); the table form is rejected (see `rejected/per_input_description.mthds_invalid`) | language ceiling |

## Constructs the language rejects (ceiling evidence, `rejected/`)

- `default_value` on a `concept`-typed field — refused (`concept_structure_blueprint.py:111`).
- Non-string `choices` (`[1, 2, 3]`) — refused (`choices: list[str]`, pydantic does not coerce).
- A per-input description table in `inputs` — refused (`inputs: dict[str, str]`).
- `refines` together with `structure` — refused (`concept_blueprint.py:95`).
- Multiple `refines` (`["a", "b"]`) — refused (`refines: str | None`; the TODO at `concept_blueprint.py:19` records the restriction).

## Measurement surprises worth carrying into Phase 3

- **Unknown structure-field keys vanish silently at parse.** `ConceptStructureBlueprint` ignores extras (no `extra="forbid"`), so a hopeful `minimum = 0` authors fine, validates green, and reaches nothing. The stale-schema MTHDS hook is the only thing that even warns.
- **`required` + `default_value` together: the default wins and the required-ness is dropped** by the generator's parameter ordering (`generator.py:308-311`).
- **`is_multiple()` collapses `[N]` to a bare bool** before the render, so fixed counts can never reach `minItems`/`maxItems` without touching the memo key `(concept_ref, is_multiple())` in `pipe_io_contracts.py:104`.
- **The SCHEMA render is otherwise lossless**: hop 3 → hop 5 is verbatim (measured equality), so every gap is upstream of the render — in the language, the blueprint, or the generator.
