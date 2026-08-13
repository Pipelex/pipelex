# `Time` in the PipeCompose whole-stuff conversion matrix

**Goal: close the one native that does not convert.** `PipeCompose`'s construct block unwraps a whole native stuff copied into a plain-typed field — `Text → str`, `Number → float|int`, `YesNo → bool`, `Date → date`. `Time` has no arm, so `start = { from = "start_time" }` into a `time`-typed field hands over the `TimeContent` wrapper instead of the time. This branch adds the arm, its plural counterpart, the tests, and every doc that enumerates the matrix.

**Branch:** `fix/Time-native`, forked from `dev`. **Worktree:** `_time/` — treat it as the pipelex repo root; every path below is relative to it, not to this file's own directory (it was the root `TODOS.md` while the work was in flight).

**Read first:** [`wip/native-concepts/time-native-open-questions.md`](../../../wip/native-concepts/time-native-open-questions.md) (in the workspace repo, not here) carries the decision and the design rationale — *why* each edit, and the three non-obvious points this plan only restates. If you are cold-starting, read its "Design of the accepted solution" section before touching code; it is the difference between making this change and making it correctly.

## Standing constraints

- **No version bump, no new changelog heading.** A version number is a receipt for a published artifact. This work accumulates under the existing `## [Unreleased]` in `CHANGELOG.md`.
- **Do not push and do not open a PR without asking.** Same for the `mthds-plugins` half.
- **Phase 4 is not in this worktree.** It is a `mthds-plugins/` change in the workspace checkout. Doing it here is impossible; forgetting it ships a runtime whose own skills documentation contradicts it.
- **No backward-compat shim.** The matrix simply gains a row.

## The design in one paragraph

Four edits in `pipelex/pipe_operators/compose/structured_content_composer.py`: widen the `NativeScalarValue` alias, add `datetime.time` to `NATIVE_SCALAR_TARGET_TYPES`, add the `TimeContent` arm to `_extract_native_scalar`, and refresh the matrix in the four docstrings that enumerate it. **The tuple entry is the half that is easy to miss** — it is consulted at `_convert_list_content` (routes `list[time]` to the scalar extractor) and at `_validate_item_compatibility` (turns a wrong item type into a loud error rather than a cryptic pydantic one), and it is the entire reason the `Time[]` case needs its own test. The arm needs **no fidelity guard**, unlike `Date`'s: `TimeContent` holds exactly one required field and its UTC offset lives inside the `time`'s own `tzinfo`, so the copy is lossless.

---

## Phase 1 — the runtime arm

- [x] **1.1 — `NativeScalarValue` (`:28`).** Add `datetime.time` to the `TypeAlias`. It types `NativeScalarExtraction.value` and every list-of-scalars return; the new arm does not typecheck without it.
- [x] **1.2 — `NATIVE_SCALAR_TARGET_TYPES` (`:33`).** Add `datetime.time`. Leave the comment above it as-is — it explains why there is no subclass matching (`datetime` under `date`, `bool` under `int`), which is still exactly right; `time` has no such trap and needs no new prose there.
- [x] **1.3 — the arm in `_extract_native_scalar`,** as a new `elif` immediately after the `DateContent` branch (`:417`–`:425`), plus `from pipelex.core.stuffs.time_content import TimeContent` at the top:

    ```python
    elif isinstance(stuff_content, TimeContent):
        if expected_type is datetime.time:
            return NativeScalarExtraction(matched=True, value=stuff_content.time)
    ```

    ⚠ **Identity check, not `_expects_type`.** Matches the `DateContent` arm and, more importantly, matches the plural path — which decides membership with `in` against the tuple, i.e. by identity. Using `_expects_type` here would let a `time` subclass convert as a scalar field and then fail as a list item.
    ⚠ **Do not add a fidelity guard.** There is nothing to drop. If you find yourself writing one, re-read the design doc — the `Date` guard exists because `DateContent` has two fields, not because temporal copies are inherently lossy.
    ⚠ **Do not add a `DateContent → datetime.time` arm.** A whole `Date` into a bare `time` field drops the date; the authored route is the dotted path `from = "the_date.time"`, which already works.
- [x] **1.4 — the four docstring enumerations.** All in the same file; the last one is a bare parenthetical and is the one that gets forgotten:
    - `_resolve_from_var` (`:169`–`:176`) — the bulleted conversion list.
    - `_convert_for_target_type` (`:329`) — the inline sentence.
    - `_extract_native_scalar` (`:384`–`:390`) — the "Conversion matrix" block. Say explicitly that `TimeContent → time` is lossless and needs no guard, so the asymmetry with the `Date` bullet directly above it reads as deliberate.
    - `_convert_list_items_as_scalars` (`:622`) — the type list *"(str/float/int/bool/date)"*.

## Phase 2 — tests

Both cases go in `tests/integration/pipelex/pipes/operator/pipe_compose_structured/`, in the existing `test_compose_native_scalar_conversion` parametrize list. The class is `@pytest.mark.dry_runnable` — no inference, no marker changes.

- [x] **2.1 — singular: `TimeContent → time`.** Mirror `date_content_to_date_field` exactly:
    - `compose_structured_models.mthds` — a concept line beside `DeadlineHolder` in the "Native scalar conversion testing concepts" block, e.g. `StartTimeHolder = "Holder with a time field"`. Keep the column alignment of that block.
    - `models_for_pipe_compose.py` — a `StartTimeHolder(StructuredContent)` beside `DeadlineHolder`, with `start: time = Field(...)`. The module imports `from datetime import date` today — widen it to `date, time`.
    - `test_data.py` — a `TIME_TO_TIME_CONSTRUCT` beside `DATE_TO_DATE_CONSTRUCT`.
    - the test module — a `pytest.param` with `NativeConceptCode.TIME`, `TimeContent(time=...)`, and `id="time_content_to_time_field"`. **Use a time that carries a UTC offset** (`datetime.time(15, 40, tzinfo=datetime.timezone(datetime.timedelta(hours=2)))`) and assert it survives — that is the claim that the arm is lossless where `Date`'s is guarded, and a naive-time fixture would not test it.
- [x] **2.2 — plural: `ListContent[TimeContent] → list[time]`.** This is what covers the `NATIVE_SCALAR_TARGET_TYPES` entry from 1.2; without it that line is untested and a future edit can drop it silently. Same four files, following the `text_list_to_required_str_list_field` shape (a module-level `_make_...` helper builds the `ListContent`, and `input_concept_code` stays the singular `NativeConceptCode.TIME`).
- [x] **2.3 — update the test module's header docstring** (`:3`–`:10`), which enumerates what the module covers and currently stops at *"DateContent to date field"*.
- [x] **2.4 — run the targeted suite.** Source areas touched: `pipe_operators/` plus a `.mthds` fixture, so per `tests/CLAUDE.md` that is the pipe tests plus the builder ones:

    ```bash
    .venv/bin/pytest -n auto \
      -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" \
      -o log_level=WARNING --tb=short -q \
      tests/unit/pipelex/pipe_operators/ tests/integration/pipelex/pipes/ \
      tests/unit/pipelex/builder/ tests/integration/pipelex/builder/
    ```

- [x] **2.5 — confirm the new cases actually fail without the fix.** Stash Phase 1, run 2.1 and 2.2, see them fail; restore. A conversion test that passes against the unfixed runtime is testing nothing — and the two fail differently, which is worth seeing once: the singular quietly hands the `TimeContent` wrapper to the field, while the plural falls all the way through `_validate_item_compatibility`'s four cases (none of which match, precisely because the tuple entry is missing) and dumps the items as dicts, failing later in pydantic validation of `list[time]`. That second trace is the argument for 1.2 in concrete form.

## Phase 3 — docs and changelog

- [x] **3.1 — `docs/building-methods/pipes/pipe-operators/PipeCompose.md`,** section "Copying Whole Inputs Into Native Fields". Three separate spots, all of which go stale together:
    - `:161` — the prose enumeration `(Text, Number, YesNo, Date, or a list of them)`.
    - `:165`–`:174` — the conversion table. Add a `Time` row after `Date` and a `Time[]` row after `Date[]`, keeping the singular-then-plural grouping the table already uses.
    - `:178` — the fidelity-guard paragraph. Add that `Time` needs no such guard, and why (the offset rides inside the time itself, so nothing is dropped). Stating it here is what keeps the next reader from filing the asymmetry as a bug.
- [x] **3.2 — `CHANGELOG.md`,** a `### Fixed` entry under the existing `## [Unreleased]`. Frame it as the gap it is — `Time` was introduced after the matrix was written and was never added to it — and mention that the plural `Time[]` form is covered too. No version bump, no new heading.
- [x] **3.3 — `make agent-check`.** ⚠ The auto-fixer runs inside this target and will keyword-only an ungranted positional subject; nothing in this change adds a new `def`, so there should be nothing to grant — if the check reports one, stop and look rather than accepting the rewrite.
- [x] **3.4 — `make agent-test`,** the full suite, before the branch is considered done.

### 🔶 Checkpoint — pipelex side complete

Stop here and report. Before stopping: tick the boxes above, record under this checkpoint anything that deviated from the design (a line number that had moved, a test that needed a shape the plan did not anticipate, a doc spot the plan missed), and commit so the stop point is a clean tree. Then state plainly that Phase 4 is outstanding and lives in another repo — the change is *not* shippable until it lands, because the plugin's skills would be telling agents that `Time` does not convert while the runtime converts it.

**Reached 2026-08-13. Phases 1–3 complete, `make agent-check` and the full `make agent-test` both green, tree committed.**

Deviations from the design, all minor:

- **A fifth enumeration site the plan did not list.** Beyond the four docstrings in the composer, the *test fixture* module `models_for_pipe_compose.py` carries the matrix in a section-header comment (*"TextContent -> str, NumberContent -> float, YesNoContent -> bool, DateContent -> date"*). It goes stale the same way and was updated. Nothing else in the tree enumerates the matrix — `grep`ed for the wording across `pipelex/`, `docs/` and `tests/`.
- **Names chosen for the two holders:** `StartTimeHolder.start: time` (singular) and `SlotTimesHolder.slots: list[time]` (plural). Both are ≤ 18 chars so the `.mthds` concept block's column alignment was preserved untouched. The plural fixture puts the UTC offset on the *middle* item, so a list extraction that dropped it would fail on one item and not the others.
- **Line numbers were all accurate** — nothing had moved since `c0cefb6af`.
- **2.5's predicted asymmetry held, with one wording correction.** The singular case is not *silent*: the wrapper does reach the field, but `compose()`'s own field-type summary catches it and names it — `start: TimeContent (expected time) <-- MISMATCH`, `time_type`. The plural case failed exactly as described, per-item `slots.0/1/2: time_type` against `{'time': datetime.time(...)}` dicts, having fallen through all four `_validate_item_compatibility` cases. Both traces confirm the tuple entry in 1.2 is load-bearing.
- **No drift contract fired,** as the design predicted — `make drift-check` passes untouched, no `make drift-ack` in this change.

---

## Phase 4 — the cross-repo follow-up (in `mthds-plugins/`, NOT this worktree)

Doc-only, and mandatory: `templates/skills/shared/mthds-reference.md.j2:357` names the convertible natives as `Text`, `Number`, `YesNo`, `Date`. That line is accurate against today's runtime and wrong the moment Phase 1 ships.

- [ ] **4.1 — edit the template**, not the generated files. `templates/skills/shared/mthds-reference.md.j2` is the source; `mthds/`, `mthds-dev/`, `mthds-codex/` and `mthds-sandbox/` are build outputs.
- [ ] **4.2 — `make build`**, which regenerates all four targets. Verify the four generated `skills/shared/mthds-reference.md` copies moved.
- [ ] **4.3 — check the neighbours before assuming one line is enough.** Phase 0 of the native-concepts plan found `Time` missing from *every* native enumeration in that repo, not the two files it expected. Grep the templates for the construct-conversion wording rather than trusting this list.
- [ ] **4.4 — changelog** in `mthds-plugins`.
- [ ] **4.5 — `internal-tools` integration suite.** Required by the workspace rule whenever `mthds-plugins/` is touched: `make build && make agent-test` in `internal-tools/`, Docker running. ⚠ Known trap recorded during Phase 0: these tests require the local `mthds-js` checkout to be at or ahead of the published npm `mthds` version, or `update-check` assertions fail for reasons unrelated to your change. Fast-forward `mthds-js` first if a `mthds` release has landed recently.

## Deliberately not in scope

- **`test_pipe_llm_time_output_path.py`** (OQ-2). It is an `inference`-marked live-model test on a path this change does not touch. Deferred on purpose — do not fold it in to "finish `Time`". The plural test in 2.2 is *not* this; it is `dry_runnable` and covers the tuple entry.
- **A `DateContent → time` arm** — see 1.3.
- **Any release, version bump, or `/runtime-cascade`.** Nothing on the wire changes; this rides the next ordinary pipelex release.
