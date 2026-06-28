# Distributed Execution — Plan & Track Map

The big direction: run **activities on standalone Worker pools** — separate processes from the workflow Worker pool — so workflow orchestration and inference activity execution scale independently.

This folder is the **distributed-execution track**: running MTHDS methods as Temporal workflows across separate worker processes. This README is the priority-ordered plan; the other docs are the per-topic designs and references it points to.

## Docs in this track

- [tracing-cost-reporting.md](tracing-cost-reporting.md) — as-built reference for tracing & cost reporting across workers, plus its deferred items (P0/P1 context).
- [local-cross-package-deps.md](local-cross-package-deps.md) — ship dependency blueprints inside the crate (P2).
- [remote-deps-from-github.md](remote-deps-from-github.md) — fetch dependencies from remote addresses (P3).
- [crate-first-architecture.md](crate-first-architecture.md) — the crate-first vision behind P2/P3, with deferred capabilities (stripping, fingerprint validation, cross-worker cache).
- [temporal-ids-and-naming.md](temporal-ids-and-naming.md) — implemented design for Temporal IDs, naming, and observability surfaces.
- [temporal-exception-model-revamp.md](temporal-exception-model-revamp.md) — deferred proposal to reparent workflow exceptions onto `ApplicationError`.
- [schema-reconstruction-hardening.md](schema-reconstruction-hardening.md) — deferred hardening of cross-process Pydantic-schema reconstruction.
- [unit-testing-worker-sandbox-validation.md](unit-testing-worker-sandbox-validation.md) — deferred bug: a sandboxed worker can't boot under `--is-unit-testing` because the registered test workflows fail temporalio sandbox validation.
- [bridge-changes-sibling-repo-reconciliation.md](bridge-changes-sibling-repo-reconciliation.md) — **OPEN handoff:** how the `_bridge` dev-merge changed the runtime-bridge surface (param renames, deleted graph-assembly primitive, `graph_context→trace_context`, #967/#968) and what the downstream `pipelex-mistralai-workflows` + `_workflows` repos need reconciled. Diagnosis DONE — it is the authoritative breakage inventory; now also carries item 7, the PR #987 reporting-path behavioral break (activity-side usage emissions bypass the plugin's registered buffer).
- [workflow-nondeterminism-audit.md](workflow-nondeterminism-audit.md) — **diagnosis, HIGHs fixed:** verified audit of worker-local inputs leaking into the workflow command stream (post-PR-#984). Both HIGH findings (flush activity gated on an activity-fed buffer; library/fingerprint leak on eviction) and M1 are now FIXED with regression guards; the open remainder is config-derived dispatch options and inline randomness drifting command arguments. Carries the suggested fix order.
- [nondeterminism-fix-review-follow-ups.md](nondeterminism-fix-review-follow-ups.md) — **BURNED DOWN:** verified findings from the code reviews of the H1/M1 and H2 fixes, now all resolved (per-item statuses recorded inline). The priority item — keying per-run worker-local state by `run_id` instead of `workflow_id` — is FIXED with regression guards, along with the eviction-ordering test, the flush-skip in costs-only LIVE, the `finally` simplification, helper consolidation, and the smaller cleanups.
- [nondeterminism-pre-merge-fixes.md](nondeterminism-pre-merge-fixes.md) — **PRE-MERGE, ACTIONABLE:** the two findings from PR #987's xhigh review to fix before merge — `PipelineManager` 500s resubmission of the same `pipeline_run_id` process-permanently (and its collision raise is load-bearing for the direct-mode tracer keyspace — read the coupling warning before touching it), and the module-level temporalio import in `reporting_manager.py` that puts ~130ms on every pipelex boot. Cold-start ready: evidence, fix shapes, red-first tests, acceptance.
- [nondeterminism-follow-ups-decisions-needed.md](nondeterminism-follow-ups-decisions-needed.md) — **DECISIONS NEEDED:** judgment calls deferred from the burn-down and from PR #987's pre-landing review army. Headliners: the graph-event path has no H1-style guard against in-activity tracer mutation (ties into T3), tracing-disabled workers silently drop submitter-requested events, a non-PipelexError in the unguarded tracing-setup block retries forever, and the run-id-keying residual leak/zombie-thread risks. Options + recommendations inside.
- [validate-sweep-temporal-leak-repro.md](validate-sweep-temporal-leak-repro.md) — **bug brief + e2e repro (DONE):** the `/validate` dry-run sweep leaked nested controller sub-pipes to Temporal (HTTP 422 on a standalone `PipeBatch`). Fixed (commit `3377babb`); all three guard layers now in place — in-process sentinel test, Mode-1 pytest (`test_validate_sweep_stays_in_process.py`), and the deployment-faithful Mode-2 scenario (Tier 2c in the `temporal-e2e-validate` skill, using the `pipelex validate bundle --temporal` flag).
- [temporal-e2e-validate-skill.md](temporal-e2e-validate-skill.md) — validation status of the `/temporal-e2e-validate` skill and the Step 9 (queue-options) skill bugs patched in its `queue-options-battery.md`. Full dry + live run all green; open follow-ups are the vestigial `act_jinja2_gen_text` removal and a stale Mode 1 "Known xfails" note.
- [mistral-workflows/](mistral-workflows/) — sub-track for landing the `pipelex-mistralai-workflows` plugin (the MISTRAL_NATIVE backend) onto current `dev`. Its [README](mistral-workflows/README.md) is the hub; verdict is split — land the bridge, hold the `mistralai` 1.x→2.x bump (blocked on instructor PR #2298). Carries the two ready-to-paste keep-alive prompts.

---

## Priority order

| # | Item | Detail |
|---|---|---|
| **P0 ✓** | Tracing & cost reporting across separate-process workers | shipped — [tracing-cost-reporting.md](tracing-cost-reporting.md) |
| **P0.1 ✓** | Dry-run through activity dispatch (testing affordance) | shipped as `--mock-inference` — below |
| **P0.2** | Deferred follow-ons from P0 | below |
| **P1 ✓** | Cross-worker cost report assembly | shipped (Option B — usage rides on `PipeOutput`) — below |
| **P2** | Local cross-package dependencies in the crate | [local-cross-package-deps.md](local-cross-package-deps.md) |
| **P3** | Remote dependencies from GitHub | needs P2 — [remote-deps-from-github.md](remote-deps-from-github.md) |

P0/P0.1/P0.2/P1 formed one chain (P0 unlocked the rest); **P0, P0.1, and P1 are now shipped** (see [the registry tracker](../history/registry/README.md) for the as-built sequencing). P0.2 is still open (independent follow-ons). P2/P3 are an independent chain (P2 blocks P3). [tracing-cost-reporting.md](tracing-cost-reporting.md) carries the as-built design; T1 and T2 are fixed, T3 (request-scoped tracing state) remains open.

Sibling track (separate branch, not in this plan): the error-handling work — see [`error-handling/README.md`](../error-handling/README.md).

---

## P0 — Tracing & cost reporting across separate-process workers — DONE

Shipped. The as-built design, what works today, and the open T2/T3 gaps are in [tracing-cost-reporting.md](tracing-cost-reporting.md). The remaining cross-worker read-back is P1; the explicitly-deferred follow-ons are under P0.2.

---

## P0.1 — Dry-run through activity dispatch (testing affordance) — DONE

Shipped as **`--mock-inference`** (distinct from `--dry-run`): a LIVE run (`run_mode` stays LIVE so operators dispatch normally) whose AI call is faked at the cogt inference *leaf*, inside the dispatched activity. So the cross-process surfaces — `_event_log_contexts` lookup miss, runner-side fallback, `writer_id="act_*"` emission — all fire, with no LLM spend.

As built:

- `JobMetadata.is_mock_inference: bool` carries the signal into every activity (it crosses the Temporal boundary), written single-source from `prepare_pipe_job`. The leaf (`cogt/content_generation/llm_generate.py`) branches to a shared mock in `cogt/content_generation/dry_mock.py` when the flag is set.
- The synthetic usage is **reportable non-zero** (`MOCK_INFERENCE_NB_TOKENS_BY_CATEGORY = {INPUT: 100, OUTPUT: 50}`, model `mock_inference`) — distinct from `--dry-run`'s zero-token, suppressed usage — so the cross-worker cost report actually renders. This is the durable reason `--mock-inference` ≠ `--dry-run` at the reporting layer.
- `temporal-e2e-validate` Tier 8b runs in this mode and surfaces `wf_*__w_act_*.ndjson` + a rendered cost report deterministically.

**Scope deviations (deliberate):** the leaf mock covers the **LLM leaf only**; image-gen / extract / search under `--mock-inference` fail loud with `MockInferenceUnsupportedError` (their output is stored *above* the leaf, so a leaf mock would push synthetic data through storage). `--mock-inference` is on the main `run` subcommands only (not the agent CLI). Full per-operator coverage and the eventual `is_mock_inference → run_mode=DRY` re-keying are tracked in [`../dry-run-refactor/followup-leaf-run-mode-mock.md`](../dry-run-refactor/followup-leaf-run-mode-mock.md) (B2). See [the registry feature](../history/registry/README.md) and its [`cost-reporting-overview.html`](../history/registry/cost-reporting-overview.html) for the full as-built.

---

## P0.2 — Deferred follow-ons from P0

Each is independently scoped and not blocking. Pick up individually as signals dictate.

- **`tracing_config.strict_mode: bool`** — opt-in flag that raises (instead of WARNING + drop) when the runner-side emit path fails. For compliance/audit deployments where missing trace data is a hard error.
- **DynamoDB `BatchWriteItem` for runner emission** — the current path does one `PutItem` per usage event; `BatchWriteItem` batches up to 25. Defer until throughput shows it matters.
- **NDJSON shared-filesystem invariant enforcement** — the NDJSON backend assumes `traces_dir` is visible to all writer processes (router pool + runner pool + `act_flush_trace_events`); multi-host deployments need NFS/EFS. Add a startup check that warns if `traces_dir` looks local-only on a multi-worker deployment.
- **Per-thread `writer_id` for activity event log** — the surgical lock closes the duplicate-sequence race on `next_sequence()`; a per-thread writer namespace would eliminate the contention entirely and align with how Temporal's worker pool partitions activities (dedup drops to per-thread, no hot-path lock).
- **Project-wide migration of `JobMetadata.started_at` to timezone-aware datetimes** — the landed patch builds the synthetic `now` with the incoming `started_at`'s `tzinfo`, removing the immediate `TypeError` but not the underlying inconsistency: the default factory is naive (`datetime.now`) while several callers (e.g. `pipe_abstract.py:428`) construct aware datetimes. A clean migration standardizes on `datetime.now(timezone.utc)`, documents the tz contract on `JobMetadata`, and lets `duration` subtract without per-site tzinfo matching.

---

## P1 — Cross-worker cost report assembly — DONE

Shipped via **Option B** (the locked design; see [the registry overview](../history/registry/cost-reporting-overview.html)): rather than wire `read events → inject_tokens_usages → generate_report` onto the process-singleton manager, usage rides on `PipeOutput` exactly like the graph spec, and the submitter renders the report from that field. This resolved P1 **and** the `UsageRegistry` success-path leak in one move — with nothing populating a submitter-side registry, the registry was removed outright.

As built:

- The single trace-event read in `assemble_tracing` / `act_assemble_tracing` (renamed from `graph_assembly` / `act_assemble_graph`) feeds `UsageAggregator.aggregate()` when `--costs` is on, setting `PipeOutput.tokens_usages` in both direct and Temporal modes (the same hook that builds the `GraphSpec`).
- The submitter renders via `CostRegistry.generate_report(tokens_usages=...)` fed from `pipe_output.tokens_usages` (main CLI: `pipelex/reporting/cost_report_renderer.py::render_run_cost_report`).
- A dedicated `--costs` / `is_generate_costs` switch (default on) gates usage events + `UsageAggregator` over the shared event-log transport, independent of `--graph`.
- Retired: `ReportingManager.inject_tokens_usages` / `generate_report` / `open_registry` / `close_registry`, the `UsageRegistry` model, and the local-only registry fallback (`_get_registry_strict` / `_try_add_to_registry`) are all gone.

Cross-worker case verified without spend: parent + child + activity usage aggregates into one end-of-run cost report — `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py`, `test_mock_inference_temporal.py`, and the `temporal-e2e-validate` skill's Tier 8b. The full phased as-built is in [the registry tracker](../history/registry/README.md).

---

## P2 — Local cross-package dependencies in the crate

Detailed plan: [local-cross-package-deps.md](local-cross-package-deps.md).

In one line: ship dependency blueprints inside the `LibraryCrate` so workers don't need the dependency packages on PIPELEXPATH. Prerequisite for P3.

---

## P3 — Remote dependencies from GitHub

Detailed plan: [remote-deps-from-github.md](remote-deps-from-github.md).

In one line: extend the blueprint collector from P2 with a remote (GitHub) resolver so the crate can carry deps fetched from external addresses, making workers fully stateless.

---

## Dependencies between items

```
P0 (Tracing across separate workers)
   │
   ├─► P0.1 (Dry-run through activity dispatch — testing affordance)
   ├─► P0.2 (Deferred follow-ons — independent, pick up individually)
   │
   ▼
P1 (Cross-worker cost report assembly)

P2 (Local cross-package deps)
   │
   ▼
P3 (Remote deps from GitHub)
```

P0/P0.1/P0.2/P1 and P2/P3 are independent tracks; P0 unlocked P0.1, P0.2, and P1; P2 blocks P3. **P0, P0.1, and P1 are shipped**; P0.2 (independent follow-ons) and P2/P3 remain. P0.1 (`--mock-inference`) is a testing affordance that raised confidence in P0 / P1 and unlocks future cross-process work.
