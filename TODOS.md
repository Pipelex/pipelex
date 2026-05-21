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

- [ ] `docs/under-the-hood/error-model.md` — verify the `extra="forbid"` warning no longer claims `recover_error_report()` trims unknown keys. Then read the whole file against the shipped `ErrorReport` / `recover_error_report` / disclosure-mode code and fix any other drift.
- [ ] `pipelex/temporal/exceptions.py` — verify the `UnrecoverableWorkflowFailureError` docstring no longer claims it is synthesized on a `from_dict` version-skew failure. It is synthesized only when no report dict is found at all.
- [ ] `pipelex/temporal/log_temporal.py` — the `WorkflowLog` / `ActivityLog` docstrings claim "activities/workflows read the value off `job_metadata.request_id` and pass it explicitly." No caller does that yet. Soften the docstrings to describe the parameter honestly (accepted; wiring tracked in Phase 2) so a review agent does not flag a false claim.
- [ ] Sweep docstrings in the #931-touched modules for code-doc drift and fix what no longer matches: `base_exceptions.py` (`ErrorReport`, `DisclosureMode`, `to_dict`, `to_problem_document`, `title`, `type_uri`), `temporal_error.py` (`recover_error_report`, `_message_from_exc`, `_find_error_report_dict`), `delivery_executor.py`, `error_pages_generator.py`, `error_module_registry.py`.

### 0.2 — Plan doc `api-companion-revisions.md` coherence

- [ ] Verify §D.1 and "What landed in Stage 2" describe `recover_error_report` correctly (no embedded report → synthesize; found-but-invalid dict → raise as an internal contract bug) and that the `_declared_title` value quoted matches the code.
- [ ] Rewrite §B — it says "Activity logs carry it via a `ContextVar` (same pattern as `session_id`)." That is wrong. State the decided design: `request_id` is transported on `JobMetadata` and threaded explicitly into log calls; no `ContextVar`, because a ContextVar is process-local and does not survive the Temporal serialization boundary.
- [ ] Reconcile the "Current state" Stage checklist with reality: Stages 1-4 landed, Stage 5 (webhook signing) pending. Add a pointer to this `TODOS.md` for the post-review follow-ups so a reader knows where the remaining work lives.
- [ ] Make every "What landed in Stage X" section honest — in particular Stage 1's `request_id` claim must not imply the logging is wired end-to-end when it is not.

### 0.3 — The `wip/error-handling/` hub

- [ ] `wip/error-handling/README.md` — the "Status at a glance" table does not list the API-readiness / `api-companion-revisions.md` track at all, and "What's still open" mentions only the metadata-model long tail. Add the API-readiness track to the table, and rewrite "What's still open" to list the real open items — webhook signing (Stage 5), the STRICT disclosure gap, the webhook-payload collision, the `request_id` wiring, the metadata-model long tail — each linking its tracker doc and/or this `TODOS.md`.
- [ ] Confirm the new trackers (`track-strict-disclosure-input-domain-gap.md`, `track-webhook-payload-collision.md`) are linked from the README and consistent with it.
- [ ] Confirm every `archive-*.md` file reads unambiguously as an archive (point-in-time, superseded). Do NOT rewrite archive contents — only fix a header line if one genuinely reads as a current contract.
- [ ] `changes-for-api-early-draft.md` — add a one-line "superseded — see `api-companion-revisions.md`" banner at the top if it does not already have one, so a review agent never treats the original draft spec as the contract.

### 0.4 — Cross-doc coherence check

- [ ] Final read: `TODOS.md` ↔ `api-companion-revisions.md` "Current state" ↔ `wip/error-handling/README.md` "What's still open" must agree on what is done and what is pending. Resolve any disagreement.
- [ ] `make agent-check` clean (docstring edits can trip formatting/linting).

**Acceptance:** a PR review agent reading the error-handling docs cold gets one coherent story — no doc contradicts the code, no two docs contradict each other, and pending work is clearly marked as pending.

### ⛔ CHECKPOINT 0 — Clean slate verified, STOP and record

- [ ] Run `make agent-check` — must pass.
- [ ] Commit Phase 0 as a single docs-only commit.
- [ ] Tick every Phase 0 box above.
- [ ] Append a dated **Checkpoint 0** entry to the Session log: confirm the doc set is coherent, list any doc deliberately left as-is and why, and the next action (start Phase 1).

---

## Phase 1 — STRICT disclosure: close the INPUT-domain leak (Critical #2)

Full analysis and options: [`wip/error-handling/track-strict-disclosure-input-domain-gap.md`](wip/error-handling/track-strict-disclosure-input-domain-gap.md).

STRICT disclosure mode keys its redaction passthrough on `error_domain == ErrorDomain.INPUT`, but `error_domain` is inherited up the `__cause__` chain by `_enrich_error_report_from_cause`. Two consequences: a domain-less wrapper raised `from` an INPUT cause leaks its own internal `message` through STRICT; and `to_problem_document` echoes `provider` / `model` / `provider_metadata` for INPUT reports even in STRICT.

- [ ] **Decision D1** — pick the Gap 1 fix: Option 1 (per-class `ClassVar` flagging classes that genuinely author caller-facing messages; gate STRICT passthrough on the flag) or Option 2 (stop inheriting `error_domain` onto a domain-less wrapper). Recommended: **Option 1** — it gates redaction on message provenance rather than an inherited classification, and avoids the `http_status` side effects Option 2 carries. Record the choice in the Decisions section.
- [ ] Implement the chosen Gap 1 fix in `pipelex/base_exceptions.py` (`to_dict` STRICT branch, and `_enrich_error_report_from_cause` / the report-construction path as the option requires).
- [ ] Gap 2 — strip `provider` / `model` / `provider_metadata` from the INPUT passthrough branch of `to_dict(DisclosureMode.STRICT)`. An input-classification error has no business carrying provider metadata onto an external surface.
- [ ] Align the `DisclosureMode` docstring in `pipelex/base_exceptions.py` with the implemented redaction set.
- [ ] Tests: a domain-less wrapper (`PipelexUnexpectedError`) raised `from` an INPUT-domain cause must not leak the wrapper's `message` through `to_dict(STRICT)`; `to_problem_document(disclosure_mode=STRICT)` must never emit `provider` / `model` / `provider_metadata` regardless of `error_domain`. Mirror the existing STRICT tests in `tests/unit/pipelex/test_error_report_disclosure_mode.py`.
- [ ] `make agent-check` clean; STRICT-related tests green.
- [ ] Update [`wip/error-handling/track-strict-disclosure-input-domain-gap.md`](wip/error-handling/track-strict-disclosure-input-domain-gap.md) — mark it landed, note the option taken.

**Acceptance:** STRICT never reflects a non-caller-facing message or provider metadata to an external surface, for any `error_domain`. The `DisclosureMode` docstring matches the code.

### ⛔ CHECKPOINT 1 — STOP, verify, record

- [ ] Run `make agent-check` and `make agent-test` — both must pass.
- [ ] Commit Phase 1 as a single coherent commit.
- [ ] Tick every Phase 1 box above.
- [ ] Append a dated **Checkpoint 1** entry to the Session log with: Decision D1 outcome, files touched, the exact redaction behavior now in effect, anything deferred, and the next action (start Phase 2).

---

## Phase 2 — Finish wiring `request_id` into Temporal logs (Plan Item B)

Plan Item B is half-landed. `JobMetadata.request_id`, the `pipeline_run_setup(request_id=...)` kwarg, and the `request_id` kwarg on every `WorkflowLog` / `ActivityLog` method plus `_build_extra` all shipped — but **no pipelex activity or workflow reads `job_metadata.request_id` and passes it to a log call.** The kwarg is dead surface today.

- [ ] **Decision D2** — pick the call-site strategy. Either pass the `request_id` kwarg at each meaningful Temporal log call, or build a per-invocation bound logger/adapter from `job_metadata.request_id` at activity/workflow entry. Recommended: **the bound-adapter approach**, rebuilt every invocation, to avoid threading the kwarg through every call site. It must NOT be a ContextVar and must NOT be module/process state — it is rebuilt per activity/workflow invocation from that invocation's `JobMetadata`. Record the choice.
- [ ] Wire it: at each activity and workflow entry point that has `job_metadata` in scope, read `job_metadata.request_id` and make that invocation's log records carry it via the `_build_extra` → `extra={"request_id": ...}` path.
- [ ] Remove dead surface: if the bound-adapter approach wins, drop the now-unused per-method `request_id` kwargs, or fold them into the adapter — leave no unused parameter and no inaccurate docstring behind.
- [ ] Test: a pipeline run dispatched with a `request_id` produces Temporal activity/workflow log records carrying that `request_id`. Add coverage of the `_build_extra` / logging request_id path — there is none today.
- [ ] Update the docs to reflect Item B fully landed — `api-companion-revisions.md` "What landed" / "Current state", `wip/error-handling/README.md`, and the `log_temporal.py` docstrings (which can now state the wiring as fact).
- [ ] `make agent-check` clean.

**Acceptance:** a run dispatched with a `request_id` has that id on its Temporal log records; no dead `request_id` parameter or inaccurate docstring remains.

### ⛔ CHECKPOINT 2 — STOP, verify, record

- [ ] Run `make agent-check` and `make agent-test` — both must pass.
- [ ] Commit Phase 2 as a single coherent commit.
- [ ] Tick every Phase 2 box above.
- [ ] Append a dated **Checkpoint 2** entry to the Session log with: Decision D2 outcome, the wiring mechanism chosen, files touched, whether the per-method kwargs were kept or dropped, and the next action (start Phase 3).

---

## Phase 3 — Webhook payload reserved-key collision

Full analysis and options: [`wip/error-handling/track-webhook-payload-collision.md`](wip/error-handling/track-webhook-payload-collision.md).

`DeliveryExecutor._notify_webhook` copies the caller's `WebhookTarget.payload` and writes Pipelex-owned keys (`pipeline_run_id`, `status`, `result_url`, `error`) on top. A caller can put any of those keys in their static payload and have the meaning shift silently with delivery status.

- [ ] Implement Option 1 from the tracker: a `field_validator` on `WebhookTarget.payload` in `pipelex/pipe_run/delivery_assignment.py` that rejects the reserved-key set at construction time, with a clear error naming the offending key(s).
- [ ] Tests: constructing a `WebhookTarget` with a reserved key in `payload` raises a validation error; a clean payload passes.
- [ ] `make agent-check` clean.
- [ ] Update [`wip/error-handling/track-webhook-payload-collision.md`](wip/error-handling/track-webhook-payload-collision.md) — mark it landed.

**Acceptance:** a caller cannot register a webhook whose static payload collides with a Pipelex-owned key; the failure is loud and at construction time.

---

## Phase 4 — Test coverage backfill

The `/review` pass found gaps where the refactor removed or never added coverage. Some depend on Phase 2 — do this phase after Phase 2.

- [ ] `recover_error_report` — `tests/integration/pipelex/temporal/test_recover_error_report.py` lost the cases that pinned the old "malformed → None" behavior. Add a case pinning the current contract: a report dict that is *found* but fails `ErrorReport` validation raises `pydantic.ValidationError` (treated as an internal contract bug, not synthesized).
- [ ] `_message_from_exc` (`pipelex/temporal/tprl/temporal_error.py`) — add a test for the `id()`-based cycle guard (a self-referential `__cause__` chain must terminate) and a test for the `repr(exc)` fallback when every message in the chain is empty.
- [ ] `DeliveryActivityArg` — add a focused unit round-trip test (`model_validate_json(model_dump_json())`) with a populated nested `error_report`, so a nested-model serialization regression is caught without a real Temporal worker.
- [ ] Logging `request_id` path — covered by Phase 2's test; confirm it exists and is green here.
- [ ] `make agent-check` and `make agent-test` clean.

**Acceptance:** the behaviors the refactor introduced or changed are pinned by tests; no silent regression path remains for `recover_error_report`, `_message_from_exc`, or the activity-arg round-trip.

### ⛔ CHECKPOINT 3 — STOP, verify, record

Phases 0–4 are a coherent unit: the in-repo finalization of the error-handling overhaul. Phase 5 is a separate cross-repo track.

- [ ] Run `make agent-check` and `make agent-test` — both must pass.
- [ ] Commit Phases 3–4.
- [ ] Tick every Phase 3 and Phase 4 box.
- [ ] Append a dated **Checkpoint 3** entry to the Session log: confirm all in-repo follow-ups are done, list anything still deferred, and state whether Phase 5 (webhook signing) is being picked up now or scheduled separately.
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

- Webhook VERBOSE disclosure to caller-supplied URLs — sending a full `ErrorReport` to an arbitrary unsigned endpoint is partly by design (plan §D.3: the receiver decides what to re-expose) and is mitigated once Phase 5 (signing) lands. No separate task; revisit only if the threat model changes.
- Critical #1 from the `/review` pass (`recover_error_report` raising on a stale report dict) — resolved as not-a-bug: the Temporal integration has never shipped, so there is no prior on-wire schema. Docs are aligned in Phase 0. Nothing else to do.

---

## Decisions

Record each decision here as it is taken, with date and rationale.

- **D1** (Phase 1, Gap 1 fix) — _pending_.
- **D2** (Phase 2, request_id call-site strategy) — _pending_.

---

## Session log

Append one dated entry per session / checkpoint. Each entry must leave the next session enough to cold-start: what landed, decisions taken, current code state, what is broken or deferred, and the exact next action.

- _Not started. First session: branch from `dev` after PR #931 merges, then begin Phase 0._
