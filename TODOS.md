# TODOS — `feature/API-readiness-2`

Follow-up work for the next branch after PR #931 (error-handling overhaul). This plan finalizes the loose ends a `/review` pass on #931 surfaced: a documentation clean slate first, then the deferred Critical #2, the half-wired plan Item B, and the tracked follow-ups.

**Docs come first on purpose.** We work and review step by step. Every time a doc contradicts the code or another doc, the PR review agents (Greptile, Codex, Cubic) get confused and burn the review on noise. Phase 0 makes the error-handling doc set a single coherent description of what shipped and what is still wanted — so every later phase is reviewed against a correct spec.

Each phase is self-contained; checkpoints between them are hard stops where the agent must verify, record state, and make this doc cold-start-safe.

## Branch setup

- Cut `feature/API-readiness-2` from `dev` **after PR #931 has merged**. Every phase below builds on #931's code — the `ErrorReport` BaseModel, `DisclosureMode`, `recover_error_report`, the error-page generator. If you must start before #931 merges, branch from `feature/API-readiness-merge` instead.
- The `/review` pass on #931 left uncommitted doc-alignment edits on `feature/API-readiness-merge` (`pipelex/errors/error_pages_generator.py`, `pipelex/temporal/exceptions.py`, `docs/under-the-hood/error-model.md`, `wip/error-handling/api-companion-revisions.md`, and the new `wip/error-handling/track-strict-disclosure-input-domain-gap.md`). Those should land with #931. Phase 0 below is written to be idempotent — it re-applies anything that did not land, so it does not matter whether those edits made it into #931 or not.

## How to start (cold start)

1. Read this whole file, then read the linked tracker docs under `wip/error-handling/` and `wip/security/`.
2. Check the **Session log** at the bottom — it records what the last session landed and the exact next action.
3. Resume at the first unchecked box. Respect the checkpoints — do not run past a `⛔ CHECKPOINT` without doing its stop-and-record steps.

## Ground rules

- No backward-compat shims. The Temporal integration has never shipped — there is no prior on-wire schema to preserve.
- `request_id` is transported on `JobMetadata`. **Do not introduce a `ContextVar`** for it — a ContextVar is process-local and does not cross the Temporal activity/workflow serialization boundary in distributed execution. (The CLI-delivery track uses a ContextVar legitimately because it is single-process — do not conflate the two.)
- After any code change run `make agent-check`. Use `make agent-test` to verify a phase before its checkpoint.
- Spec vs Blueprint: language rules go on blueprints, authoring convenience on specs (see `pipelex/builder/CLAUDE.md`).

---

## Phase 0 — Documentation coherence pass (clean slate)

No code-behavior changes in this phase — docs and docstrings only. Goal: every error-handling doc and docstring describes either shipped code (accurately) or wanted work (clearly, marked as wanted-not-done). No doc contradicts the code; no two docs contradict each other.

### 0.1 — Reference docs and docstrings must match shipped code

- [x] `docs/under-the-hood/error-model.md` — verify the `extra="forbid"` warning no longer claims `recover_error_report()` trims unknown keys. Then read the whole file against the shipped `ErrorReport` / `recover_error_report` / disclosure-mode code and fix any other drift.
- [x] `pipelex/temporal/exceptions.py` — verify the `UnrecoverableWorkflowFailureError` docstring no longer claims it is synthesized on a `from_dict` version-skew failure. It is synthesized only when no report dict is found at all.
- [x] `pipelex/temporal/log_temporal.py` — the `WorkflowLog` / `ActivityLog` docstrings claim "activities/workflows read the value off `job_metadata.request_id` and pass it explicitly." No caller does that yet. Soften the docstrings to describe the parameter honestly (accepted; wiring tracked in Phase 2) so a review agent does not flag a false claim.
- [x] Sweep docstrings in the #931-touched modules for code-doc drift and fix what no longer matches: `base_exceptions.py` (`ErrorReport`, `DisclosureMode`, `to_dict`, `to_problem_document`, `title`, `type_uri`), `temporal_error.py` (`recover_error_report`, `_message_from_exc`, `_find_error_report_dict`), `delivery_executor.py`, `error_pages_generator.py`, `error_module_registry.py`.

### 0.2 — Plan doc `api-companion-revisions.md` coherence

- [x] Verify §D.1 and "What landed in Stage 2" describe `recover_error_report` correctly (no embedded report → synthesize; found-but-invalid dict → raise as an internal contract bug) and that the `_declared_title` value quoted matches the code.
- [x] Rewrite §B — it says "Activity logs carry it via a `ContextVar` (same pattern as `session_id`)." That is wrong. State the decided design: `request_id` is transported on `JobMetadata` and threaded explicitly into log calls; no `ContextVar`, because a ContextVar is process-local and does not survive the Temporal serialization boundary.
- [x] Reconcile the "Current state" Stage checklist with reality: Stages 1-4 landed, Stage 5 (webhook signing) pending. Add a pointer to this `TODOS.md` for the post-review follow-ups so a reader knows where the remaining work lives.
- [x] Make every "What landed in Stage X" section honest — in particular Stage 1's `request_id` claim must not imply the logging is wired end-to-end when it is not.

### 0.3 — The `wip/error-handling/` hub

- [x] `wip/error-handling/README.md` — the "Status at a glance" table does not list the API-readiness / `api-companion-revisions.md` track at all, and "What's still open" mentions only the metadata-model long tail. Add the API-readiness track to the table, and rewrite "What's still open" to list the real open items — webhook signing (Stage 5), the STRICT disclosure gap, the webhook-payload collision, the `request_id` wiring, the metadata-model long tail — each linking its tracker doc and/or this `TODOS.md`.
- [x] Confirm the new trackers (`track-strict-disclosure-input-domain-gap.md`, `track-webhook-payload-collision.md`) are linked from the README and consistent with it.
- [x] Confirm every `archive-*.md` file reads unambiguously as an archive (point-in-time, superseded). Do NOT rewrite archive contents — only fix a header line if one genuinely reads as a current contract.
- [x] `changes-for-api-early-draft.md` — add a one-line "superseded — see `api-companion-revisions.md`" banner at the top if it does not already have one, so a review agent never treats the original draft spec as the contract.

### 0.4 — Cross-doc coherence check

- [x] Final read: `TODOS.md` ↔ `api-companion-revisions.md` "Current state" ↔ `wip/error-handling/README.md` "What's still open" must agree on what is done and what is pending. Resolve any disagreement.
- [x] `make agent-check` clean (docstring edits can trip formatting/linting).

**Acceptance:** a PR review agent reading the error-handling docs cold gets one coherent story — no doc contradicts the code, no two docs contradict each other, and pending work is clearly marked as pending.

### ⛔ CHECKPOINT 0 — Clean slate verified, STOP and record

- [x] Run `make agent-check` — must pass.
- [x] Commit Phase 0 as a single docs-only commit.
- [x] Tick every Phase 0 box above.
- [x] Append a dated **Checkpoint 0** entry to the Session log: confirm the doc set is coherent, list any doc deliberately left as-is and why, and the next action (start Phase 1).

---

## Phase 1 — STRICT disclosure: close the INPUT-domain leak (Critical #2)

Full analysis and options: [`wip/error-handling/track-strict-disclosure-input-domain-gap.md`](wip/error-handling/track-strict-disclosure-input-domain-gap.md).

STRICT disclosure mode keys its redaction passthrough on `error_domain == ErrorDomain.INPUT`, but `error_domain` is inherited up the `__cause__` chain by `_enrich_error_report_from_cause`. Two consequences: a domain-less wrapper raised `from` an INPUT cause leaks its own internal `message` through STRICT; and `to_problem_document` echoes `provider` / `model` / `provider_metadata` for INPUT reports even in STRICT.

- [x] **Decision D1** — pick the Gap 1 fix: Option 1 (per-class `ClassVar` flagging classes that genuinely author caller-facing messages; gate STRICT passthrough on the flag) or Option 2 (stop inheriting `error_domain` onto a domain-less wrapper). Recommended: **Option 1** — it gates redaction on message provenance rather than an inherited classification, and avoids the `http_status` side effects Option 2 carries. Record the choice in the Decisions section. **→ Decided 2026-05-22: Option 1** (see [Decisions](#decisions)).
- [x] Implement the chosen Gap 1 fix in `pipelex/base_exceptions.py` (`to_dict` STRICT branch, and `_enrich_error_report_from_cause` / the report-construction path as the option requires).
- [x] Gap 2 — strip `provider` / `model` / `provider_metadata` from the INPUT passthrough branch of `to_dict(DisclosureMode.STRICT)`. An input-classification error has no business carrying provider metadata onto an external surface.
- [x] Align the `DisclosureMode` docstring in `pipelex/base_exceptions.py` with the implemented redaction set.
- [x] Tests: a domain-less wrapper (`PipelexUnexpectedError`) raised `from` an INPUT-domain cause must not leak the wrapper's `message` through `to_dict(STRICT)`; `to_problem_document(disclosure_mode=STRICT)` must never emit `provider` / `model` / `provider_metadata` regardless of `error_domain`. Mirror the existing STRICT tests in `tests/unit/pipelex/test_error_report_disclosure_mode.py`.
- [x] `make agent-check` clean; STRICT-related tests green.
- [x] Update [`wip/error-handling/track-strict-disclosure-input-domain-gap.md`](wip/error-handling/track-strict-disclosure-input-domain-gap.md) — mark it landed, note the option taken.

**Acceptance:** STRICT never reflects a non-caller-facing message or provider metadata to an external surface, for any `error_domain`. The `DisclosureMode` docstring matches the code.

### ⛔ CHECKPOINT 1 — STOP, verify, record

- [x] Run `make agent-check` and `make agent-test` — both must pass.
- [x] Commit Phase 1 as a single coherent commit.
- [x] Tick every Phase 1 box above.
- [x] Append a dated **Checkpoint 1** entry to the Session log with: Decision D1 outcome, files touched, the exact redaction behavior now in effect, anything deferred, and the next action (start Phase 2).

---

## Phase 2 — Finish wiring `request_id` into Temporal logs (Plan Item B)

Plan Item B is half-landed. `JobMetadata.request_id`, the `pipeline_run_setup(request_id=...)` kwarg, and the `request_id` kwarg on every `WorkflowLog` / `ActivityLog` method plus `_build_extra` all shipped — but **no pipelex activity or workflow reads `job_metadata.request_id` and passes it to a log call.** The kwarg is dead surface today.

- [x] **Decision D2** — pick the call-site strategy. Either pass the `request_id` kwarg at each meaningful Temporal log call, or build a per-invocation bound logger/adapter from `job_metadata.request_id` at activity/workflow entry. Recommended: **the bound-adapter approach**, rebuilt every invocation, to avoid threading the kwarg through every call site. It must NOT be a ContextVar and must NOT be module/process state — it is rebuilt per activity/workflow invocation from that invocation's `JobMetadata`. Record the choice. **→ Decided 2026-05-22: bound adapter** (see [Decisions](#decisions)).
- [x] Wire it: at each activity and workflow entry point that has `job_metadata` in scope, read `job_metadata.request_id` and make that invocation's log records carry it via the `_build_extra` → `extra={"request_id": ...}` path.
- [x] Remove dead surface: if the bound-adapter approach wins, drop the now-unused per-method `request_id` kwargs, or fold them into the adapter — leave no unused parameter and no inaccurate docstring behind.
- [x] Test: a pipeline run dispatched with a `request_id` produces Temporal activity/workflow log records carrying that `request_id`. Add coverage of the `_build_extra` / logging request_id path — there is none today.
- [x] Update the docs to reflect Item B fully landed — `api-companion-revisions.md` "What landed" / "Current state", `wip/error-handling/README.md`, and the `log_temporal.py` docstrings (which can now state the wiring as fact).
- [x] `make agent-check` clean.

**Acceptance:** a run dispatched with a `request_id` has that id on its Temporal log records; no dead `request_id` parameter or inaccurate docstring remains.

### ⛔ CHECKPOINT 2 — STOP, verify, record

- [x] Run `make agent-check` and `make agent-test` — both must pass.
- [x] Commit Phase 2 as a single coherent commit.
- [x] Tick every Phase 2 box above.
- [x] Append a dated **Checkpoint 2** entry to the Session log with: Decision D2 outcome, the wiring mechanism chosen, files touched, whether the per-method kwargs were kept or dropped, and the next action (start Phase 3).

---

## Phase 3 — Webhook payload reserved-key collision

Full analysis and options: [`wip/error-handling/track-webhook-payload-collision.md`](wip/error-handling/track-webhook-payload-collision.md).

`DeliveryExecutor._notify_webhook` copies the caller's `WebhookTarget.payload` and writes Pipelex-owned keys (`pipeline_run_id`, `status`, `result_url`, `error`) on top. A caller can put any of those keys in their static payload and have the meaning shift silently with delivery status.

- [x] Implement Option 1 from the tracker: a `field_validator` on `WebhookTarget.payload` in `pipelex/pipe_run/delivery_assignment.py` that rejects the reserved-key set at construction time, with a clear error naming the offending key(s).
- [x] Tests: constructing a `WebhookTarget` with a reserved key in `payload` raises a validation error; a clean payload passes.
- [x] `make agent-check` clean.
- [x] Update [`wip/error-handling/track-webhook-payload-collision.md`](wip/error-handling/track-webhook-payload-collision.md) — mark it landed.

**Acceptance:** a caller cannot register a webhook whose static payload collides with a Pipelex-owned key; the failure is loud and at construction time.

---

## Phase 4 — Test coverage backfill

The `/review` pass found gaps where the refactor removed or never added coverage. Some depend on Phase 2 — do this phase after Phase 2.

- [x] `recover_error_report` — `tests/integration/pipelex/temporal/test_recover_error_report.py` lost the cases that pinned the old "malformed → None" behavior. Add a case pinning the current contract: a report dict that is *found* but fails `ErrorReport` validation raises `pydantic.ValidationError` (treated as an internal contract bug, not synthesized).
- [x] `_message_from_exc` (`pipelex/temporal/tprl/temporal_error.py`) — add a test for the `id()`-based cycle guard (a self-referential `__cause__` chain must terminate) and a test for the `repr(exc)` fallback when every message in the chain is empty.
- [x] `DeliveryActivityArg` — add a focused unit round-trip test (`model_validate_json(model_dump_json())`) with a populated nested `error_report`, so a nested-model serialization regression is caught without a real Temporal worker.
- [x] Logging `request_id` path — covered by Phase 2's test; confirm it exists and is green here.
- [x] `make agent-check` and `make agent-test` clean.

**Acceptance:** the behaviors the refactor introduced or changed are pinned by tests; no silent regression path remains for `recover_error_report`, `_message_from_exc`, or the activity-arg round-trip.

### ⛔ CHECKPOINT 3 — STOP, verify, record

Phases 0–4 are a coherent unit: the in-repo finalization of the error-handling overhaul. Phase 5 is a separate cross-repo track.

- [x] Run `make agent-check` and `make agent-test` — both must pass.
- [x] Commit Phases 3–4.
- [x] Tick every Phase 3 and Phase 4 box.
- [x] Append a dated **Checkpoint 3** entry to the Session log: confirm all in-repo follow-ups are done, list anything still deferred, and state whether Phase 5 (webhook signing) is being picked up now or scheduled separately.
- [ ] At this point the in-repo work is shippable. Decide with the user whether to open a PR for `feature/API-readiness-2` now and run Phase 5 on its own branch, or continue.

---

## Phase 5 — Webhook signing (Plan Item F / Stage 5) — separate cross-repo track

This is the last unshipped stage of the original error-handling plan. It is **cross-repo** (pipelex side + the API side land in coordinated lockstep) and has its own design and checkpoints. Treat it as an independent track — it can land on its own schedule and does not block Phases 0–4.

- [ ] Read [`wip/security/webhook-signing.md`](wip/security/webhook-signing.md) end to end — it is the authoritative plan for this work.
- [ ] Follow that doc's own phases and checkpoints. Do not duplicate them here.
- [ ] Coordinate the cross-repo PRs (pipelex + API) so the signing secret and verification land together.

**Acceptance:** as defined in `wip/security/webhook-signing.md`.

---

## Minor follow-ups (low priority — batch into any checkpoint)

- [ ] `pascal_case_to_kebab` acronym collision — `LLMError` and `LlmError` both kebab to `llm-error`, so two such classes would share a `type_uri` and overwrite each other's generated doc page. It is caught reactively by `test_pipelex_error_type_uri_uniqueness`. Add a defensive assert in `error_pages_generator.generate_error_pages` that fails loudly if two target classes resolve to the same slug, and a short note near `PipelexError` warning that acronym-casing variants of an existing error class name collide.
- [ ] `error_module_registry` discovery fragility — `_NON_STANDARD_ERROR_MODULES` is a hardcoded list that goes stale silently; a new error class outside an `exceptions.py` / `*_errors.py` file and not added to the tuple is omitted from generated docs and from the uniqueness check. Add a test asserting every `PipelexError` subclass reachable after a full app import is also reachable via `iter_pipelex_error_subclasses()`, so the list cannot drift unnoticed. Optionally switch the filesystem scan to `pkgutil.walk_packages` for install-layout robustness.

---

## Out of scope (recorded, not planned here)

- Webhook VERBOSE disclosure to caller-supplied URLs — sending a full `ErrorReport` to the run caller's own endpoint is by design (plan §D.3: the endpoint belongs to the caller, who already owns the run data; the receiver decides what to re-expose). Webhook signing (Phase 5) is orthogonal — it authenticates origin, it does not reduce disclosure. No separate task; revisit only if the threat model changes.
- Critical #1 from the `/review` pass (`recover_error_report` raising on a stale report dict) — resolved as not-a-bug: the Temporal integration has never shipped, so there is no prior on-wire schema. Docs are aligned in Phase 0. Nothing else to do.

---

## Decisions

Record each decision here as it is taken, with date and rationale.

- **D1** (Phase 1, Gap 1 fix) — **Option 1**, decided 2026-05-22. Add a per-class `ClassVar` flagging error classes that genuinely author caller-facing messages, and gate the STRICT-disclosure passthrough on that flag instead of on the inherited `error_domain == INPUT`. Rationale: keys redaction on the *provenance of the message* rather than an inherited classification, and avoids the `http_status` side effects Option 2 (dropping `error_domain` inheritance for domain-less wrappers) would carry.
- **D2** (Phase 2, request_id call-site strategy) — **Bound adapter**, decided 2026-05-22. `WorkflowLog` / `ActivityLog` gain an instance-level `request_id` (held by a shared `_RequestIdLog` base), built once per workflow/activity invocation from `job_metadata.request_id`; the dead per-method `request_id` kwargs are dropped. Rationale: a new log call added inside a wired entry point picks up `request_id` automatically — no per-call threading, nothing to forget — and the per-method kwarg was unused dead surface.

---

## Session log

Append one dated entry per session / checkpoint. Each entry must leave the next session enough to cold-start: what landed, decisions taken, current code state, what is broken or deferred, and the exact next action.

- **2026-05-22 — Checkpoint 0 (Phase 0 complete).** Documentation coherence pass landed as a single docs-only commit on `feature/API-readiness-2`. No code-behavior change — docstrings, comments, and markdown only. `make agent-check` clean (pyright + mypy: 0 errors).

  **Drift found and fixed:**

    - `docs/under-the-hood/error-model.md` — `ErrorReport` now described as a frozen Pydantic *model* (was "dataclass", stale since the Stage 3 `BaseModel` conversion); added the `title` / `type_uri` rows to the field table (they were missing). The `extra="forbid"` warning was already correct — it does not claim `recover_error_report()` trims unknown keys.
    - `pipelex/temporal/log_temporal.py` — softened the `WorkflowLog` / `ActivityLog` docstrings: the `request_id` kwarg is accepted but not yet threaded by any caller (wiring is Phase 2).
    - `pipelex/base_exceptions.py` — fixed a stale inline comment on `_declared_type_uri` ("bootstrap-registered errors base URI" → the `URLs.error_docs_base` constant; `type_uri()` is pure since the `ErrorManager` removal).
    - `pipelex/temporal/tprl/temporal_error.py` — dropped two stale references to the removed in-process `PipeRouter` retry loop (`TemporalError` class docstring + `_is_non_retryable`).
    - `api-companion-revisions.md` — rewrote §B Acceptance (`request_id` rides on `JobMetadata` and is threaded explicitly into log calls; **no `ContextVar`**, because a ContextVar is process-local and does not survive the Temporal serialization boundary); made the Stage 1 `request_id` claim honest (kwarg accepted, not wired end to end); rewrote "Net to the API team" to point at this `TODOS.md` for the post-review follow-ups.
    - `wip/error-handling/README.md` — added the API-readiness track to the "Status at a glance" table; rewrote "What's still open" to list webhook signing, the STRICT-disclosure gap, the webhook-payload collision, the `request_id` wiring, and the metadata-model long tail, each linking its tracker.
    - `wip/error-handling/archive-error-handling-2.md` — added an `ARCHIVED — COMPLETE` header line (the only archive whose title still read as a current plan).
    - `wip/error-handling/changes-for-api-early-draft.md` — added a "superseded — see `api-companion-revisions.md`" banner.

  **Verified correct, left as-is:** `pipelex/temporal/exceptions.py` `UnrecoverableWorkflowFailureError` docstring (already states it is synthesized only when no report dict is found); `base_exceptions.py` / `delivery_executor.py` / `error_pages_generator.py` / `error_module_registry.py` docstrings (swept — no drift). **Deliberate omission:** `error-model.md` does not yet document `DisclosureMode` / `to_problem_document` — not a contradiction (an under-the-hood doc need not be exhaustive), and Phase 1 changes STRICT behavior, so documenting it now would only be rewritten.

  **Coherence:** `TODOS.md`, `api-companion-revisions.md` "Current state", and `README.md` "What's still open" now agree — Stages 1-4 landed via PR #931; pending = webhook signing (Stage 5) + the four `/review` follow-ups.

  **Decisions:** none taken — D1 (Phase 1) and D2 (Phase 2) remain pending.

  **Next action:** start **Phase 1** — STRICT disclosure INPUT-domain leak. Take **Decision D1** first (recommended: Option 1 — per-class `ClassVar` flagging caller-facing-message authors).

- **2026-05-22 — Decision D1 recorded.** Per the user, Decision D1 is **Option 1** (see the Decisions section for the full rationale); the Phase 1 D1 box is ticked to reflect it. Phase 1 **implementation is not started** — no implementation boxes ticked, no code touched. Next action: begin Phase 1 (STRICT disclosure INPUT-domain leak) at the first unticked box (implement the Gap 1 fix).

- **2026-05-22 — Checkpoint 1 (Phase 1 complete).** STRICT-disclosure INPUT-domain leak closed on `feature/API-readiness-2` as a single commit. `make agent-check` clean (pyright + mypy: 0 errors); `make agent-test` full suite green.

  **Decision D1:** Option 1, implemented exactly as decided.

  **What landed:**

    - `pipelex/base_exceptions.py` — new `PipelexError._authors_caller_facing_message` `ClassVar` (default `False`) and new `ErrorReport.caller_facing_message: bool` field. `to_error_report()` sets the field from the class flag; `_enrich_error_report_from_cause` carries it **wrapper-wins** — never inherited from the `__cause__` chain, since it tracks the provenance of `report.message` (always the wrapper's own message). `to_dict(STRICT)` now gates the `message` passthrough on `caller_facing_message`, not on `error_domain == INPUT`.
    - **Gap 2:** new `_STRICT_PROVIDER_FIELDS` constant — `provider` / `model` / `provider_metadata` are stripped from the STRICT caller-facing passthrough branch too (already absent from the redacted branch). STRICT now never emits provider metadata for any `error_domain`.
    - `caller_facing_message` is serialized **only when `True`** (popped from `to_dict` output otherwise), so non-caller-facing reports — the common case — serialize identically to before; `from_dict` defaults it back to `False`, so the round-trip holds. `to_problem_document` never echoes it (new `_PROBLEM_DOCUMENT_OMITTED_FIELDS`) — it is internal redaction plumbing, not consumer classification.
    - `pipelex/core/interpreter/exceptions.py` (`PipelexInterpreterError`) and `pipelex/pipeline/validate_bundle.py` (`ValidateBundleError`) — the two INPUT-domain classes — set `_authors_caller_facing_message = True`. `BundleElaboratorError` inherits it (normal inheritance, unlike `_declared_title`). All other classes keep the safe `False` default.
    - `pipelex/cogt/exceptions.py` — `CogtError.to_error_report()` override threads `caller_facing_message` through too (resolves to `False`).
    - Docstrings: `DisclosureMode`, `ErrorReport.to_dict` / `to_problem_document`, `PipelexError._enrich_error_report_from_cause`, and the module constant comments rewritten to describe provenance-gated redaction.

  **Redaction behavior now in effect (STRICT):** `provider` / `model` / `provider_metadata` always dropped. If `caller_facing_message` — keep `message` + `user_action` + stable identifiers. Else — `message` → `INTERNAL_ERROR_PLACEHOLDER`, drop `user_action`, keep only the stable identifiers (`error_type` / `error_domain` / `error_category` / `retryable` / `title` / `type_uri`).

  **Tests:** `tests/unit/pipelex/test_error_report_disclosure_mode.py` rewritten for the new contract — includes the regression pin (`PipelexUnexpectedError` raised `from` a `PipelexInterpreterError` → report classified `error_domain=INPUT` but `caller_facing_message=False` → message redacted) and the Gap 2 pin (caller-facing passthrough strips provider fields). `test_error_report_problem_document.py` — old `INPUT`-passthrough test replaced; added STRICT-never-emits-provider-fields and `caller_facing_message`-never-an-extension-member tests. `test_class_level_metadata.py` — added a `caller_facing_message` class-level parametrized test.

  **Tracker:** `wip/error-handling/track-strict-disclosure-input-domain-gap.md` marked landed (banner + Acceptance checkboxes ticked).

  **Deferred / not done:** Only `PipelexInterpreterError` and `ValidateBundleError` are flagged caller-facing — the exact two INPUT-domain classes the tracker named. Classes like `MthdsDecodeError` (TOML decode) author arguably-caller-facing messages but are not flagged: the safe default redacts them, which is a usability nit, not a leak, and STRICT is not rendered for those surfaces today. Widening the flag set is a future follow-up if it proves needed.

  **Decisions:** D1 done. **D2 (Phase 2) still pending.**

  **Next action:** start **Phase 2** — finish wiring `request_id` into Temporal logs. Take **Decision D2** first (recommended: bound-adapter approach, rebuilt per activity/workflow invocation).

- **2026-05-22 — Phase 1 follow-up: `MthdsDecodeError` collapsed into `PipelexInterpreterError`.** Resolves the inconsistency flagged in the Checkpoint 1 "Deferred" note. `MthdsDecodeError` was a one-line `TomlError` subclass raised in a single place (`interpreter.py`) as a verbatim field-for-field re-wrap of `TomlError` — it added no context, sat in the wrong type family (`ToolError` lineage → no `error_domain`, so a caller's broken-TOML `.mthds` was classified as a 500 instead of a 422), and forced `agent_output.py` to carry a manual `"MthdsDecodeError": "input"` classification patch.

  Per the user's decision, deleted the class. `interpreter.py` now formats the TOML line/column into the message and raises `PipelexInterpreterError` directly (already `error_domain=INPUT` + `caller_facing_message=True`); the original `TomlError` stays on the `__cause__` chain. The four `except MthdsDecodeError` blocks in `validate_bundle.py` fold into the existing `except PipelexInterpreterError` clauses (identical resulting `ValidateBundleError`, same message); the three CLI `except (PipelexInterpreterError, MthdsDecodeError)` tuples collapse to `except PipelexInterpreterError`; the `agent_output.py` hint + domain patch entries are removed; the `invalid_mthds.py` test cases expect `PipelexInterpreterError`. `docs/errors/` regenerated via `pipelex-dev generate-error-pages` (orphan `mthds-decode-error.md` removed, `index.md` updated). `make agent-check` clean; `make agent-test` green. There is now one interpreter-input error class, correctly classified — no `agent_output.py` patch needed.

- **2026-05-22 — Phase 1 follow-up: `/code-review` pass.** An xhigh-effort `/code-review` of the Phase 1 + `MthdsDecodeError` commits found no runtime bug but flagged doc-coherence regressions: the Phase 1 STRICT-behavior change had updated only `track-strict-disclosure-input-domain-gap.md` and this file, leaving `CHANGELOG.md`, `wip/error-handling/api-companion-revisions.md`, and `wip/error-handling/README.md` still describing the old `error_domain == INPUT` passthrough. Fixed all three to describe the provenance-gated (`caller_facing_message`) rule; `README.md` "What's still open" no longer lists the now-landed STRICT gap (items renumbered). Also restored an `error_category`-retention assertion that the STRICT-redaction test rewrite had dropped. **Two findings left as judgment calls, not acted on:** (4) `bundle_elaborator.py:81` raises an internal "...this is a bug" invariant assertion as `BundleElaboratorError`, which inherits `caller_facing_message=True`, so STRICT would reflect that internal message — it is a defense-in-depth guard the code comments call "unreachable today"; the clean fix is to raise `PipelexUnexpectedError` there. (5) `to_dict(STRICT)` of a caller-facing report emits the internal `caller_facing_message: true` flag onto the lossy projection (harmless boolean; `to_problem_document` already scrubs it via `_PROBLEM_DOCUMENT_OMITTED_FIELDS`). `make agent-check` clean. Next action unchanged: start **Phase 2**.

- **2026-05-22 — Phase 1 follow-up: applied review findings 4 & 5.** The two `/code-review` findings previously left as judgment calls are now fixed. (4) `bundle_elaborator.py:81` — the internal "…this is a bug" nested-directive guard now raises `PipelexUnexpectedError` instead of `BundleElaboratorError`. It is a genuine internal-invariant violation, so it no longer rides the caller-facing `PipelexInterpreterError` path (`interpreter.py`'s `except BundleElaboratorError` no longer catches it — it surfaces as an unexpected error, 500, message redacted under STRICT, which is correct). The other `BundleElaboratorError` raises (caller-facing collision / invalid-bundle messages) are unchanged. (5) `to_dict(STRICT)` of a caller-facing report no longer emits the internal `caller_facing_message` flag — new `_STRICT_PASSTHROUGH_DROPPED_FIELDS` constant drops it alongside the provider fields; the flag rides only the VERBOSE round-trip format. The STRICT-passthrough test assertion was flipped to pin its absence. `make agent-check` clean; `make agent-test` green. Next action unchanged: start **Phase 2**.

- **2026-05-22 — Checkpoint 2 (Phase 2 complete).** `request_id` log wiring finished on `feature/API-readiness-2` as a single commit. `make agent-check` clean (pyright + mypy: 0 errors); `make agent-test` full suite green.

  **Decision D2:** bound adapter — implemented as decided (see the Decisions section).

  **What landed:**

    - `pipelex/temporal/log_temporal.py` — new `_RequestIdLog` base holds an instance-level `request_id`; `WorkflowLog` / `ActivityLog` subclass it. `_build_extra` is now an instance method reading the bound `request_id`. The per-method `request_id` kwarg — dead surface, no caller ever passed it — is **dropped** from every log method. The module-level `workflow_log` / `activity_log` singletons stay, unbound (`request_id is None`), for call sites with no `job_metadata` in scope.
    - `pipelex/temporal/tprl_pipe/wf_pipe_run.py` and `wf_pipe_router.py` — the workflow entry points that log. Each `run()` builds a per-invocation `workflow_log = WorkflowLog(request_id=<job_metadata>.request_id)` as its first statement; every existing `workflow_log.*` call in the function picks it up unchanged (the local shadows nothing — the import is now the `WorkflowLog` class). `WfPipeRun` reads `pipe_job.job_metadata.request_id`; `WfPipeRouter` reads `workflow_arg.job_metadata.request_id`.
    - Activities were checked: no Temporal activity logs via `activity_log` today (only `TemporalError._log_*` does, and it has no `job_metadata`), so there is no activity entry point to wire — `ActivityLog` keeps the symmetric bound capability for when one appears.

  **Wiring mechanism:** per-invocation bound `WorkflowLog`, rebuilt every workflow `run()` from that invocation's `JobMetadata` — no `ContextVar`, no module/process state. A new log call added inside a wired entry point carries `request_id` automatically.

  **Per-method kwargs:** dropped (not kept). `request_id` is held as instance state on the bound adapter; the kwargs were unused dead surface.

  **Tests:**

    - `tests/unit/pipelex/temporal/test_log_temporal_request_id.py` — pins the `_build_extra` path: a bound `WorkflowLog` / `ActivityLog` packs `extra={"request_id": ...}` into the log call, an unbound one passes `extra=None`.
    - `tests/integration/pipelex/temporal/test_wf_pipe_run_request_id_logging.py` — end-to-end: dispatches `WfPipeRun` (failing-router stub, modeled on `test_wf_pipe_run_failure_path.py`) with a `request_id` on `job_metadata`, captures the `temporalio.workflow` logger, asserts records carry `record.request_id`. Verified to have teeth — temporarily unbinding the logger made it fail (`request_ids seen: ['None']`), then reverted.

  **Docs:** `api-companion-revisions.md` §B Acceptance + the Stage 1 `WorkflowLog`/`ActivityLog` bullet + the "Net to the API team" post-review-follow-ups bullet rewritten to describe the landed wiring; `wip/error-handling/README.md` "What's still open" — the `request_id` log-wiring item removed, items renumbered; `log_temporal.py` docstrings state the wiring as fact.

  **Deferred / not done:** `TemporalError._log_critical` / `_log_error` (`temporal_error.py`) still log via the unbound singletons — they are error-bridge helpers, not entry points, and have no `job_metadata` in scope; threading `request_id` there is out of scope for Item B. The `wf_test_*` workflows likewise stay unbound (test infra, no inbound request id).

  **Decisions:** D1 + D2 done.

  **Next action:** start **Phase 3** — webhook payload reserved-key collision. Full analysis and options in [`wip/error-handling/track-webhook-payload-collision.md`](wip/error-handling/track-webhook-payload-collision.md); implement Option 1 (a `field_validator` on `WebhookTarget.payload` rejecting the reserved-key set at construction time).

- **2026-05-22 — Phase 2 follow-up: `/code-review` pass.** An xhigh-effort `/code-review` of the Phase 2 commit (5-angle + sweep) found **no correctness bugs** — the `request_id` wiring, the `WorkflowLog` / `ActivityLog` refactor, and both tests verified clean across line-by-line, removed-behavior, cross-file, language-pitfall, and wrapper-correctness angles (all 7 method bodies confirmed to route to the right logger at the right level; the dropped per-method kwarg confirmed dead surface with no caller). Two low-severity test-hygiene tweaks applied: the integration test's `addHandler` / `setLevel` moved inside the `try` so the `finally` restore is structurally airtight; the unit test (`test_log_temporal_request_id.py`) parametrized over all seven severity methods — was `.info()` only — so 28 cases now pin every method's level + `extra`. `make agent-check` clean; both test files green. Next action unchanged: start **Phase 3**.

- **2026-05-22 — Checkpoint 3 (Phases 3 & 4 complete).** The in-repo finalization of the error-handling overhaul is done on `feature/API-readiness-2`, landed as a single coherent commit. `make agent-check` clean (pyright + mypy: 0 errors); `make agent-test` full suite green.

  **Phase 3 — webhook payload reserved-key collision:**

    - `pipelex/pipe_run/delivery_assignment.py` — new `_RESERVED_WEBHOOK_PAYLOAD_KEYS` frozenset (`pipeline_run_id` / `status` / `result_url` / `error`) and a `field_validator` (`_reject_reserved_keys`, `mode="after"`) on `WebhookTarget.payload` that raises a `ValueError` naming the offending key(s) at construction time. A misconfigured webhook now fails when the `DeliveryAssignment` is built, not silently at delivery time. Option 1 from the tracker, implemented as planned.
    - `tests/unit/pipelex/pipe_run/test_delivery_assignment.py` — added to `TestDeliveryAssignment`: a parametrized reject test (one case per reserved key), a multi-collision test (the error names every offending key), and a clean-payload pass test.
    - Tracker `track-webhook-payload-collision.md` — marked landed (banner added).

  **Phase 4 — test coverage backfill:**

    - `recover_error_report` — `tests/unit/pipelex/temporal/test_recover_error_report.py` gained `test_found_but_invalid_report_dict_raises_validation_error`: a dict that `_find_error_report_dict` accepts (`error_type` + `message`) but that fails `ErrorReport` validation (missing required `title` / `type_uri`) raises `pydantic.ValidationError` — pins the current contract that a found-but-invalid report is an internal contract bug, not synthesized away. (The TODOS Phase 4 line names this file under `tests/integration/` — stale path; the file is and always was under `tests/unit/`. Harmless.)
    - `_message_from_exc` — new `tests/unit/pipelex/temporal/test_message_from_exc.py` (`TestMessageFromExc`): the `id()`-based cycle guard (a self-referential `__cause__` chain terminates) and the `repr(exc)` fallback (every message in the chain empty). Imports the private function with the codebase's established `# noqa: PLC2701  # pyright: ignore[reportPrivateUsage]` pattern.
    - `DeliveryActivityArg` — new `tests/unit/pipelex/temporal/test_delivery_activity_arg.py` (`TestDeliveryActivityArg`): a focused JSON round-trip (`model_validate_json(model_dump_json())`) with a populated nested `ErrorReport` (incl. a nested `UserAction`), catching a nested-model serialization regression without a live Temporal worker.
    - Logging `request_id` path — confirmed `tests/unit/pipelex/temporal/test_log_temporal_request_id.py` (from Phase 2) exists and is green (28 parametrized cases).

  **Doc coherence (beyond the strict checklist, for clean-slate consistency):** `wip/error-handling/README.md` "What's still open" + "Status at a glance" — Phases 3-4 removed from the open list, items renumbered (only webhook signing + the metadata-model long tail remain open); `api-companion-revisions.md` "Net to the API team" — the post-review follow-ups now all marked landed; `CHANGELOG.md` `[Unreleased]` — the delivery-webhook entry gained a sentence noting reserved keys are now rejected at construction (the webhook feature is unreleased, so this is a constraint on a new feature, not a breaking change to shipped software).

  **Deferred / not done:** Nothing from Phases 0-4. The two "Minor follow-ups" (`pascal_case_to_kebab` acronym collision; `error_module_registry` discovery fragility) are still open — TODOS marks them low-priority and batchable into any checkpoint; left for a future pass. Phase 5 (webhook signing) is the separate cross-repo track, untouched.

  **Decisions:** D1 + D2 done (Phases 1-2). No new decision in Phases 3-4.

  **Next action:** All in-repo follow-ups (Phases 0-4) are done — `feature/API-readiness-2` is shippable. **Decision pending with the user:** open a PR for `feature/API-readiness-2` now and run Phase 5 (webhook signing) on its own branch, or continue into Phase 5 on this branch. Phase 5 is cross-repo (pipelex + API in lockstep) per [`wip/security/webhook-signing.md`](wip/security/webhook-signing.md).
