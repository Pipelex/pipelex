# Dry-run / validation consolidation

All dry-run / validation traffic now flows through one service — **`BundleValidator`**, composing the same `acquire_library` / `prepare_pipe_job` execution seam the runner uses. This replaced the four parallel dry-run code paths (`dry_run.py`, `dry_run_with_graph.py`, the dead `dry_pipe_router.py`, kept `dry_run_pipeline.py`).

The work is framed as three parts (D-plan **A/B/C**). **Part A — the in-process consolidation — shipped on `main` in #956.** Parts B and C are deferred to their own branches and are the bulk of the open work below.

- **What exists now** → [`consolidation-as-built.md`](./consolidation-as-built.md) (the as-built architecture + the decisions that hold).
- **Why it's shaped this way + the full Part B/C design** → [`D-plan.md`](./D-plan.md) (the design source).
- **Rendered PR recap** → [`PR-bundle-validator.html`](./PR-bundle-validator.html) (a point-in-time snapshot of the consolidation PR).

---

## Open follow-ups — do not forget

Everything below is **not yet done**. Each deferred workstream has its own tracker (phases, pre-flight gates, handoff blocks); the smaller items are listed inline here because this is their only home.

### Deferred workstreams — own branches

> **Parts B and C are the two dry-run modes** (full-distribution-with-leaf-mocks, and one-in-process-activity-in-memory). How they relate, what they share, and who builds the common `scoped_content_generator` seam → [`dry-run-modes-master-plan.md`](./dry-run-modes-master-plan.md).

| Workstream | What it delivers | Status / gate | Tracker |
|---|---|---|---|
| **Part B — leaf-level run-mode mock** | Move the LIVE/DRY decision down to the cogt leaf so DRY *honors the backend* (DRY-on-Temporal dispatches `act_llm_gen_*` and mocks inside the activity). Retires the "DRY → local" shortcut. (req 1) | Not started. Has **pre-flight human-input items** (run_mode carrier, object-mock fidelity, synthetic-report disposition) — resolve before phase B1. | [`followup-leaf-run-mode-mock.md`](./followup-leaf-run-mode-mock.md) |
| **Part C — dry-run + validation as one in-process Temporal activity** | The API dispatches the whole job — validation sweep **+** graph-producing dry-run — to a worker as one activity that runs in-process and traces the graph **in memory** (no DynamoDB round-trip, no NDJSON, no usage/cost). Returns the status map **+** `GraphSpec`. (req 2) | **Built** on `feature/Dry-run-as-temporal-activity` (+ `pipelex-api` `feature/Update-dry-run-api`) — all phases through Checkpoint F (phase record in that branch's `TODOS.md`); verified by Mode-1 isolation tests and Tier 2d of `temporal-e2e-validate` (activity + API arms, GREEN+RED on a real 3-process stack). As-built record: [`consolidation-as-built.md` § Part C](./consolidation-as-built.md). The `pipelex-api` branch needs a pipelex release/rev bump (> v0.32.1) before merge. Deferred: Phase G0 standalone activity (`temporalio` bump); retiring the old worker-workflow graph path; moving `pipe_structures` into the activity result. | [`followup-temporal-validation-activity.md`](./followup-temporal-validation-activity.md) |
| **Run-outcome seam** *(optional)* | Have the run primitive *return* its classified outcome so `BundleValidator` consumes a typed outcome instead of re-catching + chain-walking the re-raised exception (D-plan D6). | Not started. **Optional tightening, not a bug** — gated on "is it worth the cross-backend churn?" Default: leave it. | [`followup-run-outcome-seam.md`](./followup-run-outcome-seam.md) |

### Cross-repo

- **MTHDS skills — namespaced `validate` identity.** The single-pipe `validate pipe` agent-CLI surfaces now emit the namespaced `domain.code` (the whole-set surfaces were already namespaced). Skills that exact-match a bare code against the returned `pipe_code` need updating. Self-contained SWE-agent handoff: [`handoff-skills-validate-namespaced-identity.md`](./handoff-skills-validate-namespaced-identity.md). Could not be done from this repo.

### Verify (at/after the #956 merge)

- **`pipelex-api` pin flip.** During co-development the `pipelex-api` `pyproject.toml` carried an editable `pipelex = { path = "../_sig" }` pin (keeps its CI red). It must be flipped to the merged `pipelex` git rev now that #956 has landed. **Confirm this happened** — if `pipelex-api` CI is still red on the editable pin, this is the cause.

### Hardening & cleanups — anytime, small

Part-C operational hardening (heartbeat/cancellation, CPU-bound activity body, worker-vs-API config drift, double dry-run of the main pipe, `_pipe_source_map` scoping, selected-pipe wire field, per-queue dispatch tuning) has its own tracker: [`followup-dry-validate-hardening.md`](./followup-dry-validate-hardening.md).

| Item | Where | Note |
|---|---|---|
| **Per-sweep unique `pipeline_run_id`** | `bundle_validator.validate_pipes` | The report registry + per-pipe graph-trace read are keyed by the **constant** `SpecialPipelineId.DRY_RUN_UNTITLED`, so two concurrent in-process sweeps collide (2nd `open_registry` raises "already exists"; interleaved `close_registry` can drop the other's registry). Mint a unique id per sweep and thread it through `open_registry` + `prepare_pipe_job` + `close_registry` — one fix also scopes the per-pipe trace read to an empty dir. **Rides with Part C** (no concurrent sweeping exists in-process today). `close_registry` is already hardened to `pop(..., None)`. |
| **Shared `acquired_library(...)` helper** | ~6 sites | The "restore outer current-library first, then teardown" `finally` is copied across `validate_bundle.py` (×4), `execution_seams.acquire_library`, and `bundle_validator.acquire_and_validate` (now via `clear_current_library`). Extract one context manager / helper so the load-bearing ordering lives in one place. |
| **`acquire_and_validate` self-teardown guard** | `bundle_validator.acquire_and_validate` | If a caller passes an explicit `library_id` equal to the already-current library, the `finally` restores-then-tears-down the same library (dangling current pointer). Guard `prev_library_id != acquired_id`, or document that `library_id` must not alias the caller's current library. Default `library_id=""` is safe, so latent. |
| ~~**`__init__` content-generator injection seam**~~ | `bundle_validator.BundleValidator.__init__` | **Resolved by Part C** — no constructor seam was needed: `validate_pipes` wraps its sweep loop in `scoped_content_generator(ContentGenerator.make_inline())` (ContextVar scope alongside `scoped_pipe_router`), forcing the inline generator under any hub. |
| **Real-config FAILURE / `allowed_to_fail` integration test** | `tests/integration/.../test_bundle_validator.py` | Integration coverage is SUCCESS-path + real cross-package SKIPPED. The namespaced `allowed_to_fail` match is pinned only at unit level (mocked config). Add a real-config FAILURE-match test (e.g. load `failing_pipelines.mthds`). |
| **Success-path report-registry leak** *(pre-existing)* | `runner.execute_pipeline` finally | Production never closes the report registry on the **success** path either (the `finally` tears down tracer / event-log / library but not the registry). Predates this work; a registry-ownership change spanning setup→run→report. Out of this consolidation's scope, but worth tracking. |
| **Test-style nits** *(very low)* | `pipelex-api` route tests + pipelex `test_agent_output` | Opportunistic: share the duplicated `_build_client()` across the two route-test modules; fold the overlapping body asserts in the runner-with-signatures test; trim the cosmetic domain assertion. None blocking. |

### Out of scope — future (D-plan §7)

- API endpoint unification in `pipelex-api` (`/validate` + `/execute` → `/run`).
- CLI artifact-write dedup — `_run_core.py` gates artifact writing via `save_main_stuff` / `save_working_memory` in two copies (main + agent CLI); re-scope before touching.
- Rename `WfPipeRouter` / `WfPipeRun` for clarity (see `A-taxonomy.md` §6).

---

## Background — original audit (historical)

These predate the consolidation and the signature-validation feature; each carries a banner noting what's still accurate. Kept because D-plan's invariants (load-profile-is-safe, API/worker parity) for Parts B/C rest on them. Read only for context.

| File | What |
|---|---|
| [`00-questions.md`](./00-questions.md) | The three founding questions of the audit (is `DryPipeRouter` dead? class taxonomy? FastAPI load profile?). Answers still hold. |
| [`A-taxonomy.md`](./A-taxonomy.md) | `PipeRouter` / `PipeRun` / `WfPipeRouter` / `WfPipeRun` side-by-side; hub swap; `DryPipeRouter` dead-code proof; signature-validation delta. |
| [`B-load-profile.md`](./B-load-profile.md) | CPU/memory/I/O audit — the basis for "dry-run is safe in-process." |
| [`C-synthesis.md`](./C-synthesis.md) | One-page condensed answers to the founding questions. |
| [`E-parity-gate.md`](./E-parity-gate.md) | API-process vs Temporal-worker class-registry parity. Conclusion repurposed by D4/D5 (see its banner); the evidence still holds. |
