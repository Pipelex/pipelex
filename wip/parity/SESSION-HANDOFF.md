# Session handoff — parity gaps, both phases built

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

**Phase 2 is built too — but not on this branch.** The plan gated it on #1081/#1082 merging; Louis overrode that gate, because each of these is a defect *those PRs introduce*, so deferring meant merging a package whose stated contract is false and then re-opening the same files to repair it. Phase 2 therefore shipped **inside** the kernel stack, in the `_kernel/` worktree:

| Gap | Outcome | Commit |
| --- | --- | --- |
| 2.1 `llm_text` narrowness | fixed | `9fbb12f34` on `refactor/Kernel` (#1081) |
| 2.2 `llm_object` prompting style | **withdrawn** — not a live defect | silenced by `f688989a6` (#1081); deferred as KF-16 |
| 2.3 kernel cannot build an `ImgGenPrompt` | fixed | `7279effbd` on `refactor/Kernel-phase2` (#1082) |
| — its boot-contract arm | added | `015688747` on `refactor/Kernel-phase3` (#1083) |

**Nothing about Phase 2 lands on `fix/Parity-gaps`.** This branch's only Phase 2 artifact is the plan/README/handoff record you are reading.

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
3. ~~Poll CI + the review bots, fan out an Opus 5 sub-agent over their feedback.~~ Done — CI green, Greptile 5/5 clean, cubic clean, Sonnet-5 `/code-review` clean, one Codex P2 verified pre-existing and deferred. Both bot threads answered inline and resolved.
4. ~~Finalize with gstack's `/review`.~~ Done — verdict **land**. It caught one real defect the other four missed (the `Anything` import omission) plus three doc inaccuracies, all fixed; the rest deferred to [`deferred-review-observations.md`](deferred-review-observations.md).
5. ~~Rounds 3–4: cubic follow-ups.~~ Done. Round 3 = a fair catch on a stale code comment (fixed, `c4788e47b`); round 4 = a P1 duplicate of Codex's round-1 P2, answered with measurements (`e0f2d2362`).
6. **Merge decision is Louis'.** Every prescribed review step in the goal has run. Final state on `e0f2d2362`: **23 checks success, 6 skipped, 0 failures, 0 unresolved threads.** Nothing is pending on the PR.
7. ~~**Phase 2** only after #1081 / #1082 merge.~~ Superseded — folded into the kernel stack instead (see above). What remains there is the stack's own review cycle: push the three branches, poll CI and the bots, and merge in order #1081 → #1082 → #1083.

**One open question wants a human ruling** (it does not block Phase 1): whether a hand-written class should have to be *named* in the `.mthds` to bind, or whether the bare-name auto-detect at `concept_factory.py:389` keeps working. Two independent reviewers converged on it — see [`structureless-concept-with-registered-class.md`](structureless-concept-with-registered-class.md), which now carries the measurements.

## What changed, file by file

| File | What |
| --- | --- |
| `pipelex/libraries/crate_normalization.py` | `_index_pipe_refs_by_code` + `_qualify_pipe_ref` resolving crate-wide, raising on ambiguity/absence |
| `pipelex/libraries/exceptions.py` | `CrateNormalizationError` docstring names the new raise reasons (the docstring is the generator source for `docs/errors/crate-normalization-error.md`; it must fit 150 columns on one line) |
| `pipelex/codegen/emitters/python_structures.py` | `_base_class` emits `TextContent` for a structureless concept, root base for a Python-class-backed one; `_native_class` routes the `Anything` fallback through `_structured_content` so the root base it names is actually imported |
| `pipelex/codegen/emitters/python_common.py` | `_import_statement` pre-explodes past `PY_EXPLODE_WIDTH` |
| `tests/unit/pipelex/libraries/test_crate_normalization.py` | `_cross_domain_crate` fixture + closedness / cross-domain / special-outcome / ambiguity / absence tests |
| `tests/unit/pipelex/codegen/test_projection_agrees_with_runtime_base.py` | new — the four-shape ancestor-agreement gate |
| `tests/unit/pipelex/codegen/conftest.py`, `test_python_structures_emitter.py` | `refines_anything_crate` fixture + the load-the-module gate for the `Anything` fallback |
| `tests/unit/pipelex/codegen/test_emitted_artifacts_are_lint_clean.py` | `_assert_ruff_clean` split so the new import-block format-stability test reuses the format half |
| `docs/under-the-hood/codegen-projections.md`, `docs/errors/crate-normalization-error.md` | doc updates (the errors page is generated — regenerate with `make generate-error-pages`, never hand-edit) |
| `CHANGELOG.md` | three `[Unreleased]` → `Fixed` entries |
| `wip/parity/*` | plan (Checkpoint A recorded), README status, D-1 deferral note, this file |

## Things worth knowing before touching this again

- **The D-1 deviation is deliberate and argued.** The plan recommended "own domain first, then crate-wide"; what landed is crate-wide only. `PipeLibrary.get_optional_pipe` does *not* prefer the caller's domain — it raises on an ambiguous bare code — so the own-domain rung would have created a fresh disagreement in the exact case the two resolutions differ. Full table in [`d1-domain-hint-deferred.md`](d1-domain-hint-deferred.md). If a reviewer pushes back, that doc is the answer, not a reason to change the code.
- **One plan grounding claim was stale** and is corrected in Checkpoint A: the lint-clean test already ran `ruff format --check`, parametrized down to line-length 88. The real hole was coverage — no crate shape produces an import line past 88, since each native content class lives in its own module — so 1.3's gate is a direct test on `render_import_block`, not another crate fixture.
- **`extra="allow"` stayed** on the structureless arm, per the plan, and it is still load-bearing — an earlier version of this note claimed otherwise and was wrong. On a `TextContent` base it preserves every field *alongside* `text`; drop it and pydantic's default `extra="ignore"` strips them silently. What it does not do is let the promoted arm accept an object payload carrying no `text`, because that field is required — and the runtime's class for the same declaration refuses that payload too, which is the agreement 1.2 exists to hold. Verify before re-arguing this: `class X(TextContent): model_config = ConfigDict(extra="allow")` keeps `{"text": …, "source": …}` whole; without it you get `{"text": …}`.
- **The keyword-only hook fires on every edit** under `pipelex/`. Record a subject grant *before* running checks if a subject should stay positional — `make agent-check` runs the auto-fixer, which will silently keyword-only an ungranted one.
- **A green cubic *check* does not mean cubic found nothing.** Its check bucket went `pass` on the same run whose review body said "1 issue found". Read `gh api repos/.../pulls/N/reviews` bodies, not just `gh pr checks`. (Cubic also *edits* an earlier review body in place once threads are resolved, so re-fetching an old review can show a different summary than when it was posted.)
- **The local clock in this worktree is UTC+7.** Filtering the GitHub API with a local-time string silently returns nothing and looks exactly like "the bots have not replied". Always build timestamp filters from `date -u`.
- **`make agent-test` takes ~19 minutes.** Run it in the background and use the targeted paths from `tests/CLAUDE.md` while iterating.
- **Stacked rebases need `--onto`.** Folding Phase 2 into the stack meant rebasing #1082 and #1083 onto rewritten parents. `git rebase <new-base> <branch>` replays the branch's *whole* history including the parent commits already rewritten, which conflicts in every file the parent touched; `git rebase --onto <new-base> <old-base> <branch>` is the correct form, with `<old-base>` the parent tip the branch was actually built on. Verify each one by `git diff <pre-rebase-tag>..<new-tip>` — it must show *exactly* the folded change and nothing else.
- **Never redirect a `git` command's output to `/dev/null`.** `git stash push -- <paths>` refuses when the paths include an untracked file; with the error silenced, the following `git stash pop` applied a *different, unrelated* stash into the tree. It survived only because a conflicted pop does not drop the stash. Use `mv` to set a file aside for a red-green check — `git stash` is the wrong tool whenever untracked files are involved.
- **A fixture that already registers an import cannot gate a missing one.** The `Anything` defect was invisible to `every_type_kind_crate` because its structured concepts import `StructuredContent` anyway. Gating an *omission* needs a crate where nothing else supplies the thing — hence the single-concept `refines_anything_crate`. Worth remembering before adding a shape to a rich fixture and calling it covered.
