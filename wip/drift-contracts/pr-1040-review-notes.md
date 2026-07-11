# PR #1040 review notes — deferred drift-tooling findings

Two codex findings on `pipelex/cli/dev_cli/commands/drift/drift_cmd.py` from the PR #1040 review pass. Both describe real code behavior (verified against the code), but neither is worth hardening now: the drift tool is an internal dev CLI, CI backstops the first, and the second is a documented design choice with a narrow failure mode. Captured here so the candidate fixes aren't lost.

## A1 — `drift ack` does not stage the ack file, so local `drift check` can false-green

Reporter: codex (P2). Thread: <https://github.com/Pipelex/pipelex/pull/1040#discussion_r3564484373>

`drift check` hashes trigger files from the **git index** but loads ack files from the **working tree** (`load_all_acks` globs `.drift/acks/*.toml` on disk). `drift ack` writes the ack file without staging it. So right after an ack, the local gate passes even though the ack blob is not in the commit being built — if the developer forgets to `git add` the ack, the false green only flips red in CI (fresh checkout: `MISSING_ACK` / `DIGEST_MISMATCH`).

**Why deferred:** the false green is purely local; CI deterministically catches anything that lands. The doc already instructs committing the ack together with the change. Dev-loop papercut, not a correctness hole.

**Recorded candidate fix (clean, low-risk):** have `drift ack` auto-stage the ack file it writes (`git add .drift/acks/<id>.toml` after `save_ack`). The ack is a tool-written artifact, never hand-edited, so auto-staging is safe; it makes the local gate honest (the ack lands in the same index the check reads) and removes the forgot-to-add footgun. Note: the alternative "read acks from the index" would report `MISSING_ACK` immediately after a successful ack unless combined with auto-staging, so auto-staging is the load-bearing part. Test approach: temp-git-repo test asserting the ack path appears in `git diff --cached --name-only` after `drift ack`.

## A2 — verify commands run against the working tree while the ack digest covers staged blobs

Reporter: codex (P2). Thread: <https://github.com/Pipelex/pipelex/pull/1040#discussion_r3564484375>

In `drift_ack_cmd`, verify commands run against the working tree, then the digest is computed from staged blob OIDs, then `_warn_uncovered_working_tree` warns, then the ack is written unconditionally. If a trigger file has staged content plus extra unstaged edits, the ack certifies staged content that the verify commands never ran on exactly.

**Why deferred:** the warn-not-fail behavior is deliberate and documented (`docs/contribute/drift-contracts.md` — the digest is index-based by design, and `drift ack` warns on matching unstaged/untracked files). The failure mode is narrow: stage a trigger, edit it further without re-staging, ack, *and* have the staged-vs-tree delta flip a verify result. Codex's proposed blanket fail-on-any-unstaged-trigger contradicts the documented index-based philosophy and would add friction for the many contracts with no `verify_commands` at all.

**Recorded candidate fix (if ever needed):** escalate warn→fail only when the contract has `verify_commands` AND a matching trigger file is unstaged/untracked — that is the one case where the verify guarantee is meaningfully weakened. Test approach: temp-repo test asserting `drift ack` raises `DriftAckError` for a verify-command contract with a dirty matching trigger, while still only warning for a no-verify contract.
