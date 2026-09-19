---
status: active
item: L-260917-87199b
---

# Deferred review findings — the pinned-natives version constant

Two findings from the round-2 `/rev` pass on `fix/Dead-natives-version-constant` (profile 2, bar `defects`) that were real but not defects that matter at that bar. Both are unverified: no verifier was paid for them, because the bar would have deferred them whatever a verifier said.

## The page-version reader matches "pinned at MTHDS" too loosely (unverified)

`tests/unit/pipelex/core/concepts/test_pinned_natives_vs_standard.py`, in `read_spec_pinned_version`.

The regex is `[Pp]inned at MTHDS\s+`?(\d+\.\d+\.\d+)`?`, collected over the whole page, with every match required to agree. Today the standard's `native-concepts.md` has exactly two matches and both say `2.0.0`, so the reader is correct and the unanimity check is what makes a half-done re-pinning on the page a failure rather than a coin toss.

The claim is that `[Pp]inned` also matches inside `re-pinned`, `un-pinned` and `previously pinned`, so a page that one day writes "previously pinned at MTHDS `2.0.0`" beside a new "Pinned at MTHDS `3.0.0`" would fail the unanimity assertion with a message saying the page states more than one pinned version — a red that is neither a pipelex bug nor the drift the assertion exists to diagnose. Because this module reads the sibling checkout deliberately unpinned, such a red can land on an unrelated pull request.

Nothing on the page has that shape today, so this is a robustness question about wordings the standard has not used. If it is ever worth narrowing, anchoring to the heading spelling alone — the `## The Pinned Set — Pinned at MTHDS <version>` line — is the change, and it trades the prose/heading cross-check away for it.

## The changelog entry narrates its own test coverage (unverified)

`CHANGELOG.md`, the `## [Unreleased]` entry for this constant.

`.claude/rules/changelog.md` asks an entry to say the change a consumer can see and to leave out test rewrites. The entry's second half describes the two readers the change adds. The counter-argument, and why it was left alone: "has no reader" is half of what the ledger item reported as the bug, so the readers are the fix rather than tests incidental to it. The entry is within the rule's one-to-three-sentence bound either way. Worth a second look when the release entry is cut, where a shorter form may read better beside its neighbours.
