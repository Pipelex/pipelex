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

## Phase 4: Markdown-Default Agent CLI Output

> Make all agent CLI commands return markdown by default, with `--format json` for structured output.
> Currently `models`, `doctor`, `check-model` already support this. This phase extends it to
> `run`, `validate`, and error output. Commands where JSON IS the payload (`inputs`, `concept`,
> `pipe`) are excluded -- their output format is inherent to the command's purpose.
>
> **Scope:**
> - `run` (pipe, bundle, method): success output as markdown, `--format json` for structured
> - `validate` (pipe, bundle, method): success output as markdown, `--format json` for structured
> - `agent_error()`: markdown by default to stderr, `--format json` for structured
> - `init`: success output as markdown (simple confirmation)
> - **Excluded:** `inputs` (returns JSON template), `concept`/`pipe` (returns TOML), `fmt`/`lint` (passthrough)

- [ ] **4.1** Add `agent_error_markdown()` function to `agent_output.py`
  - Markdown rendering of errors, parallel to `agent_error()` which remains the JSON path
  - Format: heading with error type, message body, hint as a tip callout, error_source as code block
  - Must still print to stderr and `raise typer.Exit(1) from cause`

- [ ] **4.2** Add format-aware error dispatch
  - Introduce a way for commands to pass the current `CliOutputFormat` to the error path
  - Options: thread-local / context var, or pass format explicitly to a new `agent_error_dispatch(format, ...)` wrapper
  - `agent_error()` (JSON) and `agent_error_markdown()` are the two backends
  - Keep `agent_error()` as the default when format is unknown (e.g., errors during init before format is parsed)

- [ ] **4.3** Add `--format` option to `run` commands
  - Add `output_format: CliOutputFormat = CliOutputFormat.MARKDOWN` option to `pipe_cmd.py`, `bundle_cmd.py`, `method_cmd.py`
  - Follow existing pattern from `models_cmd.py`: `match/case` on format
  - JSON path: existing `agent_success(result)` unchanged
  - Markdown path: new `_format_run_markdown(result)` function
  - Run markdown should render: main_stuff content (markdown representation if available, else formatted JSON), output file path, graph file path

- [ ] **4.4** Add `--format` option to `validate` commands
  - Same pattern as 4.3 for `validate/pipe_cmd.py`, `bundle_cmd.py`, `method_cmd.py`
  - Markdown path: new `_format_validate_markdown(result)` function
  - Validate markdown should render: pass/fail summary, list of validated pipes with status, error details if any

- [ ] **4.5** Add `--format` option to `init` command
  - Same pattern for `init_cmd.py`
  - Markdown path: simple confirmation with target dir, backends enabled, routing profile

- [ ] **4.6** Wire format into error handlers in `agent_cli_factory.py`
  - `make_pipelex_for_agent_cli()` catches init errors before format is known -- keep JSON for these
  - Command-level error handlers should respect the format option

- [ ] **4.7** Update `agent_cli/CLAUDE.md` to document the new output contract
  - Default format is markdown for all commands except inputs/concept/pipe/fmt/lint
  - `--format json` available on run, validate, init, models, doctor, check-model
  - Errors respect the same format option
  - Document the markdown structure for each command

- [ ] **4.8** Tests for Phase 4
  - Test that `run` with no `--format` produces markdown to stdout
  - Test that `run --format json` produces valid JSON to stdout
  - Test that `validate` with no `--format` produces markdown
  - Test that errors produce markdown to stderr by default
  - Test that errors with `--format json` produce JSON to stderr
  - Test that `inputs` command is unaffected (always JSON)

---

## Phase 5: Retry Architecture

> Move retry responsibility from workers to PipeRouter — the dispatch layer that sits between
> pipeline orchestration and pipe execution. Workers classify errors, PipeRouter retries.
>
> **Design principle — three retry layers, each with a distinct role:**
>
> | Layer | What | Retries on | Controlled by |
> |-------|------|-----------|---------------|
> | SDK transport | Connection resets, DNS, 503 | Built into OpenAI/Anthropic/Google SDKs | SDK defaults |
> | **PipeRouter (new)** | **TRANSIENT CogtErrors after SDK retries exhausted** | **Rate limits, timeouts, brief outages** | **`pipelex.toml` config** |
> | Temporal (future) | Longer failures, workflow-level retry | Service outages, cascading errors | Temporal retry policy |
>
> The PipeRouter retry is complementary to Temporal: it handles fast transients (seconds),
> Temporal handles longer failures (minutes). Without Temporal, PipeRouter retry is the only
> application-level retry — Pipelex must remain usable and resilient standalone.
>
> **Where in the code:** `PipeRouterProtocol.run()` in `pipe_run/pipe_router_protocol.py:47-67`.
> Currently catches `PipeRunError` only. The new logic adds a retry loop around
> `_run_pipe_job()` that catches `CogtError` with `is_retryable=True`.

- [ ] **5.1** Remove tenacity from gateway workers
  - `gateway_extract_worker.py`: remove `_make_retryer()`, `_is_retryable_portkey_error()`,
    `_log_retry()`, tenacity imports, and the `async for attempt in self._make_retryer()` wrapper
  - `gateway_search_worker.py`: same removal
  - Remove `TenacityConfig` from `config_cogt.py` and the `tenacity_config` field from `Cogt`
  - Remove corresponding entries from `pipelex.toml` config files
  - Remove `tenacity` from project dependencies if no longer used anywhere
  - Remove `tools/misc/tenacity_utils.py` if no longer referenced
  - Verify errors still propagate with correct `InferenceErrorCategory` (existing tests should cover)

- [ ] **5.2** Audit all workers for ad-hoc retry logic
  - Confirm no worker does business-level retries outside of SDK internals
  - Instructor's `max_retries` for structured generation is acceptable (it retries on schema
    validation failure, not transport errors) — document this with a code comment
  - Document any remaining retry behavior in a code comment at the worker level

- [ ] **5.3** Add transient retry config to `PipelineExecutionConfig`
  - Add to `PipelineExecutionConfig` in `system/configuration/configs.py`:
    ```
    max_transient_retries: int          # 0 = disabled (default for backward compat)
    transient_retry_base_wait: float    # seconds, e.g. 2.0
    transient_retry_max_wait: float     # seconds, e.g. 30.0
    transient_retry_backoff_multiplier: float  # e.g. 2.0
    ```
  - Add defaults in `pipelex/pipelex.toml` (disabled: `max_transient_retries = 0`)
  - Add commented-out overrides in `.pipelex/pipelex.toml` project config (invitation to enable)
  - Config flows through existing path: `get_config().pipelex.pipeline_execution_config`
    which is already passed to `PipelexRunner` and accessible from `PipeRouterProtocol.run()`

- [ ] **5.4** Add transient retry loop to `PipeRouterProtocol.run()`
  - Modify `pipe_run/pipe_router_protocol.py` `run()` method:
    - Wrap `_run_pipe_job()` call in a retry loop
    - Catch `CogtError` where `error_category.is_retryable` is True
    - On retryable error: log attempt number + wait duration + error category, sleep with
      exponential backoff, continue loop
    - On non-retryable error (`CONFIGURATION`, `CONTENT`, `CAPACITY`): fail immediately (no retry)
    - On max retries exhausted: raise the last error as-is (preserve the cause chain)
    - On `PipeRunError` (existing handling): no change, still wraps as `PipeRouterError`
    - `_before_run()` is called once (before the loop), not on each retry
    - `_after_failing_run()` is called once (after all retries exhausted or non-retryable)
  - The retry config comes from `PipelineExecutionConfig` — need to thread it through.
    Options: add to `PipeJob`, or access via `get_config()` directly in the protocol.

- [ ] **5.5** Thread retry config to PipeRouter
  - Decide how `PipeRouterProtocol.run()` accesses `PipelineExecutionConfig`:
    - Option A: Add `execution_config` to `PipeJob` (explicit, but changes the model)
    - Option B: Access via `get_config()` in the protocol (simple, uses existing singleton)
  - Implement the chosen approach

- [ ] **5.6** Tests for Phase 5
  - Unit test: `CogtError` with `TRANSIENT` retries up to max, then raises
  - Unit test: `CogtError` with `CONFIGURATION` fails immediately (no retry)
  - Unit test: `CogtError` with `CONTENT` fails immediately
  - Unit test: `CogtError` with `CAPACITY` fails immediately
  - Unit test: `PipeRunError` (non-CogtError) is unaffected by retry logic
  - Unit test: `max_transient_retries = 0` disables retry (backward compat)
  - Unit test: retry logging includes attempt number, wait duration, error category
  - Unit test: backoff increases with each attempt
  - Verify gateway workers raise with correct category on first failure (no silent retries)
  - Existing worker error handling tests should still pass unchanged

---

## Phase 6: ErrorReport Everywhere

> Extend the structured error reporting from inference-only (`CogtError`) to the full exception hierarchy.
> This eliminates the fragile string-keyed dicts in `agent_output.py` and gives every error path
> a self-describing report.

- [ ] **6.1** Set default `error_category` on uncategorized `CogtError` subclasses
  - These subclasses currently inherit `error_category = None` and produce empty reports when raised
    without an instance-level override:
    - CONFIGURATION: `RoutingProfileLibraryNotFoundError`, `InferenceBackendLibraryNotFoundError`,
      `InferenceBackendLibraryValidationError`, `ModelManagerError`, `ModelDeckNotFoundError`,
      `ModelDeckValidationError`, `RoutingProfileLibraryError`, `InferenceModelSpecError`
    - CONTENT: `LLMPromptSpecError`, `LLMPromptTemplateInputsError`, `LLMPromptParameterError`,
      `PromptImageFactoryError`, `PromptImageFormatError`, `PromptDocumentFactoryError`,
      `ImgGenPromptError`, `ImgGenParameterError`
    - Leave as None (set per-instance by workers): `LLMCompletionError`, `ImgGenGenerationError`,
      `ExtractJobFailureError`, `SearchJobFailureError` — these are correctly dynamic
  - Decide case-by-case for: `ImageContentError`, `CostRegistryError`, `ReportingManagerError`,
    `SdkTypeError`, `ExtractOutputError`, `GeneratedImageError`, `LLMAssignmentError`,
    `InferenceBackendLibraryError`

- [ ] **6.2** Add `error_domain` and `user_action` to key non-CogtError exceptions
  - Add optional class-level `error_domain` field to `PipelexError` (values: "input", "config", "runtime")
  - Update `PipelexError.to_error_report()` to include `error_domain` in the report
  - Set defaults on key exceptions:
    - `PipelineExecutionError`: domain="runtime", user_action="Check pipe_stack to identify which pipe failed"
    - `PipeExecutionError`: domain="runtime"
    - `ValidateBundleError`: domain="input", user_action="Check the validation_errors array for specific issues"
    - `PipelexInterpreterError`: domain="input"
    - `PipelexSetupError`: domain="config"
    - `PipelexConfigError`: domain="config"
    - Service errors (`InferenceSetupRequiredError`, `GatewayTermsNotAcceptedError`, etc.): domain="config"
  - Files to modify: `base_exceptions.py`, `pipeline/exceptions.py`, `pipe_run/exceptions.py`,
    `core/interpreter/exceptions.py`, `system/pipelex_service/exceptions.py`

- [ ] **6.3** Migrate inference-related hints from `AGENT_ERROR_HINTS` into exception classes
  - For each inference error type in `AGENT_ERROR_HINTS`, move the hint string to `user_action` on the class
  - Keep non-inference hints in the dict (FileNotFoundError, JSONDecodeError, etc. — we can't add
    attributes to built-in exceptions)
  - Update `agent_error()` to prefer `report.user_action` over dict lookup (already partially done)

- [ ] **6.4** Migrate `AGENT_ERROR_DOMAINS` into exception classes
  - For each error type in `AGENT_ERROR_DOMAINS`, set the corresponding `error_domain` on the class
  - Update `agent_error()` to prefer `report.error_domain` over dict lookup
  - The dicts become fallback-only for non-PipelexError exceptions

- [ ] **6.5** Add drift-detection test
  - Unit test that discovers all `PipelexError` subclasses caught in agent CLI handlers
    and verifies they either have class-level metadata OR an entry in the fallback dicts
  - This prevents the "new exception added, forgot to update dicts" failure mode

- [ ] **6.6** Tests for Phase 6
  - Test `to_error_report()` on non-CogtError exceptions includes `error_domain`
  - Test that `agent_error()` output for inference errors gets hint from class, not dict
  - Test that `agent_error()` output for non-PipelexError still gets hint from dict fallback
  - Test default categories on previously-uncategorized CogtError subclasses

---

## Phase 7: Temporal Bridge (deferred — belongs on Temporal branch)

> This phase prepares the Temporal integration to use `InferenceErrorCategory` for retry decisions
> and `to_error_report()` for structured error details. It should be implemented on the Temporal
> integration branch where it can be tested end-to-end.
>
> Prerequisites from this branch: Phases 4-6 complete, all exceptions carry structured reports.

- [ ] **7.1** Update `TemporalError.from_message_exception()` to use `error_category.is_retryable`
- [ ] **7.2** Pack `to_error_report()` dict into `ApplicationError` details
- [ ] **7.3** Document that `RetryPolicyConfig.non_retryable_error_types` is a fallback for exceptions without category
- [ ] **7.4** Tests for the Temporal bridge
