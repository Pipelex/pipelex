# Drift Contracts

Drift contracts turn the "keep docs in sync with code" policy from advisory prose into a deterministic, mechanically-checked obligation. A **drift contract** declares: *when these trigger files change, these review targets must be re-examined against the change, and the examination must be recorded.* The tool cannot judge whether a doc is still correct — that takes a human or an agent — but it can prove, deterministically, that someone looked at this exact content and said so on the record.

## The three synchronization tiers

Not every code↔doc relationship deserves a review contract. This repo distinguishes three tiers, and a drift contract is the right tool only for the last one:

| Tier | Mechanism | Judgment needed |
|---|---|---|
| **Derived** | Regenerate and diff: `check-config-sync`, `check-mthds-schema`, `check-gateway-models`, `generate-error-pages`, `generate-error-identity` | None — the output is a pure function of its sources |
| **Linkage** | Referential integrity of declared cross-references (the spec ↔ verifying-test back-link pair) | None — links either resolve or they don't |
| **Review** | Drift contracts: "this changed → that must be looked at, and the look recorded" | Yes — someone must judge whether the target still holds |

The standing rule: **anything mechanizable becomes a derived check.** If a review contract keeps opening and the review is always the same mechanical comparison, delete the contract and write a derived check instead — it needs no judgment and can't be rubber-stamped. The best review contract is one you eventually mechanize out of existence. Corollary: generated artifacts (`docs/errors/`, `derived/`, `tests/data/errors/error_identity.txt`, gateway model docs, the migration goldens) must never appear in a contract's `review` list — reviewing generator *output* is how you end up editing generated files, and a generated artifact's staleness is already somebody's derived check.

**A review target does not have to be prose.** Most are docs, because most staleness is a sentence that stopped being true — but the obligation is "look at this and judge", and what has to be judged is sometimes source. `config-docs` carries the migration ledgers and the two modules holding the four validators that narrow a configuration value domain: a narrowing expressed in a validator is invisible to the fingerprint projection the coverage gate reads, so no derived check can ever demand the ledger entry it owes, and the review list is the only place that obligation can land. The bar is the same as for a doc — the target must be something a person reads and judges, never something a command regenerates.

## How it works

Three pieces:

- **`drift.toml`** (repo root, human-authored) declares the contracts: `triggers` (globs over tracked files), optional `exclude`, `review` targets, and optional `verify_commands`.
- **`.drift/acks/<contract-id>.toml`** (tool-written, committed) records the last fulfilled review: a content digest, the reviewer, a timestamp, a rationale, and the per-file trigger snapshot.
- **`pipelex-dev drift plan|check|ack`** computes obligations, checks them, and records acks. Make wrappers: `make drift-plan`, `make drift-check` (in the `make agent-check` and `make check` aggregates; in CI it currently runs as an **advisory** job that is visible on the PR but does not block merges — it will be promoted to a required check), `make drift-ack CONTRACT=… RATIONALE="…"`.

The validity rule is a single equality, with no base ref, no git diff, and no timestamps:

> A contract is **fulfilled** iff the stored ack digest equals the digest recomputed from the current tree. Otherwise it is **open**.

The digest covers both the contract's own definition and the `(path, blob OID)` pairs of every tracked file matching its triggers — so editing a trigger file, adding or deleting a matched file, *or editing the contract itself* all open the contract. A brand-new contract has no ack, so it is open until its targets are reviewed once and acked: adoption is explicit, contract by contract.

## Where the gate acts

One view of every surface the contract system touches, from the working tree to the merge:

| Surface | What happens there |
|---|---|
| **Make targets** | `make drift-check` (alias `dc`) is the pass/fail gate; `make drift-plan` (`dp`) is the read-only diagnosis; `make drift-ack CONTRACT=… RATIONALE="…"` (`da`, optional `BY=` for agents) records the review. All three wrap `pipelex-dev drift`. |
| **Quality checks** | `drift-check` runs inside the `make agent-check` and `make check` aggregates, alongside the other repo gates — a local check cannot pass with an open contract or a rotten manifest, so an open contract surfaces before CI. Mind the index: the digest reads staged content, so unstaged trigger edits are invisible to the gate until `git add`. |
| **Commits** | The digest is computed from the **git index**, and `drift ack` stages the ack file it writes — so the ack, the code change, and any doc fix land in the same commit, reviewed as one diff. |
| **Branches / merges** | After a merge, `drift check` recomputes the digest over the merged tree. An ack that was valid on either side but does not cover the merged trigger content fails the check until the merged state is reviewed and re-acked (see [Merges](#merges)). |
| **PRs / CI** | The `lint-drift` CI job runs `make drift-check` on every PR — currently advisory (visible, not merge-blocking; promotion to a required check is planned). The committed ack file appears in the PR diff, so the reviewer sees the rationale next to the change it covers. |

The gate acts on *content*, never on *time*: there is no base ref, no diff against a branch, no timestamp freshness — only the digest equality below.

## The ack workflow

When `make drift-check` fails (locally or in CI), run:

```bash
make drift-plan
```

It prints one Markdown packet per open contract: the description, exactly which trigger files were added/removed/modified since the last ack, the review targets, the verify commands, and the previous reviewer's rationale. To fulfill a contract:

1. **Review the targets against the trigger changes.** Actually read them. Update whatever is stale. "Nothing to update" is a legitimate outcome — say so in the rationale. Two traps worth naming, because searching the target for what changed walks past both: a claim that quantifies (*every*, *only*, *the sole exception*, a count) rots by **omission**, so the symbol that falsified it is absent from the sentence and has to be found by re-deriving the set from the code; and a claim *about* another artifact — a test, a module — is verified against what that artifact does, never against its docstring or a sibling doc, which drift from the same edit that missed them.
2. **Stage the trigger files:** `git add` them (staging is enough; you don't need to commit first, and other unstaged changes elsewhere are fine). **The digest is computed from the git index, not the working tree** — an unstaged edit or an untracked file is invisible to the ack, and `drift ack` warns when it sees one that matches the triggers. For a contract with `verify_commands` that warning escalates to a hard error: the verify commands run on the working tree, so a matching unstaged edit or untracked file means they certify content the digest does not cover. This coverage check runs both **before** the verify commands (so an already-dirty tree fails fast) and **after** them (so a trigger the verify commands themselves format or generate is caught too, not silently left out of the digest).
3. **Record the ack:**

    ```bash
    make drift-ack CONTRACT=config-docs RATIONALE="Documented the new activity_queues setting; other config pages unaffected."
    ```

    This first runs the contract's `verify_commands` (each one `shlex`-split and run without a shell, from the repo root; the first failure aborts the ack), then recomputes the digest from the index, writes the ack file, and stages it — the ack lands in the same index the check reads, so the local gate and the commit you are building agree. If staging the written ack fails (e.g. a locked git index), the ack file is removed rather than left unstaged, so a later `drift check` reports a missing ack instead of a false green.

4. **Commit the ack file together with the change it covers** (it is already staged). The ack surfaces in the PR diff, so the reviewer sees the rationale next to the change — that is the audit trail.

`reviewed_by` defaults from `git config user.name`; agents pass `BY=<identity>` (e.g. a model name or session URL). The rationale is required and is the on-the-record review decision — write an honest sentence, not "docs fine".

## Why there is no bypass

`drift ack` has no `--skip-verify`, and `drift check` has no override label. Every escape hatch here is a rubber-stamp invitation, and the legitimate escape already exists: acking with a rationale that says "no doc change needed" is cheap, honest, and auditable. If a contract opens so often that acking feels like ceremony, the contract is mis-scoped — narrow its triggers or mechanize it into a derived check; don't add a bypass.

## Merges

Two branches that each re-acked the same contract can produce a literal merge conflict in its ack file — but don't rely on that: a line-wise auto-merge can just as well splice the two acks into one that neither branch reviewed. The guarantee to rely on is different: **after the merge, `drift check` recomputes the digest over the merged tree**, and a spliced or stale ack simply fails the check, because the merged trigger content was never reviewed as a whole. Resolution is the same either way: finish the merge, review, then re-ack on the merged tree.

## Manifest hygiene

`drift check` hard-fails on manifest rot, not just open contracts: a trigger glob or review target matching zero tracked files, triggers fully shadowed by excludes, duplicate or malformed contract ids, an ack file with no matching contract, or an ack whose `contract` field disagrees with its filename. A rename that leaves a glob dead is caught on the same PR that should fix it — edit `drift.toml` first, then re-ack.

Keep the manifest small. Contracts are added one at a time, where staleness has actually hurt; growth should follow pain, not tooling enthusiasm.
