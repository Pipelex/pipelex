# Autofix track

Deterministic auto-fixing of `.mthds` validation errors — fixes attached to validation diagnostics, applied by a convergence loop.

| Doc | What it is | Status |
| --- | --- | --- |
| [master-plan.md](master-plan.md) | Executive step ladder: spike → wave 1 → protocol/API/MCP/editor waves | **CURRENT — steps 1 + 2 DONE, step 3 next** |
| [suggested-fixes-design.md](suggested-fixes-design.md) | The live design: architecture, fix rules, phases | **CURRENT — steps 1 + 2 DONE; per-checkpoint findings + the step-2 abstraction verdict recorded inside** |
| `deferred-checkpoint-{0,a,a-prime,b,c}-review-items.md` | Real-but-deferred items from each checkpoint's code review (multi-file targeting, conformance fixture sync, upstream `pipelex-tools-py` follow-ups, rename convergence cap, …) | **CURRENT** |
| [spike-reviewers-guide.md](spike-reviewers-guide.md) | Reviewer's guide for the step-1 spike PR (#1027) — the chain, invariants, test map | **DONE — Checkpoint 0 cleared 2026-07-07; archived from the worktree-root `TODOS.md`** |
| [`TODOS.md`](../../TODOS.md) (worktree root) | Detailed implementation plan for the CURRENT step, with progress checkboxes | **step 2 (wave-1 rule breadth) DONE — will be rewritten as the PR #1031 reviewer's guide** |
| [old-plan-to-auto-fix.md](old-plan-to-auto-fix.md) | The original `feature/Bundle-fixer` plan (standalone fix engine) | Superseded — kept as reference; its "Legacy reference" citations point at code that no longer exists |

The abandoned `feature/Bundle-fixer` branch still exists and holds harvestable domain logic (see the design doc's salvage section), but its architecture is not the one we're building.
