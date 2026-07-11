# Smart Inputs — signature-driven input shaping: design

Status: **design approved — all decisions D1–D11 decided with Louis** (D1–D4 on 2026-07-06, D5–D11 approved 2026-07-07 with two amendments: the D9 resolution via a native `YesNo` concept as a companion track, and the D11 template-generation `--explicit` flag). Branch `feature/Smart-inputs` (worktree `_smart`), based on main at v0.38.0 (includes TOML inputs #1022 and Optionals phase 1 #1021). Execution order across the whole track (YesNo → Datetime → Smart Inputs, one release) is in this folder's `README.md`. No implementation plan yet — that comes next.

## 1. The problem

When you run a pipeline, the expected shape of every input is already known: the pipe declares `inputs = { question = "legal.Question", priority = "scoring.Priority", cvs = "native.Document[]" }`, and that declaration is parsed into an `InputStuffSpecs` (name → `StuffSpec{concept, multiplicity, presence}`) before any input data is read. Yet the inputs file must be *self-describing*: anything beyond a bare string or list of strings needs the `{"concept": "...", "content": ...}` envelope, repeating type information the runtime already has.

The root cause is architectural, and it is one line wide. Every surface — CLI (JSON/TOML file, inline JSON), Python API, hosted runner — funnels inputs through a single chokepoint: `WorkingMemoryFactory.make_from_pipeline_inputs` → `StuffFactory.make_stuff_from_stuff_content_or_data` (`pipelex/core/stuffs/stuff_factory.py:229`). The call site, `prepare_pipe_job` (`pipelex/pipeline/execution_seams.py:198`), **holds the resolved `pipe` object — `pipe.inputs` is the full signature — and never passes it down.** Interpretation is bottom-up, from the value's shape alone:

| You provide | Declared input | What happens today |
|---|---|---|
| `"What are the fees?"` | `legal.Question` (refines Text) | **Silent mistype.** Becomes a `native.Text` stuff, not a `Question`. Runs anyway (`validate_before_run` checks presence only) — the graph, provenance, and concept-driven branching see the wrong type. |
| `42` | `scoring.Priority` (refines Number) | **Hard error.** `int`/`float` aren't even in the `StuffContentOrData` protocol type. |
| `{"invoice_number": "INV-001", "amount": 1250.0}` | `accounting.Invoice` (structured) | **Hard error** demanding the envelope: "does not have a 'concept' key". |
| `[{"name": "Alice"}, {"name": "Bob"}]` | `crm.Person[]` | **Hard error** (list of dicts unsupported without envelope). |
| `[]` | `contracts.Clause[]` | **Hard error** ("cannot create Stuff from empty list") — even though the signature names the item concept. |

So today's behavior is a mix of hard errors (numbers, dicts) and silent type erosion (strings for refined concepts). Both stem from the same signature-blindness.

The mental-model statement of the fix: **inputs are arguments to a typed function; the signature is the type annotation; the call site should not repeat the types.** Today's inputs file is a serialization of working memory (self-describing, mirror-of-internal-shape). It should instead be *values*, interpreted top-down against the declared signature — with the explicit envelope remaining as the escape hatch, not the default ceremony.

Everything the fix needs already exists as primitives: `ConceptLibrary.is_compatible` (refinement/subsumption, `pipelex/libraries/concept/concept_library.py:98`), `Concept.get_structure_class()` (concept → pydantic model, `pipelex/core/concepts/concept.py:174`), `StuffContentFactory.make_content_from_value` (structure class + str/dict → typed content, `pipelex/core/stuffs/stuff_content_factory.py:12`), and `InputStuffSpecs` itself (`pipelex/core/pipes/inputs/input_stuff_specs.py`). They have just never been composed at the right seam.

## 2. The shape at a glance

Given this method:

```toml
[concept.Question]
description = "A question about a legal document"
refines = "Text"

[concept.Priority]
description = "A priority level from 1 to 5"
refines = "Number"

[concept.Invoice]
description = "An invoice"
structure = { invoice_number = "text", amount = "number" }

[pipe.analyze_case]
inputs = { question = "Question", priority = "Priority", invoice = "Invoice", exhibits = "native.Document[]" }
output = "CaseAnalysis"
```

Today's `inputs.json`:

```json
{
  "question": {"concept": "legal.Question", "content": "What are the fees?"},
  "priority": {"concept": "legal.Priority", "content": {"number": 3}},
  "invoice": {"concept": "legal.Invoice", "content": {"invoice_number": "INV-001", "amount": 1250.0}},
  "exhibits": {"concept": "native.Document", "content": [{"url": "exhibit-a.pdf"}]}
}
```

With smart inputs:

```json
{
  "question": "What are the fees?",
  "priority": 3,
  "invoice": {"invoice_number": "INV-001", "amount": 1250.0},
  "exhibits": ["exhibit-a.pdf"]
}
```

Every value is interpreted against the declared spec: the string becomes a *`Question`* (the declared concept, correctly typed — not `native.Text`), the number a `Priority`, the dict validates against `Invoice`'s structure class, and the list satisfies `Document[]` element-wise with each string read as a URL/path. The envelope form still works everywhere and is now additionally *checked* against the declaration.

## 3. Options considered for where the smartness lives

- **A. Signature-driven shaping at the core seam (chosen).** Thread `pipe.inputs` into working-memory construction; interpret each provided value against its declared `StuffSpec`. One chokepoint, so every surface benefits at once; fixes both the hard errors and the silent mistyping; strictly widens what is accepted.
- **B. CLI-layer preprocessing.** Shape the loose file into canonical envelope form inside the CLI before core sees it. Rejected: API/client/SDK users get nothing, the logic duplicates per surface, and the CLI would re-do signature resolution the runtime performs anyway. The smartness would sit on the wrong side of the funnel.
- **C. Retype-after-build (promotion pass).** Keep bottom-up building, then promote each Stuff's concept to the declared concept when compatible. Rejected as a standalone: bare numbers and dicts explode before promotion ever runs. Retyping is a sub-mechanism of A, not an alternative.
- **D. LLM-assisted adaptation.** When deterministic shaping fails (a dict whose fields *almost* match the structure, a CSV with different column names), optionally run a mapping step — Pipelex eating its own dog food. Deferred to a later phase as an explicit opt-in (see §8); v1 smartness must be deterministic and predictable.

## 4. Decisions taken (D1–D4, with Louis, 2026-07-06)

### D1 — Activation: always-on, all surfaces, no flag

Signature-driven interpretation is the default behavior wherever a signature exists — CLI file/inline inputs, Python API `execute(inputs=dict)`, hosted runner. No `--smart-inputs` flag, no config knob. Rationale: it strictly widens the accepted input space; the only behavioral change to previously-working inputs is *better typing* (bare strings now typed as the declared concept instead of `native.Text`), which is a fix, not a regression. Consistent with the no-backward-compat principle. Alternatives rejected: opt-in flag (splits docs into two modes, adds ceremony), CLI-only (see option B above).

Out of scope of the flag question: inputs passed as an already-built `WorkingMemory` bypass shaping entirely (they are already typed).

### D2 — Multiplicity: auto-wrap singles, element-wise shaping, empty lists legal

When the declared spec has multiplicity (`X[]` or `X[N]`):

- A JSON list shapes **element-wise**: each item is interpreted against the item concept (strings, numbers, dicts — same rules as singulars), producing a `ListContent` typed with the declared concept.
- A **single bare value auto-wraps** into a one-item list. Generous, matches the feature's spirit. Fixed-count `[N]` still validates the count — a single value only satisfies `[1]`.
- An **empty list is legal** and produces an empty `ListContent` typed with the declared item concept. (Today it's an error because there is nothing to infer from; the signature removes the ambiguity. This also aligns with Optionals D4: emptiness is the plural "nothing".)
- Conversely, a list provided where a singular is declared is a **hard error** (we can't guess which item was meant).

### D3 — File-ish native concepts: a bare string is a URL/path

When the declared concept resolves to a file-carrying native content class (Image, Document, and any concept refining them), a bare string is read as a URL/path: `"photo": "photo.jpg"` satisfies an `Image` input. Unambiguous because these concepts don't refine Text — there is no collision with text interpretation; the signature is what disambiguates. The existing `{"url": ...}` dict form keeps working (and is itself now shaped by the signature, no envelope needed). The CLI's relative-path resolution (`resolve_inputs_paths`) must learn to resolve these bare strings too — today it only walks `"url"` keys; it needs the signature to know which bare strings are paths (see D7, seams).

### D4 — Failure mode: hard error with a rendered template hint

When a provided value cannot be shaped to the declared concept — wrong scalar kind, dict failing structure validation, list where singular is declared, envelope naming an incompatible concept — the run fails with a typed error that names the input, the declared concept ref, what was provided, and **renders the expected shape** by reusing the template machinery (`InputStuffSpecs.build_inputs_template` / `StuffSpec.render_stuff_spec`). No fallback to bottom-up inference on failure: predictability beats forgiveness, and the silent-mistyping path must not survive through a back door. New error classes go in the relevant `exceptions.py` with class-level `error_domain`/`user_action` so docs pages, `type_uri`s, and RFC 7807 rendering come free.

## 5. Decisions D5–D11 (approved 2026-07-07)

### D5 — The interpretation matrix (the core of the mechanism)

For each provided input with a declared `StuffSpec` (after D2's multiplicity peeling), dispatch on the *declared concept's* nature, not the value's shape:

| Declared concept resolves to | Accepted bare values | Result |
|---|---|---|
| Text-refining (structure class ⊑ `TextContent`) | `str` | Declared concept's structure class instantiated with the text — the Stuff is typed as the *declared* concept |
| Number-refining (⊑ `NumberContent`) | `int`, `float` (NOT `bool` — see D9) | Same, `number` field set |
| Image/Document-refining | `str` (URL/path, D3) or `{"url": ...}`-style dict | Native content class from url |
| Structured (⊑ `StructuredContent`) | `dict` | `structure_class.model_validate(dict)` — pydantic does the real validation |
| `Dynamic` / `Anything` | anything | Fall back to today's bottom-up rules (the signature genuinely doesn't know) |
| YesNo-refining (future, D9 companion track) | `true` / `false` | Typed yes/no content — this row activates when the native `YesNo` concept lands |

Cross-kind mismatches are D4 errors: a string for a Number-refining concept is an error, not a parse attempt (`"42"` stays a string — no coercion across JSON types; JSON already distinguishes). Python-object inputs (`StuffContent` instances, `ListContent`) keep today's behavior, plus the D6 compatibility check.

### D6 — Explicit forms are checked, and explicit wins when compatible

The envelope `{"concept": C, "content": ...}` and direct `StuffContent` objects remain fully supported. Two changes:

- **New check:** the provided/inferred concept must be compatible with the declared concept (`ConceptLibrary.is_compatible(tested=provided, wanted=declared)`), else D4 error. Today there is NO such check — you can feed any envelope concept to any input and nothing notices until something downstream misbehaves. This closes the other half of the silent-mistyping hole.
- **Explicit wins when compatible:** if the caller names a concept that *refines* the declared one (passes `sales.UrgentQuestion` where `legal.Question` is declared... when compatible), the provided, more specific concept is kept on the Stuff. The caller is volunteering information; the signature only sets the lower bound.

Envelope-shape collision rule: a dict whose keys are exactly `{"concept", "content"}` is always read as an envelope, even if the declared structured concept happens to have fields named `concept` and `content`. The escape hatch for that (pathological) structure is the envelope itself: `{"concept": "x.That", "content": {"concept": ..., "content": ...}}`. One deterministic rule, no sniffing.

### D7 — Where the shaper lives (code seams)

- New module `pipelex/core/memory/input_shaper.py` (name open — see §7): a pure function/class taking `(pipeline_inputs, input_specs: InputStuffSpecs, search_domain_codes)` → `WorkingMemory`, built on the existing `StuffContentFactory` / `is_compatible` primitives.
- `WorkingMemoryFactory.make_from_pipeline_inputs` gains an `input_specs: InputStuffSpecs | None = None` parameter; `None` keeps today's bottom-up path (callers that genuinely have no signature).
- `prepare_pipe_job` (`execution_seams.py:198`) passes `pipe.inputs` — the boundary contract, same choice the Optionals code made in the omitted-optional pass right below (`execution_seams.py:226`), NOT `needed_inputs()` (whose aggregation carries children's markers).
- The signature to shape against is the **entry pipe's** declaration only; sub-pipe inputs flow through working memory internally and are never re-shaped.
- CLI relative-path resolution (`_inputs_path_resolver.py`) currently rewrites relative `"url"` values before the library is loaded. With D3, bare strings for file concepts also need resolving — simplest is to move/duplicate path resolution after pipe resolution, or resolve lazily at shaping time by threading the base dir. To be settled at implementation-plan time.

### D8 — Unknown input names are errors

With a signature in hand, a provided name absent from `pipe.inputs` is a **typo detector**: error naming the unknown input and listing the declared ones. Today extras are silently carried in working memory and never read. Risk to weigh: any workflow deliberately over-providing inputs (shared inputs file across several pipes of a bundle?) would break — if that pattern matters, downgrade to a warning. Leaning error (loud beats silent), flagging explicitly because it is the one place smart inputs *narrows* accepted behavior.

### D9 — Booleans: an error today, a native `YesNo` concept as a companion track

There is no boolean native concept today (natives: Text, Number, Image, Document, HTML, TextAndImages, Page, JSON, SearchResult, Dynamic, Anything, Composite), so within Smart Inputs a bare `true` at the top level of an input has no declared target it can satisfy — D4 error mentioning that booleans live inside structured concepts (the structure-field level already has a `boolean` field type). Guards that hold regardless: Python `bool` is a subclass of `int`, so the Number arm must explicitly exclude `bool` before accepting ints; `null` at the top level is an error too — absence is expressed by *omitting* the key (Optionals), not by null.

**Resolution (decided 2026-07-07): the gap is real and gets fixed by a native `YesNo` concept, shipped as its own companion track** (same pattern as the planned DATETIME native concept from the TOML-inputs track — a native concept touches LLM structured output, rendering, schema regen, the MTHDS spec and downstream mirrors, not just inputs). LLM pipelines constantly produce yes/no judgments ("does this contract contain a penalty clause?"), and today authors hack them as `Text` answering "yes"/"no" or a single-field structure.

Naming: **`YesNo`**, chosen over Boolean (geeky), TrueFalse, Logical, Truth, and Checkbox. Precedents from user-friendly language history: Microsoft Access named its boolean field type literally "Yes/No"; Excel calls TRUE/FALSE "logical values" (the Logical function category); Inform 7 calls the type a "truth state"; Airtable/Notion/Salesforce say "Checkbox" (names the widget, not the meaning). `YesNo` reads as "the answer to a yes/no question" — exactly what these values are in LLM pipelines (`output = "YesNo"`), fits the plain-noun native family, and the PascalCase compound follows the TextAndImages precedent.

When `YesNo` lands, the D5 matrix gains a row (YesNo-refining concept + JSON `true`/`false` → typed content) and this D9 error arm narrows to genuinely-unshapeable scalars. Open questions parked for that track: the content class field name (`YesNoContent` following the `NumberContent.number` pattern), rendered_plain as "yes"/"no", whether the lowercase `boolean` structure-field type gains a friendlier alias for consistency, and how PipeLLM generates a `YesNo` output.

### D10 — Protocol widening (MTHDS-brand surface)

`StuffContentOrData` / `PipelineInputs` live in `mthds/protocol/pipeline_inputs.py` — MTHDS-brand, spec territory. The type must widen to admit scalars, lists of dicts, and empty lists; honestly it converges toward "any JSON value | StuffContent forms". The interpretation semantics (this design's matrix) should be spec'd on the MTHDS side (docs/specs + the mthds repo), since signature-driven reading is a property of the protocol's inputs format, not a Pipelex quirk — no `pipelex_` naming anywhere wire-visible. Downstream mirrors (mthds-python, mthds-js `PipelineInputs` types, conformance rows, JSON schema if any) sweep after the pipelex release, same de-gate pattern as Optionals/TOML-inputs.

### D11 — Interactions with adjacent features

- **Optionals:** unchanged. An omitted `?` input still becomes a not-provided absence record; shaping only applies to *provided* values. Presence markers don't affect the interpretation matrix.
- **Mock inputs (dry run):** unchanged; mock filling happens after user-input shaping, on whatever is still missing.
- **CSV tabular inputs:** today the `{"url": "*.csv"}` → `ListContent[rows]` detection requires the envelope (it needs a concept). With shaping, the declared concept powers it: `"people": "people.csv"` (bare string, D3-style) or `"people": {"url": "people.csv"}` under a declared `csv_demo.Person[]` can trigger the CSV reader with no envelope. Nice compounding win; needs the multiplicity-declared arm to try tabular detection before the "string for structured concept" error.
- **TOML inputs (#1022):** nothing format-specific — both parsers produce the same dict; shaping happens downstream of parsing. TOML templates (`--format toml`) simplify identically.
- **Template generation (`pipelex build inputs`):** the **default becomes the light, signature-driven shape** — example *values* shaped like what smart inputs accepts — and the fully ceremonial envelope shape stays available behind a flag (decided 2026-07-07; proposed spelling `--explicit`, matching the docs' "Explicit Format" vocabulary; composes with the existing `--format json|toml`). This flips the default template from "here is the required ceremony" to "here are the values to fill in". One thing the envelope template teaches that the light one loses is *which concept each input expects* — in TOML mode the light template can carry that as comments (`# concept: legal.Question`); JSON has no comments, which is another reason to keep the `--explicit` form around.

## 6. What this deliberately does not do (non-goals)

- **No cross-type parsing.** `"42"` for a Number input is an error; JSON already distinguishes scalars. Smart means signature-driven, not guessy.
- **No LLM in the loop** (v1). See §8.
- **No fuzzy field matching** on structured dicts — pydantic validation semantics as-is (missing required field = error). Field-level aliasing/mapping is exactly where option D would start.
- **No change to outputs** or to how working memory serializes — this is strictly the input boundary.

## 7. Naming

Candidates discussed for the feature name and the mechanism term:

- **Smart Inputs** — feature/marketing name (branch already votes for it). Docs headline: "Smart Inputs — just provide the values."
- **Signature-driven input shaping** — the mechanism term for spec/docs prose; "shaping" says values are molded to a declared shape.
- Also considered: implicit inputs (sounds magic), loose inputs (sounds sloppy), natural inputs, call-site inference (accurate but jargon).

Internal name proposal: `InputShaper` (module `input_shaper.py`). Open to taste.

## 8. Later-phase candidates (design now, ship later)

- **LLM-assisted adaptation (option D).** Opt-in (`--adapt` or similar): when deterministic shaping fails, run a small mapping pipe to convert the provided value into the declared structure (field renaming, unit conversion, free text → structured). Requires clear provenance ("this input was AI-adapted") and probably a dry-run preview. Powerful for agent-facing flows and the webapp uploader.
- **Cross-input file references.** `"contract": "contract.txt"` for a Text-refining input — reading bare strings as *file paths to text* is tempting but ambiguous (is the string the content or a path?). Unlike D3, Text refinements collide head-on with literal strings. Any design here needs an explicit marker (e.g. `{"path": ...}`) rather than sniffing. Parked.
- **Defaults / coalescing.** Input-level defaults belong to the Optionals phase-2 `??` track (see `wip/optionals/optionals-design.md` §15), not here — noted only because both features touch "what happens when the caller provides less".

## 9. Surfaces impacted (checklist for the future plan)

- `pipelex/core/stuffs/stuff_factory.py`, `stuff_content_factory.py` — shaping primitives; keep bottom-up path for the no-signature/Dynamic fallback.
- New `pipelex/core/memory/input_shaper.py` (or similar) + `WorkingMemoryFactory.make_from_pipeline_inputs(input_specs=...)`.
- `pipelex/pipeline/execution_seams.py` `prepare_pipe_job` — pass `pipe.inputs`.
- `pipelex/cli/commands/run/_inputs_path_resolver.py` — bare-string path resolution for file concepts (D3/D7).
- New error classes in the relevant `exceptions.py` + regenerated error pages (`make gep`).
- `pipelex/core/pipes/inputs/input_renderer.py` + `pipelex build inputs` / `pipelex-agent inputs` CLIs — light templates by default, `--explicit` flag for the envelope form, concept comments in TOML mode (D11).
- Companion track (separate design): native `YesNo` concept (D9) — NativeConceptCode entry, content class, structure-generator mapping, LLM output support, schema regen + mthds spec + downstream mirrors.
- Protocol: `mthds` `pipeline_inputs.py` widening + spec section; downstream mirrors gated on release (D10).
- Docs: `docs/building-methods/pipes/provide-inputs.md` rewrite (it shrinks dramatically), `docs/tools/cli/run.md`, `build/inputs.md`, agent CLI docs.
- Tests: unit (shaping matrix, one test class per arm), e2e (bare-values inputs file through `pipelex run`), error-message snapshots for D4.
- Skills: `mthds-inputs` skill (mthds-plugins) — post-release sweep with the rest of the cross-repo wave.
