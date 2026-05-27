# API team handoff — `feature/API-readiness-2`

**Status.** In-repo work on this branch is at a natural pause point. The branch is shippable as a coherent unit; no PR is open yet. Two threads still need API-team coordination (one cross-repo, one in-repo follow-up). This doc is a *launchpad* for the next session — it tells you what to read and what to decide, not what to write.

> The execution ledger originally lived at the repo root as `TODOS.md`; it was archived 2026-05-28 to `wip/error-handling/archive-todos-api-readiness-2.md`. Paths below refer to the archived location.

**Audience.** A fresh Claude Code session pointed at this file by Louis.

---

## How to use this doc

Do **not** draft anything from this file alone. Read the authoritative sources first, then come back here to follow the structure.

Cold-start reading order:

1. `wip/error-handling/archive-todos-api-readiness-2.md` end-to-end — Phases, Decisions, full Session log. The Session log is the ground truth for what shipped.
2. `wip/error-handling/README.md` and the tracker docs it links.
3. `wip/security/webhook-signing.md`.
4. `git log main..HEAD --oneline` and `git diff main...HEAD --stat` to see the actual shape of the branch.
5. The repo-root `CLAUDE.md` for the workspace map — which downstream repos (`pipelex-api`, `pipelex-platform`, `pipelex-api-deploy`, `pipelex-app`, `pipelex-back-office`, `n8n-nodes-pipelex`, cookbooks/templates) consume what.

Only after that should you produce the deliverables (below).

---

## What sits on this branch

Don't restate it. Re-derive from `wip/error-handling/archive-todos-api-readiness-2.md` + the Session log entries for the completed Checkpoints. The shape is:

- A coherent error-handling and webhook-contract overhaul (multiple Phases, all in-repo).
- One large structural refactor of where error classes live in the source tree.
- A documented follow-up that the recent `/code-review` pass uncovered, partially fixed, and partially deferred.

What's **not** on this branch: webhook signing (the cross-repo track) and the discovery-contract follow-up. Both are flagged in `wip/error-handling/archive-todos-api-readiness-2.md`.

---

## Topics to cover when talking to the API team

Bucket them — don't list flat. For each topic, re-derive the actual change from the source files and decide which API-side repo it touches. The buckets:

- **Behavior changes in shipped code** — anything that changes what an API caller / webhook subscriber / Temporal log consumer sees.
- **Code-shape changes** — anything that affects import paths, exception-type names, or the surface that downstream tests pin against.
- **Docs-site state** — what's in `docs/errors/` right now, including anything temporarily missing or renamed.
- **Cross-repo work still pending** — the security track + the follow-up Phase.

For each topic, tag with: (a) which API-side repo is affected, (b) whether it's a breaking change, (c) whether the API team needs to act in lockstep with this PR landing or just be aware.

---

## Questions to resolve before drafting anything

- Which topics require API-side action vs. only awareness?
- Does any behavior change need a coordinated rollout (version pin, feature flag, joint release)?
- What's the version-bump / `CHANGELOG.md` `[Unreleased]` strategy for this branch? Look at the current `[Unreleased]` block before adding to it.
- Is now the right moment to kick off the deferred cross-repo track, or should it wait until this branch lands?
- Which downstream repo is the right *first* recipient of the handoff? (The list of consumers is in the repo-root `CLAUDE.md`.)
- Should the deferred in-repo follow-up be flagged to the API team at all, or kept internal?
- What's the right communication channel — Slack, PR description, GitHub issue, a cross-repo doc?

---

## Deliverables expected from the fresh session

1. **A short plan for Louis.** Order of operations (PR first vs. message first vs. parallel), risks, recommended next action. Two paragraphs max.
2. **A draft handoff message in two forms:**
   - *Human form* — short, points at source docs, suitable for Slack/email.
   - *Agent-prompt form* — self-contained, suitable for pasting into a Claude Code session in one of the API-side repos to drive their adaptation work. Should give that downstream agent enough context to read the right files in *this* repo without needing follow-up.

Both forms should *point at* source-of-truth docs, not restate them. The API team will read the PR and the tracker files directly.

---

## Don'ts

- Don't restate the Session log here. Point at it.
- Don't enumerate every changed file, moved class, or renamed module. Point at the relevant Checkpoint entry.
- Don't draft the handoff message *inside this file*. That's a deliverable, not a tracker.
- Don't treat the deferred Phases as in progress. They aren't.
- Don't expand this file as new work lands. If the picture changes, update `wip/error-handling/archive-todos-api-readiness-2.md` (the source of truth) and revisit this brief.
