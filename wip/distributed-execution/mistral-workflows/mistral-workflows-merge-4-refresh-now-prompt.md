# Prompt — refresh `feature/Mistral-workflows-merge-4` from `dev` (use now)

Paste the block below into a fresh Claude Code session in `/Users/lchoquel/repos/Pipelex/_workflows`.

---

We keep `feature/Mistral-workflows-merge-4` alive as a long-lived branch = **`dev` + a held-back `mistralai` 1.x→2.x SDK bump** (held because `instructor` has no PyPI release that supports mistralai 2.x — blocked on instructor PR #2298). The full rationale is in `wip/mistral-workflows-merge-readiness.md`; read its TL;DR before touching dependencies.

I want to bring `feature/Mistral-workflows-merge-4` up to date with the latest `dev`. Please:

1. `git fetch origin`, then check out `feature/Mistral-workflows-merge-4` (confirm the working tree is clean first).
2. Merge `origin/dev` into it.

**What to expect — heads up:**

- The merge conflicts in **`CHANGELOG.md` only**. It's the routine "both sides added a `[Unreleased]` entry" conflict — resolve by keeping both sets of bullets (union), no content is lost. Nothing else should conflict.
- **Do NOT merge `feature/Runtime-bridge-extraction` into this branch.** That branch's tip pins `mistralai 1.12.0` in the lockfile, which would conflict with — and risk silently reverting — this branch's whole reason to exist (the mistralai 2.4.4 bump). `dev` is the only correct merge source. (The runtime-bridge work isn't on `dev` yet anyway, and this branch already carries its own copy.)
- **The mistral SDK bump must survive untouched.** After resolving, verify the held-back dependency state is still intact:
  - `pyproject.toml` still has `mistralai>=2.4.4` and the `[tool.uv.sources] instructor = { git = "https://github.com/Ian321/instructor.git", rev = "…" }` fork pin.
  - `uv.lock` still resolves `mistralai` 2.x (not 1.12.x) and `instructor` from the git rev.
  - `pipelex/plugins/mistral/*.py` keep the `mistralai.client.*` 2.x import paths.
  - `dev` brings no mistral dependency changes, so none of the above should have moved — but check, because this is the one thing we must not lose.

3. Run `make agent-check` and `make agent-test`; both must be green before you finish.
4. Do **not** push or open a PR — this is just keeping the branch fresh. Leave it on the merged commit and summarize what came in from `dev` (e.g. v0.31.0 release, #960, #962, #963).

If anything other than `CHANGELOG.md` conflicts, stop and show me — that would mean the topology changed (e.g. the bridge already landed on `dev`), and the right move is then the rebuild path in `wip/mistral-workflows-merge-4-rebuild-after-bridge-lands-prompt.md`, not a plain merge.
