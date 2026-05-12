# Temporal — Deferred Items Index

Single index of work explicitly deferred out of shipped Temporal phases and the in-flight `feature/Temporal-merge-3` (PR #891) merge. Each entry links back to the doc that owns the full context — this file is just the directory so nothing falls off the radar.

For non-temporal deferrals, see [`../deferred-items.md`](../deferred-items.md).

---

## Replay-determinism: remaining `get_config()` reads inside workflow code

**Source:** PR #891 review (chatgpt-codex-connector, 2026-05).
**Owner doc:** Phase 0 of [`00-enterprise-readiness-analysis.md`](00-enterprise-readiness-analysis.md) — bullet "Eliminate remaining config reads inside workflow code".
**Precedent:** the same class of issue was already solved at the submitter boundary for `WorkflowExecutorFactory` (bypassed inside workflows — see `tprl/workflow_caller.py:179+`) and for `TemporalManager.session_id` (`stamp_submitter_session_id` in `tprl/observability.py`).

Two call paths still re-derive options from `get_config()` at workflow runtime, which would diverge on replay after any config edit:

- `pipelex/temporal/tprl/observability.py:104-107` — `build_search_attributes` reads `get_config().temporal.search_attributes` (`enabled` + `attributes`). Affects every in-workflow caller: `wf_pipe_run.py:57`, `temporal_pipe_router.py:85`. Fix: snapshot enabled attribute names at submitter, carry on `PipeJob` / `JobMetadata`, make the helper actually pure (matches its docstring claim).
- `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py` — every `make_*` method calls `worker_config.resolve_dispatch(..., queue_options_by_queue=get_config().temporal.queue_options, is_traced=get_config()...)` inside workflow code. Fix: snapshot resolved dispatch options per activity at the submitter boundary, or freeze the relevant config blocks into the workflow input.

**Exit gate (proposed):** zero `get_config()` reads in workflow code paths, enforced by an AST scanner extension (the existing scanner already catches guarded top-level `temporalio` imports — same shape).

---

## `WorkflowExecutionError` → `ApplicationError` cleanup

**Source:** Phase 5 / 6 follow-up; only deferred item from temporal-primitives Phases 1–6.
**Owner doc:** [`../temporal-primitives/03-temporal-error-handling-revamp.md`](../temporal-primitives/03-temporal-error-handling-revamp.md).

`WorkflowExecutionError` doesn't subclass `temporalio.exceptions.FailureError`, so the workaround in commit `117bbe01` registers it in the Worker's `workflow_failure_exception_types` list. Proposal: make `WorkflowExecutionError` subclass `ApplicationError`, drop the registration, simplify the exception model end-to-end.

---

## `except Exception` removals in workflow-critical paths

**Source:** [`00-enterprise-readiness-analysis.md`](00-enterprise-readiness-analysis.md) gap #3 + Phase 0 first bullet.
**Owner doc:** Phase 0 of `00-enterprise-readiness-analysis.md`.

Priority files: `tprl_pipe/wf_pipe_router.py` (multiple `except Exception`), `tprl_pipe/act_assemble_graph.py` (one labeled `# TODO: wip — do not catch all exceptions`). Already partially addressed in commit `117bbe01` for `tprl/workflow_caller.py`; the workflow-side and activity-side catches remain.

---

## Out-of-scope-but-tracked from temporal-primitives

**Owner doc:** [`../temporal-primitives/02-id-and-naming-plan.md`](../temporal-primitives/02-id-and-naming-plan.md) §"Out of scope".

These are explicitly out of scope for the shipped temporal-primitives work but stay on the watchlist:

- `workflow.set_current_details(...)` for in-flight progress.
- Memo population beyond the optional `library_crate` fingerprint.
- Per-pipe Workflow Type registration.
- Search-attribute schema versioning / migration tooling.
- `display_label` parameter at the `PipeRun` entry point.
- **Unifying the two child-spawn paths.** Was attempted (Phase 5 follow-up), reverted (`ac8e2335`) for replay-determinism reasons — a clean unification needs the submitter-snapshot pattern above to land first.
- `WorkflowIDReusePolicy` choice — stays at SDK default `ALLOW_DUPLICATE`; revisit whether `REJECT_DUPLICATE` catches double-execution bugs now that workflow IDs are deterministic from `pipeline_run_id`.

---

## Real-cluster validation gaps

**Source:** [`../temporal-primitives/02-id-and-naming-plan.md`](../temporal-primitives/02-id-and-naming-plan.md) §"Known follow-ups (deferred)" under Phase 6.

- Hard-fail path against a real Temporal cluster — unit suite covers the contract via mocked clients; run `/temporal-e2e-validate` once a real-cluster credential is available.
- `[temporal.search_attributes].enabled = false` end-to-end path on a real cluster — covered by unit tests + propagation-by-construction; deferred for explicit e2e verification.

---

## Enterprise-readiness roadmap (Phases 1–5 of `00-enterprise-readiness-analysis.md`)

Everything beyond Phase 0 in [`00-enterprise-readiness-analysis.md`](00-enterprise-readiness-analysis.md) is deferred-by-design and lives there with full context. Not duplicated here. Headline items:

- Phase 1 — Security baseline (mTLS, OAuth/OIDC, envelope encryption, PII redaction).
- Phase 2 — Observability (OpenTelemetry, metrics exporter, structured audit log).
- Phase 3 — Multi-tenant admission control + quotas.
- Phase 4 — DR/BCP + rolling-deployment guidance.
- Phase 5 — Productization polish (tuning_mode resolution, sandbox passthrough config, rate-limit semantics).
