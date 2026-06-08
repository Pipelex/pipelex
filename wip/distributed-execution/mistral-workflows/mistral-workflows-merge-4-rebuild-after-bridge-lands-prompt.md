# Prompt — rebuild `feature/Mistral-workflows-merge-4` after the runtime-bridge PR squash-merges to `dev` (use later)

Paste the block below into a fresh Claude Code session in `/Users/lchoquel/repos/Pipelex/_workflows`. **Only use this once `feature/Runtime-bridge-extraction` (PR #959) has landed on `dev`.** Until then, keep the branch fresh with `wip/mistral-workflows-merge-4-refresh-now-prompt.md` instead.

---

Background: `feature/Mistral-workflows-merge-4` is a long-lived branch = **`dev` + a held-back `mistralai` 1.x→2.x SDK bump** (held on `instructor` PR #2298; see `wip/mistral-workflows-merge-readiness.md`). It carries its **own, original, unsquashed** copy of the runtime-bridge commits (`71de6fb1`, `1a0f5dfa`, the `runtime_bridge` extraction, etc.).

The runtime-bridge work has now squash-merged into `dev` as a **single** commit — so `dev` and `merge-4` both contain the bridge, but as **different SHAs with diverged content** (dev has the review-followed-up version; merge-4 has the older one). A plain `git merge dev` would now conflict hard across every `pipelex/runtime_bridge/**` file — the classic "long-lived branch outlives the squash-merge of its own content" tangle. **Do not try to merge through that.**

Instead, **rebuild the branch fresh off `dev` and re-apply only the mistral delta.** The branch's *unique* content is tiny — the mistral provider files plus the dependency bump; everything else (including the now-canonical, review-followed-up `runtime_bridge`) comes for free from `dev`.

Please do this:

1. `git fetch origin`. Confirm the bridge actually landed on `dev`: `git ls-tree origin/dev pipelex/runtime_bridge` should be non-empty. If it's empty, **stop** — the bridge hasn't landed; use the refresh prompt instead.
2. Preserve the old branch: rename `feature/Mistral-workflows-merge-4` → `archive/Mistral-workflows-merge-4-presquash` (or just leave it and branch anew). Don't delete it until the rebuild is verified green.
3. Create the new branch off `origin/dev` (call it `feature/Mistral-workflows-merge-5`, or reset `-4` to `origin/dev` if you prefer to keep the name).
4. Re-apply **only the mistral delta**. The authoritative file list is the "Hold on the branch" section of `wip/mistral-workflows-merge-readiness.md` — read it, don't trust the list below blindly. As of writing it is:
   - **source:** `pipelex/plugins/mistral/{mistral_config,mistral_extract_worker,mistral_factory,mistral_llm_worker,mistral_llms}.py` (includes the `mistralai.client.*` 2.x import reorg and the `message is None` retry guard in `mistral_llm_worker.py`).
   - **tests:** `tests/unit/pipelex/plugins/{test_plugin_pipelex_storage_images,test_transport_retry_wiring}.py` and `tests/unit/pipelex/plugins/mistral/{test_mistral_worker_error_handling,test_extract_mistral_metadata,test_mistral_llm_worker_object_error_handling,test_mistral_extract_worker_semantic,test_mistral_reasoning}.py`.
   - Bring these over with `git checkout <old-merge-4-branch> -- <files…>`. Reconcile by hand if `dev` changed any of them in the meantime.
5. Re-apply the **dependency bump** to `pyproject.toml`: `mistralai>=2.4.4` and the `[tool.uv.sources] instructor = { git = "https://github.com/Ian321/instructor.git", rev = "…" }` fork pin (keep the `# Temporary: …` comment referencing instructor #2298). Then **regenerate the lockfile fresh** with `uv lock` — do **not** copy the old `uv.lock`; let it resolve against current `dev`.
6. Run `make agent-check` and `make agent-test`; both must be green.
7. Confirm the held-back state is correct: `uv.lock` resolves `mistralai` 2.x + `instructor` from the git rev, and the new branch's diff vs `dev` is *just* the mistral provider files + the two dependency files (no stale bridge churn). That small, crisp diff is exactly what becomes the PR once `instructor` ships mistralai-2.x support on PyPI.
8. Do not push or open a PR unless I ask — but do report the final diff-vs-`dev` summary so I can sanity-check the delta.

After this, update `wip/mistral-workflows-merge-readiness.md` and `wip/README.md` to reflect the new branch name and that the bridge is now upstream on `dev`.
