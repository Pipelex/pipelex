# Mistral Workflows user docs — held back from the live site (re-publish on launch)

**Status: HELD BACK on the bridge branch.** The Mistral Workflows user docs are written and live in the repo, but the bridge PR keeps them **out of the published docs site** (docs.pipelex.com) so the site doesn't advertise the `pipelex-mistralai-workflows` package before it exists on PyPI. Re-publish them when the package launches.

## Why

The PyPI distribution name `pipelex-mistralai-workflows` is not registered yet. Printing `pip install pipelex-mistralai-workflows` on a public page invites someone to squat the name. The package also isn't published, so any install instruction would just fail. So the bridge PR holds the user-facing docs back rather than shipping docs for an unreleased package.

The **code** (the bridge entry point, primitives, execution modes) ships in this PR regardless — only the user-facing Mistral Workflows *docs* are held back.

## What is held back

The six pages under `docs/distributed-execution/mistral-workflows/` (`index`, `installation`, `your-first-pipelex-workflow`, `execution-modes`, `streaming`, `choosing-a-backend`). They still exist in the repo; they are excluded from the MkDocs build via `exclude_docs:` in `mkdocs.yml`, so they are neither served nor in the nav. The parent pages were softened to "coming soon" and de-linked from them (otherwise the `mkdocs build --strict` in `doc-check.yml` fails on links to excluded pages).

## Prerequisite before re-publishing

1. **Claim the name on PyPI first** — register `pipelex-mistralai-workflows` (a `0.0.0` placeholder release is enough) so re-publishing the docs no longer advertises an unclaimed name. This is the real squatting fix; the doc hold is only defense-in-depth (the name already appears across the public repo).
2. The package must actually publish, so `pip install pipelex-mistralai-workflows` resolves.

## Re-publish checklist (reverse of the hold)

In `pipelex` (wherever the bridge has landed — `dev`, then merged into `_workflows`):

- **`mkdocs.yml`** — delete the `exclude_docs:` block for `distributed-execution/mistral-workflows/`, and restore the `Mistral Workflows:` nav subsection (Overview / Installation & Preview Status / Your First Pipelex Workflow / Execution Modes / Streaming Progress / Choosing a Backend) under `Distributed Execution`.
- **`docs/distributed-execution/index.md`** — restore the two-backend overview (Temporal + Mistral Workflows, with the links and the "what's shared" framing) instead of the Temporal-only + "coming soon" version.
- **`docs/features/distributed-execution.md`** — restore the second backend bullet (link + name) and the "Choosing a Backend" link; restore the Mistral mention in the "Get started" line.
- **`docs/distributed-execution/temporal/index.md`** — restore the "one of two backends … see Pipelex on Mistral Workflows / Choosing a Backend" cross-links.
- **`docs/under-the-hood/pipe-routing-and-execution.md`** — restore the two-host-runtime framing and the `See [Execution Modes]` link.
- **`docs/reliability/durable-execution.md`** — restore the two-backend wording and the Mistral / Choosing-a-Backend links.
- **`README.md`** — restore the real install instruction (`pip install pipelex-mistralai-workflows`) in the "Mistral Workflows orchestration" note, replacing the "coming soon / install details follow" placeholder.
- **`CHANGELOG.md`** — restore the install + import-path guidance (`pip install pipelex-mistralai-workflows`, import from `pipelex_mistralai_workflows.*`) in the "Mistral Workflows integration extracted" entry.

After restoring, run `mkdocs build --strict` (matches `doc-check.yml`) and confirm the Mistral pages build and the nav renders.

## Where the hold was done (to diff/revert against)

On the bridge branch (`feature/Runtime-bridge-extraction`, PR #969):

- de-advertising README/CHANGELOG (removed the `pip install` lines): commit `e8dfa0e2`.
- unpublishing the docs (mkdocs `exclude_docs` + nav removal + parent-page softening): the commit that adds this file.

`git show <sha>` on those two commits gives the exact reverse diff for the checklist above.
