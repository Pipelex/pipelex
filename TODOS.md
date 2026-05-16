# TODOS — Fix two error-classification miscategorizations

> **Type:** TDD plan (RED → GREEN → REFACTOR), two independent bug fixes with a checkpoint between them.
> **Source:** [wip/error-handling/deferred-items/file-not-found-category-mismatch.md](wip/error-handling/deferred-items/file-not-found-category-mismatch.md) and item 1 of [wip/error-handling/deferred-items/search-worker-review-followups.md](wip/error-handling/deferred-items/search-worker-review-followups.md).
> **Branch:** `fix/error-classification-categories`, based on `feature/Error-handling-2`.

---

## Status — as of 2026-05-16

Fresh branch, nothing done yet. **The next session starts at Phase 0.**

Two independent classification bugs, both surfaced during the worker-classification sweep code reviews and deliberately deferred so the sweep could land additively. Each is a small, self-contained fix; do them in order, commit separately, with a checkpoint between.

`make agent-check` and `make agent-test` are expected clean on this branch at creation time — verify in Phase 0 so any later failure is attributable to this work.

---

## The two bugs

### Bug A — `LinkupNoResultError` classified `TRANSIENT` (should be `CONTENT`)

`_classify_linkup_error` in `pipelex/plugins/linkup/linkup_search_worker.py` (`_classify_linkup_error`, ~line 42) and `pipelex/plugins/linkup/linkup_extract_worker.py` (~line 47) has **no explicit branch** for `LinkupNoResultError`. It falls through to the final fallback (`msg = f"Linkup error: {exc}"`), which classifies every unrecognized error `error_category=TRANSIENT` + `UserActionKind.WAIT_AND_RETRY`.

A search "no result" is **not transient**: retrying the identical query returns no result again. With the `PipeRouter` transient-retry loop now landed (`max_transient_retries`, exponential backoff), a `TRANSIENT` classification means the router burns its full retry budget and backoff sleeps on a query that cannot succeed. Before the retry loop landed this was a cosmetically wrong label; now it wastes real time.

**Fix:** add an explicit `isinstance(exc, LinkupNoResultError)` branch *before* the fallback, classifying it `error_category=InferenceErrorCategory.CONTENT` + `UserActionKind.CHANGE_INPUT`, with a detail along the lines of "Linkup found no results — broaden or rephrase the query." Apply to **both** Linkup workers (search → `SearchJobFailureError`, extract → `ExtractJobFailureError`). `LinkupNoResultError` is already imported in both files (it appears in the `except (...)` tuple), so no new import is needed.

**Behavior change — intentional.** `InferenceErrorCategory.CONTENT.is_retryable` is `False`; `TRANSIENT.is_retryable` is `True`. After the fix the router no longer retries a no-result search — that is the point of the fix. Must be called out in the changelog.

> The deferred doc mentions "all three Linkup workers ... and the shared fallback." At branch-creation time there are only two Linkup worker files, each carrying its own copy of `_classify_linkup_error`. In Phase 0, grep `_classify_linkup_error` across `pipelex/plugins/linkup/` to confirm there is no third site or shared helper that also needs the branch.

### Bug B — `FileNotFoundError` classified `CONFIGURATION` (should be `CONTENT`)

The `except FileNotFoundError` branch is classified `error_category=CONFIGURATION` + `UserActionKind.CHANGE_INPUT` in:

- `pipelex/plugins/docling/docling_extract_worker.py` (~line 97)
- `pipelex/plugins/pypdfium2/pypdfium2_worker.py` (~line 91)

`CONFIGURATION` is used everywhere else for setup problems (paired with `CHECK_CREDENTIALS` / `CHANGE_MODEL` / `CONTACT_SUPPORT`); a missing input file is a *content* problem — the input the caller provided cannot be opened. The current `CONFIGURATION` + `CHANGE_INPUT` pairing is internally inconsistent. The branches immediately below the `FileNotFoundError` one in both files already use `CONTENT` + `CHANGE_INPUT` — the fix makes the missing-file branch match its siblings.

**Fix:** flip the `FileNotFoundError` branch to `error_category=InferenceErrorCategory.CONTENT`, keeping `UserActionKind.CHANGE_INPUT`.

**Behavior change — none.** `CONFIGURATION` and `CONTENT` are both `is_retryable=False`, so retry behavior is unchanged. This is purely a correctness/consistency fix. Confirm in Phase 0 that nothing downstream branches on the specific category beyond `retryable` (a quick grep of `error_category` consumers).

---

## Phase 0 — Orientation

- Confirm a clean baseline: `make agent-check`, then the targeted test command in Phase 3.
- Confirm the category decisions above. Both are "Option 1" from the deferred-items docs — already the recommended resolution; there is no open design question, just confirm and proceed.
- Grep to confirm exact sites and current line numbers (the `~line` numbers above are from `feature/Error-handling-2` at branch creation and may have drifted):
  - `_classify_linkup_error` across `pipelex/plugins/linkup/`
  - `FileNotFoundError` across `pipelex/plugins/docling/` and `pipelex/plugins/pypdfium2/`

## Phase 1 — Bug A: Linkup no-result → `CONTENT` (RED → GREEN)

### RED

- `tests/unit/pipelex/plugins/linkup/test_linkup_worker_error_handling.py` has **no** `LinkupNoResultError` case at branch creation — so RED *adds* coverage rather than flipping an existing assertion. Add a case (one `TestClass` per module; parametrize with the existing error cases) asserting, for a `LinkupNoResultError`, `report.error_category == "content"` and `report.retryable is False` — for both the search and the extract worker. It fails today (the error falls through to the `TRANSIENT` fallback).
- Check `tests/unit/pipelex/plugins/linkup/test_data.py` for the existing Linkup error fixtures and mirror their shape.

### GREEN

- Add the explicit `isinstance(exc, LinkupNoResultError)` branch to `_classify_linkup_error` in both `linkup_search_worker.py` and `linkup_extract_worker.py`.
- `make agent-check`; run the linkup unit tests.

> **CHECKPOINT 1 — Bug A done.** Commit Bug A on its own: `fix: classify Linkup no-result as CONTENT, not TRANSIENT`. The two bugs are independent — a clean separate commit keeps the diff reviewable. Next session/step: Phase 2.

## Phase 2 — Bug B: FileNotFoundError → `CONTENT` (RED → GREEN)

### RED

- `tests/unit/pipelex/plugins/pypdfium2/test_pypdfium2_worker_error_handling.py` (~line 82) asserts `report.error_category == "configuration"` for a `FileNotFoundError`. Flip the expectation to `"content"`. It now fails (the worker still raises `CONFIGURATION`).
- `tests/unit/pipelex/plugins/docling/test_docling_worker_error_handling.py` — grep for the `FileNotFoundError` case and flip its category expectation to `"content"`; if there is no such case, add one mirroring the pypdfium2 test.

### GREEN

- Flip the `except FileNotFoundError` branch from `CONFIGURATION` to `CONTENT` in both `docling_extract_worker.py` and `pypdfium2_worker.py`.
- `make agent-check`; run the docling + pypdfium2 unit tests.

## Phase 3 — REFACTOR + docs + full verification

- `CHANGELOG.md` `[Unreleased]` — one entry covering both fixes. Explicitly note that the Linkup change makes a no-result search **non-retryable** (intentional behavior change — stops the router from retrying a query that cannot succeed), and that the `FileNotFoundError` change does not alter retry behavior.
- Resolve the two deferred-items docs:
  - Delete `wip/error-handling/deferred-items/file-not-found-category-mismatch.md` (fully addressed).
  - In `wip/error-handling/deferred-items/search-worker-review-followups.md`, mark item 1 (`LinkupNoResultError`) as landed; **keep the remaining items** — they are out of scope here.
- `wip/error-handling/README.md` — the retry/worker-classification tracks are already "Landed"; no status-table change is required. Optionally note the two cleanups.
- `make agent-check` clean; `make agent-test` full suite green.

### Targeted test command

Run the three worker error-handling test modules directly (pure unit tests — they construct SDK exceptions and call `to_error_report()`, no provider calls):

```bash
.venv/bin/pytest -o log_level=WARNING --tb=short -q \
  tests/unit/pipelex/plugins/linkup/test_linkup_worker_error_handling.py \
  tests/unit/pipelex/plugins/docling/test_docling_worker_error_handling.py \
  tests/unit/pipelex/plugins/pypdfium2/test_pypdfium2_worker_error_handling.py
```

Run the full `make agent-test` before wrapping up, per `_tprl/CLAUDE.md`.

---

## Out of scope

- The items in `search-worker-review-followups.md` beyond item 1.
- The Extract / Classify / Render decomposition ([wip/error-handling/track-extract-classify-render.md](wip/error-handling/track-extract-classify-render.md)) — the large per-worker deduplication refactor; a separate effort.
- Re-categorizing any `CONFIGURATION` / `TRANSIENT` site not named above.

## Risks / gotchas

- **Don't widen the Linkup fix.** Only `LinkupNoResultError` moves to `CONTENT`; `LinkupTimeoutError` / `LinkupTooManyRequestsError` are genuinely `TRANSIENT` and stay. Add the new branch *before* the catch-all fallback, not in place of it — the fallback must still classify unrecognized errors as `TRANSIENT`.
- **`error_category` is a `StrEnum`.** Tests compare against the string value (`"content"`, `"configuration"`); worker code uses the enum member (`InferenceErrorCategory.CONTENT`). Keep both straight.
- **Both Linkup workers, in sync.** The deferred doc is explicit: fix search and extract together so their `_classify_linkup_error` copies don't drift.
