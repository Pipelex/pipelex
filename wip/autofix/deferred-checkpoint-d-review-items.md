# Deferred follow-ups from Checkpoint D (Phase D step exit — PR #1031)

The PR #1031 review surfaced one unresolved thread (codex, P2). It is a **confirmed** but **low-severity, fail-safe** edge-case bug whose proper fix requires a design decision, so it is deferred here with the thread left open rather than patched during triage. (The earlier "PR #1031, cubic P2" cross-reference in `deferred-checkpoint-c-review-items.md` is a *different* finding — the `main_pipe` `SET_KEY` cross-file gap — not this one.)

## 1. Dotted-key controller inputs misfire `sync-controller-inputs`

**Reporter.** codex (P2), on `pipelex/pipeline/fixes/planner.py:94-98` (`_plan_sync_controller_inputs`).

**What it is.** When a controller input is authored with a **quoted dotted key** — e.g. `inputs = { "cv.name" = "Text" }` on a `PipeSequence` — the input-sync fix targets the wrong TOML key and either skips or duplicates.

**Mechanism (all cited).**

- `InputStuffSpecs.validate_concept_codes` collapses the authored key `cv.name` → root `cv` via `get_root_from_dotted_path` (`pipelex/core/pipes/inputs/input_stuff_specs.py:55`), so `self.inputs.root` is keyed by root names only.
- `_declared_inputs_for_fix` / `_expected_inputs_for_fix` read those already-normalized root keys (`pipelex/core/pipes/pipe_abstract.py:301-304`, `279-291`). The authored dotted key is gone before the pure planner runs.
- The planner emits ops keyed on `cv` (`planner.py:94` SET, `planner.py:98` DELETE). The applier matches the **literal** TOML key (`applier.py:198` for SET, `207-208` for DELETE). Because `cv` ≠ `"cv.name"`, the op misses.

**The authoring form is supported, not a mistake.** `is_valid_input_name` explicitly permits dotted (sub-attribute) input names, and `test_fix_applier_inputs_sync.py:94` (`test_dotted_input_key_survives_format`) authors exactly `inputs = { "cv.name" = "Text", cv = "Curriculum", note = "Text" }` on a `PipeSequence`, calling `"cv.name"` "a supported sub-attribute name." That test only covers deleting an *unrelated* sibling key, so this drift scenario is real and untested. (Note: only the **quoted** form is reachable — an unquoted `cv.name = "Text"` nests to `{cv: {name: ...}}`, whose dict value fails `PipeBlueprint.inputs: dict[str, str]` at blueprint parse. codex scoped the claim correctly.)

**Why it fails safe (this is the reason it is low-severity, not a correctness trap).**

- **Case A — extraneous dotted input.** `DELETE_KEY cv` finds no `cv` key (only `"cv.name"`) → **skipped** (`applier.py:207-208`) → `any_op_applied=False`, no file write → the same fix fingerprint is re-proposed next iteration → the loop bails **loudly** with `is_valid=False`, bail_reason "no progress" (`fix_loop.py:191-203`). The file is untouched and the error is correctly reported unfixed.
- **Case B — drifting dotted input (concept/multiplicity mismatch).** `SET_KEY cv=<new>` **appends** `cv` beside the existing `"cv.name"` (`applier.py:198`). On re-validation `InputStuffSpecs` re-collapses both to root `cv`; iteration order makes the later (`cv=<new>`, correct) value win, so validation **passes** — but a stale/shadowed `"cv.name"` line is left in the file. It is valid TOML and invisible to the `EXTRANEOUS_INPUT_VARIABLE` check (which iterates `self.inputs.variables`, i.e. root keys — `pipe_abstract.py:385`), so it never re-errors.
- **No path** reports an invalid bundle as valid, crashes, or corrupts the file. Even a hypothetical key-order flip in Case B would just fail validation and re-hit the same no-progress bail. Worst observed outcome: a loud "couldn't fix" (Case A) or a cosmetic stale line in an otherwise-correct, valid file (Case B).

**Why deferred, not fixed now.** The planner is **structurally blind** to the dotted case — normalization to `cv` is lossy and irreversible before the planner ever sees the data, and `declared_inputs={"cv": ...}` is indistinguishable from a genuine bare `cv` declaration. So the planner cannot detect or guard it without disabling *all* controller-input fixes. That leaves three real options, and choosing among them is a design decision:

1. **Applier-side root-aware resolution (recommended).** In `_apply_one_op` (`applier.py:191-210`), when `table_path` ends in `inputs`, resolve any existing literal key whose `get_root_from_dotted_path(key) == fix_op.key` before acting: DELETE removes that dotted key; SET replaces/renames it in place instead of appending a sibling. Bounded and local, but it special-cases an intentionally **path-generic** applier (see its module docstring) — so it needs a conscious "yes, `inputs` tables get special treatment" call.
2. **Carry the authored key through.** Preserve the un-normalized requirement expression from `InputStuffSpecs` into the error data so the planner can target the literal key. This ripples widely — everything downstream relies on `self.inputs.root` being root-keyed — and touches the error model plus all three raise sites (`pipe_abstract.py:339-340`, `380-381`, `394-395`). Heaviest option.
3. **Accept the edge case.** Given it already fails safe, document it and move on.

Recommendation: option 1 if we decide dotted controller inputs are worth first-class fix support; otherwise option 3. Option 2 is out of proportion to the payoff.

**If revisited.** Implement option 1 in `applier.py`, and pin both cases in `test_fix_applier_inputs_sync.py`: Case A (extraneous dotted key actually removed, loop converges instead of bailing) and Case B (drifting dotted key replaced **in place**, no duplicate `cv` line left behind). `test_dotted_input_key_survives_format` is the existing sibling test to sit next to.

**Thread:** https://github.com/Pipelex/pipelex/pull/1031 — codex comment on `pipelex/pipeline/fixes/planner.py:94-98` (left open).
