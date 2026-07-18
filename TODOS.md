# PipeCompose construct: whole-stuff → native-field conversion fixes

**Status: GREEN — CHECKPOINT 2 closed. Phases 1+2+3 complete: fix landed and verified (PR #1051 merged to `dev`, shipped in release v0.39.2). Remaining: Phase 4 cross-repo follow-ups — now DE-GATED since v0.39.2 ships the fix.**

## Cold-start state (as of Checkpoint 2, 2026-07-17)

- **Branch:** `fix/PipeCompose-bug` (off `dev`-lineage tip `e660283bf`), committed and PR'd to `dev` at Checkpoint 2.
- **The change** (all verified green together — `make agent-check` clean, full `make agent-test` passed):
  - Modified: `pipelex/pipe_operators/compose/structured_content_composer.py` (the whole fix: `_extract_native_scalar` matrix + `NATIVE_SCALAR_TARGET_TYPES` + `NativeScalarExtraction` NamedTuple at module top; Optional unwrap in `_get_field_expected_type`/`_get_nested_field_class`; `_convert_list_items_as_scalars`; loud `_validate_item_compatibility`)
  - Modified: `subject_grants.toml` (grant for `unwrap_optional`'s positional `annotation` param — do not let `make fko` demote it)
  - Modified (test support): `tests/integration/pipelex/pipes/operator/pipe_compose_structured/{compose_structured_models.mthds,models_for_pipe_compose.py,test_data.py}` (new holder concepts/models/constructs for native-scalar cases)
  - New: `pipelex/tools/typing/annotation_utils.py` (`unwrap_optional`)
  - New tests: `tests/e2e/test_pipe_compose_whole_stuff_mthds.py` + `tests/e2e/fixtures/compose_whole_stuff/`, `tests/integration/pipelex/pipes/operator/pipe_compose_structured/test_pipe_compose_native_scalar_conversions.py`, `tests/unit/pipelex/tools/test_annotation_utils.py`
  - Docs (Phase 3): `docs/building-methods/pipes/pipe-operators/PipeCompose.md` gained a "Copying Whole Inputs Into Native Fields" section (conversion matrix + worked example with optional fields); `CHANGELOG.md` `[Unreleased]` gained the Fixed entry; docs sweep found no other page describing construct `from` semantics, and the `StructuredContentComposerTypeError` error page is generated boilerplate with no raising-condition prose — nothing else to align.
  - New: this `TODOS.md`
- **Resume with:** Phase 4 below — ONLY after a pipelex release ships the fix.
- **Quick re-verify:** the e2e command in "Red test" below (expect all tests passing), or the targeted suites in Phase 2's checklist.

## The problem in one paragraph

A user designing a method with `/pipelex-design` used PipeCompose construct mode to copy whole native stuffs into native-typed fields of a structured output — `rejection_email = { from = "email" }` where `email` is a whole `Text` stuff, and `interview_questions = { from = "questions" }` where `questions` is a whole `Text[5]` stuff. Structural validation accepted it; the dry-run runnable gate rejected it because the composed field received the content wrapper object (`TextContent`, `ListContent[...]`) instead of the native value (`str`, `list[str]`). The user's usage was correct: the PipeCompose reference (`docs/building-methods/pipes/pipe-operators/PipeCompose.md`, "Copy value from input variable or nested field") and the composer's own design (`_resolve_from_var` docstring: "TextContent -> str: extract .text", "ListContent -> list[X]: extract items") both promise exactly this conversion. The implementation has gaps. **Verdict: fix pipelex, do not change the language or warn users off the pattern.**

Full analysis with the user's original bundle and reasoning: `../mcp-demos/wip/pipe-compose-issue/README.md` (workspace sibling repo; + runnable repro under `repro/`). Note: that README's §5/§8 conclude "whole-stuff `from` hands over the wrapper **by design**" — that is a misdiagnosis of these bugs as a language rule; this plan is the correction.

## Diagnosis — three gaps, all in `pipelex/pipe_operators/compose/structured_content_composer.py`

All verified empirically against the dev tree (v0.39.1 era, branch `dev`):

1. **`Optional[...]` target fields are never converted.** Non-required structure fields generate `Optional[X]` annotations (`pipelex/core/concepts/structure_generation/generator.py:302-304`). `_get_field_expected_type` (`structured_content_composer.py:377`) returns the raw union annotation, and every `_expects_*` helper returns False on it (`issubclass(Optional[str], str)` raises TypeError → False at `:392-408`; `get_origin(Optional[List[str]])` is `Union`, not `list`, at `:474-484`), so `_convert_for_target_type` falls into its "unknown target type, return as-is" fallback and pydantic then rejects the wrapper. **Proof of oversight, not decision:** the NESTED path already unwraps Optional in `_get_nested_field_class` (`:704-717`); the FROM_VAR path never got the same treatment. And flipping the field to `required = true` makes the same whole-Text copy convert cleanly to `str`.
2. **List items that are native scalars are not extracted.** Even with a required `list`/`item_type = "text"` target (`List[str]`), `_convert_list_items_as_dicts` (`:501`) dumps each `TextContent` item as a dict `{"text": "..."}` via `model_dump` instead of extracting `.text` → `questions.N: string_type` pydantic errors. Related: `_validate_item_compatibility` (`:555`) silently no-ops when the expected item type has no `model_validate` (e.g. `str`), so the mismatch surfaces as a confusing downstream pydantic error rather than a clear conversion error.
3. **Scalar wrappers other than `TextContent` are not handled at all.** `_convert_for_target_type` (`:298`) special-cases only `TextContent` and `ListContent`. A whole `Number` stuff into a required `number` field fails with `NumberContent (expected float)`. Same family presumably applies to `YesNo` → `boolean` and `Date` → `date` fields.

Reference matrix of what worked vs. broke PRE-FIX (v0.39.1 behavior, from the repro — every ❌ row is green since the fix):

| Construct source | Target field | Pre-fix (v0.39.1) |
|---|---|---|
| `{ from = "score.candidate_name" }` (dotted path to scalar leaf) | any matching native | ✅ works (raw Python value, skips conversion) |
| literal (`is_fit = true`) | matching native | ✅ works |
| `{ from = "<whole Text stuff>" }` | required `text` | ✅ works (designed conversion fires) |
| `{ from = "<whole Text stuff>" }` | optional `text` | ❌ gap 1 |
| `{ from = "<whole Text[] stuff>" }` | required `list`/`item_type="text"` | ❌ gap 2 |
| `{ from = "<whole Text[] stuff>" }` | optional `list`/`item_type="text"` | ❌ gaps 1+2 (the user's exact case) |
| `{ from = "<whole Number stuff>" }` | required `number` | ❌ gap 3 |

## Red test (already written, this is the gate)

- `tests/e2e/test_pipe_compose_whole_stuff_mthds.py` — one dry-run test (`validate_bundle` must pass the runnable gate on every pipe) + one parametrized live test (deterministic PipeCompose execution, no inference, asserts composed values AND exact native types).
- Fixture bundle: `tests/e2e/fixtures/compose_whole_stuff/compose_whole_stuff.mthds` — one holder concept + one compose pipe per row of the matrix above.
- Pre-fix state (red): `whole_text_to_required_text_field` (control) passed; the dry-run test and the other live cases failed with the wrapper-mismatch errors quoted in the diagnosis. All green since Phase 1 landed.
- Run it: `.venv/bin/pytest -n auto -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" -o log_level=WARNING --tb=short -q tests/e2e/test_pipe_compose_whole_stuff_mthds.py`

## Fix design

All changes in `pipelex/pipe_operators/compose/structured_content_composer.py` (+ possibly a small typing util):

- **Optional unwrap (gap 1):** add a helper that unwraps `Optional[X]`/`X | None` to `X` when there is exactly one non-`None` arm (handle both `typing.Union` and `types.UnionType` origins — mirror the logic already in `_get_nested_field_class:704-717`). Apply it in `_get_field_expected_type`, and refactor `_get_nested_field_class` to use the same helper. Candidate home if made reusable: `pipelex/tools/typing/`.
- **Scalar wrapper matrix (gap 3):** extend `_convert_for_target_type` so each native scalar wrapper converts to its native target: `NumberContent.number` → `float`/`int`, `YesNoContent.yes_no` → `bool`, and (decision D1) `DateContent` → `date`. Keep the existing "target expects the wrapper class → keep object" behavior symmetrical for each (like `_convert_text_content` does for `TextContent`).
- **List item scalar extraction (gap 2):** in the `list[X]` target path, when the expected item type is a native scalar (`str`/`float`/`int`/`bool`/`date`), extract the scalar from each item wrapper using the same per-wrapper conversion as above, instead of `model_dump`. Keep dict-dumping for structured item types (that path is correct and tested).
- **Loud failure for unconvertible items:** make `_validate_item_compatibility` raise `StructuredContentComposerTypeError` when the expected item type is not a model and no scalar extraction applies, instead of silently passing the item through to a cryptic pydantic error.
- Dotted-path resolution (`_resolve_dotted_path`) already funnels StuffContent leaves through `_convert_for_target_type`, so gaps 1 and 3 fixes benefit it automatically; raw leaves are untouched.

### Decisions to arbitrate (ask Louis if unsure)

- **D1 — matrix scope:** `Text` + `Number` + `YesNo` are clearly in. Is `DateContent` → `date` in scope now (`DateContent` carries `date` + optional `time`; target `date` fields would take `.date`)? Recommendation: include `Date`, skip `Time`/`datetime` until a use case shows up.
- **D2 — true multi-arm unions** (e.g. a field typed `str | int`): recommendation: unwrap ONLY the Optional shape (single non-None arm); leave genuine unions on the current as-is fallback and revisit on demand.
- **D3 — static (pre-dry-run) detection:** a structurally impossible construct source (e.g. whole `Image` stuff → `text` field) could be caught at blueprint validation instead of dry-run. Out of scope here; if judged worthwhile, record as a deferred follow-up in `wip/` per the deferred-items convention.

### Rulings taken (Checkpoint 1)

- **D1 ruling:** followed the recommendation — matrix is `TextContent → str`, `NumberContent → float/int` (never `bool`, an `int` subclass), `YesNoContent → bool`, `DateContent → date` (exact `date` target only, never `datetime`, a `date` subclass). `Time`/`datetime` targets deferred until a use case shows up.
- **D2 ruling:** followed the recommendation — `unwrap_optional` unwraps ONLY the single-non-None-arm shape (both `Optional[X]` and `X | None` origins); genuine multi-arm unions are returned unchanged. Side effect: `_get_nested_field_class` previously picked the *first* non-None arm of a multi-arm union arbitrarily; it now leaves such unions untouched (same as the FROM_VAR path).
- **D3:** untouched, remains a candidate deferred follow-up.

### Deviations from the fix design (Checkpoint 1)

- Instead of one `_convert_*_content` method per wrapper, a single `_extract_native_scalar` conversion-matrix helper runs first in `_convert_for_target_type` (shared by the field path and the list-item path); wrapper → wrapper-class targets keep flowing through the generic `_convert_content_for_field` path, so the "target expects the wrapper class → keep object" symmetry is preserved for every wrapper. `_convert_text_content`'s str-extraction branch moved into that shared helper.
- `_validate_item_compatibility` raises only when the expected item type is a **native scalar** (str/float/int/bool/date), not for every non-model type: non-model item types such as `dict[...]` legitimately validate from the `model_dump` output, so a blanket raise would have regressed them. The list[native-scalar] path normally diverts to `_convert_list_items_as_scalars` (which raises its own clear error) before reaching that guard.
- The unwrap helper landed as `pipelex/tools/typing/annotation_utils.py::unwrap_optional` (subject grant recorded for the positional `annotation` param), unit-tested in `tests/unit/pipelex/tools/test_annotation_utils.py` (flat dir, matching the existing tools test layout).
- Perimeter tests went into a new sibling module `test_pipe_compose_native_scalar_conversions.py` (1 TestClass per module rule) rather than extending `test_pipe_compose_content_conversions.py`; coverage includes a falsy `YesNoContent(yes_no=False) → bool` case and `DateContent → date`.

## Checklist

### Phase 1 — core fix (red → green)

- [x] Diagnose the failure and validate the three gaps empirically (scratchpad repros: required-vs-optional discriminator, required-list failure, Number failure)
- [x] Red e2e test: fixture bundle + test module (see "Red test" above), verified red, `make agent-check` green
- [x] Optional-unwrap helper + use it in `_get_field_expected_type` and `_get_nested_field_class`
- [x] Scalar wrapper conversion matrix in `_convert_for_target_type` (D1 scope)
- [x] List-item native-scalar extraction in the `list[X]` path
- [x] `_validate_item_compatibility` raises clearly on unconvertible item types
- [x] Red e2e module fully green (dry-run + all live cases)

### Phase 2 — perimeter tests

- [x] Sibling module `test_pipe_compose_native_scalar_conversions.py` with: TextContent → `Optional[str]` field, ListContent → `Optional[list[str]]` field, ListContent[TextContent] → `list[str]`, NumberContent → `float`, YesNo (falsy) → `bool`, Date → `date`, using registered Python models with Optional annotations
- [x] Unwrap helper unit-tested (`tests/unit/pipelex/tools/test_annotation_utils.py`)
- [x] `make agent-check` green
- [x] Targeted suites green: `tests/unit/pipelex/pipe_operators/ tests/integration/pipelex/pipes/` + the e2e module
- [x] Full `make agent-test` green

**CHECKPOINT 1 — fix landed and verified.** Update this file: check off the boxes, note any deviation from the fix design, record D1/D2 rulings. Good handoff point before docs.

### Phase 3 — docs + changelog (this repo)

- [x] `docs/building-methods/pipes/pipe-operators/PipeCompose.md`: document the whole-stuff copy in construct mode — worked example copying a whole `Text` and a whole `Text[]` input into native fields, including an optional field; state the conversion matrix (wrapper → native target, wrapper → wrapper target)
- [x] `CHANGELOG.md` `[Unreleased]` → Fixed: PipeCompose construct `{ from = "..." }` now converts whole native stuffs into optional native fields, native-scalar list items, and non-Text scalar wrappers (Number/YesNo/…)
- [x] Grep `docs/` for other PipeCompose construct mentions that describe or constrain `from` semantics; align them (no other page describes construct `from`; error pages are generated boilerplate — nothing to change)

**CHECKPOINT 2 — ✅ CLOSED.** Committed, gates passed, PR #1051 merged to `dev`; the fix shipped in release v0.39.2.

### Phase 4 — cross-repo follow-ups (de-gated by v0.39.2)

- [ ] `pipelex-plugins/skills/pipelex-design/references/writing-mthds.md` (source of truth; per-target copies under `pipelex-plugins/{pipelex,pipelex-vibe,pipelex-codex}/skills/...`): add a worked whole-stuff copy example to the PipeCompose construct section. Do NOT add a "from must reference a structured field" warning — that would enshrine the bug
- [ ] `mthds-plugins/mthds-dev/skills/shared/mthds-reference.md`: same check — align the construct `from` description if needed
- [ ] `mcp-demos/wip/pipe-compose-issue/README.md`: annotate §5/§8 — root cause was implementation gaps (fixed in pipelex <version>), not a language rule; the compose-based design the user abandoned is the recommended shape again
- [ ] Optional (user-facing): the shipped `recruitment_screening` method (`mcp-demos/pipelex-wip/recruitment_screening/`) can revert to the generate → compose two-step design to restore the structural carry-over guarantee — Louis/user's call
