# Vacuous presence lint — design

**Status:** design settled on 2026-08-25 and implemented as designed on the same day, with §9's three decisions ratified rather than revised. The tracker's Phases 1 through 3 are closed; 4.3 (PR review triage) and 4.5 (the final tracker rewrite) are what remain. What is left is follow-up rather than design: the items in §8 and the four entries in [`deferred.md`](deferred.md). Tracker: [`TODOS.md`](../../TODOS.md) at the repo root, which carries the running log and the deviations. Origin: a cross-repo request filed from the form-kernel side, queued in the workspace inbox as `2026-08-25-pipelex-warn-required-input-all-optional-concept.md` (not linked — it lives outside this repo).

## 1. The problem

A method input declared without `?` (presence `plain`, or `!`) whose concept declares only optional fields is a declaration that can enforce nothing. The concept's schema admits `{}`, so the only thing "the caller must supply this" can mean is "the caller must supply an empty object". Validation accepts it silently today.

Every consumer that has to *materialise* such an input is left inventing a meaning. The form kernel `@pipelex/mthds-form` hit this on 2026-08-24: readiness was vacuously satisfied (a struct that demands nothing is "filled"), the gate rejected the absent property (`must have required property 'opts'`), and the Run button was live on a form the API would refuse. The kernel closed it on its side (a required struct with no required children now counts as missing until touched), but the end user still faces a required section in which every field is optional — and no consumer can tell the method author that the declaration is ambiguous. Only validation can, and validation lives here.

## 2. Verdict on the inbox idea: confirmed, with three amendments

The idea is right and the channel is right: an advisory item on the validation report's `warnings` array — the seam built for exactly this class of finding — that never flips `is_valid`. Three things in the request were left to us to decide, and each changes the shape of the lint:

1. **Scope it to entry pipes, not every pipe.** The inbox hedged on this ("whether to warn on every pipe or only entry-point signatures"). Linting every pipe would flag a legitimate and common design: an extraction pipe whose output is an all-optional structure ("record whatever the document states"), consumed by a downstream pipe as a plain input. That downstream slot is present by dataflow — the producer always yields *a* value — and its emptiness is the producer's honest output shape, so neither remedy the lint offers applies. The smell exists only at the boundary where a *caller* (a human, a form, an API client) has to conjure the value. That boundary is the bundle's declared `main_pipe`. See D2.
2. **Judge the concept through the input-form descriptor, not through a third crate walker.** The descriptor already answers "what does this slot demand" for the form: presence, `gating`, and the concept's merged structure with per-field `required` — across refinement chains, class-backed concepts (pydantic `is_required()`), and pinned natives. Re-deriving that in the lint would be a second (with `hint_warnings`, a third) walker over the same facts, and the two existing walkers are already known to diverge (`wip/engine-hints/deferred.md`). Linting the descriptor means the lint judges exactly what the form kernel will see. See D1.
3. **Give the warnings one composition point.** The report's `warnings` are assembled site by site today, and the sites disagree: the protocol path emits the optionality and hint lints, the agent CLI, the builder ops and the bare CLI emit the optionality lint alone. One more copy of the pattern for this lint would make the disagreement worse. One function builds every advisory warning, and every advisory-bearing channel calls it — which is every whole-bundle validate channel; the builder's `validate_all` and the bare CLI's single-pipe `validate` deliberately surface none. This closes the deferral recorded in `wip/engine-hints/deferred.md` (first bullet) and `wip/input-semantics/deferred-report-artifacts-on-cli-channels.md` (§1), and therefore takes on the one prerequisite those notes attach to it. See D6.

## 3. The rule

For each **entry pipe** of the validated batch, for each **top-level** field of its input-form descriptor:

> Warn when the field is **gating** (`gating: true` — the run cannot start until the caller provides content) and its node is an **`object` that declares no required field** (`kind: "object"` with no entry in `fields` carrying `required: true`; an empty `fields` list counts).

Everything else is silent, and each silence is deliberate:

| Descriptor node | Verdict | Why |
|---|---|---|
| `object`, at least one `required: true` field | silent | Content is definable: the caller must fill that field. |
| `object`, all fields optional | **warn** | The empty object satisfies the declaration. This is the case. |
| `object`, no fields at all | **warn** (variant wording) | The degenerate all-optional case: only `{}` fits. |
| `object` under presence `?` (`gating: false`) | silent | The author has already said the value may be absent — the ambiguity is resolved in the right direction. |
| `list`, variable multiplicity (`Concept[]`) | silent | Never gates by the descriptor's own rule: `[]` is its legitimate value. Item vacuity is a different question (§7). |
| `list`, fixed count (`Concept[N]`) | silent in this version | Gates, but the vacuity question is per item; deferred (§7). |
| `text`, `prose`, `number`, `boolean`, `date`, `enum`, `document`, `image` | silent | A scalar or file demands a value; emptiness there is the form's `isFilled` concern, not a declaration defect. |
| `unknown` (`Dynamic`, `Anything`, `Json`, `Composite`, a cross-package or unresolvable concept) | silent | No authored fact to judge; the honest answer is no verdict. |

The predicate reads `gating`, not `presence`, on purpose. `gating` is the descriptor's *stated* fact that a renderer must block Run until this slot has content, and the lint is precisely "you asked for a gate but content is undefinable here". Stating the lint on the same fact the renderer keys on means the two cannot disagree, and it makes the variable-list exclusion fall out of the descriptor's rule rather than being restated. Both `plain` and `!` gate, so both warn; the message names the marker that was written.

Nested structures are judged **one level deep**. A required field that is itself an all-optional object (`{"opts": {}}`) does not warn in this version — see §7 for why the boundary is drawn here.

## 4. Decisions

### D1 — Substrate: the input-form descriptor

The lint is a pure function over `dict[str, PipeInputFormDescriptor]` (the output of `build_input_form`) plus the set of entry pipe refs. It never touches the crate, the class registry or the pipes.

Why: the descriptor is the reference derivation of what a slot demands (workspace spec `docs/specs/mthds-input-form-descriptor.md`) and it is what the form kernel consumes. Judging the same artifact guarantees the lint and the kernel's readiness rule agree by construction. It also gives class-backed concepts and pinned natives for free — a hand-written `StructuredContent` subclass whose fields all carry defaults is reflected as all-optional by `_with_reflected_constraints`, exactly as the S2 ruling says it should be.

Consequence: on channels that do not build the descriptor today (the CLI and builder channels), the composition point builds it internally for the lint. That is a crate walk per validate, inside the window the sites already hold open — and it is *not* the deferred question of emitting the descriptor on the CLI envelope (`deferred-report-artifacts-on-cli-channels.md` §2), which stays open: computing an artifact for a lint and putting it on the wire are different decisions.

Rejected: a crate walker beside `_HintLinter`, reading `ConceptBlueprint.structure` and merging along `refines`. It would duplicate `InputFormDeriver._merged_structure`, `_first_class_structure` and the class-backed reflection, and would be the third judgment of the same facts.

### D2 — Scope: the batch's entry pipes

An entry pipe is the domain-qualified `main_pipe` of every bundle blueprint in the validated batch. A bundle with no `main_pipe` contributes no entry pipe; a batch with none is not linted.

Why: §2 item 1 — the smell is a caller-boundary smell, and `main_pipe` is where a method meets its caller. This is also what the hosted app and the starters render a form for.

Where the entry refs come from, per channel: the protocol path, the agent-CLI `validate bundle`, the builder `validate_bundle` / `validate_bundle_content` and the bare CLI's `validate bundle` all hold `ValidateBundleResult.blueprints`, so they qualify each bundle's `main_pipe` with `PipeFactory.make_pipe_ref_with_domain`, the same spelling `select_primary_blueprint` uses. The library-wide `validate all` — on the bare CLI and the agent CLI alike — holds no blueprints in hand, but the library manager retains the accumulated blueprints of the acquired library (it rebuilds the crate from them), so a small accessor on `LibraryManagerAbstract` exposes them; the plan's first test on that channel verifies the accumulation actually holds on the `acquire_library` path before relying on it.

Rejected: (a) every pipe — flags the extraction-output pattern, trains authors to ignore the channel; (b) call-graph roots (pipes no other loaded pipe depends on) — needs no plumbing, but flags every reusable pipe of a helper library validated on its own, and `pipe_dependencies()` returns bare codes, so cross-domain matching would be approximate.

### D3 — Presence: `plain` and `!` alike

Both markers gate, both warn. The message names the marker that was written so the remedy reads against the author's own text. At an entry pipe a `!` is unusual (there is no upstream slot to assert), but it is legal and it gates identically.

### D4 — Depth: one level

The predicate looks at the demanded object's direct fields only. See §7 for the transitive case and why it is deferred rather than folded in.

### D5 — Identity and wire shape

A new member of `PipeValidationErrorType`, the pipe enum, since the item locates a pipe input: **`INPUT_PRESENCE_VACUOUS = "input_presence_vacuous"`**. It joins the closed registry automatically (`VALIDATION_ERROR_TYPES` is a union of the enums), the exhaustive `match` blocks on the enum's properties gain the member, and the corpus vocabulary generator lists it as advisory-excluded beside `optional_force_redundant`, with the same reason (an entry contract keyed on `expected_error` has nowhere to put a warning on a valid entry).

The item: `category: pipe_validation`, `error_type: input_presence_vacuous`, `pipe_code` bare, `domain_code` the pipe's domain, `variable_names: [<slot>]`, `message`. No `concept_code`: the protocol's locator table defines `concept_code` on a `pipe_validation` item as the reference that did not resolve, spelled as the author wrote it, and this item has a resolved, descriptor-qualified concept — carrying it there would misuse the locator. The concept is named in the message by its qualified ref, and a consumer that needs it structurally reads `input_form[pipe_ref]`, where the same slot carries `concept_ref`.

Rejected name: `optional_presence_vacuous`, which would keep the `optional_*` family prefix of the other presence-marker diagnostics. The prefix names the optionals feature, but a reader of the wire sees "optional presence" on an input that is precisely not optional. `input_presence_vacuous` is unambiguous on its own.

### D6 — One composition point for every advisory warning

A new module `pipelex/pipeline/advisory_warnings.py` owns the assembly:

- `build_advisory_warnings(*, taint_analyses, input_form, entry_pipe_refs, qualified_crate)` — pure over precomputed ingredients; concatenates the families in a fixed order (optionality, presence vacuity, hints), each family in its own deterministic order. The protocol path calls this with the ingredients it already computes.
- `collect_advisory_warnings(*, pipes, entry_pipe_refs)` — gathers the ingredients inside the open validation window (the taint walk, the descriptor, the current library's crate qualified once) and calls the pure builder. The CLI and builder channels call this.

Every site that assembles `warnings` today switches to one of the two, and the bare CLI's yellow echo renders whatever the builder returns. The invalid arm and the single-pipe surfaces stay warning-less, as the protocol spec states.

This brings the hint lints onto the CLI and builder channels, which is the engine-hints deferral. Its stated prerequisite is taken on here: hint messages interpolate authored content raw and unbounded, one item per unknown key, so before that lint reaches a channel an author invokes casually, the lint elides long tokens and caps findings per site (a short "and N more" tail). This is small and it is the honest price of a single composition point.

Rejected: a flag on the composition point selecting which families a channel carries. It would preserve the disagreement the composition point exists to remove.

### D7 — Message wording

All-optional structure, plain input:

> Input 'opts' of pipe 'demo.run' must be supplied (declared without '?'), but concept 'demo.RunOptions' declares no required field — an empty object satisfies it, so a caller cannot tell what to fill in. Mark the input optional (`opts = "demo.RunOptions?"`) if the pipe can run without it, or make at least one field of 'demo.RunOptions' required.

`!` input: the parenthesis reads "(declared with a force marker '!')". Field-less structure: "declares no field at all — only an empty object fits it", and the second remedy reads "or give 'demo.RunOptions' a required field". The concept is always the descriptor's qualified `concept_ref`. The message carries no authored free text (no descriptions), so it needs no eliding.

## 5. Blast radius

Runtime:

- `pipelex/validation_error_types.py` — the new member and its comment; every exhaustive `match` property over the type union.
- `pipelex/pipeline/vacuous_presence_warnings.py` — new: the pure lint over descriptors.
- `pipelex/pipeline/advisory_warnings.py` — new: the composition point (D6).
- `pipelex/pipeline/hint_warnings.py` — token eliding and the per-site cap (D6's prerequisite).
- `pipelex/libraries/library_manager_abstract.py`, `library_manager.py` — the accumulated-blueprints accessor (D2).
- `pipelex/pipeline/validate_in_process.py`, every site in `pipelex/cli/agent_cli/commands/validate/_validate_core.py` and `pipelex/builder/operations/validate_ops.py`, `pipelex/cli/commands/validate/_validate_core.py` — switch to the composition point.
- `pipelex/pipeline/validation_report.py`, `pipelex/base_exceptions.py` — docstrings that name `build_optionality_warnings` as the warnings source.
- `pipelex/cli/dev_cli/commands/generate_corpus_vocabulary_cmd.py` + regenerated `pipelex/test_extras/mthds_corpus/vocabulary.toml` — the advisory exclusion (D5).

Docs in this repo: `docs/building-methods/pipes/understanding-optionality.md` (the warnings bullet becomes a list of the advisory lints), `docs/building-methods/concepts/inline-structures.md` (a short note: an all-optional structure as a required method input triggers the lint), `docs/under-the-hood/input-form-descriptor.md` (the gating rule now has a lint stated on it), `docs/tools/cli/agent-cli.md` (the advisory note lists all three families and drops "not wired into this CLI's array"), `docs/under-the-hood/error-model.md` and `docs/contribute/mthds-test-corpus.md` (the advisory-only members are now several), `CHANGELOG.md` under `[Unreleased]`.

Tests: a unit decision table over hand-built descriptors; protocol integration cases (entry pipe warns, the same shape on a sub-pipe does not, class-backed all-defaulted structure warns, no `main_pipe` means no lint, `?` silences); an agent-CLI `validate bundle` envelope case and a `validate all` case; the hint cap; the corpus vocabulary gate re-run.

## 6. Interactions worth knowing before implementing

- **`build_input_form` must run inside the validation window** (class-backed reflection reads the class registry). Every site the composition point serves already holds the window open; `validate_in_process` builds it before its `finally`, and the plan keeps it there.
- **`qualify_crate` runs twice per protocol validate** today (`build_input_form` and the hint lint each qualify the accumulated crate). The collector qualifies once and hands the result to the hint lint; whether `build_input_form` also accepts a pre-qualified crate is opportunistic — do it only if it falls out cleanly, it is a recorded deferral, not this work's goal.
- **Pinned native objects** (`Page`, `TextAndImages`, `SearchResult`) all declare required fields, so they never fire. The lint reads facts, not identities, so if a native were ever pinned all-optional it would fire — and the message's second remedy would be impossible for the author. Acceptable: the first remedy still holds, and a native pinned that way is the language's bug to fix.
- **`ConceptStructureBlueprint.required` defaults to `False`**, so a structure authored with the long form and no `required = true` anywhere is all-optional. The shorthand `field = "description"` is a required text field, so a structure with any shorthand field never fires. Worth stating in the docs note, since it is the difference between the two spellings an author is most likely to miss.

## 7. Out of scope, and why the line is here

- **Transitive vacuity** (`{"opts": {}}` — a required field that is itself an all-optional object). Deferred, not rejected. One level is where the form kernel's trap bit, and the transitive notion's edges are fuzzy: a required text admits `""`, a required list admits `[]`, and a lint whose boundary is arguable is a lint that gets ignored. If it comes back, the natural formulation is "no path from the slot to a scalar or file field passes only through required fields", stated on the descriptor.
- **Fixed-count lists** (`Concept[N]` of an all-optional concept). Gates, admits `[{}, {}]`. Same per-item question as above; deferred with it.
- **Sub-pipes a caller might run directly** through the API's `pipe_ref` selector. Not linted (D2). If that becomes a real path for form rendering, the entry set can be widened without changing the rule.
- **Single-pipe validate surfaces.** Stay warning-less, as the protocol spec states.
- **The `mthds-form` side.** The kernel's fix stands on its own; nothing here changes the descriptor or the wire.

## 8. Cross-repo follow-ups to file at close

Each is an `wip/inbox/` item filed from this repo when the implementation lands, not a widening of this diff:

- **`workspace`** — `docs/specs/pipelex-mthds-protocol.md`: the advisory-warnings section gains the new occupant; the "one further value" sentence under the optionality table and the registry prose become plural. `conformance/`: a valid-arm row `valid_input_presence_vacuous` in `validate-error-qa` with its fixture, and `tests/pipelex_api/test_validate_warnings.py` / `tests/pipelex_agent/test_validate_optionals.py` extended (gated on the release that carries the lint). `make check-spec-links` after both.
- **`pipelex-js`** — `packages/runtime/src/bundle/categorize.ts` transcribes `PipeValidationErrorType` member for member and its parity check compares against the reference enum; the new member has to be added there.
- **`pipelex-starter-js`** — `docs/input-form.md`'s "shape to avoid" paragraph can point at the lint once a release carries it.
- **Corpus consumers** (`conformance`, `mthds-ui`, `vscode-pipelex`) re-vendor `vocabulary.toml` through the sync plugin at the next release; nothing to file, the drift gates say so.

## 9. The decisions that were ratified before implementation

1. Entry-pipe scope (D2) rather than every pipe — the one that changes what authors see most.
2. The wire name `input_presence_vacuous` (D5).
3. Bringing the hint lints onto the CLI and builder channels through the composition point, with the cap (D6) — the only item that widens beyond the request; the alternative is the flag D6 rejects.
