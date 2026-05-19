# Deferred — Phase 12 search worker review follow-ups

**Surfaced during:** Phase 12 (`_tprl/TODOS.md`) code review of `ca2763c2` "feat: Phase 12 search worker audits".

Three minor, non-blocking observations from the code review. None is a Phase 12 regression — each is either a pre-existing pattern faithfully carried forward or a test-scope choice consistent with the sibling extract workers.

---

## 1. `LinkupNoResultError` classified as `TRANSIENT` / `WAIT_AND_RETRY` — LANDED

**Status:** resolved on branch `fix/error-classification-categories`. `_classify_linkup_error` now has an explicit `LinkupNoResultError` branch — `CONTENT` + `CHANGE_INPUT` — in both the search and the extract worker, placed before the `TRANSIENT` catch-all. The `test_data.py` `no_result` cases were updated to expect `CONTENT`, and explicit `to_error_report()` no-result tests assert `retryable is False`. Only two Linkup worker files exist (no third site / shared fallback); both were fixed together.

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
