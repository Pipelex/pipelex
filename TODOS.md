# Smart Inputs — signature-driven input shaping: implementation plan

Status: **plan written 2026-07-07, implementation not started.** Design home: `wip/inputs/smart-inputs-design.md` (**approved** — decisions D1–D11 are settled; do **not** relitigate them here). Branch `feature/Smart-inputs`, worktree `_smart`, tip `fb186fa58`, 24 commits ahead of `origin/dev`, based on main at v0.38.0 (TOML inputs #1022 + Optionals phase 1 #1021). Both native-concept prerequisites — `YesNo` (#1028) and `Date` (#1029) — have already landed on this branch; Smart Inputs is the final track car, shipping in the same release wave.

How to use this doc: work the phases in order, check boxes as you go, and at each **CHECKPOINT** run the checkpoint protocol (below) and fill in the "state" line so the next session cold-starts from here. This file is the active working plan (mirrors how YesNo/Date used the repo-root `TODOS.md`); on completion it gets archived to `wip/inputs/smart-inputs-implementation-plan.md` as the as-built record.

---

## Checkpoint protocol — every CHECKPOINT is a HARD STOP

At each checkpoint the executing agent **must stop** and do all three, in order:

1. **Verify progress.** Run the gates for the phase: `make agent-check` (ruff/plxt/pyright-0/mypy-Success/cko), targeted pytest on the phase's new modules, and — at the phase's end — `make tb` (boot) and `make agent-test` (full suite). A checkpoint is not "reached" until its gates are green. Commit the phase as one commit; record the SHA.
2. **Gather cold-start context.** Update this file: check the phase's boxes, fill the CHECKPOINT "state" line (what landed, commit SHA, decisions taken, anything that fought back), and append any new settled decision to the micro-decisions log. If a doubt or tradeoff surfaced, capture it as a new `wip/inputs/<name>.md` note rather than silently deciding (the "defer on doubt" rule the Date track used). The goal: a fresh session can resume from this file with zero lost context.
3. **Fan out a code review.** Spawn a **Sonnet-5 sub-agent** running the `/code-review` skill (or the `pr-review-toolkit:code-reviewer` agent) over **only this phase's changes**. **Pointer-only context** — hand it the phase's commit SHA, `git diff <phase-base>..HEAD`, or the working-tree files, and nothing else: **never** the plan, the design rationale, the decision letters, or your own conclusions. The reviewer's eyes must stay independent. Goal per the brief: *clean solid software, not over-engineering* — no impossible-scenario guards, smallest correct surface. Triage its findings: apply genuine wins, dismiss the unreachable, and defer design-tradeoff findings as `wip/inputs/<name>.md` notes. Record the round in the state line.

The **final** checkpoint (Phase 5) additionally runs the heavier **gstack `/review`** (Opus fan-out: testing + maintainability + adversarial-red-team, each pointer-only) as the finalize pass — **user-gated, never launch it unprompted** (it is billed).

---

## 0. Cold-start context — read this first

**What ships:** the inputs a caller provides are interpreted **top-down against the pipe's declared signature** instead of bottom-up from their shape alone. A bare string becomes the *declared* concept (a `legal.Question`, not `native.Text`); a bare number satisfies a `Number`-refining input; a bare dict validates against a structured concept; a JSON list shapes element-wise into `ListContent[declared]`; the `{concept, content}` envelope stays as an escape hatch and is now *compat-checked*. Full problem statement, the shape-at-a-glance example, and D1–D11 with rationale are in `smart-inputs-design.md` — do not relitigate. The plan starts from design **§9 "Surfaces impacted"**.

**The mechanism in one sentence:** every surface (CLI file/inline, Python API, hosted runner) funnels inputs through one chokepoint that is signature-blind today; thread the signature into it and dispatch each value on the *declared concept's nature*.

**Key mechanism facts** (re-verified against the worktree 2026-07-07 — line numbers approximate, re-grep each symbol before citing):

- **The chokepoint.** `StuffFactory.make_stuff_from_stuff_content_or_data` (`pipelex/core/stuffs/stuff_factory.py:230`) shapes each value bottom-up. Its Case 1 (direct: str→Text, list[str]→Text list, `StuffContent`/`ListContent` passthrough, list[StuffContent]) and Case 2 (envelope `{concept, content}` — arms 2.1/2.1d bool→YesNo/2.1e·f date/2.3 StuffContent/2.5 dict/2.6 list) are the behavior Smart Inputs makes top-down. The terminal `Unexpected type for content value` is `:654`. **No signature is consulted anywhere in it.** YesNo/Date already added compat-checked scalar-envelope arms here (2.1d/2.1e/2.1f) — Smart Inputs generalizes that pattern.
- **The single seam to wire.** `make_from_pipeline_inputs` (`pipelex/core/memory/working_memory_factory.py:68`) has **exactly one caller**: `prepare_pipe_job` (`pipelex/pipeline/execution_seams.py:198`). That function already holds `pipe.inputs` and already reads `pipe.inputs.named_stuff_specs` a few lines down for the Optionals pass (`:226`). `prepare_pipe_job` is itself the single funnel for **all** surfaces — called by `bundle_validator.py` (validate/dry-run), `pipeline_run_setup.py` (real runs), and `dry_run_in_process.py`. Wiring the signature into that one `make_from_pipeline_inputs` call ⇒ D1 (all surfaces) for free.
- **`pipe.inputs` is an `InputStuffSpecs`** (`pipelex/core/pipes/pipe_abstract.py:95`, `= Field(default_factory=InputStuffSpecs)`). `InputStuffSpecs` (`pipelex/core/pipes/inputs/input_stuff_specs.py:38`) is a `RootModel[dict[str, StuffSpec]]`; useful members already present: `.root`, `.named_stuff_specs`, `.declared_names`, `.required_names`, `.is_variable_existing(name)`, `.get_required_stuff_spec(name)`, `.build_inputs_template()`, `.render_inputs()`. Each `StuffSpec` (`pipelex/core/pipes/stuff_spec/stuff_spec.py:10`) = `concept: Concept` + `multiplicity: VariableMultiplicity | None` + `presence: PresenceMarker`, with `.is_multiple()` and `.render_stuff_spec(fmt)`.
- **Multiplicity encoding (D2).** `VariableMultiplicity = bool | int` (a **type alias**, not a class, `pipelex/core/pipes/variable_multiplicity.py:10`): `None` = single, `True` = `X[]` (variable list), `int N` = `X[N]` (fixed count). `PresenceMarker(StrEnum)` = PLAIN/OPTIONAL/FORCE with `.is_optional`. Peel multiplicity first, then dispatch the item.
- **Concept-nature detection (D5).** There is **no** single "which native family does this concept refine" helper. The only tool is `ConceptLibrary.is_compatible(tested_concept, *, wanted_concept, strict=True)` (`pipelex/libraries/concept/concept_library.py:97`) called once per candidate native — exactly what `stuff_factory.py` does today for Text/YesNo/Date (`:477/:494/:504/:522`). `strict=True` = refinement/structural-equivalence only (no field-subset fallback). The 14 native codes (`NativeConceptCode`, `pipelex/core/concepts/native/concept_native.py:22`): Dynamic, Text, Image, Document, Html, TextAndImages, Number, YesNo, Date, Page, JSON, SearchResult, Anything, Composite. `Concept.get_structure_class()` (`pipelex/core/concepts/concept.py:174`) → the content class; a concept is "structured" when that class ⊑ `StructuredContent` and is not a native. `are_concept_compatible` special-cases Dynamic.
- **Building primitives (reuse, don't reinvent).** `StuffContentFactory.make_content_from_value(subclass, *, value)` and `make_stuff_content_from_concept_required(concept, *, value)` (`pipelex/core/stuffs/stuff_content_factory.py:14/:59`) already turn a str/bool/date/dict into typed content honoring refining subclasses. `make_stuff_content_from_concept_with_fallback` falls back to `TextContent` when unregistered. The shaper composes these + `is_compatible` — the new code is the *top-down dispatch*, not new content builders.
- **Protocol is runtime-unvalidated (D10 is release-gated, NOT a blocker).** `PipelineInputs` / `StuffContentOrData` (`mthds/protocol/pipeline_inputs.py`, in the **mthds-python** pinned dep) is a bare `TypeAlias` (`dict[str, StuffContentOrData]`), **verified**: no pydantic model, no runtime validation. So a bare `int`/`float`/`bool` in the inputs dict **flows straight to the shaper at runtime** even though the static type doesn't admit it. Core-scope Smart Inputs shapes bare scalars *before* this seam and works day one; the D10 widening only makes the type honest for typed SDK/API callers + downstream mirrors, and rides the release wave (Optionals/TOML-inputs precedent).
- **Path resolution today (D3/D7).** `resolve_inputs_paths(inputs_dict, *, base_dir)` → `resolve_url_in_value` (`pipelex/cli/commands/run/_inputs_path_resolver.py:75/:45`) recursively rewrites relative paths **only under keys literally named `"url"`** — it has **no** view of the pipe/signature. Called at `_run_core.py:162` and `stdin_resolver.py:191` (base_dir = inputs file's parent). D3 needs bare strings for Image/Document-family concepts resolved too; that needs the signature (Phase 3 settles where).
- **CSV compounding (D11).** `_try_make_csv_list_stuff(concept, *, content, name, code)` (`stuff_factory.py:138`, called from Case 2.5 `:555`) fires when `content` is exactly `{"url": "<tabular-path>"}` under a **non-native** concept → `ListContent[row-concept]` via `concept.get_structure_class()`. With shaping, `"people": "people.csv"` (bare, D3) or `{"url": "people.csv"}` under a declared `Person[]` can trigger it with no envelope.
- **D8 has no home today.** Nothing compares provided input names to `pipe.inputs`; `make_from_pipeline_inputs` blindly `add_new_stuff`s every key, and `execution_seams.py:210`'s `provided_names` is used only to subtract from mock-fill. `InputStuffSpecs.is_variable_existing` / `.declared_names` are the predicates a D8 check uses. The shaper is the natural home (it holds both the provided dict and the specs).
- **Template rendering today (D11).** `input_renderer.py` (`build_inputs_template`, `render_inputs`, `render_inputs_toml`, `serialize_inputs_template_to_toml` via tomlkit) → `InputStuffSpecs.build_inputs_template()` → per-spec `render_stuff_spec(JSON)` → `Concept.render_concept_representation(is_multiple=)` → `ConceptRepresentationGenerator._generate_basic_value` (`pipelex/core/concepts/concept_representation_generator.py:294`, has the temporal branch). Today this emits the **envelope** form; D11 flips the default to bare values. CLI entrypoints: `pipelex build inputs` = `pipelex/cli/commands/build/inputs/pipe_cmd.py` + `_inputs_core.py` (format switch `:92`); `pipelex-agent inputs` = `pipelex/cli/agent_cli/commands/inputs/{pipe_cmd,_inputs_core}.py` + `builder/operations/inputs_ops.py:build_inputs_for_pipe`. Both already carry `--format json|toml` (`InputsTemplateFormat`).
- **Error homes (D4).** New shaping errors belong in `pipelex/core/memory/exceptions.py` (the shaper's package). The precedent to copy is `pipelex/cli/commands/run/exceptions.py::InputsTimeOnlyNotSupportedError`: class-level `error_domain = ErrorDomain.INPUT`, `user_action = UserAction(kind=UserActionKind.CHANGE_INPUT, detail=…)`, `_authors_caller_facing_message = True`. `OptionalValueAbsentError` (`pipelex/core/pipes/inputs/exceptions.py`) is the other in-tree example. Every error class subclasses `PipelexError`; run `make gep` after adding/renaming.

**Test + e2e layout** (extend these, don't invent new trees): unit — `tests/unit/pipelex/core/stuffs/test_stuff_content_factory.py`, `test_stuff_factory_implicit_memory.py` + its `data.py` (the case table YesNo/Date extended), `tests/unit/pipelex/core/memory/` (working-memory tests); new shaper tests go in `tests/unit/pipelex/core/memory/input_shaper/` (one TestClass per module, mirroring `stuffs/date_content/`). e2e — `tests/e2e/pipelex/pipes/<feature>/<bundle>/<bundle>.mthds` + a `test_*.py` (precedents: `tests/e2e/pipelex/pipes/{date,yes_no}/`).

**House rules that bite here:** TDD (tests first, red→green); keyword-only args (bare `*` after the subject — `make cko` gates, plus a PostToolUse hook at edit time); error classes only in `exceptions.py` modules; exhaustive `match/case` over enums, **never** `case _`; `make agent-check` after code changes; `make agent-test` before wrapping a session (`make atd` if it hangs); `make tb` for a quick boot check; `make gep` regenerates error pages; no hardcoded counts in docs/comments; changelog entries under `[Unreleased]`; docs updated in the same change (§ "Documentation" in CLAUDE.md).

---

## Gaps surfaced while planning — confirm defaults (recommendations given, loop not blocked)

The design settled D1–D11; three corners it doesn't spell out. Recommended defaults let execution proceed; flag to Louis if any feels wrong.

- **Out-of-matrix natives.** D5's matrix names Text / Number / Image·Document / Structured / Dynamic·Anything / YesNo / Date. It is silent on a declared input concept refining **Html, JSON, Page, TextAndImages, SearchResult, Composite**. **Recommendation:** treat these like Dynamic — *no* new top-down arm; fall back to today's bottom-up `StuffFactory` for that single input (preserves current behavior, widens nothing, breaks nothing). Revisit per-native only if a real need appears. Confirm.
- **D3 path-resolution seam.** Where do bare strings for Image/Document concepts get relative-path-resolved, given the current resolver is signature-blind and pre-core? **Recommendation:** make the CLI resolver signature-aware — pass the resolved pipe's `InputStuffSpecs` into `resolve_inputs_paths` so it resolves bare strings whose declared concept is Image/Document-family *in addition to* `"url"` keys — keeping path resolution a CLI concern (API/SDK callers pass absolute URLs/storage URIs, no base_dir). Settle the exact mechanism as Phase 3's first task (it hinges on pipe-resolution ordering in `_run_core.py`).
- **D8 severity.** Design leans **error** on unknown input names but flags the shared-inputs-file-across-pipes risk. **Recommendation:** error (loud beats silent), with a message that lists the declared names — the one place Smart Inputs narrows behavior. Confirm; downgrade to a warning only if a real over-provisioning workflow surfaces.

---

## Phase 1 — The `InputShaper` core (D5 matrix, D2 multiplicity, D6 compat, D8 names, D4 errors)

Build the shaper as a **pure, fully unit-tested unit that is not yet wired** into any run. It reuses the existing primitives (`StuffContentFactory`, `is_compatible`, and delegates Dynamic/out-of-matrix/already-built values to the current `StuffFactory`); the new code is the top-down dispatch. Tests construct `InputStuffSpecs` fixtures directly — no seam needed.

- [x] **Tests first (red→green).** New `tests/unit/pipelex/core/memory/input_shaper/` (one TestClass per module + shared `data.py`): one arm per D5 row — Text-refining ← str; Number-refining ← int/float and **rejects bool** (the `bool ⊑ int` trap) and rejects `"42"` (no cross-type parse); YesNo-refining ← bool; Date-refining ← date/datetime obj + ISO str; Image/Document-refining ← bare str + `{"url":…}` dict; Structured ← dict (pydantic validates; missing-required-field → D4); Dynamic/Anything ← bottom-up passthrough. D2: list shapes element-wise into `ListContent[declared]`; single bare value auto-wraps; empty list → empty `ListContent[declared]`; `X[N]` count-checked (single satisfies `[1]`, not `[2]`); list-under-singular → D4. D6: envelope `{concept, content}` compat-checked, explicit-refining-concept wins, incompatible → D4; the exact-two-keys collision rule. D8: unknown provided name → error listing declared names. D9 guards: top-level `null`/`None` → D4 (absence = omit key); bool never leaks into the Number arm. Each failure asserts the rendered expected-shape template appears in the message. **DONE**: 4 test modules (`test_scalar_arms.py`, `test_multiplicity.py`, `test_explicit_forms.py`, `test_errors.py`) + `conftest.py` (autouse class-scoped library setup) + `data.py` (refining/structured content classes + `build_input_specs` helper), 39 tests, all green.
- [x] **New module `pipelex/core/memory/input_shaper.py`** — `InputShaper.shape(pipeline_inputs, *, input_specs: InputStuffSpecs, search_domain_codes) -> WorkingMemory`. Internal `resolve_input_kind(concept) -> InputKind` (new `StrEnum`: TEXT/NUMBER/YES_NO/DATE/IMAGE/DOCUMENT/STRUCTURED/DYNAMIC) composed from ordered `is_compatible(concept, get_native_concept(X), strict=True)` checks + the structured/dynamic fallback. Per-input algorithm: D8 name check (batch, first) → look up spec → explicit-form arm (D6 compat, post-hoc) → D9 null guard → D5 kind dispatch (DYNAMIC short-circuits to bottom-up before multiplicity peel) → D2 multiplicity peel → build `Stuff` typed as the declared (or compatible-more-specific) concept. Delegate Dynamic / out-of-matrix natives / explicit forms to `StuffFactory.make_stuff_from_stuff_content_or_data`.
- [x] **New error classes in `pipelex/core/memory/exceptions.py`** (D4) — `InputShapingError` base + `WrongScalarKindError`, `ListWhereSingularError`, `MultiplicityCountMismatchError`, `StructureValidationError`, `ExplicitConceptIncompatibleError`, `UnknownInputNameError`, `NullInputError`. `error_domain = ErrorDomain.INPUT`, `_authors_caller_facing_message = True`; base carries a per-instance `user_action` (advice differs per failure). Each `make(...)` names the input, the declared concept ref, what was provided, and **renders the expected shape** via `stuff_spec.render_stuff_spec(JSON)`. `make gep` ran (new pages written).
- [x] `make agent-check` green (pyright 0 / mypy Success / cko PASSED); targeted pytest on the new modules green (39); `make tb` green (9); core memory/stuffs/concepts suite green (855).

### CHECKPOINT 1 — the shaper exists, is unit-green, and is NOT yet wired

Run the checkpoint protocol (verify · cold-start update · Sonnet-5 `/code-review` fan-out, pointer-only). This is the largest reviewable unit and the one most prone to over-engineering — the review's mandate is *smallest correct surface*.

State: **REACHED (2026-07-07).** The `InputShaper` core exists, is unit-green (41 tests), and is NOT wired into any run (pure; Phase 2 wires the seam). Gates: `make agent-check` fully green (pyright 0 / mypy Success / cko PASSED), `make tb` green (9), core memory/stuffs/concepts suite green (855). Cold-start micro-decisions appended below. Committed as the single Phase-1 commit on `feature/Smart-inputs` (message `feat(core): Smart Inputs Phase 1 — the InputShaper core (not yet wired)`; find via `git log --grep "Smart Inputs Phase 1"`).

**Review round 1** — Sonnet-5 `pr-review-toolkit:code-reviewer`, pointer-only (working-tree diff, no plan/design/rationale). One **Critical** + two Minor. Triage:

- **Critical (APPLIED).** A bare Python `list` of already-built `StuffContent` items (e.g. `[Question(text="a"), Question(text="b")]` for a declared `Question[]` — the documented `StuffContentOrData` Case-1.4 form, handled bottom-up today) crashed in per-item shaping (`_build_item_content` only accepted bare scalars/dicts) → `WrongScalarKindError`. Genuine regression vs today's behavior / D1's "no regression, only better typing". **Fix:** `_build_item_content` now handles a `StuffContent` item by building it bottom-up (concept inferred from its class) + D6 compat-check against the declared item concept, mirroring the wrapped-`ListContent` path; `search_domain_codes` threaded down `_shape_with_multiplicity`/`_shape_list`/`_build_item_content`. This preserves D2 for the singular case (list-where-singular still errors) and fixed-count checks. Two regression tests added (`test_list_of_prebuilt_stuff_content_items`, `test_list_of_prebuilt_incompatible_item_raises`).
- **Minor (no change).** The `InputKind.DYNAMIC` arm in `_build_item_content`'s match is dead but a justified exhaustive-match guard (repo forbids `case _`); reviewer agreed.
- **Minor (APPLIED).** `test_errors.py`'s `expects_rendered_shape` column was always `True` (dead flexibility) → dropped; the rendered-shape assertion is now unconditional.

No design-tradeoff findings to defer. The one pre-existing asymmetry the shaper does not close (envelope escape hatch still builds plain `TextContent` for a Text-refining concept via `StuffFactory` Case 2.1c, while the bare path builds the refining subclass) is already tracked in `wip/inputs/scalar-envelope-arm-asymmetry.md` for Phase 5 triage.

---

## Phase 2 — Wire the seam: top-down shaping goes live on all surfaces (D7, D1, D8)

The behavior-change phase. Small and contained (one factory param, one call site), but this is where real runs start interpreting values top-down — the riskiest integration point, hence its own checkpoint.

- [ ] **Tests first.** e2e: a **bare-values inputs file** (design §2 example — `question` str→Question, `priority` number→Priority, `invoice` dict→Invoice, `exhibits` list-of-strings, an empty list) through `pipelex run … --dry-run`, asserting each Stuff carries the **declared** concept (not `native.Text`). Error-message snapshot tests for a D4 mismatch and a D8 unknown name. A regression test pinning that a **no-signature** caller (`input_specs=None`) still gets today's bottom-up behavior. A test that a bare `int` survives to the shaper despite the narrow `PipelineInputs` alias (runtime-reachability pin).
- [ ] **`WorkingMemoryFactory.make_from_pipeline_inputs`** gains `input_specs: InputStuffSpecs | None = None`: `None` → today's bottom-up loop (unchanged); present → delegate to `InputShaper.shape(...)`.
- [ ] **`prepare_pipe_job`** (`execution_seams.py:198`) passes `input_specs=pipe.inputs` — the method-boundary contract, **not** `needed_inputs()` (same choice the Optionals pass made at `:226`). Confirm no other caller of `make_from_pipeline_inputs` exists (grep — currently one) and that validator / real-run / dry-run all inherit it through `prepare_pipe_job`.
- [ ] **D8 goes live**: unknown provided names now error (the shaper raises). Verify no in-tree fixture bundle relied on silently-ignored extra inputs; if one does, that's a real signal — fix the fixture, don't loosen D8.
- [ ] `make agent-check` + full `make agent-test` green (this phase can perturb existing input tests — expect and fix fallout).

### CHECKPOINT 2 — top-down shaping is live end-to-end

Run the checkpoint protocol. Emphasize in the cold-start update: any existing-test fallout and how it was resolved (a genuine behavior fix vs a test that encoded the old bottom-up mistyping). Sonnet-5 `/code-review`, pointer-only.

State: _pending._

---

## Phase 3 — File-ish concepts (D3/D7) + CSV-by-signature (D11 compounding)

- [ ] **Settle the D3 path-resolution mechanism** (first task — decide, then implement): confirm pipe-resolution ordering in `_run_core.py` and either make `resolve_inputs_paths` signature-aware (recommended — pass the pipe's `InputStuffSpecs`, resolve bare strings for Image/Document-family concepts alongside `"url"` keys) or thread a `base_path` into the shaper. One resolution point, no base_dir leaking into core.
- [ ] **Tests first.** e2e: a bare-string image/document input (`"photo": "photo.jpg"`, `"exhibits": ["a.pdf","b.pdf"]`) resolves relative paths and builds `ImageContent`/`DocumentContent`; the `{"url":…}` dict form still works and is now signature-shaped (no envelope). CSV: `"people": "people.csv"` and `{"url": "people.csv"}` under a declared `Person[]` trigger the tabular reader → `ListContent[Person]` with no envelope (the shaper's multiplicity/structured arm tries CSV before erroring).
- [ ] Implement the D3 bare-string → url/path arm in the shaper's Image/Document dispatch; wire CSV detection into the declared-multiplicity/structured arm ahead of the "dict for structured concept" error.
- [ ] `make agent-check` + targeted e2e green.

### CHECKPOINT 3 — file-ish inputs and CSV-by-signature work

Run the checkpoint protocol. Sonnet-5 `/code-review`, pointer-only.

State: _pending._

---

## Phase 4 — Template generation flips to the light shape (D11)

The default `pipelex build inputs` / `pipelex-agent inputs` template becomes the **light, signature-driven values** (example values shaped like what the shaper accepts); the ceremonial envelope form moves behind an **`--explicit`** flag, composing with the existing `--format json|toml`. TOML light templates carry the declared concept as a comment (`# concept: legal.Question`); JSON can't (no comments), which is itself a reason to keep `--explicit`.

- [ ] **Tests first.** Golden-template tests: light JSON + light TOML (with concept comments) for a mixed-signature pipe; `--explicit` reproduces today's envelope template; both compose with `--format`. **Round-trip test** (the bug the Date `/review` caught — a template that won't `run` is worthless): `build inputs` (light default) → `run --dry-run` succeeds against the same pipe.
- [ ] Implement: a light-vs-explicit switch through `input_renderer.build_inputs_template` / `InputStuffSpecs.build_inputs_template` / `StuffSpec.render_stuff_spec` / `Concept.render_concept_representation` (the envelope wrapping happens in that chain today — gate it). Add `--explicit` to `build inputs` `pipe_cmd.py` + `_inputs_core.py` and to `pipelex-agent inputs` (`pipe_cmd.py` + `inputs_ops.py`). TOML concept comments via the tomlkit path in `serialize_inputs_template_to_toml`.
- [ ] `make agent-check` + targeted tests green.

### CHECKPOINT 4 — templates default to light, `--explicit` restores the envelope

Run the checkpoint protocol. Sonnet-5 `/code-review`, pointer-only.

State: _pending._

---

## Phase 5 — Docs, changelog, deferred-notes triage, wrap + finalize review

- [ ] **Docs.** Rewrite `docs/building-methods/pipes/provide-inputs.md` (it shrinks dramatically — "just provide the values", envelope demoted to the escape hatch); update `docs/tools/cli/run.md`, `build/inputs.md`, and the agent-CLI inputs docs for the light-template default + `--explicit`.
- [ ] **Triage the deferred notes Smart Inputs was meant to unify** — for each, apply-and-delete or re-defer with a reason: `scalar-envelope-arm-asymmetry.md` (str arm should now preserve a refining concept's subclass, like the bool arm — unify in the shaper); `loader-vs-factory-date-split-duplication.md` (the top-level-literal conversion and per-concept shaping collapse into the shaper's Date arm); `case1-bare-date-arm-gap.md` (a top-level array of date literals should now build `ListContent[DateContent]` via D2 + the shaper); note `container-default-temporal-codegen-gap.md`, `structure-field-fidelity-guard.md`, `refines-hint-native-list-drift.md` as still-out-of-scope (structure-field codegen / release-wave authoring sweep) unless naturally touched.
- [ ] **Changelog** under `[Unreleased]`: Smart Inputs — signature-driven input shaping (bare values accepted, declared-concept typing, envelope compat-checked, unknown-name detection). Breaking where it narrows (D8). No `wip/` mentions.
- [ ] **Bookkeeping.** Update `wip/inputs/README.md` (Smart Inputs → done; the track's remaining work is the one release-cut cross-repo wave) and archive this file to `wip/inputs/smart-inputs-implementation-plan.md`.
- [ ] Full `make agent-check` + `make agent-test` green.

### CHECKPOINT 5 — track complete; finalize review

Run the checkpoint protocol, **plus** the finalize **gstack `/review`** (Opus fan-out: testing + maintainability + adversarial-red-team, each pointer-only) — **user-gated: do not launch it unprompted.** Then the track is ready for the release wave.

State: _pending._

---

## Deferred / release-wave sweep — NOT this plan's scope (listed so nothing is lost)

Shared per-release wave with YesNo + Date (see `wip/inputs/README.md`), done once, not per-feature:

- **D10 protocol widening** — `mthds/protocol/pipeline_inputs.py` `StuffContentOrData` widens to admit bare scalars / lists-of-dicts / empty lists (converges to "any JSON value | StuffContent forms"), with the interpretation semantics spec'd MTHDS-side (`docs/specs/` + the `mthds` repo). Release-gated (Optionals/TOML-inputs de-gate pattern). Runtime already works; this is type-honesty for typed callers.
- **Downstream mirrors** — `mthds-python` + `mthds-js` `PipelineInputs` types, conformance rows, JSON schema copies (`mthds-schema-sync` skill), MTHDS spec native-concept + inputs-format sections.
- **Authoring-guidance surfaces** — `mthds-plugins` skills (`mthds-inputs`, `mthds-build`), `vscode-pipelex` completion lists, and the `ConceptSpec.refines` native-list hint (derive from `NativeConceptCode` — `refines-hint-native-list-drift.md`).
- **Off critical path** — LLM-assisted input adaptation (design §8, opt-in); the shared YesNo/Date scalar-native LLM-output ergonomics.

---

## Micro-decisions log

_(append settled decisions here as phases land — mirrors the Date/YesNo plans)_

- Shaper location & shape: **module `pipelex/core/memory/input_shaper.py`, class `InputShaper`** (design D7). Reuses `StuffContentFactory` / `is_compatible` / the existing `StuffFactory` fallback — the new code is only the top-down dispatch.
- Concept-nature resolution: **a local `resolve_input_kind(concept) -> InputKind` in the shaper**, composed from ordered `is_compatible(…, strict=True)` checks (no in-tree "which family" helper exists to reuse).
- D8 home: **the shaper** (holds both provided dict and specs). Severity **error** by default (see Gaps).
- D10: **not a blocker** — `PipelineInputs` is a runtime-unvalidated `TypeAlias`, so bare scalars reach the shaper at runtime; the widening is release-gated type-honesty.
- Out-of-matrix natives (Html/JSON/Page/TextAndImages/SearchResult/Composite): **bottom-up fallback** (see Gaps — confirm).
- D3 path resolution: **signature-aware CLI resolver** recommended; exact mechanism settled as Phase 3's first task (see Gaps).

**Phase 1 (2026-07-07) — settled while building the shaper:**

- **Explicit forms unified into one post-hoc-compat path.** Envelope `{concept, content}` dict, `DictStuff`, and directly-provided `StuffContent`/`ListContent` all route to one `_shape_explicit`: build via `StuffFactory.make_stuff_from_stuff_content_or_data` (today's behavior, so the explicit — possibly more-specific — concept wins), then `is_compatible(tested=built.concept, wanted=declared)`; incompatible → D4 `ExplicitConceptIncompatibleError`. Chosen over pre-resolving the envelope's concept ref because `DictStuff.concept` may be a `DictConcept` object, not a str — pre-resolution was fragile. Trade-off: an envelope naming a concept that is *both* incompatible *and* unbuildable surfaces StuffFactory's build error first (not D4); the buildable-but-incompatible case (the interesting one) gives D4. Acceptable.
- **Scalar building via canonical-dict-wrap — zero changes to `StuffContentFactory`.** Each arm wraps the bare value into the structure class's canonical field dict (`{"text": v}` / `{"number": v}` / `{"url": v}`; date/str and bool passed through directly since `make_content_from_value` already honors those), then calls `StuffContentFactory.make_stuff_content_from_concept_required(concept, value=…)`. This makes a Text/Number-**refining** subclass build correctly (e.g. `Question(text=…)`, `Priority(number=…)`) without touching `make_content_from_value` (whose str-arm still uses `== TextContent`, not `issubclass`). Consequence: the `scalar-envelope-arm-asymmetry.md` note stays deferred — the shaper's **bare** path now builds the refining subclass, but the **envelope** escape hatch still delegates to `StuffFactory` Case 2.1c which builds a plain `TextContent` (concept kept, content not the subclass). Flag for Phase 5 triage.
- **`value` typed `Any` inside the shaper.** The public `shape(pipeline_inputs: PipelineInputs, …)` keeps the declared contract, but internal value params are `Any` because the runtime admits bare `int`/`float`/`bool`/`None`/list-of-dicts that the narrow `PipelineInputs`/`StuffContentOrData` alias does not (D10 widening is release-gated). This is what lets the D9 null guard and the Number/scalar arms be reachable without pyright flagging them unreachable.
- **`InputKind` keeps a `DYNAMIC` member; the per-item builder has one guarded unreachable branch.** `_shape_one` short-circuits `DYNAMIC` to the bottom-up factory before multiplicity peeling, so `_build_item_content` never sees `DYNAMIC` — but its `match` over `InputKind` stays exhaustive (house rule: no `case _`) with a `DYNAMIC` arm that raises `PipelexUnexpectedError`. Justified exhaustive-match guard, not an impossible-input guard on caller data.
- **`resolve_input_kind` order:** `is_dynamic_concept` short-circuit → ordered strict `is_compatible` against YesNo, Date, Number, Image, Document, Text (mutually exclusive natives, order safe) → non-native `StructuredContent` subclass → `STRUCTURED`; else `DYNAMIC` (covers out-of-matrix natives Html/JSON/Page/TextAndImages/SearchResult/Composite/Anything and any unregistered class, via a `ConceptValueError` catch).
