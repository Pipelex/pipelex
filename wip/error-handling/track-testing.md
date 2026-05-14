# Track — Testing

## What this track is

The test coverage that proves the error-handling system actually behaves as specified end-to-end, and the drift-detection that keeps the metadata-on-classes contract honest as the codebase grows.

Today **worker-level classification tests are comprehensive** (many parametrized tests per worker exercising rate-limit, quota, content-policy, auth, timeout, connection paths). Two gaps remain at higher levels: there is no full-chain runner→CLI→JSON snapshot, and there is no automated check that every `PipelexError` subclass referenced in the agent CLI dicts is either still named correctly or has class-level metadata.

## Current state

- **Inference layer** — per-worker test modules under `tests/unit/pipelex/plugins/<provider>/` mock the SDK to raise each typed exception and assert the resulting domain exception has the expected `error_category`, `user_action`, and model descriptor.
- **Classification helpers** — parametrized tests in `tests/unit/pipelex/cogt/inference/` cover the message-pattern discriminators (`is_quota_exhaustion_*`, `is_content_policy_violation`) for every provider.
- **Anthropic instructor unwrap** — `tests/unit/pipelex/plugins/anthropic/test_anthropic_worker_object_error_handling.py::test_real_instructor_wraps_rate_limit_and_fix_unwraps_correctly` locks in the assumption against real `instructor.from_anthropic(...)` so it can't silently rot if `instructor`'s wrapping shape changes.
- **`to_error_report()` shape** — unit tests in `tests/unit/pipelex/cogt/exceptions/` confirm the report includes the right fields per `CogtError` subclass, that `to_dict()` drops `None` fields, and that JSON serialization round-trips cleanly.

## Open gaps

### No full-chain runner→CLI→JSON snapshot

The inference layer is well-covered in isolation, but nothing asserts that the **whole pipeline** — pipeline failure with a known worker error → wrapped through pipe operators → wrapped through `PipelineExecutionError` → consumed by `agent_error()` → printed to stderr — produces JSON with the expected `error_category`, `retryable`, `model`, `provider`, `error_source` fields.

This is the test that would catch:

- A new wrapper exception silently swallowing `error_category` on the way up.
- `agent_error()` regressing on which fields it forwards.
- `_build_error_source()` producing a degraded chain.
- `error_category` arriving in the JSON as a Python repr instead of the StrEnum value.

### No drift-detection for `agent_output.py` dicts

`AGENT_ERROR_HINTS`, `AGENT_ERROR_DOMAINS`, and `RETRYABLE_ERROR_TYPES` are string-keyed by exception class name (`pipelex/cli/agent_cli/commands/agent_output.py`). Renaming an exception silently breaks the lookup; adding a new exception silently leaves agents without a hint or domain. There is no test that ensures the dict entries refer to real classes or that newly-added `PipelexError` subclasses have either an entry in the fallback dict or class-level metadata.

## Followups

### 1. Full-chain integration snapshot

Add a test (likely under `tests/integration/pipelex/cli/agent_cli/`) that:

- Builds a minimal pipeline where one pipe will fail with a deterministic worker error (e.g. a mocked `LLMCompletionError` with `error_category=TRANSIENT`, model + provider set).
- Runs `pipelex-agent run` via the CLI test harness (or invokes the agent CLI command function directly).
- Captures stderr and asserts the JSON contains: `error: true`, `error_type`, `message`, `error_category: "transient"`, `retryable: true`, `model`, `provider`, `error_source` with the expected frames in order (worker → pipe operator → router → runner → CLI).

One or two scenarios is enough; the goal is to catch wiring regressions, not to exhaustively cover every combination.

### 2. Drift-detection unit test for `agent_output.py`

A test that:

- Discovers all `PipelexError` subclasses caught in the agent CLI handlers (parse imports from `agent_cli_factory.py` and the command files, or simply walk `PipelexError.__subclasses__()` recursively and filter).
- For each, asserts that **either** the class has class-level `error_domain` / `user_action` (once those are added — see [track-metadata-model.md](track-metadata-model.md)) **or** there is a corresponding entry in `AGENT_ERROR_HINTS` and `AGENT_ERROR_DOMAINS`.
- Inverse check: every key in `AGENT_ERROR_HINTS` / `AGENT_ERROR_DOMAINS` / `RETRYABLE_ERROR_TYPES` corresponds to a real exception class name (catches stale dict entries when a class is renamed or deleted).

This test is what closes the "silent breakage when classes are renamed" failure mode. It should sit next to `agent_output.py` (e.g. `tests/unit/pipelex/cli/agent_cli/test_agent_output_drift.py`).

### 3. Snapshot tests for representative Rich error output

Once the Rich panel helper is extracted (see [track-cli-delivery.md](track-cli-delivery.md)), snapshot one or two of the eleven handler outputs to confirm no rendering drift during the refactor. These are not load-bearing for production correctness; they protect the refactor.

### 4. Shared `instructor` test utilities

When porting the `instructor`-unwrap fix to OpenAI Completions, OpenAI Responses, Mistral, and Google (see [track-worker-classification.md](track-worker-classification.md)), lift the shared test helpers from the Anthropic file into `tests/helpers/instructor_test_utils.py`:

- `_wrap_in_instructor_retry(sdk_exc, *, include_failed_attempts=True)`.
- `_DummySchema(BaseModel)`.
- A `_make_llm_job(mocker)` skeleton.

These reduce per-worker test boilerplate and ensure the wrapping factory matches what real `instructor` produces.

## Related tracks

- [track-metadata-model.md](track-metadata-model.md) — drift-detection test depends on the class-level metadata story being landed (or at least on the agreed contract).
- [track-cli-delivery.md](track-cli-delivery.md) — full-chain snapshot exercises the agent JSON path; once markdown-default lands, mirror the snapshot for markdown.
- [track-worker-classification.md](track-worker-classification.md) — shared `instructor` test utilities live here.
- [track-temporal-integration.md](track-temporal-integration.md) — once category-aware Temporal retry lands, a parallel full-chain test should exercise the activity → workflow boundary.
