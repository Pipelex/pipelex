# Dry-Run Refactor — Notes Index

Branch: `feature/Validate-with-signatures-4-fix-dry-run`. Goal: consolidate all dry-run code paths through `PipelexRunner` so dry and live runs share one entry point — **now layered on top of the signature-validation feature**, which already re-wired these paths.

> **Read this first — the situation changed since the draft was written.**
> The original draft (a few days old) documented this refactor as *already shipped* on a branch called `fix/dry-run`. That branch was **never merged**. It forked at v0.29.1 and the live branch then moved ~55 commits past it independently — landing the **signature-validation** feature (`PipeSignature`, `--allow-signatures`, strict pre-check) which **re-touched the exact dry-run code this refactor wants to delete**. So: none of the deletions/migrations the draft claimed are in the tree, and the refactor's original motivation (a "silent dry-run regression" in `validate_bundle`) **has since been fixed** — through the very path the plan wanted to remove. The implementation/validation docs were moved to [`archive/`](./archive/); everything else was re-grounded on the current code.

## Current state of the world (what's actually true today)

- The four parallel dry-run modules **all still exist**: `pipelex/pipe_run/dry_run.py`, `dry_run_pipeline.py`, `dry_run_with_graph.py`, `dry_pipe_router.py`.
- `DryPipeRouter` is **still dead code** (never instantiated outside its own definition) — the draft's central finding holds.
- `validate_bundle` **already dry-runs on load** (`validate_bundle.py`) — the three `# TODO: wip - restore or refactor dry run` are gone. The regression the plan targeted is closed.
- That fix arrived via the **old** `dry_run_pipes` path, which signature-validation then extended. `dry_run.py` is now **load-bearing for signatures**: it hosts the strict signature pre-check (`collect_signature_refs` / `collect_signature_paths` → `SignaturesNotAllowedError`), threads `allow_signatures`, and exports `convert_stuff_spec_to_typed_named` that **`pipe_signature.py` itself imports**.
- `allowed_to_fail_pipes` is **still** in `configs.py` + `pipelex.toml`. `convert_to_working_memory_format` is **still** in `dry_run.py` (imported by `pipeline_run_setup.py` and `dry_run_with_graph.py`).

So the consolidation is still desirable, but it is now a **bigger** operation than the draft assumed: any "route dry-run through `PipelexRunner`" design must find a new home for the signature strict-check, thread `allow_signatures` + `dry_run_pipe_codes` through the runner, and preserve the single-aggregated-error UX. See [`D-plan.md`](./D-plan.md).

## Read order

| File | Purpose | Status |
|---|---|---|
| **[`D-plan.md`](./D-plan.md)** | **The live plan.** Re-grounded on the current signature-aware code. Lists current reality, the in-scope consolidation, the new constraints signature-validation imposes, and an explicit slot for the clarified requirements still to be folded in. | **Read this first.** Rewritten. |
| [`00-questions.md`](./00-questions.md) | The three founding questions of the original audit (is `DryPipeRouter` dead? taxonomy of the runtime classes? FastAPI load profile?). | Historical origin. Answers still hold. |
| [`A-taxonomy.md`](./A-taxonomy.md) | Side-by-side of `PipeRouter` / `PipeRun` / `WfPipeRouter` / `WfPipeRun`; call chains local vs Temporal; hub swap; `DryPipeRouter` dead-code proof. Plus a signature-validation delta section. | Background. Structurally accurate (line numbers as of ~v0.29.1). |
| [`B-load-profile.md`](./B-load-profile.md) | CPU/memory/I/O audit of the dry-run path — basis for "dry-run is safe in-process." | Background. Still valid. |
| [`C-synthesis.md`](./C-synthesis.md) | One-page condensed answers to the founding questions. | Background. §5 updated for the closed regression. |
| [`E-parity-gate.md`](./E-parity-gate.md) | The blocking check: does the API process load the same class registry as the Temporal worker? Verdict drives "DRY → local". | Background. Verdict still holds. |
| [`archive/`](./archive/) | The implementation + validation docs for the **abandoned** `fix/dry-run` branch. Reference only. | Archived. Not current. |

## TL;DR

**Problem (still real).** Dry-run has four parallel code paths that bypass the `PipelexRunner → PipeRun → DeliveryExecutor` orchestration, plus a confirmed dead `DryPipeRouter`. Under the principle *"a run is a run"*, dry and live should share one entry point.

**What changed since the draft.** The "silent regression" motivation is gone — `validate_bundle` dry-runs again. But the path that fixes it (`dry_run.py` / `dry_run_pipes`) is now the home of the signature-validation strict-check and is imported by `pipe_signature.py`. The consolidation therefore has to carry the whole signature surface, not just delete it.

**What's next.** Re-scope the consolidation on top of signatures (`D-plan.md`), then fold in the clarified requirements. The mechanical shopping list from the abandoned attempt ([`archive/fix-dry-run-implementation.md`](./archive/fix-dry-run-implementation.md)) is still a useful starting menu.
