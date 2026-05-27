# PR #943 — review-agent comment triage and fixes

**Status:** code complete, uncommitted, **PR-thread replies/resolves not posted yet** (user-directed hold).

**PR:** <https://github.com/Pipelex/pipelex/pull/943>
**Branch:** `feature/API-readiness-2` (post-merge-from-`dev` state, merge commit `8a1dd8cc`).
**Date:** 2026-05-27.

## Why this work happened

Three unresolved review-agent threads on PR #943:

| # | File:line | Reporter | Severity |
|---|---|---|---|
| 1 | `pipelex/temporal/tprl/temporal_error.py:15` | chatgpt-codex-connector | P2 |
| 2 | `pipelex/pipeline/validate_bundle.py:203` | greptile-apps | P1 |
| 3 | `pipelex/temporal/tprl_pipe/act_deliver.py:19` | greptile-apps | P2 |

The user invoked `/review-pr-agents` with the explicit instruction: *no backward compatibility, especially for Temporal* — which directly governs the verdict on #1.

## Verdicts

### #1 — Codex: "Restore recovery of old Temporal error reports"

**False positive (by policy).** Codex flagged that `_ERROR_REPORT_REQUIRED_KEYS` (the marker set in `error_report_dict_from_details`) now requires `title` and `type_uri` alongside `error_type` and `message`, which would break recovery of in-flight workflows produced by a previous pipelex release during a rolling deploy.

This is exactly the backward-compatibility shape the user rejects, and the branch's own ground rules already document this stance — `_for_api/TODOS.md` "Ground rules" says: *"No backward-compat shims. The Temporal integration has never shipped — there is no prior on-wire schema to preserve."* Memory entry `[[project_temporal_not_shipped]]` reinforces it.

No code change. Will reply with rationale + resolve.

### #2 — Greptile: "Current library lost"

**Confirmed (P1).** When a validation entry point runs inside a caller's outer current-library scope and then fails, the `finally` block calls `teardown_current_library()`, which **clears** the ContextVar entirely — clobbering the outer scope. The next `get_current_library()` in the same async context raises `RuntimeError: No current library set`.

The bug is at four sites in `pipelex/pipeline/validate_bundle.py`: `validate_bundle`, `validate_bundles_from_directory`, `load_concepts_only`, `load_concepts_only_from_directory`. A 13-line TODO comment in the file (`validate_bundle.py:137-150`) already documented this exact bug, named the right fix pattern (the capture-and-restore in `submitter_hydration.rehydrate_pipe_output_with_crate`), and punted to post-merge.

**Fix.**

- New public helper `get_current_library_id_or_none()` in `pipelex/hub.py` (reads the `_library_id` ContextVar without raising on unset). A `scoped_current_library(library_id: str)` context manager is also added in `hub.py` but is **not yet used** — it is kept for the upcoming `submitter_hydration.py` migration (separate follow-up commit). The TODO comment in `validate_bundle.py` is gone.
- All 4 entry points in `validate_bundle.py` capture `prev_library_id = get_current_library_id_or_none()` before `set_current_library(library_id=library_id)`, then in the failure-only `finally` branch restore the prior value (`set_current_library(library_id=prev_library_id)` or, when no outer was set, `teardown_current_library()`). The success-path behavior is unchanged on purpose: the caller's library is left as current after the function returns, which `_runner_core.py`, `_inputs_core.py`, `_output_core.py`, the agent_cli `validate_pipe_in_bundle_core`, `validate_ops.py:184`, and `inputs_ops.py` all rely on for their immediate `get_required_pipe(pipe_code=...)` call.
- 4 new regression tests in `tests/integration/pipelex/pipeline/test_validate_bundle_library_lifecycle.py` (new `TestValidateBundleRestoresOuterLibraryOnFailure` class) — one per entry point. Each sets an outer current library, forces a translated failure (via the existing `_BrokenResult` patch pattern), and asserts `get_current_library() == outer_library_id` post-call. All four failed before the fix (`RuntimeError: No current library set`), pass after.

**Collateral.** None — `ValidateBundleResult` / `LoadConceptsOnlyResult` are unchanged, and no existing test relied on the leaky pre-fix behavior in a way that needed updating. The success-path keeps the caller's library current, so call sites that read `get_current_library()` after a successful call continue to work as before.

### #3 — Greptile: "Delivery logs lose request"

**Confirmed (P2).** `DeliveryActivityArg` did not carry `request_id` or `JobMetadata`, so the delivery activity in `act_deliver.py` could not build a request-bound `ActivityLog` — and `DeliveryExecutor`'s storage/webhook completion logs lost correlation with the workflow logs and the originating API request.

**Fix.**

- `DeliveryActivityArg` gains `request_id: str | None = None`.
- `wf_pipe_run.py:102` populates it from `pipe_job.job_metadata.request_id` at activity-dispatch time.
- `act_deliver.py` passes `arg.request_id` through to `executor.execute(...)`.
- `DeliveryExecutor.execute` / `_store_results` / `_notify_webhook` accept `request_id: str | None = None`. Because `pipelex.log` (custom dispatch) does not accept `extra=`, `request_id` is inlined as `, request_id={request_id}` into the existing `key=value` log strings — the same shape the lines already use for `pipeline_run_id` and `url`. Suffix is conditional: when `request_id is None`, the field is omitted entirely (no stray `request_id=None`).
- 3 new regression tests in `tests/unit/pipelex/pipe_run/test_delivery_executor.py`:
  - storage-completion log includes `request_id=...` when set,
  - webhook-completion log includes `request_id=...` when set,
  - both log lines OMIT the field entirely when `request_id` is unset (defense against a stray `request_id=None`).
- 2 new field-coverage cases in `tests/unit/pipelex/temporal/test_delivery_activity_arg.py`: the round-trip preserves `request_id`, and the field defaults to `None` for runs without an inbound id.

## Files changed

```
pipelex/hub.py                                                  (+1 public helper get_current_library_id_or_none; +scoped_current_library context manager — added but unused, kept for the upcoming submitter_hydration.py migration)
pipelex/pipeline/validate_bundle.py                             (4 sites: capture prev_library_id, restore-or-teardown on failure only; TODO comment removed)
pipelex/pipe_run/delivery_executor.py                           (request_id threaded through 3 method signatures + 2 log strings)
pipelex/temporal/tprl_pipe/act_deliver.py                       (+1 field, +1 kwarg passthrough)
pipelex/temporal/tprl_pipe/wf_pipe_run.py                       (+1 kwarg populated from job_metadata)

tests/integration/pipelex/pipeline/test_validate_bundle_library_lifecycle.py   (+1 test class, 4 new tests)
tests/unit/pipelex/pipe_run/test_delivery_executor.py                          (+3 new tests for request_id in delivery logs)
tests/unit/pipelex/temporal/test_delivery_activity_arg.py                      (existing roundtrip extended + 1 new defaults test)
```

## Verification

- `make agent-check` — ruff/format/pyright/mypy: **0 errors**.
- `make agent-test` — full suite **green**, including all 7 new regression tests.
- TDD discipline observed for both fixes: red test first, implementation second, green confirmed before moving on.

## Open follow-ups

- **PR-thread replies + resolves** — held at user's request, not yet posted. When ready:
  - Thread `PRRT_kwDOOwmMFc6FG301` (codex, temporal_error.py) → reply with policy rationale ("no backward-compat for Temporal; pre-shipping wire shape can change freely"), then resolve.
  - Thread `PRRT_kwDOOwmMFc6FHB_5` (greptile, validate_bundle.py) → reply summarizing the prev-library capture-and-restore pattern at all 4 entry points + 4 regression tests, then resolve. (The `scoped_current_library` helper added to `hub.py` is intentionally unused for now — it is staged for the submitter_hydration.py migration in a separate follow-up commit.)
  - Thread `PRRT_kwDOOwmMFc6FHCBU` (greptile, act_deliver.py) → reply summarizing the `request_id` plumbing from `JobMetadata` through to the delivery completion logs + 3 regression tests, then resolve.

- **Commit shape** — fix #2 and fix #3 are independent and could land as two commits, or one bundled. The collateral (`library_id` on result types + 6 test updates) belongs with fix #2. Awaiting user direction.

- **Push** — `feature/API-readiness-2` is 16 commits ahead of origin (the dev-merge plus this fix) and not yet pushed. Awaiting user direction.

## Notes for the next session

- `get_current_library_id_or_none()` is now a public helper on `pipelex.hub` — use it anywhere a caller needs to snapshot `_library_id` without raising on unset.
- `scoped_current_library(library_id: str)` is also public on `pipelex.hub` but **currently unused**. It restores the prior `_library_id` on context exit (success or exception); intended for the upcoming `submitter_hydration.py` migration. Note that it does NOT fit the `validate_bundle.py` shape, which intentionally keeps the new library current on the success path — that is why the entry points there use a manual capture-and-restore in the failure-only branch.
- The success-path "caller's library is left as current" behavior of `validate_bundle` / `load_concepts_only` is the canonical contract — `_runner_core.py`, `_inputs_core.py`, `_output_core.py`, `validate_pipe_in_bundle_core`, `validate_ops.py:184`, and `inputs_ops.py` all rely on it for the immediate `get_required_pipe(...)` call after a successful validation.
- The `request_id` correlation now flows: inbound API → `JobMetadata.request_id` → `WfPipeRun.run()` builds a bound `WorkflowLog` (existing) → `DeliveryActivityArg.request_id` (new) → `DeliveryExecutor.execute(request_id=...)` (new) → `, request_id={...}` suffix on the storage/webhook completion lines.
