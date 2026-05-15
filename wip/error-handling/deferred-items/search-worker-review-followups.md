# Deferred — Phase 12 search worker review follow-ups

**Surfaced during:** Phase 12 (`_tprl/TODOS.md`) code review of `ca2763c2` "feat: Phase 12 search worker audits".

Three minor, non-blocking observations from the code review. None is a Phase 12 regression — each is either a pre-existing pattern faithfully carried forward or a test-scope choice consistent with the sibling extract workers.

---

## 1. `LinkupNoResultError` classified as `TRANSIENT` / `WAIT_AND_RETRY`

`_classify_linkup_error` (in all three Linkup workers — search, extract, and the shared fallback) classifies `LinkupNoResultError` as `error_category=TRANSIENT` with `UserActionKind.WAIT_AND_RETRY`.

For a search, "no result" is arguably *not* transient — retrying the identical query will return no result again. A non-retryable category (e.g. `CONTENT` with `CHANGE_INPUT`, "broaden or rephrase the query") would be more accurate.

**Why we kept it in Phase 12:** the pre-existing `linkup_search_worker.py` already routed `LinkupNoResultError` through the `TRANSIENT` fallback, and the reference `linkup_extract_worker.py` does the same. Phase 12's goal was sibling consistency, so it mirrored the established pattern rather than drifting.

**Resolution:** when revisited, fix it across all three Linkup workers together (search, extract, and any shared fallback) so they stay consistent. Check the existing `test_linkup_worker_error_handling.py` test data — it locks in `no_result → TRANSIENT` / `"linkup error"` substring — and update those expectations.

**Affected files:**

- `pipelex/plugins/linkup/linkup_search_worker.py` (`_classify_linkup_error` fallback branch)
- `pipelex/plugins/linkup/linkup_extract_worker.py` (`_classify_linkup_error` fallback branch)
- `tests/unit/pipelex/plugins/linkup/test_data.py` (`SEARCH_ERROR_CASES` / `EXTRACT_ERROR_CASES` lock in `TRANSIENT`)

---

## 2. `_search_structured` path not directly tested

The new semantic tests (`test_linkup_search_worker_semantic.py`, `test_gateway_search_worker_semantic.py`) exercise the classification logic only through `_search_sourced_answer`. The `_search_structured` entry point routes through the same shared helper (`_classify_linkup_error` / `_call_relay`), so the classification logic *is* fully covered — but the second entry point is never exercised end-to-end.

This is consistent with the sibling `test_gateway_extract_worker_semantic.py`, which likewise tests only `_extract_web_fetch` and not `_extract_base64_url`. The shared-helper design makes the gap low-risk.

**Resolution:** optional — add a parametrized case (or a `@pytest.mark.parametrize` over the entry-point method) covering `_search_structured` if a regression ever appears there.

---

## 3. Gateway test omits non-status `APIError` subtypes

`test_gateway_search_worker_semantic.py` parametrizes the five `APIStatusError` subclasses (HTTP status errors). Non-status `APIError` subtypes — `portkey_exc.APITimeoutError` and `APIConnectionError` — also hit the same `except portkey_exceptions.APIError` branch and would produce metadata with `status_code=None`.

The sibling `test_gateway_extract_worker_semantic.py` has the identical gap, so Phase 12 is consistent with the reference.

**Resolution:** optional — add a parametrized case for a non-status `APIError` (timeout / connection) to both the search and extract Gateway semantic tests to assert the `status_code=None` metadata shape.

**Affected files:**

- `tests/unit/pipelex/plugins/gateway/test_gateway_search_worker_semantic.py`
- `tests/unit/pipelex/plugins/gateway/test_gateway_extract_worker_semantic.py`
