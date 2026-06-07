# Mistral Workflows ↔ Pipelex — Extract as a Real Mistral Plugin

Self-contained plan. Sibling document `mistral-workflows-sub-module.md` (the
former `TODOS.md`) records what was built in-tree under
`pipelex/plugins/mistralai_workflows/` during Phases 1.x–2.1. That work is the
*input* to this project, not background to redo.

## 1. Why

What we shipped is the **functional equivalent** of a Mistral Workflows plugin
but packaged as an optional extra of `pipelex` (`pipelex[mistralai-workflows]`,
imported from `pipelex.plugins.mistralai_workflows.*`). Mistral defines a
plugin as a **standalone, pip-installable package** that depends on
`mistralai-workflows>=2.0.0` and exposes activities / workflows / dependencies
under its own top-level package (the `mistralai.workflows.plugins.*`
namespace is reserved for Mistral-supported packages).

To match that contract we need to:

1. Stop shipping Mistral-specific code inside the `pipelex` distribution.
2. Ship a separate distribution (PyPI: `pipelex-mistralai-workflows`,
   Python package: `pipelex_mistralai_workflows`) that `pip install`s
   `pipelex` and `mistralai-workflows>=3.3.0` and re-exports the same
   activities, with a Mistral-style "component" / dependency wrapper.
3. Keep the framework-agnostic embedding core (`bridge.py`,
   `execution_mode.py`, `bootstrap.py`, `exceptions.py`) reachable from
   *any* host, not just Mistral — so other durable runtimes (raw Temporal,
   future plugins) can reuse it.

## 2. Goals & non-goals

**Goals**

- Pure-Python `pipelex` distribution: no `mistralai-workflows` extra, no
  `pipelex/plugins/mistralai_workflows/` directory.
- New repo `pipelex-mistralai-workflows` scaffolded from
  `pipelex-starter-python` and adapted for a library (not an app), with
  identical lint/type/test toolchain to the rest of the workspace.
- Public surface preserved: a user who today writes
  `from pipelex.plugins.mistralai_workflows.activities import pipelex_run_pipe`
  has a clear, mechanical migration to the new import path.
- Mistral-idiomatic ergonomics: a `pipelex_dependency` (or equivalent
  component) so workers wire Pipelex the same way they wire
  `mistralai_chat_complete` today.
- CI on the new repo runs the integration test layers that need the
  optional dep (currently layer-2 / layer-3 in `mistral-workflows-sub-module.md` §3).
- Docs split cleanly: embedding-core docs stay in pipelex; Mistral-specific
  recipes move to the new repo's docs.

**Non-goals**

- Re-doing Phase 1.x / Phase 2.x design. The behavior, boundary types,
  execution modes, streaming semantics, and gotchas are all locked in —
  see `mistral-workflows-sub-module.md` §2 and §4. Treat them as spec.
- Goal 1 from the original doc (porting Pipelex orchestration to run *on*
  Mistral Workflows). Still out of scope.
- Backwards-compatibility shims in `pipelex` for the old import path. Per
  project rule (CLAUDE.md "No backward compatibility"), we just change it
  and note the migration in the changelog.

## 3. Decision points to resolve before coding

A follow-up agent should not start until these are answered. Each has a
proposed default; flag any that need a human call.

1. **Where does the framework-agnostic core live?**
   - Option A *(recommended default)*: keep `bridge.py`,
     `execution_mode.py`, `bootstrap.py`, `exceptions.py` inside `pipelex`,
     promoted out of `plugins/mistralai_workflows/` into something like
     `pipelex/embedding/` (name TBD). The new plugin pkg imports from there.
     Pros: any host (raw Temporal, future plugins) can reuse it; smaller
     surface to maintain in the new repo.
   - Option B: move *everything* into `pipelex-mistralai-workflows`. Pros:
     `pipelex` stays leaner. Cons: any future host has to either depend on
     the Mistral plugin pkg (wrong) or re-implement.
   - This decision drives the rest of the file moves.

2. **Package + distribution names.**
   - PyPI: `pipelex-mistralai-workflows` (proposed). Confirm naming aligns
     with other Pipelex packages on PyPI.
   - Top-level Python package: `pipelex_mistralai_workflows`. The
     `mistralai.workflows.plugins.*` namespace is reserved, so we cannot
     squat there.
   - GitHub repo: `pipelex-mistralai-workflows` under the existing org,
     side-by-side with the other repos listed in the workspace `CLAUDE.md`.

3. **Versioning & release cadence.**
   - Pin a minimum `pipelex` version per release. Decide whether to track
     `pipelex` major versions 1:1 or use independent SemVer.
   - Decide whether the new repo follows the same release skill / version
     conventions as `pipelex` (CHANGELOG.md format, `release/vX.Y.Z`
     branches, etc.). Default: yes, identical.

4. **Mistral component wrapper shape.**
   - Mistral's existing plugins ship a "dependency" (e.g.
     `mistralai_chat_complete`) that workers register. We should ship at
     least one — likely a wrapper around `ensure_pipelex_booted()` plus a
     `LibraryCrate` snapshot. Final shape needs a quick read of how
     `mistralai.workflows.plugins.mistralai` exposes its dependency before
     committing.

5. **Cookbook example.**
   - The deferred Phase 1.3 cookbook entry (`pipelex-cookbook/examples/c_advanced/mistral-workflows/`)
     should land *after* the new package is on PyPI, importing from the new
     path. Coordinate timing.

## 4. Workstreams

Three streams, parallelizable once §3 is resolved. Each has its own
follow-up agent / PR.

### Stream A — Refactor inside `pipelex`

In this repo (`_mistral/`, eventually merged back). High-level only; the
follow-up agent figures out the file moves once §3.1 is decided.

- Lift the framework-agnostic core to its new home (Option A) or remove it
  entirely (Option B).
- Delete the Mistral-specific modules (`activities.py`, `streaming.py`,
  `streaming_event_forwarder.py`) and their unit + integration tests.
- Drop the `[mistralai-workflows]` extra from `pyproject.toml`. Drop the
  `[[tool.mypy.overrides]]` block that exists only because Mistral's
  source uses PEP 695 syntax (re-add it in the new repo).
- Move docs: `docs/under-the-hood/mistralai-workflows-{plugin,recipes}.md`
  go to the new repo's docs site. Leave a stub in pipelex docs that links
  out.
- CHANGELOG entry under `[Unreleased]` describing the move + migration.
- Verify: `make agent-check` and `make agent-test` green; `git grep
  mistralai_workflows` returns nothing in `pipelex/` after the move.

### Stream B — Scaffold `pipelex-mistralai-workflows` from `pipelex-starter-python`

New repo, side-by-side with the other workspace repos.

- Copy `pipelex-starter-python/` as the starting point. Rename the package
  dir, rewrite `pyproject.toml` (`name`, `description`, dependencies,
  package list, classifiers).
- Convert from "app starter" to "library":
  - Drop the `my_project/hello_world.{mthds,py}` example.
  - Add a real `LICENSE` (MIT, matching pipelex).
  - Replace the README with one that explains: install, register the
    activity on a worker, call it from a workflow, link to recipes.
  - Wire `py.typed` (already present in starter — keep).
- `pyproject.toml` deltas vs starter:
  - `name = "pipelex-mistralai-workflows"`.
  - `dependencies = ["pipelex>=X.Y", "mistralai-workflows>=3.3.0"]` (no
    `[mistralai,anthropic,...]` extras — this is a library, not an app).
  - Re-add the `[[tool.mypy.overrides]]` for `mistralai.workflows.*`
    (PEP 695 source) — copy from pipelex `pyproject.toml`.
  - Pytest markers: copy the relevant subset; drop `inference`/`llm`/etc.
    if the test suite only does layer-2 / layer-3 worker tests.
- Add a Makefile mirroring the `agent-check` / `agent-test` / `cleanderived`
  targets used elsewhere in the workspace, so CLAUDE.md instructions in
  this repo and the new repo overlap.
- Add `CLAUDE.md` for the new repo. Short — point at workspace `CLAUDE.md`
  and call out: must not depend on internal `pipelex` paths, only the
  promoted public embedding core.
- GitHub Actions: copy the matrix from `pipelex` if there is one, or wire
  a minimal `uv sync && make agent-check && make agent-test` workflow.

### Stream C — Move the plugin code into the new repo

After A and B land (or in a coordinated PR pair).

- Move `activities.py`, `streaming.py`, `streaming_event_forwarder.py`
  into `pipelex_mistralai_workflows/`. Rewrite imports to point at the
  promoted embedding core in `pipelex`.
- Move the integration tests (`test_activities_direct.py`,
  `test_activities_offloaded.py`, `test_activities_streaming.py`,
  `test_bridge_temporal_blocking.py`, `test_bridge_temporal_fire_and_forget.py`)
  and their fixtures (`conftest.py`, `test_data/bridge_test.mthds`,
  `test_data/bridge_funcs.py`).
- Layer-1 framework-agnostic tests (`test_bridge_direct.py`, the unit tests
  under `tests/unit/pipelex/plugins/mistralai_workflows/`) follow the
  embedding core — they stay in `pipelex` if we picked Option A, move if
  Option B.
- Add the Mistral component / dependency wrapper from §3.4.
- First release to PyPI as `0.1.0`. Tag, write release notes, link from
  the pipelex CHANGELOG migration entry.

## 5. Migration story for users

Single-paragraph note in pipelex CHANGELOG and in the new repo's README:

> Mistral Workflows integration moved from
> `pipelex[mistralai-workflows]` / `pipelex.plugins.mistralai_workflows.*`
> into a dedicated package: `pip install pipelex-mistralai-workflows` and
> import from `pipelex_mistralai_workflows.*`. No API changes; the
> activities, boundary types, and execution modes are identical.

Per project rule, no compat shim. The pipelex release that drops the
extra and the first `pipelex-mistralai-workflows` release ship together.

## 6. Open risks (track but don't block)

- **Version coupling.** The plugin pkg depends on internal-but-public
  embedding APIs of `pipelex`. Decide on a stable surface (probably what
  `bridge.py` already exposes) and document it as such, or breakage will
  cascade on every pipelex release.
- **Test parity in CI.** Today layer-2 / layer-3 tests run on every PR in
  pipelex CI because `uv sync --all-extras` pulls the optional dep. Once
  extracted, those tests only run in the new repo. Make sure both repos'
  CI matrices are healthy before flipping the switch.
- **OffloadableField import path drift.** Already noted in
  `mistral-workflows-sub-module.md` §6. Carries over verbatim.

## 7. Resuming a session

1. Read `mistral-workflows-sub-module.md` §2, §4, §5 — these are the
   binding design decisions and gotchas you must respect.
2. Read this file end-to-end.
3. Resolve §3 with the user before writing code. Especially §3.1 (where
   the framework-agnostic core lives) — every other choice depends on it.
4. Pick a stream from §4. Streams A and B can run in parallel; Stream C
   waits on both.
