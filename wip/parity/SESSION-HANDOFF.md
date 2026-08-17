# Session handoff — parity gaps, both phases built

**Branch:** `fix/Parity-gaps` in the `_gaps/` worktree, off `dev` at `221b8ee0b`. **PR:** [#1085](https://github.com/Pipelex/pipelex/pull/1085) → `dev`, open.

Read this first, then [`README.md`](README.md) and [`parity-gaps-plan.md`](parity-gaps-plan.md) (Checkpoint A holds the full record of what landed).

## Resume here (round 3 fully answered 2026-08-04, ~11:20 local / 04:20 UTC)

**Everything is pushed. Nothing is half-done.** Round 3 ran as four sub-rounds — 3a through 3d, each one cubic re-reviewing the head the previous fix produced — and all of them are arbitrated and answered. The next action is to read whatever comes back on *these* heads, then merge.

**One consistent labelling scheme, since the doc uses it throughout:** rounds 1–2 were the pre-2026-08-04 passes; **round 3** is this session, split into **3a** (the first cubic pass on the round-2 heads), **3b** (the KF-3 holder fix, which rewrote the whole stack), **3c** (the KF range), and **3d** (the spec divergence and the stale-status fixes). Anything below labelled "rounds 3–4" belongs to the *older* #1085-only numbering and is left as written, because it is a historical record of that PR's own cycle.

| PR | Branch / worktree | Round 3 |
| --- | --- | --- |
| [#1081](https://github.com/Pipelex/pipelex/pull/1081) (1/3) | `refactor/Kernel` — `_kernel/` | KF-3's wrong holder fixed (3b); cubic clean on head |
| [#1082](https://github.com/Pipelex/pipelex/pull/1082) (2/3) | `refactor/Kernel-phase2` — `_kernel/` | dead-hash fix (3a); rebased (3b); cubic clean on head |
| [#1083](https://github.com/Pipelex/pipelex/pull/1083) (3/3) | `refactor/Kernel-phase3` — `_kernel/` | fixes in 3a/3b/3c/3d; rebased twice; cubic clean on head |
| [#1085](https://github.com/Pipelex/pipelex/pull/1085) | `fix/Parity-gaps` — `_gaps/` | fixes in 3a/3d; **3d's answer is the one to read**; re-pinged |

**Read heads live** — `for p in 1081 1082 1083 1085; do gh pr view $p --json number,headRefOid; done`. Deliberately not written down: the kernel branches are rebased whenever a parent moves, so any head recorded here is wrong within one push.

**What round 3 produced, in order of what matters.**

1. **A real spec divergence, found in 3d and *not* fixed.** The MTHDS spec says bare pipe references "do NOT fall through to other domains"; the runtime searches across domains and Phase 1's 1.1 mirrored it. Both readers agree with each other and both disagree with the standard — in *two* rows, and in opposite directions. Written up in [`bare-pipe-ref-spec-divergence.md`](bare-pipe-ref-spec-divergence.md); it subsumes D-1, so settle the two together and the spec question first.
2. **KF-3 was pointed at the wrong operator (3b), and the argument rested on it.** `pipe_structure.py` has never referenced `LLMPromptBlueprint` — on any branch, including `dev`. `PipeLLM` holds it as `llm_prompt_spec`. The corrected reading changes the item's shape: **what is production-dead is `make_llm_prompt`, one method — not the model**, which stays. Fixed at the source, hence the stack rewrite.
3. **Round 2's arbitration had a hole (3a).** Recorded below under the rejected findings — the general lesson is there and it is the one worth carrying forward.
4. **Three self-staling constructs were converted, not patched**: commit hashes → subjects, a `KF-1..KF-15` range → the file, and a hardcoded helper count → no count. Each had already gone stale at least once; two produced review findings this round.

Backups to roll back to: `backup/parity-pre-round3` and `backup/kernel-{,phase2-,phase3-}pre-round3b`.

**Greptile and Codex have gone quiet, and the dates are the honest way to say it** — neither has posted anything since **2026-08-02** on the three kernel PRs and **2026-08-03** on #1085, across every push and every ping since. (Dates rather than a round count: the count needs editing on each new round and was already inconsistent with itself inside this file.) Cubic is the only live external signal. Before reading "the bots are clean" as coverage, decide deliberately whether to chase them — the finalization review already demonstrated once that a defect can survive every bot plus a cold `/code-review`.

**This table deliberately carries no head SHAs.** It used to, and they were wrong within one push — the three kernel branches are rebased whenever a parent moves, and every branch moves when a review round lands. Read the live heads instead: `for p in 1081 1082 1083 1085; do gh pr view $p --json number,headRefOid; done`.

**What round 2 produced** (a record of that round, not the current state — see the dates above). Cubic came back on all four heads; **Greptile and Codex did not, despite pings** — cubic was already the only fresh external signal by then, so treat "the bots are happy" with corresponding caution. Its findings were mostly doc-accuracy, and the arbitration is recorded in a comment on each PR. The substantive ones:

- **#1081 — the one that mattered.** `wip/prompting-style/README.md` (since superseded by `prompt-style-as-an-authoring-decision.md` in the same directory) described the prompting style as derived "in two places that must agree" and rested its first argument on exactly that. False since the extraction: `pipe_llm.py:223` calls the kernel's `derive_templating_style`, so there is one site. Left alone, KF-16's design basis would have carried a false premise.
- **#1082.** `ImgGenPromptBlueprint`'s class docstring still advertised the four things it had just delegated to the kernel, contradicting its own module docstring.
- **Deferred as KF-17**, not fixed: the resolvers select the model choice by truthiness, so `model=""` falls through to the deck default. The chain is verbatim from `dev`'s `pipe_llm.py`, the interpreter calls these same functions so no divergence exists, and pydantic already rejects `""` on every authored path. The honest fix is `LLMModelChoice` rejecting `""` at the type boundary once — a deliberate pass, not a spot edit.

**One finding was rejected on verification — do not re-litigate it:** "the changelog gate conflicts with the Phase 2 record" — the line already reads "per user-visible fix", which is the scoping the finding asked for.

**And one rejection was itself half-wrong, which is the lesson worth keeping.** Round 2 reported that "`model` was already optional on `llm_text`". Checked against the code that was false — pre-fix the façade declared `model: LLMModelChoice` with no default — so it was rejected and the round moved on. Round 3 came back with the same subject from the other end: §2.1's own "✅ Done" record *asserted* `model` was already optional. The bot had been echoing this plan, not misreading the code, and rejecting the code claim left the false sentence sitting in the doc to be re-reported. **When a finding is wrong about the code, check whether it is right about a doc that says so** — a claim has to be traced to its source before "verified false" means anything.

**Next actions, in order:**

1. Read the bot feedback on all four — **review bodies and inline comments, not check states** (see the cubic trap below). Greptile posts as *issue comments*; cubic posts *reviews* + issue comments; Codex posts reviews. If Greptile and Codex stay silent again, decide whether to chase them or proceed on cubic alone.
2. Fan out an **Opus 5** sub-agent to dedupe, verify each item, and arbitrate — fixing **only clear wins**, no over-engineering, no guarding impossible scenarios. Anything doubtful becomes a `.md` in `wip/parity/`. Tell the sub-agent it is **STRICTLY READ-ONLY**.
3. Merge in order **#1081 → #1082 → #1083**. #1085 is independent of the stack and can merge whenever Louis chooses.

**A trap this round taught, now written into the kernel plan:** a doc that lives *on* a stacked branch must name commits **by subject, never by SHA**. Every rebase of the parent rewrites every hash on the child, so the SHAs are dead before anyone reads them — including the "corrected" ones a reviewer suggests. Cubic's proposed replacements were themselves already stale when the fix was written.

**Local gates.** `make agent-check` and `make drift-check` green on every branch. Full `make agent-test` green on `refactor/Kernel-phase3`, which is the stack tip and therefore carries all three PRs' content — the only source change in this round is a docstring, so it was not re-run on each branch separately. CI green on all four. Nothing is owed locally.

Each rebase in this round was verified the same way: tag the tip, rebase with `--onto`, then `git diff <pre-rebase-tag>..<new-tip>` and confirm it shows **exactly** the intended change and nothing else. Both rebases conflicted in one file only — the plan's status block, which both sides genuinely edited. That is the legitimate shape; an unexpected conflicted *source* file means the command was wrong, and the right move is to abort rather than resolve.

Backup tags on `origin`, in case a rebase needs undoing: `backup/kernel-pre-fold`, `backup/kernel-phase2-pre-fold`, `backup/kernel-phase3-pre-fold`, `backup/kernel-phase3-pre-2.3`, `backup/kernel-phase3-pre-resplit`, plus this round's `backup/kernel-pre-botround2`, `backup/kernel-phase2-pre-botround2`, `backup/kernel-phase3-pre-botround2`.

## Where the work stands

**Phase 1 is complete and committed.** All three dev-buildable fixes landed with their gates, each red-green verified (gate written first, run against the unfixed tree, observed to fail for the stated reason). Nothing is left to build in Phase 1.

Gates all run and green at `d9efffbfb`:

- `make agent-check` ✅
- full `make agent-test` ✅ (~19 min)
- `make drift-check` ✅ — re-run **after** `git add`, because it reads the git index, not the working tree
- real-world confirmation of 1.1 against `../pipelex-cookbook/examples/wip/advisory_board/`: the dangling ref `advisory_orchestrator.master_advisory_orchestrator -> advisory_orchestrator.present_as_markdown` is gone
- `[Unreleased]` changelog entry for each of the three fixes

**Phase 2 is built too — but not on this branch.** The plan gated it on #1081/#1082 merging; Louis overrode that gate, because each of these is a defect *those PRs introduce*, so deferring meant merging a package whose stated contract is false and then re-opening the same files to repair it. Phase 2 therefore shipped **inside** the kernel stack, in the `_kernel/` worktree:

| Gap | Outcome | Commit (by subject — the stack is rebased, so hashes die) |
| --- | --- | --- |
| 2.1 `llm_text` narrowness | fixed | *make llm_text as wide as the op beneath it* — `refactor/Kernel` (#1081) |
| 2.2 `llm_object` templating style | **withdrawn** — not a live defect; deferred as KF-16, now **closed** | silenced by the KF-16 numbering commit on #1081, which added the `llm_object` docstring recording why its single `model` is correct (its subject line is truncated in git — *"…to keep the stack's"* — so match on `KF-16`). **KF-16 closed 2026-08-14 by dissolution** on `fix/Keyless-dry-run` (*Phase 1 — templating style becomes an authoring decision on the LLM path*): the derivation is deleted, the style is authored on the pipe, and that docstring goes with it |
| 2.3 kernel cannot build an `ImgGenPrompt` | fixed | *let a runtime-only caller build the image prompt it has to pass in* — `refactor/Kernel-phase2` (#1082) |
| — its boot-contract arm | added | *give the image prompt assembler the boot-contract arm the rule owes it* — `refactor/Kernel-phase2` (#1082), same PR as the entry point |
| — the kernel doc's drift review | recorded | *record the image prompt assembler on the page that specifies the kernel* — `refactor/Kernel-phase3` (#1083), where the doc and its contract live |

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
6. **Merge decision is Louis'.** Every prescribed review step in the goal has run. That was the state **as of `e0f2d2362`, before round 3** — 23 checks success, 6 skipped, 0 failures, 0 unresolved threads. It is a record of that moment, not of the current head: round 3 (3a–3d) has landed since. The top of this file is the current summary, and heads are read live rather than written down. Check the head before reading "nothing is pending".
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
- **⚠ Crate-wide resolution is a *runtime-parity* choice, not the spec's rule — and the MTHDS standard says the opposite.** The spec sentence is *"Bare pipe references do NOT fall through to other domains or other packages"*, from § *Resolution Order for Bare Pipe References* in the sibling **`mthds/` repo** at the workspace root — **not in this repo**, so it will not resolve from a `pipelex` checkout. The runtime's `get_optional_pipe` searches across domains anyway, and 1.1 mirrored it on purpose. The two readers now agree with each other and **both disagree with the standard, in two places and in opposite directions** — looser on one row, stricter on the other. That is the right stopping point for a parity change and the wrong place to leave the story untold — written up with the full table in [`bare-pipe-ref-spec-divergence.md`](bare-pipe-ref-spec-divergence.md), which also explains why it subsumes D-1. Do not "fix" either reader alone.
- **One plan grounding claim was stale** and is corrected in Checkpoint A: the lint-clean test already ran `ruff format --check`, parametrized down to line-length 88. The real hole was coverage — no crate shape produces an import line past 88, since each native content class lives in its own module — so 1.3's gate is a direct test on `render_import_block`, not another crate fixture.
- **`extra="allow"` stayed** on the structureless arm, per the plan, and it is still load-bearing — an earlier version of this note claimed otherwise and was wrong. On a `TextContent` base it preserves every field *alongside* `text`; drop it and pydantic's default `extra="ignore"` strips them silently. What it does not do is let the promoted arm accept an object payload carrying no `text`, because that field is required — and the runtime's class for the same declaration refuses that payload too, which is the agreement 1.2 exists to hold. Verify before re-arguing this: `class X(TextContent): model_config = ConfigDict(extra="allow")` keeps `{"text": …, "source": …}` whole; without it you get `{"text": …}`.
- **The keyword-only hook fires on every edit** under `pipelex/`. Record a subject grant *before* running checks if a subject should stay positional — `make agent-check` runs the auto-fixer, which will silently keyword-only an ungranted one.
- **A green cubic *check* does not mean cubic found nothing.** Its check bucket went `pass` on the same run whose review body said "1 issue found". Read `gh api repos/.../pulls/N/reviews` bodies, not just `gh pr checks`. (Cubic also *edits* an earlier review body in place once threads are resolved, so re-fetching an old review can show a different summary than when it was posted.)
- **The local clock in this worktree is UTC+7.** Filtering the GitHub API with a local-time string silently returns nothing and looks exactly like "the bots have not replied". Always build timestamp filters from `date -u`.
- **`make agent-test` takes ~19 minutes.** Run it in the background and use the targeted paths from `tests/CLAUDE.md` while iterating.
- **Stacked rebases need `--onto`.** Folding Phase 2 into the stack meant rebasing #1082 and #1083 onto rewritten parents. `git rebase <new-base> <branch>` replays the branch's *whole* history including the parent commits already rewritten, which conflicts in every file the parent touched; `git rebase --onto <new-base> <old-base> <branch>` is the correct form, with `<old-base>` the parent tip the branch was actually built on. Verify each one by `git diff <pre-rebase-tag>..<new-tip>` — it must show *exactly* the folded change and nothing else.
- **Never redirect a `git` command's output to `/dev/null`.** `git stash push -- <paths>` refuses when the paths include an untracked file; with the error silenced, the following `git stash pop` applied a *different, unrelated* stash into the tree. It survived only because a conflicted pop does not drop the stash. Use `mv` to set a file aside for a red-green check — `git stash` is the wrong tool whenever untracked files are involved.
- **A fixture that already registers an import cannot gate a missing one.** The `Anything` defect was invisible to `every_type_kind_crate` because its structured concepts import `StructuredContent` anyway. Gating an *omission* needs a crate where nothing else supplies the thing — hence the single-concept `refines_anything_crate`. Worth remembering before adding a shape to a rich fixture and calling it covered.
