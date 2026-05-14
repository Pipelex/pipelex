# Deferred — `FileNotFoundError` category vs `UserActionKind` mismatch

**Surfaced during:** Phase 11 (`_tprl/TODOS.md`) code review of `de61d4b9`.

## Issue

In `docling_extract_worker.py` and `pypdfium2_worker.py`, the `FileNotFoundError` branch is categorized as:

- `error_category=InferenceErrorCategory.CONFIGURATION`
- `user_action.kind=UserActionKind.CHANGE_INPUT`

This pairing is internally inconsistent with how `CONFIGURATION` is used elsewhere in the codebase, which is typically paired with `CHECK_CREDENTIALS`, `CHANGE_MODEL`, or `CONTACT_SUPPORT`. A missing-input-file is more naturally a *content* problem (the input the caller provided cannot be opened) than a *configuration* problem (the setup is wrong).

## Why we kept the current pairing in Phase 11

The pre-existing worker code already raised `error_category=CONFIGURATION` on `FileNotFoundError`, and the pre-existing `test_pypdfium2_worker_error_handling.py` / `test_docling_worker_error_handling.py` lock in `report.error_category == "configuration"`. Changing the category in the same commit that added the structured `UserAction` would have either (a) flipped existing test expectations or (b) introduced a category-vs-action inconsistency.

We chose (b) for Phase 11 to keep the existing categorization contract intact and isolate the `UserAction` migration as additive.

## Resolution options

1. **Flip to `CONTENT` + `CHANGE_INPUT`.** Matches every other CONTENT branch in the codebase (Mistral 400, Google 400, Anthropic content-policy …). Requires updating the existing extract-worker tests to expect `"content"` rather than `"configuration"` and (importantly) reviewing whether anything downstream branches on the category — `retryable` is `False` for both, so retry behavior is unchanged.

2. **Introduce a new `UserActionKind.CHECK_INPUT_PATH`.** Keeps the CONFIGURATION category but gives a tighter user-action signal for "the path/URI you passed doesn't exist." Worth doing only if we have a concrete CLI / agent rendering that wants to distinguish "the input file doesn't exist" from "the file exists but is malformed."

3. **Leave it.** The mismatch is real but harmless. Document and move on.

## Recommendation

Resolution option **1** when the categorization can be revisited as part of a CLI / telemetry consumer change — i.e. when there is a concrete consumer that would benefit from the cleaner classification. Until then, leave as-is.

## Affected files

- `pipelex/plugins/docling/docling_extract_worker.py` (FileNotFoundError branch)
- `pipelex/plugins/pypdfium2/pypdfium2_worker.py` (FileNotFoundError branch)
- `tests/unit/pipelex/plugins/docling/test_docling_worker_error_handling.py` (locks in `"configuration"`)
- `tests/unit/pipelex/plugins/pypdfium2/test_pypdfium2_worker_error_handling.py` (locks in `"configuration"`)
- `tests/unit/pipelex/plugins/docling/test_docling_worker_semantic.py` (asserts CONFIGURATION + CHANGE_INPUT in Phase 11)
- `tests/unit/pipelex/plugins/pypdfium2/test_pypdfium2_worker_semantic.py` (asserts CONFIGURATION + CHANGE_INPUT in Phase 11)
