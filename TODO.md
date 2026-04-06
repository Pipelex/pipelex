# TODO: Worker Error Handling Standardization

> Reference: `wip/worker-error-handling-review.md` for the full review of current state.

---

## Definition of DONE

Every phase is done when **all** of the following are true:

1. **All workers catch SDK-specific exceptions** and wrap them in domain exceptions with `from exc`, model descriptor in message, and error category assigned
2. **`make agent-check` passes** (pyright, mypy, ruff)
3. **`make agent-test` passes** (full test suite green)
4. **New unit tests exist** for each changed error path — tests verify:
   - The correct custom exception type is raised
   - The error category is set correctly
   - The error message includes model descriptor
   - The `from exc` chain is preserved
   - The `to_error_report()` output matches the expected JSON schema
5. **CLI `--format json` error output** is tested with snapshot tests for representative error types
6. **Temporal compatibility verified**: `TemporalError.from_message_exception()` correctly extracts error category and maps to `non_retryable` based on category, tested with unit tests
7. **Agent CLI** `agent_error()` updated to use structured fields from exceptions rather than lookup dicts, tested

---

## Phase 0: Error Category Infrastructure

> Foundation that all other phases depend on. No worker changes yet.

- [x] **0.1** Create `InferenceErrorCategory` enum in `pipelex/cogt/exceptions.py`
  - Values: `TRANSIENT`, `CONFIGURATION`, `CONTENT`, `CAPACITY`
  - Import from `pipelex.types.StrEnum`
  - Add `is_retryable` property: `True` only for `TRANSIENT`

- [x] **0.2** Add `error_category` field to `CogtError`
  - Optional field, default `None` (backward compatible)
  - Subclasses that already know their category set it at class level (e.g. `LLMModelNotFoundError` → `CONFIGURATION`)

- [x] **0.3** Add `user_action` optional field to `CogtError`
  - Short, plain-English suggestion for the user or agent
  - Set per-instance by workers when raising, or per-class as a default

- [x] **0.4** Add `to_error_report()` method on `PipelexError`
  - Returns a dict with: `error_type`, `message`, `error_category` (if set), `user_action` (if set), `retryable` (derived from category), `provider` (if set), `model` (if set)
  - Only includes non-None fields
  - This is the single source of truth for all error serialization (CLI JSON, agent output, Temporal)

- [x] **0.5** Tests for Phase 0
  - Unit tests for `InferenceErrorCategory` enum properties
  - Unit tests for `to_error_report()` on `CogtError` and its subclasses
  - Test that `to_error_report()` output is JSON-serializable
  - Test backward compat: existing exceptions without category still work

---

## Phase 1: CLI Error Output

> Main CLI (`pipelex`) always uses Rich output. Agent CLI (`pipelex-agent`) uses markdown text by default, or JSON with `--format json`. See `CliOutputFormat` in `agent_output.py`.

- [x] **1.1** Refactor `agent_output.py` to use `to_error_report()`
  - Replace the `AGENT_ERROR_HINTS`, `RETRYABLE_ERROR_TYPES`, `AGENT_ERROR_DOMAINS` lookup dicts
  - Instead, call `exc.to_error_report()` when the exception is a `PipelexError`
  - Keep the lookup dicts as fallback for non-PipelexError exceptions (FileNotFoundError, JSONDecodeError, etc.)
  - Merge agent-specific fields (hint, error_source) on top of the report

- [x] **1.2** Update `error_handlers.py` to use `to_error_report()` for Rich output
  - Each `handle_*` function calls `to_error_report()` to build the error data
  - Rich formatting uses the report fields for consistent, structured display
  - No `--format` option on the main CLI — it is always Rich

- [x] **1.3** Tests for Phase 1
  - Snapshot tests: representative errors in agent CLI JSON mode match expected schema
  - Test that `agent_error()` output includes fields from `to_error_report()`
  - Test that agent CLI `--format json` produces valid JSON on stderr for known error types
  - Test that agent CLI default (no `--format`) produces markdown text output
  - Test that main CLI still produces Rich output (no format option)

---

## Phase 2: Bring OpenAI/Anthropic Workers to Full Coverage

> These are already Tier 1/2, add the missing pieces.

- [x] **2.1** Add `RateLimitError` handling to all OpenAI workers
  - `openai_completions_llm_worker.py`, `openai_responses_llm_worker.py`, `openai_img_gen_worker.py`, `openai_completions_img_gen_worker.py`
  - Catch `RateLimitError` → `LLMCompletionError` / `ImgGenGenerationError` with `error_category=TRANSIENT`
  - `user_action`: "Rate limited by OpenAI — the system will retry automatically"

- [x] **2.2** Add `APITimeoutError` handling to all OpenAI workers
  - Same files as 3.1
  - Catch `APITimeoutError` → domain error with `error_category=TRANSIENT`

- [x] **2.3** Add `AuthenticationError` to `openai_completions_img_gen_worker.py` (currently missing)
  - With `error_category=CONFIGURATION`

- [x] **2.4** Add SDK exception handling to `openai_img_gen_worker.py`
  - Currently has no try/except — add full pattern matching other OpenAI workers

- [x] **2.5** Add `RateLimitError` and `APITimeoutError` to `anthropic_llm_worker.py`
  - Same pattern as OpenAI

- [x] **2.6** Set `error_category` on all existing exception raises in OpenAI/Anthropic workers
  - `NotFoundError` → `CONFIGURATION`
  - `APIConnectionError` → `TRANSIENT`
  - `BadRequestError` → `CONTENT` (default), `CONFIGURATION` (if detectable)
  - `AuthenticationError` → `CONFIGURATION`
  - `InstructorRetryException` → `CONTENT`

- [x] **2.7** Add content policy detection for OpenAI and Anthropic
  - Inspect `BadRequestError` message for "content_policy", "safety", "content_filter" keywords
  - Raise with `error_category=CONTENT`, `user_action`: "Content was rejected by safety filters — revise the prompt"
  - Also check `finish_reason == "content_filter"` in OpenAI response validation

- [x] **2.8** Add quota/credits exhaustion detection for OpenAI and Anthropic
  - **Problem:** Rate limit (429) and out-of-credits (429) share the same HTTP status — must inspect the error body to distinguish them
  - **OpenAI:** `RateLimitError` with `"insufficient_quota"` or `"exceeded your current quota"` in message → `CAPACITY`; `AuthenticationError` with `"insufficient_quota"` → `CAPACITY`
  - **Anthropic:** `RateLimitError` or `PermissionDeniedError` with `"quota"` or `"billing"` in message → `CAPACITY`
  - Raise with `error_category=CAPACITY`, `non_retryable=True`
  - `user_action`: "Your {provider} account has exceeded its quota — check your billing dashboard at {billing_url}"
  - Billing URLs: OpenAI → `platform.openai.com/account/billing`, Anthropic → `console.anthropic.com/settings/billing`
  - **Must be checked before the generic `RateLimitError` → `TRANSIENT` handler** (order matters in except blocks, or use message inspection within a single handler)

- [x] **2.9** Tests for Phase 2
  - Unit tests per worker: mock SDK to raise each exception type, verify correct domain exception + category
  - Test content policy detection on known error message patterns
  - Test quota detection: mock `RateLimitError` with quota message → verify `CAPACITY` category
  - Test quota detection: mock `RateLimitError` with generic rate limit message → verify `TRANSIENT` category
  - Test that `to_error_report()` includes provider and model for each error path

---

## Phase 3: Bring Tier 3 Workers Up

> The workers with no error handling at all.

- [x] **3.1** `google_llm_worker.py` — add Google API exception handling
  - Catch `google.genai.errors.ClientError` / `ServerError` with status code inspection
  - Map to `LLMCompletionError` with appropriate categories
  - 429 with quota patterns → `CAPACITY`; generic 429 → `TRANSIENT`
  - 401/403 → `CONFIGURATION`, 404 → `CONFIGURATION`, 400 → `CONTENT`

- [x] **3.2** `google_img_gen_worker.py` — same pattern as 3.1 for image generation
  - Map to `ImgGenGenerationError` with categories

- [x] **3.3** `mistral_llm_worker.py` — add Mistral SDK exception handling
  - Catch `MistralError` with `status_code` inspection
  - Map to `LLMCompletionError` with categories
  - Quota detection: HTTP 402 (Payment Required) or 429 with `"quota"` in message → `CAPACITY`

- [x] **3.4** `mistral_extract_worker.py` — add error handling
  - Wrap Mistral OCR API calls
  - Map to `ExtractJobFailureError` with categories
  - Same quota detection pattern as 3.3

- [x] **3.5** `bedrock_llm_worker.py` — add AWS error handling
  - Catch `botocore.exceptions.ClientError` with error code inspection
  - `ThrottlingException`: inspect message — `"quota"` or `"limit exceeded"` → `CAPACITY`; otherwise → `TRANSIENT`
  - `AccessDeniedException` → `CONFIGURATION`
  - `ValidationException` → `CONTENT`
  - AWS-specific: `ServiceQuotaExceededException` → `CAPACITY`

- [x] **3.6** `azure_img_gen_worker.py` — wrap httpx errors
  - Catch `httpx.HTTPStatusError` with status code inspection
  - 429 → `TRANSIENT`, 402 → `CAPACITY`, 401/403 → `CONFIGURATION`, 400 → `CONTENT`
  - Catch `httpx.ConnectError` → `TRANSIENT`
  - Catch `httpx.TimeoutException` → `TRANSIENT`

- [x] **3.7** `fal_img_gen_worker.py` — add FAL error handling
  - Catch `FalClientHTTPError`, `FalClientTimeoutError`, `MissingCredentialsError`, `FalClientError`
  - Map to `ImgGenGenerationError` with categories

- [x] **3.8** `huggingface_img_gen_worker.py` — add HuggingFace error handling
  - Catch `InferenceTimeoutError`, `HfHubHTTPError`
  - Map to `ImgGenGenerationError` with categories

- [x] **3.9** `docling_extract_worker.py` — add conversion error handling
  - Wrap `docling` conversion calls
  - Map to `ExtractJobFailureError` (ValueError/RuntimeError → CONTENT, FileNotFoundError → CONFIGURATION, OSError → TRANSIENT)

- [x] **3.10** `linkup_extract_worker.py` and `linkup_search_worker.py` — add Linkup error handling
  - Catch all `linkup` exception types (AuthenticationError, InsufficientCreditError, TooManyRequestsError, etc.)
  - Map to `ExtractJobFailureError` / `SearchJobFailureError` with categories

- [x] **3.11** `pypdfium2_worker.py` — add PDF operation error handling
  - Wrap pypdfium2 calls
  - Map to `ExtractJobFailureError` (ValueError/RuntimeError → CONTENT, FileNotFoundError → CONFIGURATION, OSError → TRANSIENT)

- [x] **3.12** Add quota/credits detection to gateway workers
  - `gateway_extract_worker.py`, `gateway_img_gen_worker.py`, `gateway_search_worker.py`
  - Added `_classify_portkey_error_category()` method to each gateway worker
  - Inspect `portkey_exceptions.APIStatusError` status code and message
  - 402 or 429 with quota patterns → `CAPACITY`; RateLimitError → `TRANSIENT`; AuthenticationError → `CONFIGURATION`; BadRequestError → `CONTENT`

- [x] **3.13** Tests for Phase 3
  - Unit tests per worker: mock SDK to raise each exception type, verify domain exception + category
  - At least 2 error scenarios per worker (one transient, one configuration)
  - Quota detection tests: mock 429 with quota message → verify `CAPACITY`; mock 429 without → verify `TRANSIENT`

---

## Phase 4: Retry Standardization

> Extract the gateway workers' retry pattern into a shared utility.

- [ ] **4.1** Create shared retry decorator/mixin
  - Extract from `gateway_extract_worker.py`'s tenacity pattern
  - Parameterized: retry on `TRANSIENT` category, fail fast on others
  - Configurable max retries, backoff from worker config
  - Logs each retry with attempt number, wait duration, error category

- [ ] **4.2** Apply to all remote API workers
  - OpenAI, Anthropic, Google, Mistral, Azure, FAL, HuggingFace, Linkup
  - Replace any existing ad-hoc retry logic
  - Skip for local workers (docling, pypdfium2)

- [ ] **4.3** Add retry to `gateway_img_gen_worker.py` (currently missing unlike gateway extract/search)

- [ ] **4.4** Tests for Phase 4
  - Unit test: transient error retries up to max, then raises
  - Unit test: configuration error fails immediately (no retry)
  - Unit test: retry logging includes attempt number and wait duration
  - Integration test: verify gateway img gen worker retries on transient errors

---

## Phase 5: Enrich Error Messages

> Now that infrastructure is in place, make every error message actionable.

- [ ] **5.1** Audit all `user_action` strings across workers
  - Every error path should have a user_action that tells the user (or agent) exactly what to do
  - Group by category:
    - TRANSIENT: "will retry automatically" or "try again in a moment"
    - CONFIGURATION: specific fix ("check API key", "enable backend X", "model Y not available on your plan")
    - CONTENT: "revise the prompt", "reduce input size", "content flagged by safety filters"
    - CAPACITY: "upgrade your plan" or "wait for quota reset"

- [ ] **5.2** Add `provider` field to worker exceptions
  - Set by each worker: "openai", "anthropic", "google", "mistral", "azure", "fal", "huggingface", "linkup", "docling", "pypdfium2"
  - Included in `to_error_report()`

- [ ] **5.3** Migrate `AGENT_ERROR_HINTS` for inference errors
  - Move inference-related hints from `agent_output.py` lookup dict into the exception classes themselves (via `user_action`)
  - Keep non-inference hints (FileNotFoundError, JSONDecodeError, etc.) in the lookup dict

- [ ] **5.4** Tests for Phase 5
  - Test that every `CogtError` subclass used by workers has a non-None `user_action`
  - Test that every worker exception includes `provider` in `to_error_report()`

---

## Phase 6: Temporal Bridge

> Make `TemporalError` use the new category system. Now that all workers carry error categories, the Temporal integration can leverage them for retry decisions and structured error details.

- [ ] **6.1** Update `TemporalError.from_message_exception()` in `_temporal/pipelex/temporal/tprl/temporal_error.py`
  - If the `PipelexError` has `error_category`, use `is_retryable` to set `non_retryable` on the `ApplicationError`
  - Pass `error_category` as the `type` field (or keep class name as type and add category to details)
  - Preserve existing behavior for exceptions without a category (fall back to `non_retryable_error_types` config list)

- [ ] **6.2** Update `RetryPolicyConfig.non_retryable_error_types` usage
  - Document that the config list is a fallback for exceptions that don't carry a category
  - Long-term: as workers gain categories, the config list shrinks

- [ ] **6.3** Add `to_error_report()` data as `ApplicationError` details
  - Temporal's `ApplicationError` accepts `details` (arbitrary serializable data)
  - Pack the `to_error_report()` dict into details so workflows and clients can inspect structured error info
  - Update `TemporalError.from_app_error()` to extract and expose these details

- [ ] **6.4** Tests for Phase 6
  - Unit test: `TemporalError.from_message_exception()` with a `CogtError` that has `error_category=TRANSIENT` → `non_retryable=False`
  - Unit test: `TemporalError.from_message_exception()` with `error_category=CONFIGURATION` → `non_retryable=True`
  - Unit test: `TemporalError.from_app_error()` round-trips the error report details
  - Unit test: exceptions without category fall back to config list behavior
