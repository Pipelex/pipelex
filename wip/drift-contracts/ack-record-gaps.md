# Drift contracts — two gaps in the ack record

**Status: for ruling.** Two findings about `.drift/acks/*.toml` as a *data model*, both surfaced on 2026-07-29 while merging `dev` into `refactor/Hub-2` (merge commit `647f97881`). Neither is about whether a contract is worth keeping — that is the [phase-3 verdict](phase-3-verdict.md)'s question — so they are recorded here rather than inserted into a doc that is already awaiting rulings. Both want a decision before the verdict's Phase V1 manifest wave, because both get worse as the manifest grows.

Finding 1 is logged in the [dogfood log](dogfood-log.md) under its 2026-07-29 `cli-docs` entry. Finding 2 is not — it is a property of the registry, not of any one ack.

## Finding 1 — the ack registry has no merge semantics

### What happened

Merging `dev` into `refactor/Hub-2` conflicted on `.drift/acks/cli-docs.toml`. Both branches had acked the same contract; the file holds exactly one ack; the two sides carried different digests *and* different `trigger_files` blob maps. Resolving to either side would have left a file that looks like a valid ack and is not, because the merged trigger content is a third thing that equals neither parent's. The contract necessarily reopened, and `drift plan` presented the union of both branches' changes — the entire modularity sweep, 26 files under `pipelex/cli/**` — as unreviewed, despite three prior acks on that branch having already covered it.

### Why this is structural, not a bug in the merge

The digest is a claim about a **whole tree state**: `compute_contract_digest` hashes the contract definition plus the *complete* `trigger_files` map (every matched trigger's blob OID, not just the changed ones). A claim of that shape can only ever be true of one linear history. A merge produces a tree that is neither parent, so — outside a fast-forward, where the ack and the tree stay consistent by construction — **the merge invalidates both parents' acks by definition**. There is no resolution that preserves either.

Two distinct shapes, worth separating because only one of them is visible:

- **Both branches acked the same contract** → textual conflict in the ack file. Loud, and the resolver is forced to think. This is what happened here.
- **Only one branch acked, the other merely touched triggers** → git auto-merges the ack file cleanly, no conflict, and the contract silently reopens at the next `drift check`. Still fail-loud at check time, but the merge itself gives no signal.

The trap in the first shape is worth naming precisely: `git checkout --ours/--theirs` on an ack file produces a plausible-looking record whose `rationale` describes a review of *one branch's* changes while its digest is stale. `drift check` catches the stale digest, so this cannot ship silently — but a resolver who takes a side and moves on has written a misleading rationale into a permanent record, and only the digest saves them. **The safe resolution is to treat any conflicted ack file as garbage, complete the merge, then re-review and re-ack.** That is what this merge did.

### The cost

Any long-lived branch pays a contract's full review cost again at **every** merge from its base, for every contract whose triggers either side touched. With `N` contracts and `M` merges the branch pays up to `N × M` reviews, and the overwhelming majority re-present already-reviewed work. The verdict doc's Phase V1 raises `N` from 4 to 6 and repairs triggers to widen two of them, so this multiplies rather than staying flat.

### Why it still is not a defect

Reopening is the conservative answer and the right default. The merged state genuinely has not been reviewed *as a whole*, and the one thing that must never happen — a stale ack passing `drift check` — does not happen. The complaint is about proportionality, not correctness.

### It is the same problem the content-aware digest already solves

Measured on this merge, over the 26 changed triggers (`git diff dev HEAD`, filtering `from`/`import` lines):

| | files |
|---|---|
| import-line changes only | **19** |
| substantive changes | **7** |

The 7 substantive ones carry three distinct changes in total, all already reviewed on the branch: the `PipelexInterpreter` → `MthdsParser` rename, the matching `PipelexInterpreterError` → `MthdsParserError` rename (which also re-keys one `AGENT_ERROR_HINTS` entry), and `build_registrar` gaining `builtin_plugins` / `core_unconditional_plugin_names`.

So a digest that ignored diffs confined to `import` / `from` statements — the narrowing the `config-docs` entry of 2026-07-28 proposes on independent grounds, and which the `cli-docs` clean-pass entries have been building toward for seven consecutive openings — would have reduced this merge's reopening from 26 files to 7, and would have made the *merge* case nearly free without weakening the contract in any of its recorded real-catches. **The two proposals are the same lever.** That is the load-bearing point for the verdict: merge friction is not a separate problem needing separate machinery, it is the strongest single argument for a narrowing already on the table.

### Options

1. **Do nothing.** Accept re-review at every merge. Honest, and cheap while `N` is small and branches are short-lived; the modularity track shows neither assumption holds.
2. **Adopt the content-aware digest** (already proposed for other reasons). Does not eliminate merge reopenings — it makes the common refactor-sweep case collapse to near-nothing. **Recommended**, because it is one change buying two wins.
3. **Teach the ack a merge rule** — e.g. an ack could store the commit it was recorded at, and `drift check` could treat a contract as still-acked if every trigger's content at HEAD is reachable from an acked state on some parent. This is real work, it re-implements a chunk of merge-base reasoning, and it trades a loud correct answer for a subtle one. **Not recommended** on the clean-solid rule; revisit only if (2) lands and merge friction is still material.
4. **Document the resolution protocol** regardless of the above: a conflicted ack file is never resolved by picking a side. One paragraph in `docs/contribute/drift-contracts.md`. **Recommended and independent** — it costs nothing and closes the misleading-rationale trap.

- [ ] **DECISION M1 (Louis):** confirm option 2 is folded into the content-aware-digest ruling rather than tracked separately, and option 4 is written up.

## Finding 2 — `--by` silently overwrites a deliberate reviewer identity

### The evidence

`make drift-ack` writes the whole ack file, and `--by` defaults to `get_git_user_name`. So a re-ack by a different actor relabels the record with no prompt and no diff worth noticing. That is not hypothetical — it already happened to **every contract in the registry**:

| contract | 2026-07-27 | current |
|---|---|---|
| `cli-docs` | `Claude (Opus 5 1M context)` | `Louis Choquel` |
| `config-docs` | `Claude (Opus 5)` | `Louis Choquel` |
| `hub-layering-convention` | `Claude (Opus 5 1M context)` | `Louis Choquel` |
| `keyword-only-convention` | `Claude (Opus 5)` | `Louis Choquel` |

The three flips landed in `41341a227` (#1067) and the fourth in `cee4588b5` (#1069). The registry now reads as uniformly human-reviewed, and that uniformity is an artifact of the default, not a record of who reviewed anything.

### Why this is sharper than "a default that is sometimes wrong"

The dogfood log already predicted it. The fourth `hub-layering-convention` entry (2026-07-27) records deliberately *setting* agent attribution and closes: *"If the pilot keeps agents in the loop, `--by` should probably not default to the committer."* The prediction came true within a day — and the mechanism is worse than a bad default, because it **erases a value someone chose on purpose**. An ack is the pilot's primary evidence stream; `reviewed_by` is the field that says whether a human or an agent produced that evidence, which is precisely the question a pilot about review obligations needs to answer. A field that silently reverts cannot answer it.

Note the second-order effect: this is now the **third** instance of the pattern the log keeps recording — an ack's own edits containing an error that a later review catches (cf. the fourth and ninth `hub-layering-convention` entries). Here the error is in the *registry* rather than in a rationale or a comment, and nothing in the machinery re-reads it at all.

`reviewed_by` is **not** part of the digest (`compute_contract_digest` hashes only the contract definition and `trigger_files`), so it can be corrected by hand at any time without invalidating an ack. That makes the fix cheap and the regression cheap to undo.

### Options

1. **Drop the `get_git_user_name` default** — make `--by` required. Loud, one-line change, forces the question at every ack. Slightly annoying for the human case.
2. **Keep the default, add an agent-aware override** — e.g. `drift ack` reads an env var the agent harness sets, falling back to git user. Correct attribution with no ceremony for humans; needs the harness to actually set it. **Recommended.**
3. **Keep the default, make the skill always pass `--by`.** Cheapest — the `drift-review` skill is what agents actually invoke, so putting `--by` in the skill's ack step fixes the observed failure mode without touching the CLI. Weaker than (2): it fails open for any agent that acks without the skill. **Recommended as the immediate step** regardless of (1) or (2).

- [ ] **DECISION M2 (Louis):** pick an option, and decide whether to restore the four clobbered attributions. Restoring is a hand-edit of four `reviewed_by` lines and does not touch any digest — but the reviews behind `41341a227` / `cee4588b5` were, on my reading of that work, agent reviews, and re-attributing someone else's merged records is your call, not mine.

## What was changed, and what was not

In the merge commit `647f97881`:

- The `cli-docs` ack was re-recorded after an actual review (not a rubber-stamp — targets checked against the live CLI on both sides), with the dogfood-log entry Finding 1 comes from.
- `reviewed_by` on that ack was left at the `Louis Choquel` default, on the reasoning that the registry was uniform and consistency should not be broken unilaterally.

After it, while writing this doc:

- **That reasoning turned out to be wrong** — the uniformity *was* the regression in Finding 2, which only surfaced when the ack history was traced. `reviewed_by` on the `cli-docs` ack is now `Claude (Opus 5 1M context)`, matching what that same ack carried on 2026-07-27 and matching who actually performed the review. `drift check` still passes, confirming the field is outside the digest.
- The 2026-07-29 dogfood-log entry said *"23 of the 26 triggers changed by import line alone"*. The measured figure is **19**; the entry is corrected. The original number was asserted from a partial reading of the diff rather than counted, and a first attempt at counting it used a `pipelex/cli/**/*.py` pathspec that silently skips files sitting directly in `pipelex/cli/`. Recorded because this log's standard is that an ack's own output gets checked like anything else — and because the near-miss is a reminder that `**/` globs in a hand-written verification command are not the same set as the contract's own matcher.

Deliberately not done:

- No change to the other three acks' `reviewed_by` — see DECISION M2. Those are attributions on already-merged work, and re-labelling someone else's review record is not a call to make unilaterally.
- No change to `drift.toml`, the digest algorithm, or the ack model. Both findings are proposals for the verdict, not fixes to apply ahead of it.
