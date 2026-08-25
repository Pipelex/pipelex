# Vacuous presence lint — implementation tracker

**Design:** [`wip/full-optional/design.md`](wip/full-optional/design.md) — read it first; this tracker assumes its decisions (entry-pipe scope, descriptor substrate, one composition point, the `input_presence_vacuous` wire name, the hint-lint cap riding along) and does not restate the rationale. The three decisions to ratify are its §9.

## Live state — rewrite this block, never append to it

Record only what the tools cannot re-derive: the SHA a step landed in, a decision and its reason, the exact error a gate printed. Never branch, PR or working-tree status.

- **Where the work stands:** design written on 2026-08-25; nothing implemented yet. Next: ratify design §9, then Phase 1.
- **Decisions taken since the design:** none yet.
- **Gates last run green:** not yet run on this work.

## Standing rules

- **Branch:** `feature/Full-optional-lint` off `dev`; the PR targets `dev`. The prefix vocabulary is closed and spelled out (`feature/`, never `feat/`).
- **Tests before code** (red → green) for every rule in the design's decision table; mutation-test a green test by breaking the predicate it guards and watching it go red.
- **Gates before any push:** `make agent-check` and the full `make agent-test` (never `make test`). If the local `.pipelex/pipelex_override.toml` storage override is still in place, the boot tests it reds are pre-existing — move it aside for the full run.
- **Docs in the same change**, changelog under `## [Unreleased]` only, no counts, no mention of `wip/` docs in the changelog.
- **Cross-repo work goes to `../wip/inbox/`** (design §8) at close — never widen this diff into another repo.
- **Update this tracker as work happens:** tick a box the moment its step is done, append a dated line to the progress log after every commit, gate run, decision and surprise, and rewrite the live-state block the moment it stops being true.

## Phase 1 — the lint itself

Pure, unit-tested, not yet wired anywhere.

- [ ] 1.1 Add `PipeValidationErrorType.INPUT_PRESENCE_VACUOUS = "input_presence_vacuous"` with its advisory-only comment beside `OPTIONAL_FORCE_REDUNDANT`; extend the enum's exhaustive `match` properties (`is_controller_input_drift`, `is_inadequate_output`) so pyright stays green; confirm `tests/unit/pipelex/errors/test_validation_error_types.py` picks the member up unchanged.
- [ ] 1.2 Write the unit decision table first, red: `tests/unit/pipelex/pipeline/test_vacuous_presence_warnings.py` over hand-built `PipeInputFormDescriptor`s — one case per row of design §3 (all-optional object warns; one required field is silent; field-less object warns with the variant wording; `?` is silent; variable list silent; fixed-count list silent; every scalar/file kind silent; `unknown` silent), plus: a non-entry pipe with the warning shape is silent, `!` warns and names the marker, output order is by entry pipe ref then authored slot order, and the item shape (category `pipe_validation`, bare `pipe_code`, `domain_code`, `variable_names`, no `concept_code`).
- [ ] 1.3 Implement `pipelex/pipeline/vacuous_presence_warnings.py`: `build_vacuous_presence_warnings(*, input_form, entry_pipe_refs) -> list[ValidationErrorItem]`, the two message variants of design §D7, module docstring stating the rule and the one-level depth.
- [ ] 1.4 Green; mutation-test at least the `gating` read (flip to `required`: the variable-list case must go red) and the `required` scan (drop the empty-fields branch: the field-less case must go red).

## Phase 2 — composition point, entry pipes, every channel

- [ ] 2.1 Add the accumulated-blueprints accessor to `LibraryManagerAbstract` / `LibraryManager` (design §D2). Write the `validate all` test first: a library dir holding a bundle with a `main_pipe` whose gating input is all-optional must produce the warning on the `validate all` envelope — this is the test that proves `_blueprints` is populated on the `acquire_library` path; if it is not, record what you found in the live-state block and decide between populating it and deriving entry refs another way before going on.
- [ ] 2.2 Add `pipelex/pipeline/advisory_warnings.py` (design §D6): `build_advisory_warnings(*, taint_analyses, input_form, entry_pipe_refs, qualified_crate)` pure, and `collect_advisory_warnings(*, pipes, entry_pipe_refs)` gathering the ingredients inside the window (taint walk, descriptor, the current library's crate qualified once). A helper that qualifies every bundle's `main_pipe` with `PipeFactory.make_pipe_ref_with_domain` — the spelling `select_primary_blueprint` uses — lives beside it or in `blueprint_selection.py`.
- [ ] 2.3 Hint-lint prerequisite (design §D6): in `hint_warnings.py`, elide interpolated authored tokens beyond a fixed length and cap findings per site with an "and N more" tail; unit-test both in `test_hint_warnings.py`. Extend the existing cap-free tests only where the cap changes their expectation.
- [ ] 2.4 Switch every site to the composition point: `validate_in_process.py` (pure builder, with the `input_form` and taint analyses it already computes and the entry refs from `result.blueprints`); every site in `cli/agent_cli/commands/validate/_validate_core.py` and in `builder/operations/validate_ops.py`; the bare CLI's `_echo_optionality_warnings` becomes `_echo_advisory_warnings`. Remove the direct `build_optionality_warnings` imports at those sites; fix the docstrings in `validation_report.py` and `base_exceptions.py` that name it as the warnings source.
- [ ] 2.5 Integration tests, protocol path (`tests/integration/pipelex/pipeline/test_protocol_validate.py` or a sibling module): entry pipe with a plain all-optional input warns and the report stays valid and runnable; the same input shape on a non-main pipe of the same bundle is silent; a class-backed concept whose pydantic fields all carry defaults warns; a batch with no `main_pipe` is silent; `?` on the same slot is silent; the hint lint still rides beside it.
- [ ] 2.6 Agent-CLI envelope test for `validate bundle` (the warning rides `warnings`, `is_valid` stays true, exit code unchanged) and the markdown rendering shows it under "Warnings"; builder `validate_bundle_content` twin.
- [ ] 2.7 Verify the three presentation surfaces the engine-hints deferral asked to check now that hint lints reach them: agent-CLI JSON and markdown, bare-CLI yellow echo, builder-ops JSON — one fixture with all three families firing at once, asserting family order and item shape.

**CHECKPOINT 1 — after Phase 2.** Update the live-state block: what the `validate all` test found about blueprint accumulation, any deviation from the design, the gate results. A fresh session should be able to pick up Phase 3 from this file alone.

## Phase 3 — vocabulary, docs, changelog

- [ ] 3.1 `generate_corpus_vocabulary_cmd.py`: add the advisory exclusion for `input_presence_vacuous` (same reason as `optional_force_redundant`); run `make generate-corpus-vocabulary`; confirm the corpus exhaustivity and linter-exclusion gates stay green.
- [ ] 3.2 `docs/building-methods/pipes/understanding-optionality.md`: the `warnings` bullet becomes a short list of the advisory lints (useless `!`, vacuous presence, the intent-hint trio), each with its wire name and one sentence.
- [ ] 3.3 `docs/building-methods/concepts/inline-structures.md`: a note that `required` defaults to `false` in the long form, that the shorthand string field is required, and that an all-optional structure named by a gating method input triggers `input_presence_vacuous` — with the two remedies.
- [ ] 3.4 `docs/under-the-hood/input-form-descriptor.md` § "Required, presence and gating": state that the lint is defined on `gating` and why.
- [ ] 3.5 `docs/tools/cli/agent-cli.md` advisory note: list the three families; delete the sentence saying the hint lints are not wired into the CLI array; keep the single-pipe exclusion.
- [ ] 3.6 `docs/under-the-hood/error-model.md` and `docs/contribute/mthds-test-corpus.md`: the advisory-only registry members are now several; reword the "one has no shape" passages accordingly.
- [ ] 3.7 `CHANGELOG.md` `[Unreleased]`: one **Added** entry for the lint (bold label, a few sentences: what fires, where, the two remedies, entry-pipe scope) and one **Changed** entry for the composition point (every whole-bundle validate channel now carries the same advisory families, the hint lints included, with the message cap). No counts.
- [ ] 3.8 If `docs/specs/` links or a drift contract fire on any touched file, resolve through `make drift-plan` / `make drift-ack` with an honest rationale.

## Phase 4 — gates, PR, follow-ups

- [ ] 4.1 `make agent-check` green.
- [ ] 4.2 Full `make agent-test` green (override moved aside if needed); record the run in the progress log.
- [ ] 4.3 Commit and open the PR against `dev`; wait for Greptile and Codex by SHA (`gh pr view --json reviews,comments`), triage with `/review-pr-agents`, reply and resolve threads in the same pass.
- [ ] 4.4 File the inbox items of design §8: `workspace` (protocol spec section + conformance rows and tests), `pipelex-js` (`categorize.ts` member), `pipelex-starter-js` (docs pointer). Each with `repo/path:line` evidence.
- [ ] 4.5 Add a dated status line to `wip/full-optional/design.md` naming the merge SHA, and rewrite the live-state block here for the last time. Do not delete or archive this tracker — that is a separate decision after review.

**CHECKPOINT 2 — after Phase 4.** The work is done when the PR is merged and the inbox items are filed; the release that carries the lint is what unblocks the conformance and corpus-consumer halves, and that version goes in the live-state block when it is cut.

## Progress log

- 2026-08-25 — Design written to `wip/full-optional/design.md` from the inbox request; the three amendments (entry-pipe scope, descriptor substrate, one composition point) recorded as decisions to ratify. No code yet.
