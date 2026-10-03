---
status: active
item: L-260919-9965d0
---

# Judgment family — what is left, and in what order

Phases 1 and 2 are built and reviewed, and the design was ratified on 2026-09-20, so nothing is waiting on a decision. Three things finish the campaign, and they are ordered: the last branch lands, the standard change merges, then phase 3 is written. `design.md` holds the contracts and the ratified decisions; `plan.md` is the tracker and carries phase 3's checklist; this file is the way back in.

Re-derive where things stand rather than trusting a note: `gh pr list --repo Pipelex/pipelex`, `wt list`, and `ledger show <id>`.

## 1. Land #1216 — `pipelex`

The bottom two pull requests of the stack have landed on `dev`: #1214 (phase 1, the spike, its findings and the campaign documents) as `fbe8dffa9`, and #1215 (phase 2a, the judgment family at the cogt level) as `9d54f072b`. Before #1215 landed, its deck file was renumbered `6_judgment_deck.toml`, so that it no longer shares the `5_` prefix with `5_doc_gen_deck.toml`. One pull request is left, and it now targets `dev`:

| PR | Branch | Worktree | What it carries |
| --- | --- | --- | --- |
| #1216 | `feature/Typesafe-backend` | `_pipelex--typesafe-backend` | Phase 2b: the TypeSafe backend, and the ratification |

Land it with `/ledger-land pipelex#1216 --merge`, which squashes it into `dev`, reaps the worktree and reads the body's ledger lines. If `dev` has moved since the branch last took it in, merge `origin/dev` into the branch first so CI runs against the real `dev`. Where that merge conflicts on a file #1215 also touched, the branch's side is dev's content plus the TypeSafe layer, so keep it and add only what `dev` has gained since.

**Never rebase this branch.** A rebase rewrites its commits, the recorded `/rev` passes stop being ancestors of the head, and the merge gate then refuses the landing. Merging `dev` in, by `git merge origin/dev` or `gh pr update-branch`, is safe.

#1214 closed L-260919-3aeab8 and advanced the epic, #1215 advanced L-260919-502f36, and #1216 closes it. Once #1216 is on `dev`, checkpoint 1's release condition is met — the `typesafe` extra is no longer published against an SDK nothing imports — and the changelog entries under `## [Unreleased]` announce the family and the backend together.

## 2. The standard change — `mthds`

Item L-260919-178ad6, and phase 3 cannot go green before it. In `mthds`, re-pin the native set in `docs/spec/native-concepts.md` at a new standard version, and add `PipeJudge` to the language reference:

- `YesNo` — unchanged required `yes_no`, plus optional `probability`.
- `Choice` — required `choice`; optional `confidence` and `probabilities`.
- `Rating` — required `level`; optional `confidence`, `probabilities` and `position`.

Two questions are this change's own to settle, and the design's position on each is recorded on the item: `Choice` and `Rating` join the out-of-matrix natives, and a light-form `YesNo` stays the bare boolean. `PipeJudge`'s template field is `question`, with `prompt` accepted as a synonym.

It is done when the page has merged **and** the sibling `mthds/` checkout at the workspace root has been refreshed, because `tests/unit/pipelex/core/concepts/test_pinned_natives_vs_standard.py` reads that page live from it.

## 3. Phase 3, the operator — `pipelex`

Item L-260919-406599, blocked by both steps above. `wt add --for L-260919-406599`, `ledger claim` from inside it, and work the phase 3 checklist in `plan.md`, which already carries what ratification costs each step. Its first item, the natives in the engine, is the one that may be worth a pull request of its own.

## Loose ends to pick up on the way

- **Unverified review deferrals**, listed in `plan.md` at checkpoint 2: the wildcard arm in `_check_answer_is_offered`, the unread `retry-after-ms` header, the status-less `TypeSafeError` sitting in the shared classifier's table, and `typesafe_answer: Any` in the translation. Each is a reviewer's claim nobody has checked.
- **Filed elsewhere**: L-260919-9da413, the Temporal activity and queue for the leaf, owned by `pipelex-server`; and L-260919-afb6c0, the protocol's missing `judgment` model category, owned by `mthds`.
- **Leases**: release them when pausing with `ledger wrap-up`, and claim again with `ledger claim <id> --renew` from inside the worktree when picking the work back up.
