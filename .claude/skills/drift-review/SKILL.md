---
name: drift-review
description: >
  Resolve open drift contracts — the review obligations between code and docs
  declared in drift.toml. Use whenever `make drift-check` (or the `make
  agent-check` / `make check` aggregates, or the CI lint-drift job) fails with
  open contracts, when the user
  says "drift check failed", "resolve the drift contract", "ack the drift",
  "run drift plan", or after any change that touches a file a contract in
  drift.toml names as a trigger. Performs the review for real and records an
  honest ack whose rationale opens with the review's verdict.
---

# Drift Review

Resolve open drift contracts: review the declared targets against what actually changed, fix staleness, record the ack with its verdict. Full system reference: `docs/contribute/drift-contracts.md`. The manifest is `drift.toml` at the repo root.

A contract is "open" when tracked files matching its triggers changed (in the git index) since the last recorded review — or the contract definition itself changed, or it never had an ack. The tool proves *that* a review happened; this skill's job is to make the review *genuine*. There is deliberately no bypass anywhere in the system — the legitimate escape is an honest "nothing to update" rationale, which is cheap and auditable.

## Workflow

### 1. See what's open

```bash
make drift-plan            # all open contracts
make drift-plan CONTRACT=<id>   # one contract's full packet
```

Each packet gives you: the description, exactly which trigger files were added/removed/modified since the last ack, the review targets, the verify commands, the previous ack's rationale, and the exact ack command to run.

### 2. Review — this is the point, not a formality

Work from the trigger diff to the review targets:

- For each added/modified/removed trigger file, identify what a reader of the review targets could observe changing: new, renamed, or removed options, settings, defaults, commands, behaviors. Use `git diff` on the trigger files; the previous ack's rationale tells you what the last review already covered, so focus on what changed since.
- Grep the review targets for the changed names, settings, and symbols — then read the surrounding prose. A mention can be present but stale (wrong default, wrong behavior, incomplete), not just missing.
- **Grep finds wrong mentions; it cannot find missing ones.** A claim that quantifies — *every*, *all*, *only*, *the sole exception*, *none*, or any count — is a claim about a **set**, and it rots by omission: the symbol that falsified it appears nowhere in the sentence that is now false, so searching the target for what changed will never surface it. Read the targets for their quantified claims and re-derive each set from the code. (Same root as the no-hardcoded-counts rule — "the three helpers" and "the sole exception" go stale identically.)
- **Verify each claim against the artifact it is about, never against another document.** A claim about a test is checked by reading what the test *executes* — its calls, its parametrize lists — not its docstring; a claim about a module, by enumerating the module. A docstring, a sibling doc, or the previous ack is not evidence: prose drifts from the same edit that missed it, so two documents agreeing is agreement, not verification.
- Fix what's stale, following the repo's doc rules: docs describe current reality, no hardcoded counts, MkDocs conventions (blank line before lists). When the fix is to a quantified claim, prefer converting the construct over correcting the value — name the class ("the deck-reading helpers") rather than restating a count that will rot again.
- "Nothing to update" is a legitimate verdict — but only after you actually opened and read the review targets. If you didn't open them, you haven't reviewed.

### 3. Stage, then ack

The digest is computed from the **git index**, not the working tree: `git add` the trigger files (and any doc fixes you made). Staging is enough — no commit needed first, and unrelated unstaged changes elsewhere are fine. Take `drift ack`'s warnings about untracked or unstaged-modified matched files seriously: an unstaged edit is invisible to the ack. For a contract with verify commands, a matched unstaged or untracked file is a hard error (the verify run would certify content the digest does not cover) — stage the files, then re-run.

```bash
make drift-ack CONTRACT=<id> RATIONALE="<verdict>: <honest sentence>" BY="<your identity>"
```

As an agent, always pass `BY` with your **own actual identity** — the model you are actually running as, in the form `BY="Claude (<your model name>)"`. Do not copy a model name from an example or from a previous ack; the reviewer field is audit data and must name who really did the review. Never ack under the human's `git config user.name`. The contract's verify commands run first (no shell, fail-fast); a failure aborts the ack. Fix what the verifier caught — do not look for a bypass; none exists, by design.

**The rationale is the on-the-record review decision.** It must say what was reviewed and what the verdict was:

- Bad: `"docs fine"`, `"reviewed"`, `"re-ack after refactor"`
- Bad: `"the page's claim still matches the test's stated exception"` — that is two documents agreeing. Name what you re-derived from the code, so a weak method is visible at write time rather than in the next merge.
- Good: `"real-catch: Documented the new activity_queues setting in general-config.md; other config pages unaffected."`
- Good: `"clean-pass: CLI change is internal plumbing (renamed a private helper); no user-visible surface moved; cli docs and agent-CLI contract doc verified unchanged."`

### 4. Verify and commit

`make drift-check` must pass. `drift ack` stages the ack file it writes; commit the ack file(s) under `.drift/acks/` **together with the change they cover** — the rationale lands in the PR diff next to the change, which is the audit trail. Never hand-edit files under `.drift/acks/`.

## Mandatory: open the rationale with the verdict

The one question only usage can answer about a contract is whether its ack friction is proportionate to the staleness it catches, so every rationale starts with one verdict, followed by a colon — `drift ack` refuses a rationale that does not:

- **real-catch** — the review found actual staleness, and this change fixes it;
- **clean-pass** — genuinely reviewed, nothing was stale;
- **friction** — the contract opened on changes that could not have affected its targets.

The ack file is committed with the change it covers, so `git log -p .drift/acks/` is the evidence from which a contract's keep, narrow, mechanize or drop decision is made. Write nothing anywhere else: there is no log file.

A `clean-pass` is a fine outcome; a *pattern* of clean-passes on the same contract is signal. When the verdict is `friction`, say in the rationale which trigger narrowing would have prevented the opening, then file that narrowing in the workspace ledger, owned by `pipelex` (`ledger new --owner pipelex --type task --title "…" --gist "…"`), or note it on the open item that already proposes it. Where there is no ledger, put the proposal in your report to the user.

## Failure modes

- **`drift check` fails on manifest rot** (dead trigger glob, zero-match review target, orphan ack, id/filename mismatch): the manifest itself needs fixing — edit `drift.toml` first (typically a rename left a glob dead), then re-review and re-ack. Editing a contract reopens it; that is expected.
- **A verify command fails:** it caught something real — fix it; the ack stays blocked until the verifier passes.
- **A contract keeps reopening on edits that cannot affect its targets:** keep recording `friction` in the rationale and file the trigger narrowing as above. Do not grow the manifest (no new contracts) without the user's explicit say-so — growth follows pain, not tooling enthusiasm.
