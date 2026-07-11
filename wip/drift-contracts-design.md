# Drift Contracts — deterministic review obligations between code, docs, and tests

## Status

Design accepted and implemented (engine in Phase 1, wiring/seeds/docs in Phase 2 — see `TODOS.md` for execution state and the engineering-review decisions that refined this text). The main refinement over the original proposal: digests are computed from the **git index** (staged blob OIDs via `git ls-files -s`), not from working-tree bytes — see "The validity rule" below.

## Problem

CLAUDE.md already states the policy ("document at every iteration", "keep the toml files and configs.py in sync", "keep specs and conformance in sync"), but prose policy is advisory: nothing tells a PR author — human or agent — *which* docs and tests are stale relative to *this* change, and nothing records that the check happened. The research brief proposes a deterministic traceability tool for this. This design adapts that proposal to what the Pipelex repo already has, and deliberately simplifies it in several places.

## What the repo already has — and the actual gap

The brief describes a greenfield. We are not greenfield. Three synchronization tiers already exist in some form:

| Tier | Mechanism | Judgment needed | Status in this repo |
|---|---|---|---|
| **Derived** | Regenerate + diff: `check-config-sync`, `check-mthds-schema`, `check-gateway-models`, `check-rules`, `generate-error-pages` | None — output is a pure function of sources | **Exists**, wired into `make check` and CI |
| **Linkage** | Referential integrity of declared cross-references: `conformance/scripts/check-spec-links.py` (spec `> Verified by:` ↔ test `pytest.mark.spec`) | None — links either resolve or they don't | **Exists** for the spec/conformance pair |
| **Review** | "This code changed → these docs/tests must be *looked at* against this exact change, and the look must be recorded" | Yes — a human or agent must judge whether the prose/tests still hold | **Missing** — this is the gap |

This framing yields the first design principle: **the new tool covers only the review tier**. Derived checks stay exactly where they are (Makefile + `pipelex-dev` commands); they are strictly better than review contracts because they need no judgment and can't be rubber-stamped. Whenever a review contract turns out to be mechanizable — the doc section could be generated, the sync could be checked structurally — the right move is to *delete the review contract and write a derived check*. The best review contract is one you eventually mechanize out of existence.

## Core model

A **drift contract** declares: "when these trigger files change, these review targets must be re-examined, and the examination must be acknowledged." The system has three pieces:

- a **manifest** (`drift.toml`, repo root, human-authored) declaring contracts;
- **ack state** (`.drift/acks/<contract-id>.toml`, one file per contract, tool-written, committed) recording the last fulfilled review;
- a **CLI** (`pipelex-dev drift plan|check|ack`) that computes obligations, gates CI, and records acks.

### The validity rule — one equality, no base ref

This is the main deviation from the brief. The brief computes obligations from a git diff against a configurable base ref, then compares hashes against a review record. That drags in a whole class of problems: which base ref, how CI resolves it on stacked branches, force-pushes, merges from dev. None of it is needed. The validity rule is a single equality over tree content:

> A contract is **fulfilled** iff the stored ack digest equals the digest recomputed from the current tree. Otherwise it is **open**.

The digest for a contract is `sha256` over: the contract's own definition (canonically serialized — sorted keys and sorted glob lists, so reformatting or reordering `drift.toml` never churns the digest), plus the sorted list of `(path, content-hash)` pairs for every tracked file matching its trigger globs. Content hashes are the **staged blob OIDs from the git index**, read via a single `git ls-files -s` over the matched paths — matching and hashing share the same index source, hashing is filter-normalized (CRLF/smudge safe), and the digest covers exactly what lands in the commit. The cost of index semantics: trigger files must be `git add`-ed before `drift ack` to be covered (staged, not committed; other unstaged changes are fine).

Properties that fall out of this rule:

- **No base ref, no git diff, no timestamps.** `drift check` needs only the working tree and the committed ack files. It gives the same answer locally, in CI, on a rebase, on a squash-merge.
- **The ack travels with the content.** Merging dev into a feature branch brings dev's trigger changes *and* dev's acks in the same tree, so digests match again automatically. A PR that changes triggers without re-acking fails; a PR that changes nothing passes; there is no "stale relative to what?" question.
- **Editing a contract's definition forces a re-ack** (the definition is inside its own digest). Widening a trigger glob or adding a review target is itself a reviewable event.
- **Adding a contract forces an initial review** — a new contract has no ack, so it is open until someone reviews the targets once and acks. Adoption is explicit, contract by contract.
- **File deletion and rename are covered** — the matched-file set is part of the digest.
- **Merges are backstopped by the digest, not by conflicts.** Two branches re-acking the same contract *can* conflict in its ack file, but a line-wise auto-merge can just as well splice the two acks into one neither branch reviewed — do not rely on the conflict. The guarantee is that `drift check` recomputes the digest over the merged tree, so a spliced or stale ack fails the check: the combined content was never reviewed as a whole. Resolution either way — finish the merge, review, re-run `drift ack` on the merged tree.

Timestamps and reviewer identity are recorded for human audit, but they carry no validity semantics — exactly the brief's "hashes over timestamps" conclusion, taken one step further by removing the diff too.

### Directionality

Contracts are directional: triggers on one side, review targets on the other. Docs changing does not require re-reviewing code. Where a doc *is* the source of truth (spec-like pages), list it as a trigger of its own contract — symmetry is expressed by putting paths on both sides, not by a special mode.

## Manifest format

TOML, not YAML — this repo's idiom (`pipelex.toml`, `pyproject.toml`), and `plxt` already formats and lints TOML. Root-level `drift.toml` so it is as visible as the policy it enforces.

```toml
version = 1

[contracts.config-docs]
description = "User-facing configuration docs must track the config model and the shipped defaults."
triggers = [
    "pipelex/system/configuration/**/*.py",
    "pipelex/pipelex.toml",
]
review = [
    "docs/configuration/**/*.md",
]
verify_commands = ["make tb"]

[contracts.cli-docs]
description = "CLI docs and the agent-CLI contract doc must track the CLI surface."
triggers = [
    "pipelex/cli/**/*.py",
]
exclude = [
    "pipelex/cli/dev_cli/**",
]
review = [
    "docs/tools/cli/",
    "pipelex/cli/agent_cli/CLAUDE.md",
]
verify_commands = []
```

Notes on the schema:

- One flat `review` list instead of the brief's `docs:/tests:/examples:` sub-maps — paths self-describe their category, and the packet renderer can group by prefix if grouping ever helps. Fewer fields, less ceremony.
- `triggers`, `exclude`, and `review` take globs or paths, matched against `git ls-files` output only (tracked files — untracked noise and `.gitignore` handling come free, and CI sees the same set).
- `verify_commands` are commands `drift ack` runs before writing the ack (see below). They should be *targeted* (a specific pytest path, `make tb`), not the full suite — CI runs the full gates anyway.

## Ack state format

One file per contract under `.drift/acks/`, committed. Per-contract files keep unrelated PRs from conflicting on a shared state file; two branches re-acking the *same* contract may conflict, and either way the post-merge digest recompute is what catches an unreviewed combination (see above).

```toml
contract = "config-docs"
digest = "sha256:4e03f2a1…"
reviewed_by = "louis"
reviewed_at = "2026-07-03T14:12:09Z"
rationale = "Added the activity_queues setting; documented it in docs/configuration/config-technical/; make tb green. No other config-docs pages affected."

[trigger_files]
"pipelex/system/configuration/configs.py" = "blob:a1b2c3…"
"pipelex/pipelex.toml" = "blob:99ffee…"
```

The per-file map exists for *messaging*, not validity: when a contract is open, `drift plan` diffs the stored map against the current tree to say precisely which trigger files were added, removed, or modified since the last ack — without any git-diff machinery. The previous `rationale` is also shown in the plan packet: the last reviewer's decision is exactly the context the next reviewer wants.

Because acks are committed files, they surface in the PR diff: a reviewer sees the rationale next to the change it covers. That is the audit trail — no CI artifacts, no PR metadata, no bot comments.

## Command surface

Three commands, not the brief's four-plus — manifest validation folds into `check`, and the "review packet" is just the detailed form of `plan`.

```bash
pipelex-dev drift plan [CONTRACT]      # what is open, why, and what to do — markdown by default
pipelex-dev drift check                # CI gate: pure, fast, no command execution
pipelex-dev drift ack CONTRACT --rationale "…"   # run verify_commands, then record the ack
```

Make wrappers follow the existing pattern: `drift-plan`, `drift-check`, `drift-ack`, with `drift-check` added to the `make check` aggregate.

### `drift plan`

Lists open contracts. Per the workspace surface-output conventions, the default output is Markdown — the primary consumer is an agent handed the packet — with `--format json` for software. For each open contract: description, which trigger files changed/appeared/vanished since the last ack, the review targets, the verify commands, and the previous rationale. With a `CONTRACT` argument, the full packet for that one contract.

```markdown
## Open contract: config-docs

User-facing configuration docs must track the config model and the shipped defaults.

**Trigger changes since last ack** (by louis, 2026-07-03, "Added the activity_queues setting…"):

- modified: pipelex/system/configuration/configs.py
- modified: pipelex/pipelex.toml

**Review targets:**

- docs/configuration/**/*.md

**To fulfill:** review the targets against the trigger changes, update what is stale, then run
`make drift-ack CONTRACT=config-docs RATIONALE="…"` (this runs: make tb).
```

### `drift check`

The CI gate. Pure and fast (glob matching + digest comparison; it shells only to git plumbing — `ls-files` — and never executes verify commands): it validates that the manifest parses and is schema-valid, that every trigger glob matches at least one tracked file (dead globs are manifest rot — hard error), that every review target resolves to something that exists, that every contract has an ack, and that every ack digest matches the recomputed digest. Non-zero exit prints, per open contract, the same actionable block CI users get from the other check targets — ending with "run `make drift-plan`".

`drift check` goes into `make check` and CI. It deliberately does **not** go into `make agent-check`: that target is the tight post-edit lint loop, and doc-review obligations belong at the end of a change, not after every edit. The failure message in CI is the agent's entry point.

### `drift ack`

Requires `--rationale`. Runs the contract's `verify_commands` first; any failure aborts the ack — no `--skip-verify` flag in the MVP, because every escape hatch here is a rubber-stamp invitation, and the real escape hatch already exists (acking with a rationale that says "no doc change needed" is legitimate and cheap). `reviewed_by` defaults from `git config user.name`, overridable with `--by` (agents pass their identity). Recomputes the digest from the **index** at ack time (stage trigger files with `git add` first — unstaged edits and untracked files are not covered, and the command warns when it sees one matching the triggers), writes the ack file; the ack then gets committed together with the change it covers. If files move again after the ack, CI's `drift check` catches the mismatch — so a clean tree is *not* required.

## Decisions, mapped to the brief's open questions

- **Review state inside the manifest or separate?** Separate. The manifest is human-authored and low-churn; acks are tool-written and change with every fulfilled review. One file per contract to keep any merge conflict scoped to the contract it concerns (the real merge safety net being the post-merge digest recompute).
- **Acks in repo, CI artifacts, or PR metadata?** In repo. Anything outside the tree breaks the local-equals-CI property and hides the audit trail from the PR diff.
- **Review identity for agents?** A plain string. Git already attributes the commit; `reviewed_by` is context, not authentication. Agents should pass something resolvable (e.g. model name or session URL).
- **Should ack require a clean tree?** No. Agents ack mid-flow before committing; digest mismatch after later edits is caught by `check`.
- **Human override label in CI?** No. The ack *is* the override — it costs one command and one honest sentence. A second bypass channel would only bypass the audit trail.
- **Granularity for v1?** Files and globs only. Symbol-level triggers (griffe), markdown heading anchors, and pytest node-ID validation are all deferred — they add dependency weight and slow the check, and the seed contracts below don't need them.
- **Generated docs as review targets?** Excluded. Generated artifacts (`docs/errors/`, `derived/mthds_schema.json`, gateway model docs) belong to the derived tier and must never appear in `review` lists — reviewing generator *output* is how you end up editing generated files, which we already forbid.
- **Infer candidate contracts from coverage/imports?** Not in scope. Manifest growth should follow pain, not tooling enthusiasm.

## What this deliberately does not do

Unchanged from the brief, and worth restating because they bound the tool's promises:

- It does not prove docs are semantically correct — it proves the declared reviewer looked, at this exact content, and said so on the record.
- It does not trace the whole repo. Contracts are added one at a time, where staleness has actually hurt.
- It does not replace the CLAUDE.md documentation culture; it enforces the culture's floor on the few surfaces where silent drift is most expensive.

And one addition: it does not handle cross-repo contracts. The spec/conformance pair spans the workspace root and the `conformance/` repo and already has a purpose-built checker (`check-spec-links.py`) doing linkage-tier validation with in-file markers; `drift` is per-repo and should not absorb it. If cross-repo review contracts become pressing, that is a separate design.

## Failure modes, honestly

- **Rubber-stamping.** The tool cannot force a real review. Mitigations: mandatory rationale, PR-visible ack diffs, verify commands at ack time, and — most importantly — keeping the contract count low enough that each open contract is a genuine event rather than background noise. If we observe reflexive acks ("docs fine" on every PR), the contract is mis-scoped: either narrow its triggers or mechanize it into a derived check.
- **Review fatigue from over-broad triggers.** `pipelex/cli/**` will open the cli-docs contract on pure refactors. Acceptable at first (the ack costs a sentence); if it grates, narrow triggers to the surface-defining modules rather than adding bypass mechanisms.
- **Manifest rot.** Dead globs and vanished review targets are hard `check` failures, so rot is loud, not silent.
- **Ack-file merge conflicts.** Scoped per contract; possible but not guaranteed (a line-wise auto-merge can splice two acks silently). The real safety net is the post-merge digest recompute in `drift check`. Documented resolution: merge, review, then re-ack.
- **Line-ending/filter edge cases.** Resolved by construction: digests use staged blob OIDs from the index, which are filter-normalized, so a smudge/clean filter or CRLF checkout cannot make local and CI hashes differ.

## Seed contracts

Start with three, all in the `pipelex` repo, all places where prose has already drifted or plausibly will (exact target lists to be settled at implementation time against the current docs tree):

- **config-docs** — triggers: `pipelex/system/configuration/**/*.py`, `pipelex/pipelex.toml`; review: `docs/configuration/**`; verify: `make tb`. The structural toml↔configs.py sync is already mechanized by `check-config-sync` and `make tb`; this contract covers what those cannot — the prose.
- **cli-docs** — triggers: `pipelex/cli/**/*.py` excluding `dev_cli/`; review: `docs/tools/cli/`, `pipelex/cli/agent_cli/CLAUDE.md`. The agent-CLI output-format contract doc is load-bearing for the whole workspace's surface conventions.
- **keyword-only-convention** — triggers: `pipelex/cli/dev_cli/commands/keyword_only_guard.py`; review: `docs/contribute/keyword-only-arguments.md`. Small, sharp, and the doc is explicitly the convention's specification.

Candidates deliberately *not* seeded: anything under `wip/` (not release-facing), generated pages (derived tier), broad feature docs (too noisy to start), spec/conformance (covered, cross-repo).

## Rollout plan

### Phase 1 — engine

Implement `drift plan|check|ack` as `pipelex-dev` commands (`pipelex/cli/dev_cli/commands/drift_cmd.py` or a small sub-package), with manifest parsing, digest computation, ack read/write, and unit tests covering: digest stability, contract-definition-in-digest, added/removed/modified trigger reporting, dead-glob and missing-target failures, ack-then-edit invalidation.

**Checkpoint 1:** engine green under `make agent-test`, no Makefile or CI wiring yet. Natural handoff — the remaining work is integration and manifest authoring, a fresh session can pick it up from the tests.

### Phase 2 — wiring and seeds

Add the `drift-plan` / `drift-check` / `drift-ack` Make targets, put `drift-check` into the `make check` aggregate (and thereby CI), author `drift.toml` with the three seed contracts, perform the three initial reviews for real (not rubber-stamped — this is the first dogfood), and commit the initial acks. Document the system: a page under `docs/contribute/` explaining contracts, the ack workflow, and the merge-conflict resolution rule.

**Checkpoint 2:** CI enforcing, seeds live. Then **stop and dogfood for a few weeks of normal PRs** before growing the manifest. The open question that only usage can answer: is the ack friction proportionate to the staleness it catches?

### Phase 3 — agent ergonomics (after dogfooding verdict)

Polish the `plan` packet for agent consumption, add `--format json` for software consumers, and teach the workflow to agents where they already look: a short section in the contributor docs and, if warranted, the failure-message text itself is usually enough — agents follow actionable CI errors well. Consider a repo-local skill only if the raw commands prove insufficient.

### Deferred

- Symbol-level triggers via griffe; markdown-anchor targets; pytest node-ID validation via `--collect-only`.
- Unifying the derived-tier checks into `drift plan` output as read-only `kind = "derived"` entries, so one command shows the full sync map. Nice-to-have; duplicates Makefile wiring today.
- Cross-repo contracts (workspace-root specs, conformance, downstream consumers).
- Semantic assistance: `cocode`'s doc/code drift proofreading could consume the plan packet as its work list — the deterministic layer decides *what* to look at, cocode helps judge *whether* it drifted.
- Extraction into a standalone tool for the other workspace repos, if the pipelex-repo dogfood earns it.

## Bottom line

Keep the brief's core inversion — a deterministic tool decides which reviews are owed and whether they were fulfilled; agents and humans merely fulfill them — but strip the mechanism to one equality: *ack digest == current digest, computed from tree content alone*. No base refs, no timestamps, no diff plumbing, no separate validate command, no override channel. Three commands, a TOML manifest, per-contract committed acks, three seed contracts, and a hard rule that anything mechanizable becomes a derived check instead. If the dogfood shows the acks catching real staleness at tolerable friction, grow the manifest; if it shows ceremony, we will have learned that cheaply.
