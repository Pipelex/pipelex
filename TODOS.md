# Validation-error reporting & surfacing — improvement plan

## Goal (use this as the /goal)

Perfect, clear validation-error reports and fix reports on every surface: every validation error must state — in MTHDS author syntax, never internal repr — what is wrong, where it is, and exactly what to write to fix it; and every surface (human `pipelex validate` / `pipelex fix`, agent `pipelex-agent validate` / `pipelex-agent fix` in markdown and JSON, the API `/validate` payload) must present that explanation at full strength, with an actionable next step, verified hands-on against the `pipelex-demos/bad_bundles` playground.

## Where this work lives

- Branch/worktree: `feature/Autofix` in `_autofix/` (this directory). The autofix track's steps 1–5 are done (rules, loop, agent + human `fix bundle` CLIs, `💡 Suggested fix:` lines in validate); step 6 (release train) is pending — see `wip/autofix/master-plan.md` and `wip/autofix/step5-human-cli-surfacing.md`. This plan is a follow-on quality track born from dogfooding the playground.
- Related deferred items to fold in opportunistically: `wip/autofix/deferred-checkpoint-e-review-items.md` (validate footer over-count; cross-CLI duplications) and the step-5 doc's explicitly-deferred "richer still-invalid markdown for the agent command".

## The test bed (built 2026-07-09, session before this plan)

`/Users/lchoquel/repos/Pipelex/pipelex-demos/bad_bundles/` — a playground of deliberately broken `.mthds` bundles, one scenario per directory, covering every autofix rule plus an unfixable-collision safety case and a kitchen-sink combo. Its `README.md` documents every scenario and the exact commands; `_pristine/` holds backups and `./restore.sh` re-breaks everything, so it can be exercised repeatedly. **This is where every before/after comparison in this plan gets verified.**

Run everything from the `pipelex-demos` repo root with its own venv (the user fixed it; it has the `fix` command):

```bash
cd /Users/lchoquel/repos/Pipelex/pipelex-demos
source .venv/bin/activate
export PIPELEX_NO_DECK_NOTICE=1
pipelex validate bundle bad_bundles/01_wrong_sequence_output/bundle.mthds
pipelex-agent validate bundle bad_bundles/01_wrong_sequence_output/bundle.mthds
pipelex fix bundle bad_bundles/01_wrong_sequence_output/bundle.mthds --diff
./bad_bundles/restore.sh
```

## Confirmed diagnosis (from the dogfooding session — reproduce on scenario 01)

Comparing `pipelex validate`, `pipelex-agent validate`, and `pipelex fix --diff` on `bad_bundles/01_wrong_sequence_output` showed the three surfaces are *consistent* (one engine, zero drift) but the explanation quality is carried almost entirely by the `💡 Suggested fix:` line — the core message is weak, and the agent surface doesn't even show that line as prose. Specifics, with pointers:

1. **Messages leak internal repr instead of author syntax.** The sequence-multiplicity raise site (`pipelex/pipe_controllers/sequence/pipe_sequence.py:114-118`) says `declares output multiplicity=None, but the last step ... has output multiplicity=True` — Python internals (`None` = single, `True` = list). An author writes `StoryIdea` vs `StoryIdea[]`. The message never shows the solution.
2. **The `(required: [...], provided: ...)` suffix is misleading on multiplicity errors.** Appended generically in `categorize_pipe_validation_with_libraries_error` (`pipelex/core/pipes/handle_pipe_errors.py:193`) by raw-repr-ing `required_concept_codes` (a Python list) and `provided_concept_code` (a string). For `INADEQUATE_OUTPUT_MULTIPLICITY` the concepts are identical by definition (the concept check passed just above), so it prints two same-looking refs — and the list-repr brackets `['story_studio.StoryIdea']` accidentally mimic MTHDS `[]` multiplicity syntax. It reads like a multiplicity statement it is not making.
3. **The correct solution string exists at the raise site and is thrown away by the message.** `expected_output_ref` is computed as exactly `"StoryIdea[]"` (`pipe_sequence.py:86-90`, via `StuffSpec.to_bundle_representation`) but flows only into the fix-planner enrichment (the `💡` line). Any surface showing only `message` (agent top line, API consumers) gets the `None`/`True` riddle.
4. **The agent markdown under-delivers on the workspace's own "format follows consumer" doctrine.** `pipelex-agent validate` markdown = a title, a *truncated* top message (drops the required/provided detail the item has), a boilerplate hint ("Check the validation_errors array for specific issues", from `pipelex/pipeline/exceptions.py:92`), then a raw JSON dump of `validation_errors`. The per-item prose rendering the human renderer got in step 5 (titled error, field lines, `💡 Suggested fix:` line, actionable footer naming the fix command) never got mirrored to the agent markdown. Doctrine reference: workspace-root `CLAUDE.md` § "Surface output conventions" and `docs/specs/pipelex-mthds-protocol.md` § "Presentation vs contract".
5. **The human footer is the model to generalize:** `💡 N of these errors can be fixed automatically — run: pipelex fix bundle <path>` — "a hint needs an action behind it". The agent surfaces have no equivalent (neither validate nor the hint text), even though the payload carries `suggested_fix` with `safety: "safe"`.

## Key code map

| Concern | Where |
| --- | --- |
| Raise sites of pipe validation errors (message wording) | `pipelex/pipe_controllers/sequence/pipe_sequence.py` (multiplicity + concept + taint); sibling controllers/operators under `pipelex/pipe_controllers/`, `pipelex/pipe_operators/` |
| Error-type enum + `is_*` properties | `pipelex/core/pipes/exceptions.py` (`PipeValidationErrorType`, `INADEQUATE_OUTPUT_MULTIPLICITY` at :108) |
| Categorizer that builds error data + appends the required/provided suffix | `pipelex/core/pipes/handle_pipe_errors.py:180-209` |
| Shared items builder (single source of truth; attaches `suggested_fix`) | `pipelex/pipeline/validation_errors.py:24` (`build_validation_error_items`) |
| Fix planner (rules, descriptions, `KNOWN_FIX_CODES`) | `pipelex/pipeline/fixes/planner.py` |
| Fix loop + result model | `pipelex/pipeline/fixes/fix_loop.py` |
| Human validate/fix rendering (items renderer, 💡 lines, footer) | `pipelex/cli/error_handlers.py` (`display_validation_error_items`, `handle_validate_bundle_error`); `pipelex/cli/commands/fix/` (`_fix_core.py`, `_diff_sandbox.py`) |
| Agent CLI output plumbing (markdown/JSON two-stream, error envelope) | `pipelex/cli/agent_cli/commands/agent_output.py` (`_render_error_markdown` at :289); `pipelex/cli/agent_cli/commands/fix/`; agent CLI conventions in `pipelex/cli/agent_cli/CLAUDE.md` |
| Agent/API fix markdown renderer (CLI-free) | `pipelex/pipeline/fixes/fix_render.py` (`format_fix_markdown`) |
| API error envelope (`ValidateBundleError.to_error_report`, boilerplate hint) | `pipelex/pipeline/exceptions.py` (hint at :92, report at ~:154) |
| Tests pinning current wordings/renderings | `tests/unit/pipelex/cli/test_validate_suggested_fix_rendering.py`, `tests/unit/pipelex/cli/commands/fix/test_fix_bundle_human_format.py`, `tests/integration/pipelex/cli/test_fix_bundle_human.py`, `tests/integration/pipelex/pipeline/test_fix_convergence_loop.py`, e2e under `tests/e2e/pipelex/cli/` and `tests/e2e/agent_cli/` |
| Cross-repo wording corpus (regen after wording changes) | `conformance/validate-error-qa/` — the generated error-explanation QA corpus, freshness-tested against the live API (see workspace-root `CLAUDE.md`) |

## Guardrails

- **Presentation vs contract:** wordings, markdown shape, exit codes, and hints are presentation — free to improve. The structured fields (`is_valid`, `error_type`, `category`, `suggested_fix`, `validation_errors[]`) are the machine contract — additive changes only, and any addition ripples to the API report and conformance fixtures (step-6 already owes a `suggested_fix` fixture regen; coordinate, don't collide).
- **One engine, every surface:** improvements go into the message at the raise site or the shared items builder/renderers — never into per-surface private wording that can drift.
- Wording changes WILL break string-pinning tests; update the pins in the same change (that's the point of them).

## Phases

### Phase 0 — Cold-start orientation

- [ ] Read this file top to bottom; skim `wip/autofix/step5-human-cli-surfacing.md` (design decisions D5.4/D5.5 explain the human renderer) and `pipelex/cli/agent_cli/CLAUDE.md` (two-stream output conventions).
- [ ] Run the playground: `./bad_bundles/restore.sh`, then all three surfaces on scenario 01 (commands above) and capture the current outputs as the "before" baseline (save to `wip/validation-reporting/before/` in this repo — create the dir).
- [ ] Sweep the remaining scenarios (02–10) across the three surfaces and note, per scenario, every message that fails the bar "states the problem AND the concrete author-syntax action". This inventory drives Phase 1's scope.

### Phase 1 — Message quality at the source (the engine, so every surface benefits)

- [ ] Rewrite the sequence multiplicity-mismatch message (`pipe_sequence.py:114`) in author terms using the already-computed `expected_output_ref` and a `to_bundle_representation` rendering of the declared output — e.g. "the sequence 'brainstorm' declares output 'StoryIdea', but its last step 'gen_ideas' yields 'StoryIdea[]'. Update the sequence's output to 'StoryIdea[]' (or change the last step)."
- [ ] Fix the required/provided suffix (`handle_pipe_errors.py:193`): suppress it for multiplicity errors (concepts identical by definition), and for the cases where it stays, render author-syntax refs — never Python list repr.
- [ ] Audit every other pipe/blueprint validation message surfaced by the Phase 0 inventory for the same diseases (internal repr like `multiplicity=None/True`, Python reprs of lists, missing "what to write" action) and rewrite to the same bar. Candidates: concept mismatch, controller-input drift wording, native-redecl, pipe-code syntax, optional/taint messages.
- [ ] Update string-pinning tests; run targeted suites per `tests/CLAUDE.md` mapping (pipeline + cli + e2e paths).
- [ ] **CHECKPOINT 1** — update this doc (status, decisions, deltas); re-capture scenario outputs and diff against the before-baseline; good handoff point for a fresh session.

### Phase 2 — Agent surfaces catch up to the human renderer (markdown presentation)

- [ ] `pipelex-agent validate` markdown: render `validation_errors` items as prose (humanized `error_type` title, message, per-field lines, `💡 Suggested fix:` line), not a JSON dump — reuse/mirror the item-driven structure of `display_validation_error_items`; keep the JSON block only in `--format json`.
- [ ] Fix the truncated top-line summary (it currently drops detail the item carries).
- [ ] Replace the boilerplate hint (`pipeline/exceptions.py:92`) with an actionable, fix-aware footer: when N items carry a `safe` suggested fix, say so and name the exact command (`pipelex-agent fix bundle <path>` with `-L` echo), mirroring the human footer.
- [ ] Same pass on `pipelex-agent fix` still-invalid markdown (`fix_render.py`): remaining errors rendered as prose items with their 💡 lines (this is the step-5 deferred "richer still-invalid markdown").
- [ ] Update agent-CLI tests + e2e; check `mthds-plugins/docs/mthds-agent-output-audit.md` expectations still hold for hook consumers (hooks pin `--format json`, so prose changes must not touch the JSON contract).
- [ ] **CHECKPOINT 2** — update this doc; verify every bad_bundles scenario through both agent commands.

### Phase 3 — JSON / API parity and the fix-report surfaces

- [ ] Verify the API `/validate` payload (`ValidateBundleError.to_error_report`) carries the improved messages verbatim and the hint improvement lands there too; a produced verdict stays a 200/`is_valid` discriminated body — no contract change.
- [ ] Human + agent fix reports: apply the Phase 1 message bar to `bail_reason` wordings and the "still shows a suggested fix that was not applied" tip; confirm `--diff` preview wording matches the real run.
- [ ] If any structured field is worth adding for consumers (e.g. `expected_output_ref` / declared-vs-expected as data), do it additively and note the wire addition for the step-6 changelog + conformance fixture regen.
- [ ] **CHECKPOINT 3** — update this doc.

### Phase 4 — Full-sweep QA and closeout

- [ ] Restore the playground and run every scenario × every surface (`validate` human/agent-md/agent-json, `fix` human/agent, `--diff`, and the collision bail of scenario 09); each output must meet the goal bar with no regressions.
- [ ] Regenerate/refresh the `conformance/validate-error-qa/` corpus against the new wordings (coordinate with step 6's release ordering — corpus freshness-tests against the *live* API).
- [ ] Docs: update the error-reporting docs in `docs/` (and `pipelex-demos/bad_bundles/README.md` if commands or outputs changed); CHANGELOG entry under `[Unreleased]`.
- [ ] `make agent-check` + `make agent-test`; final status update in this doc.

## Status log

- 2026-07-09 — Plan written from the dogfooding session (playground built + three-surface diagnosis on scenario 01). No implementation started.
