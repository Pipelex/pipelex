# TODOS — Inference Workers: Excellent Error Handling

> **Source of truth:** [wip/error-handling/track-worker-classification.md](wip/error-handling/track-worker-classification.md).
> **Implementation reference:** `pipelex/plugins/anthropic/anthropic_llm_worker.py`.
> **Test reference:** `tests/unit/pipelex/plugins/anthropic/test_anthropic_worker_object_error_handling.py`.
> **Out-of-scope follow-up:** [wip/error-handling/track-extract-classify-render.md](wip/error-handling/track-extract-classify-render.md) — the natural next step once this sweep lands. Do **not** pull forward.

---

## Strategy — how we test SDK boundaries

We do **not** mock SDK modules wholesale. We:

1. **Construct real SDK exception types** with minimal fake response objects (e.g. `anthropic.RateLimitError(..., response=httpx.Response(status_code=429, request=...))`). The worker's `isinstance(...)` checks fire against the real classes, so the test survives SDK renames.
2. **Patch only the SDK's outbound I/O method** with `mocker.AsyncMock(side_effect=sdk_exc)` — never replace exception classes or SDK modules.
3. **For instructor-using LLM workers, use real `instructor.from_*()`** against a patched underlying client. The whole point of this work is to handle `InstructorRetryException`'s real wrapping shape; a faked instructor would defeat it.

**Tradeoff:** real-instructor tests are ~0.5s each because instructor runs its full retry loop. We keep **one** real-instructor end-to-end test per provider; the other categorization cases use a synthetic `_wrap_in_instructor_retry(sdk_exc)` helper to build an `InstructorRetryException` directly. Constructing some SDK exceptions requires reading the SDK source for required kwargs (httpx shapes for OpenAI/Anthropic; Google's response wrapper). Acceptable cost; the alternative (mock modules) is brittle and fights the type checker.

---

## Scope

Lift every inference worker **beyond** the current Anthropic-as-reference standard. "Beyond" means:

1. **Primary fix:** close the `InstructorRetryException` unwrap defect on OpenAI Completions, OpenAI Responses, Mistral LLM, Google Gemini LLM (the four workers flagged in [track-worker-classification.md](wip/error-handling/track-worker-classification.md#instructor-unwrap-missing-on-four-other-workers)).
2. **Beyond-reference upgrade A — `UNKNOWN` category.** The current "fall back to `CONTENT`" for an unrecognized underlying exception is wrong. Add `InferenceErrorCategory.UNKNOWN` (with `is_retryable=False`) and route the fallback there. Surfaces real unknowns in telemetry instead of silently mis-categorizing them.
3. **Beyond-reference upgrade B — structured SDK metadata.** Every raised `CogtError` carries a `provider_metadata: ProviderErrorMetadata` with `status_code`, `request_id`, `retry_after_seconds`, `provider_error_code`, `body`. Unlocks the retry / temporal / CLI tracks already listed as open in the README.
4. **Beyond-reference upgrade C — structured `UserAction`.** Replace the free-form `user_action: str` with `user_action: UserAction(kind: UserActionKind, detail: str)`. Lets the CLI render consistent advice and lets agent JSON be typed.
5. **Hygiene:** migrate every worker's `instructor.exceptions` → `instructor.core` import.
6. **Coverage:** test parity with the Anthropic suite per provider — ~7 categorization cases via synthetic wrap + 1 real-instructor end-to-end. Each case now asserts `provider_metadata` and `user_action.kind` alongside `error_category`.
7. **Other worker kinds:** audit and lift img-gen, extract, and search workers to the same standard (including upgrades A–C).

The Extract/Classify/Render decomposition that would eliminate duplication across all 18+ workers is **deferred** to [track-extract-classify-render.md](wip/error-handling/track-extract-classify-render.md). It is the natural next step once this sweep lands.

TDD discipline applies to every phase: **RED** (test that fails) → **GREEN** (minimal code to pass) → **REFACTOR** (clean up).

---

## Phase 0 — Test helper foundation

Lift reusable test pieces from `tests/unit/pipelex/plugins/anthropic/test_anthropic_worker_object_error_handling.py` to a shared module so every provider test can import them.

- [x] **RED** — write `tests/helpers/test_instructor_test_utils.py` asserting:
  - `wrap_in_instructor_retry(sdk_exc)` returns an `InstructorRetryException` whose `failed_attempts[-1].exception is sdk_exc`
  - `wrap_in_instructor_retry(sdk_exc, include_failed_attempts=False)` produces a wrap where `failed_attempts is None or []` (tenacity-fallback path; `__cause__` is set by callers)
  - `DummySchema` is a minimal `BaseModel` subclass with a single `text: str` field
- [x] **GREEN** — create `tests/helpers/instructor_test_utils.py` exposing `wrap_in_instructor_retry`, `DummySchema`, and a `make_llm_job(mocker)` skeleton lifted from the Anthropic test (names made public so pyright doesn't flag cross-module private-use)
- [x] Update `test_anthropic_worker_object_error_handling.py` to import from the shared helper; confirm `.venv/bin/pytest tests/unit/pipelex/plugins/anthropic/` stays green
- [x] Investigate whether **AWS Bedrock LLM worker** (`pipelex/plugins/bedrock/bedrock_llm_worker.py`) uses `instructor` for structured generation. **Finding:** No — `_gen_object` raises `LLMCapabilityError` ("It is not possible to generate objects with a BedrockLLMWorker") with a `# TODO: try with the newest instructor release` comment. **No Phase 8.5 needed.** Bedrock LLM still benefits from upgrades A–C in Phase 11.
- [x] Run `make agent-check`

> ### **STOP — CHECKPOINT A: Test helper foundation landed**
>
> Update this file's checkboxes, commit, and prepare cold-start handoff. Next session resumes at Phase 1.
>
> **Hand-off context:**
> - Shared helpers at `tests/helpers/instructor_test_utils.py` ✅
> - Anthropic tests still green ✅
> - AWS Bedrock instructor-usage decision: _record in Running Notes_

---

## Phase 1 — Shared unwrap helper

Move `_extract_underlying_sdk_exception` from the Anthropic worker to `pipelex/cogt/inference/error_classification.py` so the four pending workers can share one implementation. Promote it to a public name (drop the leading underscore).

- [x] **RED** — write `tests/unit/pipelex/cogt/inference/test_error_classification_unwrap.py`:
  - returns the SDK exception when `instructor_exc.failed_attempts[-1].exception` is set
  - falls back to `__cause__.last_attempt._exception` when `failed_attempts` is empty (tenacity path)
  - returns `None` when both paths are empty
  - never raises on malformed input (defensive)
- [x] **GREEN** — move the function from `pipelex/plugins/anthropic/anthropic_llm_worker.py` to `pipelex/cogt/inference/error_classification.py`. Renamed to `extract_underlying_sdk_exception` (public).
- [x] Update `anthropic_llm_worker.py` to import from the shared module; Anthropic worker tests still pass. Removed the now-redundant `test_extract_underlying_uses_cause_when_failed_attempts_missing` test from the Anthropic suite (covered by the new shared test module).
- [x] Run `make agent-check`

> ### **STOP — CHECKPOINT B: Shared unwrap helper landed**
>
> **Hand-off context:**
> - `extract_underlying_sdk_exception` lives in `pipelex/cogt/inference/error_classification.py` ✅
> - Anthropic worker imports from the shared module ✅
> - Next phases land the three data-contract upgrades before touching the four pending workers

---

## Phase 2 — `InferenceErrorCategory.UNKNOWN` (upgrade A)

The current "fall back to `CONTENT`" path when `extract_underlying_sdk_exception` returns something we don't recognize is technically wrong — `CONTENT` means "the LLM returned bad content," but the truth is "we don't know what happened." `UNKNOWN` with `is_retryable=False` makes downstream retry decisions accurate and surfaces "we should add this case" in telemetry.

- [x] **RED** — write `tests/unit/pipelex/cogt/inference/test_error_classification_unknown.py`. (Note: the enum is defined in `pipelex/cogt/exceptions.py`, not `error_classification.py`. The plan-doc reference was off; tests still import from the correct path.)
- [x] **RED** — in `test_anthropic_worker_object_error_handling.py`, renamed `test_unrecognized_underlying_falls_back_to_content` → `test_unrecognized_underlying_falls_back_to_unknown`; assertion now expects `InferenceErrorCategory.UNKNOWN`.
- [x] **GREEN** — added `UNKNOWN = "unknown"` to `InferenceErrorCategory` in `pipelex/cogt/exceptions.py` (lowercase value to match the existing convention; the test asserts `str(...) == "unknown"`).
- [x] **GREEN** — extended `InferenceErrorCategory.is_retryable` to return `False` for `UNKNOWN` (added to the existing `CONFIGURATION | CONTENT | CAPACITY` group).
- [x] **GREEN** — Anthropic worker's `InstructorRetryException` fallback now raises `error_category=UNKNOWN` (was `CONTENT`).
- [x] Run `make agent-check`

> ### **STOP — CHECKPOINT C: `UNKNOWN` category landed**
>
> **Hand-off context:**
> - `UNKNOWN` category present with `is_retryable=False` ✅
> - Anthropic reference worker uses `UNKNOWN` for the unrecognized-underlying fallback ✅
> - Other workers still use `CONTENT` fallback; migrated in their respective phases

---

## Phase 3 — `ProviderErrorMetadata` field (upgrade B)

Every raised inference error should carry structured SDK metadata so downstream consumers (retry/temporal/CLI) don't have to scrape it back from the exception chain.

- [x] **RED** — wrote `tests/unit/pipelex/cogt/inference/test_provider_error_metadata.py` (required/optional fields, round-trip)
- [x] **RED** — wrote `tests/unit/pipelex/plugins/anthropic/test_extract_anthropic_metadata.py` (status_code, request_id, retry-after, provider_error_code from body, graceful handling of APIConnectionError/APITimeoutError shapes)
- [x] **RED** — in `test_anthropic_worker_object_error_handling.py`, added `provider_metadata` assertions to rate-limit/quota/bad-request cases plus a `to_error_report()` serialization test.
- [x] **GREEN** — defined `ProviderErrorMetadata` (Pydantic `BaseModel`) in `pipelex/cogt/inference/error_classification.py`.
- [x] **GREEN** — added `provider_metadata: ProviderErrorMetadata | None = None` on `CogtError` (rather than scattering on each of the four leaf classes). Rationale in running notes — every CogtError subclass now carries the field uniformly with no per-class `__init__` plumbing.
- [x] **GREEN** — wrote `extract_anthropic_metadata(exc: BaseException) -> ProviderErrorMetadata` in `pipelex/cogt/inference/error_classification.py`. Tolerates the two SDK shapes (APIStatusError vs APIConnectionError/APITimeoutError).
- [x] **GREEN** — updated `_raise_categorized_anthropic_sdk_error` to call `extract_anthropic_metadata(sdk_exc)` once and pass `provider_metadata=metadata` to every `LLMCompletionError` and `AnthropicCredentialsError` raise.
- [x] **GREEN** — added `provider_metadata` to `ErrorReport` (with `arbitrary_types_allowed=True` for the Pydantic dataclass), and wired the field into `CogtError.to_error_report()`. Used `rebuild_dataclass(ErrorReport, ...)` in `cogt/exceptions.py` to resolve the forward reference at import time (keeps `base_exceptions.py` free of cogt deps).
- [x] Ran `make agent-check` — clean.

> ### **STOP — CHECKPOINT D: `ProviderErrorMetadata` field landed**
>
> **Hand-off context:**
> - Four dynamic-category exception types carry `provider_metadata` ✅
> - Anthropic worker (reference) populates it via `extract_anthropic_metadata` ✅
> - `to_error_report()` serializes it ✅
> - Other workers leave `provider_metadata=None` for now; migrated in their respective phases

---

## Phase 4 — Structured `UserAction` (upgrade C)

Replace the free-form `user_action: str` with `user_action: UserAction(kind: UserActionKind, detail: str)`. This phase has two parts: define the new types and migrate every existing call site mechanically. Per-worker phases later refine the `kind` from the placeholder `UNKNOWN` to semantic values.

- [x] **RED** — wrote `tests/unit/pipelex/cogt/inference/test_user_action.py`:
  - `UserActionKind` is a `StrEnum` with values `WAIT_AND_RETRY`, `CHECK_BILLING`, `CHECK_CREDENTIALS`, `CHANGE_INPUT`, `CHANGE_MODEL`, `CONTACT_SUPPORT`, `UNKNOWN`
  - `UserAction` is a Pydantic `BaseModel` with `kind: UserActionKind` and `detail: str`
  - Round-trips through `model_dump`/`model_validate`
- [x] **RED** — updated Anthropic worker test cases to assert `user_action.kind` AND `user_action.detail` per the semantic mapping
- [x] **GREEN** — defined `UserActionKind` (StrEnum) and `UserAction` (BaseModel) in `pipelex/cogt/inference/error_classification.py`
- [x] **GREEN** — changed the `user_action` field type on `CogtError` from `str | None` to `UserAction | None`; updated `ErrorReport` accordingly with a TYPE_CHECKING forward ref; extended the `rebuild_dataclass` namespace in `cogt/exceptions.py` to include `UserAction`
- [x] **GREEN — mechanical migration of every existing call site:** every `user_action=...` site in `pipelex/plugins/**` now wraps the existing advice string as `UserAction(kind=UserActionKind.UNKNOWN, detail=<the_string>)`. Also migrated the two class-level defaults: `InferenceBackendCredentialsError` (cogt/exceptions.py) and `AnthropicCredentialsError` (plugins/anthropic/anthropic_exceptions.py)
- [x] **GREEN** — refined the Anthropic worker (reference) to use semantic `UserActionKind` values: rate-limit → `WAIT_AND_RETRY`, quota → `CHECK_BILLING`, timeout/connection → `WAIT_AND_RETRY`, content-policy → `CHANGE_INPUT`, bad-request fallback → `CHANGE_INPUT`, permission-denied → `CHECK_CREDENTIALS`
- [x] **GREEN** — `to_error_report()` serialization unchanged structurally; nested `UserAction` is now serialized by `TypeAdapter.dump_python()` as a `{"kind": "...", "detail": "..."}` dict (Pydantic v2 handles the nested model). CLI consumers (`pipelex/cli/error_handlers.py` and `pipelex/cli/agent_cli/commands/agent_output.py`) now read `report.user_action.detail` instead of treating it as a string.
- [x] **VERIFY** — targeted tests pass: `tests/unit/pipelex/cogt/`, `tests/unit/pipelex/plugins/`, `tests/unit/pipelex/cli/` all green.
- [x] Ran `make agent-check` — clean (0 errors, 0 warnings).

> ⚠️ **Risk note:** `to_error_report()` JSON shape changes from `"user_action": "<string>"` to `"user_action": {"kind": "...", "detail": "..."}`. Consumers downstream (CLI rendering, agent JSON, Temporal `ApplicationError.details`) read fields not specific shapes, but verify with a grep across `pipelex/` and the CLI for any code that does `error_report["user_action"]` as a string. Bring it up to the new shape in the same phase.

> ### **STOP — CHECKPOINT E: Structured `UserAction` landed**
>
> **Hand-off context:**
> - `UserAction` model + `UserActionKind` enum defined ✅
> - Field type changed on every `CogtError` subclass that owns `user_action` ✅
> - Every existing call site mechanically migrated to wrap with `UserAction(kind=UNKNOWN, detail=<existing string>)` ✅
> - Anthropic worker fully refined with semantic `UserActionKind` values ✅
> - `to_error_report()` JSON shape updated ✅
> - Other workers still carry `kind=UNKNOWN` placeholder; refined in their respective phases

---

## Phase 5 — OpenAI Completions LLM

Apply unwrap-and-dispatch to `pipelex/plugins/openai/openai_completions_llm_worker.py`. The current `_gen_object` body has a nested `try { try { ... } except InstructorRetryException }`. Collapse to a single `try`; replace the inner with the unwrap-and-dispatch branch; replace the six SDK clauses with a single tuple-catch that delegates to the same categorization helper `_gen_text` uses. Simultaneously: write `extract_openai_metadata`, populate `provider_metadata`, refine `user_action.kind` to semantic values.

- [x] **RED** — wrote `tests/unit/pipelex/plugins/openai/test_extract_openai_metadata.py` covering status_code, request_id (via `exc.request_id` set from `x-request-id` header in `APIStatusError.__init__`), retry-after, provider_error_code (from `exc.type` / `exc.code` since OpenAI's `_make_status_error` already pre-unwraps `body["error"]`), and the `APIConnectionError`/`APITimeoutError` shapes.
- [x] **RED** — wrote `tests/unit/pipelex/plugins/openai/test_openai_completions_worker_object_error_handling.py` mirroring the Anthropic layout: rate-limit→TRANSIENT/WAIT_AND_RETRY, quota→CAPACITY/CHECK_BILLING, timeout/connection→TRANSIENT/WAIT_AND_RETRY, bad-request+content-policy→CONTENT/CHANGE_INPUT, bad-request generic→CONTENT/CHANGE_INPUT, auth→CONFIGURATION/CHECK_CREDENTIALS, not-found→CONFIGURATION/CHANGE_MODEL, non-SDK→UNKNOWN with provider_metadata=None, plus real-instructor end-to-end.
- [x] **GREEN** — added `extract_openai_metadata` in `pipelex/cogt/inference/error_classification.py` along with a small `_request_id_from_exc_or_response` helper (Anthropic exposes `exc.request_id` directly; OpenAI mirrors it from `response.headers["x-request-id"]` via `APIStatusError.__init__`).
- [x] **GREEN** — refactored `_gen_object`: collapsed the nested try, added `InstructorRetryException` unwrap-and-dispatch through a new `_raise_categorized_openai_sdk_error` helper, and routes the unrecognized-underlying fallback to `UNKNOWN`. Tuple-catch on direct-path SDK exceptions also delegates to the same helper.
- [x] **GREEN** — `_gen_text` now uses the same `_raise_categorized_openai_sdk_error` helper. Every raise carries `provider_metadata=extract_openai_metadata(sdk_exc)` and a semantic `UserActionKind`.
- [x] Migrated `from instructor.exceptions import InstructorRetryException` → `from instructor.core import InstructorRetryException`.
- [x] **AUDIT** — OpenAI SDK hierarchy (`openai/_exceptions.py`): `BadRequestError(400)`, `AuthenticationError(401)`, `OAuthError(extends AuthenticationError)`, `PermissionDeniedError(403)`, `NotFoundError(404)`, `ConflictError(409)`, `UnprocessableEntityError(422)`, `RateLimitError(429)`, `InternalServerError(5xx)`, plus `APIConnectionError`/`APITimeoutError`. Added `InternalServerError` and `PermissionDeniedError` to the tuple-catch (previously missing). `ConflictError` / `UnprocessableEntityError` are not raised by the chat-completion path in practice and fall through to the `UNKNOWN` path; documented here so they can be added later if telemetry shows them appearing.
- [x] Ran `.venv/bin/pytest tests/unit/pipelex/plugins/openai/` (60 passed) and `make agent-check` (0 errors, 0 warnings).

> ### **STOP — CHECKPOINT F: OpenAI Completions done**
>
> **Hand-off context:**
> - Wrapped-path categorization parity with `_gen_text` ✅
> - `extract_openai_metadata` helper landed ✅
> - All raised errors carry `provider_metadata` + semantic `user_action.kind` ✅
> - `instructor.core` import migrated ✅
> - SDK exception hierarchy audited (notes in test docstring / Running Notes)

---

## Phase 6 — OpenAI Responses LLM

Same shape as Phase 5 with one specialization: `NotFoundError` raises `LLMModelNotFoundError(message=msg, model_handle=...)` (not just `LLMCompletionError`) so callers can swap models. Keep that specialization inside the categorization helper so it fires on both wrapped and unwrapped paths. `extract_openai_metadata` from Phase 5 is reused (same SDK).

- [x] **RED** — wrote `tests/unit/pipelex/plugins/openai/test_openai_responses_worker_object_error_handling.py` mirroring Phase 5's case list and assertions. Extra case: wrapped `NotFoundError` raises `LLMModelNotFoundError` (not `LLMCompletionError`), `model_handle` is populated, and `provider_metadata.status_code == 404`. Plus real-instructor end-to-end using `instructor.Mode.RESPONSES_TOOLS` with `openai_client.responses.create` patched.
- [x] **GREEN** — refactored `_gen_object` in `pipelex/plugins/openai/openai_responses_llm_worker.py`. Added `_raise_categorized_openai_sdk_error` helper specialized for Responses (raises `LLMModelNotFoundError` for `NotFoundError`); both `_gen_text` and `_gen_object` now dispatch through it. Tuple-catch and `InstructorRetryException` unwrap path both use the same helper.
- [x] **GREEN** — `LLMModelNotFoundError` now carries `provider_metadata` end-to-end. Required updating `ModelNotFoundError.__init__` in `pipelex/cogt/exceptions.py` to accept and forward `error_category`, `user_action`, and `provider_metadata` kwargs to `CogtError.__init__`. `ModelWaterfallError` continues to work (it forwards only `message` and `model_handle`; new optional kwargs default to `None`).
- [x] Migrated `from instructor.exceptions import InstructorRetryException` → `from instructor.core import InstructorRetryException` in this worker.
- [x] **AUDIT** — OpenAI SDK hierarchy confirmed identical to Phase 5 (`openai/_exceptions.py`): all of `BadRequestError(400)`, `AuthenticationError(401)`, `PermissionDeniedError(403)`, `NotFoundError(404)`, `RateLimitError(429)`, `InternalServerError(5xx)`, `APIConnectionError`, `APITimeoutError` are caught (plus `OAuthError` which extends `AuthenticationError`). `ConflictError` (409) and `UnprocessableEntityError` (422) fall through to the `UNKNOWN` path (not raised on the Responses path in practice — same call as Phase 5).
- [x] Ran `.venv/bin/pytest tests/unit/pipelex/plugins/openai/` (70 passed), full `tests/unit/pipelex/cogt/` + `tests/unit/pipelex/plugins/` sweep (940 passed), `make agent-check` (0 errors, 0 warnings).

> ### **STOP — CHECKPOINT G: OpenAI Responses done**
>
> **Hand-off context:**
> - `LLMModelNotFoundError(model_handle=...)` plumbing fires on the wrapped path AND carries provider_metadata ✅
> - Both OpenAI workers at full parity ✅

---

## Phase 7 — Mistral LLM

Smallest of the four — `_classify_mistral_error` already does the work; the wrapped path just never reaches it. Add `extract_mistral_metadata`.

- [x] **RED** — wrote `tests/unit/pipelex/plugins/mistral/test_extract_mistral_metadata.py` (10 tests). Mistral's body is a raw JSON string (not a pre-parsed dict like OpenAI/Anthropic), so the helper JSON-parses it on a best-effort basis. `NoResponseError` is a separate `Exception` subclass with no response metadata — every status-related field comes back as `None`.
- [x] **RED** — wrote `tests/unit/pipelex/plugins/mistral/test_mistral_llm_worker_object_error_handling.py` (10 tests). Cases (each asserts category + `user_action.kind` + `provider_metadata`):
  - Wrapped `MistralError` (rate-limit generic 429) → `TRANSIENT` + `WAIT_AND_RETRY`
  - Wrapped `MistralError` (429 with quota keywords) → `CAPACITY` + `CHECK_BILLING`
  - Wrapped `MistralError` (HTTP 402) → `CAPACITY` + `CHECK_BILLING`
  - Wrapped `MistralError` (content-policy 400) → `CONTENT` + `CHANGE_INPUT`
  - Wrapped `MistralError` (generic 400) → `CONTENT` + `CHANGE_INPUT`
  - Wrapped `MistralError` (auth 401) → `CONFIGURATION` + `CHECK_CREDENTIALS`
  - Wrapped `MistralError` (not-found 404) → `CONFIGURATION` + `CHANGE_MODEL`
  - Wrapped `MistralError` (server error 500) → `TRANSIENT` + `WAIT_AND_RETRY`
  - Wrapped non-`MistralError` (e.g. `ValueError`) → `UNKNOWN` + `provider_metadata=None`
  - Real-instructor end-to-end: patches `Mistral.chat.complete_async` (which is what `instructor.from_mistral` ultimately calls)
  - **Note: skipped timeout/connection cases.** Mistral does not have separate `APITimeoutError`/`APIConnectionError` classes the way OpenAI/Anthropic do — its only network-layer exception is `NoResponseError` (a separate `Exception` subclass, not a `MistralError`). HTTP-level errors all surface as `MistralError` with `status_code` set.
- [x] **GREEN** — added `extract_mistral_metadata(exc: BaseException) -> ProviderErrorMetadata` in `pipelex/cogt/inference/error_classification.py`. Reads `status_code`, `headers` (httpx.Headers — for `x-request-id` and `retry-after`), and `body` (raw JSON string). JSON-parses the body on a best-effort basis; tolerates non-JSON bodies (e.g. HTML error pages from upstream) by leaving `provider_error_code=None` and storing the raw string. Added a small `_provider_error_code_from_flat_body` helper because Mistral's body is flat (`{"message": ..., "type": ..., "code": ...}`) while OpenAI/Anthropic wrap it as `{"error": {...}}` — falls back to the nested helper for endpoints that use that shape.
- [x] **GREEN** — refactored `_gen_object` in `pipelex/plugins/mistral/mistral_llm_worker.py`:
  ```python
  except InstructorRetryException as instructor_exc:
      underlying_exc = extract_underlying_sdk_exception(instructor_exc=instructor_exc)
      if isinstance(underlying_exc, MistralError):
          raise self._classify_mistral_error(underlying_exc) from instructor_exc
      msg = f"Mistral structured generation failed after retries for model '{self.inference_model.desc}': {instructor_exc}"
      raise LLMCompletionError(msg, error_category=InferenceErrorCategory.UNKNOWN) from instructor_exc
  except MistralError as exc:
      raise self._classify_mistral_error(exc) from exc
  ```
  Dropped the dead `except LLMCompletionError: raise` clause (no callee was raising a pre-categorized `LLMCompletionError` from inside the try). Dropped the misleading `error_category=CONTENT` fallback that previously fired for any unwrappable `InstructorRetryException` — it now routes to `UNKNOWN` per the Phase 2 convention.
- [x] **GREEN** — refined `_classify_mistral_error` to attach `provider_metadata=extract_mistral_metadata(exc)` on every raise and use semantic `UserActionKind` values: rate-limit→WAIT_AND_RETRY, quota (402 or 429+keywords)→CHECK_BILLING, 401/403→CHECK_CREDENTIALS, 404→CHANGE_MODEL, content-policy→CHANGE_INPUT, generic bad-request→CHANGE_INPUT, 5xx→WAIT_AND_RETRY, fallback→WAIT_AND_RETRY. Note: previously the fallback path lacked a `user_action` entirely; it now carries one too so downstream consumers see a uniform shape.
- [x] Migrated `from instructor.exceptions import InstructorRetryException` → `from instructor.core import InstructorRetryException` in `mistral_llm_worker.py`.
- [x] **AUDIT** — `mistralai` SDK exception hierarchy (rooted at `mistralai/models/`):
  - `MistralError(Exception)` — base for all HTTP errors. Carries `message`, `status_code` (int), `body` (str — raw response text), `headers` (httpx.Headers), `raw_response` (httpx.Response).
  - `SDKError(MistralError)` — fallback when no more specific error class matches.
  - `ResponseValidationError(MistralError)` — pydantic validation failure on response shape.
  - `HTTPValidationError(MistralError)` — server-side validation error (typically 422).
  - `NoResponseError(Exception)` — separate (not a MistralError); raised when no HTTP response is received at all (network/timeout). The current worker tuple-catch only catches `MistralError`, so `NoResponseError` would propagate as-is — acceptable today because the tenacity retry layer above absorbs it. If telemetry surfaces it later, add a dedicated branch.
- [x] Ran `.venv/bin/pytest tests/unit/pipelex/plugins/mistral/` (51 passed) and full plugins+cogt sweep (962 passed); `make agent-check` clean (0 errors, 0 warnings).

> ### **STOP — CHECKPOINT H: Mistral LLM done**
>
> **Hand-off context:**
> - `extract_mistral_metadata` lives in `pipelex/cogt/inference/error_classification.py` alongside the OpenAI/Anthropic helpers ✅
> - `_classify_mistral_error` now attaches `provider_metadata` + semantic `user_action.kind` on every branch ✅
> - `_gen_object` unwraps `InstructorRetryException` and dispatches through `_classify_mistral_error`; unrecognized underlying routes to `UNKNOWN` ✅
> - `instructor.core` import migrated ✅
> - `MistralError` body is a raw JSON string (unlike OpenAI/Anthropic which deliver a dict); the helper parses it on a best-effort basis. The flat top-level shape (`{"type": ..., "code": ...}`) is handled in addition to the nested `{"error": {...}}` shape via the new `_provider_error_code_from_flat_body` helper.

---

## Phase 8 — Google Gemini LLM

Symmetric to Mistral, plus `ServerError → TRANSIENT` direct mapping that doesn't need `_classify_google_client_error`. Add `extract_google_metadata`.

- [x] **RED** — wrote `tests/unit/pipelex/plugins/google/test_extract_google_metadata.py` (10 tests). Google's `APIError`/`ClientError`/`ServerError` carry `code: int` (HTTP status — *not* `status_code`), `message`, `status` (symbolic name like `RESOURCE_EXHAUSTED`), and `details` (the raw JSON response dict). Constructed via `genai_errors.ClientError(code, response_json, response)` with an `httpx.Response` for header-bearing cases.
- [x] **RED** — wrote `tests/unit/pipelex/plugins/google/test_google_llm_worker_object_error_handling.py` (10 tests). Cases (each asserts category + `user_action.kind` + `provider_metadata`):
  - Wrapped `genai_errors.ServerError` (500) → `TRANSIENT` + `WAIT_AND_RETRY`
  - Wrapped `genai_errors.ClientError` (429 generic) → `TRANSIENT` + `WAIT_AND_RETRY`
  - Wrapped `genai_errors.ClientError` (429 quota / `RESOURCE_EXHAUSTED`) → `CAPACITY` + `CHECK_BILLING`
  - Wrapped `genai_errors.ClientError` (400 content-policy) → `CONTENT` + `CHANGE_INPUT`
  - Wrapped `genai_errors.ClientError` (400 generic) → `CONTENT` + `CHANGE_INPUT`
  - Wrapped `genai_errors.ClientError` (401 auth) → `CONFIGURATION` + `CHECK_CREDENTIALS`
  - Wrapped `genai_errors.ClientError` (403 forbidden) → `CONFIGURATION` + `CHECK_CREDENTIALS`
  - Wrapped `genai_errors.ClientError` (404 not-found) → `CONFIGURATION` + `CHANGE_MODEL`
  - Wrapped non-SDK exception (`ValueError`) → `UNKNOWN` + `provider_metadata=None`
  - Real-instructor end-to-end: patches `client.aio.models.generate_content` (what `instructor.from_genai` ultimately calls in `use_async=True` mode); requires injecting a real `genai_types.Content` from `prepare_user_contents` because instructor's gemini message converter rejects a bare empty list as a message.
- [x] **GREEN** — added `extract_google_metadata(exc: BaseException) -> ProviderErrorMetadata` in `pipelex/cogt/inference/error_classification.py` alongside a small `_google_provider_error_code_from_details` helper (reads `error.status` then top-level `status` to recover symbolic names like `RESOURCE_EXHAUSTED`, `UNAUTHENTICATED`, `PERMISSION_DENIED`). `request_id` comes from `response.headers["x-goog-request-id"]` (falling back to `x-request-id`); status code from `exc.code` (Google does not use `exc.status_code`); body is `exc.details`.
- [x] **GREEN** — refactored `pipelex/plugins/google/google_llm_worker.py`. Added `_raise_categorized_google_sdk_error(sdk_exc, chain_from)` helper that dispatches `ServerError` directly to TRANSIENT (no need for the 4xx discriminator) and routes `ClientError` through `_classify_google_client_error`. Both `_gen_text` and `_gen_object` now go through the helper. `_gen_object` unwraps `InstructorRetryException` first; unrecognized underlying routes to `UNKNOWN` per Phase 2 convention (previously fell back to `CONTENT`).
- [x] **GREEN** — refined `_classify_google_client_error` to attach `provider_metadata=extract_google_metadata(exc)` on every raise and use semantic `UserActionKind` values: 404→CHANGE_MODEL, 401/403→CHECK_CREDENTIALS, 429+quota→CHECK_BILLING, 429+generic→WAIT_AND_RETRY, 400+content-policy→CHANGE_INPUT, 400+generic→CHANGE_INPUT, 4xx fallback→WAIT_AND_RETRY. Previously the 404, 401/403, generic-400, and 4xx-fallback paths lacked a `user_action` entirely; they now carry one so downstream consumers see a uniform shape. Existing `test_google_worker_error_handling.py` (the direct `_gen_text` path) keeps passing — the `expected_action_substring` check is `None` for the cases we newly populated, so adding a `user_action.detail` is a no-op for the assertion.
- [x] Migrated `from instructor.exceptions import InstructorRetryException` → `from instructor.core import InstructorRetryException` in `google_llm_worker.py`.
- [x] **AUDIT** — `google-genai` SDK exception hierarchy (`google/genai/errors.py`):
  - `APIError(Exception)` — base for all HTTP errors. Carries `code: int` (HTTP status), `response` (httpx/requests/replay response, may be `None`), `message`, `status` (symbolic), `details` (raw JSON dict).
  - `ClientError(APIError)` — 4xx errors.
  - `ServerError(APIError)` — 5xx errors.
  - `UnknownFunctionCallArgumentError(ValueError)`, `UnsupportedFunctionError(ValueError)`, `FunctionInvocationError(ValueError)`, `UnknownApiResponseError(ValueError)` — these are tool-calling / response-parsing failures, not HTTP errors. They subclass `ValueError`, not `APIError`, so they fall through to the wrapped-path `UNKNOWN` branch. Acceptable today; if telemetry shows them appearing in inference flows, add a dedicated branch.
  - Note: Google's SDK does *not* have separate timeout/connection classes the way OpenAI/Anthropic do. Network-level failures propagate as the underlying `httpx`/`requests` exceptions and would fall through tuple-catch, hitting the wrapped-path `UNKNOWN` branch or being absorbed by tenacity retry above.
- [x] Ran `.venv/bin/pytest tests/unit/pipelex/plugins/google/` (68 passed) and full plugins+cogt sweep (889 passed); `make agent-check` clean (0 errors, 0 warnings).

> ### **STOP — CHECKPOINT I: Google Gemini LLM done**
>
> **Hand-off context:** all four instructor-unwrap workers now classify wrapped errors correctly AND carry full structured metadata + semantic user_action. LLM-side defect closed; beyond-reference upgrades A–C delivered for the four targeted workers plus Anthropic.

---

## Phase 9 — LLM cross-cutting cleanup

- [x] Full LLM test sweep: `.venv/bin/pytest tests/unit/pipelex/plugins/{anthropic,openai,mistral,google}/` — 217 passed.
- [x] `rg "from instructor.exceptions" pipelex/` — zero results (`instructor.core` migration complete on all five LLM workers).
- [x] **Uniformity check** — `rg "raise LLMCompletionError" pipelex/plugins/{anthropic,openai,mistral,google}/` — every match now carries `provider_metadata=` and `user_action=UserAction(...)`. The orphan response-shape validation paths (empty choices, no candidates, None content, exhausted-thinking-tokens, instructor-misconfigured-for-Responses) that previously raised bare `LLMCompletionError(msg)` were migrated to explicit `error_category` + `provider_metadata=None` (non-SDK paths) + semantic `UserAction`. Audit one-liner `rg "raise LLMCompletionError" pipelex/plugins/{anthropic,openai,mistral,google}/ -A 6 | rg -v "provider_metadata" | rg "raise (LLM|Img|Extract|Search)"` returns empty.
- [x] **AWS Bedrock decision check** — Phase 0 confirmed Bedrock LLM worker does not use `instructor` (the `_gen_object` path raises `LLMCapabilityError`). No Phase 8.5 was created. Bedrock still benefits from upgrades A–C in Phase 11.
- [x] Updated [wip/error-handling/track-worker-classification.md](wip/error-handling/track-worker-classification.md): the "Instructor unwrap missing on four other workers" gap is gone, the per-provider unwrap-and-dispatch followups are collapsed into a "landed" note, and a sentence about beyond-reference upgrades A/B/C now sits in the opening paragraph.
- [x] Updated [wip/error-handling/README.md](wip/error-handling/README.md): "Worker classification" row marks the LLM-side track as landed and points the remaining non-LLM-worker migration at `_tprl/TODOS.md` Phases 10–12. "Error metadata model" row reflects that `ProviderErrorMetadata` + `UserAction` are now uniform across LLM workers.
- [x] `make agent-check && make agent-test` — clean.

> ### **STOP — CHECKPOINT J: LLM-side track closed**
>
> **Hand-off context:** worker-classification track has no remaining LLM-side gaps. Track docs reflect reality. Beyond-reference upgrades A–C live across all LLM workers that this sweep touched (Anthropic + 4). Other LLM workers still need upgrade migration via Phase 11. Ready to audit non-LLM worker kinds.

---

## Phase 10 — Img-gen worker audits

> Note: each worker within this phase is an independent unit of work. The agent may save/checkpoint between workers if context grows — record per-worker hand-off in the Running Notes section.

The img-gen workers already have basic classification landed. This phase brings each up to the beyond-reference standard: extract metadata, structured user_action, UNKNOWN fallback where applicable, and confirms SDK exception coverage.

For each worker: (a) read source — confirm every documented SDK exception type is caught and routed through the right discriminator; (b) write `extract_<provider>_metadata` helper if not already done (some providers may already have it from LLM workers — e.g. OpenAI img-gen reuses `extract_openai_metadata`); (c) update each raise to pass `provider_metadata=...` and semantic `user_action=UserAction(...)`; (d) replace `CONTENT` fallback with `UNKNOWN` where the underlying is genuinely unknown; (e) update tests to assert metadata + user_action.kind.

- [x] **OpenAI img-gen** — `pipelex/plugins/openai/openai_img_gen_worker.py` (reuse `extract_openai_metadata`). Introduced `_raise_categorized_openai_sdk_error` helper, collapsed the per-exception except blocks into a single tuple-catch that delegates through it. Added `InternalServerError` and `PermissionDeniedError` to the catch (previously not caught). Every raise carries `provider_metadata=extract_openai_metadata(sdk_exc)` and a semantic `UserActionKind`. `NotFoundError` continues to raise `ImgGenModelNotFoundError(model_handle=...)`.
- [x] **OpenAI Completions img-gen** — `pipelex/plugins/openai/openai_completions_img_gen_worker.py` (reuse `extract_openai_metadata`). Same helper-method pattern as the standalone OpenAI img-gen worker.
- [x] **Google img-gen** — `pipelex/plugins/google/google_img_gen_worker.py`. `_classify_google_client_error` now attaches `provider_metadata=extract_google_metadata(exc)` on every branch and uses semantic `UserActionKind` values: 404→CHANGE_MODEL, 401/403→CHECK_CREDENTIALS, 429+quota→CHECK_BILLING, 429+generic→WAIT_AND_RETRY, 400+content-policy→CHANGE_INPUT, 400+generic→CHANGE_INPUT, 4xx fallback→WAIT_AND_RETRY. `ServerError` (500) now also carries `provider_metadata` + semantic `WAIT_AND_RETRY`. Per Phase 11/12 follow-up, kept `ImgGenGenerationError` (not `ImgGenModelNotFoundError`) for 404 to match the existing test contract; mirror with the LLM worker.
- [x] **Azure img-gen** — `pipelex/plugins/azure_rest/azure_img_gen_worker.py` (path was `azure_rest`, not `azure`). Added `extract_azure_metadata` to `error_classification.py` (reads status, `x-ms-request-id` / `apim-request-id` / `x-request-id` headers, retry-after; JSON-parses the response body on a best-effort basis to surface `provider_error_code` from both flat and nested error shapes; tolerates HTML error pages from upstream). Introduced `_raise_categorized_azure_status_error` helper; every raise carries `provider_metadata` + semantic `UserActionKind`. Added a 404 branch (deployment not found → CHANGE_MODEL) that wasn't present in the original worker; the previous fallback-to-CONFIGURATION path now uses `CONTACT_SUPPORT` since it's reached only for unexpected status codes.
- [x] **FAL img-gen** — `pipelex/plugins/fal/fal_img_gen_worker.py`. Added `extract_fal_metadata` to `error_classification.py` (reads `status_code`, `response_headers` dict for `x-request-id` / `x-fal-request-id` and `retry-after`, `error_type` as `provider_error_code`, JSON-parses the response text body when available). `_raise_categorized_fal_http_error` helper handles `FalClientHTTPError` with semantic `UserActionKind`; `MissingCredentialsError` → CHECK_CREDENTIALS; `FalClientTimeoutError`/`FalClientError` → WAIT_AND_RETRY. Added a 404 branch (model not found → CHANGE_MODEL).
- [x] **HuggingFace img-gen** — `pipelex/plugins/huggingface/huggingface_img_gen_worker.py`. Added `extract_huggingface_metadata` to `error_classification.py` (uses `exc.request_id` which `HfHubHTTPError.__init__` mirrors from `X-Request-Id` / `X-Amzn-Trace-Id` / `X-Amz-Cf-Id`; reads body from `response.text` since HF wraps `requests.Response`, not `httpx.Response`). `_raise_categorized_hf_http_error` helper with semantic `UserActionKind`; `InferenceTimeoutError` → WAIT_AND_RETRY. Added 404→CHANGE_MODEL and 402→CHECK_BILLING branches.
- [x] **Gateway img-gen** — `pipelex/plugins/gateway/gateway_img_gen_worker.py`. Added `extract_gateway_metadata` to `error_classification.py` (Portkey SDK exception shape mirrors OpenAI — `APIStatusError` exposes `status_code`, `response.headers`, `body` as a pre-parsed dict). Added `GatewayFactory.make_user_action_from_portkey_error` and `GatewayFactory.make_provider_metadata_from_portkey_error` classmethods that complement the existing `classify_error_category`/`make_error_summary_from_portkey_error` helpers. Img-gen worker now uses all four. Extract/search workers can adopt the new helpers in Phase 11/12.
- [x] `make agent-check && .venv/bin/pytest tests/unit/pipelex/plugins/ tests/unit/pipelex/cogt/` — 1069 passed, 0 errors, 0 warnings.

> ### **STOP — CHECKPOINT K: Img-gen audit complete**
>
> **Hand-off context:**
> - `extract_azure_metadata`, `extract_fal_metadata`, `extract_huggingface_metadata`, `extract_gateway_metadata` all live in `pipelex/cogt/inference/error_classification.py` alongside the LLM-side helpers ✅
> - Every img-gen worker raises `ImgGenGenerationError` / `ImgGenModelNotFoundError` with `provider_metadata` + semantic `UserActionKind` ✅
> - All new tests parallel the Anthropic reference suite (metadata test + worker-level semantic test asserting category + user_action.kind + provider_metadata fields) ✅
> - Gateway helpers (`make_user_action_from_portkey_error`, `make_provider_metadata_from_portkey_error`) are ready for adoption by `gateway_extract_worker.py` and `gateway_search_worker.py` in Phases 11/12

---

## Phase 11 — Extract worker audits + AWS Bedrock LLM (if not handled in 8.5)

Same approach as Phase 10. Bedrock LLM lands here too if Phase 0 found it doesn't use instructor (no unwrap defect, but it still benefits from upgrades A–C).

- [x] **AWS Bedrock LLM** — `pipelex/plugins/bedrock/bedrock_llm_worker.py`. Added `extract_bedrock_metadata` to `error_classification.py` (reads `Error.Code`, `ResponseMetadata.HTTPStatusCode` / `RequestId` / `HTTPHeaders.retry-after`; keeps the full `response` dict as `body`). Introduced `_classify_bedrock_client_error` helper; every raise carries `provider_metadata` + semantic `UserActionKind` (CHECK_BILLING for quota, CHECK_CREDENTIALS for AccessDenied, CHANGE_INPUT for ValidationException, CHANGE_MODEL for ResourceNotFoundException, WAIT_AND_RETRY for throttling / unavailable / unknown). Added a `ResourceNotFoundException` branch (previously absent — fell through to the TRANSIENT fallback).
- [x] **Mistral extract** — `pipelex/plugins/mistral/mistral_extract_worker.py`. Refactored `_classify_mistral_error` to mirror the LLM worker's shape (attached `provider_metadata` + semantic `UserActionKind` on every branch). Previously the 401/403, 404, generic-400, and fallback paths lacked a `user_action` entirely — now they all carry one for uniformity.
- [x] **Docling extract** — `pipelex/plugins/docling/docling_extract_worker.py`. Added `extract_local_extract_metadata` (shared helper in `error_classification.py`) for local extractors — every status field comes back as `None`, only `sdk_exception_type` / `provider_error_code` are meaningful. All four exception branches (`FileNotFoundError`, `ValueError`, `RuntimeError`, `OSError`) now carry `provider_metadata` + semantic `UserActionKind`.
- [x] **Linkup extract** — `pipelex/plugins/linkup/linkup_extract_worker.py`. Added `extract_linkup_metadata` (Linkup SDK does not expose response metadata — only `sdk_exception_type` / `provider_error_code` are meaningful; the SDK class name is the canonical signal). Refactored to a `_classify_linkup_error` method (mirrors the search worker's shape — search adoption deferred to Phase 12). Single tuple-catch in `_extract_pages` dispatches through the helper.
- [x] **Gateway extract** — `pipelex/plugins/gateway/gateway_extract_worker.py`. Adopted `extract_gateway_metadata` + `GatewayFactory.make_user_action_from_portkey_error` (both landed in Phase 10). Both `_extract_web_fetch` and `_extract_base64_url` raise `ExtractJobFailureError` with `provider_metadata` + `user_action`. Tenacity retry wraps the call and reraises — categorization signal survives the retry boundary intact.
- [x] **pypdfium2** — `pipelex/plugins/pypdfium2/pypdfium2_worker.py`. Reused the shared `extract_local_extract_metadata` helper added for Docling. Every exception branch carries `provider_metadata` + semantic `UserActionKind`.
- [x] `make agent-check && .venv/bin/pytest tests/unit/pipelex/plugins/ tests/unit/pipelex/cogt/` — 0 errors, 0 warnings; 1122 passed.

> ### **STOP — CHECKPOINT L: Extract audit complete**
>
> **Hand-off context:**
> - `extract_bedrock_metadata`, `extract_linkup_metadata`, `extract_local_extract_metadata` all live in `pipelex/cogt/inference/error_classification.py` alongside the existing per-provider helpers ✅
> - Bedrock LLM, Mistral extract, Docling extract, Linkup extract, Gateway extract, pypdfium2 — every raise carries `provider_metadata` + semantic `UserActionKind` ✅
> - Linkup search worker (Phase 12) still has its own `_classify_linkup_error` with UNKNOWN placeholders; it can adopt `extract_linkup_metadata` in Phase 12 with a single helper swap.
> - Gateway search worker (Phase 12) similarly can adopt `extract_gateway_metadata` + `make_user_action_from_portkey_error` mirroring the extract worker's adoption.

---

## Phase 12 — Search worker audits

- [x] **Linkup search** — `pipelex/plugins/linkup/linkup_search_worker.py`. Refactored `_classify_linkup_error` to mirror the extract worker's shape: attaches `provider_metadata=extract_linkup_metadata(exc)` on every branch and uses semantic `UserActionKind` values (CHECK_CREDENTIALS for auth, CHECK_BILLING for insufficient-credit, WAIT_AND_RETRY for rate-limit/timeout/fallback, CHANGE_INPUT for invalid-request). Previously the timeout, invalid-request, no-result/unknown, and fallback branches lacked a `user_action` entirely — now every branch carries one. `LinkupNoResultError`/`LinkupUnknownError` route through the fallback (TRANSIENT + WAIT_AND_RETRY), same as before.
- [x] **Gateway search** — `pipelex/plugins/gateway/gateway_search_worker.py`. `_call_relay`'s `except portkey_exceptions.APIError` block now also calls `GatewayFactory.make_user_action_from_portkey_error(exc)` and `extract_gateway_metadata(exc)` (both landed in Phase 10), and passes `user_action=` + `provider_metadata=` to `GatewaySearchResponseError`. The tenacity retry boundary is preserved: `AsyncRetrying(reraise=True)` reraises the last `APIError` verbatim into the except block, so categorization signal and request_id survive across the retry boundary — same pattern confirmed for the extract worker in Phase 11.
- [x] `make agent-check && make agent-test` — clean.

> ### **STOP — CHECKPOINT M: Search audit complete**
>
> **Hand-off context:**
> - Both search workers (Linkup, Gateway) now raise `SearchJobFailureError` / `GatewaySearchResponseError` with `provider_metadata` + semantic `UserActionKind` on every branch ✅
> - Linkup search reuses `extract_linkup_metadata`; Gateway search reuses `extract_gateway_metadata` + `GatewayFactory.make_user_action_from_portkey_error` — no new helpers needed in this phase ✅
> - New tests: `test_linkup_search_worker_semantic.py` (7 cases), `test_gateway_search_worker_semantic.py` (5 cases). Existing `test_linkup_worker_error_handling.py` still passes — the `_classify_linkup_error` refactor preserved every error message substring and category it asserts.
> - All worker kinds (LLM, img-gen, extract, search) are now at the beyond-reference standard. Phase 13 is the final cross-cutting integration check.

---

## Phase 13 — Final integration check

- [x] Full suite: `make agent-test` — clean.
- [x] Confirmed no `except Exception:` regressions: `rg "except Exception" pipelex/plugins/` returns matches only in `teardown()` cleanup methods (`google_llm_worker`, `google_img_gen_worker`, `gateway_extract_worker`) plus the non-worker `bedrock_list.py` / `mistral_factory.py`. Every match is pre-existing best-effort async-client cleanup with a documented reason in source ("Log but don't fail teardown if cleanup has issues"). None sit on an error-classification path; no regressions introduced by this sweep.
- [x] Confirmed `from exc` chaining: every SDK-error raise chains via `from exc`; the migrated response-shape raises that sit inside `except` blocks (`gateway_search_worker._extract_content`, `fal_factory.make_generated_image_list`) keep `from exc`; the remaining response-shape raises are post-success validation checks (not in an `except` block) so they correctly carry no `from exc`.
- [x] **Uniformity check** — every raised `LLMCompletionError` / `ImgGenGenerationError` / `ExtractJobFailureError` / `SearchJobFailureError` / `GatewaySearchResponseError` now carries `provider_metadata=` and `user_action=UserAction(...)`. The audit surfaced a real gap: Phases 10–12 migrated the SDK-error raises but left the **response-shape validation** bare raises (`raise XError(msg)`) untouched in the img-gen / extract / gateway-search workers — unlike the LLM workers, which Phase 9 cleaned up. Migrated all of them (openai/google/azure/gateway/openai-completions img-gen, fal_factory, gateway extract, gateway search) to mirror the Phase 9 LLM treatment. See running notes.
- [x] Confirmed `rg "kind=UserActionKind.UNKNOWN" pipelex/plugins/` returns zero matches — no placeholder `UNKNOWN` user-action kinds remain anywhere in the plugins.
- [x] Updated [wip/error-handling/README.md](wip/error-handling/README.md) status table — "Error metadata model" and "Worker classification" rows now read as landed for **all** inference workers (LLM + img-gen + extract + search), with the residual "still need migration" clauses dropped.
- [x] Confirmed [wip/error-handling/track-testing.md](wip/error-handling/track-testing.md) "worker-level classification tests are comprehensive" claim still matches reality — Phases 10–12 added `test_*_semantic.py` suites for img-gen / extract / search workers; the higher-level gaps (full-chain snapshot, dict-drift detection) the doc lists are still open. No update needed.
- [x] **Extract/Classify/Render track is ready to start:** all four prerequisites in [track-extract-classify-render.md](wip/error-handling/track-extract-classify-render.md) are satisfied — `InferenceErrorCategory.UNKNOWN` (Phase 2), `ProviderErrorMetadata` Pydantic model (Phase 3), structured `UserAction` (Phase 4), instructor-unwrap landed on the four workers (Phases 5–8). The doc's "Current state (assumed post-TODOS.md sweep)" section now matches actual reality; no update needed.

> ### **DONE**

---

## Running notes

Use this section to capture decisions, surprises, and cold-start handoff context as phases land. Add timestamped entries; never delete.

- **2026-05-14 — Phase 0 landed.** Shared helpers at `tests/helpers/instructor_test_utils.py` expose `wrap_in_instructor_retry`, `DummySchema`, and `make_llm_job`. Names are public (no underscore) because pyright flags cross-module use of underscore-prefixed identifiers with `reportPrivateUsage`. Anthropic worker tests refactored to import the shared helpers; all 24 tests pass.
- **2026-05-14 — Bedrock decision.** `pipelex/plugins/bedrock/bedrock_llm_worker.py::_gen_object` raises `LLMCapabilityError` and does not use instructor (the file's only `instructor` mention is a `# TODO` comment). No `Phase 8.5` will be created. Bedrock still gets upgrades A–C in Phase 11.
- **2026-05-14 — Phase 1 landed.** `extract_underlying_sdk_exception` lives in `pipelex/cogt/inference/error_classification.py`. Anthropic worker imports from the shared module. The defensive try/except around `failed_attempts[-1]` swallows `TypeError`/`KeyError`/`IndexError` to keep the helper safe against malformed input (the tests cover a string-as-failed_attempts case). Defending only against typing/lookup exceptions (not generic Exception) keeps real bugs visible.
- **2026-05-14 — Phase 2 landed.** `InferenceErrorCategory.UNKNOWN` lives in `pipelex/cogt/exceptions.py` (NOT `error_classification.py` — TODOS.md text was off). Value is lowercase `"unknown"` to match other members. `is_retryable=False`. Anthropic worker's `InstructorRetryException` fallback uses UNKNOWN. Other workers still use whatever they had — they get migrated in their own phases.
- **2026-05-14 — Phase 4 landed.** `UserActionKind` (StrEnum) and `UserAction` (BaseModel) live in `pipelex/cogt/inference/error_classification.py`. Decisions:
  - **Field type changed on the base `CogtError`** (not per-leaf), keeping subclasses uniform — same approach as `provider_metadata` in Phase 3.
  - **JSON shape change.** `report_dict["user_action"]` is now a nested `{"kind": "...", "detail": "..."}` object instead of a free string. `Pydantic v2` `TypeAdapter.dump_python(... mode="python")` recursively serializes nested `BaseModel` fields inside the `ErrorReport` Pydantic dataclass, so no extra plumbing was needed in `to_error_report()`.
  - **CLI consumers updated.** `pipelex/cli/error_handlers.py` and `pipelex/cli/agent_cli/commands/agent_output.py` read `report.user_action.detail` (with `None`-guard) instead of treating the field as a string. Tests in `tests/unit/pipelex/cogt/test_exceptions.py` and `tests/unit/pipelex/cli/test_agent_output.py` were migrated to construct `UserAction(...)` explicitly. Worker tests that previously did `exc_info.value.user_action.lower()` now do `exc_info.value.user_action.detail.lower()`.
  - **Anthropic worker semantic kinds.** The Anthropic reference worker (and `AnthropicCredentialsError`'s class-level default, plus `InferenceBackendCredentialsError`'s class-level default) use semantic `UserActionKind` values. Every other worker (OpenAI Completions/Responses, OpenAI img-gen, OpenAI completions img-gen, Google LLM/img-gen, Mistral LLM/extract, Bedrock LLM, Linkup extract/search, Azure img-gen, FAL img-gen, HuggingFace img-gen) carries `kind=UNKNOWN` as a placeholder for now. Per-worker phases will refine those.
- **2026-05-14 — Phase 5 landed.** OpenAI Completions LLM brought up to the beyond-reference standard.
  - **`extract_openai_metadata` shape.** OpenAI's `_make_status_error` (in `_client.py`) pre-unwraps `body["error"]` so `body["type"]` / `body["code"]` sit at the top level — and the SDK already mirrors those onto `exc.type` / `exc.code`. So `extract_openai_metadata` reads `provider_error_code` from `getattr(exc, "type", None) or getattr(exc, "code", None)` rather than re-parsing the body. `request_id` comes from `exc.request_id` which `APIStatusError.__init__` sets from `response.headers["x-request-id"]`. Factored that out into a shared `_request_id_from_exc_or_response` helper that works for both Anthropic (which exposes `exc.request_id` directly) and OpenAI.
  - **Helper method pattern.** Mirrored the Anthropic worker: introduced `_raise_categorized_openai_sdk_error(sdk_exc, chain_from=None)` so both `_gen_text` and `_gen_object` dispatch through the same place. Removed the nested try in `_gen_object` — there is now a single try with two except clauses (`InstructorRetryException` then the SDK tuple).
  - **SDK coverage expanded.** Added `InternalServerError` (5xx → TRANSIENT + WAIT_AND_RETRY) and `PermissionDeniedError` (403 → CONFIGURATION + CHECK_CREDENTIALS) to the tuple-catch, neither of which was previously caught. `ConflictError` (409) and `UnprocessableEntityError` (422) are not raised on the chat-completion path in practice; if telemetry surfaces them later they fall through to the wrapped-path `UNKNOWN` branch and can be added.
  - **Semantic UserActionKind values:** rate-limit→WAIT_AND_RETRY, quota→CHECK_BILLING, timeout/connection/server→WAIT_AND_RETRY, not-found→CHANGE_MODEL, bad-request (content-policy or generic)→CHANGE_INPUT, auth/permission-denied→CHECK_CREDENTIALS.
  - **`instructor.exceptions` → `instructor.core`** import migration done in this worker.
  - **Tests.** New: `test_extract_openai_metadata.py` (10 tests) and `test_openai_completions_worker_object_error_handling.py` (10 tests including a real-instructor end-to-end). Existing `test_openai_worker_error_handling.py` still passes — the `_gen_text` refactor preserved the user-visible behavior for the cases it covered.
- **2026-05-14 — Phase 6 landed.** OpenAI Responses LLM brought up to the beyond-reference standard.
  - **Worker-local helper, not shared with Completions.** The categorization helper is a method on `OpenAIResponsesLLMWorker` (not a shared free function with Completions) because Responses specializes `NotFoundError` into `LLMModelNotFoundError` (so callers can swap models), while Completions raises `LLMCompletionError`. The branch shape and SDK coverage are otherwise identical to Phase 5. Mirroring the helper instead of sharing avoids leaking worker-specific concerns (`inference_model.name` for `model_handle`) into a shared helper signature.
  - **`ModelNotFoundError.__init__` extended.** To carry `provider_metadata` and a semantic `user_action` on `LLMModelNotFoundError`, the parent `ModelNotFoundError.__init__` in `pipelex/cogt/exceptions.py` now accepts and forwards `error_category`, `user_action`, and `provider_metadata` kwargs to `CogtError.__init__`. `ModelWaterfallError` continues to construct correctly: it forwards only `message` and `model_handle`, and the new kwargs default to `None` so the class-level `error_category = InferenceErrorCategory.CONFIGURATION` default kicks in.
  - **Real-instructor end-to-end test uses `instructor.Mode.RESPONSES_TOOLS`.** instructor's Responses path (`AsyncResponse.create_with_completion`) is only attached on the `AsyncInstructor` when mode is `RESPONSES_TOOLS` or `RESPONSES_TOOLS_WITH_INBUILT_TOOLS`. The underlying call goes through `async_map_chat_completion_to_response → client.responses.create`, so the test patches `openai_client.responses.create` (not `.chat.completions.create` like Phase 5's test).
  - **SDK exception coverage now uniform with Phase 5.** Added `InternalServerError` (5xx → TRANSIENT + WAIT_AND_RETRY) and `PermissionDeniedError` (403 → CONFIGURATION + CHECK_CREDENTIALS) to the tuple-catch — both were previously missing. `ConflictError` / `UnprocessableEntityError` are not raised on the responses path in practice and fall through to the wrapped-path `UNKNOWN` branch.
  - **Semantic UserActionKind values:** rate-limit→WAIT_AND_RETRY, quota→CHECK_BILLING, timeout/connection/server→WAIT_AND_RETRY, not-found→CHANGE_MODEL (on `LLMModelNotFoundError`), bad-request (content-policy or generic)→CHANGE_INPUT, auth/permission-denied→CHECK_CREDENTIALS.
  - **Tests.** New: `test_openai_responses_worker_object_error_handling.py` (10 tests including a real-instructor end-to-end). Existing `test_openai_worker_error_handling.py` (which tests the `_gen_text` Responses path through `responses.create`) still passes — the `_gen_text` refactor preserved the user-visible behavior for the categories it covered.
- **2026-05-14 — Phase 7 landed.** Mistral LLM brought up to the beyond-reference standard.
  - **`extract_mistral_metadata` body parsing.** Unlike OpenAI/Anthropic — whose SDKs deliver `body` as a pre-parsed dict — Mistral's SDK sets `MistralError.body` to the raw response *text string* (from `httpx.Response.text`). The helper JSON-parses it on a best-effort basis and stores the parsed dict back on `ProviderErrorMetadata.body` so downstream consumers see a uniform shape. Non-JSON bodies (HTML error pages from upstream gateways during 502/504s) are tolerated: `provider_error_code` stays `None` and `body` keeps the raw string.
  - **Two body shapes.** Mistral returns the flat shape `{"message": ..., "type": ..., "code": ...}` on most endpoints, but some endpoints wrap it as `{"error": {...}}`. Added a small `_provider_error_code_from_flat_body` helper and fall back to the existing nested-shape helper to cover both. The OR-chain (`flat or nested`) means whichever shape Mistral uses, we extract the code.
  - **No separate timeout/connection classes.** Mistral has only `MistralError` (HTTP errors with a `status_code`) and `NoResponseError` (a sibling `Exception` for true no-response failures — network-level). The current worker tuple-catch on `MistralError` does not catch `NoResponseError`, so it propagates up to the tenacity retry layer. Acceptable today; documented in the audit notes inside Phase 7. If telemetry surfaces it later, add a dedicated branch in `_gen_text`/`_gen_object` similar to OpenAI's `APIConnectionError`/`APITimeoutError`.
  - **Dead `except LLMCompletionError` clause removed.** The prior `_gen_object` had an `except LLMCompletionError: raise` clause between the SDK catch and the `InstructorRetryException` catch. Nothing on the call path raised `LLMCompletionError` from inside the try, so the clause was dead. Removing it lets pyright/mypy see the unwrap path more cleanly.
  - **Fallback path now routes to UNKNOWN.** Previously the unwrapped-instructor fallback used `error_category=CONTENT`, which silently mis-categorized non-Mistral underlying exceptions. Per Phase 2 convention, it now routes to `UNKNOWN` with `provider_metadata=None`.
  - **Semantic UserActionKind values:** rate-limit→WAIT_AND_RETRY, quota (402 or 429+keywords)→CHECK_BILLING, 401/403→CHECK_CREDENTIALS, 404→CHANGE_MODEL, content-policy→CHANGE_INPUT, generic bad-request→CHANGE_INPUT, 5xx→WAIT_AND_RETRY, fallback→WAIT_AND_RETRY. Previously the 401/403/404 paths and the fallback path lacked a `user_action` entirely; they now carry one so downstream consumers see a uniform shape.
  - **Tests.** New: `test_extract_mistral_metadata.py` (10 tests) and `test_mistral_llm_worker_object_error_handling.py` (10 tests including a real-instructor end-to-end). Existing `test_mistral_worker_error_handling.py` (the direct `_gen_text` path) still passes — the `_classify_mistral_error` refactor preserved the categorization output for every case it covered.
- **2026-05-14 — Phase 8 landed.** Google Gemini LLM brought up to the beyond-reference standard.
  - **`extract_google_metadata` field shape.** Google's SDK differs from OpenAI/Anthropic on three points: (1) HTTP status lives on `exc.code` (not `exc.status_code`); (2) the response body lives on `exc.details` (the raw JSON dict the API returned, *not* `exc.body`); (3) the symbolic error code is a textual `status` field like `RESOURCE_EXHAUSTED`, `UNAUTHENTICATED`, `PERMISSION_DENIED` — read from `details["error"]["status"]` with a top-level `details["status"]` fallback for endpoints that flatten the payload. Added `_google_provider_error_code_from_details` helper to handle both shapes. `request_id` reads `x-goog-request-id` first (Google-specific) and falls back to `x-request-id` for older endpoints. `response` may be `None` (the SDK constructor accepts it), so the helper degrades gracefully — every header-derived field becomes `None`.
  - **Helper method + ServerError specialization.** Introduced `_raise_categorized_google_sdk_error(sdk_exc, chain_from)` so both `_gen_text` and `_gen_object` dispatch through one place. `ServerError` is handled directly in the helper (TRANSIENT + WAIT_AND_RETRY) without going through the 4xx-discriminator in `_classify_google_client_error` — same shape as Phase 8's plan called for.
  - **Fallback path now routes to UNKNOWN.** Previously `_gen_object`'s `InstructorRetryException` clause raised `LLMCompletionError` with `error_category=CONTENT`, which silently mis-categorized any non-Google underlying exception. Per Phase 2 convention, it now routes to `UNKNOWN` with `provider_metadata=None`.
  - **Real-instructor test required a real `Content` object.** instructor's gemini message converter (`instructor/providers/gemini/utils.py:565`) rejects a bare `list` as a message: it expects each message to be a dict or a `genai_types.Content`. The Google worker wraps `prepare_user_contents`'s return value as `messages=[contents]`, so when the mock returned `[]` we ended up with `messages=[[]]` which crashes the converter. The real-instructor test now injects a `genai_types.Content(role="user", parts=[Part.from_text(text="hi")])` so instructor reaches the SDK call (which we patched to raise `ClientError`). The other 9 tests in the suite use a synthetic `wrap_in_instructor_retry(sdk_exc)` that side-effects the instructor client mock directly, so they never go through the converter.
  - **Semantic UserActionKind values:** 404→CHANGE_MODEL, 401/403→CHECK_CREDENTIALS, 429+quota→CHECK_BILLING, 429+generic→WAIT_AND_RETRY, 400+content-policy→CHANGE_INPUT, 400+generic→CHANGE_INPUT, 4xx fallback→WAIT_AND_RETRY, 5xx (ServerError)→WAIT_AND_RETRY. Previously the 404/401/403/generic-400/fallback paths lacked a `user_action`; they now carry one so downstream consumers see a uniform shape.
  - **Img-gen worker untouched.** `pipelex/plugins/google/google_img_gen_worker.py` has its own `_classify_google_client_error` copy with the same shape. It is in scope for Phase 10 (img-gen audits), not Phase 8 — left as-is for now.
  - **SDK hierarchy audited.** `genai_errors.{APIError, ClientError, ServerError}` are the HTTP error classes; `UnknownFunctionCallArgumentError`, `UnsupportedFunctionError`, `FunctionInvocationError`, `UnknownApiResponseError` are tool-calling / parsing failures that subclass `ValueError`, *not* `APIError`. They fall through tuple-catch and route to wrapped-path `UNKNOWN`. Google's SDK doesn't have separate timeout/connection classes the way OpenAI/Anthropic do — network failures propagate as the underlying `httpx`/`requests` exceptions.
  - **Tests.** New: `test_extract_google_metadata.py` (10 tests) and `test_google_llm_worker_object_error_handling.py` (10 tests, including a real-instructor end-to-end). Existing `test_google_worker_error_handling.py` (direct `_gen_text` path through `ClientError`/`ServerError`) still passes — the `_classify_google_client_error` refactor preserved every case it covered, and the newly-populated `user_action.detail` fields are no-ops where the test asserted `expected_action_substring is None`.
- **2026-05-14 — Phase 10 landed.** Img-gen worker audits complete. Beyond-reference upgrades A–C delivered across all seven img-gen workers (OpenAI, OpenAI Completions, Google, Azure, FAL, HuggingFace, Gateway). Decisions:
  - **Path correction.** TODOS.md text said `pipelex/plugins/azure/azure_img_gen_worker.py` but the actual path is `pipelex/plugins/azure_rest/azure_img_gen_worker.py`. No `azure` plugin directory exists; updated test paths to `tests/unit/pipelex/plugins/azure_rest/`.
  - **New `extract_*_metadata` helpers.** Four new helpers added: `extract_azure_metadata`, `extract_fal_metadata`, `extract_huggingface_metadata`, `extract_gateway_metadata`. Each handles the SDK's specific exception shape (Azure: raw httpx exceptions on a REST API; FAL: `FalClientHTTPError` with `response_headers` dict and `error_type` attribute; HuggingFace: `HfHubHTTPError` wraps `requests.Response` not `httpx.Response` and mirrors `request_id` onto the exception; Gateway: Portkey SDK mirrors OpenAI shape so the helper is straightforward).
  - **Specialization decision: 404 → `ImgGenModelNotFoundError` only on OpenAI workers.** The original Google/Azure/FAL/HF img-gen workers raised `ImgGenGenerationError(error_category=CONFIGURATION)` for 404, not `ImgGenModelNotFoundError`. To preserve existing test contracts and behavior parity with the LLM-side Google worker (which also uses `LLMCompletionError` not `LLMModelNotFoundError` for 404), kept that behavior for Google/Azure/FAL/HF. Only the OpenAI workers (which originally raised `ImgGenModelNotFoundError`) preserve that specialization. All workers now carry `UserActionKind.CHANGE_MODEL` on the 404 path regardless of which exception class fires.
  - **Gateway helper-class pattern.** Added two new `GatewayFactory` classmethods (`make_user_action_from_portkey_error`, `make_provider_metadata_from_portkey_error`) rather than inlining a helper inside the worker, so that `gateway_extract_worker.py` and `gateway_search_worker.py` can adopt the same path in Phase 11/12 without duplicating the dispatch logic.
  - **No UNKNOWN-category fallback added to img-gen workers.** Unlike the LLM workers (which have an `InstructorRetryException` wrapped path that can carry a non-recognized underlying), img-gen workers all use a direct tuple-catch on the SDK exception types. Anything that falls outside the tuple-catch propagates as-is (acceptable behavior — the tenacity retry layer above absorbs them). No new UNKNOWN code paths needed in this phase.
  - **Pyright `dict[Unknown, Unknown] | Any | None` corner.** `extract_gateway_metadata` narrows `body` inside an `isinstance(body, dict)` block, then passes `body` back to `ProviderErrorMetadata(body=...)`. Pyright widens to `dict[Unknown, Unknown] | Any | None` at the call site (the narrowing partially "leaks"). Worked around by aliasing the narrowed variable and `cast("Any", raw_body)` at the call site. This is a known pyright pattern; the other `extract_*` helpers don't trigger it because they don't narrow body via isinstance in the same block.
  - **Tests.** New test files: `test_openai_img_gen_worker_error_handling.py`, `test_openai_completions_img_gen_worker_error_handling.py`, `test_google_img_gen_worker_error_handling.py`, `test_extract_azure_metadata.py`, `test_azure_img_gen_worker_error_handling.py`, `test_extract_fal_metadata.py`, `test_fal_img_gen_worker_semantic.py`, `test_extract_huggingface_metadata.py`, `test_huggingface_img_gen_worker_semantic.py`, `test_extract_gateway_metadata.py`, `test_gateway_img_gen_worker_semantic.py`. Existing tests (`test_google_worker_error_handling.py`, `test_azure_worker_error_handling.py`, `test_fal_worker_error_handling.py`, `test_hf_worker_error_handling.py`) all still pass — the new tests are additive (asserting metadata + user_action.kind) rather than replacing existing categorization checks.

- **2026-05-14 — Phase 3 landed.** `ProviderErrorMetadata` + `extract_anthropic_metadata` live in `pipelex/cogt/inference/error_classification.py`. Decisions:
  - **Field placement.** `provider_metadata` was added to `CogtError` (not the four leaf classes the plan named). The uniform base-class field keeps every subclass's `__init__` consistent and lets `to_error_report()` serialize it generically. Non-SDK CogtError subclasses just leave it `None` — same cost as Optional fields on the four leaves, simpler code.
  - **`AnthropicCredentialsError` carries metadata too** because we now have the metadata at the raise site and dropping it would lose auth-error telemetry (status_code 401, request_id).
  - **Forward reference resolution.** `ErrorReport` (Pydantic dataclass in `base_exceptions.py`) takes `ProviderErrorMetadata` as a string-forward-ref. To avoid making `base_exceptions` depend on `cogt/`, `cogt/exceptions.py` does the import and calls `rebuild_dataclass(cast("Any", ErrorReport), _types_namespace=...)`. The cast is needed because pyright doesn't recognize Pydantic dataclasses through its `PydanticDataclass` protocol. `arbitrary_types_allowed=True` is set on the dataclass config because `ProviderErrorMetadata` is a `BaseModel` (not a dataclass), which Pydantic v2 dataclasses don't accept by default.
  - **Body type handling.** `extract_anthropic_metadata` reads `exc.body` (Any) and `exc.response.headers["retry-after"]`. `_provider_error_code_from_body` casts the body to `dict[str, Any]` to silence `reportUnknownMemberType` on `.get()`. The fallback chain is `error.type` then `error.code` — Anthropic uses `type`, but other providers (when this helper pattern is replicated) commonly use `code`, so we accept both for future reuse.

- **2026-05-14 — Phase 11 landed.** Extract worker audits complete. Beyond-reference upgrades A–C delivered across Bedrock LLM (only LLM-side worker remaining), Mistral extract, Docling extract, Linkup extract, Gateway extract, pypdfium2. Decisions:
  - **`extract_bedrock_metadata` shape.** botocore's `ClientError` carries `response: dict` shaped `{"Error": {"Code": ..., "Message": ...}, "ResponseMetadata": {"RequestId": ..., "HTTPStatusCode": ..., "HTTPHeaders": {...}}}`. Status comes from `ResponseMetadata.HTTPStatusCode` (note: capital H — not `status_code`), request id from `ResponseMetadata.RequestId`, retry-after from `HTTPHeaders.retry-after`, provider_error_code from `Error.Code` (e.g. `ThrottlingException`). The full `response` dict is kept as `body` so downstream consumers don't need to re-scrape `str(exc)`. Tolerates malformed exceptions (no `response` attr) — every status-related field comes back as `None`.
  - **`extract_linkup_metadata` minimal shape.** The Linkup Python SDK raises typed exceptions (`LinkupAuthenticationError`, `LinkupTooManyRequestsError`, `LinkupInvalidRequestError` …) but does *not* expose `response`, `status_code`, `request_id`, or `retry-after` headers. The exception class name is the canonical signal — surfaced as both `sdk_exception_type` and `provider_error_code` so downstream consumers can branch without importing the Linkup SDK at the call site.
  - **`extract_local_extract_metadata(exc, provider=...)`** is a single shared helper for local (non-HTTP) extractors. Docling and pypdfium2 both reuse it; the per-call `provider` argument keeps the provider name on the metadata even though the helper is generic. Local extractors raise generic Python exceptions (`FileNotFoundError`, `ValueError`, `RuntimeError`, `OSError`) — the underlying exception class name is the only meaningful signal, so both `sdk_exception_type` and `provider_error_code` carry it.
  - **Bedrock 404 branch added.** The pre-existing `_gen_text` had ThrottlingException, ServiceQuotaExceededException, AccessDeniedException, ValidationException, ModelNotReadyException / ServiceUnavailableException, and a TRANSIENT fallback — but no explicit `ResourceNotFoundException` (404) branch. Added one that routes to CONFIGURATION + CHANGE_MODEL, mirroring the LLM-side pattern for `LLMModelNotFoundError`-ish semantics. The fallback path now routes to WAIT_AND_RETRY (was bare CONFIGURATION → no user_action).
  - **Mistral extract worker: dropped placeholder `UserAction(kind=UNKNOWN)`.** The pre-existing worker had `kind=UserActionKind.UNKNOWN` placeholders on 3 of 7 branches and no `user_action` at all on the other 4 (401/403, 404, generic 400, 500, fallback). Now every branch carries a semantic `kind` — uniform with the LLM worker.
  - **Linkup search worker NOT migrated in this phase.** The search worker (`linkup_search_worker.py`) has its own near-identical `_classify_linkup_error` method with UNKNOWN placeholders. Phase 12 will migrate it; for now the extract and search workers temporarily have *different* user-action kinds for the same SDK exceptions. This is intentional — Phase 11 is "extract only" by design.
  - **Gateway extract worker: tenacity retry boundary preserved.** The worker wraps Portkey calls in `AsyncRetrying(reraise=True, stop=stop_after_attempt(N))`. When all retries are exhausted, the last `APIError` is reraised verbatim into our `except portkey_exceptions.APIError as exc:` block — categorization signal and request_id are preserved across the retry boundary. Confirmed by inspection; no behavior change needed.
  - **Pyright body-dict cast pattern.** When tests assert against `metadata.body["Error"]["Code"]`, pyright narrows `metadata.body` (typed `Any | None`) to `dict[Unknown, Unknown]` through `isinstance(..., dict)`, which trips `reportUnknownMemberType`. The fix that works across providers is `body: Any = metadata.body; assert isinstance(body, dict); assert body["Error"]["Code"] == ...` — the explicit `Any` annotation keeps pyright from re-narrowing the indexed access.
  - **Tests.** New test files: `test_extract_bedrock_metadata.py` (8 tests), `test_bedrock_worker_semantic.py` (9 cases), `test_mistral_extract_worker_semantic.py` (10 cases), `test_docling_worker_semantic.py` (4 cases), `test_linkup_extract_worker_semantic.py` (10 cases including all 10 Linkup SDK exception types), `test_gateway_extract_worker_semantic.py` (5 cases), `test_pypdfium2_worker_semantic.py` (4 cases). All existing tests (`test_bedrock_worker_error_handling.py`, `test_mistral_worker_error_handling.py`, `test_docling_worker_error_handling.py`, `test_linkup_worker_error_handling.py`, `test_pypdfium2_worker_error_handling.py`, `test_gateway_*`) keep passing — the new tests are additive (asserting metadata + user_action.kind) rather than replacing existing categorization checks. Final sweep: `make agent-check` (0 errors) + 1122 plugins/cogt unit tests pass.

- **2026-05-15 — Phase 13 landed. Sweep DONE.** Final integration check complete. Decisions:
  - **Response-shape bare raises migrated.** The uniformity check surfaced that Phases 10–12 only migrated *SDK-error* raises — the *response-shape validation* bare raises (`raise XError(msg)` after a successful HTTP call when the payload is empty/malformed) were left untouched in the img-gen / extract / gateway-search workers. Phase 9 had explicitly cleaned these up for the LLM workers; Phases 10–12 had no equivalent step. Migrated every one of them to mirror Phase 9: `openai_img_gen` (5), `google_img_gen` (4), `azure_img_gen` (5), `gateway_img_gen` (13), `openai_completions_img_gen` (3), `fal_factory` (3), `gateway_extract` (2), `gateway_search` (3).
  - **Category policy for response-shape failures.** Three buckets, each with `provider_metadata=None` (non-SDK paths — no provider error code, status, or request id to extract): (a) "the model produced no usable image/output" (empty data, no candidates, no image bytes) → `error_category=CONTENT` + `UserActionKind.CHANGE_INPUT`, detail leads with "try rephrasing the prompt" — mirrors Phase 9's LLM treatment of "empty choices" / "content is None"; (b) "the provider returned a malformed/unexpected response shape" (missing output format, malformed size, missing url/width/height/content-type, unparseable payload) → `error_category=UNKNOWN` + `UserActionKind.CHANGE_MODEL` — rephrasing the prompt cannot fix a malformed response, so the actionable recourse is a different model; (c) "the provider returned no response at all" (`response is None` after retries exhausted) → `error_category=UNKNOWN` + `UserActionKind.CONTACT_SUPPORT`. The bucket-(b) split was a self-review correction: the first pass had used `CHANGE_INPUT` with detail text recommending a different model — a kind/detail mismatch — across ~21 sites; the kind, category, and detail now agree.
  - **No tests broke.** No existing test asserted on these response-shape error messages or their (previously absent) `error_category`, so the migration is purely additive. `gateway_img_gen` / `gateway_extract` / `gateway_search` / `fal_factory` needed `InferenceErrorCategory` + `UserAction` + `UserActionKind` added to their imports.
  - **`except Exception` audit.** The matches in `pipelex/plugins/` are all pre-existing best-effort `teardown()` async-client cleanup blocks (documented "log but don't fail teardown"), not error-classification paths — left as-is.
  - **Verification.** `make agent-check` clean (0 errors, 0 warnings); `make agent-test` clean. Extract/Classify/Render track prerequisites all confirmed satisfied — that track is ready to start.

- **2026-05-15 — Phase 12 landed.** Search worker audits complete. Beyond-reference upgrades A–C delivered across both search workers (Linkup, Gateway). Decisions:
  - **No new helpers needed.** Linkup search reuses `extract_linkup_metadata` (added Phase 11); Gateway search reuses `extract_gateway_metadata` + `GatewayFactory.make_user_action_from_portkey_error` (added Phase 10). Phases 10/11 explicitly pre-positioned these so Phase 12 is a pure adoption phase.
  - **Linkup search `_classify_linkup_error` mirrors the extract worker.** The search worker only catches the seven search-relevant Linkup exceptions (`LinkupAuthenticationError`, `LinkupInsufficientCreditError`, `LinkupTooManyRequestsError`, `LinkupTimeoutError`, `LinkupInvalidRequestError`, `LinkupNoResultError`, `LinkupUnknownError`) — not the three fetch-specific ones (`LinkupFetchResponseTooLargeError`, `LinkupFetchUrlIsFileError`, `LinkupFailedFetchError`) that only the extract worker handles. So the search `_classify_linkup_error` has no fetch-too-large branch; otherwise it is shape-identical to extract. `LinkupNoResultError`/`LinkupUnknownError` route through the TRANSIENT + WAIT_AND_RETRY fallback. Error message strings kept identical to the prior implementation so the existing `test_linkup_worker_error_handling.py` substring assertions still pass.
  - **Gateway search retry boundary preserved.** `_call_relay` wraps the Portkey call in `AsyncRetrying(reraise=True, stop=stop_after_attempt(N))`. When retries are exhausted the last `APIError` is reraised verbatim into `except portkey_exceptions.APIError as exc:`, so `extract_gateway_metadata(exc)` sees the original response/headers and `request_id` survives — same finding as the Phase 11 Gateway extract worker.
  - **Tests.** New: `test_linkup_search_worker_semantic.py` (7 cases) and `test_gateway_search_worker_semantic.py` (5 cases), both mirroring the Phase 11 extract semantic suites. Existing `test_linkup_worker_error_handling.py` (which covers both extract and search workers) still passes. `make agent-check` clean (0 errors, 0 warnings); `make agent-test` clean.
