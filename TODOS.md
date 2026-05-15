# TODOS — Error Handling, Phase 2: Resilience, Agent Delivery, Broad-Except Hygiene

> **Branch:** `feature/Error-handling-2`
> **Current-state reference:** [wip/error-handling/README.md](wip/error-handling/README.md) and the `track-*.md` docs it links.
> **Prior sweep (completed, archived):** [wip/error-handling/archive-worker-classification-sweep.md](wip/error-handling/archive-worker-classification-sweep.md).
> **Discipline:** every phase runs RED (failing test) → GREEN (minimal code to pass) → REFACTOR (clean up). Run `make agent-check` after every phase; `make agent-test` at each checkpoint.

---

## Why this plan exists

Three priorities drive the next phase of error-handling work, in priority order:

1. **Resilience** — perfect the Temporal integration, while still working thoroughly and efficiently *without* Temporal.
2. **Agent CLI delivers errors in plain markdown** — clear and efficiently usable by agents — with JSON available via an explicit option.
3. **Never catch broad `except Exception`** except at CLI / API boundaries, per the repo's error-handling rules.

The work is sequenced so the **shared foundation lands first**: both the Temporal bridge and the agent markdown renderer draw from `ErrorReport`, which today has no `error_domain` field. Building either consumer before `error_domain` lands means re-touching an incomplete schema. The broad-`except` sweep goes first of all because it is small, independent, and de-risks the classification that the other two priorities consume.

---

## Verification findings (checked against the codebase before planning)

These were verified directly — not taken on faith from prior notes.

- **`error_domain` is genuinely missing.** `ErrorReport` (`pipelex/base_exceptions.py`) has no `error_domain` field; `PipelexError.to_error_report()` returns only `error_type` + `message`. `agent_error()` (`pipelex/cli/agent_cli/commands/agent_output.py`) sources `error_domain` *unconditionally* from the `AGENT_ERROR_DOMAINS` string dict — confirmed by the inline comment "error_domain: always from lookup dict". The string dicts (`AGENT_ERROR_HINTS`, `AGENT_ERROR_DOMAINS`, `RETRYABLE_ERROR_TYPES`) are class-name-keyed and drift-prone.
- **The broad-`except` rule is not satisfied — but the prior framing overstated the danger.** There are broad `except Exception` sites across non-test code. Triaged:
  - **Allowed** — CLI command roots (`pipelex/cli/**`), dev CLI, agent CLI command handlers, async-task / workflow root handlers (`wf_pipe_router.py`, `pipe_run.py`, telemetry exporters). These are the documented exception to the rule.
  - **Broad but re-raises (observe-and-reraise)** — `pipe_abstract.py` (around lines 496, 605) and `llm_worker_abstract.py` (around lines 374, 411) catch to record a tracing/OTel span on the error path, then `raise`. They do **not** swallow. Spirit of the rule (unknown failures must surface) is honored.
  - **Best-effort cleanup** — `teardown()` in `google_llm_worker.py`, `google_img_gen_worker.py`, `gateway_extract_worker.py` (and the gateway search worker) swallow cleanup failures *by design* ("log but don't fail teardown"). These are **not** in the inference/classification path — the prior claim that they "swallow an SDK exception before it's classified" is inaccurate.
  - **Plugin / user-code trust boundary** — `pipe_func.py` (around line 189) wraps an error from a user-supplied registered function into `PipeRunError`. User code can raise anything; a broad catch here is defensible, like a CLI boundary.
  - **Genuinely narrowable** — `pipe_func.py` (around line 196) catches broadly around `working_memory.get_stuff()` when it should catch only the stuff-not-found exception. Other sites in business logic (`func_registry.py`, `working_memory_factory.py`, `model_lists.py`, `model_deck.py`, `output_renderer.py`, `structured_content_composer.py`, `delivery_executor.py`, and similar) need per-site triage.
  - **Conclusion:** Phase 1 is a correctness/hygiene sweep, not an emergency. The genuinely-wrong narrowing set is small; most sites are either allowed or legitimate-but-broad and need an explicit, justified marker rather than a rewrite.
- **`InferenceErrorCategory.is_retryable` already exists** — retry *decisions* (the PipeRouter loop, the Temporal `from_message_exception` bridge) are unblocked today. Only the *payloads/renderers* need the completed `ErrorReport`.
- **PipeRouter has no retry loop** — `PipeRouterProtocol.run()` (`pipelex/pipe_run/pipe_router_protocol.py`) catches only `PipeRunError`. Retry lives inside two gateway workers via `tenacity`.
- **The Temporal bridge is name-based** — `TemporalError.from_message_exception()` (`pipelex/temporal/tprl/temporal_error.py`) uses the static `non_retryable_error_types` config list and never consults `InferenceErrorCategory.is_retryable`; `ApplicationError.details` is empty.

---

## Sequencing

```
Phase 1  Broad-except hygiene sweep        (priority 3 — independent, de-risks classification)
   └─ CHECKPOINT A
Phase 2  error_domain on the error model   (metadata foundation, part 1)
Phase 3  Class-level metadata on exceptions (metadata foundation, part 2)
Phase 4  Retire agent-CLI string dicts      (metadata foundation, part 3)
   └─ CHECKPOINT B  — shared foundation landed
Phase 5  PipeRouter retry loop             (priority 1 — the "works without Temporal" half)
Phase 6  Temporal bridge: category + details (priority 1 — the Temporal half)
   └─ CHECKPOINT C  — resilience landed
Phase 7  Agent CLI markdown delivery        (priority 2)
Phase 8  Full-chain integration coverage    (testing — verifies the above end-to-end)
```

Phases 5–6 (resilience) and Phase 7 (CLI) touch disjoint files and could run in parallel; the order above keeps priority 1 ahead of priority 2 for a sequential single-session pass.

---

## Phase 1 — Broad `except Exception` hygiene sweep

**Goal:** every broad `except Exception` in non-test code is either narrowed to the specific exception(s) actually raised, or — where the broad catch is legitimate (allowed boundary, observe-and-reraise, best-effort cleanup, user-code boundary) — carries an explicit `# noqa: BLE001` with a one-line justification. After this phase, a new unjustified broad catch fails lint.

### RED

- [x] Confirm whether ruff's `BLE001` (`flake8-blind-except`) rule is enabled in the project's ruff config. If not, enable it. Run `make agent-check` and capture the full list of flagged sites — this is the RED baseline (the check fails).
- [x] Triage every flagged non-test site into one of: **allowed boundary**, **observe-and-reraise**, **best-effort cleanup**, **user-code boundary**, **narrowable**. Record the triage table in Running Notes.

### GREEN

- [x] **Narrowable sites** — replace `except Exception` with the specific exception type(s) the call can raise. Start with `pipe_func.py` (the inner catch around `working_memory.get_stuff()` → the stuff-not-found exception). Work through the other business-logic sites identified in triage.
- [x] **Observe-and-reraise sites** (`pipe_abstract.py`, `llm_worker_abstract.py` span-recording catches) — keep the broad catch (telemetry must fire on *every* failure) and add `# noqa: BLE001` with a comment stating it records a span then re-raises. Alternatively restructure with `try/except/else` so success vs error span-ending is explicit. Either way, nothing is swallowed. **Note:** ruff `BLE001` does not flag handlers that re-raise, so these sites need no `noqa` and were left untouched.
- [x] **Best-effort cleanup sites** (`teardown()` async-client close paths) — narrow to the exceptions `aclose()` / `asyncio.run()` can actually raise (`RuntimeError`, connection/transport errors) where determinable; otherwise keep with `# noqa: BLE001` and the existing "log but don't fail teardown" comment.
- [x] **User-code boundary** (`pipe_func.py` outer catch of the registered function) — keep with `# noqa: BLE001` and a comment that registered functions are user code and may raise anything; the wrap into `PipeRunError` is the boundary. **Note:** the outer catch re-raises as `PipeRunError`, so ruff does not flag it; no `noqa` needed.
- [x] **Allowed boundaries** (CLI roots, async-task roots) — confirm each is genuinely at a root; add `# noqa: BLE001` where the rule flags them.
- [x] Run `make agent-check` until clean.

### REFACTOR

- [x] Leave `BLE001` enabled as a permanent guard so future broad catches surface in lint.
- [x] Spot-check that no narrowing changed observable behavior (a previously-caught exception that now propagates) — note any intentional behavior changes in the changelog.

> ### STOP — CHECKPOINT A: Broad-except sweep landed ✅
>
> Update checkboxes, commit, run `make agent-test`. The codebase now satisfies priority 3 and lint guards it. Next session resumes at Phase 2.
>
> **Status:** landed. `make agent-check` clean (ruff + plxt + pyright + mypy). Triage table and decisions recorded in Running Notes below.
>
> **Hand-off context to record in Running Notes:** the triage table, any intentional behavior changes from narrowing, and whether `BLE001` was newly enabled or already on.

---

## Phase 2 — `error_domain` on the error model

**Goal:** `error_domain` becomes a first-class field on the exception hierarchy and on `ErrorReport`, so it no longer depends on the agent-CLI string dict. This is the schema change both downstream consumers (Temporal, CLI markdown) need before they are built.

Reference: [track-metadata-model.md](wip/error-handling/track-metadata-model.md) followups 1.

### RED

- [ ] Write `tests/unit/pipelex/exceptions/test_error_domain.py` asserting:
  - `ErrorDomain` is a `StrEnum` (imported from `pipelex.types`) with values `INPUT`, `CONFIG`, `RUNTIME`.
  - `PipelexError.to_error_report()` carries `error_domain` when the class declares one, and omits it (`None`) otherwise.
  - `ErrorReport.to_dict()` drops `error_domain` when `None` and includes it otherwise.

### GREEN

- [ ] Add `ErrorDomain` `StrEnum` (decide placement — likely `pipelex/base_exceptions.py` or `pipelex/types`-adjacent; ask the user if placement is ambiguous).
- [ ] Add an optional class-level `error_domain: ErrorDomain | None = None` attribute on `PipelexError`.
- [ ] Add `error_domain: str | None = None` to the `ErrorReport` frozen dataclass.
- [ ] Update `PipelexError.to_error_report()` to include `error_domain` from the class attribute.
- [ ] Update `CogtError.to_error_report()` so it forwards `error_domain` too (it overrides the base method).
- [ ] Run `make agent-check`.

### REFACTOR

- [ ] No change to consumers yet — `agent_error()` still reads its dict. Phase 4 flips the precedence. Keeping consumer changes out of this phase keeps the schema change reviewable in isolation.

---

## Phase 3 — Class-level metadata on non-`CogtError` exceptions

**Goal:** the key non-`CogtError` exceptions self-describe `error_domain` and `user_action` at the class level, and the uncategorized `CogtError` subclasses get their `error_category` defaults. After this phase, the metadata lives on the classes — the string dicts become removable in Phase 4.

Reference: [track-metadata-model.md](wip/error-handling/track-metadata-model.md) followups 2–3.

### RED

- [ ] Write `tests/unit/pipelex/exceptions/test_class_level_metadata.py` asserting each targeted exception's `to_error_report()` carries the expected `error_domain` and `user_action`:
  - `PipelineExecutionError`, `PipeExecutionError` (`pipelex/pipeline/exceptions.py`) → `error_domain=RUNTIME`.
  - `ValidateBundleError` (`pipelex/pipeline/validate_bundle.py`) → `error_domain=INPUT`.
  - `PipelexInterpreterError` (`pipelex/core/interpreter/exceptions.py`) → `error_domain=INPUT`.
  - `PipelexSetupError`, `PipelexConfigError` (`pipelex/base_exceptions.py`) → `error_domain=CONFIG`.
  - Service errors (`pipelex/system/pipelex_service/exceptions.py`) → `error_domain=CONFIG`.
- [ ] Add tests asserting the previously-uncategorized `CogtError` subclasses now report a non-`None` `error_category` (prompt-spec / prompt-template / prompt-parameter / prompt-image / prompt-document families → `CONTENT`).

### GREEN

- [ ] Set class-level `error_domain` (and `user_action` where the track doc proposes concrete text) on the non-`CogtError` exceptions listed above. Use the user-action wording from [track-metadata-model.md](wip/error-handling/track-metadata-model.md) followup 2.
- [ ] Set `error_category` defaults on the uncategorized `CogtError` subclasses (the prompt-* families → `CONTENT`). Decide case-by-case for `ImageContentError`, `CostRegistryError`, `ReportingManagerError`, `SdkTypeError`, `ExtractOutputError`, `GeneratedImageError`, `LLMAssignmentError`, `InferenceBackendLibraryError` — record each decision in Running Notes. Leave the four per-instance "outcome" exceptions (`LLMCompletionError`, `ImgGenGenerationError`, `ExtractJobFailureError`, `SearchJobFailureError`) uncategorized at the class level — workers set them per-instance.
- [ ] Run `make agent-check`.

### REFACTOR

- [ ] Scan for any other frequently-raised `PipelexError` subclass that obviously belongs to one domain and is cheap to annotate while the context is fresh — but do not chase exhaustiveness; the drift test in Phase 4 will surface gaps.

---

## Phase 4 — Retire the agent-CLI string dicts + drift detection

**Goal:** `agent_error()` reads class-level metadata first and falls back to the string dicts *only* for non-`PipelexError` built-ins (`FileNotFoundError`, `JSONDecodeError`, `ValidationError`, …) that cannot carry class attributes. A drift-detection test guards the remaining dict entries.

Reference: [track-metadata-model.md](wip/error-handling/track-metadata-model.md) followups 4–6, [track-testing.md](wip/error-handling/track-testing.md) followup 2.

### RED

- [ ] Write `tests/unit/pipelex/cli/agent_cli/test_agent_output_drift.py`:
  - Every key in `AGENT_ERROR_HINTS` / `AGENT_ERROR_DOMAINS` / `RETRYABLE_ERROR_TYPES` resolves to a real exception class name (catches stale entries after a rename/delete).
  - Every `PipelexError` subclass either declares class-level `error_domain` + `user_action`, or appears in the fallback dicts. (Walk `PipelexError.__subclasses__()` recursively.)
- [ ] Write tests asserting `agent_error()` prefers `report.error_domain` / `report.user_action` over the dict when the cause is a `PipelexError`, and still falls back to the dict for a built-in exception type.

### GREEN

- [ ] In `agent_output.py`, change `agent_error()` so `error_domain` and `hint` come from `cause.to_error_report()` first; the dicts are consulted only when the report has no value (i.e. non-`PipelexError` causes).
- [ ] Remove the `AGENT_ERROR_HINTS` / `AGENT_ERROR_DOMAINS` entries that key on `PipelexError` subclasses (now redundant — metadata is on the classes). Keep only built-in / third-party exception entries.
- [ ] Run `make agent-check`.

### REFACTOR

- [ ] Add a short comment at the dict definitions stating they are now built-ins-only fallbacks and that `PipelexError` subclasses must carry class-level metadata (guarded by the drift test).
- [ ] Confirm `RETRYABLE_ERROR_TYPES` is still needed only for non-`CogtError` causes; trim if the report's `retryable` now covers a former entry.

> ### STOP — CHECKPOINT B: Shared metadata foundation landed
>
> Update checkboxes, commit, run `make agent-test`. `ErrorReport` is now complete (`error_domain` included) and the metadata lives on the exception classes, drift-guarded. Both remaining priorities can now build on a stable schema.
>
> **Hand-off context to record in Running Notes:** the case-by-case `error_category` decisions from Phase 3, which dict entries survived as built-ins-only, and any `PipelexError` subclass the drift test flagged as still needing metadata.

---

## Phase 5 — PipeRouter retry loop (resilience without Temporal)

**Goal:** `PipeRouter` retries `InferenceErrorCategory.TRANSIENT` failures with exponential backoff, driven by config, disabled by default. This is the application-level resilience layer that must work when Temporal is absent. Retry logic moves out of the two gateway workers into the dispatch layer.

Reference: [track-retry-and-resilience.md](wip/error-handling/track-retry-and-resilience.md) followups 1–6.

### RED

- [ ] Write `tests/unit/pipelex/pipe_run/test_pipe_router_retry.py` asserting:
  - A `CogtError` with `error_category=TRANSIENT` retries up to `max_transient_retries`, then re-raises the last error (cause chain preserved).
  - A `CogtError` with `CONFIGURATION` / `CONTENT` / `CAPACITY` / `UNKNOWN` fails immediately (no retry).
  - A `PipeRunError` (non-`CogtError`) is unaffected and still wraps as `PipeRouterError`.
  - `max_transient_retries = 0` disables retry entirely (backward compatibility).
  - Backoff wait increases each attempt; the retry log line includes attempt number, wait duration, and error category.
  - `_before_run()` runs once before the loop; `_after_failing_run()` runs once after retries are exhausted or on a non-retryable error.

### GREEN

- [ ] Add retry config fields to `PipelineExecutionConfig` (`pipelex/system/configuration/configs.py`): `max_transient_retries: int`, `transient_retry_base_wait: float`, `transient_retry_max_wait: float`, `transient_retry_backoff_multiplier: float`. Per project rules: no defaults in the class body — put defaults in `pipelex/pipelex.toml` with `max_transient_retries = 0`; add commented-out overrides in `.pipelex/pipelex.toml`.
- [ ] Add the retry loop to `PipeRouterProtocol.run()` (`pipelex/pipe_run/pipe_router_protocol.py`): wrap `_run_pipe_job()`, catch `CogtError` where `error_category is not None and error_category.is_retryable`, sleep with exponential backoff, continue; re-raise on exhaustion; non-retryable categories fail immediately; the existing `PipeRunError` path is unchanged.
- [ ] Thread the retry config via `get_config()` inside the protocol (Option B in the track doc) — consistent with how `pipeline_execution_config` is already accessed.
- [ ] Run `make tb` (boot sequence — verifies the config model and the three `pipelex.toml` files agree). Run `make agent-check`.

### REFACTOR

- [ ] Remove `tenacity` retry from the gateway extract and search workers (`_make_retryer`, `_is_retryable_portkey_error`, `_log_retry`, the `async for attempt` wrapper). Confirm errors still propagate with the correct `InferenceErrorCategory` on first failure.
- [ ] Remove `TenacityConfig` from `pipelex/cogt/config_cogt.py` and its `pipelex.toml` entries, **only if** nothing else uses it (`pipelex/plugins/fal/fal_poller.py` still uses tenacity for polling and `log_retry` from `tenacity_utils.py` — verify before removing the `tenacity` dependency or `tenacity_utils.py`).
- [ ] Add a one-line code comment at the `instructor` `max_retries` call sites noting it retries schema-validation, not transport — out of scope for router retry.

---

## Phase 6 — Temporal bridge: category-aware retry + details payload

**Goal:** Temporal's retry decision flows from `InferenceErrorCategory.is_retryable` (the same signal as the PipeRouter loop), and `ApplicationError.details` carries the full `ErrorReport` across the activity → workflow boundary.

Reference: [track-temporal-integration.md](wip/error-handling/track-temporal-integration.md) followups 1–4.

### RED

- [ ] Write `tests/unit/pipelex/temporal/test_temporal_error_bridge.py` asserting:
  - `from_message_exception()` on a `CogtError` with `TRANSIENT` produces `non_retryable=False`.
  - …with `CONFIGURATION` / `CONTENT` / `CAPACITY` / `UNKNOWN` produces `non_retryable=True`.
  - …on a non-`CogtError` `PipelexError` falls back to the `non_retryable_error_types` name list.
  - …on a `CogtError` with `error_category=None` falls back to the name list (no crash).
  - `ApplicationError.details` round-trips through Temporal serialization with all `ErrorReport` fields intact.
  - Log severity (critical / error) matches the retry decision on both the `from_message_exception` and `from_app_error` paths.

### GREEN

- [ ] In `pipelex/temporal/tprl/temporal_error.py`, `from_message_exception()`: when `exc` is a `CogtError` with a non-`None` `error_category`, derive retryability from `error_category.is_retryable` and set `non_retryable = not is_retryable` on the `ApplicationError`. When the category is `None`, keep the existing `non_retryable_error_types` lookup.
- [ ] Pack `exc.to_error_report().to_dict()` into `ApplicationError.details`. `from_app_error()` extracts the details payload and surfaces it back as fields on the resulting `TemporalError` so the structured data survives the round-trip.
- [ ] Update the docstrings of `RetryPolicyConfig.non_retryable_error_types` and `non_retryable_error_types_extra` (`pipelex/temporal/config_temporal.py`) to state that the name list is a *fallback* for category-less exceptions and an override mechanism — category decides retryability for `CogtError`.
- [ ] Run `make agent-check`.

### REFACTOR

- [ ] Check the in-process PipeRouter retry (Phase 5) and the Temporal retry agree on what "transient" means — both consult `is_retryable`. Note in Running Notes how the two layers compose (Temporal sees a non-retryable error only after the router exhausted its retries, or for non-`TRANSIENT` categories).

> ### STOP — CHECKPOINT C: Resilience landed
>
> Update checkboxes, commit, run `make agent-test`. Run the Temporal integration tests per `_tprl/CLAUDE.md` (`--temporal-server` options). Priority 1 is complete: Pipelex retries transients standalone and across the Temporal boundary from one shared signal.
>
> **Hand-off context to record in Running Notes:** whether the gateway-worker tenacity removal changed any timing-sensitive test, the final disposition of the `tenacity` dependency, and how the two retry layers compose.

---

## Phase 7 — Agent CLI markdown delivery

**Goal:** the agent CLI emits plain markdown by default for `run` / `validate` / `init` and for the error path; JSON is available via `--format json`. The eleven near-identical Rich handlers in `error_handlers.py` collapse onto one panel helper.

Reference: [track-cli-delivery.md](wip/error-handling/track-cli-delivery.md) followups 1–6.

### RED

- [ ] Write tests under `tests/unit/pipelex/cli/agent_cli/` (or integration where the CLI harness fits) asserting:
  - `run` / `validate` with no `--format` produce markdown to stdout.
  - `run --format json` / `validate --format json` produce valid JSON to stdout.
  - An error with no `--format` produces markdown to stderr; with `--format json`, JSON to stderr.
  - The `inputs` command is unaffected (always JSON per the `agent_cli/CLAUDE.md` contract).

### GREEN

- [ ] Add `agent_error_markdown(message, error_type, cause, **extra)` to `agent_output.py` — markdown to stderr (error-type heading, message body, hint as a tip callout, `error_source` as a code block), still `raise typer.Exit(1)`.
- [ ] Introduce a format-aware error dispatch (explicit `format` argument or a `ContextVar`). Keep JSON as the default when format is unknown (errors during init, before the format option is parsed — see `agent_cli_factory.py`).
- [ ] Add `--format markdown|json` to `run`, `validate`, `init` (`match/case` on `CliOutputFormat`, default `MARKDOWN`), mirroring `models_cmd.py`. Add the markdown renderers: `_format_run_markdown`, `_format_validate_markdown`, and the `init` confirmation. Files: `commands/run/{pipe,bundle,method}_cmd.py`, `commands/validate/{pipe,bundle,method}_cmd.py`, `commands/init_cmd.py`.
- [ ] Run `make agent-check`.

### REFACTOR

- [ ] Extract `display_error_panel(console, *, title, fields, error_message, tip, links)` in `pipelex/cli/error_handlers.py`; rewrite each `handle_*` to build its field list and call the helper. Exception-specific logic stays in the handler; the panel shape lives in one place.
- [ ] Update `pipelex/cli/agent_cli/CLAUDE.md`: markdown is the default for `run` / `validate` / `init` / `models` / `doctor` / `check-model`; `--format json` available on all of them; errors respect the same option; document each command's markdown structure.

---

## Phase 8 — Full-chain integration coverage

**Goal:** prove the whole pipeline — worker error → pipe operators → `PipelineExecutionError` → `agent_error()` → stderr — produces correct structured output, in both JSON and markdown. This catches wiring regressions no per-worker test can.

Reference: [track-testing.md](wip/error-handling/track-testing.md) followups 1 and 3.

### RED

- [ ] Add a full-chain test under `tests/integration/pipelex/cli/agent_cli/`: a minimal pipeline where one pipe fails with a deterministic worker error (mocked `LLMCompletionError`, `error_category=TRANSIENT`, model + provider set). Run `pipelex-agent run` via the CLI harness, capture stderr.
  - **JSON path:** assert the JSON has `error: true`, `error_type`, `message`, `error_category: "transient"`, `retryable: true`, `error_domain`, `model`, `provider`, and an `error_source` chain in order (worker → pipe operator → router → runner → CLI).
  - **Markdown path:** assert the markdown contains the error type, message, hint, and source frames.
- [ ] Add a snapshot test for one or two representative Rich error outputs (`error_handlers.py`) to confirm the Phase 7 panel-helper refactor introduced no rendering drift.

### GREEN

- [ ] Fix any wiring gap the full-chain test exposes (a wrapper exception dropping `error_category`, `agent_error()` not forwarding a field, `_build_error_source()` degrading the chain, an enum serialized as a Python repr instead of its `StrEnum` value).

### REFACTOR

- [ ] If the full-chain test reveals a recurring forwarding bug, fix it at the source (the wrapper exception) rather than patching the renderer.

> ### STOP — FINAL: All three priorities landed
>
> Run `make agent-check` and `make agent-test`. Run the Temporal integration suite. Update [wip/error-handling/README.md](wip/error-handling/README.md) — flip the CLI delivery, retry & resilience, Temporal integration, and testing tracks to their new status. Archive this `TODOS.md` into `wip/error-handling/` alongside the prior sweep.

---

## Out of scope

- **Extract / Classify / Render decomposition** ([track-extract-classify-render.md](wip/error-handling/track-extract-classify-render.md)) — unblocked but a separate, large refactor. Do not pull forward.
- **`FileNotFoundError` category/action mismatch** ([wip/error-handling/deferred-items/file-not-found-category-mismatch.md](wip/error-handling/deferred-items/file-not-found-category-mismatch.md)) — resolve only when a concrete consumer benefits.

---

## Running Notes

_Append decisions, surprises, and hand-off context here as each phase lands. Keep checkpoint hand-off context in the matching CHECKPOINT block above and the detail here._

### Phase 1 — Broad-except hygiene sweep (landed)

**`BLE001` status:** was *already present in ruff config but disabled* — it sat in the `# TODO: stop ignoring these rules` block of `pyproject.toml`'s ruff `ignore` list. Phase 1 removed it from that list, so it is now an active, permanent lint guard.

**Scope:** `BLE001` flags broad catches repo-wide, including test code. Phase 1 is scoped to non-test code, so `tests/**/*.py` was added to ruff `per-file-ignores` for `BLE001` (7 test sites: defensive fixtures and failure-mode assertions). Test-code broad catches are out of scope.

**Key surprise — ruff's re-raise exemption:** `BLE001` does **not** flag a broad `except Exception` whose handler re-raises (the caught or a wrapped exception). Of the 128 `except Exception` statements in `pipelex/`, ruff flagged only the **96** that *swallow*. This means the plan's "observe-and-reraise" sites (`pipe_abstract.py`, `llm_worker_abstract.py` span-recording catches) and the `pipe_func.py` *outer* user-code-boundary catch (wraps into `PipeRunError`) were never flagged and needed **no `noqa`** — the rule already permits them. Net work was: 3 narrowed + 93 `noqa`.

**Triage table (96 flagged, swallowing sites):**

| Category | Sites | Disposition |
| --- | --- | --- |
| Narrowable | `pipe_func.py:196` (inner `get_stuff` catch), `func_registry.py:319` (`get_type_hints`), `model_deck.py:707` (`load_toml_from_path_if_exists`) | Narrowed — see below |
| Allowed boundary | agent-CLI command handlers (`cli/agent_cli/commands/**`), CLI command code (`cli/commands/**`), dev CLI (`cli/dev_cli/**`), Temporal workflow/activity roots (`wf_pipe_router.py`, `act_assemble_graph.py`), async-task root (`pipe_run.py`), telemetry exporters/managers (`system/telemetry/**`) | `# noqa: BLE001` |
| Best-effort cleanup | `teardown()` async-client close paths in `gateway_extract_worker.py`, `google_img_gen_worker.py`, `google_llm_worker.py`; `__del__` in `ndjson_event_log.py` | `# noqa: BLE001` (kept "log but don't fail teardown" comments; teardown `aclose()` raises too broad a set to narrow safely) |
| Defensive utility / fallback | `json_utils.py` (×3, kajson serialization fallback), `string_utils.py:58` (arbitrary `__str__`), `class_utils.py:97` (schema-compare fallback), `output_renderer.py` (×2, placeholder render), `structured_content_composer.py:107` (diagnostic string builder), `working_memory_factory.py:190` & `dry_run.py:187` (dry-run mock fallback), `delivery_executor.py` (×2, best-effort graph/file rendering), `library_manager.py:1177` (`model_rebuild`) | `# noqa: BLE001` — broad catch is the intended design (must never crash the surrounding flow); narrowing would risk silently re-propagating |

**Narrowing decisions (3 sites — no observable behavior change intended):**

- `pipe_func.py:196` — inner catch around `working_memory.get_stuff()` narrowed to `WorkingMemoryStuffNotFoundError` (the only exception `get_stuff()` raises).
- `func_registry.py:319` — catch around `typing.get_type_hints()` narrowed to `(NameError, TypeError)`, matching the already-narrow `(ValueError, TypeError)` catch 18 lines above it.
- `model_deck.py:707` — catch around `load_toml_from_path_if_exists()` narrowed to `(TomlError, OSError)` (TOML parse failure / unreadable file), matching the method's docstring "if the file can't be read or parsed".

`noqa` directives for the 93 legitimate sites were applied with `ruff check --select BLE001 --add-noqa`. Most sites already carry an adjacent explanatory comment that serves as the justification.
