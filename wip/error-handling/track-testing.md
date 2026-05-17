# Track — Testing

## What this track is

The test coverage that proves the error-handling system behaves as specified end-to-end, and the drift-detection that keeps the metadata-on-classes contract honest as the codebase grows.

Coverage is landed at every level: per-worker classification, the classification helpers, the `instructor` unwrap, `to_error_report()` shape, the full-chain runner→CLI→JSON snapshot, the agent-CLI dict drift-detection, and the Rich-panel snapshots.

## Current state

### Inference layer

- **Per-worker classification** — test modules under `tests/unit/pipelex/plugins/<provider>/` mock the SDK to raise each typed exception and assert the resulting domain exception has the expected `error_category`, `user_action`, `provider_metadata`, and model descriptor. Each LLM worker also has a raw-SDK-transport-error case pinning the post-`instructor`-confinement behavior (a transport error propagates raw and classifies correctly).
- **Classification helpers** — parametrized tests in `tests/unit/pipelex/cogt/inference/` cover the message-pattern discriminators (`is_quota_exhaustion_*`, `is_content_policy_violation`) for every provider.
- **`instructor` unwrap** — each provider has one end-to-end test against real `instructor.from_<provider>(...)` (e.g. `tests/unit/pipelex/plugins/anthropic/test_anthropic_worker_object_error_handling.py`) so the unwrap can't silently rot if `instructor`'s wrapping shape changes; the remaining categorization cases use the synthetic `wrap_in_instructor_retry` helper in `tests/helpers/instructor_test_utils.py`.
- **`instructor` schema-retry helper** — `tests/unit/pipelex/cogt/llm/test_instructor_retry.py` asserts a transport-style exception is not retried (the predicate excludes it) and a `pydantic.ValidationError` is retried up to `stop_after_attempt`.
- **Transport retry** — `tests/unit/pipelex/cogt/inference/test_transport_retry.py` covers the `tenacity`-based SDK-less wrapper; `tests/unit/pipelex/plugins/test_transport_retry_wiring.py` asserts each SDK client factory builds its client with the configured `transport_max_retries`.

### Reporting and serialization

- **`to_error_report()` shape** — unit tests in `tests/unit/pipelex/cogt/exceptions/` confirm the report includes the right fields per `CogtError` subclass, that `to_dict()` drops `None` fields, and that JSON serialization round-trips cleanly.

### Full-chain and delivery

- **Full-chain runner→CLI→JSON snapshot** — `tests/integration/pipelex/cli/agent_cli/test_run_error_chain.py` builds a minimal pipeline where one pipe fails with a deterministic worker error, runs the agent CLI, and asserts the emitted JSON carries `error_category`, `retryable`, `model`, `provider`, and an `error_source` chain in the expected order (worker → pipe operator → router → runner → CLI). This is the test that catches a wrapper exception silently swallowing `error_category`, `agent_error()` regressing on forwarded fields, or `error_category` arriving as a Python repr instead of the StrEnum value.
- **Drift-detection for `agent_output.py` dicts** — `tests/unit/pipelex/cli/test_agent_output_drift.py` walks the `PipelexError` hierarchy and asserts every key in `AGENT_ERROR_HINTS` / `AGENT_ERROR_DOMAINS` / `RETRYABLE_ERROR_TYPES` corresponds to a real exception class, and that a `PipelexError` subclass is either covered by class-level metadata or has a fallback dict entry. This closes the "silent breakage when classes are renamed" failure mode.
- **Rich-panel snapshots** — `tests/unit/pipelex/cli/test_error_handlers_snapshot.py` snapshots representative `display_error_panel` outputs so the shared-helper refactor can't drift the rendered layout.

### Temporal boundary

- `tests/unit/pipelex/temporal/test_temporal_error_bridge.py` pins `from_message_exception`'s retry-flag derivation from `InferenceErrorCategory`; `tests/integration/pipelex/temporal/test_activity_error_boundary.py` drives a real `CogtError` from a real activity through a real worker and asserts what `from_app_error` receives on the workflow side.

## Open gaps

None load-bearing. Two optional refinements are recorded in [deferred-items/](deferred-items/): the Temporal integration test verifies the converted payload rather than Temporal's retry-engine behavior, and a couple of search/extract worker tests omit non-status `APIError` subtypes. Both are deliberate scope choices.

## Related tracks

- [track-metadata-model.md](track-metadata-model.md) — the drift-detection test enforces the class-level metadata contract.
- [track-cli-delivery.md](track-cli-delivery.md) — the full-chain snapshot and Rich-panel snapshots exercise the delivery paths.
- [track-worker-classification.md](track-worker-classification.md) — the shared `instructor` test utilities live in `tests/helpers/instructor_test_utils.py`.
- [track-temporal-integration.md](track-temporal-integration.md) — the activity → workflow boundary tests.
