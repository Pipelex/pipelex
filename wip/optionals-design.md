# Optionals in the MTHDS conceptual typing system — design choices

Status: design proposal, no code written. Branch `feature/Optionals`. This document gathers the design space for adding optionality (`?`) to concept refs, presents each decision with options and consequences, and marks a recommendation for each. Decisions are numbered D1–D10 and summarized at the end.

Decision status (2026-07-03, Louis): **all open questions resolved** — D3 implicit lifting, D4 `?` forbidden on plurals, `continue` = "declared output absent" (§14), naming (`!` = force marker, `?` pronounced "optional"), and D6 lints via a general `warnings` array on the validation report (bundled into the same protocol bump as the `optional` flag). The design is ready for implementation planning.

## 1. The problem

MTHDS can express *how many* values flow through a slot (`contracts.PenaltyClause[]`) but not *whether* a value flows at all. Every declared input is unconditionally required and every declared output is unconditionally produced. Real methods constantly need "maybe there is no value", and today authors work around it in four ways, all bad:

- **The empty-string hack.** A required structured field whose description says "empty string if full match" (seen verbatim in the cookbook's `rfp_qualifier`: `gap_description = { ..., description = "... empty string if partial or no match, empty string if full match", required = true }`). The type system says "always a value"; the prompt smuggles in the absence convention. Downstream pipes must know the convention to test for it.
- **Hallucination pressure.** "Extract the penalty clause" with `output = "PenaltyClause"` gives the model no way to say "there isn't one" — the schema demands a value, so the model invents one. This is the single worst failure mode: it is silent and it is wrong.
- **The invisible optional in `PipeCondition`.** An outcome mapped to `continue` returns working memory unchanged and produces *no* output — a de-facto optional that the type system cannot see. Validation runs all branches during dry run and never models the "produced nothing" path, so nothing downstream is checked against it.
- **The cosmetic `@?`.** The prompt sigil `@?var` (→ `{% if var %}{{ var|tag("var") }}{% endif %}`) says "render only if present", but the variable detection still counts it as a required input, and the runtime gate (`validate_before_run`) still hard-fails when it is missing. The author can express optional *rendering* but not optional *presence*.

And when a value genuinely is missing at run time, the user gets one of: a generic `PipeRunInputsError` (whose message says "Dry run of ..." even on live runs — pre-existing bug, `pipe_abstract.py:349`), a `WorkingMemoryStuffNotFoundError` listing valid keys, or a Jinja `UndefinedError` from deep inside template rendering. None of them can say *why* the value is absent, because absence is not a modeled fact — it's just a missing dict key.

Swift's optional model is the guide: declare with `?`, chain with `?`, force with `!`, all checked at compile time so `nil` never surprises you at run time. The translation problem is that MTHDS is declarative and high-level: there is no expression context in which to write `a?.b`, no `if let` statement. The unwrapping constructs must live where MTHDS authors already work — input/output declarations, prompts, and controllers — and the "compile time" is our validation engine.

## 2. Recommended shape at a glance

Before the decision grind, here is the full recommended design on the running example, so the taste is visible end-to-end:

```toml
[pipe.extract_penalty_clause]
type = "PipeLLM"
inputs = { contract = "contracts.Contract" }
output = "contracts.PenaltyClause?"          # NEW: this pipe may legitimately find nothing
prompt = """Extract the penalty clause from this contract, if there is one.
@contract"""

[pipe.assess_penalty]
type = "PipeLLM"
inputs = { penalty_clause = "contracts.PenaltyClause" }   # plain required input
output = "contracts.PenaltyAssessment"
prompt = """Assess the severity of this penalty clause. @penalty_clause"""

[pipe.write_report]
type = "PipeLLM"
inputs = { contract = "contracts.Contract", assessment = "contracts.PenaltyAssessment?" }  # NEW: absorbs absence
output = "contracts.ContractReport"
prompt = """Write a contract report.
@contract
@?assessment"""
```

Semantics, in order:

- `extract_penalty_clause` declares an **optional output**. The runtime gives the LLM an explicit way to answer "no penalty clause" (a maybe-wrapper schema carrying a reason), and when it does, the slot is recorded as **absent with provenance** ("no penalty clause found in this contract") instead of holding a hallucinated value.
- `assess_penalty` declares a plain required input fed by a maybe-absent slot. It is **lifted**: when the clause is absent, the pipe is *skipped* and its own output is recorded absent, provenance chaining back to the extraction. This is Swift's `a?.b` — write `?` once where absence enters; the chain short-circuits.
- `write_report` declares an **optional input** (`?`): it runs regardless, and its prompt handles both arms via `@?assessment`. This is where the absence chain terminates — the explicit sink.
- Validation proves the whole thing: every slot that may be absent must terminate in an explicit sink (an optional input, a forced input `!`, or an optional method output), or the bundle is invalid. Absence can never silently reach a consumer that doesn't expect it.
- If the author instead writes `penalty_clause = "contracts.PenaltyClause!"`, absence becomes a **typed runtime failure** whose report names the variable, the consuming pipe, the producing pipe, and the model's stated reason for the absence.

## 3. Three kinds of "nothing" — and which one this is

The design must not blur three distinct notions, two of which already exist:

| Notion | Where it lives | Existing? | Example |
|---|---|---|---|
| Field-level null | Inside a structured content: `required = false` → generated `Optional[T] = None` | Yes | `notes` field of an Invoice is `None` |
| Plural emptiness | A list slot with zero items: `ListContent(items=[])` | Yes | Extraction found no requirements → `RFPRequirement[]` is empty |
| Slot absence | A named slot in working memory has **no Stuff at all** | **New** | No penalty clause → no `PenaltyClause` stuff exists |

`?` is about the third notion only. Concepts themselves stay total and singular — the existing multiplicity philosophy ("concepts are always singular; multiplicity is a property of the flow") extends naturally: **concepts are always present; presence is a property of the slot.** So `?`, like `[]`, is legal only where slots are declared (pipe `inputs` and `output`), never on concept definitions, `refines`, `concept_ref`/`item_concept_ref` structure fields, or package export lists.

## 4. The Swift dictionary

| Swift | MTHDS analog | Phase |
|---|---|---|
| `T?` declaration | `output = "X?"` / `inputs = { v = "X?" }` | 1 |
| `nil` | Absent slot, recorded with provenance in working memory | 1 |
| `a?.b.c` optional chaining | Lifting: a pipe with a plain required input fed by a maybe-absent slot is skipped, its output becomes absent (D3) | 1 |
| `x!` force unwrap | `inputs = { v = "X!" }` → typed runtime error if absent | 1 |
| Function taking `T?` | Optional input `X?`: pipe runs, handles absence itself (prompt guards) | 1 |
| `if let` / `guard let` | `@?var` and `{% if var %}` in prompts; PipeCondition branching on presence | 1 (idiom), 2 (sugar) |
| `?? default` | Input defaults / fallback values | 2 |
| `try?` (error → nil) | `on_error = "absent"` on a pipe with optional output | 2 |
| `compactMap` | PipeBatch whose inner pipe has optional output → absences dropped from result list | 1 or 2 |

## 5. D1 — Grammar: where `?` and `!` may appear

The suffix grammar becomes:

```
io_ref   := concept_ref_or_code marker?
marker   := "[]" | "[" digits "]" | "?" | "!"     # v1: markers are mutually exclusive
```

- `?` is legal on pipe **inputs and outputs** (blueprints and specs), and therefore on method signatures (a method is a pipe).
- `!` is legal on **inputs only** — it is a use-site assertion, not a type. `!` on an output is meaningless (a producer doesn't unwrap anything) and is a grammar error.
- In v1, `?` may not combine with `[]`/`[N]` — see D4. If we ever allow it, the order is fixed: multiplicity then presence (`X[]?`), read "the list slot may be absent".
- `?` and `!` never appear in concept definitions, `refines`, structure-field `concept_ref`s, or `METHODS.toml` refs. Package-layer parsers (`qualified_ref` in pipelex, mthds-js, mthds-python) never see them.

Consequences: the change concentrates in the multiplicity parser (`variable_multiplicity.py` — one regex plus its inline twin), the looser input-factory regex, and the naive `[`-splitter in `concepts/helpers.py` which today would silently pass a `?` through. While touching this file, fix the `MUTLIPLICITY_PATTERN` typo (rename to `MULTIPLICITY_PATTERN`).

An alternative considered and rejected: expressing optionality as an expanded input table (`penalty = { concept = "PenaltyClause", optional = true }`) instead of a suffix. It avoids grammar changes but breaks symmetry with `[]`, is far more verbose, requires inventing an expanded input form that doesn't exist today, and gives outputs no way to be optional at all. The suffix is the design the user asked for and the right one; the expanded form can arrive later for defaults (D10) without conflict.

Naming (DECIDED 2026-07-03): `?` is the **optional marker**, pronounced "optional" (consistent with the `@?` sigil); `!` is the **force marker** (Swift-familiar). These are the terms the spec, docs, error messages, and skills use.

## 6. D2 — What absence *is* at runtime

Options:

- **A. Absent key + absence ledger (recommended).** Absence stays what it mechanically is today — no Stuff under that name — but becomes a *recorded fact*: working memory gains a small side-table of `AbsenceRecord`s (`variable_name`, `producing_pipe`, `kind` = declared-absent | skipped | not-provided, `reason`, and the upstream record it chains to). A pipe that produces absence writes a record instead of a Stuff. `get_optional_stuff` and the run report can then distinguish "declared absent, here's why" from "never produced — that's a bug".
- **B. Sentinel Stuff (present key, null content).** Make `Stuff.content` nullable or introduce an `AbsentContent`. Rejected: it breaks the strongest invariant in the content model (`Stuff.content` is never None, every accessor assumes it), leaks nulls into templates and the wire, and forces every operator to check for the sentinel. All cost, no benefit over A.

Consequence of A: the wire format for run results needs an explicit representation of absence (D8), because "key missing from the output dict" must now be readable as "absent by design, reason attached" rather than ambiguous. The ledger is also what makes the failure UX (D9) possible — provenance is captured at the moment absence is produced, not reconstructed at failure time.

## 7. D3 — Consuming an optional: the central decision

A slot is **maybe-absent** if it is fed by an optional output, by a liftable (skippable) pipe, or is an optional method input. What may a downstream pipe's input declaration say about such a slot?

The recommended model is a trichotomy on the input marker:

| Input form | Static rule when fed maybe-absent | Runtime behavior when actually absent | Swift analog |
|---|---|---|---|
| `v = "X"` (plain) | Allowed; the pipe becomes *liftable* and its output maybe-absent (taint propagates) | Pipe is **skipped**; absence recorded with provenance "skipped because v absent ← ..." | `a?.b` chaining |
| `v = "X?"` (optional) | Allowed; taint **terminates** here | Pipe **runs**; templates see the var as absent and must guard (D7) | function taking `T?` |
| `v = "X!"` (forced) | Allowed; taint terminates here | Pipe would run, but absence raises a typed error carrying the provenance chain | `x!` |

And the safety theorem validation enforces: **every absence source must reach an explicit sink** (`?` input, `!` input, or a `?` on the enclosing method's declared output). If taint reaches a non-optional method output or otherwise escapes unhandled, validation fails with a dedicated error naming the source, the path, and the three ways to fix it.

**DECIDED 2026-07-03: implicit lifting approved** — chosen for user-friendliness. Consequence: the mitigations listed below (liftable-pipe visibility in the validation report, skipped-node rendering in the graph, run-report skip reasons) are commitments of phase 1, not optional extras.

Why implicit lifting for plain inputs (rather than Swift's "consuming an optional without unwrapping is a compile error"):

- It matches Swift more closely than it first appears: in `a?.b.c.d`, you write `?` exactly once — at the point absence enters — and `.b.c.d` are *implicitly* conditional. The MTHDS equivalent of that single `?` is the optional output declaration upstream; the pipes in between are the `.b.c.d`.
- It is what a high-level declarative language should do: "no penalty clause → no severity assessment" is the obviously-intended semantics, and demanding a marker on every intermediate pipe turns a one-decision design into annotation churn.
- It keeps pipe signatures reusable. `assess_penalty : PenaltyClause → PenaltyAssessment` stays a total, non-optional pipe; the *flow context* lifts it. The same pipe used in a flow where the clause is guaranteed present is not polluted by optional markers it doesn't need. (This is precisely functorial lifting: the chain applies `(T → U)` to a `T?` and gets a `U?`.)
- The escape hatches are exactly where Swift puts them: `!` to assert, `?` to absorb.

The honest counter-argument: implicit skipping is action-at-a-distance. An author who *didn't intend* their pipe to be skippable might be surprised a step didn't run. Mitigations, in order of importance: (1) the taint can never appear out of nowhere — some upstream author wrote an explicit `?`, and the sink is also explicit, so the skip zone is bracketed by visible markers; (2) the validation report lists every liftable pipe ("may be skipped when X is absent"), so it is visible at build time, not just run time; (3) the run report and graph render skipped pipes distinctly (D8/D9). If we still find this too implicit in practice, the strict alternative below is a compatible tightening (it turns silently-allowed cases into errors), so starting permissive does not paint us into a corner — whereas starting strict and loosening later would churn every method written in between.

Rejected alternatives:

- **Strict-explicit (Swift-literal).** Plain `X` fed by maybe-absent = validation error; author must write `?`, `!`, or a new chain sigil on every consuming input. Consequence: mid-chain noise, and the "chain sigil" would have to be invented (a third marker meaning "skip me", distinct from `?` which means "run me") — three markers where the trichotomy needs two.
- **Error-only (no skip at all).** `?` inputs and `!` are the only consumers; feeding maybe-absent into plain `X` is an error. Consequence: every pipe downstream of an extraction must guard its prompt for a value that, when absent, makes the pipe pointless. Authors would immediately ask for skip; PipeCondition + `continue` boilerplate would proliferate.

One more rule: an input may declare `?` even when fed by a guaranteed-present slot (over-tolerance is allowed, exactly as Swift lets you pass a `T` where `T?` is expected). This matters for signature stability — a reusable pipe can declare tolerant inputs without caring what feeds it. `!` on a guaranteed slot is statically useless; recommend allowing it silently in v1 (a future advisory channel can lint it, D6).

## 8. D4 — Optionals and plurals

Should `X[]?` exist? The distinction it would encode is "the list step was skipped" vs "the list step ran and found nothing". Options:

- **A. Forbid `?` on plural refs; absence of a plural normalizes to the empty list (recommended).** `[]` already has a perfectly good "nothing": empty. When a pipe with plural output is skipped by lifting, the runtime writes an **empty ListContent** (plus an absence-flavored note in the ledger for observability) rather than an absent slot. Taint stops there: downstream batch over it runs zero branches (already today's clean behavior), downstream prompts see an empty list.
- **B. Allow `X[]?` as a distinct state.** Two kinds of nothing for every plural slot; every consumer must consider both; PipeBatch needs an absent-vs-empty policy; templates need to distinguish undefined from empty. High complexity, and the "skipped vs empty" signal is preserved anyway in the ledger and the graph without needing a type-level distinction.

**DECIDED 2026-07-03: option A** — `?` forbidden on plurals; the empty list does the job. It yields a pleasing symmetry: `?` is the absence story for singulars, `[]`-emptiness is the absence story for plurals, and the two never stack. Corollary: `!` on plural inputs is also forbidden (there is nothing to force).

Bonus primitive that falls out: **PipeBatch whose inner pipe has optional output performs compaction** — absent branch results are dropped, so the batch output is `X[]` containing only found items (Swift's `compactMap`). The existing `build_or_skip`-inside-batch test pattern (condition routing rejects to `continue`) is exactly this, done by hand today; optionals make it typed. Whether compaction ships in phase 1 or 2 is a scoping call — the semantics should be fixed now.

## 9. D5 — Producing absence: which pipes can declare `output = "X?"`

Grammar-wise, allow `?` on any pipe's output (uniformity; over-claiming optionality is harmless and preserves signature evolution room — a method may declare `X?` to reserve the right to return absence later). Semantically, absence is actually *produced* in these ways:

- **PipeCondition with special outcomes.** If any outcome maps to `continue` (or `default_outcome = "continue"` is reachable), the declared output MUST be `X?` — this makes today's invisible optional explicit, and validation finally models the no-output path. This is the cleanest immediate win of the whole feature. (Interaction with the required-main-stuff invariant: see §14.)
- **PipeLLM / structured generation with a maybe-wrapper.** When `output = "X?"`, the response schema becomes a wrapper the model can decline through: conceptually `{ found: bool, reason_if_absent: str, value: X | null }` (instructor's `Maybe` pattern). `found = false` → absence record carrying the model's stated reason. This kills the hallucination pressure *and* harvests the reason that makes downstream error messages excellent. For non-structured text outputs (`Text?`), the same wrapper applies. The exact wrapper shape and prompt scaffolding is an implementation detail of the operator, invisible in the `.mthds` surface.
- **Lifted (skipped) pipes** — absence propagates per D3, no declaration needed on the intermediate pipe itself (its declared output stays total; effective optionality is computed).
- **Optional method inputs** — a caller may omit `v = "X?"` from `inputs.json` / the execute request; the slot starts as recorded-absent ("not provided by caller") instead of raising `PipeRunInputsError`.

Note the asymmetry with intermediate pipes: *method-boundary* signatures (the top-level pipe's inputs/output, anything exported/signature-matched) must be explicit about optionality — that's the API contract, and `contract_match` canonicalization must compare presence markers. *Internal* step-to-step effective optionality is inferred. Explicit at boundaries, inferred locally — same balance Swift strikes between API signatures and local type inference.

## 10. D6 — Static validation: the taint pass

The validator gains an absence-propagation pass over each controller's dataflow, computing per-slot presence: `guaranteed` or `maybe-absent`, using exactly the bookkeeping that already exists (`PipeSequence.needed_inputs`'s `generated_outputs` set is where "produced upstream" is tracked; it gains a presence dimension). Checks, all static:

- Optional output feeding the checks in D3's matrix (nothing to check — every arm is legal; the *pipe-level* results are recorded for reporting).
- Taint reaching a non-optional method output, sequence output, or other boundary → **error** (`OPTIONAL_NOT_HANDLED`, a new `PipeValidationErrorType`), message naming the absence source, the propagation path, and the three fixes (`?` the output, `!` an input, absorb with a `?` input).
- `continue`-reachable PipeCondition without `?` output → error (`OPTIONAL_OUTPUT_REQUIRED`).
- `?`/`!` grammar misuse (on plurals, on outputs for `!`, on `refines`...) → error at blueprint parse (`OPTIONAL_MARKER_INVALID`).
- Optional input referenced unguarded in a template → see D7.

New error types flow automatically through the existing machinery (`build_validation_error_items` → agent CLI JSON/markdown, API 422, conformance) — the plumbing is already unified; we add enum values, fixtures, and conformance rows, not new channels.

Two sub-decisions:

- **Dry-run modeling.** v1: keep the dry run all-present (mock every input, including optional ones) and rely on the static taint pass for the absent arm. Alternative: dual-arm dry run (a second pass with all optionals absent) — better coverage of skip paths and template guards, but doubles dry-run cost and requires the skip machinery to run under DRY. Recommend static-only in v1, dual-arm as a follow-up if the static pass proves insufficient.
- **Advisory channel.** Some findings are lints, not errors: `!` on a guaranteed slot, `?` output on a pipe that can never produce absence. The validation report is binary today; the only advisory precedent is `pending_signatures`/`is_runnable`. Options: (a) mirror that pattern with a dedicated `optionality_notes` list; (b) add a general `warnings` array to the report (protocol change, conformance impact, but the right long-term shape); (c) stay silent on lints in v1. **DECIDED 2026-07-03: option (b)** — a general `warnings` array (same item shape as errors, never flips `is_valid`), bundled into the same protocol bump that adds the `optional` flag to IO contracts, so one bump covers both. Note the split with the *factual* liftable-pipe inventory ("pipe X may be skipped when Y is absent"), which is dataflow information, not a lint — it ships as structured data on the valid report (beside `pipe_io_contracts`), per the D3 implicit-lifting commitment.

## 11. D7 — Prompts and templates: what the author sees

When an optional input is absent, what does the Jinja context contain? Options:

- **A. Nothing — the variable is undefined (recommended).** `{% if var %}` and `@?var` work (falsy), `{{ var }}` renders empty, and a *deep* unguarded use (`{{ var.amount }}`) raises — loud, which is what we want, but today it surfaces as a raw `Jinja2TemplateRenderError`. Pair with the static guard-lint below so authors rarely meet that error.
- **B. A well-behaved `Absent` object** (falsy, chains safely, renders empty — a ChainableUndefined flavor). Everything renders silently; nothing ever fails. Rejected: silence hides bugs — an unguarded `{{ var.amount }}` producing empty prose *changes the prompt's meaning* without anyone noticing. Swift taste says absence misuse should be loud.

The static companion (this is what makes A safe): validation lints that every template reference to a declared-optional input is **guarded** — reachable only inside `{% if var %}`-style guards or via `@?var`. The AST walk that already extracts required variables (`detect_jinja2_required_variables`) can classify guarded vs unguarded references. Unguarded use of an optional → validation error with a precise fix ("wrap in `{% if assessment %}` or use `@?assessment`").

Two existing warts this design must fix in passing:

- `@?var` currently still *registers the variable as required* (the detection walks both the `{% if %}` condition and body). Under optionals, `@?` on a declared-optional input must not mark it required — this finally makes `@?` mean what it says. `@?` on a *non*-optional input stays as today (cosmetic conditional rendering of a guaranteed value — still occasionally useful for falsy-but-present values, e.g. empty text).
- The `None`-renders-as-`"None"` gotcha (field-level `None` produces the literal string `None` in prompts, and `|default()` doesn't catch `None`) is adjacent, field-level territory — out of scope for slot optionality, but worth a follow-up lint of its own since users will conflate the two kinds of nothing when debugging prompts.

## 12. D8 — Wire, API, and graph surfaces

- **IO contracts.** `PipeInputContract`/`PipeOutputContract` (and the protocol spec + mthds-js/mthds-python mirrors + `StuffSpecInfo` in mthds-ui) gain `optional: bool`. Neutral, MTHDS-brand naming — this is language surface, not runtime-specific, so no `pipelex_` prefixing anywhere on the wire.
- **Run results.** An absent output must be *explicitly* absent on the wire, not just a missing key: the result carries the absence records (variable, producing pipe, kind, reason, provenance chain). A run whose main output is absent is a **success with an absent result**, not an error — clients branch on the structured field (presence), never on transport (same presentation-vs-contract rule as `/validate`'s `is_valid`).
- **Execute requests.** Omitting an optional method input is legal; omitting a required one keeps today's failure but the error can now say "this input is required — the method also has optional inputs X, Y you may omit".
- **Graph.** `GraphSpec` gains a `skipped` node state (alongside failed) and edges from optional outputs get a marker; mthds-ui renders skipped nodes/optional edges distinctly (dashed is the obvious treatment) and shows the absence reason in the detail panel. This is where "why did my workflow produce nothing?" gets answered visually.

## 13. D9 — Failure UX and the error taxonomy

New error classes (in the relevant `exceptions.py` modules, so docs pages, `type_uri`s, and RFC 7807 rendering come free):

- `OptionalValueAbsentError` — the `!` failure. Carries: variable name, consuming pipe, the full provenance chain from the ledger, and the original reason. `error_domain = RUNTIME` (it is data-dependent — the method's assumption failed on this input data, not the caller's request shape), with a `user_action` explaining that the method force-unwraps (`!`) a value this input data doesn't contain.
- The validation-side errors from D6 (`OPTIONAL_NOT_HANDLED` etc.) ride the existing `PipeValidationError` machinery.

The concrete failure a user sees when a force-unwrap trips (markdown arm; the JSON/problem+json arm carries the same fields structured):

> **Pipe `assess_penalty` requires `penalty_clause` to be present (declared `contracts.PenaltyClause!`), but it is absent.**
> Absence origin: pipe `extract_penalty_clause` produced no value — "The contract contains no penalty or liquidated-damages clause."
> Fix in the method: declare the input `contracts.PenaltyClause?` and guard the prompt, or let the step skip by removing `!`. Fix in the data: provide a contract that contains a penalty clause.

Compare with today's equivalent (`Stuff 'penalty_clause' not found in working memory, valid keys are: [...]`). The delta is the entire point of the feature: absence with provenance turns "mysterious missing key" into "the model looked and found nothing, here is where and why".

Success-path observability matters equally: the run report enumerates recorded absences and skipped pipes even when the run succeeds, so "my report doesn't mention penalties" is answerable without debugging.

## 14. Interactions with in-flight work

- **Required-main-stuff invariant** (`feature/Required-main-stuff`, PR #1014): that track enforces "main stuff always exists" and makes `PipeCondition` `continue` pass-through-or-error. Optionals deliberately create runs whose final output is absent. Reconciliation: an `AbsenceRecord` satisfies the invariant as the terminal state of `main_stuff` when (and only when) the method output is declared `?` — the invariant becomes "main stuff is always *resolved*: a value or a recorded absence". Also, `continue`'s two possible semantics ("pass previous main stuff through" vs "declared output is absent") must be picked consciously: under optionals the coherent reading is **declared output absent, memory otherwise unchanged**. **DECIDED 2026-07-03: `continue` = declared output absent.** This decision must be propagated to the Required-main-stuff track before either merges semantics that contradict the other.
- **`@?` required-variable detection** (D7) — the fix lands as part of this feature.
- **Pre-existing wart to fix while in the area:** structure-field shorthand strings default to `required=True` while the expanded `ConceptStructureBlueprint` defaults `required=False` — opposite defaults for the same concept. Unrelated to slot optionality but adjacent enough to confuse; fix or at least document deliberately.
- **Not in scope:** structure-field `?` sugar (e.g. `concept_ref = "X?"` meaning `required=false`). It would create two spellings for one thing and blur the slot-vs-field distinction §3 works hard to establish. Revisit only if field/slot unification ever becomes a goal.

## 15. Phase-2 candidates (design now, ship later)

- **`try?` analog — `on_error = "absent"`.** A pipe attribute, legal only when the output is `?`: a failing pipe degrades to a recorded absence (kind = `failed`, reason = the error) instead of failing the run. Powerful resilience primitive (flaky enrichment step → absent, not dead run). Two hard requirements inherited from our error-handling principles: the underlying error must still be fully captured in the run report/trace (degraded success, never a swallowed failure), and terminal-failure webhooks/notifications semantics must be worked out so "degraded" is distinguishable from "clean". Scoping to *which* errors degrade (inference errors yes, config errors no?) is the main open design question.
- **Coalescing — the `??`.** Input-level defaults. For native concepts (Text, Number...) a literal default is easy (`v = { concept = "Text?", default = "N/A" }` — note this finally motivates an expanded input table form). For structured concepts, a default *pipe* (`fallback = "make_default_x"`) is the more MTHDS-native shape. Both deferrable; nothing in phase 1 blocks either.
- **Presence-branching sugar for PipeCondition.** The v1 idiom is `expression_template = "{{ 'present' if penalty_clause is defined else 'absent' }}"` with outcomes mapped on `present`/`absent`. If it proves common, add first-class sugar (e.g. `switch_on_presence = "penalty_clause"`). Idiom first, sugar on evidence.

## 16. Blast radius

Inside `pipelex/` (the bulk): grammar (`variable_multiplicity.py` + the input-factory regex + the `[`-splitter in `concepts/helpers.py`), `StuffSpec`/`NamedStuffSpec` gain the presence field, `InputStuffSpecs.required_names` splits required/declared, the three runtime miss-gates (`validate_before_run`, `SubPipe`, PipeCondition's branch check) learn the trichotomy, `PipeSequence.needed_inputs`/`generated_outputs` gain the taint dimension, WorkingMemory gains the absence ledger, PipeLLM gains the maybe-wrapper, mock seeding and the dry-run sweep learn optional slots, validation gains the new error types + template guard-lint, `contract_match` canonicalization compares markers, builder specs mirror blueprint validation, error classes + generated error pages, graph tracer `skipped` state, and docs.

Cross-repo (from the workspace survey):

| Repo | Surfaces | Size |
|---|---|---|
| `mthds/` (spec) | Normative suffix table + concept-reference-syntax sections in `mthds-format.md`, per-pipe-type allow/forbid rules, `validation-rules.md`, a new optionality language guide beside `multiplicity.md`, reconcile `@?` docs, regenerate JSON schema | L |
| `vscode-pipelex/` | `strip_concept_qualifiers` in the LSP (strips `[...]` but not `?` — a trailing `?` breaks resolution today) + tests, TextMate grammar regexes, bundled schema sync, `plxt` format preservation | M |
| `mthds-ui/` | `StuffSpecInfo.optional`, Shiki grammar copy, skipped-node + optional-edge rendering, detail panels | M |
| `mthds-plugins/` | Skill templates that teach the ref syntax (`shared/mthds-reference.md.j2`, build/inputs/fix skills) + regeneration; teach the trichotomy and `@?` pairing | M |
| `conformance/` + `docs/specs/` | `PipeIOContract.optional` in the protocol spec, new validation-error categories in the locked contract, valid/invalid fixtures (`optional_not_handled.mthds` etc.), error-QA corpus entries | M |
| `mthds-js` / `mthds-python` | Type mirrors (IO contracts, ValidationErrorItem); package-layer ref parsers untouched by design (D1) | S |
| `pipelex-api/` | Pass-through; new absence fields in run results, docs | S |
| JSON schemas | Regenerate only — `inputs`/`output` are unconstrained strings, already `?`-permissive | S |

Sequencing note: per workspace rules, `docs/specs/` + `conformance/` move in the same change as the pipelex surface they verify; the mthds spec, tooling, and UI repos can follow the runtime release.

## 17. Phasing

- **Phase 1 — the language core (pipelex + spec/conformance).** D1 grammar, D2 ledger, D3 trichotomy + lifting, D4 plural rules, PipeCondition `continue` integration, optional method inputs, D6 taint validation + new error types, D7 template guard-lint + `@?` fix, D9 error classes + failure UX, IO-contract `optional` flag, run-result absence records, graph `skipped` state. This is a complete, useful feature on its own — even before LLM maybe-outputs, it legitimizes conditional flows and optional method inputs.
- **Phase 2 — producing absence from models.** PipeLLM/`Text?` maybe-wrapper with reasons, batch compaction if not in 1.
- **Phase 3 — ergonomics.** `on_error = "absent"`, coalescing/defaults, presence sugar, dual-arm dry run if warranted.
- **Cross-repo wave** after the pipelex release: mthds spec pages, vscode/plxt, mthds-ui, skills.

## 18. Decision summary

| # | Decision | Recommendation |
|---|---|---|
| D1 | Grammar | `?` suffix on inputs+outputs; `!` inputs only; mutually exclusive with `[]` in v1; never on concept definitions/refines/fields |
| D2 | Runtime absence | Absent key + provenance ledger; no null Stuff |
| D3 | Consumption | Trichotomy `X` (lift/skip) / `X?` (absorb) / `X!` (force); every absence source must reach an explicit sink |
| D4 | Plurals | `?` forbidden on plurals; skipped plural output normalizes to empty list |
| D5 | Producers | `?` output allowed anywhere; `continue`-reachable conditions MUST declare it; LLM maybe-wrapper (phase 2); boundaries explicit, internals inferred |
| D6 | Validation | Static taint pass, new `PipeValidationErrorType`s; dry run stays all-present in v1; general `warnings` array on the validation report (decided) |
| D7 | Templates | Absent = undefined (loud on deep use) + static guard-lint; `@?` finally means optional |
| D8 | Wire | `optional` on IO contracts; absence records in run results; absent main output = success, not error |
| D9 | Errors | `OptionalValueAbsentError` with provenance chain; RFC 7807 + error pages via existing machinery |
| D10 | Deferred | `on_error = "absent"` (`try?`), coalescing (`??`), presence sugar — phase 2/3, semantics sketched now |

Decided 2026-07-03 (Louis): D3 (implicit lifting), D4 (forbid `?` on plurals), the `continue`-absent semantics (§14), naming (`!` force marker, `?` "optional"), and D6 lints via a general `warnings` array. All open questions resolved; ready for implementation planning.

## 19. Open questions — resolutions (2026-07-03)

1. **Implicit lifting (D3): APPROVED** — implicit, for user-friendliness. Mitigations (validation-report liftable-pipe inventory, graph skipped-node rendering, run-report skip reasons) are phase-1 commitments.
2. **Skip vs empty for plurals (D4): APPROVED** — `?` forbidden on plurals; the empty list does the job.
3. **`continue` semantics (§14): APPROVED** — `continue` = "declared output absent". To be propagated to the Required-main-stuff track.
4. **Warnings channel (D6): APPROVED** — general `warnings` array on the validation report, bundled into the same protocol bump as the `optional` flag on IO contracts. The distinction that sharpened the question stands in the design: *factual dataflow info* (liftable-pipe inventory) ships as structured data on the valid report; *lints* (useless `!`, over-claimed `?`) go in `warnings`.
5. **Naming: APPROVED** — `!` = "force marker"; `?` pronounced "optional".
