# mistralai 2.x bump — master status, verification & next steps

The single doc to read to understand where the mistralai-2.x work stands, what **you** need to verify, and what to do next. Cross-repo: it covers both `_workflows` (this repo) and the `pipelex-mistralai-workflows` plugin.

For *why* this shape (why `feature/Mistral-workflows-merge-4` was retired instead of merged), see [background-rationale.md](background-rationale.md).

## TL;DR

- `feature/Mistral-workflows-merge-4` is **retired**. dev's #969 reconciled the runtime bridge that merge-4 pioneered, so merge-4's only unique value — the **mistralai 2.x SDK bump** — was rebranched clean onto current `dev`.
- The work now lives on **two local branches**, both committed, both green (`agent-check` + `agent-test`), and deliberately **not pushed**.
- Everything is **gated from publishing** behind one external blocker: the `instructor` PyPI release that adds mistralai-2.x support ([567-labs/instructor#2298](https://github.com/567-labs/instructor/pull/2298)). Local/editable development is unaffected.

## The two branches

| Repo | Branch | Commit | What it carries |
|---|---|---|---|
| `_workflows` (this repo) | `feature/mistralai-2x-bump` (off `origin/dev`) | `b7d57c577` | The mistralai-2.x HOLD group (Mistral provider on the 2.x `mistralai.client.*` layout, `mistralai>=2.4.4`, the `instructor` git-fork pin) **plus the `refactor/Plugins-3` merge** (`a34ca9a7e`) — the whole plugin system + the Temporal-config-out-of-core externalization. See `wip/plugins/temporal-config-out-of-core.md` "Phase 3 — as-built". |
| `pipelex-mistralai-workflows` | `feature/Mistral-native` | `272c72d` | Plugin reconciled onto the post-#969 bridge **and** the Temporal externalization, **now a discoverable `pipelex.plugins` entry-point plugin** (registers the `MISTRAL_NATIVE` orchestrator); re-pinned to the editable `../_workflows` (consumes the branch above); Mistral-native cost reporting. |

Plus doc commits on this branch for this folder and `wip/plugins/`.

> **Note (2026-06-21).** Earlier rows pointed at `e13587f4b` / `11902f6`, before `refactor/Plugins-3` was merged into this branch and the plugin was made entry-point-discoverable. The publish gate below is unchanged.

> **Drift note.** `feature/mistralai-2x-bump` was cut off `origin/dev` on 2026-06-09 and carries only the SDK bump, so it falls *behind* `dev` as `dev` advances (`git status -sb` shows the count). That is expected for a parked branch — the HOLD group barely intersects anything else, so a rebase onto current `dev` is cheap and is the first un-gate step below. Re-run both gates after any rebase.

## What YOU need to verify

Run these to confirm the state yourself. Nothing here is destructive.

**1. Review the `_workflows` change (it should be *small* — only the SDK bump):**

```bash
cd /Users/lchoquel/repos/Pipelex/_workflows
git switch feature/mistralai-2x-bump
git diff --stat origin/dev...feature/mistralai-2x-bump          # only mistral provider + deps + this doc
git diff origin/dev...feature/mistralai-2x-bump -- pyproject.toml   # mistralai>=2.4.4 + instructor fork source
```

What to check: the diff vs `origin/dev` touches **only** `pipelex/plugins/mistral/*`, their tests, `test_transport_retry_wiring.py`, `pyproject.toml`, `uv.lock`, CHANGELOG, and `wip/`. If anything under `runtime_bridge/`, `graph/`, `temporal/`, or `pipe_run/` appears, the rebranch leaked bridge code — it should not.

**2. Confirm the deps resolve as intended:**

```bash
grep -A2 '^name = "mistralai"' uv.lock | grep version       # expect 2.4.9 (>= 2.4.4)
grep -A2 '^name = "instructor"' uv.lock | grep Ian321       # expect the git fork
```

**3. Re-run the `_workflows` gates (should be green):**

```bash
make agent-check && make agent-test
```

**4. Review + gate the plugin:**

```bash
cd /Users/lchoquel/repos/Pipelex/pipelex-mistralai-workflows
git switch feature/Mistral-native
git show 11902f6 --stat
make agent-check && make agent-test
```

What to check in the plugin diff: the graph-assembly activity became `act_pipelex_assemble_tracing` (unified `assemble_tracing`), `graph_context` → `trace_context` throughout, and `pyproject.toml` pins `pipelex = { path = "../_workflows", editable = true }`. The plugin's offline `agent-test` already exercises the Mistral-native dispatch path (in-process workflow env) including a FIRE_AND_FORGET round-trip.

**5. (Optional, key-gated) live Mistral Workflows run.** `make agent-test` mocks/skips real inference. A true end-to-end run against Mistral needs a `MISTRAL_API_KEY` and the plugin's inference-marked path; treat it as the final confidence check before any release, not a gate for the local branches.

## The gate — why nothing is pushed or published

`pipelex[mistralai]` pulls `instructor` for structured output, and the current PyPI `instructor` does **not** support mistralai 2.x. We use a git fork (`Ian321/instructor`, pinned in `_workflows`'s `[tool.uv.sources]`) to develop locally. If either package were published with that fork pin live, PyPI consumers would get mistralai 2.x against PyPI `instructor` = broken structured output.

So: **do not merge to `dev`/`main` or publish to PyPI while the fork pin exists.** Local editable use is fine (the fork resolves in the lockfiles).

## Next steps

**Now (your call):**

1. Review both diffs and run both gates (the checklist above).
2. Decide what to do with the two local branches: leave them parked, or push them as **WIP branches only** (not into `dev`) so the work is backed up / shareable. Either is fine — just don't open a merge-to-`dev` PR while gated.
3. Confirm `feature/Mistral-workflows-merge-4` can be archived/deleted (its bridge work is on `dev`; its SDK work is on `feature/mistralai-2x-bump`).

**When `instructor` #2298 ships mistralai-2.x to PyPI (un-gate):**

0. Rebase `feature/mistralai-2x-bump` onto current `origin/dev` (`git fetch && git rebase origin/dev`) and re-run its gates — the branch has been parked and `dev` has moved.
1. In `_workflows/pyproject.toml`: delete the `[tool.uv.sources] instructor = { git = ... }` block and raise the `instructor>=…` floor to the release that adds 2.x support.
2. `uv lock`, then `make agent-check && make agent-test`.
3. Run the optional live Mistral inference + OCR round-trip (key-gated) once.
4. Re-lock the plugin (`uv lock`) and re-run its gates so it picks up PyPI `instructor`.
5. Only then is the path open to land/publish (release flow is separate).

## Pointers

- [background-rationale.md](background-rationale.md) — why retire merge-4 (the pre-execution analysis).
- `~/.claude/plans/merge-dev-into-this-abundant-newt.md` — the executed plan (as-built).
- `_workflows` `CHANGELOG.md` `[Unreleased]` and the plugin `CHANGELOG.md` `[Unreleased]` — the user-facing notes for this work.
