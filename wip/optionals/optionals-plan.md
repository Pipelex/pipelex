# Optionals — phase-1 implementation plan (CLOSED — phase 1 complete)

> **Status: COMPLETE.** All steps A–F landed and the FINAL CHECKPOINT cleared — the tracker holding the checkpoint log + hand-off notes is kept at workspace level. Live follow-ups: the release-time spec-suite gate removal and cross-repo wave items in `wip/optionals/deferred-step-f-notes.md`. This document is kept as the narrative record; `wip/optionals/optionals-design.md` remains the design reference (incl. phases 2–3).

Branch `feature/Optionals` (worktree `_optionals`). Design: `wip/optionals/optionals-design.md` — all decisions D1–D11 decided. This plan covers **phase 1 of §17**: the complete language core in pipelex, with the protocol spec and our cross-repo spec suite moving in the same change. The LLM maybe-wrapper (phase 2) and ergonomics (phase 3) are out of scope; the cross-repo wave (mthds spec, vscode/plxt, mthds-ui, skills) follows the pipelex release and must land **after** the Required-main-stuff Phase 3 sweep.

Working rules: TDD (red tests first per step), `make agent-check` after every code change, full `make agent-test` at each checkpoint, one commit per checkpoint, no backward compatibility (breaking changes go in the changelog under `[Unreleased]`).

Live progress tracking (checkboxes, checkpoint log, decisions/deviations) was in `TODOS.md` at the worktree root, now archived as the phase-1 tracker at workspace level; this document stays the narrative plan.

## Step A — grammar and carriers (parse `?` / `!`, no behavior change)

- Extend the marker grammar (D1) in `pipelex/core/pipes/variable_multiplicity.py` (+ its inline twin), the looser regex in `input_stuff_specs_factory.py`, and the naive `[`-splitter in `concepts/helpers.py`. Fix the `MUTLIPLICITY_PATTERN` typo while there.
- `StuffSpec`/`NamedStuffSpec` gain the presence marker (a `PresenceMarker` StrEnum: plain / optional / force); `InputStuffSpecs.required_names` splits into required vs declared.
- Blueprint-parse-time grammar errors (`OPTIONAL_MARKER_INVALID`): `?` on plurals, `!` on outputs or plurals, markers on concept definitions / `refines` / structure-field refs / package refs (D1, D4).
- Builder specs mirror the blueprint rules (`to_blueprint()` passes markers through); `contract_match` canonicalization compares presence markers (D5).
- Tests: parser unit tests for every marker × multiplicity combination, blueprint + spec accept/reject fixtures.

**CHECKPOINT A** — markers parse, validate, and round-trip; zero runtime behavior change; all gates green; run the checkpoint protocol from the phase-1 tracker (kept at workspace level).

## Step B — absence at runtime (ledger + trichotomy + lifting)

- WorkingMemory gains the absence ledger (D2): `AbsenceRecord` (`variable_name`, `producing_pipe`, `kind` = declared-absent | skipped | not-provided, `reason`, upstream chain). New tri-state resolved accessor (Stuff | AbsenceRecord) for post-run reads — do **not** resurrect `optional_main_stuff` (§14).
- The three runtime miss-gates learn the trichotomy (D3): `PipeAbstract.validate_before_run` (fix the "Dry run of ..." message bug on the live path), `SubPipe`, PipeCondition's branch check. Plain input fed absence → **skip** (lift) + record skipped-absence for the pipe's output with provenance; `?` input → run; `!` input absent → `OptionalValueAbsentError` (D9: new error class in the relevant `exceptions.py`, provenance chain, RFC 7807 + error page via `pipelex-dev generate-error-pages`).
- The per-pipe graph-tracer epilogue in `pipe_abstract.py` (the success path reads `working_memory.get_main_stuff()` directly) learns the resolved-as-absent arm **here, not in Step E** — it fires on every pipe run, so the first skipped pipe would crash it. The method-level boundaries (delivery, CLI, telemetry, serialization) still land in Steps C/E, so Step B tests sink every absence before the method boundary (a downstream `?` input); end-to-end absent-main-output coverage belongs to Step E.
- Skipped plural output normalizes to empty `ListContent` + ledger note (D4); taint stops.
- Optional method inputs (D5): omitting a `?` input in `inputs.json` / the execute request → not-provided record instead of `PipeRunInputsError`; the required-input error message gains the "these optional inputs may be omitted" hint.
- Mock seeding / dry-run sweep learn optional slots (dry run stays all-present per D6).
- Tests: lift-skip chain with provenance, absorb, force-failure UX (assert the message names variable, pipes, and reason), plural normalization, optional method inputs, run-report absence enumeration.

**CHECKPOINT B** — absence exists, propagates, and fails loudly only through `!`; all gates green; run the checkpoint protocol from the phase-1 tracker (kept at workspace level).

## Step C — controllers: `continue` replacement + parallel combine (D11)

- **PipeCondition `continue`** (§14): replace pass-through-or-error with "declared output absent, memory otherwise unchanged" — record the absence (kind = declared-absent, reason = the evaluated expression/outcome), stamp no main stuff, return success. Same in dry run (the all-special-outcomes guard becomes: legal iff output declared `?`). Rewrite `test_pipe_condition_continue_delivery.py` to pin the new semantics (keep the run-id stamping assertions) — these tests exercise the delivery boundary, so `delivery_executor.py` (typed + raw arms: absent main output delivers an explicit absence artifact, not an error) moves up from Step E into this step. Document the migration idiom (previous value stays in memory under its own name; coalescing is the phase-2 answer).
- **PipeParallel combine under absence** (D11): absent branch result → structured output field with `required = false` absorbs as field-`None`; `Composite` output omits the component + ledger note. Runtime guard raises a typed error if a required field's branch is absent (should be statically unreachable after Step D, but the runtime must not feed `combine_stuffs` a hole).
- PipeBatch compaction (D4 bonus): inner `?` output → absent branch results dropped from the aggregated list. Ship it here if it falls out of the lifting machinery naturally; otherwise defer to phase 2 with the semantics recorded.
- Tests: continue-absent (live + dry), parallel with absorbed/omitted/required-absent branches, batch compaction if shipped.

**CHECKPOINT C** — controllers speak absence; the #1014 `continue` tests replaced; all gates green; run the checkpoint protocol from the phase-1 tracker (kept at workspace level).

## Step D — static validation: the taint pass + template lint

- Absence-propagation pass over controller dataflow (D6): `PipeSequence.needed_inputs` / `generated_outputs` gain the presence dimension; per-slot presence computed (`guaranteed` / `maybe-absent`).
- New `PipeValidationErrorType`s: `OPTIONAL_NOT_HANDLED` (taint reaches a non-optional boundary — message names source, path, three fixes), `OPTIONAL_OUTPUT_REQUIRED` (`continue`-reachable condition without `?` output), the D11 static error (required structure field fed by a maybe-absent branch, extending #1014's `validate_output_with_library` checks).
- Template guard-lint (D7): classify guarded vs unguarded references to declared-optional inputs in the Jinja AST walk; unguarded → validation error with the precise fix. Fix `@?` so it no longer registers a declared-optional variable as required.
- Liftable-pipe inventory as structured data on the valid report (D3 phase-1 commitment), beside `pipe_io_contracts`.
- Tests: taint fixtures (valid + each error type), guard-lint accept/reject, `@?` detection.

**CHECKPOINT D** — validation proves the safety theorem ("every absence source reaches an explicit sink"); all gates green; run the checkpoint protocol from the phase-1 tracker (kept at workspace level).

## Step E — wire, boundaries, and graph

- Protocol bump, one motion (D6 + D8): `optional: bool` on `PipeInputContract`/`PipeOutputContract`, the general `warnings` array on the validation report (same item shape as errors, never flips `is_valid`), absence records on run results. Neutral MTHDS naming, no `pipelex_` prefixes.
- Populate `warnings` with the useless-`!` lint (`!` on a guaranteed slot — presence data comes from Step D's taint pass). The over-claimed-`?` lint (a `?` output that can never produce absence) is deliberately **not** emitted in phase 1: D5 blesses over-claiming as signature-evolution room, and phase 2 makes `?` on operator outputs meaningful — linting it now would warn on exactly the declarations phase 2 rewards.
- The remaining post-run boundaries learn the resolved-as-absent arm (§14 checklist; the tracer epilogue is handled in Step B, the delivery executor in Step C): CLI run cores (bare, agent, agent-API), `otel_factory.py`, `resolve_main_stuff_root_key` / `payloads.py` / `pipeline_response.py`. `main_stuff_name: str` **stays required** — it names the declared output slot; consumers branch on the absence record. Absent main output = success with an absent result.
- Graph (D8): `GraphSpec` gains the `skipped` node state and optional-edge marker; tracer registers skip reasons. (mthds-ui rendering is the cross-repo wave.)
- Sweep the invariant prose to "a pipe run always resolves its declared output: a value or a recorded absence".
- Tests: end-to-end absent-main-output run over each surface (delivery artifacts, execute response, CLI output, telemetry), graph skipped-state serialization.

**CHECKPOINT E** — an absent result is a first-class success everywhere in-repo; all gates green; run the checkpoint protocol from the phase-1 tracker (kept at workspace level).

## Step F — specs, spec suite, docs, release prep

- Protocol spec: `optional` flag, `warnings` array, absence records, new validation-error categories; matching fixtures (`optional_not_handled.mthds` etc.) + error-QA corpus rows in our cross-repo spec suite; the spec-link check green.
- Regenerate the MTHDS JSON schema and error pages; docs: an optionality guide beside `multiplicity.md`'s pipelex counterpart, pipe-page updates (PipeCondition, PipeParallel, PipeBatch), `@?` docs reconciled.
- Changelog under `[Unreleased]`: breaking — `continue` semantics, `?`/`!` grammar, protocol additions.
- Full `make agent-test` + `make tb`.

**FINAL CHECKPOINT** — phase 1 complete; hand off to the cross-repo wave (after RMS Phase 3) and phase 2 (LLM maybe-wrapper). Close or fold this doc.
