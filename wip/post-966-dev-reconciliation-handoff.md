# `_workflows` (merge-4) — post-#966 dev reconciliation handoff

**Trigger: execute this once PR #966 (`feature/Runtime-bridge-extraction`) has landed on `dev`.** Self-contained — a fresh session in this worktree can run it with no prior context. Written 2026-06-07.

## What you're holding

- **Worktree:** `/Users/lchoquel/repos/Pipelex/_workflows`, branch `feature/Mistral-workflows-merge-4` (PR #954 family).
- **Companion (read for the full rationale):** [`wip/mistral-workflows-merge-readiness.md`](mistral-workflows-merge-readiness.md) — the merge basis. It assessed merge-4 on 2026-06-03 and concluded "split: land the bridge now, hold the mistralai 2.x bump." That split already happened: **`feature/Runtime-bridge-extraction` (= PR #966) IS merge-4's `runtime_bridge` extraction, carved off `dev`.**

## The key realization

Once #966 is on `dev`, **merge-4's bridge work is redundant** — `dev` now carries the canonical, reconciled version of exactly the `runtime_bridge/` + Temporal-rewiring work that merge-4 pioneered, *plus* dev's later distributed-cost-reporting (#967) and `GraphContext→TraceContext` (#968) changes that merge-4 predates. merge-4 still has the **old** shape: `pipelex/graph/graph_context.py` (not `trace_context.py`), `runtime_bridge/primitives/graph_assembly.py` (deleted on dev), `act_assemble_graph` (became `act_assemble_tracing`), no `pipe_run/tracing_assembly.py`, `run_pipe_via_bridge(graph_context=...)`.

So merge-4's **only remaining unique value** is the **mistralai 2.x HOLD group** — the major SDK bump that is *independently blocked* on `instructor` PR #2298 shipping mistralai-2.x support to PyPI (see the readiness doc's "blocker" + "tracking issue" sections; that gate is unchanged by #966).

That reframes the work: **don't fight a big conflict-heavy merge to preserve merge-4's bridge commits — they're now dev's.** Reduce merge-4 to just the HOLD group, rebased on the post-#966 `dev`.

## Preconditions to check first

```bash
cd /Users/lchoquel/repos/Pipelex/_workflows
git fetch origin
# Confirm #966 is actually on dev (look for the reconciled bridge surface):
git ls-tree origin/dev pipelex/graph/ | grep -E 'graph_context|trace_context'   # expect trace_context.py, NOT graph_context.py
git ls-tree origin/dev pipelex/pipe_run/tracing_assembly.py                      # expect it to exist (dev #967)
git ls-tree origin/dev pipelex/runtime_bridge/primitives/ | grep graph_assembly  # expect EMPTY (deleted)
git ls-tree origin/dev pipelex/temporal/tprl_pipe/ | grep assemble               # expect act_assemble_tracing.py
```

If `trace_context.py` / `tracing_assembly.py` / `act_assemble_tracing.py` are present on `origin/dev` and `graph_assembly.py` is gone, #966 (and #967/#968) are in — proceed. If not, #966 hasn't fully landed; stop.

## Recommended path — Option (ii): retire merge-4, cut a minimal HOLD-group branch off the new `dev` (PREFERRED)

merge-4's bridge bulk is now in `dev`; what's left is the small, enumerated HOLD group. The readiness doc already proved this set is separable (it built #966 by the symmetric move — soft-reset off dev, revert the HOLD group). Do the mirror image: take `dev`, apply *only* the HOLD group.

The HOLD group (verbatim from the readiness doc's "Hold on the branch" list — re-confirm against the live tree, don't trust counts):

- `pyproject.toml`: `mistralai>=2.4.4` and the `[tool.uv.sources] instructor = { git = ... }` fork pin. (`temporalio==1.24.0` already landed via #966 — verify it's on dev, don't re-add.)
- The coupled `uv.lock` changes.
- Mistral provider **source** (the `mistralai.client.*` import reorg required by 2.x): `pipelex/plugins/mistral/{mistral_config,mistral_extract_worker,mistral_factory,mistral_llm_worker,mistral_llms}.py`.
- Mistral provider **tests** (same reorg — they fail pyright `reportMissingImports` under 1.x, so they must travel with the bump): `tests/unit/pipelex/plugins/{test_plugin_pipelex_storage_images,test_transport_retry_wiring}.py` and `tests/unit/pipelex/plugins/mistral/{test_mistral_worker_error_handling,test_extract_mistral_metadata,test_mistral_llm_worker_object_error_handling,test_mistral_extract_worker_semantic,test_mistral_reasoning}.py`.
- The **`message is None` guard** in `mistral_llm_worker.py` (2.x-coupled — only type-valid under mistralai 2.x; do NOT cherry-pick it anywhere that's still on 1.x).

Steps:

1. Branch off the new dev: `git checkout origin/dev -b feature/mistralai-2x-bump` (pick the final name with the user).
2. Bring over **only** the HOLD-group files from merge-4: `git checkout feature/Mistral-workflows-merge-4 -- <each HOLD-group path>`. Because these files barely intersect the bridge/tracing/graph rename (provider plugins + deps), they apply onto the reconciled dev tree cleanly. The one cross-check: confirm the `graph_context→trace_context` rename did **not** touch any mistral provider file you're carrying (grep the merge-4 versions for `graph_context` before checking them out — expect none).
3. `make agent-check` — expect pyright/mypy to now accept the 2.x provider imports + the `message is None` guard (they're valid under 2.x). If pyright flags a provider file, the reorg list is incomplete — diff that file against merge-4 and against dev to find the missing migration.
4. `make agent-test` — full non-inference suite. The bridge/tracing/Temporal tests are dev's (already green); the provider tests are the migrated 2.x ones.
5. **Gate unchanged:** this branch must NOT land on `dev`/`main` while the `instructor` git-fork pin exists (PyPI consumers of `pipelex[mistralai]` would get mistralai 2.x + PyPI-instructor = broken structured output). File/track the instructor issue per the readiness doc's "tracking issue" section if not already filed. Land only once `instructor` PR #2298 ships mistralai-2.x to PyPI, then: drop the `[tool.uv.sources] instructor` block, raise the `instructor>=…` floor, `uv lock`, re-run both gates + a **live Mistral inference + OCR round-trip** (key-gated, not in `agent-test`).

After this, `feature/Mistral-workflows-merge-4` can be retired/archived — its bridge work lives on dev, its SDK-bump work lives on the new focused branch.

## Fallback — Option (i): merge new `dev` into merge-4 (only if you must preserve merge-4's history)

`git merge origin/dev` will conflict across every bridge/tracing/graph file because merge-4 holds the pre-rename copies and dev holds the reconciled ones. Resolve **every** such conflict by taking **dev's** side (dev is canonical post-#966/#967/#968): keep `trace_context.py` / `tracing_assembly.py` / `act_assemble_tracing.py`, delete merge-4's `graph_assembly.py`, adopt `trace_context` everywhere. Keep merge-4's side **only** for the HOLD-group files above. Then run the same `agent-check`/`agent-test` gates and the same instructor gate. This is messier and leaves redundant history — prefer (ii).

## Do NOT

- Do not try to land merge-4 (or its successor) to `dev` while the `instructor` fork pin is live — that gate predates and survives #966.
- Do not cherry-pick the `message is None` guard onto any 1.x tree — pyright rejects it as `reportUnnecessaryComparison` under mistralai 1.x.
- Do not re-introduce `graph_context` / `graph_assembly.py` / `act_assemble_graph` — those are deliberately gone on dev.

## After this lands (or is staged), the third repo

The published package **`pipelex-mistralai-workflows`** consumes this bridge surface and has its own post-#966 reconciliation. See its handoff: `pipelex-mistralai-workflows/wip/post-966-bridge-reconciliation-handoff.md`. It can pin directly to a post-#966 `dev` rev and does **not** strictly depend on this `_workflows` consolidation — but if you keep the package's editable `../_workflows` override, point it at the reconciled branch from Option (ii).

## Also: re-publish the held-back Mistral Workflows user docs

The bridge PR (#969, `feature/Runtime-bridge-extraction`) ships the Mistral Workflows **docs** in the repo but holds them **out of the published docs site** (docs.pipelex.com), because the `pipelex-mistralai-workflows` PyPI name is not claimed/published yet and the live site must not advertise an unreleased package (squatting risk + broken install). When merge-4 absorbs the reconciled bridge, those docs come along still-excluded — so the same hold carries forward and must be lifted when the package launches.

What's held back and exactly how to restore it (mkdocs `exclude_docs` block to delete, nav subsection + parent-page links to restore, README/CHANGELOG install lines to put back) is in the bridge branch's checklist: **`wip/distributed-execution/mistral-workflows/docs-held-back-from-live-site.md`** (in `pipelex`, lands on `dev` with #969). Prerequisite before re-publishing: **claim `pipelex-mistralai-workflows` on PyPI first** (a `0.0.0` placeholder is enough) — that, not the doc hold, is the real squatting fix.
