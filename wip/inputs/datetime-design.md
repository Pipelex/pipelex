# Datetime track — a native `Date` concept: design proposal

Status: **design approved — all decisions DT1–DT8 approved by Louis 2026-07-07**. Companion track to `YesNo` (smart-inputs-design.md §D9), step 2 of the execution order in this folder's `README.md`. Time-boxed and abandonable by design: every decision below is severable, and the whole track can stop at any point without blocking YesNo or Smart Inputs. Implementation plan: `datetime-implementation-plan.md`.

## 1. What this must deliver, and the bar it must clear

Three concrete jobs:

- **Retire the TOML rejection.** Since TOML inputs (#1022), TOML's native date/datetime/time literals are rejected wholesale by `InputsDatetimeNotSupportedError` (`pipelex/cli/commands/run/_inputs_file_loader.py:111`) with "quote it as a string in the meantime". The meantime ends here.
- **Give the native family a temporal concept.** Dates are arguably the most common typed value on the documents Pipelex methods read — contracts (effective date, termination date), invoices (issue date, due date), tickets (departure), certificates (date of birth). Today authors model them as `Text` or as a `date` structure field; there is no concept-level citizen.
- **Ready the Smart Inputs matrix row.** The D5 interpretation matrix gains a temporal row when this lands (purely additive).

The bar, per Pipelex's identity: the concept must read like something found *on a document*, not in a type system — non-tech authors write `output = "Date"` the way they'd label a column in a spreadsheet. And it must be LLM-native: an agent reading the concept must know instantly what to write, and a PipeLLM constrained to produce it must never be *forced by the schema* to state more than the source document states.

## 2. The central question: one concept or three?

TOML distinguishes four temporal literals (offset date-time, local date-time, local date, local time); Python/pydantic/JSON-Schema split the family into `date`, `time`, `date-time`. The programming answer is therefore "three concepts". We propose the document answer instead: **one**.

**The document test.** Walk the documents Pipelex is built for. A contract says "Effective Date: March 1, 2026". An invoice says "Due date: 2026-08-06". A plane ticket says "Departure: 7 Jul 2026, 15:40". A meeting invite says "Date & time: July 7 at 3:00 PM CET". In plain speech every one of these is *a date* — sometimes with a time, sometimes without. Nobody reading a ticket says "the departure datetime". A time alone, unmoored from any date ("opening hours: 9:00"), is comparatively rare and is not the same kind of thing — it's a recurring time-of-day, not a point in history.

**The LLM-fidelity test — the decisive argument.** Suppose we shipped separate `Date` and `Datetime` concepts. The author of an extraction pipe must now *predict the precision of documents they haven't seen*. Declare `output = "Datetime"` and the document says "delivery by March 15": constrained generation forces the model to fabricate a time — you get `2026-03-15T00:00:00`, hallucinated precision that propagates downstream looking exactly like real data. Declare `Date` and the document carries a full timestamp: the time is silently discarded. Both failure modes are structural — no prompt engineering fixes a schema that demands more (or less) than the source states. A single concept with an *optional* time component makes both failure modes unrepresentable: the LLM states the date, adds the time only when the source has one, and the output's precision *is* the document's precision.

**Precedents from user-friendly systems** (same lineage as the YesNo naming research): Notion's property is "Date" and optionally includes a time; Google Calendar events have a date and optionally a time (all-day vs timed — same model); Airtable's "Date" field has an "include time" toggle; Access says "Date/Time" as one type. The tools built for non-programmers converged on exactly this shape: one thing called a date, time optional.

**Rejected alternatives:**

- **Three natives (`Date`, `Time`, `Datetime`)** — maximal fidelity to TOML/stdlib, but two of the three earn almost nothing on real documents, the native family is precious real estate (every agent holds the whole list in mind), and the author-must-predict-precision trap remains.
- **Two natives (`Date` + `Datetime`)** — the conventional programming compromise; still has the fabricated-midnight trap, still forces a choice the author can't reliably make, and "Datetime" is database lingo on a surface that speaks contract-and-invoice.
- **One native named `Datetime` with required time** — the name fails the plain-language test and the required time fails the fidelity test.
- **One native, time always optional, named `Date`** — **proposed.**

What we give up: time-of-day alone has no native home (TOML local-time literals stay rejected, with a narrowed message — see DT5). If demand materializes, a `Time` native can be added later without disturbing anything decided here.

## 3. The shape at a glance

```toml
[concept.DueDate]
description = "The date payment is due"
refines = "Date"

[concept.Departure]
description = "The scheduled departure of the flight"
refines = "Date"

[pipe.extract_departure]
type = "PipeLLM"
description = "Extract the departure from the ticket"
inputs = { ticket = "Ticket" }
output = "Departure"
prompt = """Extract the scheduled departure from this ticket: @ticket"""
```

The LLM sees a schema with a required `date` and an optional `time`, each field description telling it to state only what the source states. From a ticket it produces `{"date": "2026-07-07", "time": "15:40:00"}`; from "delivery by March 15" it produces `{"date": "2026-03-15", "time": null}` — no fabricated midnight.

On the inputs side, TOML literals just work:

```toml
# inputs.toml
hearing_date = 2026-09-01            # a Date — date only
departure = 2026-07-07T15:40:00+02:00  # a Date — with time and offset, faithfully kept
```

## 4. Proposed decisions

### DT1 — One native concept, named `Date`

`NativeConceptCode.DATE = "Date"`, concept ref `native.Date`, description: *"A calendar date, optionally with a time of day — as precise as its source states."* One new native, not two or three (§2). The track keeps its colloquial "Datetime" name in the roadmap; the concept an author sees is `Date`.

Breaking consequence (native codes are reserved): a bundle declaring its own `[concept.Date]` becomes an error. Workspace grep across every repo finds no such concept today. Changelog: breaking.

### DT2 — Content shape: `DateContent` with `date` + optional `time`

```python
class DateContent(StuffContent):
    date: datetime.date
    time: datetime.time | None = None
```

Follows the `NumberContent.number` field-naming pattern. The UTC offset, when the source states one, rides on the `time` field's `tzinfo` — pydantic parses and serializes `"15:40:00+02:00"` natively. This makes the invalid states unrepresentable by construction: no time without a date, no offset without a time (a calendar date alone has no meaningful offset). Field descriptions on the class carry the anti-fabrication instruction ("include the time only when the source states one — never invent a time"), which flows into `model_json_schema()` and is therefore inherited by every refining concept's LLM generation for free.

Helpers kept minimal for core scope: a `to_datetime()` method for Python consumers that need a `datetime.datetime` (behavior when `time is None` — raise vs midnight-default — settled at implementation-plan time; leaning raise, so nobody gets a silent midnight). No comparison/arithmetic surface (non-goal).

### DT3 — Timezone policy: fidelity, not normalization

The concept stores **what the source states — never more, never less**. Offset present in the source → preserved verbatim; absent → naive time, and nothing downstream invents one. No normalization to UTC at the concept level: converting timezones is a *computation*, i.e. a pipe's job, not a data type's. Offsets only, no named-timezone (IANA) support: names require DST arithmetic and a tz database, and the sources we read (ISO strings, TOML literals) carry offsets, not names. "3 PM Paris time" extracts as a naive 15:00 plus whatever the prompt asks for — resolving it to an offset is an explicit pipe step if a method needs it. The naive-vs-aware question dissolves: both are valid states of the same concept, distinguished by what the document said.

### DT4 — Rendering: ISO 8601, truncated to stated precision

`rendered_plain` / `rendered_markdown` / `rendered_html` render the ISO 8601 form of exactly what is stored: `2026-07-07`, `2026-07-07T15:40:00`, `2026-07-07T15:40:00+02:00`. ISO is locale-free, unambiguous, and the temporal notation LLMs know best — this is what a prompt sees when a `Date` input is inserted via `@var`/`$var`. `rendered_json` mirrors the two-field structure (`{"date": ..., "time": ...}`). `short_desc`: "a date (2026-07-07)" / "a date and time (2026-07-07T15:40:00+02:00)". Structured concepts already render embedded dates as ISO (`html_rendering.py:53`), so this is consistent with existing behavior. Human/locale-friendly formatting ("July 7, 2026") is presentation, deliberately left to Jinja filters or downstream renderers — never the concept's job.

### DT5 — Inputs behavior in core scope (pre-Smart-Inputs)

This track ships before signature-driven shaping, so it extends today's bottom-up rules:

- **TOML date and datetime literals map natively.** `tomllib` yields real `datetime.date` / `datetime.datetime` objects; the loader's rejection walk stops rejecting them. Bottom-up: a bare `datetime.date`/`datetime.datetime` value becomes a `native.Date` stuff (mirror of "bare string becomes `native.Text`") — `StuffFactory` gains the arm, `StuffContentFactory.make_content_from_value` gains the `DateContent` special cases (date object, datetime object, ISO string, `{"date","time"}` dict).
- **TOML local-time literals stay rejected**, with a narrowed error: a time without a date is not a `Date`. The error class survives with a scoped-down name/message (detail for the plan; message should say "a time of day alone has no date to attach to — include the date or quote the value as a string").
- **JSON bare strings are NOT sniffed.** A top-level `"2026-07-07"` in `inputs.json` stays `Text` under bottom-up rules — guessing "ISO-looking string means date" is exactly the guessy behavior the Smart Inputs non-goals forbid. JSON callers reach `Date` via the envelope (`{"concept": "Date", "content": "2026-07-07T15:40:00"}`) until Smart Inputs lands, at which point the declared signature does it (DT6).
- **Python API** accepts `datetime.date` / `datetime.datetime` objects directly, same mapping.

### DT6 — The Smart Inputs matrix row (forward note, lands with that feature)

When signature-driven shaping ships, the D5 matrix gains: *Date-refining concept (⊑ `DateContent`)* ← accepted bare values: ISO 8601 `str` (strict — pydantic parsing, no loose formats, no "March 7"), `datetime.date` / `datetime.datetime` objects (TOML/Python), `{"date": ..., "time": ...}` dict. Explicitly rejected: `int`/`float` (no epoch-seconds interpretation — pydantic's lenient number-to-datetime coercion must be disabled, the temporal cousin of the bool-is-not-int guard in D9). ISO-string acceptance here is not cross-type parsing in the forbidden sense: JSON has no temporal type, the string is the only possible carrier, and the declared signature is what disambiguates — the same logic that lets D3 read bare strings as URLs for file concepts.

### DT7 — LLM output: rides the object path day one; ergonomics deferred with YesNo's

`PipeLLM` with a non-Text output already ships the content class's `model_json_schema()` to the LLM (`assignment_models.py:95`), so `output = "Date"` works from day one: the model sees `{date: string/format=date, time: string/format=time | null}` plus the DT2 field descriptions. No special generation path in core scope. Whether scalar-wrapper natives deserve a leaner generation form (the cousin-of-maybe-wrapper question) is already parked as the YesNo LLM-output-ergonomics follow-up — `Date` joins that same follow-up rather than opening its own. Note: `Date` has an easier ride than `YesNo` here, because its object form is genuinely two fields, not a wrapped scalar.

### DT8 — Fix the `date` structure-field misnomer (severable adjacent cleanup)

Discovered while grounding this design: the structure-field type `date` (`ConceptStructureBlueprintFieldType.DATE`) maps to Python `datetime.datetime` (`structure_generation/generator.py:375`), whose JSON schema is `format: date-time`. So **every cookbook extraction with a `type = "date"` field (invoice dates, DPE dates) already forces the LLM to fabricate a time of day today** — the field-level version of the exact hallucination this design eliminates at concept level. Proposed fix, aligned with the no-backward-compat principle: field type `date` maps to `datetime.date` (what the name says), and a new field type `datetime` maps to `datetime.datetime` for the rare field that genuinely wants a timestamp. Touches the generator's two mapping sites, the blueprint default-value validator (`concept_structure_blueprint.py:180` currently checks `isinstance(..., datetime)`), the line-64 TODO, schema regen, and docs (`inline-structures.md`). Breaking for any method that relied on `date` fields carrying time — workspace usages all name calendar dates and would *improve*. Severable: ships as its own commit in the same wave, and dropping it doesn't dent DT1–DT7. An alternative field-level design — making `date` fields carry the DT2 composite — is rejected: structure fields are plain machine types by design; a field wanting document-fidelity semantics can be `type = "concept", concept_ref = "Date"`.

## 5. Non-goals

- **No `Time` native.** Time-of-day alone (opening hours) has no native home; degrade to Text or a structure field. Add later if real demand appears.
- **No partial dates.** "March 2026", "Q3" are not representable — the precision floor is a full calendar date. Anything fuzzier is `Text` or a domain-structured concept (the EDTF rabbit hole stays closed).
- **No durations or relative dates.** "Net 30 days", "next Tuesday" are different concepts (a future `Duration` native is imaginable; not now).
- **No named timezones, no DST math, no normalization** (DT3).
- **No locale rendering** (DT4) and **no comparison/arithmetic surface** on the concept.

## 6. Core-scope surfaces checklist (for the implementation plan)

- `pipelex/core/concepts/native/concept_native.py` — `DATE = "Date"` + arms in the four exhaustive matches (`structure_class`, `is_composite`, `is_text_concept`, `is_dynamic_concept`).
- New `pipelex/core/stuffs/date_content.py` — `DateContent` per DT2/DT4.
- `pipelex/core/registry_models.py` — register `DateContent` in `CoreRegistryModels.STUFF`.
- `pipelex/core/concepts/concept_factory.py` — `case NativeConceptCode.DATE:` arm with the DT1 description.
- `pipelex/core/stuffs/stuff_factory.py` + `stuff_content_factory.py` — bottom-up arms per DT5.
- `pipelex/cli/commands/run/_inputs_file_loader.py` + `run/exceptions.py` — narrow the rejection to time-only per DT5; update both catch sites' expectations; regen error pages (`make gep`).
- Dry-run mock filling — verify the mock path in `working_memory_factory.py` can synthesize a `Date` (likely free via the registry; confirm at plan time).
- DT8 (severable): `concept_structure_blueprint.py`, `structure_generation/generator.py`, docs.
- Schema regen (`pipelex-dev generate-mthds-schema`) — note the native ref itself doesn't change the schema shape; DT8 does (field-type enum).
- Docs: `docs/building-methods/concepts/native-concepts.md` table entry; inputs docs mention of TOML literals; `inline-structures.md` if DT8 ships.
- Tests: content-class unit tests (render matrix, offset round-trip), inputs-loader tests replacing the four-flavor rejection parametrization (date ✓, local datetime ✓, offset datetime ✓, local time ✗ narrowed), e2e `.mthds` with TOML date inputs, LLM-output smoke via existing structured-gen harness.
- Downstream wave (per-release, shared with YesNo/Smart Inputs): MTHDS spec native table (`mthds/docs/language/concepts.md`, `spec/mthds-format.md`), schema sync, mthds-python/mthds-js mirrors, conformance, skills, editor tooling completion lists.

## 7. Abandonability check

The README's standby clause holds. DT1–DT4 are one enum value, one small class, one factory arm — the irreducible core. DT5 is the payoff (retires the shipped error) but degrades gracefully if dropped (the error simply keeps telling users to quote strings). DT6 belongs to Smart Inputs anyway. DT7 costs nothing. DT8 is explicitly severable. If the composite-content semantics (optional time, offset-on-time) turn out to fight the machinery anywhere — mock filling, kajson round-trips, schema emission — the track stops, nothing else on the train is blocked, and this document records where it stopped and why.
