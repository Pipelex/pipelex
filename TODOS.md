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

- [ ] **RED** — write `tests/unit/pipelex/plugins/mistral/test_extract_mistral_metadata.py`. **First** confirm `MistralError` and its subclasses' attribute shapes against the installed `mistralai` (varies across versions).
- [ ] **RED** — write `tests/unit/pipelex/plugins/mistral/test_mistral_llm_worker_object_error_handling.py`. Cases (each asserts category + `user_action.kind` + `provider_metadata`):
  - Wrapped `MistralError` (rate-limit) → `TRANSIENT` + `WAIT_AND_RETRY`
  - Wrapped `MistralError` (HTTP 402 / quota match) → `CAPACITY` + `CHECK_BILLING`
  - Wrapped `MistralError` (timeout) → `TRANSIENT` + `WAIT_AND_RETRY`
  - Wrapped `MistralError` (connection) → `TRANSIENT` + `WAIT_AND_RETRY`
  - Wrapped `MistralError` (content-policy) → `CONTENT` + `CHANGE_INPUT`
  - Wrapped `MistralError` (auth) → `CONFIGURATION` + `CHECK_CREDENTIALS`
  - Wrapped non-`MistralError` (e.g. `pydantic.ValidationError`) → `UNKNOWN` + `UNKNOWN`
  - Real-instructor end-to-end: patch `mistralai.Mistral.chat.complete_async` (or current `from_mistral` adapter target) with `AsyncMock(side_effect=MistralError(...))`
- [ ] **GREEN** — write `extract_mistral_metadata(exc: MistralError) -> ProviderErrorMetadata`
- [ ] **GREEN** — add to `pipelex/plugins/mistral/mistral_llm_worker.py`:
  ```python
  except InstructorRetryException as instructor_exc:
      underlying = extract_underlying_sdk_exception(instructor_exc)
      if isinstance(underlying, MistralError):
          raise self._classify_mistral_error(underlying) from instructor_exc
      msg = f"Mistral structured generation failed after retries for model '{self.inference_model.desc}': {instructor_exc}"
      raise LLMCompletionError(
          msg,
          error_category=InferenceErrorCategory.UNKNOWN,
          user_action=UserAction(kind=UserActionKind.UNKNOWN, detail="Unexpected error from Mistral structured generation"),
          provider_metadata=None,
      ) from instructor_exc
  ```
- [ ] **GREEN** — refine `_classify_mistral_error` to attach `provider_metadata=extract_mistral_metadata(exc)` and use semantic `user_action.kind` on every raise inside it
- [ ] Migrate `instructor.exceptions` → `instructor.core`
- [ ] **AUDIT** — `mistralai` SDK exception hierarchy
- [ ] Run tests + `make agent-check`

> ### **STOP — CHECKPOINT H: Mistral LLM done**

---

## Phase 8 — Google Gemini LLM

Symmetric to Mistral, plus `ServerError → TRANSIENT` direct mapping that doesn't need `_classify_google_client_error`. Add `extract_google_metadata`.

- [ ] **RED** — write `tests/unit/pipelex/plugins/google/test_extract_google_metadata.py`. **First** check `genai_errors.ServerError` / `ClientError` constructor shape (they wrap an HTTP response object); reuse the construction pattern from existing `_classify_google_client_error` tests if any exist.
- [ ] **RED** — write `tests/unit/pipelex/plugins/google/test_google_llm_worker_object_error_handling.py`. If construction is awkward, prefer wrapping a real SDK exception via `_wrap_in_instructor_retry(real_sdk_exc)` and keep only the real-instructor end-to-end test provider-specific. Cases (each asserts category + `user_action.kind` + `provider_metadata`):
  - Wrapped `genai_errors.ServerError` → `TRANSIENT` + `WAIT_AND_RETRY`
  - Wrapped `genai_errors.ClientError` (rate-limit) → `TRANSIENT` + `WAIT_AND_RETRY`
  - Wrapped `genai_errors.ClientError` (quota) → `CAPACITY` + `CHECK_BILLING`
  - Wrapped `genai_errors.ClientError` (content-policy) → `CONTENT` + `CHANGE_INPUT`
  - Wrapped `genai_errors.ClientError` (auth) → `CONFIGURATION` + `CHECK_CREDENTIALS`
  - Wrapped `genai_errors.ClientError` (bad request) → `CONTENT` + `UNKNOWN`
  - Wrapped non-SDK exception → `UNKNOWN` + `UNKNOWN`
  - Real-instructor end-to-end: patch the `genai.Client.aio.models.generate_content`-equivalent that `instructor.from_genai` calls
- [ ] **GREEN** — write `extract_google_metadata(exc: genai_errors.APIError) -> ProviderErrorMetadata` (or whatever the Google base class is)
- [ ] **GREEN** — add to `pipelex/plugins/google/google_llm_worker.py`:
  ```python
  except InstructorRetryException as instructor_exc:
      underlying = extract_underlying_sdk_exception(instructor_exc)
      if isinstance(underlying, genai_errors.ServerError):
          msg = f"Google API server error for model '{self.inference_model.desc}': {underlying}"
          raise LLMCompletionError(
              msg,
              error_category=InferenceErrorCategory.TRANSIENT,
              user_action=UserAction(kind=UserActionKind.WAIT_AND_RETRY, detail="Google API server error — will retry"),
              provider_metadata=extract_google_metadata(underlying),
          ) from instructor_exc
      if isinstance(underlying, genai_errors.ClientError):
          raise self._classify_google_client_error(underlying) from instructor_exc
      msg = f"Google structured generation failed after retries for model '{self.inference_model.desc}': {instructor_exc}"
      raise LLMCompletionError(
          msg,
          error_category=InferenceErrorCategory.UNKNOWN,
          user_action=UserAction(kind=UserActionKind.UNKNOWN, detail="Unexpected error from Google structured generation"),
          provider_metadata=None,
      ) from instructor_exc
  ```
- [ ] **GREEN** — refine `_classify_google_client_error` to attach `provider_metadata=extract_google_metadata(exc)` and use semantic `user_action.kind` on every raise
- [ ] Migrate `instructor.exceptions` → `instructor.core`
- [ ] **AUDIT** — `google-genai` SDK exception hierarchy
- [ ] Run tests + `make agent-check`

> ### **STOP — CHECKPOINT I: Google Gemini LLM done**
>
> **Hand-off context:** all four instructor-unwrap workers now classify wrapped errors correctly AND carry full structured metadata + semantic user_action. LLM-side defect closed; beyond-reference upgrades A–C delivered for the four targeted workers plus Anthropic.

---

## Phase 9 — LLM cross-cutting cleanup

- [ ] Full LLM test sweep: `.venv/bin/pytest tests/unit/pipelex/plugins/{anthropic,openai,mistral,google}/` — confirm zero failures
- [ ] `rg "from instructor.exceptions" pipelex/` — must return zero results
- [ ] **Uniformity check** — `rg "raise LLMCompletionError" pipelex/plugins/{anthropic,openai,mistral,google}/` — every match should include `provider_metadata=` AND `user_action=UserAction(...)` (with a semantic `kind`, not `UNKNOWN`, except for the unrecognized-underlying fallback paths)
- [ ] **AWS Bedrock decision check** — if Phase 0 found Bedrock uses `instructor`, confirm Phase 8.5 landed (or schedule it now). If not, confirm the Bedrock worker still benefits from upgrades A–C in Phase 11 below.
- [ ] Update [wip/error-handling/track-worker-classification.md](wip/error-handling/track-worker-classification.md):
  - Move "Instructor unwrap missing on four other workers" out of "Open gaps"
  - Strike followups 1 (Phase 1), 2–5 (Phases 5–8), and 6 (Phases 5–8) from the followup list
  - Add a note that beyond-reference upgrades A (UNKNOWN), B (ProviderErrorMetadata), C (UserAction) have landed across these workers
- [ ] Update [wip/error-handling/README.md](wip/error-handling/README.md) status table row "Worker classification" → drop the gap clause; mark Landed. Update "Error metadata model" row to reflect that structured metadata is now uniform across LLM workers.
- [ ] `make agent-check && make agent-test`

> ### **STOP — CHECKPOINT J: LLM-side track closed**
>
> **Hand-off context:** worker-classification track has no remaining LLM-side gaps. Track docs reflect reality. Beyond-reference upgrades A–C live across all LLM workers that this sweep touched (Anthropic + 4). Other LLM workers still need upgrade migration via Phase 11. Ready to audit non-LLM worker kinds.

---

## Phase 10 — Img-gen worker audits

> Note: each worker within this phase is an independent unit of work. The agent may save/checkpoint between workers if context grows — record per-worker hand-off in the Running Notes section.

The img-gen workers already have basic classification landed. This phase brings each up to the beyond-reference standard: extract metadata, structured user_action, UNKNOWN fallback where applicable, and confirms SDK exception coverage.

For each worker: (a) read source — confirm every documented SDK exception type is caught and routed through the right discriminator; (b) write `extract_<provider>_metadata` helper if not already done (some providers may already have it from LLM workers — e.g. OpenAI img-gen reuses `extract_openai_metadata`); (c) update each raise to pass `provider_metadata=...` and semantic `user_action=UserAction(...)`; (d) replace `CONTENT` fallback with `UNKNOWN` where the underlying is genuinely unknown; (e) update tests to assert metadata + user_action.kind.

- [ ] **OpenAI img-gen** — `pipelex/plugins/openai/openai_img_gen_worker.py` (reuse `extract_openai_metadata`)
- [ ] **OpenAI Completions img-gen** — `pipelex/plugins/openai/openai_completions_img_gen_worker.py` (reuse `extract_openai_metadata`)
- [ ] **Google img-gen** — `pipelex/plugins/google/google_img_gen_worker.py` (reuse `extract_google_metadata`)
- [ ] **Azure img-gen** — `pipelex/plugins/azure/azure_img_gen_worker.py` (new `extract_azure_metadata`)
- [ ] **FAL img-gen** — `pipelex/plugins/fal/fal_img_gen_worker.py` (new `extract_fal_metadata`)
- [ ] **HuggingFace img-gen** — `pipelex/plugins/huggingface/huggingface_img_gen_worker.py` (new `extract_huggingface_metadata`)
- [ ] **Gateway img-gen** — `pipelex/plugins/gateway/gateway_img_gen_worker.py` (new or shared `extract_gateway_metadata`)
- [ ] `make agent-check && make agent-test`

> ### **STOP — CHECKPOINT K: Img-gen audit complete**

---

## Phase 11 — Extract worker audits + AWS Bedrock LLM (if not handled in 8.5)

Same approach as Phase 10. Bedrock LLM lands here too if Phase 0 found it doesn't use instructor (no unwrap defect, but it still benefits from upgrades A–C).

- [ ] **AWS Bedrock LLM** — `pipelex/plugins/bedrock/bedrock_llm_worker.py` (skip if Phase 8.5 already shipped — confirm in Running Notes)
- [ ] **Mistral extract** — `pipelex/plugins/mistral/mistral_extract_worker.py` (reuse `extract_mistral_metadata`)
- [ ] **Docling extract** — `pipelex/plugins/docling/docling_extract_worker.py` (new `extract_docling_metadata` — Docling is not an HTTP SDK; metadata fields like `status_code`/`request_id` will be `None` for most cases, but `sdk_exception_type` and `provider_error_code` still useful)
- [ ] **Linkup extract** — `pipelex/plugins/linkup/linkup_extract_worker.py` (new `extract_linkup_metadata`)
- [ ] **Gateway extract** — `pipelex/plugins/gateway/gateway_extract_worker.py` (reuse `extract_gateway_metadata`; has its own tenacity retry — confirm it doesn't swallow categorization signal or strip metadata)
- [ ] **pypdfium2** — `pipelex/plugins/pypdfium2/pypdfium2_worker.py` (pypdfium2 is purely local; minimal metadata, no network — adapt fields accordingly)
- [ ] `make agent-check && make agent-test`

> ### **STOP — CHECKPOINT L: Extract audit complete**

---

## Phase 12 — Search worker audits

- [ ] **Linkup search** — `pipelex/plugins/linkup/linkup_search_worker.py` (reuse `extract_linkup_metadata`)
- [ ] **Gateway search** — `pipelex/plugins/gateway/gateway_search_worker.py` (reuse `extract_gateway_metadata`; has its own tenacity retry — confirm categorization survives the retry boundary)
- [ ] `make agent-check && make agent-test`

> ### **STOP — CHECKPOINT M: Search audit complete**

---

## Phase 13 — Final integration check

- [ ] Full suite: `make agent-test`
- [ ] Confirm no `except Exception:` regressions: `rg "except Exception" pipelex/plugins/` — must be empty (or each match has a documented reason in source)
- [ ] Confirm every worker chains via `from exc` and uses `msg = ...; raise XError(msg) from exc` (per `_tprl/CLAUDE.md` rules)
- [ ] **Uniformity check** — every raised `LLMCompletionError` / `ImgGenGenerationError` / `ExtractJobFailureError` / `SearchJobFailureError` in `pipelex/plugins/` includes `provider_metadata=` (`None` allowed only for non-SDK fallback paths) AND `user_action=UserAction(...)` (with `kind != UNKNOWN`, except for fallback paths). One-liner audit: `rg "raise (LLMCompletionError|ImgGenGenerationError|ExtractJobFailureError|SearchJobFailureError)" pipelex/plugins/ -A 6 | rg -v "provider_metadata" | rg "raise (LLM|Img|Extract|Search)"` — should return zero "orphan" raises
- [ ] Confirm `rg "kind=UserActionKind.UNKNOWN" pipelex/plugins/` only matches inside fallback / unrecognized-underlying paths (not in any semantically-typed catch)
- [ ] Update [wip/error-handling/README.md](wip/error-handling/README.md) status table — drop any residual-gap clauses introduced during audits; update "Error metadata model" → fully landed if metadata is now uniform
- [ ] Confirm [wip/error-handling/track-testing.md](wip/error-handling/track-testing.md) "worker-level classification tests are comprehensive" claim still matches reality (or update it)
- [ ] **Verify the Extract/Classify/Render track is ready to start:** [track-extract-classify-render.md](wip/error-handling/track-extract-classify-render.md) prerequisites should all be satisfied. Confirm the doc still accurately describes the current state.

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
- **2026-05-14 — Phase 3 landed.** `ProviderErrorMetadata` + `extract_anthropic_metadata` live in `pipelex/cogt/inference/error_classification.py`. Decisions:
  - **Field placement.** `provider_metadata` was added to `CogtError` (not the four leaf classes the plan named). The uniform base-class field keeps every subclass's `__init__` consistent and lets `to_error_report()` serialize it generically. Non-SDK CogtError subclasses just leave it `None` — same cost as Optional fields on the four leaves, simpler code.
  - **`AnthropicCredentialsError` carries metadata too** because we now have the metadata at the raise site and dropping it would lose auth-error telemetry (status_code 401, request_id).
  - **Forward reference resolution.** `ErrorReport` (Pydantic dataclass in `base_exceptions.py`) takes `ProviderErrorMetadata` as a string-forward-ref. To avoid making `base_exceptions` depend on `cogt/`, `cogt/exceptions.py` does the import and calls `rebuild_dataclass(cast("Any", ErrorReport), _types_namespace=...)`. The cast is needed because pyright doesn't recognize Pydantic dataclasses through its `PydanticDataclass` protocol. `arbitrary_types_allowed=True` is set on the dataclass config because `ProviderErrorMetadata` is a `BaseModel` (not a dataclass), which Pydantic v2 dataclasses don't accept by default.
  - **Body type handling.** `extract_anthropic_metadata` reads `exc.body` (Any) and `exc.response.headers["retry-after"]`. `_provider_error_code_from_body` casts the body to `dict[str, Any]` to silence `reportUnknownMemberType` on `.get()`. The fallback chain is `error.type` then `error.code` — Anthropic uses `type`, but other providers (when this helper pattern is replicated) commonly use `code`, so we accept both for future reuse.
