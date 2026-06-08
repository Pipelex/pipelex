# Mistral Workflows merge — readiness & plan

Sub-track of [distributed-execution](../README.md): bringing the `pipelex-mistralai-workflows` plugin (Mistral's native Workflows as a Pipelex execution backend) onto current `dev`. This is the MISTRAL_NATIVE execution mode's home outside the core runtime.

## Docs

- [mistral-workflows-merge-readiness.md](mistral-workflows-merge-readiness.md) — **the hub.** Cold-start assessment of whether `feature/Mistral-workflows-merge-4` is safe to PR into `dev`. Verdict: the `runtime_bridge` extraction is clean/additive/green and safe to land; the blocker is a `mistralai` 1.x→2.x bump that drags in a temporary `instructor` git-fork pin on a core dep (blocked on instructor PR #2298). Recommends splitting — land the bridge, hold the SDK bump.
- [mistral-workflows-plugin-extract.md](mistral-workflows-plugin-extract.md) — design: extracting the plugin surface.
- [mistral-workflows-sub-module.md](mistral-workflows-sub-module.md) — design: the sub-module layout option.
- [mistral-workflows-merge-4-refresh-now-prompt.md](mistral-workflows-merge-4-refresh-now-prompt.md) — ready-to-paste prompt to keep `merge-4` alive while held: merge `dev` in now (only `CHANGELOG.md` conflicts; the mistral bump must survive).
- [mistral-workflows-merge-4-rebuild-after-bridge-lands-prompt.md](mistral-workflows-merge-4-rebuild-after-bridge-lands-prompt.md) — ready-to-paste prompt for after the bridge squash-merges to `dev`: rebuild the branch off `dev` and re-apply only the mistral delta, to dodge the squash-merge tangle.
- [docs-held-back-from-live-site.md](docs-held-back-from-live-site.md) — **re-publish checklist.** The Mistral Workflows user docs ship in the repo but are excluded from the published docs site (so it doesn't advertise the unreleased `pipelex-mistralai-workflows` package). What's held back and how to restore it when the package launches — claim the PyPI name first.

Pairs with [bridge-changes-sibling-repo-reconciliation.md](../bridge-changes-sibling-repo-reconciliation.md) in the parent track, which tracks what the downstream `pipelex-mistralai-workflows` repo needs reconciled after the `_bridge` surface changes.
