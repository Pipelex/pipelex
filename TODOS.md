# TODOS — Error Handling, Phase 2: Resilience, Agent Delivery, Broad-Except Hygiene

> **Branch:** `feature/Error-handling-2`
> **Current-state reference:** [wip/error-handling/README.md](wip/error-handling/README.md) and the `track-*.md` docs it links.
> **Prior sweep (completed, archived):** [wip/error-handling/archive-worker-classification-sweep.md](wip/error-handling/archive-worker-classification-sweep.md).
> **Discipline:** every phase runs RED (failing test) → GREEN (minimal code to pass) → REFACTOR (clean up). Run `make agent-check` after every phase; `make agent-test` at each checkpoint.

---

## ▶ Start here — cold-start status

**This plan is built for cold-start handoff: one phase per session.** Phases 1, 1.5, 2, 3, 4, 5, 5.5, 6, 7 are **landed and committed** (through CHECKPOINT E — see the checkpoint blocks and Running Notes for what shipped). The plan was **revised 2026-05-15** to make the "resilience without Temporal" strategy explicit: Phase 5.5 (bounded fan-out concurrency) was added as a coupled pillar beside Phase 5, the HTTP-status mapping was folded into Phase 7, and two coherence decisions were flagged in the Phase 5 section.

**Next phase: Phase 8.** (Priority 1 — resilience — and priority 2 — error delivery — are both complete; Phase 8 is the full-chain integration coverage that verifies the whole pipeline end-to-end.)

**How to run a phase from a cold start:**

1. Read this section, then "Why this plan exists", "Verification findings", "Sequencing", then the target phase section in full.
2. Read the `track-*.md` doc the phase references (under `wip/error-handling/`) — that is the verified current-state ground.
3. Skim the Running Notes at the bottom for prior per-phase decisions.
4. Work the phase RED → GREEN → REFACTOR. Run `make agent-check` after each step.
5. At the phase's CHECKPOINT: fill in the **Status** line, record hand-off context in Running Notes, commit, run `make agent-test`, then **stop**. The next phase is a fresh session.

Each phase from 5 onward has its own checkpoint (C, C.5, D, E, FINAL) so no single session carries more than one phase of context.

---

## Why this plan exists

Three priorities drive the next phase of error-handling work, in priority order:

1. **Resilience** — perfect the Temporal integration, while still working thoroughly and efficiently *without* Temporal. "Without Temporal" has **two pillars**: **bounded retry** of transient failures (Phase 5), and **bounded fan-out concurrency** (Phase 5.5) so a large workload — e.g. one pipe over 1,000 documents — degrades gracefully instead of overwhelming asyncio / memory / provider rate limits. Durable crash-survival is explicitly *not* attempted standalone — that is the Temporal pitch, and the standalone path should *advertise* it when limits are hit, not fake it.
2. **Errors surface cleanly on every delivery surface** — the agent CLI emits plain markdown, clear and efficiently usable by agents, with JSON via an explicit option; and `ErrorReport` carries a documented `error_domain` → HTTP-status mapping so any downstream API (relay, back-office) renders it without reinventing the contract.
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
- **PipeRouter has no retry loop** — `PipeRouterProtocol.run()` (`pipelex/pipe_run/pipe_router_protocol.py`) catches only `PipeRunError`. Retry lives inside two gateway workers via `tenacity` — vibe-coded, inconsistent (`gateway_extract_worker` retries 500s/timeouts; `gateway_search_worker` retries almost nothing) and with an absurd `max_retries = 50` default.
- **Fan-out is unbounded** — `PipeBatch` (`pipelex/pipe_controllers/batch/pipe_batch.py`) and `PipeParallel` (`pipelex/pipe_controllers/parallel/pipe_parallel.py`) both end in a plain `asyncio.gather(*tasks)` over *all* branches. A pipe run over N items spawns N coroutines, N deep-copied working memories, and N simultaneous inference calls at once. There is **no semaphore, no chunk size, no `max_concurrency` config** anywhere — the asymmetry is concrete: the Temporal path already has task-queue rate limiting, the standalone path has none.
- **The Temporal bridge is name-based** — `TemporalError.from_message_exception()` (`pipelex/temporal/tprl/temporal_error.py`) uses the static `non_retryable_error_types` config list and never consults `InferenceErrorCategory.is_retryable`; `ApplicationError.details` is empty.

---

## Sequencing

```
Phase 1   Broad-except hygiene sweep       (priority 3 — independent, de-risks classification)
   └─    A
Phase 1.5 Second-pass narrowing of catches (priority 3 — narrows what Phase 1 noqa'd, finishes the sweep)
   └─ CHECKPOINT A.5
Phase 2   error_domain on the error model  (metadata foundation, part 1)
Phase 3  Class-level metadata on exceptions (metadata foundation, part 2)
Phase 4  Retire agent-CLI string dicts      (metadata foundation, part 3)
   └─ CHECKPOINT B  — shared foundation landed
Phase 5   PipeRouter retry loop            (priority 1 — resilience without Temporal, pillar A)
   └─ CHECKPOINT C
Phase 5.5 Bounded fan-out concurrency       (priority 1 — resilience without Temporal, pillar B)
   └─ CHECKPOINT C.5  — resilience-without-Temporal complete
Phase 6   Temporal bridge: category + details (priority 1 — the Temporal half)
   └─ CHECKPOINT D  — resilience landed
Phase 7   Error delivery: CLI markdown + HTTP mapping (priority 2)
   └─ CHECKPOINT E
Phase 8   Full-chain integration coverage   (testing — verifies the above end-to-end)
   └─ FINAL
```

Phases 5 and 5.5 are a **coupled pair** — both are "resilience without Temporal". Retry without bounded concurrency amplifies a thundering herd (retrying N failed calls = N more calls), so land both before exercising retry at scale; 5.5 may even precede 5. Phases 5–6 (resilience) and Phase 7 (delivery) touch disjoint files and could run in parallel; the order above keeps priority 1 ahead of priority 2 for a sequential single-session pass.

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
> Update checkboxes, commit, run `make agent-test`. The codebase now satisfies priority 3 and lint guards it. Next session resumes at Phase 1.5.
>
> **Status:** landed. `make agent-check` clean (ruff + plxt + pyright + mypy). Triage table and decisions recorded in Running Notes below. Phase 1 was deliberately conservative — it parked 93 catches behind `# noqa: BLE001` so the lint guard could land fast; Phase 1.5 narrows the ones that can be narrowed.
>
> **Hand-off context to record in Running Notes:** the triage table, any intentional behavior changes from narrowing, and whether `BLE001` was newly enabled or already on.

---

## Phase 1.5 — Second-pass narrowing of the `noqa: BLE001` sites

**Goal:** Phase 1 enabled `BLE001` and parked 93 broad catches behind `# noqa: BLE001` so the lint guard could land fast. That was deliberately conservative — several of those catches *can* be narrowed to the exception(s) the guarded call actually raises, and a few silently swallow. Phase 1.5 revisits every `noqa: BLE001` site, narrows each catch whose raised exceptions are knowable, restructures the silent-swallow sites, and leaves a `# noqa` only where the broad catch is genuinely correct (true CLI / agent command roots, telemetry that must never break the app, `__del__` at interpreter shutdown). Special attention to the `# TODO: wip - do not catch all exceptions` markers.

After this phase every surviving `# noqa: BLE001` carries a one-line justification and represents a real, defended decision — not a deferral.

### RED

- [x] Re-list every `# noqa: BLE001` site (`grep -rn "noqa: BLE001" pipelex`). Confirm against the triage groups below.
- [x] For each site to be narrowed, determine the exact exception set the guarded call can raise — read the callee, do not guess. Where a narrowed catch changes observable behavior (an exception that used to be swallowed now propagates), add or extend a unit test that pins the intended behavior *before* narrowing. List those tests here. — _No new pinning tests: every narrowing catches the same real exception set on the expected path; none is an intended behavior change. `make agent-test` (REFACTOR step) is the regression check._
- [x] The genuinely-legitimate group (Group F) gets no code change — only a verification pass and a justification comment.

### GREEN

**Group A — `# TODO: wip - do not catch all exceptions` sites (do these first):**

- [x] `delivery_executor.py:177` `_generate_graph_files` — narrow the catch around `generate_graph_outputs()` to the exception(s) graph generation raises; keep it best-effort (a graph failure must not fail delivery) but only for those types. — _ASSESS: kept broad + justified; deep mermaid/reactflow/jinja2 render tree._
- [x] `delivery_executor.py:192` `_try_add_rendered_file` — narrow the catch around the render coroutine to the rendering exception(s). — _ASSESS: kept broad + justified; renders include the jinja2 stuff-viewer template._
- [x] `delivery_executor.py:231` `_deliver_to_storage` — narrow the catch wrapping `storage_provider.store()` into `StorageDeliveryError` to the storage-provider exception type(s). (Re-raises, so not `noqa`'d — but the `# TODO` still applies.) — _Kept broad `except Exception` (re-raises as `StorageDeliveryError`; ruff exempts re-raising handlers); TODO replaced with a real comment._
- [x] `delivery_executor.py:265` `_notify_webhook` — narrow the catch wrapping the webhook POST into `WebhookDeliveryError` to `httpx` request/transport errors (`httpx.HTTPStatusError` is already handled separately just above). — _Narrowed → `except httpx.RequestError`._
- [x] `act_assemble_graph.py:52` — Temporal graph-assembly activity. If this is a true activity root, keep the broad catch but replace the `# TODO` with a real justification. Otherwise narrow to the graph-assembly / event-log exception(s). — _Kept broad + justified (true activity root)._
- [x] Remove every `# TODO: wip - do not catch all exceptions` comment as its site is resolved.

**Group B — defensive utilities (narrow to the real exception set):**

- [x] `json_utils.py:384,444,497` — three identical `kajson.dumps()` fallbacks → narrow to `(TypeError, UnijsonEncoderError)` (kajson's encoder error). — _Narrowed; added `from kajson.exceptions import UnijsonEncoderError`._
- [x] `class_utils.py:97` `are_classes_equivalent` — narrow the catch around `model_json_schema()` to pydantic's schema-generation error(s); the manual-field-comparison fallback stays. — _Narrowed → `(PydanticUserError, PydanticUndefinedAnnotation)`._
- [x] `library_manager.py:1177` — narrow the catch around `structure_class.model_rebuild()` to pydantic rebuild errors (`NameError` / `PydanticUndefinedAnnotation`). — _Narrowed → `(NameError, PydanticUserError)`._
- [x] `mistral_factory.py:257` `_clean_base64` — narrow to `(binascii.Error, ValueError)`. — _Narrowed → `except ValueError` (covers `binascii.Error`/`UnicodeDecodeError`, both `ValueError` subclasses)._
- [x] `output_renderer.py:54,92` — narrow the catches around `render_stuff_spec()` to the rendering exception(s). — _ASSESS: kept broad + justified; `render_concept_representation` spans concept-structure resolution + pydantic schema generation over dynamic concepts._
- [x] `dry_run.py:187` and `working_memory_factory.py:190` — narrow the mock-creation fallbacks to the factory / pydantic-validation exception(s) that `make_mock_content` / `TypedNamedStuffSpec.make_from_named` / `StuffFactory.make_stuff` actually raise. — _`dry_run.py:187` narrowed → `except ValidationError`. `working_memory_factory.py:190` ASSESS: kept broad + justified (polyfactory mock build over arbitrary dynamic classes)._
- [x] `string_utils.py:58` (`f"{value}"` on arbitrary input) and `structured_content_composer.py:107` (diagnostic string builder) — assess: arbitrary `__str__` / introspection genuinely can raise anything. Either narrow to `(AttributeError, KeyError, TypeError)` or keep with an explicit justification. Record the decision in Running Notes. — _Both KEPT broad + justified (a partial narrow would be wrong: arbitrary `__str__`/`__format__` can raise any exception). `structured_content_composer.py:107` already had a justification — left unchanged._

**Group C — teardown best-effort cleanup:**

- [x] `gateway_extract_worker.py:76,78`, `google_img_gen_worker.py:86,89`, `google_llm_worker.py:103,106` — narrow the inner `asyncio.run(... aclose())` catch to `RuntimeError` plus the transport/connection errors `aclose()` raises; narrow or explicitly justify the outer teardown catch. Keep the "log but don't fail teardown" intent. — _ASSESS: kept broad `except Exception` + `# noqa: BLE001` + justification. First narrowed to `except RuntimeError`; code review flagged that the inner catch wraps `asyncio.run(aclose())` which genuinely runs `aclose()` — a non-enumerable failure surface over a duck-typed/deep connection pool — so narrowing defeats the "never fail teardown" contract. Reverted; matches Phase 1's "too broad to narrow safely" note._

**Group D — CLI code that is not a true command root (narrow):**

- [x] `init/ui/backends_ui.py:88` — narrow the file-read catch to `(TomlError, OSError)`. — _Narrowed._
- [x] `show_cmd.py:160` — narrow the routing-profile load catch to the config / IO error(s). — _Narrowed → `except MarkupError`. NOTE: not a "load" catch — `routing_profile` is already loaded; the block prints Rich markup with interpolated config strings, so `rich.errors.MarkupError` is the real failure mode._
- [x] `init/backends.py:137` (extension suggestion), `:168` (save terms), `:176` (disable gateway) — narrow each inner catch to what its called helper raises; the outer `:183` is a command-level boundary (Group F). — _`:137` → `except EOFError` (no-stdin `Confirm.ask`); `:168`/`:176` → `(OSError, TOMLKitError)`; `:183` kept broad + justified (command-level boundary)._
- [x] `doctor_cmd.py` config-load helpers (`:103`, `:121`, `:320`) — narrow to `(TomlError, OSError)`. Triage the remaining `doctor_cmd.py` catches per-site: the doctor's job is "probe and report", so a broad catch around a whole probe is defensible — keep those with a justification, narrow the ones wrapping a single well-typed call. — _DONE — `:103`→`(PipelexCLIError, OSError)`, `:121`/`:320`→`(TomlError, OSError)`; the 9 probe / `--fix`-handler catches kept broad + justified. See Running Notes._

**Group E — silent-swallow sites (restructure):**

- [x] `wf_pipe_router.py:120,165` — `except Exception: pass` (`# noqa: BLE001, S110`). Silent swallow of trace / event-log cleanup. Narrow to the cleanup exception(s); if kept broad, at minimum log at debug level and drop the bare `pass`. — _DONE — both `try/except` blocks removed entirely: `event_log` is always a `BufferingEventLog` and its `close()` is a verified no-op (empty body), so the calls are now bare `event_log.close()`._

**Group F — genuinely legitimate (verify + justify only, no narrowing):**

- [x] Agent CLI command roots that convert to `agent_error()` (the documented CLI boundary) — confirm each is at the command root and `agent_error()` is `NoReturn`; keep `# noqa: BLE001`. — _DONE — 23 sites; `agent_error()` confirmed `-> NoReturn`; each got a justification comment._
- [x] Dev CLI command roots (`_dev_cli.py` and `dev_cli/commands/*`) — keep. — _DONE — 10 sites in `_dev_cli.py` + 3 in `dev_cli/commands/*`; each got a justification comment._
- [x] Telemetry (`exception_capture.py`, `telemetry_manager.py`, `posthog_span_exporter.py`) — telemetry must never break the app; keep with a justification comment. — _DONE — `exception_capture.py:84,91` and `telemetry_manager.py:199` got new comments; `telemetry_manager.py:209/217/225` and `posthog_span_exporter.py:368` already had one._
- [x] `init/command.py:484`, `init/routing.py:156`, `init/backends.py:183` — command-level boundaries; keep. — _DONE — `init/command.py:484` and `init/routing.py:156` got new comments; `init/backends.py` (now `:185`) already had one._
- [x] `ndjson_event_log.py:190` (`__del__`) — interpreter-shutdown safety net; keep. — _DONE — already carried a justification comment; verified._
- [x] `pipe_run.py:41` — records `DeliveryStatus.FAILED`. Decide: narrow to `PipelexError` now, or defer to Phase 5 (the PipeRouter retry loop touches this path). Record the decision. — _DECISION: kept broad + justified. It is observe-and-reraise — the catch records `DeliveryStatus.FAILED` then re-raises the original exception unconditionally at method end. Narrowing to `PipelexError` would be wrong: a non-`PipelexError` failure would skip the FAILED-status recording. Not a deferral — a legitimate permanent boundary; Phase 5 can still restructure the path._
- [x] Run `make agent-check` until clean after each group.

### REFACTOR

- [x] Every surviving `# noqa: BLE001` has a one-line justification comment on the same or an adjacent line. — _Verified: all 76 surviving sites carry a comment on the following line._
- [x] No `# TODO: wip - do not catch all exceptions` comment remains anywhere. — _Verified: `grep` returns nothing._
- [x] Run `make agent-test`. For each narrowed site, confirm no test fails because a previously-swallowed exception now propagates — if one does, that is either the intended fix or a sign the narrowing is wrong; resolve per-site. — _DONE — `make agent-test` passed; no narrowing regressed a test._
- [x] Record in Running Notes: the final count of surviving `noqa: BLE001`, the per-site decisions for the "assess" sites (Group B last bullet, `doctor_cmd.py`, `pipe_run.py`), and any behavior change where an exception now propagates. — _DONE — see Running Notes below._

> ### STOP — CHECKPOINT A.5: broad-except sweep fully narrowed
>
> **Status (landed 2026-05-15):** COMPLETE — Groups A, B, C, D, E, F and REFACTOR all landed. `make agent-check` clean (ruff + plxt + pyright 0 errors + mypy 0 issues); `make agent-test` passed. 76 surviving `# noqa: BLE001`, each carrying a one-line justification; no `# TODO: wip` markers remain. Per-site decisions are in the "Phase 1.5" section of Running Notes below.
>
> Commit. Every broad catch is now either narrowed or a defended, justified boundary. Next session resumes at Phase 2.
>
> **Hand-off context to record in Running Notes:** the final `noqa: BLE001` count, the "assess"-site decisions, and any intentional behavior change from narrowing.

---

## Phase 2 — `error_domain` on the error model

**Goal:** `error_domain` becomes a first-class field on the exception hierarchy and on `ErrorReport`, so it no longer depends on the agent-CLI string dict. This is the schema change both downstream consumers (Temporal, CLI markdown) need before they are built.

Reference: [track-metadata-model.md](wip/error-handling/track-metadata-model.md) followups 1.

### RED

- [x] Write `tests/unit/pipelex/exceptions/test_error_domain.py` asserting:
  - `ErrorDomain` is a `StrEnum` (imported from `pipelex.types`) with values `INPUT`, `CONFIG`, `RUNTIME`.
  - `PipelexError.to_error_report()` carries `error_domain` when the class declares one, and omits it (`None`) otherwise.
  - `ErrorReport.to_dict()` drops `error_domain` when `None` and includes it otherwise.

### GREEN

- [x] Add `ErrorDomain` `StrEnum`. — _Placed in `pipelex/base_exceptions.py` next to `PipelexError`/`ErrorReport` (mirrors `InferenceErrorCategory` living beside `CogtError` in `cogt/exceptions.py`)._
- [x] Add an optional class-level `error_domain: ErrorDomain | None = None` attribute on `PipelexError`.
- [x] Add `error_domain: str | None = None` to the `ErrorReport` frozen dataclass. — _Placed after `error_category`; both `ErrorReport` constructors use kwargs so field order is safe._
- [x] Update `PipelexError.to_error_report()` to include `error_domain` from the class attribute.
- [x] Update `CogtError.to_error_report()` so it forwards `error_domain` too (it overrides the base method).
- [x] Run `make agent-check`. — _Clean (ruff + plxt + pyright 0 errors + mypy 0 issues)._

### REFACTOR

- [x] No change to consumers yet — `agent_error()` still reads its dict. Phase 4 flips the precedence. Keeping consumer changes out of this phase keeps the schema change reviewable in isolation.

---

## Phase 3 — Class-level metadata on non-`CogtError` exceptions

**Goal:** the key non-`CogtError` exceptions self-describe `error_domain` and `user_action` at the class level, and the uncategorized `CogtError` subclasses get their `error_category` defaults. After this phase, the metadata lives on the classes — the string dicts become removable in Phase 4.

Reference: [track-metadata-model.md](wip/error-handling/track-metadata-model.md) followups 2–3.

### RED

- [x] Write `tests/unit/pipelex/exceptions/test_class_level_metadata.py` asserting each targeted exception's `to_error_report()` carries the expected `error_domain` and `user_action`:
  - `PipelineExecutionError`, `PipeExecutionError` (`pipelex/pipeline/exceptions.py`) → `error_domain=RUNTIME`.
  - `ValidateBundleError` (`pipelex/pipeline/validate_bundle.py`) → `error_domain=INPUT`.
  - `PipelexInterpreterError` (`pipelex/core/interpreter/exceptions.py`) → `error_domain=INPUT`.
  - `PipelexSetupError`, `PipelexConfigError` (`pipelex/base_exceptions.py`) → `error_domain=CONFIG`.
  - Service errors (`pipelex/system/pipelex_service/exceptions.py`) → `error_domain=CONFIG`.
- [x] Add tests asserting the previously-uncategorized `CogtError` subclasses now report a non-`None` `error_category` (prompt-spec / prompt-template / prompt-parameter / prompt-image / prompt-document families → `CONTENT`).

### GREEN

- [x] Set class-level `error_domain` (and `user_action` where the track doc proposes concrete text) on the non-`CogtError` exceptions listed above. Use the user-action wording from [track-metadata-model.md](wip/error-handling/track-metadata-model.md) followup 2. — _`user_action` set on `PipelineExecutionError` (kind `UNKNOWN`) and `ValidateBundleError` (kind `CHANGE_INPUT`); `user_action` added as a class attr on `PipelexError` and forwarded by the base `to_error_report()`. Service-error domain set on the `PipelexServiceError` base + `PipelexServiceConfigValidationError` so all gateway/remote-config subclasses inherit it._
- [x] Set `error_category` defaults on the uncategorized `CogtError` subclasses (the prompt-* families → `CONTENT`). Decide case-by-case for `ImageContentError`, `CostRegistryError`, `ReportingManagerError`, `SdkTypeError`, `ExtractOutputError`, `GeneratedImageError`, `LLMAssignmentError`, `InferenceBackendLibraryError` — record each decision in Running Notes. Leave the four per-instance "outcome" exceptions uncategorized. — _Case-by-case decisions in Running Notes._
- [x] Run `make agent-check`. — _Clean. Updated `tests/unit/pipelex/test_base_exceptions.py` cold-import expectation (`PipelexConfigError` now reports `error_domain=config`)._

### REFACTOR

- [x] Scan for any other frequently-raised `PipelexError` subclass that obviously belongs to one domain. — _Deliberately stayed within the listed scope per "do not chase exhaustiveness"; the Phase 4 drift test guards the rest._

---

## Phase 4 — Retire the agent-CLI string dicts + drift detection

**Goal:** `agent_error()` reads class-level metadata first and falls back to the string dicts *only* for non-`PipelexError` built-ins (`FileNotFoundError`, `JSONDecodeError`, `ValidationError`, …) that cannot carry class attributes. A drift-detection test guards the remaining dict entries.

Reference: [track-metadata-model.md](wip/error-handling/track-metadata-model.md) followups 4–6, [track-testing.md](wip/error-handling/track-testing.md) followup 2.

### RED

- [x] Write the drift test. — _Placed at `tests/unit/pipelex/cli/test_agent_output_drift.py` (flat, beside the existing `test_agent_output.py` — the `agent_cli/` subdir does not exist yet). Two sub-checks, both adapted from the plan against the actual dict contents:_
  - _**Stale-key check:** every dict key is either a live `PipelexError` subclass name (walked recursively after importing the defining modules) **or** a documented non-`PipelexError` key. The plan's literal "resolves to a real exception class" is false for ~6 keys (`ArgumentError`, `BinaryNotFoundError`, `GraphSpecParseError`, `BundleError`, `InitConfigError`, `UnknownCommandError`) which are synthetic `error_type` labels passed straight to `agent_error()` — no class exists. They (plus builtins / `mthds`-package / `ValueError`-subclass keys) are listed in a documented `_NON_PIPELEX_ERROR_KEYS` allowlist._
  - _**No-double-source check:** no `PipelexError` subclass that declares class-level `error_domain` / `user_action` also appears in `AGENT_ERROR_DOMAINS` / `AGENT_ERROR_HINTS`. This replaces the plan's "every `PipelexError` subclass declares metadata or appears in the dicts" — that literal check is infeasible (dozens of subclasses have neither, and Phase 3 REFACTOR explicitly says not to chase exhaustiveness). The no-double-source check is the achievable, valuable drift guard: it fails the build if a class gains metadata but its redundant dict entry is left behind._
- [x] Write tests asserting `agent_error()` prefers `report.error_domain` over the dict when the cause is a `PipelexError`, and still falls back to the dict for a built-in exception type. — _Added to `test_agent_output.py`; `user_action`/hint precedence was already report-first and already covered._

### GREEN

- [x] In `agent_output.py`, change `agent_error()` so `error_domain` comes from `cause.to_error_report()` first; the dict is the fallback. — _`hint` was already report-first; only `error_domain` needed the change (new `report_domain` local)._
- [x] Remove the redundant `AGENT_ERROR_HINTS` / `AGENT_ERROR_DOMAINS` entries. — _Removed only entries whose class now carries class-level metadata (the "now redundant" ones): 2 from `AGENT_ERROR_HINTS` (`ValidateBundleError`, `PipelineExecutionError`), 9 from `AGENT_ERROR_DOMAINS` (`ValidateBundleError`, `PipelexInterpreterError`, `PipelineExecutionError`, `PipeExecutionError`, + 5 service errors). PipelexError subclasses NOT migrated in Phase 3 keep their dict entries — removing them would be a non-redundant regression. See Running Notes._
- [x] Run `make agent-check`. — _Clean. Updated `test_agent_output.py::test_agent_error_falls_back_to_lookup_when_report_fields_none` to key off `PipeExecutionError` (its hint survives) instead of the removed `ValidateBundleError`._

### REFACTOR

- [x] Add a short comment at the dict definitions. — _States the dicts are the fallback for error types that cannot self-describe (builtins, third-party, synthetic labels, un-migrated `PipelexError` subclasses) and that migrated classes must not appear — drift-test enforced. Not "built-ins-only": the dicts still hold un-migrated `PipelexError` subclass entries._
- [x] Confirm `RETRYABLE_ERROR_TYPES` is still needed only for non-`CogtError` causes. — _Both entries (`RemoteConfigFetchError`, `PipeOperatorModelAvailabilityError`) are non-`CogtError` `PipelexError` subclasses whose `to_error_report()` carries no `retryable`; nothing to trim. Added a comment saying so._

> ### STOP — CHECKPOINT B: Shared metadata foundation landed ✅
>
> **Status (landed 2026-05-15):** COMPLETE — Phases 2, 3, 4 landed. `make agent-check` clean (ruff + plxt + pyright 0 errors + mypy 0 issues); `make agent-test` passed (full suite). `ErrorReport` now carries `error_domain`; `error_domain` + `user_action` live as class-level metadata on the key non-`CogtError` exceptions; the uncategorized prompt-* `CogtError` families carry `error_category=CONTENT`; `agent_error()` reads `error_domain` report-first; the redundant lookup-dict entries are removed and `test_agent_output_drift.py` guards the rest. Per-phase decisions are in the Running Notes "Phase 2 / 3 / 4" sections below. Next session resumes at Phase 5.
>
> `ErrorReport` is now complete (`error_domain` included) and the metadata lives on the exception classes, drift-guarded. Both remaining priorities can now build on a stable schema.
>
> **Hand-off context recorded in Running Notes:** the case-by-case `error_category` decisions from Phase 3, which dict entries survived (not built-ins-only — see the note), and why the drift test does not flag un-migrated `PipelexError` subclasses.

---

## Phase 5 — PipeRouter retry loop (resilience without Temporal)

**Goal:** `PipeRouter` retries `InferenceErrorCategory.TRANSIENT` failures with exponential backoff, driven by config, **enabled by default with a small retry budget**. This is the application-level resilience layer that must work when Temporal is absent. Retry logic moves out of the two gateway workers into the dispatch layer.

Reference: [track-retry-and-resilience.md](wip/error-handling/track-retry-and-resilience.md) followups 1–6.

**Two coherence decisions to settle in this phase (flagged 2026-05-15):**

- **Default retry budget — do not default to 0.** Today the gateway workers retry up to 50× via `tenacity`. Phase 5's REFACTOR removes that. If the new router retry defaults to `max_transient_retries = 0`, the out-of-the-box behavior becomes *no retry at all* — strictly worse than today, and that is **not** "backward compatibility". The default must be a small sane number (recommended: **3**). `0` stays a valid value (explicit opt-out), just not the default.
- **`CAPACITY` stays out of the fast retry loop.** `InferenceErrorCategory.is_retryable` is `False` for `CAPACITY` — keep it that way; do **not** overload `is_retryable`. A rate-limit (429) is "retryable" only on a much longer timescale and is really an *overwhelm* signal — Phase 5.5 owns it (back off on `provider_metadata.retry_after_seconds`, reduce concurrency, advise Temporal). The router loop retries `TRANSIENT` only.

### RED

- [x] Write `tests/unit/pipelex/pipe_run/test_pipe_router_retry.py` asserting:
  - A `CogtError` with `error_category=TRANSIENT` retries up to `max_transient_retries`, then re-raises the last error (cause chain preserved).
  - A `CogtError` with `CONFIGURATION` / `CONTENT` / `CAPACITY` / `UNKNOWN` fails immediately (no retry).
  - A `PipeRunError` (non-`CogtError`) is unaffected and still wraps as `PipeRouterError`.
  - `max_transient_retries = 0` disables retry entirely (explicit opt-out — but it is *not* the default; see the coherence decisions above).
  - Backoff wait increases each attempt; the retry log line includes attempt number, wait duration, and error category.
  - `_before_run()` runs once before the loop; `_after_failing_run()` runs once after retries are exhausted or on a non-retryable error.

### GREEN

- [x] Add retry config fields to `PipelineExecutionConfig` (`pipelex/system/configuration/configs.py`): `max_transient_retries: int`, `transient_retry_base_wait: float`, `transient_retry_max_wait: float`, `transient_retry_backoff_multiplier: float`. Per project rules: no defaults in the class body — put defaults in `pipelex/pipelex.toml` with `max_transient_retries = 3` (a small sane budget — see the coherence decision above; **not** `0`); add commented-out overrides in `.pipelex/pipelex.toml`. — _Done; commented-out overrides also added to `pipelex/kit/configs/pipelex.toml` (kept in sync with `.pipelex/`)._
- [x] Add the retry loop to `PipeRouterProtocol.run()` (`pipelex/pipe_run/pipe_router_protocol.py`): wrap `_run_pipe_job()`, catch `CogtError` where `error_category is not None and error_category.is_retryable`, sleep with exponential backoff, continue; re-raise on exhaustion; non-retryable categories fail immediately; the existing `PipeRunError` path is unchanged.
- [x] Thread the retry config via `get_config()` inside the protocol (Option B in the track doc) — consistent with how `pipeline_execution_config` is already accessed. — _DEVIATION: Option B as literally written is impossible. `pipelex.config` imports `pipelex.hub`, and `hub` type-imports `PipeRouterProtocol` — any `config` import in `pipe_router_protocol.py` (module **or** function scope) trips pyright's `reportImportCycles`. Resolved with a hybrid: a dependency-free `TransientRetrySettings` model (`pipelex/pipe_run/transient_retry.py`) the protocol carries as an instance attribute, populated from `get_config()` by each concrete router at construction via `make_transient_retry_settings()` in `pipe_router.py`. See Running Notes._
- [x] Run `make tb` (boot sequence — verifies the config model and the three `pipelex.toml` files agree). Run `make agent-check`.

### REFACTOR

- [x] Remove `tenacity` retry from the gateway extract and search workers (`_make_retryer`, `_is_retryable_portkey_error`, `_log_retry`, the `async for attempt` wrapper). Confirm errors still propagate with the correct `InferenceErrorCategory` on first failure. — _Done. The now-dead `response is None` defensive branches (and `attempt_number` tracking) were also removed._
- [x] Remove `TenacityConfig` from `pipelex/cogt/config_cogt.py` and its `pipelex.toml` entries, **only if** nothing else uses it (`pipelex/plugins/fal/fal_poller.py` still uses tenacity for polling and `log_retry` from `tenacity_utils.py` — verify before removing the `tenacity` dependency or `tenacity_utils.py`). — _`TenacityConfig` removed. `tenacity` dependency and `tenacity_utils.py` KEPT — `fal_poller.py` and `remote_config_fetcher.py` still use them. See Running Notes for the breaking-change note on stale user configs._
- [x] Add a one-line code comment at the `instructor` `max_retries` call sites noting it retries schema-validation, not transport — out of scope for router retry. — _Done in the four LLM workers (google, anthropic, openai completions, openai responses)._

> ### STOP — CHECKPOINT C: PipeRouter retry loop landed
>
> Update checkboxes, run `make agent-check` and `make agent-test`, commit. Then **stop — Phase 5.5 is a fresh session.**
>
> **Status (landed 2026-05-15):** COMPLETE — RED, GREEN, REFACTOR all landed. `make agent-check` clean (ruff + plxt + pyright 0 errors + mypy 0 issues); `make tb` passes; `make agent-test` passed. Per-decision detail in the "Phase 5" section of Running Notes below.
>
> **Hand-off context to record in Running Notes:** the two coherence decisions as actually settled (final default `max_transient_retries`; `CAPACITY` disposition); whether removing the gateway-worker `tenacity` changed any timing-sensitive test; the final disposition of the `tenacity` dependency, `TenacityConfig`, and `tenacity_utils.py`; the retry config fields added and their `pipelex.toml` defaults.
>
> **Next session resumes at Phase 5.5** — re-read the "Start here" section, "Why this plan exists", the Phase 5.5 section, and [track-retry-and-resilience.md](wip/error-handling/track-retry-and-resilience.md).

---

## Phase 5.5 — Bounded fan-out concurrency (resilience without Temporal, pillar B)

**Goal:** `PipeBatch` fans out over its N items in **bounded chunks** driven by a `max_concurrency` config, so a large workload — one pipe over 1,000 documents — no longer spawns N coroutines, N deep-copied working memories, and N simultaneous inference calls at once. This is a *basic, honest* backpressure effort with plain Python — **not** durable execution. When the workload is large or `CAPACITY` errors persist, the failure path surfaces a clear `user_action` pointing at the Temporal track as the durable, rate-limited answer. Pillar B of "resilience without Temporal"; coupled with Phase 5 (see Sequencing).

Reference: [track-retry-and-resilience.md](wip/error-handling/track-retry-and-resilience.md) — this is net-new ground the track doc does not yet cover; capture the design back into the track doc as it lands.

### RED

- [x] Write `tests/unit/pipelex/pipe_controllers/test_pipe_batch_concurrency.py` asserting:
  - With `max_concurrency = K`, no more than `K` branch coroutines are ever in flight at once (use a probe that increments/decrements a counter on entry/exit and records the peak).
  - All N items still complete and results preserve input order.
  - `max_concurrency` unset / very large → behaves as today (single `asyncio.gather`).
  - A failure in one branch still propagates (define and pin chunk-failure semantics — first error wins; in-flight branches in the failing chunk are awaited or cancelled deterministically).
  - _DEVIATION: the bounded fan-out was extracted into a generic, isolated helper `gather_bounded` (`pipelex/tools/misc/async_utils.py`) that `PipeBatch` calls — far more unit-testable than `_live_run_controller_pipe`, which needs heavy fixture setup. The test therefore lives at `tests/unit/pipelex/tools/misc/test_async_utils.py` (beside what it tests) rather than the plan's `pipe_controllers/test_pipe_batch_concurrency.py`. All four RED assertions map onto the helper. `PipeBatch`'s own use of it is covered by the existing `tests/integration/pipelex/pipes/` batch tests._

### GREEN

- [x] Add a `max_concurrency: int` config field (decide placement: `PipelineExecutionConfig` next to the retry fields, or a small dedicated `ConcurrencyConfig` — record the call). Per project rules: no default in the class body — default in `pipelex/pipelex.toml` (recommended: a sane modest value, **not** unbounded), commented-out override in `.pipelex/pipelex.toml`. — _Placed on `PipelineExecutionConfig` next to the retry fields (same "resilience without Temporal" concern — no separate `ConcurrencyConfig`). Typed `Annotated[int, Field(ge=1)] | Literal["unbounded"]` — an explicit literal disables the bound rather than a magic `0`. Default `max_concurrency = 8` in `pipelex/pipelex.toml`; commented-out overrides in `.pipelex/pipelex.toml` and `pipelex/kit/configs/pipelex.toml`._
- [x] Implement bounded fan-out in `PipeBatch` (`pipelex/pipe_controllers/batch/pipe_batch.py`). Prefer **chunked execution** (process items in chunks of K) over a bare `asyncio.Semaphore`: chunking bounds *memory* — only K working-memory deep-copies are materialized at once — which a semaphore alone does not. — _Done via the `gather_bounded` helper, which takes per-branch *factories* (not coroutines) and invokes them chunk-by-chunk, so each deep-copied working memory is materialized only when its chunk runs. `PipeBatch` builds one factory per branch; item-stuff creation + graph-tracer registration stay in an upfront loop (cheap, sync)._
- [x] Decide whether `PipeParallel` also needs a bound. It fans over a *fixed, pipe-defined* branch set (usually small), not a data-driven N — the scaling risk is `PipeBatch`. Record the decision in Running Notes. — _DECISION: not bounded. `PipeParallel` fans over a fixed, pipe-defined branch set, not a data-driven N; left as a plain `asyncio.gather`._
- [x] Run `make tb` (boot sequence — config model ↔ `pipelex.toml` agreement). Run `make agent-check`. — _`make tb` passes; `make agent-check` clean (ruff + plxt + pyright 0 errors + mypy 0 issues)._

### REFACTOR

- [x] Graceful-degradation messaging: when a `PipeBatch` workload exceeds a soft threshold, or when `CAPACITY` errors recur, attach an advisory `user_action` / log line naming the **Temporal track** as the durable, rate-limited path. Advisory, never fatal — "we made a basic effort; here is the stronger solution." — _Done as a `log.warning` (advisory, never fatal): when a `PipeBatch` fans out over more than `LARGE_BATCH_ADVISORY_THRESHOLD` (100) items, it logs once, naming the Temporal track and the active `max_concurrency`. A soft item-count threshold was chosen over `CAPACITY`-recurrence detection — the latter needs cross-branch error aggregation that is out of proportion for "basic, honest backpressure"; the Phase 5 retry loop + this advisory cover the honest standalone story._
- [x] Record in Running Notes how this composes with Phase 5: bounded concurrency *reduces* how often `CAPACITY` is hit; the router retry loop handles the residual `TRANSIENT`; persistent `CAPACITY` is the honest "go Temporal" boundary. — _Recorded below._

> ### STOP — CHECKPOINT C.5: Bounded fan-out concurrency landed — resilience-without-Temporal complete
>
> Update checkboxes, run `make tb`, `make agent-check`, and `make agent-test`, commit. Then **stop — Phase 6 is a fresh session.**
>
> **Status (landed 2026-05-16):** COMPLETE — RED, GREEN, REFACTOR all landed. `make agent-check` clean (ruff + plxt + pyright 0 errors + mypy 0 issues); `make tb` passes; targeted `pipe_controllers` / `tools` / `pipes` suites pass; `make agent-test` passed. Per-decision detail in the "Phase 5.5" section of Running Notes below.
>
> Both standalone-resilience pillars now stand: Pipelex retries transients (Phase 5) and bounds its fan-out (Phase 5.5) without Temporal.
>
> **Hand-off context to record in Running Notes:** the `PipeParallel` bounding decision; the chosen `max_concurrency` default and config placement; the chunk-failure semantics; the graceful-degradation messaging; how Phases 5 + 5.5 compose.
>
> **Next session resumes at Phase 6** — re-read the "Start here" section, the Phase 6 section, and [track-temporal-integration.md](wip/error-handling/track-temporal-integration.md).

---

## Phase 6 — Temporal bridge: category-aware retry + details payload

**Goal:** Temporal's retry decision flows from `InferenceErrorCategory.is_retryable` (the same signal as the PipeRouter loop), and `ApplicationError.details` carries the full `ErrorReport` across the activity → workflow boundary.

Reference: [track-temporal-integration.md](wip/error-handling/track-temporal-integration.md) followups 1–4.

### RED

- [x] Write `tests/unit/pipelex/temporal/test_temporal_error_bridge.py` asserting:
  - `from_message_exception()` on a `CogtError` with `TRANSIENT` produces `non_retryable=False`.
  - …with `CONFIGURATION` / `CONTENT` / `CAPACITY` / `UNKNOWN` produces `non_retryable=True`.
  - …on a non-`CogtError` `PipelexError` falls back to the `non_retryable_error_types` name list.
  - …on a `CogtError` with `error_category=None` falls back to the name list (no crash).
  - `ApplicationError.details` round-trips through Temporal serialization with all `ErrorReport` fields intact.
  - Log severity (critical / error) matches the retry decision on both the `from_message_exception` and `from_app_error` paths.

### GREEN

- [x] In `pipelex/temporal/tprl/temporal_error.py`, `from_message_exception()`: when `exc` is a `CogtError` with a non-`None` `error_category`, derive retryability from `error_category.is_retryable` and set `non_retryable = not is_retryable` on the `ApplicationError`. When the category is `None`, keep the existing `non_retryable_error_types` lookup.
- [x] Pack `exc.to_error_report().to_dict()` into `ApplicationError.details`. `from_app_error()` extracts the details payload and surfaces it back as fields on the resulting `TemporalError` so the structured data survives the round-trip.
- [x] Update the docstrings of `RetryPolicyConfig.non_retryable_error_types` and `non_retryable_error_types_extra` (`pipelex/temporal/config_temporal.py`) to state that the name list is a *fallback* for category-less exceptions and an override mechanism — category decides retryability for `CogtError`.
- [x] Run `make agent-check`.

### REFACTOR

- [x] Check the in-process PipeRouter retry (Phase 5) and the Temporal retry agree on what "transient" means — both consult `is_retryable`. Note in Running Notes how the two layers compose (Temporal sees a non-retryable error only after the router exhausted its retries, or for non-`TRANSIENT` categories).

> ### STOP — CHECKPOINT D: Resilience landed (Temporal half)
>
> Update checkboxes, run `make agent-check` and `make agent-test`, commit. Run the Temporal integration tests per `_tprl/CLAUDE.md` (`--temporal-server` options). Then **stop — Phase 7 is a fresh session.**
>
> **Status (landed 2026-05-16):** COMPLETE — RED, GREEN, REFACTOR all landed. `make agent-check` clean (ruff + plxt + pyright 0 errors + mypy 0 issues); `make agent-test` passed (full suite). Temporal integration suite (`tests/integration/pipelex/temporal/`, in-process server) passed — 94 passed, 4 xpassed (pre-existing xdist-flaky tests that happened to pass; not a regression), 0 failures, no timing-sensitive regression. Per-decision detail in the "Phase 6" section of Running Notes below.
>
> Priority 1 is complete: standalone, Pipelex retries transients and bounds fan-out concurrency; across the Temporal boundary, retry flows from the same `is_retryable` signal and `ErrorReport` round-trips in `ApplicationError.details`.
>
> **Hand-off context:** the in-process retry (Phase 5) and Temporal retry compose as nested layers agreeing on `is_retryable` — see "How Phases 5 and 6 compose" in Running Notes. The Temporal integration suite surfaced no timing-sensitive regression.
>
> **Next session resumes at Phase 7** — re-read the "Start here" section, the Phase 7 section, and [track-cli-delivery.md](wip/error-handling/track-cli-delivery.md).

---

## Phase 7 — Error delivery: agent CLI markdown + HTTP-status mapping

**Goal (priority 2 — errors surface cleanly on every delivery surface):**

- **CLI:** the agent CLI emits plain markdown by default for `run` / `validate` / `init` and for the error path; JSON is available via `--format json`. The eleven near-identical Rich handlers in `error_handlers.py` collapse onto one panel helper.
- **HTTP:** `pipelex` itself is a library — there is no API server inside the package (verified: zero `fastapi` / `HTTPException` usage). But the HTTP API repos (`pipelex-relay`, `pipelex-back-office`) need to render `ErrorReport` as an HTTP response, and today the `error_domain` → status mapping is implicit and gets reinvented per repo. This phase puts a **documented, authoritative `error_domain` → HTTP-status mapping in the library** so the downstream FastAPI exception handler is a trivial one-screen adapter. The library stays HTTP-agnostic (no FastAPI dependency) — it only owns the mapping table.

Reference: [track-cli-delivery.md](wip/error-handling/track-cli-delivery.md) followups 1–6.

### RED

- [x] Write tests under `tests/unit/pipelex/cli/agent_cli/` (or integration where the CLI harness fits) asserting:
  - `run` / `validate` with no `--format` produce markdown to stdout.
  - `run --format json` / `validate --format json` produce valid JSON to stdout.
  - An error with no `--format` produces markdown to stderr; with `--format json`, JSON to stderr.
  - The `inputs` command is unaffected (always JSON per the `agent_cli/CLAUDE.md` contract).
  - _Landed as `test_run_format.py`, `test_validate_format.py`, `test_agent_error_format.py`, `test_inputs_format_unaffected.py` under `tests/unit/pipelex/cli/agent_cli/` + an autouse `conftest.py` resetting the format ContextVar. The error-format assertions live in `test_agent_error_format.py` (markdown vs JSON dispatch + `agent_error_markdown` rendering); the `inputs`-unaffected check is a reflection test that no `inputs` subcommand has an `output_format` param._
- [x] Write `tests/unit/pipelex/test_error_http_status.py` asserting the `error_domain` → HTTP-status mapping: `INPUT` → 422 (unprocessable input the caller can fix), `CONFIG` → 500 (server-side environment/config problem), `RUNTIME` → 500; `error_domain = None` → 500. And: when `provider_metadata.status_code` is a 429, the mapping yields 429 with `retry_after_seconds` exposed for a `Retry-After` header (provider-status passthrough takes precedence over the domain default). — _Done; covers both `error_domain_to_http_status()` (pure function) and `ErrorReport.http_status` (property, with the 429 passthrough)._

### GREEN

- [x] Add `error_domain_to_http_status()` (and/or an `ErrorReport.http_status` property) — recommended location `pipelex/base_exceptions.py`, next to `ErrorDomain` / `ErrorReport`. Pure mapping, no `fastapi` import. It considers `provider_metadata.status_code` (429 passthrough) first, then `error_domain`, then a 500 default. — _Both added: `error_domain_to_http_status(ErrorDomain | None) -> int` is the pure domain table (exhaustive `match`, no `case _`); `ErrorReport.http_status` is the property that layers the 429 passthrough on top._
- [x] Add `agent_error_markdown(message, error_type, cause, **extra)` to `agent_output.py` — markdown to stderr (error-type heading, message body, hint as a tip callout, `error_source` as a code block), still `raise typer.Exit(1)`. — _Done; shares `_assemble_error_payload()` with the JSON path, renders via `_render_error_markdown()` (heading / message / `> 💡` hint callout / `## Details` / `## Error source` code block)._
- [x] Introduce a format-aware error dispatch (explicit `format` argument or a `ContextVar`). Keep JSON as the default when format is unknown (errors during init, before the format option is parsed — see `agent_cli_factory.py`). — _DEVIATION: a `ContextVar` (`_agent_cli_output_format`, default `JSON`) — and `agent_error()` itself is the dispatcher (JSON vs markdown) rather than a separate `agent_error_dispatch`. This is cleaner: all ~80 existing `agent_error(...)` call sites follow `--format` for free with zero edits; a command opts in via `set_agent_cli_output_format()`. JSON stays the default for anything before a command opts in (app callback, unknown-command, factory init errors). See Running Notes._
- [x] Add `--format markdown|json` to `run`, `validate`, `init` (`match/case` on `CliOutputFormat`, default `MARKDOWN`), mirroring `models_cmd.py`. Add the markdown renderers: `_format_run_markdown`, `_format_validate_markdown`, and the `init` confirmation. Files: `commands/run/{pipe,bundle,method}_cmd.py`, `commands/validate/{pipe,bundle,method}_cmd.py`, `commands/init_cmd.py`. — _Done. Renderers: `format_run_markdown` (`run/_output_helpers.py`), `format_validate_markdown` (new `validate/_output_helpers.py`), `_format_init_markdown` (`init_cmd.py`). Success path uses a shared `agent_success_formatted(result, markdown_renderer)` helper. `models`/`check-model`/`doctor` also wired to `set_agent_cli_output_format()` so their errors follow `--format` too. NAMING CONFLICT resolved: `validate bundle`'s graph-format option was `--format`/`-f` — renamed to `--graph-format`/`-f` so `--format` is uniformly the output-format flag (breaking CLI change, per repo no-back-compat policy)._
- [x] Run `make agent-check`. — _Clean (ruff + plxt + pyright 0 errors + mypy 0 issues)._

### REFACTOR

- [x] Extract `display_error_panel(console, *, title, fields, error_message, tip, links)` in `pipelex/cli/error_handlers.py`; rewrite each `handle_*` to build its field list and call the helper. Exception-specific logic stays in the handler; the panel shape lives in one place. — _`display_error_panel` extracted (banner / aligned fields / error message / 💡 tip / dimmed links). Applied to the three genuinely field-shaped handlers: `handle_model_choice_error`, `handle_model_availability_error`, `handle_model_deck_preset_error`. DEVIATION: the plan's "each `handle_*`" overstated uniformity — the gateway / telemetry / inference / validate-bundle handlers have prose / structured-detail bodies that are not a `(label, value)` field list (the track doc itself notes the gateway handlers have prose bodies); they keep custom bodies. Snapshot coverage is Phase 8._
- [x] Update `pipelex/cli/agent_cli/CLAUDE.md`: markdown is the default for `run` / `validate` / `init` / `models` / `doctor` / `check-model`; `--format json` available on all of them; errors respect the same option; document each command's markdown structure. — _Done — new "Output format" section (default markdown, JSON-only commands, ContextVar dispatch, per-command markdown structure); commands table + Key Patterns updated._
- [x] Document the `error_domain` → HTTP-status mapping where a downstream API author will find it (a docstring on the helper plus a short note in `wip/error-handling/track-cli-delivery.md` or `architecture.md`), including the 429 / `Retry-After` passthrough. The mapping table is authoritative in the library; API repos call the helper, they do not redefine it. — _Done — full docstrings on `error_domain_to_http_status()` and `ErrorReport.http_status`, plus a "HTTP-status mapping (authoritative)" section in `track-cli-delivery.md`._

> ### STOP — CHECKPOINT E: Error delivery landed
>
> Update checkboxes, run `make agent-check` and `make agent-test`, commit. Then **stop — Phase 8 is a fresh session.**
>
> **Status (landed 2026-05-16):** COMPLETE — RED, GREEN, REFACTOR all landed. `make agent-check` clean (ruff + plxt + pyright 0 errors + mypy 0 issues); `make agent-test` passed (full suite). The agent CLI now emits markdown by default for `run` / `validate` / `init` (and `models` / `check-model` / `doctor` already did), with `--format json` for the structured payload; errors follow the same option via a per-invocation `ContextVar`. `ErrorReport` carries a documented, authoritative `error_domain` → HTTP-status mapping (`error_domain_to_http_status()` + `ErrorReport.http_status`, 429 passthrough). Per-decision detail in the "Phase 7" section of Running Notes below.
>
> Priority 2 is complete: the agent CLI emits markdown by default with `--format json`, and `ErrorReport` carries a documented `error_domain` → HTTP-status mapping.
>
> **Hand-off context to record in Running Notes:** the final HTTP-status mapping table; where the panel helper landed; any Rich-rendering change from the `error_handlers.py` refactor.
>
> **Next session resumes at Phase 8** — re-read the "Start here" section, the Phase 8 section, and [track-testing.md](wip/error-handling/track-testing.md).

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

### Phase 1.5 — Second-pass narrowing of `noqa: BLE001` sites (IN PROGRESS — checkpoint 2026-05-15)

**Final state:** ALL groups (A–F) and REFACTOR landed. `make agent-check` is clean (ruff + plxt + pyright 0 errors + mypy 0 issues). `make agent-test` passed. **76 surviving `# noqa: BLE001`** (down from 91 at RED), each carrying a one-line justification comment on the following line; zero `# TODO: wip - do not catch all exceptions` markers remain. An independent code review of the staged diff ran at the earlier checkpoint; its one finding (the Group C teardown narrowing) was applied — see the Group C entry below.

**RED findings:**

- 91 `# noqa: BLE001` sites found (the plan estimated 93 — line drift since Phase 1, no material difference). 5 `# TODO: wip - do not catch all exceptions` markers (`delivery_executor.py` ×4, `act_assemble_graph.py` ×1).
- **No new pinning tests were added.** Every narrowing catches the *same real exception set* the guarded call raises on its expected path — none is an *intended* behavior change. Behavior only differs if a latent bug raises an unexpected type; `make agent-test` (the REFACTOR step) is the regression check for exactly that, as the plan frames it.
- The editor's inline pyright surfaces many `reportMissingImports` for optional inference SDKs (`anthropic`, `google.genai`, `mistralai`, `fal_client`, `botocore`, `docling`, `temporalio`). That is an artifact of the editor's diagnostic environment — the real `make agent-check` pyright (run with `--pythonpath .venv/bin/python`) reports 0 errors. Ignore the inline noise.

**Landed — per-site dispositions (all pass `make agent-check`):**

_Group A (`delivery_executor.py`, `act_assemble_graph.py`) — all 5 `# TODO: wip` comments removed:_

| Site | Disposition |
| --- | --- |
| `_generate_graph_files` | KEPT broad `# noqa: BLE001` + justification. ASSESS — `generate_graph_outputs()` is a deep mermaid/reactflow/jinja2 render tree; surface not enumerable; best-effort (a graph failure must not fail delivery). |
| `_try_add_rendered_file` | KEPT broad `# noqa: BLE001` + justification. ASSESS — renders include the jinja2 stuff-viewer template. |
| `_store_results` | KEPT broad `except Exception` — re-raises as `StorageDeliveryError`; ruff exempts re-raising handlers so no `noqa`. TODO replaced with a real comment. Wraps `generate_result_files()` (deep). |
| `_notify_webhook` | NARROWED → `except httpx.RequestError` (re-raises as `WebhookDeliveryError`; `httpx.HTTPStatusError` handled just above). |
| `act_assemble_graph` | KEPT broad `# noqa: BLE001` + justification — true Temporal activity root; best-effort observability, degrades to `None`. |

_Group B:_

| Site | Disposition |
| --- | --- |
| `json_utils.py:384,444,497` | NARROWED → `(TypeError, UnijsonEncoderError)`; added `from kajson.exceptions import UnijsonEncoderError`. |
| `class_utils.py:97` | NARROWED → `(PydanticUserError, PydanticUndefinedAnnotation)`; added pydantic import. |
| `library_manager.py:1177` | NARROWED → `(NameError, PydanticUserError)`. |
| `mistral_factory.py:257` | NARROWED → `except ValueError` — `binascii.Error` and `UnicodeDecodeError` are both `ValueError` subclasses, so `ValueError` is the correct minimal catch (the plan's `(binascii.Error, ValueError)` is redundant). |
| `dry_run.py:187` | NARROWED → `except ValidationError` (`TypedNamedStuffSpec.make_from_named` is a pydantic construction). |
| `working_memory_factory.py:190` | KEPT broad + justification. ASSESS — `make_mock_content` builds mocks via polyfactory over arbitrary dynamic structure classes; wide unstable surface; falls back to text content. |
| `string_utils.py:58` | KEPT broad + justification. ASSESS — `f"{value}"` invokes arbitrary `__str__`/`__format__`; can raise anything; a partial narrow would be wrong. |
| `structured_content_composer.py:107` | KEPT broad, unchanged — already had a justification comment. |
| `output_renderer.py:54,92` | KEPT broad + justification. ASSESS — `render_stuff_spec` → `render_concept_representation` spans concept-structure resolution + pydantic schema generation over dynamic concepts. |

_Group C — all 6 teardown sites (`gateway_extract_worker.py`, `google_img_gen_worker.py`, `google_llm_worker.py`):_ KEPT broad `except Exception` + `# noqa: BLE001` + justification (ASSESS). First narrowed to `except RuntimeError`, but the code review correctly flagged that the inner catch wraps `asyncio.run(aclose())` — which genuinely runs `aclose()`; its failure surface over a duck-typed/deep connection pool is not enumerable, and the teardown contract is "never fail". Reverted; this matches Phase 1's original "`aclose()` raises too broad a set to narrow safely" note.

_Group D (partial):_

| Site | Disposition |
| --- | --- |
| `backends_ui.py:88` | NARROWED → `(TomlError, OSError)`. |
| `show_cmd.py:160` | NARROWED → `except MarkupError`. NOT a "load" catch (the plan misread it) — `routing_profile` is already loaded; the block prints Rich markup with interpolated config strings, so `rich.errors.MarkupError` is the real mode. |
| `backends.py:137` | NARROWED → `except EOFError` (`suggest_extension_install_if_needed`'s only uncaught exception is `EOFError` from `Confirm.ask` with no stdin). |
| `backends.py:168,176` | NARROWED → `(OSError, TOMLKitError)`; added `from tomlkit.exceptions import TOMLKitError`. |
| `backends.py:183` | KEPT broad + justification — command-level boundary (Group F category). |

**Checkpoint fix:** the first `make agent-check` flagged 8 `E501` (justification comments >150 chars); all shortened; re-check clean.

**Group D — `doctor_cmd.py` (landed):**

| Site | Disposition |
| --- | --- |
| `:103` (`init_config`) | NARROWED → `(PipelexCLIError, OSError)`; added `from pipelex.cli.exceptions import PipelexCLIError`. `init_config` does os/shutil work (the `os.makedirs` outside its inner try raises `OSError`) and wraps the rest into `PipelexCLIError`. |
| `:121` (`load_config` + `model_validate`) | NARROWED → `(TomlError, OSError)`. Verified `ConfigLoader.load_config()` only does TOML loading + file IO (`TomlError` / `OSError`); the `ValidationError` from `model_validate` is caught separately just above. |
| `:320` (`load_toml_from_path`) | NARROWED → `(TomlError, OSError)`. `load_toml_from_path` raises only `TomlError` (parse) or `OSError` (`open()`). |
| `:231`, `:253`, `:294`, `:373`, `:767` | KEPT broad + justification. Doctor probes — "probe and report" over a non-enumerable surface (whole credential/model scans, kit-template lookups). |
| `:881`, `:900`, `:911`, `:937` | KEPT broad + justification. Doctor `--fix` handlers wrapping whole sub-commands (`init_cmd`/`update_cmd`/`replace_backend_file`); a fix failure is reported, the run continues. |
| `:785` (`doctor_cmd` command root) | Unchanged — already had a justification comment. |

**Group E — `wf_pipe_router.py:120,165` (landed):** both `try/except Exception: pass` blocks removed entirely. `event_log` is always a `BufferingEventLog`; its `close()` is a verified no-op (empty body) and cannot raise, so both call sites are now a bare `event_log.close()`. No `noqa` survives at these sites.

**Group F — verify + justify (landed, no narrowing):** all sites confirmed as true boundaries; a one-line justification comment was added wherever one was missing.

- **Agent CLI command roots (23 sites)** — `cli/agent_cli/commands/**`. Each catches at the command function and routes through `agent_error()` (confirmed `-> NoReturn` in `agent_output.py`) — the documented CLI error boundary. The agent-CLI `doctor_cmd.py:134` had a redundant trailing `# agent_error has NoReturn` comment folded into the new justification.
- **Dev CLI command roots (13 sites)** — `_dev_cli.py` ×10 (all identical: print a `rich` Traceback then `sys.exit(1)`) + `generate_mthds_schema_cmd.py`, `check_mthds_schema_cmd.py`, `preprocess_test_models_cmd.py` (the last had a weak `# Catch-all for unexpected errors` comment, strengthened).
- **Telemetry (7 sites)** — `exception_capture.py:84,91` + `telemetry_manager.py:199` got new comments; `telemetry_manager.py:209/217/225` and `posthog_span_exporter.py:368` already carried one.
- **`wf_pipe_router.py:108,115,142,157`** — workflow tracing setup/teardown observe-and-log catches (line numbers shifted from the plan's `145,160` after the Group E removal). Each got a "best-effort — must never fail the workflow" justification.
- **`init/command.py:484`, `init/routing.py:156`** — command-level boundaries; got new comments. `init/backends.py` (now `:185`) already had one.
- **`ndjson_event_log.py:190`** (`__del__`) — interpreter-shutdown safety net; already justified.
- **`pipe_run.py:41`** — kept broad + justified; see the Group F checkbox decision above (observe-and-reraise).

**REFACTOR (landed):** every surviving `# noqa: BLE001` verified to carry a comment on the following line (76/76); `grep` confirms no `# TODO: wip - do not catch all exceptions` remains; `make agent-check` clean and `make agent-test` passed.

**Behavior changes from Phase 1.5 narrowing:** none intended. The three Group D narrowings (`:103`, `:121`, `:320`) each catch the same real exception set the guarded call raises on its expected path. If an unexpected exception type were ever raised, it now propagates to the `doctor_cmd` root catch (`:785`) — which already degrades gracefully — instead of being caught locally. `make agent-test` passed, confirming no test depended on the previously-broad catch.

**Final `noqa: BLE001` count: 76** (91 at Phase 1.5 RED → 81 after Groups A/B/C/D-partial at the earlier checkpoint → 76 after Group D narrowing ×3 and Group E removal ×2 this session).

**Assess-site decisions (kept broad + justified — the REFACTOR Running Notes requirement):** `_generate_graph_files`, `_try_add_rendered_file`, `act_assemble_graph` (Group A); `working_memory_factory.py:190`, `string_utils.py:58`, `structured_content_composer.py:107`, `output_renderer.py:54,92` (Group B); the 6 `teardown()` catches in `gateway_extract_worker.py` / `google_img_gen_worker.py` / `google_llm_worker.py` (Group C); `backends.py:183` (Group D, command boundary). Each wraps a non-enumerable exception surface (deep render/template trees, polyfactory mock building, arbitrary `__str__`, `asyncio.run(aclose())` over a connection pool, or a command-level boundary) and is a genuine best-effort / boundary catch.

### Phase 2 — `error_domain` on the error model (landed 2026-05-15)

`ErrorDomain` (`StrEnum`: `INPUT` / `CONFIG` / `RUNTIME`) was placed in `pipelex/base_exceptions.py`, next to `PipelexError` and `ErrorReport` — the analogue of `InferenceErrorCategory` living beside `CogtError` in `cogt/exceptions.py`. The plan left placement open ("ask the user if ambiguous"); this was the consistent call and `base_exceptions.py` is what consumes it, so no import indirection is needed.

`ErrorReport` gained `error_domain: str | None = None` (typed `str`, mirroring `error_category` — keeps the field a plain string and matches the existing pattern). `PipelexError` gained the class attr `error_domain: ErrorDomain | None = None`; both `PipelexError.to_error_report()` and the `CogtError` override forward it. No consumer changes (Phase 4's job).

### Phase 3 — Class-level metadata on exceptions (landed 2026-05-15)

**`user_action` on the base class.** Phase 3 needs class-level `user_action`, so `PipelexError` gained `user_action: UserAction | None = None` and the base `to_error_report()` now forwards it. `CogtError` already declared its own `user_action` class attr + `__init__` param — left as-is (a harmless same-typed override; removing it is out of scope).

**`error_domain` set on:** `PipeExecutionError` + `PipelineExecutionError` → `RUNTIME`; `ValidateBundleError` + `PipelexInterpreterError` → `INPUT`; `PipelexConfigError` + `PipelexSetupError` → `CONFIG`; `PipelexServiceError` (base) + `PipelexServiceConfigValidationError` → `CONFIG` (all gateway / remote-config errors inherit via `PipelexServiceError`).

**`user_action` set on** (only where the track doc proposes concrete text): `PipelineExecutionError` → `UserAction(UNKNOWN, "Check pipe_stack to identify which pipe failed")`; `ValidateBundleError` → `UserAction(CHANGE_INPUT, "Check the validation_errors array for specific issues")`. `CHANGE_INPUT` fits a bad-bundle fix; `UNKNOWN` is the honest kind for a generic execution failure (`UserActionKind` has no diagnostic-investigation kind — the `detail` carries the real guidance).

**Prompt-* `CogtError` families → `CONTENT`** (firm, per track followup 3): `LLMPromptSpecError`, `LLMPromptTemplateInputsError`, `LLMPromptParameterError`, `PromptImageFactoryError`, `PromptImageFormatError`, `PromptDocumentFactoryError`, `ImgGenPromptError`, `ImgGenParameterError`.

**Case-by-case `error_category` decisions** (the eight the plan flagged):

| Class | Decision | Rationale |
| --- | --- | --- |
| `ImageContentError` | `CONTENT` | Name is explicit ("image content"). Currently unused — assigned by name semantics. |
| `SdkTypeError` | `CONFIGURATION` | Raised when the injected SDK client is the wrong type for the worker — a setup/wiring misconfiguration. |
| `InferenceBackendLibraryError` | `CONFIGURATION` | Raised during backend-library validation/setup (`backend_library.py`). |
| `CostRegistryError` | `None` (uncategorized) | Internal cost-bookkeeping error; not a classifiable inference failure. |
| `ReportingManagerError` | `None` | Internal reporting error; not a classifiable inference failure. |
| `GeneratedImageError` | `None` | Internal PIL→raw image-conversion failure; not content / config / capacity. |
| `ExtractOutputError` | `None` | Currently unused; a post-extraction processing error — not clearly one category. |
| `LLMAssignmentError` | `None` | Currently unused; ambiguous — left uncategorized. |

`None` keeps today's behavior (an uncategorized report) — the safe default for the genuinely-ambiguous / internal ones. The four per-instance "outcome" exceptions stay uncategorized as the plan directs.

**Intentional behavior change.** The targeted exceptions now emit `error_domain` (and `user_action` for two) in `to_error_report()`. `tests/unit/pipelex/test_base_exceptions.py`'s cold-import assertion was updated to expect `error_domain: 'config'` on `PipelexConfigError`'s report. For a real `ValidateBundleError` / `PipelineExecutionError` cause, `agent_error()`'s `hint` now comes from the class `user_action` (`hint` was already report-first) — the text is the track-doc wording, a slight rewording of the old dict hint.

### Phase 4 — Retire the agent-CLI string dicts + drift detection (landed 2026-05-15)

**`agent_error()` change.** Only `error_domain` needed work — `hint` (from `user_action`) was already report-first. Added a `report_domain` local; `domain = report_domain or AGENT_ERROR_DOMAINS.get(error_type)`.

**Dict entries removed** (only the now-redundant ones — those whose class gained class-level metadata in Phase 3):

- `AGENT_ERROR_HINTS`: `ValidateBundleError`, `PipelineExecutionError` (the two that gained class `user_action`).
- `AGENT_ERROR_DOMAINS`: `ValidateBundleError`, `PipelexInterpreterError`, `PipelineExecutionError`, `PipeExecutionError`, `GatewayTermsNotAcceptedError`, `GatewayApiKeyMissingError`, `GatewayDoNotTrackConflictError`, `RemoteConfigFetchError`, `RemoteConfigValidationError`.

**Dict entries that survived** — the plan's "remove all `PipelexError`-keyed entries" was NOT taken literally: it would regress every `PipelexError` subclass Phase 3 did not migrate. Survivors include `PipelexError`-subclass keys with no class-level metadata (`ModelChoiceNotFoundError`, `PipeOperatorModelChoiceError`, `PipeOperatorModelAvailabilityError`, `ModelDeckPresetValidatonError`, `TelemetryConfigValidationError`, `MthdsDecodeError`, `JsonTypeError`), plus the *hint* entries for `PipeExecutionError` / `PipelexInterpreterError` / gateway errors (those gained `error_domain` but no `user_action`, so the hint stays dict-sourced). The "(now redundant)" qualifier in the plan is operative — only redundant entries were removed; the dicts are **not** "built-ins-only".

**`RETRYABLE_ERROR_TYPES`:** unchanged. Both entries (`RemoteConfigFetchError`, `PipeOperatorModelAvailabilityError`) are non-`CogtError` `PipelexError` subclasses whose base `to_error_report()` carries no `retryable` — nothing the report covers, nothing to trim.

**Behavior change.** None for real call paths: every agent-CLI catch site that surfaces a migrated exception passes the actual exception instance as `cause`, so `error_domain` resolves from the report. A bare `error_type` string with no matching cause for a migrated class would lose its dict domain — no such call site exists. `make agent-test` is the regression check.

### Checkpoint B hand-off

- **Case-by-case `error_category` decisions:** the Phase 3 table above.
- **Which dict entries survived:** the Phase 4 "Dict entries that survived" note — un-migrated `PipelexError` subclasses + builtins / third-party / synthetic labels; **not** built-ins-only.
- **`PipelexError` subclasses still needing metadata:** the drift test does not flag these (the literal "every subclass" check was descoped as infeasible — see the Phase 4 RED notes). Un-migrated dict-referenced subclasses (`ModelChoiceNotFoundError`, `PipeOperatorModel*`, `TelemetryConfigValidationError`, `ModelDeckPresetValidatonError`, …) still rely on the fallback dicts; migrating them is future work and does not block the shared foundation.

### Phase 5 — PipeRouter retry loop (landed 2026-05-15)

**Coherence decision 1 — default retry budget:** settled as recommended. `pipelex/pipelex.toml` ships `max_transient_retries = 3`, `transient_retry_base_wait = 2.0`, `transient_retry_max_wait = 30.0`, `transient_retry_backoff_multiplier = 2.0`. `0` is a valid explicit opt-out, not the default. Commented-out overrides added to both `.pipelex/pipelex.toml` and `pipelex/kit/configs/pipelex.toml`.

**Coherence decision 2 — `CAPACITY`:** untouched. `InferenceErrorCategory.is_retryable` still returns `False` for `CAPACITY` (and `CONFIGURATION` / `CONTENT` / `UNKNOWN`); the router loop retries `TRANSIENT` only. `CAPACITY` (rate-limit / overwhelm) is Phase 5.5's concern.

**Import-cycle deviation (the big one).** The track doc's "Option B — call `get_config()` directly inside `PipeRouterProtocol.run()`" is **not achievable**. `pipelex.config` imports `pipelex.hub`, and `hub.py` references `PipeRouterProtocol` (as a type). Any import of `pipelex.config` / `pipelex.hub` / `pipelex.system.configuration.configs` from `pipe_router_protocol.py` — at module scope **or** inside a function, and even under `TYPE_CHECKING` — trips pyright's `reportImportCycles` (verified: pyright counts function-local and TYPE_CHECKING imports for cycle detection). Resolution:

- New dependency-free module `pipelex/pipe_run/transient_retry.py` holds `TransientRetrySettings` (a plain `BaseModel`: `max_transient_retries`, `base_wait`, `max_wait`, `backoff_multiplier`, plus `compute_wait(retry_count)` for the exponential backoff). It imports only pydantic, so `pipe_router_protocol.py` can import it cycle-free.
- `PipeRouterProtocol` carries `transient_retry_settings: TransientRetrySettings` as an instance attribute (alongside `observer`). `run()` reads `self.transient_retry_settings` — no config import.
- `make_transient_retry_settings()` in `pipe_router.py` reads `get_config().pipelex.pipeline_execution_config` and builds the model. All three concrete routers (`PipeRouter`, `DryPipeRouter`, `TemporalPipeRouter`) call it in `__init__` to populate the attribute. `dry_pipe_router.py` and `temporal_pipe_router.py` import the helper from `pipe_router.py` (none of those modules are in the `hub` import chain, so no cycle).
- `hub.py`: `PipeRouterProtocol` import moved into the `TYPE_CHECKING` block (it was only ever a type there); the three function annotations referencing it were quoted. This is clean regardless of the cycle and was kept.

Net: config is read at router **construction** time, not per-`run()`. Acceptable — retry config is static for the process lifetime. The retry loop itself lives exactly where the plan wants it (`PipeRouterProtocol.run()`).

**Gateway worker `tenacity` removal.** `_make_retryer` / `_is_retryable_portkey_error` / `_log_retry` and the `async for attempt in retryer` wrappers removed from `gateway_extract_worker.py` and `gateway_search_worker.py`. The now-dead `response is None` defensive branches (only reachable if the retryer looped zero times) and the `attempt_number` counters were removed too; error messages dropped the "after N attempt(s)" phrasing. No timing-sensitive test broke — `make agent-test` passed. Three gateway test files (`test_gateway_quota_detection.py`, `test_gateway_search_worker_semantic.py`, `test_gateway_extract_worker_semantic.py`) had `worker._tenacity_config = MagicMock()` setup blocks; those are now dead and were removed.

**`tenacity` dependency / `tenacity_utils.py`: KEPT.** `pipelex/plugins/fal/fal_poller.py` (polling) and `pipelex/system/pipelex_service/remote_config_fetcher.py` both still use `tenacity` directly; `fal_poller.py` uses `log_retry` from `tenacity_utils.py`. Only `TenacityConfig` (the config model) and `Cogt.tenacity_config` were removed.

**Breaking change — stale `[cogt.tenacity_config]` in user configs.** `extra="forbid"` on `ConfigModel` means an existing `~/.pipelex/pipelex.toml` (or any layered override) that still carries `[cogt.tenacity_config]` now fails config load with `extra_forbidden`. Removed the section from the repo's three toml files (`pipelex/pipelex.toml`, `.pipelex/pipelex.toml`, `pipelex/kit/configs/pipelex.toml`) **and** from this machine's global `~/.pipelex/pipelex.toml` (which a prior `pipelex init` had populated — that is what surfaced the failure during testing). Users upgrading must remove `[cogt.tenacity_config]` from their global config — noted in CHANGELOG.

**`instructor` `max_retries`.** A one-line comment was added at the four LLM-worker call sites (`google_llm_worker.py`, `anthropic_llm_worker.py`, `openai_completions_llm_worker.py`, `openai_responses_llm_worker.py`) noting it retries schema-validation failures only, not transport — out of scope for router retry.

**Intentional behavior changes.** (1) `_after_failing_run()` now fires for a `CogtError` too (previously only `PipeRunError` was caught by `run()`; a `CogtError` propagated raw without notifying the observer). (2) An exhausted-retry or non-retryable `CogtError` is re-raised **as-is** (cause chain preserved) — it is *not* wrapped into `PipeRouterError`; only the pre-existing `PipeRunError` path still wraps.

**Aside:** `make cleanderived` during this phase erased the generated `tests/integration/pipelex/fixtures/_generated_model_sets.py`; `make rtm` regenerated it. Unrelated to retry work.

**Post-landing code review fix.** A review of the diff caught a regression: the deleted gateway-worker `_is_retryable_portkey_error` predicate had retried a `NotFoundError` whose message was "specified deployment could not be found" (a transient Portkey deployment-propagation race). With retry now driven by `GatewayFactory.classify_error_category()`, which mapped *every* `NotFoundError` → `CONFIGURATION` (non-retryable), that case would have stopped retrying. Fixed by adding `GatewayFactory._is_deployment_propagation_race()` and special-casing that message → `TRANSIENT` in `classify_error_category()` (and → `WAIT_AND_RETRY` in `make_user_action_from_portkey_error()`). A `not_found_404_deployment_propagation_race` case was added to `CLASSIFY_CASES`. Also restored field bounds the removed `TenacityConfig` used to provide: `PipelineExecutionConfig` retry fields now carry `Field(ge=0)` (`ge=1` for the backoff multiplier) so a malformed `pipelex.toml` fails at config load.

### Phase 5.5 — Bounded fan-out concurrency (landed 2026-05-16)

**The `gather_bounded` helper (design call).** The plan said "implement bounded fan-out in `PipeBatch`". Instead, the bounded fan-out is a generic, isolated helper — `gather_bounded` in the new `pipelex/tools/misc/async_utils.py` — that `PipeBatch` calls. Rationale: the helper is unit-testable in isolation with trivial probe coroutines, whereas `PipeBatch._live_run_controller_pipe` needs heavy fixture setup (working memory, concepts, a registered branch pipe). All four RED assertions test the helper directly. Consequently the test lives at `tests/unit/pipelex/tools/misc/test_async_utils.py` (beside what it tests), **not** the plan's `tests/unit/pipelex/pipe_controllers/test_pipe_batch_concurrency.py`.

**Factories, not coroutines — the key design point.** `gather_bounded` takes `Sequence[Callable[[], Awaitable[T]]]`, not coroutines. It calls each factory only when its chunk is about to run. This is what bounds *memory*: a `PipeBatch` branch factory defers its `working_memory.make_deep_copy()` until the factory is invoked, so at most `max_concurrency` deep copies exist at once. A bare `asyncio.Semaphore` over already-created coroutines would bound execution but not that materialization — the plan flagged this and chunked factory invocation is the answer.

**Chunk-failure semantics (pinned, uniform).** `gather_bounded` runs one code path for bounded and unbounded alike — the unbounded case is simply a single chunk of every factory. Each chunk uses `asyncio.gather(*chunk, return_exceptions=True)`: every branch in the chunk is awaited (drained — never orphaned or cancelled), then the first exception *by input index* is raised and no later chunk is started. A code review of the first cut caught that the original had a separate unbounded fast-path using *plain* `asyncio.gather`, which raises first-by-*completion-order* and leaves siblings orphaned — so a `PipeBatch` of ≤ 8 items (the default `max_concurrency`) would have had different, weaker failure semantics than a batch of 9+. Unifying the paths fixed that; `test_unbounded_run_propagates_lowest_index_error_over_a_faster_one` and `test_failing_chunk_is_drained_lowest_index_wins_and_later_chunks_skipped` pin index-order over time-order on both. A non-positive int bound now raises `ValueError` (`None` is the only way to request unbounded).

**Config placement and type.** `max_concurrency` on `PipelineExecutionConfig`, next to the Phase 5 retry fields — same "resilience without Temporal" concern, so no separate `ConcurrencyConfig` was introduced. Typed `Annotated[int, Field(ge=1)] | Literal["unbounded"]`: the int arm is a real bound (≥ 1, validated at config load); the explicit `"unbounded"` literal disables the bound — chosen over a magic `0` so the disabled state is self-documenting in the TOML. Default `max_concurrency = 8` in `pipelex/pipelex.toml`. Commented-out overrides in `.pipelex/pipelex.toml` and `pipelex/kit/configs/pipelex.toml`. Existing global configs without the key inherit the default from the layered base — no breaking change (unlike Phase 5's `tenacity_config` removal).

`gather_bounded` itself keeps a generic, config-agnostic contract: `max_concurrency: int | None`, where `None` is the idiomatic Python "no limit". `PipeBatch` bridges the two — it maps the config's `"unbounded"` literal to `None` before calling the helper.

**`PipeBatch` wiring.** The old single loop (item-stuff creation, graph-tracer registration, deep copy, run-params copy, router call → `tasks` list → `asyncio.gather`) is split: the upfront loop keeps the cheap synchronous work (item-stuff creation + graph-tracer registration), and a nested `async def _run_branch` holds the deferred expensive work (deep copy, run-params copy, `get_pipe_router().run()`). One `functools.partial(_run_branch, item_input_stuff, branch_output_item_code)` per branch goes into `branch_factories`, then `gather_bounded(branch_factories, max_concurrency=...)`. `partial` binds the per-branch varying args eagerly, sidestepping the loop-variable capture trap; `_run_branch` closes over only loop-invariant locals.

**`PipeParallel` — not bounded (decision).** It fans over a fixed, pipe-defined branch set (usually small), not a data-driven N. The scaling risk is `PipeBatch`. Left as a plain `asyncio.gather`, no change.

**Graceful-degradation advisory.** Module constant `LARGE_BATCH_ADVISORY_THRESHOLD = 100` in `pipe_batch.py`. When a `PipeBatch` fans out over more than that many items, `_live_run_controller_pipe` logs one `log.warning` naming the active `max_concurrency` and pointing at the Temporal track as the durable, rate-limited path. Advisory, never fatal. A soft item-count threshold was chosen over `CAPACITY`-recurrence detection: aggregating per-branch error categories across a batch is disproportionate effort for "basic, honest backpressure" — the Phase 5 retry loop already absorbs residual `TRANSIENT`, and this advisory is the honest "go Temporal" signal.

**How Phases 5 and 5.5 compose.** Bounded concurrency (5.5) *reduces how often* `CAPACITY` (rate-limit) errors are hit — fewer simultaneous provider calls. The Phase 5 router retry loop absorbs the residual `TRANSIENT` failures. Persistent `CAPACITY` *under* an already-bounded fan-out is the honest boundary where standalone resilience ends and Temporal (durable, task-queue-rate-limited execution) begins — which is exactly what the advisory log line points at. Neither pillar attempts durable crash-survival.

**Intentional behavior change.** With the default `max_concurrency = 8`, a `PipeBatch` over more than 8 items no longer runs every branch at once — it runs in chunks of 8. On the *success* path, batches of ≤ 8 items (or `max_concurrency = "unbounded"`) behave exactly as before. On the *failure* path, behavior changes uniformly for all batch sizes: a failing branch now drains its chunk (siblings are awaited, not left as orphaned background tasks) and the lowest-input-index error wins, instead of the prior plain-`asyncio.gather` first-by-completion-order selection. This is a deliberate improvement, not a regression. No test regressed: `make agent-check`, `make tb`, the targeted `pipe_controllers` / `tools` / `pipes` suites, and `make agent-test` all pass.

**Track doc.** `wip/error-handling/track-retry-and-resilience.md` gained a "Pillar B — Bounded fan-out concurrency" section capturing this design, as the plan directed (it was net-new ground).

### Phase 6 — Temporal bridge: category-aware retry + details payload (landed 2026-05-16)

**`TemporalError` extension.** `__init__` gained two passthrough params — `non_retryable: bool` and `error_report: dict[str, Any] | None`. `error_report`, when present, is splatted as the single `ApplicationError.details` entry (`super().__init__(message, *details, type=..., non_retryable=...)`) and also kept as an instance attribute for in-process readers. `non_retryable` is the Temporal-native retry flag — the inverse of `is_retryable`.

**Category-aware retry decision.** `from_message_exception()` delegates to a new `_is_non_retryable(exc, error_type)` classmethod: when `exc` is a `CogtError` with a non-`None` `error_category`, it returns `not error_category.is_retryable` — the same `is_retryable` signal the Phase 5 PipeRouter loop consults. Otherwise (non-`CogtError` `PipelexError`, or a `CogtError` raised without a category) it falls back to the configured `all_non_retryable_error_types` class-name lookup. Only `InferenceErrorCategory.TRANSIENT` is retryable, so a `TRANSIENT` `CogtError` → `non_retryable=False`; `CONFIGURATION` / `CONTENT` / `CAPACITY` / `UNKNOWN` → `non_retryable=True`.

**Details payload + round-trip.** `from_message_exception()` packs `exc.to_error_report().to_dict()` into details. `from_app_error()` recovers it via the module-level `_error_report_from_details()` helper, which scans `ApplicationError.details` for the first dict carrying the report's `error_type` + `message` shape (so an unrelated details payload is not mistaken for a report). `from_app_error()` preserves the round-tripped `non_retryable` flag and re-packs the report — the structured data (`error_category`, `user_action`, `model`, `provider`) survives the activity → workflow boundary. A legacy fallback remains: when an `ApplicationError` arrives with neither a details report nor `non_retryable` set (a plain error that never went through this bridge), `from_app_error()` still consults the class-name list for the severity decision.

**Log helpers for testability.** Logging was extracted into `_log_critical` / `_log_error` classmethods. `workflow_log` routes through `workflow.logger`, which raises `_NotInWorkflowEventLoopError` outside a live workflow event loop — so unit tests `mocker.patch.object` these two helpers (via an autouse fixture) and assert which severity the retry decision routed to. This is a pure refactor of the existing `workflow_log.critical` / `.error` calls; production behavior is unchanged.

**Config docs.** `RetryPolicyConfig.non_retryable_error_types` and `RetryPolicyConfigOverlay.non_retryable_error_types_extra` gained field-level docstrings stating the name list is a *fallback* for category-less exceptions and an *override* mechanism — category decides retryability for a category-carrying `CogtError`.

**How Phases 5 and 6 compose.** The two retry layers are nested and agree on "transient" — both read `InferenceErrorCategory.is_retryable`. The Phase 5 PipeRouter loop runs *inside* the activity: it retries a `TRANSIENT` `CogtError` up to `max_transient_retries`, sleeping between attempts. Only after that budget is exhausted (or immediately, for a non-`TRANSIENT` category) does the exception leave the activity and hit the Temporal bridge. So Temporal sees a `non_retryable=False` error only after the in-process loop already gave up on it — Temporal's own retry policy (durable, cross-worker) then gets another crack; a non-`TRANSIENT` category arrives as `non_retryable=True` and Temporal does not retry. Fast in-process retry first, durable Temporal retry on the residual.

**Known follow-up — `from_message_exception` is not yet wired (deferred, by decision).** A post-landing code review surfaced that `from_message_exception` — the activity-side half of the bridge, where the category-aware decision and `ErrorReport` details-packing live — has no production caller. Activities raise raw `CogtError` / `PipelexError`; Temporal's default failure converter auto-wraps them without packing our `ErrorReport`, so `from_app_error` currently always takes its `error_report is None` fallback branch and the category-aware path is inert in production. The Phase 6 unit test proves a self-consistent bridge round-trip but does not cross a real activity → workflow boundary. This was deliberately scoped out of Phase 6 (whose plan named only the bridge methods, not the activity wiring); it is recorded as **Followup 5** in [track-temporal-integration.md](wip/error-handling/track-temporal-integration.md) — wiring the ~8 `act_*` functions plus a real-boundary integration test is the next coherent unit of work.

### Phase 7 — Error delivery: agent CLI markdown + HTTP-status mapping (landed 2026-05-16)

**HTTP-status mapping.** `pipelex/base_exceptions.py` gained `error_domain_to_http_status(ErrorDomain | None) -> int` (the pure domain table: `INPUT` → 422, `CONFIG`/`RUNTIME`/`None` → 500; exhaustive `match`, no `case _`) and `ErrorReport.http_status` (a property that layers the provider-429 passthrough on top — when `provider_metadata.status_code == 429` it returns 429 so a downstream API can emit `Retry-After` from `retry_after_seconds`, otherwise it follows `error_domain`). The library stays HTTP-agnostic — no web-framework import; downstream FastAPI handlers call `ErrorReport.http_status` and are a trivial adapter.

**Format dispatch — the big deviation.** The plan offered "explicit `format` argument *or* a `ContextVar`" and a separate `agent_error_dispatch`. Settled as: a module-level `ContextVar` (`_agent_cli_output_format` in `agent_output.py`, default `CliOutputFormat.JSON`), and **`agent_error()` itself is the dispatcher** — it reads the ContextVar and routes to `_agent_error_json` or `agent_error_markdown`. Rationale: the agent CLI has ~80 `agent_error(...)` call sites across run/validate/init/factory; threading an explicit `format` arg through all of them is noisy and error-prone, and a separate `agent_error_dispatch` would require editing every call site. With `agent_error` as the dispatcher, every existing call site follows `--format` for free — a command opts in once via `set_agent_cli_output_format(output_format)` at its start. JSON stays the default for anything raised before a command opts in (the app callback, `PipelexAgentCLI.get_command` unknown-command handling, `make_pipelex_for_agent_cli` factory errors) because the ContextVar default is JSON. The plan's "keep `agent_error()` JSON as the default" is honored by the ContextVar default, not by keeping `agent_error` literally JSON-only. `agent_error_markdown()` is still a public function (named in the plan); JSON and markdown share `_assemble_error_payload()`.

**Markdown renderers + success path.** `format_run_markdown` (`run/_output_helpers.py`), `format_validate_markdown` (new `validate/_output_helpers.py`), `_format_init_markdown` (`init_cmd.py`). The success path goes through a shared `agent_success_formatted(result, markdown_renderer)` in `agent_output.py` (JSON → `agent_success`; markdown → `print(markdown_renderer(result))`). `format_run_markdown` handles both `build_run_output()` shapes — the `with_memory` envelope (renders `main_stuff.markdown`) and the compact concept JSON (fenced `json` block).

**`--format` naming conflict (breaking CLI change).** `validate bundle` already used `--format`/`-f` for the *graph* renderer (`GraphFormat`: mermaidflow/reactflow/both). To make `--format` uniformly the output-format flag across all commands, that option was renamed to `--graph-format`/`-f`. Breaking change for any skill invoking `validate bundle --format reactflow` — acceptable per the repo's no-back-compat policy; the agent-CLI `CLAUDE.md` documents `--graph-format`.

**`models` / `check-model` / `doctor`.** These already had `--format`; they now also call `set_agent_cli_output_format(output_format)` so their *error* paths follow the option too (previously errors were always JSON regardless). This makes the "errors respect `--format`" contract uniform.

**`error_handlers.py` refactor.** `display_error_panel(console, *, title, fields, error_message, tip, links)` extracted — the canonical red-banner / aligned-fields / error / 💡-tip / dimmed-links panel. Applied to the three genuinely field-shaped handlers: `handle_model_choice_error`, `handle_model_availability_error`, `handle_model_deck_preset_error`. DEVIATION: the plan said "rewrite *each* `handle_*`" but the gateway / telemetry / inference / validate-bundle handlers have prose or structured-detail bodies that are not a `(label, value)` field list — the track doc itself notes the gateway handlers have prose bodies. Those keep their custom bodies. The Phase 8 snapshot test will guard the field-based handlers' rendering.

**Behavior change — markdown is now the default.** `run` / `validate` / `init` previously always emitted JSON; they now default to markdown (`--format json` for the old behavior). Two existing unit tests asserted the old JSON default: `test_agent_validate_cmd.py::test_graph_generation_failure_emits_single_json_error` and `test_agent_doctor_cmd.py::test_unexpected_error_produces_json_error` — both updated to pass `output_format=CliOutputFormat.JSON` explicitly (they test the single-error / JSON-error invariants, which still hold on the JSON path). No other test regressed: `make agent-check` clean and `make agent-test` passed (full suite).

**ContextVar leakage in tests.** The format ContextVar is process-global (fine in production — one command per process). The new `tests/unit/pipelex/cli/agent_cli/conftest.py` has an autouse fixture resetting it to JSON before and after each test so it does not leak between tests.

**Post-landing code review fixes.** An independent review of the diff caught: (1) `format_validate_markdown` rendered only `validated_pipes` — it silently dropped the `graph_files` / `graphspec` keys that `validate bundle --graph` / `--view` merge into the result, so markdown mode (now the default) lost the graph-file pointers. Fixed: the renderer now surfaces a "Graph files" section and a GraphSpec note. (2) Two short loop variables (`fb`, `p`) in the rewritten `handle_model_availability_error` were left below the 3-char minimum — renamed to `fallback` / `stacked_pipe`. The reviewer's other points (the `error_domain_to_http_status` exhaustive `match` without a final return, and the ContextVar lacking `Token`/`reset`) were assessed and left as-is: pyright accepts the exhaustive match (the desired "linter catches a new enum member" guard — adding `case _` is forbidden), and the CLI is one-shot per process so `set()` without `reset()` is correct; the test conftest already isolates the ContextVar.
