# Worker Error Handling — Phase 7: Temporal Bridge (deferred — belongs on Temporal branch)

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
