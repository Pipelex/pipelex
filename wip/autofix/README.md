# Autofix track

Deterministic auto-fixing of `.mthds` validation errors — fixes attached to validation diagnostics, applied by a convergence loop.

| Doc | What it is | Status |
| --- | --- | --- |
| [master-plan.md](master-plan.md) | Executive step ladder: spike → wave 1 → protocol/API/MCP/editor waves | **CURRENT — steps 1–5 DONE (steps 3+4 merged as PR #1035; step 5 on `feature/Autofix-step5`, PR-ready); step 6 (release train) next** |
| [suggested-fixes-design.md](suggested-fixes-design.md) | The live design: architecture, fix rules, phases | **CURRENT — steps 1 + 2 DONE; per-checkpoint findings + the step-2 abstraction verdict recorded inside** |
| [step5-human-cli-surfacing.md](step5-human-cli-surfacing.md) | Detailed design + working plan for step 5 (`pipelex fix bundle` + the `💡 Suggested fix:` line in `pipelex validate`) | **DONE — all phases incl. `--diff`; CHECKPOINT B cleared (5 bugs fixed, 5 deferred); PR-ready** |
| [validation-error-reporting-plan.md](validation-error-reporting-plan.md) | Follow-on quality track (dogfooded on the internal bad-bundles playground): author-syntax messages at the raise sites, prose agent `validate`/`fix` surfaces, and one clean summary `message` on every surface | **DONE — all phases complete 2026-07-09; the cross-repo error-QA corpus regen is release-gated to step 6; archived from the worktree-root `TODOS.md`** |
| [step3-step4-hardened-loop-and-agent-apply.md](step3-step4-hardened-loop-and-agent-apply.md) | Detailed design + working plan for steps 3 (multi-file targeting) and 4 (`pipelex-agent fix bundle`) | **DONE — merged as PR #1035; review triage in [pr-1035-review-notes.md](pr-1035-review-notes.md)** |
| [pr-1035-review-notes.md](pr-1035-review-notes.md) | PR #1035 review triage — one real-but-inert finding deferred (intra-round cross-file collision) | **CURRENT** |
| `deferred-checkpoint-{0,a,a-prime,b,c,d,e}-review-items.md` | Real-but-deferred items from each checkpoint's code review (multi-file targeting, cross-repo fixture sync, upstream `pipelex-tools-py` follow-ups, rename convergence cap, the step-5 exit triage in `-e`, …) | **CURRENT** |
| [spike-reviewers-guide.md](spike-reviewers-guide.md) | Reviewer's guide for the step-1 spike PR (#1027) — the chain, invariants, test map | **DONE — Checkpoint 0 cleared 2026-07-07; archived from the worktree-root `TODOS.md`** |
| [step2-reviewers-guide.md](step2-reviewers-guide.md) | Reviewer's guide for the step-2 PR (#1031) — the chain, invariants, test map | **DONE — Checkpoint 1 cleared 2026-07-08; archived from the worktree-root `TODOS.md`** |
| [old-plan-to-auto-fix.md](old-plan-to-auto-fix.md) | The original `feature/Bundle-fixer` plan (standalone fix engine) | Superseded — kept as reference; its "Legacy reference" citations point at code that no longer exists |

The abandoned `feature/Bundle-fixer` branch still exists and holds harvestable domain logic (see the design doc's salvage section), but its architecture is not the one we're building.
