# API handoff — message drafts for `feature/API-readiness-2`

> The drafts below were written when the execution ledger lived at the repo root as `_for_api/TODOS.md`. That file was archived 2026-05-28 to `_for_api/wip/error-handling/archive-todos-api-readiness-2.md` — translate any `TODOS.md` path reference below to the archived location if reusing these drafts.

Two forms below — pick the one matching the channel. Both point at source docs rather than restating them.

---

## Form 1 — human (Slack / email)

**Subject:** `feature/API-readiness-2` ready for review — error-handling finalization + error-class refactor

Hey team — the follow-up branch to PR #931 is ready. It bundles the in-repo finalization of the error-handling overhaul (Phases 0–4 of pipelex `_for_api/TODOS.md`) and a structural refactor of where error classes live in the source tree (Phase 6).

**Things to be aware of on the API side:**

- **STRICT disclosure keying changed.** `ErrorReport.to_dict(STRICT)` / `to_problem_document(STRICT)` now key the `message` passthrough on a per-class `caller_facing_message` flag, not on `error_domain == INPUT`. Only `PipelexInterpreterError` / `ValidateBundleError` are flagged caller-facing today; everything else gets the redacted placeholder. Provider metadata (`provider` / `model` / `provider_metadata`) is now stripped under STRICT unconditionally. Background: `_for_api/wip/error-handling/track-strict-disclosure-input-domain-gap.md`.
- **`WebhookTarget.payload` rejects reserved keys at construction** — `pipeline_run_id` / `status` / `result_url` / `error`. Loud `ValidationError`, not a silent overwrite at delivery. Background: `_for_api/wip/error-handling/track-webhook-payload-collision.md`.
- **`request_id` is now end-to-end through Temporal workflow logs.** `WfPipeRun` / `WfPipeRouter` build a per-invocation `WorkflowLog` from `JobMetadata.request_id` at entry; every workflow log record carries it in `extra`. The `webhook.payload["request_id"]` piggyback can be dropped — `request_id` rides natively now.
- **Error class import paths moved (Phase 6).** Every `PipelexError` subclass now lives in `exceptions.py` or `<topic>_exceptions.py`. `MthdsDecodeError` is **deleted** — fold any `except MthdsDecodeError` into `except PipelexInterpreterError`. Class names are unchanged; only module paths shifted. The Checkpoint 6 entry in `_for_api/TODOS.md` enumerates every move.

**Pending cross-repo work** — **Webhook signing** (Phase 5 / Item F). 3-step rollout per `_for_api/wip/security/webhook-signing.md`: receiver-side dual-format verification ships first (pipelex-api), then pipelex worker switches to body-signing, then drop legacy. Independent of this PR; pick a window when you have bandwidth.

PR: [URL once opened]
Authoritative tracker: `pipelex/_for_api/TODOS.md`
Contract doc (the one to read first): `pipelex/_for_api/wip/error-handling/api-companion-revisions.md`

— Louis

---

## Form 2 — agent prompt (paste into Claude Code in `pipelex-api/`)

The pipelex branch `feature/API-readiness-2` has landed (PR [URL]). It is the in-repo finalization of the error-handling overhaul (Phases 0–4 of pipelex `_for_api/TODOS.md`) plus a Phase 6 structural refactor of where error classes live. Your job in `pipelex-api/` is to adapt this repo to the new pipelex surface: bump the `pipelex` pin, fix any broken imports, and update any code that relied on the old STRICT-disclosure keying or webhook-payload semantics.

### Read first — in the sibling pipelex repo

The pipelex repo lives side-by-side with `pipelex-api/`. The work happened on a worktree at `../_for_api/` (or look for `feature/API-readiness-2` in `../pipelex/`). Read these in order:

1. `_for_api/wip/error-handling/api-companion-revisions.md` — the **contract** for what pipelex exposes to API consumers. Authoritative. Supersedes `changes-for-api-early-draft.md` (banner at the top of the draft confirms this).
2. `_for_api/TODOS.md` — phase-by-phase changes. The Session log entries at the bottom are ground truth for what shipped.
3. `_for_api/wip/error-handling/README.md` — current state of the error-handling tracks.
4. `_for_api/wip/error-handling/track-strict-disclosure-input-domain-gap.md` — STRICT keying shift.
5. `_for_api/wip/error-handling/track-webhook-payload-collision.md` — webhook reserved-key validator.
6. `_for_api/wip/security/webhook-signing.md` — the cross-repo Phase 5 plan (NOT in this PR; separate coordination).

Then `git log main..feature/API-readiness-2 --oneline` in the pipelex worktree to see the commit shape.

### What changed that pipelex-api needs to react to

**1. STRICT disclosure keying.** `to_dict(STRICT)` and `to_problem_document(STRICT)` now key the `message` passthrough on a per-class `caller_facing_message` flag (provenance) rather than `error_domain == INPUT` (inherited classification). Only `PipelexInterpreterError` and `ValidateBundleError` are flagged caller-facing today. For everything else under STRICT: `message` is replaced with `"An internal error occurred."`, `user_action` is dropped, stable identifiers are kept. Provider metadata (`provider` / `model` / `provider_metadata`) is now stripped under STRICT unconditionally. Action: review any path that calls `to_dict(STRICT)` / `to_problem_document(STRICT)`. If it relied on `error_domain == INPUT` to surface caller-facing copy, that reasoning is gone — trust the projected dict.

**2. `WebhookTarget.payload` reserved-key validator.** `pipelex.pipe_run.delivery_assignment.WebhookTarget` now has a `field_validator` on `payload` that rejects the reserved set `{"pipeline_run_id", "status", "result_url", "error"}` at construction time. Any code or test that stuffs these into a static webhook payload now raises `pydantic.ValidationError`. Action: grep for `WebhookTarget(` and `WebhookTarget.model_validate(` and remove any reserved keys from static payloads.

**3. `request_id` is end-to-end now.** `pipeline_run_setup(request_id=...)` populates `JobMetadata.request_id`, which the worker reads at workflow entry to bind a per-invocation `WorkflowLog`. Every workflow log record then carries `request_id` in `extra`. Action: if pipelex-api still uses the legacy `webhook.payload["request_id"]` piggyback (as the original spec mentioned), drop it — `request_id` rides natively now and round-trips through `JobMetadata`. Populate it from your inbound `X-Request-ID` middleware at dispatch time.

**4. Error class import path moves (Phase 6).** Every `PipelexError` subclass now lives in a module named `exceptions.py` (default — one per package directory) or `<topic>_exceptions.py` (for directories hosting multiple separate-concern error modules — matches the existing `pipelex/plugins/*/` convention). The `*_errors.py` synonym is dropped. `pipelex/errors/error_module_registry.py` is deleted entirely. The "Checkpoint 6 (Phase 6 complete)" entry in `_for_api/TODOS.md` enumerates every file moved or created. Class names are unchanged; only module paths shifted. **`MthdsDecodeError` is deleted** — callers should catch `PipelexInterpreterError` instead (already `error_domain=INPUT` + `caller_facing_message=True`); fold any `except MthdsDecodeError` clauses. Action: grep `from pipelex.` for `*Error` imports and fix paths.

**5. `docs/errors/` is complete.** This branch's Phase 7 commit closes the previously-known discovery gap — every `PipelexError` subclass now has a generated reference page; every `type_uri` value resolves to a live page on docs.pipelex.com. No action in pipelex-api.

**6. Webhook signing (Phase 5 / cross-repo, separate track).** Not in this PR. Authoritative plan: `_for_api/wip/security/webhook-signing.md`. 3-step rollout designed to avoid lockstep deploy — receiver-side dual-format first (pipelex-api ships first, adds `sha256=<hex>` support alongside legacy bare-hex), then worker-side body-signing, then drop legacy. The pipelex-api side carries Item 1 + Item 3. Wait for Louis's green light before starting.

### How to verify your adaptation

After bumping the `pipelex` pin and applying any import path fixes:

- Run pipelex-api's full test suite. `ImportError` is the Phase 6 signal — fix paths, re-run.
- Run any test that constructs a `WebhookTarget` with a static payload. The reserved-key validator will surface any collision.
- If pipelex-api has integration tests that assert STRICT problem-document output for input errors, expect changed JSON: provider metadata stripped, `error_domain` no longer drives the passthrough.

### Don't

- Don't re-derive the spec from `changes-for-api-early-draft.md` — it is superseded by `api-companion-revisions.md`.
- Don't try to land Phase 5 webhook signing in this work — separate track, separate rollout. Wait for Louis's go.
- Don't restate the pipelex-side changes in pipelex-api code comments or PR descriptions — link to the pipelex tracker docs.
- Don't drop the trailing slash on `type_uri` values when comparing strings — pipelex emits `<base>/<kebab-class-name>/` to match MkDocs' `use_directory_urls: true` canonical form.
