# Dry-Run Refactor — Notes Index

Branch: `fix/dry-run`. PR consolidates all dry-run code paths through `PipelexRunner` so dry and live runs share the same entry point.

## Read order

| File | Purpose | When to read |
|---|---|---|
| [`00-questions.md`](./00-questions.md) | Three open questions that kicked off the audit (is `DryPipeRouter` dead code? taxonomy of the four runtime classes? FastAPI load profile?) | Background context |
| [`A-taxonomy.md`](./A-taxonomy.md) | Side-by-side of `PipeRouter` / `PipeRun` / `WfPipeRouter` / `WfPipeRun`; call chains in local vs Temporal mode; hub swap mechanism; `DryPipeRouter` dead-code verification with line numbers | If you need to understand the runtime architecture before/after |
| [`B-load-profile.md`](./B-load-profile.md) | CPU/memory/I/O audit of the dry-run path — the basis for "dry-run is safe in-process even on a FastAPI worker getting thousands of concurrent requests" | Justifies the "DRY → always local" routing decision |
| [`C-synthesis.md`](./C-synthesis.md) | One-page condensed answers to the three questions in `00`; foundation for the plan | Read if you only have 2 minutes |
| **[`D-plan-for-codex.md`](./D-plan-for-codex.md)** | **The 8-point plan that drove the refactor.** Decided design, scope, out-of-scope, kept-as-is, codex-review prompt | **Read this first if you only read one file** |
| [`E-parity-gate.md`](./E-parity-gate.md) | The blocking pre-implementation check: does the API process load the same libraries / class registry / extensions as the Temporal worker? Verdict drives the routing decision | Why "DRY → always local" is safe in our hosted topology |
| [`F-implementation.md`](./F-implementation.md) | What was actually built: file-by-file map, deletions, new helpers, the `keep_library_loaded` flag added beyond the plan, behavioral changes worth flagging in the PR | Reviewer reference; what to look at in the diff |
| [`G-validation.md`](./G-validation.md) | Lint / type-check / test commands run, what passed, known flakes, what to re-run if you change validators | Verification checklist |

## TL;DR

**Problem.** Dry-run had four parallel code paths (`dry_run.py`, `dry_run_pipeline.py`, `dry_run_with_graph.py`, `dry_pipe_router.py`) that bypassed the `PipelexRunner → PipeRun → DeliveryExecutor` orchestration. `DryPipeRouter` was dead code — mode dispatch already lives inside `PipeAbstract._run_pipe_traced`. `validate_bundle.py` had three commented-out `dry_run_pipes(...)` calls (`# TODO: wip - restore or refactor dry run`) — bundle validation had been silently regressed since the Temporal merge.

**Decision.** A run is a run. Everything goes through `PipelexRunner` with `pipe_run_mode=PipeRunMode.DRY`. In hosted FastAPI (Temporal on for LIVE), DRY routes to a local `PipeRun(PipeRouter())` per-request because the load profile (`B`) shows it's CPU-only, cheap, and Temporal would just add latency + queue pressure. Per-request `pipe_run` injection still overrides everything.

**What shipped.** Four files deleted; one config field removed (`allowed_to_fail_pipes`); six validator callsites migrated to the runner; `validate_bundle` dry-on-load restored; one regression test added; one new flag (`keep_library_loaded`) added to support pre-loaded-library validator iteration. See `F-implementation.md`.

**What did NOT ship.** API endpoint unification (`/validate`+`/execute` → `/run`); CLI artifact dedup; renaming `WfPipeRouter`/`WfPipeRun`. See `D` §"Explicitly out of scope".
