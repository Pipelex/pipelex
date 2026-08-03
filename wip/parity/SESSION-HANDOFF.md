# Session handoff — parity gaps, paused after Phase 1 lands

**Branch:** `fix/Parity-gaps` in the `_gaps/` worktree, off `dev` at `221b8ee0b`. **PR:** [#1085](https://github.com/Pipelex/pipelex/pull/1085) → `dev`, open.

Read this first, then [`README.md`](README.md) and [`parity-gaps-plan.md`](parity-gaps-plan.md) (Checkpoint A holds the full record of what landed).

## Where the work stands

**Phase 1 is complete and committed.** All three dev-buildable fixes landed with their gates, each red-green verified (gate written first, run against the unfixed tree, observed to fail for the stated reason). Nothing is left to build in Phase 1.

Gates all run and green at `d9efffbfb`:

- `make agent-check` ✅
- full `make agent-test` ✅ (~19 min)
- `make drift-check` ✅ — re-run **after** `git add`, because it reads the git index, not the working tree
- real-world confirmation of 1.1 against `../pipelex-cookbook/examples/wip/advisory_board/`: the dangling ref `advisory_orchestrator.master_advisory_orchestrator -> advisory_orchestrator.present_as_markdown` is gone
- `[Unreleased]` changelog entry for each of the three fixes

**Phase 2 is still gated** on the kernel-extraction PRs #1081 / #1082 merging to `dev`. Do not start it before they merge, and re-verify every 2.1–2.3 claim against the merged code first — the plan says so explicitly and the claims were written against unmerged PR code.

## The goal this session was executing

Verbatim, so the new session picks up the same contract:

> execute `wip/parity/parity-gaps-plan.md` until it's all done. But do stop at each required checkpoint and, after recording the progress and running `make check` and `make test`, stage the changes and fan out a **Sonnet-5** sub-agent to run the skill `/code-review`, then sort through the findings with a strict "no over-engineering" judgement.
>
> Then stack the PRs on `dev`, poll CI and the PR review bots, then fan out an **Opus 5** sub-agent to check their feedback, deduplicate, verify each item, arbitrate to solve it ONLY if it's a clear win (avoid over-engineering, don't guard impossible scenarios). Resolve the threads, push the fixes, rinse and repeat. Pinging `@greptileai` and `@cubic-dev-ai` in a comment re-triggers them.
>
> When the PR review bots are all happy, fan out an **Opus 5** sub-agent to run gstack's `/review wip/parity/parity-gaps-plan.md` and finalize the PR.
>
> **No over-engineering.** In case of any doubt, defer the issue for later as a `.md` in `./wip/parity/` — include that instruction in every sub-agent's context.
>
> **Fan-out convention for `/code-review`:** spawn each review sub-agent with **no inherited context** — hand it only a pointer to the changes under review (the phase's commit SHA, `git diff <base>..HEAD`, or the working-tree files), never the plan, the rationale, or your own conclusions.

## Next actions, in order

1. ~~Checkpoint A's code review (Sonnet-5 `/code-review`, no inherited context, pointed at `d9efffbfb`).~~ Fanned out.
2. ~~Open the PR.~~ [#1085](https://github.com/Pipelex/pipelex/pull/1085).
3. **Poll CI + the review bots**, then fan out an Opus 5 sub-agent over their feedback (dedupe, verify each item, fix only clear wins). Resolve threads, push, ping `@greptileai` / `@cubic-dev-ai` to re-trigger, repeat until clean.
4. **Finalize** with an Opus 5 sub-agent running gstack's `/review wip/parity/parity-gaps-plan.md`.
5. **Phase 2** only after #1081 / #1082 merge, re-verifying 2.1–2.3 against the merged code.

## What changed, file by file

| File | What |
| --- | --- |
| `pipelex/libraries/crate_normalization.py` | `_index_pipe_refs_by_code` + `_qualify_pipe_ref` resolving crate-wide, raising on ambiguity/absence |
| `pipelex/libraries/exceptions.py` | `CrateNormalizationError` docstring names the new raise reasons (the docstring is the generator source for `docs/errors/crate-normalization-error.md`; it must fit 150 columns on one line) |
| `pipelex/codegen/emitters/python_structures.py` | `_base_class` emits `TextContent` for a structureless concept, root base for a Python-class-backed one |
| `pipelex/codegen/emitters/python_common.py` | `_import_statement` pre-explodes past `PY_EXPLODE_WIDTH` |
| `tests/unit/pipelex/libraries/test_crate_normalization.py` | `_cross_domain_crate` fixture + closedness / cross-domain / special-outcome / ambiguity / absence tests |
| `tests/unit/pipelex/codegen/test_projection_agrees_with_runtime_base.py` | new — the four-shape ancestor-agreement gate |
| `tests/unit/pipelex/codegen/test_emitted_artifacts_are_lint_clean.py` | `_assert_ruff_clean` split so the new import-block format-stability test reuses the format half |
| `docs/under-the-hood/codegen-projections.md`, `docs/errors/crate-normalization-error.md` | doc updates (the errors page is generated — regenerate with `make generate-error-pages`, never hand-edit) |
| `CHANGELOG.md` | three `[Unreleased]` → `Fixed` entries |
| `wip/parity/*` | plan (Checkpoint A recorded), README status, D-1 deferral note, this file |

## Things worth knowing before touching this again

- **The D-1 deviation is deliberate and argued.** The plan recommended "own domain first, then crate-wide"; what landed is crate-wide only. `PipeLibrary.get_optional_pipe` does *not* prefer the caller's domain — it raises on an ambiguous bare code — so the own-domain rung would have created a fresh disagreement in the exact case the two resolutions differ. Full table in [`d1-domain-hint-deferred.md`](d1-domain-hint-deferred.md). If a reviewer pushes back, that doc is the answer, not a reason to change the code.
- **One plan grounding claim was stale** and is corrected in Checkpoint A: the lint-clean test already ran `ruff format --check`, parametrized down to line-length 88. The real hole was coverage — no crate shape produces an import line past 88, since each native content class lives in its own module — so 1.3's gate is a direct test on `render_import_block`, not another crate fixture.
- **`extra="allow"` stayed** on the structureless arm, per the plan. It no longer does load-bearing work (the class now carries a real `text` field), which was always its actual job: pass-through of unknown fields.
- **The keyword-only hook fires on every edit** under `pipelex/`. Record a subject grant *before* running checks if a subject should stay positional — `make agent-check` runs the auto-fixer, which will silently keyword-only an ungranted one.
- **`make agent-test` takes ~19 minutes.** Run it in the background and use the targeted paths from `tests/CLAUDE.md` while iterating.
