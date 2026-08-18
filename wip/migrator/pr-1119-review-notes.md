# PR #1119 review follow-ups — the one finding that was deferred rather than fixed

The v0.46.1 release PR drew three review-bot threads. Two were false positives answered on the spot, and one is deferred here: it names a real imprecision in the applier, but the state it describes cannot be produced by any migration operation today, and the patch the bot suggested would introduce a different wrong answer in its place. Deciding whether to harden the predicate anyway is a judgment call, not something a review pass should settle on its own, so the thread was left open and the reasoning written down here.

## The claim

`cubic` on `pipelex/pipeline/fixes/applier.py`, at `_at_document_start`:

> When an insertion has no trivia immediately before it but a banner after it, this returns `True` solely because the run is empty. `_settle_inserted` can then move the following section's banner above the newly inserted item instead of leaving it with that section; only a non-empty run can establish document-start status.

with the suggested one-liner `return bool(run.positions) and _is_first_entry(container=run.container, index=run.positions[0])`.

## The predicate really is imprecise

`_at_document_start` answers a question about the *run*, but every caller is asking about the *insertion point*. An empty run carries no position, so the function falls back to `not run.positions` — which is right when the insertion sits at index 0 and wrong when it sits anywhere else. The docstring ("whether the run is the first thing in the file") papers over the gap rather than closing it.

The imprecision can only ever surface in one place. At the two `_introduction_of_slot` call sites, and in `_settle_inserted`'s `else` arm, an empty run reaches `_introduction`, which finds no `Comment`, returns at `last_comment is None`, and never looks at the flag. Only `_settle_inserted`'s `if after.positions` arm can consume it, because that arm computes the flag from `before` and then applies it to a *combined* run whose contents come entirely from `after`.

## Why it is unreachable

Instrumented `_settle_inserted` over roughly 1,800 synthetic document/operation combinations (root and nested `set_key`, `ensure_table`, `move_key` in both directions, `delete_key`, `delete_table`, over documents varying the preamble, the banner shape, the blank lines and the tail) and over all 184 real ledger replays — the four shipped ledgers against every golden, kit config and packaged template.

- The flagged state (empty `before` run, root container, non-empty `after` run) is reached 102 times.
- In **every** one of them the `after` run is pure `Whitespace`. Not one contains a `Comment`, so `_introduction` short-circuits and the flag is never read.
- Output is byte-identical with and without the suggested patch across the whole corpus — zero differing cases.

The structural reason: tomlkit places a root-level insertion *after* any comment run that precedes the first table. Case A of the probe — `key_a = 1`, a banner, a blank line, `[b]` — puts the new key at body index 2, between the `Comment` and the `Whitespace`, so `before` comes back holding the comment rather than empty. For a comment to sit in the `after` run with nothing in the `before` run, an insertion would have to land *between* a value and the comment below it, which no placement path does.

## Why the suggested patch is not the fix

Forcing the state by hand (parsing a document with the key already in place and calling `_settle_inserted` on it) reproduces exactly what `cubic` described — and also shows the trap. The same patch flips the *genuine* document-start case:

| input | current | with the patch |
|---|---|---|
| `new_key = 2` / `# My pipelex config` / blank / `[b]` | preamble stays on top, above `new_key` | `new_key` stays on top, preamble pushed below it |

That first column is the documented preamble rule — "a hand-written config that starts `# My pipelex config` and then a section keeps its header line at the top". The `not run.positions` disjunct is what implements it when the insertion lands at index 0. Replacing it with `bool(run.positions)` trades one unreachable wrong answer for a different unreachable wrong answer, and picks the one that contradicts the stated rule.

## What a real fix would look like, and the open question

The honest repair is not to the run, it is to the signature: decide document-start from the insertion index (`run.positions[0]` when the run has one, `slot.first` when it does not) rather than from the run alone. That means changing `_at_document_start`'s parameters and both other call sites, and pinning it with a test for a state no operation can currently reach.

**Open for a human:** is that worth doing now, purely as hardening? The argument for is that the placement this relies on belongs to tomlkit, not to us, so a library upgrade could make the region live without anything in this repo changing. The argument against is that it is churn plus a test asserting an impossible state, for a defect no user can hit. Left open deliberately; the thread on PR #1119 is still unresolved so the question does not disappear.
