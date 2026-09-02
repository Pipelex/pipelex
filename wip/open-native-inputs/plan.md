---
status: active
item: L-260902-543ad0
---

# Open-shaped natives at input positions: the two fixes the corpus could not ride along with

Two bugs, both found while covering the open-shaped natives at slot positions in the shared inputs-template corpus (L-260831-264cbd), both filed rather than fixed because each needs a ruling of its own:

- **L-260831-8f7c8c** — a `native.Anything` input crashes `build_pipe_io_contracts`: the builder resolves a structure class for every input, and `Anything` is the one concept the standard says has none. The crash sits on the hosted validate path (`validate_in_process.py:109`), so a legal bundle renders HTTP 500 after validation already succeeded.
- **L-260831-635398** — a `native.Dynamic` input referenced in a `PipeLLM` prompt is classified as a direct image reference (`is_compatible` short-circuits to `True` on dynamic concepts, and the analyzer reads compatibility as identity), so the bundle fails dry-run validation demanding `ImageContent`.

Closing both reopens the corpus work: `native.Anything` joins `scaffold_open_natives`, and a `PipeLLM` covering `native.Dynamic` becomes writable.

## Rulings

These are the decisions the crashes were hiding. They are the reviewable core of the campaign; everything below is mechanics.

### R1 — What JSON Schema an `Anything` input publishes on the wire

**An `Anything` input publishes the permissive schema: no constraint keywords, annotated with the concept's identity like every other rendered input schema** — `{"title": "native.Anything", "description": <the concept's authored description>}`. Annotation keywords constrain nothing, so this is semantically the empty schema `{}` ("any JSON value"), which is what an untyped vehicle honestly means — while keeping the invariant that every `PipeInputContract.json_schema` carries its concept's `title`/`description` (see `Concept._render_schema_representation`, which injects both on every class-backed render). Multiplicity wraps exactly as for class-backed concepts: `Anything[]` becomes `{"type": "array", "items": <the schema>}`, a fixed count adds `minItems`/`maxItems`.

Rejected alternative: bare `{}`. Same validation semantics, but it would be the one schema on the wire with no concept identity, and consumers (`mthds-js`, `mthds-python`, the hosted validate readers) would have to special-case its emptiness to display anything.

### R2 — What example value an `Anything` input renders in a fill-in template

**The empty mapping `{}`.** This matches the ruling the projections already made for `unknown` descriptor nodes — `mthds-python`'s `inputs_template.py` states it as "the escape hatch's only honest value" — so the engine renderer and the two projections agree by construction instead of by recorded difference. This arm is needed because the corpus generator renders the engine's own fill-in template for every pipe (`render_inputs` → `InputStuffSpecs.build_inputs_template` → `render_stuff_spec(JSON)`), which crashes on `Anything` exactly like the SCHEMA path; without it, Phase 3 cannot regenerate.

### R3 — A dynamic concept is never *statically* an image (or a document)

**The prompt analyzers ask "is this definitely an X", and `Dynamic`'s universal compatibility answers a different question — so a dynamic root concept short-circuits to "no static classification" before any compatibility test runs.** A `Dynamic` input referenced in a `PipeLLM` prompt renders as text through the template, same as it already does in a `PipeCompose` `template`; an author who wants image or document attachment declares `Image`/`Document` (or a refining concept). This is the same guard shape the codebase already uses twice for exactly this trap: `PipeLLM.validate_output_with_library` ("Allow Dynamic output concept") and `InputShaper.resolve_input_kind` (dynamic returns `InputKind.DYNAMIC` before the ordered strict-compatibility loop).

Corollary: `| with_images` on a `Dynamic` variable raises `WithImagesFilterError`. Statically unknowable nested images are refused, not guessed; the existing message ("the type has no nested images") stays accurate enough.

## Phase 1 — `Anything` renders instead of crashing (fixes L-260831-8f7c8c)

Branch `fix/Anything-io-contract`, PR → `dev`. Its own PR, per the item: a wire-contract ruling deserves its own review.

1. **Structureless arm in `StuffSpec.render_stuff_spec`** (`pipelex/core/pipes/stuff_spec/stuff_spec.py`). Its docstring already names it "the one place in the whole render chain that resolves a class", so the `declares_a_structure_class` branch belongs here: when the concept declares no class, do not call `concept_provider.get_structure_class` at all — render the structureless representation directly. `Concept.render_concept_representation` keeps its strict `type[StuffContent]` parameter; add a sibling on `Concept` (e.g. `render_structureless_representation(output_format=…, multiplicity=…)`) covering SCHEMA (per R1) and JSON (per R2), sharing the array-wrap/min-max logic with `_render_schema_representation` rather than duplicating it. PYTHON stays out: the output renderer already guards `Anything` at each of its entry points, and a structureless PYTHON render has no consumer.
2. **`build_pipe_io_contracts` needs no change** — the memo, the `["content"]` indexing and `PipeInputContract` all work once the render returns. Same for the trace command's hop 4 and `InputShaper._render_expected_shape`, which crash on the same lookup today and are healed by the same arm.
3. **Tests** (red first, per TDD):
   - Unit: `render_stuff_spec` for `Anything` in SCHEMA and JSON formats, at single, `[]`, and fixed-count multiplicity — pins R1 and R2 including the array wrapping.
   - Integration: extend `tests/integration/pipelex/pipeline/test_pipe_io_contracts.py` (class `TestBuildPipeIOContracts`) with a bundle declaring an `anything_in` slot; assert the contract row publishes the R1 schema and that no `PipeIOContractError` is raised. The item's two-line repro bundle is the fixture.
   - Validate-path: one test asserting a bundle with an `Anything` input produces a *verdict* through `validate_in_process` / `direct_bundle_validator` — the regression that matters for the hosted route is "verdict, not 500".
4. **Docs + changelog**: document the published schema for `Anything` wherever `pipe_io_contracts` / input schemas are documented in `docs/`; one condensed entry under `## [Unreleased]`.
5. `make agent-check`, `make agent-test`.

**Checkpoint 1** — PR 1 open. Record here: the ruling as reviewed (did R1 survive review as annotated-permissive, or get amended?), and any deferred review findings.

> **Checkpoint 1 recorded (2026-09-01):** PR [#1178](https://github.com/Pipelex/pipelex/pull/1178) open against `dev` (branch `fix/Anything-io-contract`), full `agent-check` + `agent-test` green. R1 implemented as annotated-permissive and R2 as the empty mapping, both as planned; review outcome pending. The structureless arm landed in `StuffSpec.render_stuff_spec` with `Concept.render_structureless_representation` beside `_render_schema_representation`, sharing the array wrap through an extracted `_wrap_schema_for_multiplicity`; PYTHON is refused with `ConceptValueError`. The deferred `error_domain` ruling on `PipeIOContractError`'s residual causes is filed as L-260901-5bb532.

> **Checkpoint 1 — review outcome (2026-09-02):** R1 and R2 both survived review unamended; the reviewed additions to the PR are tests and wording only, no behaviour change. Three findings were deferred to their own items rather than widening the PR, all three the same root cause — a mechanically derived `AnythingContent` that never resolves — at sites this phase did not reach:
>
> - **L-260902-9546ef (high)** — a `PipeLLM` with `output = "Anything"` still escapes protocol `validate` as `kajson.ClassRegistryNotFoundError`, which is not a `PipelexError` and carries no `error_domain`, so the hosted route renders the same HTTP 500 this phase set out to remove. `pipe_operators/llm/pipe_llm.py:234` reads the class registry directly, bypassing `get_structure_class` and therefore the guard. This is the input fix's mirror image and the phase's biggest blind spot: the regression test is input-only.
> - **L-260902-db6d1e (normal)** — `pipelex build runner` on an `Anything` input still emits the unfollowable "include that module" advice verbatim (`builder/runner_code.py:102`, `:213`), and a concept declaring `refines = "Anything"` cannot be loaded at all (`core/concepts/concept_factory.py:466`) while codegen treats that declaration as legal.
> - **R1 is wider than the runtime, and the docs now say so.** An `Anything` input accepts a string only (shaped into a `native.Text` stuff) and refuses number, bool, list and dict — see Phase 3 item 4 below for the measured evidence. R1 stays as ruled: narrowing the published schema would state a runtime limitation as a contract. `docs/under-the-hood/pipe-io-contracts.md` names the gap explicitly so a consumer reading the contract is not surprised by it, and closing it is the shaper's job.
>
> Also corrected in review: `docs/contribute/generate-projection-corpus.md` still asserted that an `Anything` input crashes the contract builder, which this phase made false; the word *structureless* was carrying two incompatible meanings across `NativeConceptCode.is_structureless_concept` (no structure **class**, `Anything` alone) and `input_form.py` (no **pinned structure**, three natives), and the sites now say which they mean.

> **Checkpoint 1 closed (2026-09-02):** PR [#1178](https://github.com/Pipelex/pipelex/pull/1178) merged to `dev` as `68b6976`, every check green, and L-260831-8f7c8c is closed `fixed` with that merge as evidence. R1 and R2 landed exactly as ruled. The merge has not reached `main` — the release that publishes both this phase and Phase 2 is L-260828-f4e88c. With both PRs merged, Phase 3 is unblocked: the corpus can now be regenerated with `anything_in` in `scaffold_open_natives` and a `PipeLLM` covering `native.Dynamic`, subject to the refusal measured in Phase 3 item 4, which the shaper — not this phase — has to close.

## Phase 2 — dynamic concepts get no static prompt classification (fixes L-260831-635398)

Branch `fix/Dynamic-prompt-classification`, PR → `dev`. Independent of Phase 1 — disjoint files; no stacking needed.

1. **Guard in `TemplateImageAnalyzer._resolve_variable_type`** (`pipelex/pipe_operators/shared/template_image_analyzer.py`): if `NativeConceptCode.is_dynamic_concept(concept_code=root_concept.code)`, return `(False, False, False, None)` before any `is_compatible` call, with a comment naming R3. This fixes both `PipeLLM` (prompt + system prompt) and `PipeImgGen` (prompt + negative prompt), which share the analyzer.
2. **Same guard in `TemplateDocumentAnalyzer._resolve_variable_type`** (`pipelex/pipe_operators/llm/template_document_analyzer.py`, return `None`): the identical bug shape — a `Dynamic` input is recorded as a DIRECT document reference today and would fail extraction the same way the moment the image misclassification stops masking it. Fixing only the image half ships the same bug one analyzer over.
3. **Tests** (red first):
   - Unit, in `tests/unit/pipelex/pipe_operators/pipe_llm/test_template_image_analyzer.py`: a `Dynamic` input referenced plainly yields no image references; `Dynamic` with `| with_images` raises `WithImagesFilterError`. A sibling test for the document analyzer: no document references.
   - Integration: the item's minimal repro — a `PipeLLM` taking `dynamic_in = "Dynamic"` and referencing it in its prompt — passes dry-run validation, with both prompt markers (`@dynamic_in` and `$dynamic_in`).
4. **Docs + changelog**: state R3 (dynamic renders as text in prompts; declare `Image`/`Document` for attachment) on the PipeLLM / prompting docs page; one condensed entry under `## [Unreleased]`.
5. `make agent-check`, `make agent-test`.

**Checkpoint 2** — PR 2 open. Record review outcomes and anything deferred.

> **Checkpoint 2 recorded (2026-09-01):** PR [#1179](https://github.com/Pipelex/pipelex/pull/1179) open against `dev` (branch `fix/Dynamic-prompt-classification`), full `agent-check` + `agent-test` green. R3 implemented as planned: both analyzers return early for a dynamic root concept before any `is_compatible` call — the image analyzer returns `(False, False, False, None)`, the document analyzer `None` — and `| with_images` on `Dynamic` still raises `WithImagesFilterError`. The integration regression lives in `tests/integration/pipelex/pipeline/test_bundle_validator.py` (chosen because PR 1 does not touch that file, so the two PRs cannot conflict there). The compatibility-as-identity sweep across the other operator sites is filed as L-260901-605377. Review outcome pending on both PRs; Phase 3 stays gated on both merges.
>
> **Checkpoint 2 closed (2026-09-01):** PR [#1179](https://github.com/Pipelex/pipelex/pull/1179) merged to `dev` as `789726a`, all checks green, and L-260831-635398 is closed `fixed` with that merge as evidence. R3 landed exactly as ruled; nothing was amended in review. One live behaviour is deliberately given up and is now named in `CHANGELOG.md` and `docs/building-methods/pipes/pipe-operators/PipeLLM.md`: an `ImageContent` shaped into a `Dynamic` slot used to reach the model through the DIRECT reference the analyzer wrongly recorded, and now renders as text with no warning. Whether attachment should also be decided at run time, or the silence become a warning, is filed as L-260901-45becb. The merge has not reached `main` — the release that publishes it is L-260828-f4e88c. Phase 3 now waits on PR 1 alone.

## Phase 3 — reopen the corpus coverage (after both PRs merge)

This is the work L-260831-264cbd had to leave behind, and it lands as a fixture change now that neither native crashes.

1. Add `anything_in = "Anything"` to `scaffold_open_natives` in `tests/data/input_semantics/scaffold_bundle.mthds` (inputs and template), alongside its existing `json_in` / `dynamic_in` / `composite_in`. Add a `PipeLLM` pipe covering `native.Dynamic` referenced in a prompt — the coverage item 2's fix makes writable.
2. Regenerate: `.venv/bin/pipelex-dev generate-projection-corpus tests/data/input_semantics/*.mthds -o /tmp/projection-corpus`; update `tests/integration/pipelex/pipeline/test_input_form.py` expectations where the scaffold grew.
3. Re-commit the captures in `mthds-js` and `mthds-python`. L-260831-56a78f and L-260831-933a6c are already open for the current regeneration — if still open when Phase 3 runs, note the added coverage on them and let one re-commit carry both; otherwise file fresh items with `ledger new --owner mthds-python|mthds-js`.
4. **Known risk, now measured — the arm refuses.** The risk this item named is real, and PR 1's review probed it ahead of Phase 3 so the phase starts from a settled question. Against a live library, an `Anything` slot refuses the R2 template in both shapes:

   ```
   compact  {}                                          REFUSED StuffFactoryError: ... does not have a 'concept' key.
   explicit {"concept": "native.Anything", "content": {}} REFUSED StuffFactoryError: ... 'native.Anything' is not compatible with a dict content
   ```

   The refusal is broader than the empty dict. Of the JSON types, an `Anything` input accepts only a string, and shapes it into a `native.Text` stuff rather than an `Anything` one:

   ```
   string  OK -> concept=native.Text content=TextContent
   number  REFUSED    bool  REFUSED    list  REFUSED    dict  REFUSED
   ```

   So the choice this item offered — record a deliberate projection difference, or fix the shaper arm — resolves toward **fixing the shaper arm**: recording a difference would pin a template nobody can submit, which is exactly the defect the `native.JSON` entry in the same release says it removed. It also means R1's published schema ("any JSON value") is currently wider than the runtime, which `docs/under-the-hood/pipe-io-contracts.md` now says out loud rather than leaving for a consumer to discover. Adding `anything_in` to `scaffold_open_natives` before the shaper is fixed will fail the round-trip gate; `docs/contribute/generate-projection-corpus.md` records that as the reason the slot is still empty.

**Checkpoint 3** — corpus regenerated and re-committed across the three repos; both bugs closed with the merges as evidence.

> Phase 3 is tracked by L-260902-543ad0, filed when Phase 1 landed: both bug items that used to carry this campaign are closed, so the document's `item:` now names the phase that is still open rather than a finished one.

> **Checkpoint 3 recorded (2026-09-02) — the `pipelex` half.** Branch `feature/Corpus-open-shaped-natives`, PR → `dev`. Both slots are in: `anything_in = "Anything"` joins `scaffold_open_natives`, and a new `scaffold_dynamic_prompt` PipeLLM puts a `native.Dynamic` slot at a prompt position under both markers (the `@` marker had to move onto its own line — the sigil is block-content-only and rejects an inline use). The bundle validates, `agent-check` and `agent-test` are green, and the capture regenerates deterministically: nine pipes, the same six divergence classes, and byte-identical output across two runs including after `plxt fmt` realigned the new pipe's keys.
>
> **The item 4 risk resolved as declaring the gap, not as fixing the shaper.** Re-measured on `dev` at `82c56b8e3` through `shape_inputs` with the pipe's own `anything_in` spec, an `Anything` slot accepts a bare string and nothing else, returning it as a `native.Text` stuff; the empty object the contract publishes as its own template is refused in both spellings, as are number, bool, list and dict, and even the *enveloped* string is refused ("not compatible with native concept 'native.Text', 'native.Date', or 'native.Time'") — narrower than the earlier probe recorded, which measured the bare form. So the slot is captured with both its shapes declared in `EXPECTED_UNSHAPEABLE` against L-260902-10eb56, filed for the shaper arm. That is the round-trip gate's own mechanism for a known-open gap rather than a workaround: an entry states the gap, the manifest records it, and the lapse rule fails the command the moment the template starts shaping, so the fix retires its own declaration and forces the regeneration. Declaring it is not the projection difference the phase warned against — a projection difference would pin a *projection* nobody can submit, where this pins the descriptor's only honest rendering and names the runtime as what has to catch up, which is exactly what `docs/under-the-hood/pipe-io-contracts.md` already says about R1's width.
>
> **The cross-repo half is deliberately not in this branch.** A capture must come from a merged `pipelex` `dev`, and the two mirror pull requests have to merge together or `conformance`'s `check-fixture-drift` goes red on `dev` for everyone. Filed as L-260902-f7d9e7 (`mthds-python`) and L-260902-720ec1 (`mthds-js`), both `blocked_by` this phase's item, each carrying the capture's measured summary so the receiving session can check its own regeneration against it. Note for whoever picks them up: both mirrors' workspace-root checkouts currently sit on `feature/Gate-protocol-corpus-parity` with an open PR from another session's work — cut the recapture branch from `dev`.

## Ledger

- Both items carry `plan:` refs at this document. Claim (`ledger claim <id>`) at the start of each implementation phase.
- PR 1 body: `Closes L-260831-8f7c8c`. PR 2 body: `Closes L-260831-635398`. Land with `/ledger-land`.

## Deferred — noted, deliberately not in scope

- **`PipeIOContractError` declares no `error_domain`, so its residual causes still render HTTP 500** (a user structure class genuinely missing from the request, a pydantic schema-generation failure). The `Anything` fix removes the illegitimate trigger; whether the remaining ones are INPUT-domain is its own ruling, adjacent to L-260829-fa8267's theme. File a ledger item during Phase 1 rather than widening this PR.
- **A sweep of other compatibility-as-identity sites.** `grep is_compatible pipelex/pipe_operators/` shows the same pattern deciding behavior in `pipe_extract`, `pipe_img_gen`, `pipe_compose`, `pipe_search`, `pipe_structure`, and `PipeLLM`'s text-vs-object dispatch — each site reachable with a `Dynamic` input or output, each currently answered by the dynamic short-circuit. Some of those leniencies are by design (`validate_output_with_library` says so explicitly); none has been audited. File as a ledger task during Phase 2.
