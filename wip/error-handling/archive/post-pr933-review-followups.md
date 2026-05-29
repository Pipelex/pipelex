# TODOs — Post-PR #933 `/review` follow-ups

Lower-priority items left over from the pre-landing `/review` pass on
`feature/API-readiness-2` (PR #933 — error-handling overhaul, TODOS Phases 0–7).
None of these block the PR — they were either pre-existing items the reviewer
flagged per the "see something, say something" rule, or refinements that didn't
warrant action in the same commit series. Sequenced here so a fresh session can
land them coherently.

The original plan was [`../../../TODOS.md`](../../../TODOS.md). This file is its
post-merge tail.

## Branch setup

- Cut a new branch from `dev` **after PR #933 has merged**. Every section below
  references files in their post-#933 locations (Phase 6 moved many error classes
  into `exceptions.py` / `*_exceptions.py`). If #933 has not merged yet, branch
  from `feature/API-readiness-2`.

## How to start (cold start)

1. Read this whole file. It is self-contained — every item names the exact
   file:line, the symptom, and a recommended fix.
2. Resume at the first unchecked box. Phases are independent; pick the one that
   matches the available time budget (Phase A is the smallest, Phase D is a
   judgment call worth opening with the user).
3. Respect the ⛔ CHECKPOINT markers — they are hard stops.

## Ground rules

- `make agent-check` after every code change. `make agent-test` before every
  checkpoint.
- No backward-compat shims. Per project policy.
- One `TestClass` per test module; use `pytest-mock` (`MockerFixture`), not
  `unittest.mock`. See `.claude/rules/pytest-standards.md`.
- StrEnum rule: never `enum_var.value`, just `{enum_var}`. See
  `.claude/rules/python-standards.md`.

---

## Phase A — Test coverage backfill

The `/review` pass flagged six gaps where observable behavior is not pinned by a
test. None of these are bugs today; they are regression nets for future
refactors. Land as a single test-only commit.

### A.1 — `WfPipeRouter` `request_id` binding has no integration test

Only `WfPipeRun` is covered, by
`tests/integration/pipelex/temporal/test_wf_pipe_run_request_id_logging.py`. The
router-side wiring at `pipelex/temporal/tprl_pipe/wf_pipe_router.py:33` (the
per-invocation `workflow_log = WorkflowLog(request_id=workflow_arg.job_metadata.request_id)`)
can break — reverting to the module-level singleton, wrong attribute path —
without any test failing.

- [x] Add `tests/integration/pipelex/temporal/test_wf_pipe_router_request_id_logging.py`
      mirroring `test_wf_pipe_run_request_id_logging.py`: register `WfPipeRouter`
      under a worker with a failing inner pipe stub, dispatch with a
      `request_id` on `job_metadata`, capture the `temporalio.workflow` logger,
      assert at least one record carries `record.request_id == "<expected>"`.
- [x] Verify the test has teeth by temporarily reverting the `WorkflowLog(request_id=...)`
      construction to the unbound module singleton — the test must fail with
      `request_ids seen: ['None']`. Restore.

### A.2 — `caller_facing_message` inheritance contract pin

`pipelex/base_exceptions.py:317` documents that `_authors_caller_facing_message`
"is consulted by plain attribute access, so it inherits normally — a subclass
of a caller-facing error stays caller-facing." This is deliberately different
from `_declared_title` / `_declared_type_uri` (which use `cls.__dict__` to
bypass inheritance). The contract has no test pinning it; a future refactor
swapping the flag to `cls.__dict__` access would silently downgrade STRICT
disclosure for every `PipelexInterpreterError` / `ValidateBundleError`
subclass.

- [x] In `tests/unit/pipelex/exceptions/test_class_level_metadata.py`, add a
      parametrized case defining an inline subclass of `PipelexInterpreterError`
      and asserting its `to_error_report().caller_facing_message is True`.
      Mirror with a `ValidateBundleError` subclass.

### A.3 — Empty-message fallback in `recover_error_report` not tested

`pipelex/temporal/tprl/temporal_error.py:118` reads
`recovered_message = report_dict.get("message") or _message_from_exc(exc)` — the
`or` falls through to the exception-chain walk when the report dict's `message`
is empty or whitespace. Only the truthy-message branch is pinned today; a
regression swapping `or` to `??` / `is None` would silently emit
`[error report failed schema validation]` with an empty preamble.

- [x] In `tests/unit/pipelex/temporal/test_recover_error_report.py`, add a
      `test_invalid_report_with_empty_message_falls_back_to_exc_chain` that
      constructs the same 4-required-key payload as
      `test_found_but_invalid_report_dict_synthesizes_unrecoverable` but with
      `"message": ""`, and asserts the synthesized report's message contains
      both the underlying `ApplicationError` text and `"schema validation"`.

### A.4 — Force-load multi-failure aggregation contract not pinned

`pipelex/errors/error_pages_generator.py:80-98` aggregates per-module import
failures and raises one `RuntimeError` listing all of them. The existing test
`test_force_load_aggregates_non_import_error_failures` only asserts that the
**first** module's name appears in the message. A regression that re-raises on
the first failure (instead of accumulating) would still pass.

- [x] In `tests/unit/pipelex/errors/test_error_pages_generator.py`, add
      `test_force_load_walk_continues_past_first_failure` that patches
      `importlib.import_module` with a `side_effect` callable failing every
      call, then asserts at least 2 distinct dotted module names appear in the
      raised `RuntimeError.args[0]`. Remember to `_force_load_all_error_modules.cache_clear()`
      in a try/finally.

### A.5 — Webhook FAILED + `error_report=None` edge: assert `error` key is absent

The current `_notify_webhook` (`pipelex/pipe_run/delivery_executor.py:259`)
only writes `payload["error"]` when `error_report is not None`. The COMPLETED
case is pinned by `test_webhook_omits_error_when_report_is_none`, but the
FAILED case is not — a future regression defaulting `error` to `{}` on FAILED
would slip through.

- [x] In the relevant test (`tests/unit/pipelex/pipe_run/test_delivery_executor.py`),
      add a case dispatching `_notify_webhook` with `status=FAILED` and
      `error_report=None`, then `assert "error" not in payload`.

### A.6 — `WebhookTarget` validator runs construction-only

`pipelex/pipe_run/delivery_assignment.py:30-48`'s `_reject_reserved_keys`
runs at construction time only — there is no `validate_assignment=True` on the
model, so a post-construction `webhook.payload["status"] = "x"` bypasses the
validator. `_notify_webhook` `dict(webhook.payload)` shallow-copies before
override, so the wire payload is safe today, but the contract is implicit.

- [x] Add `test_reserved_key_check_runs_only_at_construction`: construct a
      clean `WebhookTarget`, mutate `webhook.payload["status"] = "x"` in place,
      assert no `ValidationError` is raised. Pins the construction-only
      contract explicitly so a future `validate_assignment=True` toggle gets
      caught as a behavior change.

### Acceptance

`make agent-check` clean; `make agent-test` clean. Six new test cases or
methods land, one regression net per gap. Each has been verified to have teeth
(temporarily breaking the production code makes the test fail).

### ⛔ CHECKPOINT A — STOP, verify, record

- [x] `make agent-check` and `make agent-test` clean.
- [x] Commit as a single test-only commit.
- [x] Append a dated entry to the Session log below.

---

## Phase B — Maintainability refactors

Four small refactors the reviewer flagged. Each is an isolated improvement; do
them in any order. Land as a small ordered series (one commit per refactor) so
each is independently reviewable.

### B.1 — Factor the `WorkflowLog` / `ActivityLog` severity duplication

`pipelex/temporal/log_temporal.py:56-131` declares 14 nearly-identical severity
methods across `WorkflowLog` and `ActivityLog`. They differ only by which
logger they target (`workflow.logger` vs `activity.logger`) and a docstring
substring ("in a workflow" vs "in an activity"). Every new severity level must
be added in two places.

- [x] Move the seven severity methods (`verbose` / `debug` / `dev` / `info` /
      `warning` / `error` / `critical`) onto the `_RequestIdLog` base. Add an
      abstract `_logger` property (or ClassVar) that each subclass overrides
      to point at `workflow.logger` or `activity.logger`. Each method becomes
      a one-liner: `self._logger.log(level=..., msg=content, extra=self._build_extra())`.
- [x] Verify both `WorkflowLog` and `ActivityLog` still satisfy the protocols
      expected by their existing call sites — the public method set is
      unchanged.
- [x] `tests/unit/pipelex/temporal/test_log_temporal_request_id.py` parametrizes
      over all seven severity methods — it should keep passing without
      modification.

### B.2 — Hoist `[error report failed schema validation]` to a module constant

`pipelex/temporal/tprl/temporal_error.py:119` builds the fallback message
inline. The marker is referenced as a stable contract in the function's
docstring and in `docs/under-the-hood/error-model.md`. Anything that wants to
detect the schema-validation fallback on the wire (a test, an ops dashboard,
the documentation) must duplicate the literal string.

- [x] Add `_ERROR_REPORT_VALIDATION_FAILED_MARKER = "[error report failed schema validation]"`
      at module scope in `pipelex/temporal/tprl/temporal_error.py`. Use it in
      the f-string. Update `tests/unit/pipelex/temporal/test_recover_error_report.py`
      (the `test_found_but_invalid_report_dict_synthesizes_unrecoverable` case)
      to import and reference the constant instead of the substring
      `"schema validation"` — pins the exact marker rather than a substring.

### B.3 — Switch `_enrich_error_report_from_cause` to `model_copy(update=...)`

`pipelex/base_exceptions.py:393-434` rebuilds the entire `ErrorReport` via the
constructor with 12 kwargs — 5 copied verbatim from `report`, 7 merged via
`or` from `cause_report`. The five "wrapper-wins" kwargs duplicate the
docstring; a new wrapper-wins field on `ErrorReport` would require editing this
list too.

- [x] Refactor to `return report.model_copy(update={...})` with just the
      cause-merged classification fields. Matches the pattern already in use
      at `pipelex/pipeline/exceptions.py:43-49` (`PipelineExecutionError.to_error_report`).
- [x] Same refactor opportunity in `pipelex/cogt/exceptions.py:87-103`
      (`CogtError.to_error_report` override duplicates 11 of the same
      constructor kwargs to add four CogtError-only fields). Switch to
      `super().to_error_report()` (which runs cause-chain enrichment) followed
      by `.model_copy(update={...})` with just the CogtError-specific fields.
- [x] No observable behavior change. Existing tests must keep passing.

### B.4 — OpenAI/VertexAI title-suffix consistency

`pipelex/plugins/openai/openai_exceptions.py:6-15` declares `_declared_title`
values that drop the trailing "error" / "failed" word that every other curated
title uses (`"AI inference failed"`, `"Library error"`, `"TOML parse error"`,
etc.). The RFC 7807 `title` field is consumer-facing.

- [x] Pick the dominant convention (keep the trailing "error" / "failed") and
      apply it to OpenAI + VertexAI:
      - `OpenAIClientFactoryError._declared_title = "OpenAI client factory error"`
        (was `"OpenAI client factory"`).
      - `VertexAIConfigError._declared_title = "VertexAI configuration error"`
        (was `"VertexAI config"`).
      - `VertexAICredentialsError._declared_title = "VertexAI credentials error"`
        (was `"VertexAI credentials"`).
- [x] Regenerate `docs/errors/` via `.venv/bin/pipelex-dev generate-error-pages`
      — the three affected pages should land with updated title frontmatter.
- [x] If `tests/unit/pipelex/test_pipelex_error_title_and_type_uri.py` asserts
      specific title strings for these classes, update them.

### Acceptance

`make agent-check` clean; `make agent-test` clean. Four refactors land, each
preserving observable behavior. Diff size reductions are visible in the affected
files.

### ⛔ CHECKPOINT B — STOP, verify, record

- [x] `make agent-check` and `make agent-test` clean.
- [x] Each refactor as its own commit.
- [x] Append a dated entry to the Session log below.

---

## Phase C — Pre-existing cleanup surfaced by the review

These items pre-date PR #933. The pre-landing review flagged them per the
project's "Flag and fix existing bugs" rule. They are independent of Phases
A/B — land any time.

### C.1 — Stale TODOs in `pipelex/pipeline/exceptions.py`

Two TODO comments live on `ValidateBundleError`:

- Line 114: `TODO: Currently not caught, but structure is prepared for future
  implementation` (about `pipe_concept_instantiation_errors`).
- Line 128: `TODO: refactor so we don't need this anymore?` (about the
  `pipe_validation_error_data` property documented as "Backwards
  compatibility").

The first never landed. The second contradicts project policy ("No backward
compatibility").

- [x] Decide with the user: land the deferred catch site for
      `pipe_concept_instantiation_errors`, or remove the unused structure.
- [x] For the `pipe_validation_error_data` property: drop it and update callers
      (preferred per policy), or remove the "Backwards compatibility" framing
      and the TODO if the property is genuinely useful as an aggregate getter.

### C.2 — Duplicate handler cascade in `pipelex/pipeline/validate_bundle.py`

`validate_bundle` (lines 103-137) and `validate_bundles_from_directory`
(lines 154-188) carry an identical six-handler `try/except` cascade
(`PipelexInterpreterError`, `PipeFactoryError`, `PipeValidationError`,
`ValidationError`, `PipeRunError`, `DryRunError`) — each translated into
`ValidateBundleError(...)` with the same fields. ~70 lines of pure duplication.
A new handler must be added in two places.

- [x] Extract the handler cascade into a helper
      `_translate_validation_error_to_validate_bundle_error(exc)` (or wrap the
      try-body in a context manager) so both call sites share one source of
      truth.
- [x] Confirm both `validate_bundle` and `validate_bundles_from_directory`
      callers still get identical `ValidateBundleError` instances after the
      refactor.

### C.3 — `BaseModelPayloadConverterError` dead code

`pipelex/temporal/exceptions.py:96` declares
`BaseModelPayloadConverterError(PipelexError)` but no code imports or raises it.
Was already dead in the previous location; the Phase 6 move surfaces the
opportunity to either delete it or wire it into actual error sites in
`pipelex/temporal/temporal_data_converter.py` where unexpected conversion
failures currently surface as generic exceptions.

- [x] Decide: delete the class (one less generated docs page) OR wire it into
      `temporal_data_converter.py` where it would add meaningful classification.

### Acceptance

Each item resolved either by landing the change or by recording a deliberate
"leave as-is" decision in the Session log with rationale.

### ⛔ CHECKPOINT C — STOP, verify, record

- [x] `make agent-check` and `make agent-test` clean.
- [x] Append a dated entry to the Session log below: which items landed, which
      were deliberately left, and why.

---

## Phase D — Design question for the user (do not action without discussion)

### D.1 — STRICT 429 strips `provider_metadata`, losing `retry_after_seconds`

`pipelex/base_exceptions.py:24` strips `provider` / `model` / `provider_metadata`
unconditionally under STRICT disclosure. But for a provider 429 (rate-limit),
`provider_metadata.retry_after_seconds` is actionable safe data the HTTP
adapter needs to emit a useful `Retry-After` header. Under STRICT, the
consumer sees `status=429` with no retry-after.

This is a **design call**, not a bug — STRICT was designed as
"classification-projection, not a path-leak shield", and the trade-off is
deliberate. But for the only HTTP-status code where the response carries an
actionable client header (`Retry-After`), the current STRICT behavior is at
odds with usability.

Options to consider:

- **Option 1.** Preserve a curated subset of `provider_metadata` (just
  `status_code` and `retry_after_seconds`) on the STRICT envelope. Minimal
  scope creep; matches the "provider attribution never belongs on an external
  surface" rule because `retry_after_seconds` is not provider attribution, it
  is a rate-limit hint.
- **Option 2.** Surface `retry_after_seconds` as a top-level field on
  `ErrorReport`, independent of `provider_metadata`. HTTP adapters read it
  whatever the disclosure mode.
- **Option 3.** Leave as-is. STRICT consumers that need `Retry-After` must
  upgrade to VERBOSE on internal-trust boundaries.

- [x] Open this with the user. Decide. Record in the Decisions section below.
- [x] If Option 1 or 2: implement, add a STRICT-passthrough-of-retry-after
      test, regenerate docs if the public surface changes.

---

## Out of scope (recorded, not planned here)

Items the reviewer noted but explicitly did not flag as actionable:

- **VERBOSE webhook payload as default** (`pipelex/pipe_run/delivery_executor.py:251`)
  — design intent: "the receiver decides what to re-expose downstream". A
  `disclosure_mode` field on `WebhookTarget` could opt a target to STRICT, but
  that is a feature, not a fix. Revisit only if a real consumer asks for it.
- **Direct-mode wrapping bare exceptions into webhook** (`pipelex/pipe_run/pipe_run.py:54`)
  — symmetric with Temporal mode by design (the `feedback_always_deliver_failure_notification.md`
  rule). Greptile flagged and lchoquel resolved it during PR #933.
- **Temporal `_log_critical` / `_log_error` unbound `activity_log` / `workflow_log`**
  — explicitly deferred in TODOS Checkpoint 2 ("error-bridge helpers, no
  `job_metadata` in scope; threading `request_id` there is out of scope for
  Item B"). Closing it requires threading `job_metadata` through
  `activity_error_boundary` and `workflow_caller` exception handlers — a
  bigger refactor. Track separately if it ever becomes a blocker.
- **Temporal wire-format version skew** — per `project_temporal_not_shipped.md`,
  Temporal hasn't shipped; rolling-deploy concerns don't apply.
- **`_humanize_class_name` `!= "Error"` guard** — theoretical, no production
  class hits the edge.
- **`_enrich_error_report_from_cause` O(N²) on deep chains** — chains are
  3-5 deep in practice. Sub-microsecond. Only profile if pathological chains
  appear.
- **`error_report_dict_from_details` sentinel-key idea** — superseded by
  Phase 7's heuristic strengthening (all four required keys must be present);
  the lookalike-dict risk window is now narrow enough that adding a sentinel
  key is over-engineering.

---

## Decisions

Record each decision here as it is taken, with date and rationale.

- **2026-05-24 — C.1: Remove unused `pipe_concept_instantiation_errors` infrastructure.** Per project policy "No backward compatibility", the never-populated-in-production field on `ValidateBundleError` + the `pipe_validation_error_data` aggregate (Backwards compatibility) property were both removed. The two callers (`pipelex/cli/agent_cli/commands/agent_output.py`, `pipelex/cli/error_handlers.py`) and the test fixture in `tests/unit/pipelex/cli/test_agent_output.py` were updated. Alternative considered: land the deferred catch site for Pydantic ValidationError in the factory instantiation path — rejected as bigger scope without a concrete need from production.
- **2026-05-24 — C.3: Delete `BaseModelPayloadConverterError`.** Never imported or raised; `temporal_data_converter.py` lets kajson failures bubble raw. Wiring the class into the converter would require adding a speculative try/except, which the project rules explicitly forbid ("Do NOT add try/except speculatively"). Cleaner to delete and regenerate the docs.
- **2026-05-24 — D.1: STRICT preserves curated `provider_metadata` subset (Option 1).** Project `provider_metadata` through a curated subset (just `status_code` + `retry_after_seconds`) on the STRICT envelope. Rationale: these two fields are actionable HTTP client hints (status mapping + `Retry-After` header), not provider attribution, so they don't violate the rule that "provider attribution never belongs on an external surface". Holds for both STRICT branches. Side effect: STRICT payloads no longer round-trip through `from_dict` (the partial `provider_metadata` fails pydantic validation on the required fields), but STRICT was already documented as a lossy projection and the existing `test_strict_does_not_round_trip` only asserted observable fields, not rehydration semantics — updated to read the dict directly. Options 2 (top-level field) and 3 (leave as-is) rejected.

---

## Session log

Append one dated entry per session / checkpoint. Each entry must leave the
next session enough to cold-start: what landed, decisions taken, current code
state, what is broken or deferred, and the exact next action.

### 2026-05-24 — Branch cut + Checkpoint A landed

- **Branch**: cut `feature/post-pr933-followups` from `feature/API-readiness-2` (PR #933 still open against `dev`).
- **Phase A** complete — six regression nets, all verified for teeth (temporarily breaking the production code makes the test fail), restored after each verification:
  - A.1: `tests/integration/pipelex/temporal/test_wf_pipe_router_request_id_logging.py` (new file) — pins the per-invocation `WorkflowLog(request_id=...)` binding in `WfPipeRouter.run` via a real worker, LLM activity mocked to fail. Teeth check: reverting to `WorkflowLog()` makes the test report `request_ids seen: ['None']`.
  - A.2: two new tests in `test_class_level_metadata.py` covering inline subclasses of `PipelexInterpreterError` and `ValidateBundleError`. Teeth check: switching `_authors_caller_facing_message` lookup to `cls.__dict__` (matching the inheritance-bypass pattern of `_declared_title`) fails both subclass cases.
  - A.3: `test_invalid_report_with_empty_message_falls_back_to_exc_chain` in `test_recover_error_report.py`. Teeth check: swapping `or` for `dict.get(..., default)` strips the preamble.
  - A.4: `test_force_load_walk_continues_past_first_failure` in `test_error_pages_generator.py`. Teeth check: adding `break` after the first failure drops the distinct module count to 1.
  - A.5: `test_webhook_omits_error_when_failed_status_with_none_report` in `test_delivery_executor.py`. Teeth check: defaulting `payload["error"] = {}` when report is None makes the test fail.
  - A.6: `test_reserved_key_check_runs_only_at_construction` in `test_delivery_assignment.py`. Pins observed behavior; `validate_assignment=True` alone doesn't trip it (mutation vs assignment), but a stricter regression (immutable payload, custom `__setitem__` validation) would.
- **Status**: `make agent-check` clean, `make agent-test` clean.
- **Next action**: commit Phase A as a single test-only commit, then start Phase B.1.

### 2026-05-24 — Checkpoint B landed

- **Phase B** complete — four refactors, each as its own commit, no observable behavior change:
  - B.1 (`refactor(temporal): hoist severity methods onto _RequestIdLog base`): collapsed the 14 duplicated severity methods on `WorkflowLog` / `ActivityLog` onto `_RequestIdLog` with a `_logger` ClassVar per subclass. Existing parametrized test suite covers both subclasses unchanged.
  - B.2 (`refactor(temporal): hoist error-report validation marker to module constant`): added `_ERROR_REPORT_VALIDATION_FAILED_MARKER` constant in `temporal_error.py`; updated `test_recover_error_report.py` to import the constant.
  - B.3 (`refactor(errors): switch _enrich_error_report_from_cause to model_copy`): both the base implementation and `CogtError.to_error_report` override now use `super().to_error_report()` + `model_copy(update={...})` with just the cause-merged fields. Wrapper-wins fields stay untouched by construction. Verified against unit + integration error-handling tests.
  - B.4 (`fix(errors): make OpenAI/VertexAI titles match the suffix convention`): three `_declared_title` values updated; `docs/errors/` regenerated (4 files diff: 3 pages + index).
- **Status**: `make agent-check` clean, `make agent-test` clean.
- **Next action**: open Phase C.1 — the stale TODOs in `pipeline/exceptions.py` need a decision (land the deferred catch site OR remove the unused structure per "No backward compatibility" policy).

### 2026-05-24 — Checkpoint C landed

- **Phase C** complete — three commits:
  - C.1 (`refactor(errors): drop unused pipe_concept_instantiation_errors infrastructure`): user chose "Remove unused structure" (see Decisions). Dropped the field from `ValidateBundleError`, the iteration loop from `agent_output.py`, the `pipe_validation_error_data` property; inlined `pipe_validation_errors` at the call site in `error_handlers.py`; updated the test fixture.
  - C.2 (`refactor(validate): extract bundle-loading handler cascade to a helper`): both `validate_bundle` and `validate_bundles_from_directory` now wrap their try-body in `with _translate_to_validate_bundle_error():` — single source of truth for the six-handler cascade.
  - C.3 (`refactor(temporal): delete unused BaseModelPayloadConverterError`): dead class deleted; docs regenerated (one orphan page removed).
- **Status**: `make agent-check` clean, `make agent-test` clean.
- **Next action**: open Phase D.1 with the user — STRICT 429 stripping `provider_metadata.retry_after_seconds` is a design call between three options. Do not action without discussion (per the plan).

### 2026-05-24 — Phase D.1 landed (final phase)

- **Phase D.1** complete — single commit `fix(errors): preserve curated provider_metadata subset under STRICT disclosure`. User chose Option 1 (curated subset). Implementation:
  - Removed `provider_metadata` from `_STRICT_PROVIDER_FIELDS` (the always-dropped set).
  - Added `_STRICT_PROVIDER_METADATA_KEPT_FIELDS = {"status_code", "retry_after_seconds"}` and a `_redact_provider_metadata_for_strict` helper.
  - Updated both STRICT branches in `ErrorReport.to_dict` (redacted and caller-facing) to project `provider_metadata` through the curated subset.
  - Updated the `DisclosureMode.STRICT` and `to_dict` docstrings.
  - Added two new tests: `test_strict_preserves_curated_provider_metadata`, `test_strict_omits_provider_metadata_when_only_curated_subset_is_empty`, `test_strict_provider_metadata_dict_carries_http_status_for_adapter`. Updated the existing `test_strict_redacts_non_caller_facing_reports`, `test_strict_strips_provider_fields_even_from_caller_facing_passthrough`, `test_strict_does_not_round_trip` (now asserts dict reads, not rehydration), `test_strict_mode_redacts_detail_and_drops_disclosure_fields` (now asserts the curated metadata rides as an extension member of the problem document).
  - The new `_redact_provider_metadata_for_strict` helper omits `provider_metadata` entirely when both curated fields are unset (no empty-dict on the wire).
- **Caveat captured**: STRICT payloads now break `ErrorReport.from_dict` because the curated `provider_metadata` lacks the required `provider` / `sdk_exception_type` fields. This is per-spec ("STRICT is lossy"), but is a behavior shift from the prior implementation where STRICT was still rehydratable. If a downstream consumer (`pipelex-relay`, `pipelex-api`, etc.) relies on rehydrating STRICT payloads, they need to migrate to reading the dict directly. Worth a heads-up in the PR description.
- **Status**: `make agent-check` clean, `make agent-test` clean. All four phases (A/B/C/D) done.
- **Next action**: this plan file is complete. Open a PR for the branch `feature/post-pr933-followups` once `feature/API-readiness-2` (PR #933) lands and the branch can rebase onto `dev`. Until then, the branch stacks on top of `feature/API-readiness-2`.
