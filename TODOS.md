# Optionals phase 1 — live tracker

Branch `feature/Optionals` (worktree `_optionals`). This file is the single live tracker: progress checkboxes, checkpoint log, decisions/deviations. Reference docs: `wip/optionals-design.md` (decisions D1–D11, all decided) and `wip/optionals-plan.md` (the narrative plan this tracker implements — steps A–F map one-to-one).

Working rules: TDD (red tests first per step), `make agent-check` after every code change, full `make agent-test` at each checkpoint, **one commit per checkpoint**, no backward compatibility (breaking changes go in the changelog under `[Unreleased]`).

## Cold-start context (update at every checkpoint)

- **Status:** Step B DONE (Checkpoint B cleared). Commit `6c258e2ba` on `feature/Optionals` (Step A was `ae4ace79e` + `80c4e56f6`). Absence is now a recorded runtime fact: `AbsenceRecord`/`AbsenceKind` in `pipelex/core/memory/absence.py`, ledger on `WorkingMemory.absences` (+ `record_absence`, `record_new_main_absence`, `get_optional_absence`, tri-state `resolve_stuff`/`resolve_main_stuff`). The trichotomy lives in `PipeAbstract._scan_input_presence` + `validate_before_run` (which now RETURNS the scan; `_run_pipe_traced` lifts via `_make_lifted_output` when `liftable` is non-empty). `OptionalValueAbsentError` (RUNTIME domain, provenance chain, error page generated) in `pipelex/core/pipes/inputs/exceptions.py`. SubPipe + PipeCondition miss-gates tolerate recorded absences; plural skip normalizes to empty `ListContent` + ledger note; `prepare_pipe_job` seeds not-provided records for omitted `?` method inputs (after mock filling, so dry stays all-present); tracer epilogue handles resolved-as-absent (`output_spec=None`). `make agent-check` + full `make agent-test` green.
- **Next action:** Step C — controllers: `continue` replacement (breaking, rewrite `test_pipe_condition_continue_delivery.py`) + PipeParallel combine under absence (D11) + delivery executor absent-main arm (moved up from Step E).
- **Key carriers for Step C:** `PipeCondition._live_run_controller_pipe` continue arm currently pass-through-or-error (and the dry-run all-special-outcomes guard) — replace with `working_memory.record_new_main_absence(AbsenceRecord(kind=DECLARED_ABSENT, ...))` + success; the D6 static rule (`continue`-reachable ⇒ `?` output) is Step D. `delivery_executor.py` typed + raw arms still raise on absent main output — they land in Step C because the rewritten continue tests exercise delivery. PipeParallel combine: `validate_output_with_library` + `combine_stuffs` feed points.
- **Open questions for Louis:** none blocking. Standing flagged compromise: `continue` pass-through breaks in phase 1 while its ergonomic replacement (`??` coalescing) is phase 2 — restructure only if Louis asks.

## Checkpoint protocol — MANDATORY STOP at every CHECKPOINT

At each checkpoint the agent MUST stop forward progress and run this sequence, in order. No rolling into the next step with the checkpoint half-done.

1. **Verify:** full `make agent-check` + `make agent-test` green (`make tb` too if config files were touched). Fix failures before anything else.
2. **Commit:** one commit for the step (changelog entry included when the step is user-visible/breaking).
3. **Update this file:** tick the boxes, fill the checkpoint log row (SHA), and refresh "Cold-start context" — decisions taken, deviations from the plan, open questions, exact next action — so a brand-new session can resume efficiently from this file alone. If a design decision changed, update `wip/optionals-design.md`/`wip/optionals-plan.md` too.
4. **Fan out a context-free code review:** spawn a **Sonnet-5 sub-agent with NO inherited context** (general-purpose agent, `model: sonnet` — never a fork) whose prompt is ONLY a pointer to the changes under review plus the instruction to run the `/code-review` skill. Example prompt: *"In /Users/lchoquel/repos/Pipelex/_optionals, run the /code-review skill on `git diff <previous-checkpoint-SHA>..HEAD`. Report findings."* Do **not** pass the plan, the design doc, the rationale, or your own conclusions — the reviewer judges the code cold. Review bar: clean solid software, not over-engineering.
5. **Triage findings:** correctness bugs → fix now (amend or follow-up commit, re-run gates). Design-tradeoff findings → do not reflexively apply; record in a deferred-items doc under `wip/optionals/` and move on. Over-engineering findings → simplify now.
6. Only then proceed to the next step.

## Prep

- [x] Commit this tracker (+ staged old-TODOS deletion). Record the SHA as the Step-A review base in the checkpoint log. *(Turned out already done: the tracker landed in `eace1d607`.)*

## Step A — grammar and carriers (parse `?` / `!`, no behavior change)

- [x] Red tests first: parser unit tests for every marker × multiplicity combination; blueprint + spec accept/reject fixtures.
- [x] Extend the marker grammar (D1) in `pipelex/core/pipes/variable_multiplicity.py` (+ its inline twin), the looser regex in `input_stuff_specs_factory.py`, and the naive `[`-splitter in `concepts/helpers.py`. Fix the `MUTLIPLICITY_PATTERN` typo while there.
- [x] `StuffSpec`/`NamedStuffSpec` gain the presence marker (a `PresenceMarker` StrEnum: plain / optional / force); `InputStuffSpecs.required_names` splits into required vs declared.
- [x] Blueprint-parse-time grammar errors (`OPTIONAL_MARKER_INVALID`): `?` on plurals, `!` on outputs or plurals, markers on concept definitions / `refines` / structure-field refs / package refs (D1, D4).
- [x] Builder specs mirror the blueprint rules (`to_blueprint()` passes markers through); `contract_match` canonicalization compares presence markers (D5).
- [x] **CHECKPOINT A** — markers parse, validate, and round-trip; zero runtime behavior change; run the full checkpoint protocol above.

## Step B — absence at runtime (ledger + trichotomy + lifting)

- [x] Red tests first: lift-skip chain with provenance, absorb, force-failure UX (assert the message names variable, pipes, and reason), plural normalization, optional method inputs, run-report absence enumeration. All tests sink absence before the method boundary (a downstream `?` input) — end-to-end absent-main-output coverage is Step E's.
- [x] WorkingMemory gains the absence ledger (D2): `AbsenceRecord` (`variable_name`, `producing_pipe`, `kind` = declared-absent | skipped | not-provided, `reason`, upstream chain). New tri-state resolved accessor (Stuff | AbsenceRecord) for post-run reads — do **not** resurrect `optional_main_stuff` (design §14).
- [x] The three runtime miss-gates learn the trichotomy (D3): `PipeAbstract.validate_before_run` (fix the "Dry run of ..." message bug on the live path), `SubPipe`, PipeCondition's branch check. Plain input fed absence → **skip** (lift) + record skipped-absence for the pipe's output with provenance; `?` input → run; `!` input absent → `OptionalValueAbsentError` (D9: new error class in the relevant `exceptions.py`, provenance chain, RFC 7807 + error page via `pipelex-dev generate-error-pages`).
- [x] The per-pipe graph-tracer epilogue in `pipe_abstract.py` (success path reads `working_memory.get_main_stuff()` directly) learns the resolved-as-absent arm **here, not in Step E** — it fires on every pipe run, so the first skipped pipe would crash it.
- [x] Skipped plural output normalizes to empty `ListContent` + ledger note (D4); taint stops.
- [x] Optional method inputs (D5): omitting a `?` input in `inputs.json` / the execute request → not-provided record instead of `PipeRunInputsError`; the required-input error message gains the "these optional inputs may be omitted" hint.
- [x] Mock seeding / dry-run sweep learn optional slots (dry run stays all-present per D6): mock seeding already enumerates every declared input including `?` ones (all-present); pinned by test, and not-provided records are only written for slots the mock pass left empty.
- [x] **CHECKPOINT B** — absence exists, propagates, and fails loudly only through `!`; run the full checkpoint protocol.

## Step C — controllers: `continue` replacement + parallel combine (D11)

- [ ] Red tests first: continue-absent (live + dry), parallel with absorbed/omitted/required-absent branches, batch compaction if shipped.
- [ ] **PipeCondition `continue`** (design §14, breaking): replace pass-through-or-error with "declared output absent, memory otherwise unchanged" — record the absence (kind = declared-absent, reason = the evaluated expression/outcome), stamp no main stuff, return success. Same in dry run (the all-special-outcomes guard becomes: legal iff output declared `?`). Rewrite `test_pipe_condition_continue_delivery.py` to pin the new semantics (keep the run-id stamping assertions).
- [ ] These tests exercise the delivery boundary, so `delivery_executor.py` (typed + raw arms: absent main output delivers an explicit absence artifact, not an error) lands **here, not in Step E**.
- [ ] Document the migration idiom (previous value stays in memory under its own name; coalescing is the phase-2 answer) in docs + changelog (breaking).
- [ ] **PipeParallel combine under absence** (D11): absent branch result → structured output field with `required = false` absorbs as field-`None`; `Composite` output omits the component + ledger note. Runtime guard raises a typed error if a required field's branch is absent (statically unreachable after Step D, but the runtime must not feed `combine_stuffs` a hole). **Checkpoint-B review pinned the entry points:** `pipe_parallel.py` `_run_branches_and_combine` (`pipe_output.main_stuff` — the raising accessor) crashes today on a lifted branch (`WorkingMemoryStuffNotFoundError`, reproduced); `pipe_batch.py` has the identical shape at its branch-collect loop and in `_dry_run_controller_pipe`. Both must move to the tri-state `resolve_main_stuff()` with the D11 policy.
- [ ] PipeBatch compaction (D4 bonus): inner `?` output → absent branch results dropped from the aggregated list. Ship it here if it falls out of the lifting machinery naturally; otherwise defer to phase 2 with the semantics recorded in the design doc.
- [ ] **CHECKPOINT C** — controllers speak absence; the #1014 `continue` tests replaced; run the full checkpoint protocol.

## Step D — static validation: the taint pass + template lint

- [ ] Red tests first: taint fixtures (valid + each error type), guard-lint accept/reject, `@?` detection.
- [ ] Absence-propagation pass over controller dataflow (D6): `PipeSequence.needed_inputs` / `generated_outputs` gain the presence dimension; per-slot presence computed (`guaranteed` / `maybe-absent`).
- [ ] New `PipeValidationErrorType`s: `OPTIONAL_NOT_HANDLED` (taint reaches a non-optional boundary — message names source, path, three fixes), `OPTIONAL_OUTPUT_REQUIRED` (`continue`-reachable condition without `?` output), the D11 static error (required structure field fed by a maybe-absent branch, extending `validate_output_with_library` checks).
- [ ] Template guard-lint (D7): classify guarded vs unguarded references to declared-optional inputs in the Jinja AST walk — guards include `{% if var %}` blocks, inline `is defined` conditionals, and `@?var`; unguarded → validation error with the precise fix. Fix `@?` so it no longer registers a declared-optional variable as required.
- [ ] Liftable-pipe inventory as structured data on the valid report (D3 phase-1 commitment), beside `pipe_io_contracts`.
- [ ] **CHECKPOINT D** — validation proves the safety theorem ("every absence source reaches an explicit sink"); run the full checkpoint protocol.

## Step E — wire, boundaries, and graph

- [ ] Red tests first: end-to-end absent-main-output run over each surface (delivery artifacts, execute response, CLI output, telemetry), graph skipped-state serialization.
- [ ] Protocol bump, one motion (D6 + D8): `optional: bool` on `PipeInputContract`/`PipeOutputContract`, the general `warnings` array on the validation report (same item shape as errors, never flips `is_valid`), absence records on run results. Neutral MTHDS naming, no `pipelex_` prefixes.
- [ ] Populate `warnings` with the useless-`!` lint (`!` on a guaranteed slot — presence data from Step D's taint pass). The over-claimed-`?` lint is deliberately **not** emitted in phase 1 (D5 blesses over-claiming as evolution room; phase 2 makes `?` on operator outputs meaningful).
- [ ] The remaining post-run boundaries learn the resolved-as-absent arm (design §14 checklist; tracer epilogue done in Step B, delivery executor in Step C): CLI run cores (bare, agent, agent-API), `otel_factory.py`, `resolve_main_stuff_root_key` / `payloads.py` / `pipeline_response.py`. `main_stuff_name: str` **stays required** — it names the declared output slot; consumers branch on the absence record. Absent main output = success with an absent result.
- [ ] Graph (D8): `GraphSpec` gains the `skipped` node state and optional-edge marker; tracer registers skip reasons. (mthds-ui rendering is the cross-repo wave.)
- [ ] Sweep the invariant prose to "a pipe run always resolves its declared output: a value or a recorded absence".
- [ ] **CHECKPOINT E** — an absent result is a first-class success everywhere in-repo; run the full checkpoint protocol.

## Step F — specs, conformance, docs, release prep

- [ ] `docs/specs/` protocol spec: `optional` flag, `warnings` array, absence records, new validation-error categories; matching `conformance/` fixtures (`optional_not_handled.mthds` etc.) + error-QA corpus rows; `make check-spec-links` green (run in `conformance/`).
- [ ] Regenerate the MTHDS JSON schema (`pipelex-dev generate-mthds-schema`) and error pages; docs: an optionality guide beside `multiplicity.md`'s pipelex counterpart, pipe-page updates (PipeCondition, PipeParallel, PipeBatch), `@?` docs reconciled.
- [ ] Changelog under `[Unreleased]`: breaking — `continue` semantics, `?`/`!` grammar, protocol additions.
- [ ] Full `make agent-test` + `make tb`.
- [ ] **FINAL CHECKPOINT** — phase 1 complete; run the full checkpoint protocol. Hand off: cross-repo wave (after the Required-main-stuff Phase 3 sweep) and phase 2 (LLM maybe-wrapper). Fold or close this tracker and `wip/optionals-plan.md`.

## Checkpoint log

| Checkpoint | Commit SHA | Review verdict | Notes |
|---|---|---|---|
| Prep | `eace1d607` | n/a | Tracker was committed alongside the plan update; serves as the Step-A review base. |
| A | `ae4ace79e` | Clean — no findings at reporting confidence | Cold Sonnet review of `eace1d607..HEAD`. Two sub-threshold doc-in-code notes applied in the follow-up commit (PipeSpec authoring-surface descriptions teach `?`/`!`; enum comment covers all three trigger cases); third note (factory doesn't re-enforce mutual exclusion) = deliberate layering, see deviations log. |
| B | `6c258e2ba` | 4 findings, all triaged | Cold Sonnet review of `80c4e56f6..HEAD`. (1)+(2) PipeParallel/PipeBatch crash (`get_main_stuff` raise) on a lifted branch — CONFIRMED reachable, but it is exactly the already-planned Step C work (D11 combine-under-absence + batch compaction); pinned explicitly in the Step C bullets. (3) delivery executor generic error on an unsunk lift chain — the plan's explicit Step C boundary (delivery arms land there). (4) duplicated miss-gate check → hoisted to `WorkingMemory.list_missing_names` in the checkpoint commit. |
| C | — | | |
| D | — | | |
| E | — | | |
| F (final) | — | | |

## Decisions & deviations log

(fill at checkpoints — anything done differently from `wip/optionals-plan.md`, with why)

- **Step A — parser is combo-permissive; validators own the mutual-exclusion rule.** `parse_concept_with_multiplicity` accepts `X[]?` (multiplicity + marker) and returns both; the D1 v1 rule (markers mutually exclusive with multiplicity) is enforced at the blueprint/spec layer where the input-vs-output context is known, raising the typed `OPTIONAL_MARKER_INVALID`. Rejecting in the parser would have degraded those cases to untyped syntax errors.
- **Step A — `OPTIONAL_MARKER_INVALID` is a `PipeValidationErrorType` raised as `PipeValidationError` inside blueprint validators**, riding the existing pydantic-unwrap machinery (`extract_wrapped_pipe_validation_error`) exactly like `BATCH_ITEM_NAME_COLLISION`. No categorizer change needed.
- **Step A — the naive `[`-splitter was renamed** `strip_multiplicity_from_concept_ref_or_code` → `strip_markers_from_concept_ref_or_code` (it now strips presence markers too; the old name would have lied). Internal helper, single caller (`pipe_factory`).
- **Step A — runtime gates pinned to `declared_names`.** The three `pipe_abstract` enumeration sites + `pipe_extract.required_variables` now use `declared_names` (all inputs), so an input declared `?` is still enforced-present at run time in Step A — exact current behavior preserved; Step B flips the gates to the trichotomy.
- **Step A — derived batch-list needs stay presence-plain.** In `pipe_parallel`/`pipe_sequence`, the computed list-input specs that override `multiplicity=True` (batch `input_list_name` derivation) do not carry the inner spec's presence (a plural + marker combo is exactly what D4 forbids); all pass-through `add_stuff_spec` sites carry `presence=stuff_spec.presence`.
- **Step A — two stale fixtures updated**, since a trailing `!` is now legal grammar: `test_pipe_blueprint.py` invalid-syntax cases switched to genuinely malformed specs (`Invalid@Format`, `Invalid@Concept`).
- **Step B — the lift gate reads the pipe's OWN declared presence, not the needed-aggregation.** A controller's `needed_inputs()` carries its children's markers (a sequence over a step needing `X` plain aggregates `X` plain even when the sequence declares `X?`). Lifting on the aggregated marker would skip the whole controller instead of letting its steps lift. `_scan_input_presence` therefore prefers `self.inputs.root[name].presence` (the boundary contract, D5 "boundaries explicit") and falls back to the needed spec's marker. Consequence: whole-controller lifting still happens when the author declares the input plain at the controller boundary — which is the intended semantics.
- **Step B — the declared-vs-needed controller input check no longer compares presence markers.** With presence on `StuffSpec`, the old full-model `!=` would have rejected exactly the legal D3 shapes (controller `X?` over child-needed `X` plain) with an empty mismatch summary. The check now compares concept + multiplicity explicitly; presence relationships across the boundary are all legal per the trichotomy (Step D's taint pass reasons about them).
- **Step B — `validate_before_run` returns the presence scan** (`InputPresenceScan`: missing / forced-absent / liftable) instead of `None`; it owns all three raise cases (force → `OptionalValueAbsentError`, missing-no-record → `PipeRunInputsError` with the run-mode-correct label + optional-inputs hint) and skips resource checks + per-pipe `_validate_before_run` when the pipe is about to be lifted (pipe-specific validation would inspect inputs the pipe never consumes — e.g. PipeCondition's expression render would crash on the absent var).
- **Step B — value-supersedes-record invariant:** `set_stuff` pops the absence record under the written name; `set_new_main_stuff` also pops the positional `main_stuff` record. The D4 plural note is written AFTER the empty list so it survives as an observability note (stuff wins in `resolve_stuff`).
- **Step B — lifting applies in dry mode too** (uniform gate): records never exist in today's dry sweeps (mock seeding is all-present per D6), so this is unreachable until Step C's continue-under-dry work, which will pin the dry semantics.
- **Step B — sequence test builds pipes in code** (`get_pipe_library().add_new_pipe`) instead of an `.mthds` fixture: a bundle declaring `PipeFunc`s can't validate standalone (the functions aren't registered in the validation hook's process).
