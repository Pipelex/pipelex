# A2: which branch takes pipelex-temporal's entry-point-group migration

**Status: RESOLVED — Louis, 2026-08-10: base on `refactor/Topology`.** Recorded as D-A2-2 in the [plan](kernel-plugin-groups-and-distribution-plan.md#a2--as-built). Built as commit `1ed047a` on a `refactor/plugin-layer-groups` branch **stacked on** `refactor/Topology`, rather than added to PR #18 itself — that keeps #18 untouched and preserves one Part-A commit per repo, while still giving the pointer fix the base it needs. When #18 merges to `dev`, the branch retargets to `dev` cleanly. The analysis below is kept for the rationale trail.

## What the commit has to contain

1. `pyproject.toml` — `[project.entry-points."pipelex.plugins"]` → `[project.entry-points."pipelex.plugins.interpreter"]`. Temporal contributes an orchestrator, a bundle validator and hub-slot claims: all interpreter-layer, and after A1 a kernel-group plugin registering any of them fails loud at register time.
2. `tests/unit/pipelex_temporal/test_temporal_plugin_http_error_mapper.py` — two `begin_plugin(...)` calls need the now-required `group=` argument.
3. **The A0 pointer fix (D-A0-2).** `tests/unit/pipelex_temporal/test_plugin_interpreter_import_closure.py` names the core-side canonical list's file twice — its `#:` comment and its failure message — and both still say `test_runtime_layer_import_closure.py`, which A0 renamed to `test_kernel_layer_import_closure.py`. The plan deliberately parked this fix here so the repo takes exactly one Part-A commit.
4. Changelog entry (same shape as the other two repos).

## Why the base branch is not obvious

`refactor/Topology` is **PR #18, still open**. It is ahead of `dev` and not behind it, and it is where the "Keep the interpreter out of an import-light register, and gate it" commit lives — the fix that closed the 104→0 contamination, and the commit that *introduced* `test_plugin_interpreter_import_closure.py`.

That file **does not exist on `dev`** (`git cat-file -e dev:…` fails).

So:

| Base | Consequence |
| --- | --- |
| `dev` | Item 3 is impossible — the file is not there. The stale pointer then arrives on `dev` the moment #18 merges, and nobody is watching for it. Items 1, 2 and 4 land cleanly. |
| `refactor/Topology` | All four items land. But a kernel-track commit now sits on an unmerged branch from the Temporal-topology track, so Part A's plugin migration can only ship when #18 ships. Two release trains coupled. |
| Both (split the commit) | Items 1/2/4 on a `dev`-based branch, item 3 folded into #18 itself. Costs the "exactly one Part-A commit per repo" property that D-A0-2 was written to preserve, and touches someone else's open PR. |

## What is not in question

- The migration itself: Temporal is interpreter-layer, no ambiguity.
- The release gate: whichever branch takes it, the commit is not pushable until the pipelex release carrying layer-split discovery exists, because CI would install released pipelex (which reads only the retired group) and go red. The pipelex pin floor bump is owed in the same window.

## Recommendation

Base on `refactor/Topology` **if #18 is expected to merge before the pipelex release that carries Part A** — which is likely, since the A2 commit is release-gated anyway and cannot ship first. The entanglement is then only nominal: both land in the same window regardless. If #18 is expected to sit open for a while, prefer the split, and accept that D-A0-2's one-commit property was the weaker constraint.
