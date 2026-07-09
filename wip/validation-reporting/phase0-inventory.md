# Phase 0 — validation-error surface inventory

Baseline captures live in [`before/`](before/) — one file per scenario, all five surfaces (`HUMAN validate`, `AGENT validate` markdown + json, `HUMAN fix --diff`, `AGENT fix` markdown), ANSI/banner stripped. Regenerate with `scratchpad/capture_before.sh` (restores the playground at the end).

Captured 2026-07-09 against `feature/Autofix` @ `d43095a7e`, pipelex `v0.38.0`, demos venv pointing at this worktree.

## The diseases, ranked by leverage

### A. Internal Python `repr` leaks into the message (Phase 1 — fix at the raise site)

The message string is the same across every surface (one engine), so a raise-site fix cures human validate, agent markdown/json top-line + `validation_errors[].message`, and the fix reports at once.

- **`inadequate_output_multiplicity`** — scenarios 01, 02, 08. Raise site `pipe_sequence.py:114-118`.
  > `…the sequence 'brainstorm' declares output multiplicity=None, but the last step 'gen_ideas' has output multiplicity=True.`
  `multiplicity=None/True` is Python internals (None=single, True=list). An author writes `StoryIdea` vs `StoryIdea[]`. The correct author-syntax ref (`expected_output_ref = "StoryIdea[]"`) is already computed at `pipe_sequence.py:86-90` but only flows to the 💡 fix line, never the message. The declared side can be rendered the same way with `self.output.to_bundle_representation(relative_to_domain=self.domain_code)`.

- **`input_stuff_spec_mismatch`** — scenario 03. **The worst offender.** Raise site `pipe_abstract.py:361-373`.
  > `Mismatched field(s): concept: declared='code='Number' domain_code='native' … refines=None' vs required='code='Text' …'`
  > `Declared: concept=Concept(code='Number', …, refines=None) multiplicity=None presence=<PresenceMarker.PLAIN: 'plain'>`
  > `Required: concept=Concept(code='Text', …) multiplicity=None presence=<PresenceMarker.PLAIN: 'plain'>`
  Four lines of `str(Concept)` + `str(StuffSpec)` + `PresenceMarker` enum repr. Author-syntax: input `dish` is declared `Number` but the step needs `Text`. Both `declared_stuff_spec` and `needed_stuff_spec` are `StuffSpec`s → `.to_bundle_representation(relative_to_domain=self.domain_code)` gives `Number` / `Text`.

### B. Misleading `(required: [...], provided: ...)` suffix (Phase 1 — the categorizer)

Appended generically in `handle_pipe_errors.py:192-193` by raw-repr-ing `required_concept_codes` (a `list[str]`) → `['story_studio.StoryIdea']`. Two problems: (1) for `inadequate_output_multiplicity` the concepts are identical by definition (concept-compat check passed just above at `pipe_sequence.py:93`), so it prints two same-looking refs; (2) the list-repr brackets `[...]` mimic MTHDS `[]` multiplicity syntax — reads like a multiplicity claim it isn't making. Fix: suppress for multiplicity errors; for the rest render author-syntax refs (join, no list-repr brackets/quotes). Note `is_inadequate_output` already exists on the enum (`exceptions.py:186`) but covers concept+multiplicity; a narrower `is_inadequate_output_multiplicity` (or an equivalent match) is needed.

### C. Pydantic `ValidationError` leak in the agent/API top-line summary (Phase 1/2)

Blueprint errors (scenarios 05, 06, 09, 10) surface a top-level `message` of the form:
> `Validation error(s):\n\nValue errors: 'concept': Value error, <the real, clean message>`
> `Value errors: 'main_pipe': Value error, …, 'pipe': Value error, …` (multi-error)

The per-item `validation_errors[].message` is **clean** — only the summarizing top-line leaks `Value errors: '<field>': Value error,`. Composed where `ValidateBundleError`'s message is built from the pydantic `ValidationError` (`validate_bundle.py:142` / interpreter `:76-86`). Scenario 09 additionally prefixes `Could not load MTHDS bundle from '…' because of:` (library-loader path). Since the item messages are already good, the top-line should summarize from the items (count + first message), not from `str(pydantic_error)`.

### D. Agent `validate` markdown = raw JSON dump, not prose (Phase 2 — the big agent gap)

Every scenario. `pipelex-agent validate` markdown = title (`# Error: ValidateBundleError`), a top message (see C), a boilerplate hint, then a fenced `json` dump of `validation_errors`. The per-item prose the human renderer got in step 5 (titled `error_type`, field lines, `💡 Suggested fix:` line, actionable footer naming the fix command) was never mirrored to agent markdown. Renderer: `agent_output.py` `_render_error_markdown` (~:289). Doctrine ("format follows consumer", workspace `CLAUDE.md`) says the agent should get prose, JSON only under `--format json`.

### E. Boilerplate agent hint (Phase 2)

Every scenario: `> 💡 **Hint:** Check the validation_errors array for specific issues` (`pipeline/exceptions.py:92`). The human footer is the model to generalize: `💡 N of these errors can be fixed automatically — run: pipelex fix bundle <path>`. When N items carry a `safe` suggested_fix, the agent hint should name the exact command (`pipelex-agent fix bundle <path>`), mirroring the human footer. The payload already carries `suggested_fix` with `safety: "safe"`.

### F. "Must be in snake_case" slightly misleads for namespace/dot errors (low priority)

Scenarios 06, 09, 10 (`invalid_pipe_code_syntax`): `Pipe code 'postcard_shop.hello' is not a valid pipe code. Must be in snake_case.` — but each dotted segment *is* snake_case; the real defect is the same-domain prefix (the `.`). The 💡 line clarifies ("Strip the same-domain prefix …"). Consider tightening the message to name the dot/prefix as the cause when a `.` is present. Optional in Phase 1's audit.

## Per-scenario surface verdict (does it meet "states the problem AND the concrete author-syntax action"?)

| Scenario | Rule(s) | Human validate | Agent validate md | Diseases |
| --- | --- | --- | --- | --- |
| 01 wrong_sequence_output | match-sequence-output | msg fails (A,B); 💡 saves it | fails (C-ish trunc, D, E) | A,B,D,E |
| 02 cascade_outputs | match-sequence-output ×2 | same as 01 | same | A,B,D,E |
| 03 inputs_drift | sync-controller-inputs | msg fails hard (A); 💡 good | fails (D,E) + A in dump | A,D,E |
| 04 missing_inputs | sync-controller-inputs | msg **good** ("Current inputs: (none)"); 💡 good | fails (D,E) | D,E |
| 05 native_concept_redecl | strip-native-concept-redecl | msg **good** | fails (C,D,E) | C,D,E |
| 06 namespace_prefix | strip-namespace ×2 | msg good-ish (F); 💡 good | fails (C,D,E) | C,D,E,F |
| 07 cross_rule_combo | sync→match | msg good (missing_input); 💡 good | fails (D,E) | D,E |
| 08 multi_file_cascade | match-sequence-output ×2 | same as 01 | same | A,B,D,E |
| 09 unfixable_collision | (bail safety) | validate msg good-ish (F); fix bail **good+actionable** | fails (C,D,E); fix dump | C,D,E,F |
| 10 kitchen_sink | all | blueprint msgs good-ish (F) | fails (C,D,E) | C,D,E,F |

Human `validate`'s `💡 Suggested fix:` line and the actionable footer are consistently strong — they carry the surface today. The core `message` is the weak link (A,B for pipe-validation; the message itself is fine for blueprint errors). The agent markdown surface is uniformly weak (D,E on every scenario; C on blueprint errors).

## What's already good (don't regress)

- Human `validate` 💡 lines + footer (`pipelex fix bundle …` with `-L` echo, `shlex`-quoted).
- Human `fix --diff` — real diff, named fixes, bail reason actionable ("Stopped: cross-file collision …").
- The `suggested_fix` structured payload (fix_code/description/safety/source/ops) is complete and identical across surfaces.
- `missing_input_variable` and `native_concept_redeclaration` messages are already author-friendly.
- Diff cosmetic realignment (column-alignment churn) is documented in the playground README — expected, not a bug.

## Phase 1 scope (driven by this inventory)

1. Rewrite `inadequate_output_multiplicity` message (A) — `pipe_sequence.py:114`.
2. Rewrite `input_stuff_spec_mismatch` message (A) — `pipe_abstract.py:361-373`.
3. Fix the required/provided suffix (B) — `handle_pipe_errors.py:192`.
4. Consider tightening `invalid_pipe_code_syntax` wording (F) — low priority, audit during Phase 1.
5. The pydantic top-line leak (C) straddles Phase 1/2 — the cleanest fix (summarize from items) belongs with the agent-summary work in Phase 2, but note it here.

Diseases D and E are Phase 2 (agent markdown prose + fix-aware footer). C is Phase 2 (top-line summary).
