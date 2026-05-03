# Worker Error Handling — Phase 6: ErrorReport Everywhere

> Reference: `wip/worker-error-handling-review.md` for the full review of current state.
> Completed phases (0–3) archived in `wip/error-handling-phases-0-3-completed.md`.

---

## Definition of DONE

A phase is done when **all** of the following are true:

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
