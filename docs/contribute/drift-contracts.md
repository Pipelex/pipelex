# Drift Contracts

Drift contracts turn the "keep docs in sync with code" policy from advisory prose into a deterministic, CI-gated obligation. A **drift contract** declares: *when these trigger files change, these review targets must be re-examined against the change, and the examination must be recorded.* The tool cannot judge whether a doc is still correct — that takes a human or an agent — but it can prove, deterministically, that someone looked at this exact content and said so on the record.

## The three synchronization tiers

Not every code↔doc relationship deserves a review contract. This repo distinguishes three tiers, and a drift contract is the right tool only for the last one:

| Tier | Mechanism | Judgment needed |
|---|---|---|
| **Derived** | Regenerate and diff: `check-config-sync`, `check-mthds-schema`, `check-gateway-models`, `generate-error-pages` | None — the output is a pure function of its sources |
| **Linkage** | Referential integrity of declared cross-references (the spec/conformance `check-spec-links` pair) | None — links either resolve or they don't |
| **Review** | Drift contracts: "this changed → that must be looked at, and the look recorded" | Yes — someone must judge whether the prose still holds |

The standing rule: **anything mechanizable becomes a derived check.** If a review contract keeps opening and the review is always the same mechanical comparison, delete the contract and write a derived check instead — it needs no judgment and can't be rubber-stamped. The best review contract is one you eventually mechanize out of existence. Corollary: generated artifacts (`docs/errors/`, `derived/`, gateway model docs) must never appear in a contract's `review` list — reviewing generator *output* is how you end up editing generated files.

## How it works

Three pieces:

- **`drift.toml`** (repo root, human-authored) declares the contracts: `triggers` (globs over tracked files), optional `exclude`, `review` targets, and optional `verify_commands`.
- **`.drift/acks/<contract-id>.toml`** (tool-written, committed) records the last fulfilled review: a content digest, the reviewer, a timestamp, a rationale, and the per-file trigger snapshot.
- **`pipelex-dev drift plan|check|ack`** computes obligations, gates CI, and records acks. Make wrappers: `make drift-plan`, `make drift-check` (in the `make check` aggregate and CI), `make drift-ack CONTRACT=… RATIONALE="…"`.

The validity rule is a single equality, with no base ref, no git diff, and no timestamps:

> A contract is **fulfilled** iff the stored ack digest equals the digest recomputed from the current tree. Otherwise it is **open**.

The digest covers both the contract's own definition and the `(path, blob OID)` pairs of every tracked file matching its triggers — so editing a trigger file, adding or deleting a matched file, *or editing the contract itself* all open the contract. A brand-new contract has no ack, so it is open until its targets are reviewed once and acked: adoption is explicit, contract by contract.

## The ack workflow

When `make drift-check` fails (locally or in CI), run:

```bash
make drift-plan
```

It prints one Markdown packet per open contract: the description, exactly which trigger files were added/removed/modified since the last ack, the review targets, the verify commands, and the previous reviewer's rationale. To fulfill a contract:

1. **Review the targets against the trigger changes.** Actually read them. Update whatever is stale. "Nothing to update" is a legitimate outcome — say so in the rationale.
2. **Stage the trigger files:** `git add` them (staging is enough; you don't need to commit first, and other unstaged changes elsewhere are fine). **The digest is computed from the git index, not the working tree** — an unstaged edit or an untracked file is invisible to the ack, and `drift ack` warns when it sees one that matches the triggers.
3. **Record the ack:**

    ```bash
    make drift-ack CONTRACT=config-docs RATIONALE="Documented the new activity_queues setting; other config pages unaffected."
    ```

    This first runs the contract's `verify_commands` (each one `shlex`-split and run without a shell, from the repo root; the first failure aborts the ack), then recomputes the digest from the index and writes the ack file.

4. **Commit the ack file together with the change it covers.** The ack surfaces in the PR diff, so the reviewer sees the rationale next to the change — that is the audit trail.

`reviewed_by` defaults from `git config user.name`; agents pass `BY=<identity>` (e.g. a model name or session URL). The rationale is required and is the on-the-record review decision — write an honest sentence, not "docs fine".

## Why there is no bypass

`drift ack` has no `--skip-verify`, and `drift check` has no override label. Every escape hatch here is a rubber-stamp invitation, and the legitimate escape already exists: acking with a rationale that says "no doc change needed" is cheap, honest, and auditable. If a contract opens so often that acking feels like ceremony, the contract is mis-scoped — narrow its triggers or mechanize it into a derived check; don't add a bypass.

## Merges

Two branches that each re-acked the same contract can produce a literal merge conflict in its ack file — but don't rely on that: a line-wise auto-merge can just as well splice the two acks into one that neither branch reviewed. The guarantee to rely on is different: **after the merge, `drift check` recomputes the digest over the merged tree**, and a spliced or stale ack simply fails the check, because the merged trigger content was never reviewed as a whole. Resolution is the same either way: finish the merge, review, then re-ack on the merged tree.

## Manifest hygiene

`drift check` hard-fails on manifest rot, not just open contracts: a trigger glob or review target matching zero tracked files, triggers fully shadowed by excludes, duplicate or malformed contract ids, an ack file with no matching contract, or an ack whose `contract` field disagrees with its filename. A rename that leaves a glob dead is caught on the same PR that should fix it — edit `drift.toml` first, then re-ack.

Keep the manifest small. Contracts are added one at a time, where staleness has actually hurt; growth should follow pain, not tooling enthusiasm.
