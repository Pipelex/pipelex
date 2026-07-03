# Optionals phase 1 — live tracker

Branch `feature/Optionals` (worktree `_optionals`). This file is the single live tracker: progress checkboxes, checkpoint log, decisions/deviations. Reference docs: `wip/optionals-design.md` (decisions D1–D11, all decided) and `wip/optionals-plan.md` (the narrative plan this tracker implements — steps A–F map one-to-one).

Working rules: TDD (red tests first per step), `make agent-check` after every code change, full `make agent-test` at each checkpoint, **one commit per checkpoint**, no backward compatibility (breaking changes go in the changelog under `[Unreleased]`).

## Cold-start context (update at every checkpoint)

- **Status:** not started. Phase-1 base = `6708593e4` (design + plan committed; this tracker not yet committed).
- **Next action:** prep commit (this tracker), then Step A.
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

- [ ] Commit this tracker (+ staged old-TODOS deletion). Record the SHA as the Step-A review base in the checkpoint log.

## Step A — grammar and carriers (parse `?` / `!`, no behavior change)

- [ ] Red tests first: parser unit tests for every marker × multiplicity combination; blueprint + spec accept/reject fixtures.
- [ ] Extend the marker grammar (D1) in `pipelex/core/pipes/variable_multiplicity.py` (+ its inline twin), the looser regex in `input_stuff_specs_factory.py`, and the naive `[`-splitter in `concepts/helpers.py`. Fix the `MUTLIPLICITY_PATTERN` typo while there.
- [ ] `StuffSpec`/`NamedStuffSpec` gain the presence marker (a `PresenceMarker` StrEnum: plain / optional / force); `InputStuffSpecs.required_names` splits into required vs declared.
- [ ] Blueprint-parse-time grammar errors (`OPTIONAL_MARKER_INVALID`): `?` on plurals, `!` on outputs or plurals, markers on concept definitions / `refines` / structure-field refs / package refs (D1, D4).
- [ ] Builder specs mirror the blueprint rules (`to_blueprint()` passes markers through); `contract_match` canonicalization compares presence markers (D5).
- [ ] **CHECKPOINT A** — markers parse, validate, and round-trip; zero runtime behavior change; run the full checkpoint protocol above.

## Step B — absence at runtime (ledger + trichotomy + lifting)

- [ ] Red tests first: lift-skip chain with provenance, absorb, force-failure UX (assert the message names variable, pipes, and reason), plural normalization, optional method inputs, run-report absence enumeration. All tests sink absence before the method boundary (a downstream `?` input) — end-to-end absent-main-output coverage is Step E's.
- [ ] WorkingMemory gains the absence ledger (D2): `AbsenceRecord` (`variable_name`, `producing_pipe`, `kind` = declared-absent | skipped | not-provided, `reason`, upstream chain). New tri-state resolved accessor (Stuff | AbsenceRecord) for post-run reads — do **not** resurrect `optional_main_stuff` (design §14).
- [ ] The three runtime miss-gates learn the trichotomy (D3): `PipeAbstract.validate_before_run` (fix the "Dry run of ..." message bug on the live path), `SubPipe`, PipeCondition's branch check. Plain input fed absence → **skip** (lift) + record skipped-absence for the pipe's output with provenance; `?` input → run; `!` input absent → `OptionalValueAbsentError` (D9: new error class in the relevant `exceptions.py`, provenance chain, RFC 7807 + error page via `pipelex-dev generate-error-pages`).
- [ ] The per-pipe graph-tracer epilogue in `pipe_abstract.py` (success path reads `working_memory.get_main_stuff()` directly) learns the resolved-as-absent arm **here, not in Step E** — it fires on every pipe run, so the first skipped pipe would crash it.
- [ ] Skipped plural output normalizes to empty `ListContent` + ledger note (D4); taint stops.
- [ ] Optional method inputs (D5): omitting a `?` input in `inputs.json` / the execute request → not-provided record instead of `PipeRunInputsError`; the required-input error message gains the "these optional inputs may be omitted" hint.
- [ ] Mock seeding / dry-run sweep learn optional slots (dry run stays all-present per D6).
- [ ] **CHECKPOINT B** — absence exists, propagates, and fails loudly only through `!`; run the full checkpoint protocol.

## Step C — controllers: `continue` replacement + parallel combine (D11)

- [ ] Red tests first: continue-absent (live + dry), parallel with absorbed/omitted/required-absent branches, batch compaction if shipped.
- [ ] **PipeCondition `continue`** (design §14, breaking): replace pass-through-or-error with "declared output absent, memory otherwise unchanged" — record the absence (kind = declared-absent, reason = the evaluated expression/outcome), stamp no main stuff, return success. Same in dry run (the all-special-outcomes guard becomes: legal iff output declared `?`). Rewrite `test_pipe_condition_continue_delivery.py` to pin the new semantics (keep the run-id stamping assertions).
- [ ] These tests exercise the delivery boundary, so `delivery_executor.py` (typed + raw arms: absent main output delivers an explicit absence artifact, not an error) lands **here, not in Step E**.
- [ ] Document the migration idiom (previous value stays in memory under its own name; coalescing is the phase-2 answer) in docs + changelog (breaking).
- [ ] **PipeParallel combine under absence** (D11): absent branch result → structured output field with `required = false` absorbs as field-`None`; `Composite` output omits the component + ledger note. Runtime guard raises a typed error if a required field's branch is absent (statically unreachable after Step D, but the runtime must not feed `combine_stuffs` a hole).
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
| Prep | — | n/a | |
| A | — | | |
| B | — | | |
| C | — | | |
| D | — | | |
| E | — | | |
| F (final) | — | | |

## Decisions & deviations log

(fill at checkpoints — anything done differently from `wip/optionals-plan.md`, with why)
