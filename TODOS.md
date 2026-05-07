# Mistral Workflows ↔ Pipelex — Plugin Extraction TODOS

> **Session status (2026-05-07).** Streams A, B, and C are **fully done and
> verified**. Both repos are green:
> - `pipelex-mistralai-workflows`: `make agent-check` clean,
>   `make agent-test` passes (all 8 tests including 3 layer-2 Mistral
>   activity tests + 2 layer-3 Temporal-marked tests + 2 fundamentals).
> - `pipelex` (`_workflows/`): `make agent-check` clean (pyright + mypy
>   across 1708 files), `make agent-test` passes, all 4 git-grep invariants
>   from A11 satisfied.
>
> **Stream D is the only remaining stream**: coordinated landing & PyPI
> publish (D1), cookbook (D2 deferred), risk-watch (D3), workspace docs
> update (D4). Resume entry point: §Stream D below.
>
> **One non-obvious gotcha discovered & fixed this session**: Mistral's
> `get_effective_task_queue()` returns `worker.deployment_name` (not
> `temporal.task_queue`) whenever `deployment_name` is set and doesn't match
> the configured task queue. A developer `.env` with
> `DEPLOYMENT_NAME=BatMac.local` (or anything else) silently routes
> activities to that deployment name, so the in-process test worker — which
> polls `TEST_TASK_QUEUE` — never picks them up and the workflow hangs
> forever. The fixture `override_mistralai_task_queue` in all 3 layer-2 test
> files now also clears `mistralai_config.worker.deployment_name = None`.
> This is the kind of thing Mistral may relax in a future release; if so,
> the override-to-None can become a no-op but should still be left in for
> safety.

---

## Progress snapshot — what was done across sessions

### Done in `_workflows/` (Stream A)

- **A1–A5 (refactor inside pipelex)** — `pipelex/runtime_bridge/` package
  fully populated with `__init__.py` (empty), `bridge.py`, `bootstrap.py`
  (without `get_pipelex_dependency`), `execution_mode.py`, and `exceptions.py`
  (with `PipelexRuntimeBridgeError` base + `MissingPipelexTemporalExtraError` +
  `PipelexBridgeRuntimeError`; `MistralWorkflowsNotInstalledError` dropped).
  All imports rewritten to `pipelex.runtime_bridge.*`. Library-id prefix
  changed to `runtime_bridge_`. Install hint changed to
  `pip install 'pipelex[temporal]'`. Module docstrings reframed as
  framework-agnostic.
- **A6 — Old plugin dir deleted.** `pipelex/plugins/mistralai_workflows/` no
  longer exists.
- **A7 — pyproject.toml updated.** The `mistralai-workflows = [...]` extra
  removed from `[project.optional-dependencies]`. The
  `[[tool.mypy.overrides]]` block for `mistralai.workflows.*` removed.
- **A8 (layer-1 tests)** — `tests/unit/pipelex/runtime_bridge/` populated
  with the four unit tests; `tests/integration/pipelex/runtime_bridge/`
  populated with `test_bridge_direct.py` + `conftest.py` + `test_data/`
  (`bridge_test.mthds` + `bridge_funcs.py`). The old
  `tests/{unit,integration}/pipelex/plugins/mistralai_workflows/` directories
  are deleted.
- **A9 — Docs removed.** `docs/under-the-hood/mistralai-workflows-plugin.md`
  + `mistralai-workflows-recipes.md` deleted; the four `mkdocs.yml` lines
  removed.
- **A10 — `[Unreleased]` rewritten.** The three plugin-landing bullets are
  out; the migration paragraph is in (Stream A, Changed bullet).

### Done in `pipelex-mistralai-workflows/` (Stream B + Stream C)

- **B1 — Starter content stripped.** `hello_world.py`, `hello_world.mthds`,
  `tests/test_pipelines/`, `tests/e2e/test_pipelex_mistralai_workflows.py`
  all deleted. (Empty `tests/e2e/conftest.py` left in place.)
- **B2 — pyproject.toml fully rewritten** (`v0.1.0`, slim deps, `[temporal]`
  extra, mypy override for `mistralai.workflows.*`, `pytest-mock` in dev,
  pruned markers, `[tool.uv.sources] pipelex = { path = "../_workflows", editable = true }`).
  Also added `pythonpath = ["tests"]` under `[tool.pytest]` so the
  `from integration.test_data.bridge_funcs import ...` import in
  `tests/integration/conftest.py` resolves at collection time
  (project rule forbids `tests/__init__.py`).
- **B3 — README rewritten.**
- **B4 — CLAUDE.md rewritten.**
- **B5 — CHANGELOG rewritten.** `[Unreleased]` empty; `[v0.1.0]` populated
  with the three landing bullets (rewritten paths) plus the Mistral
  `Depends`-ready `pipelex_dependency` bullet, and a Changed bullet noting
  the namespace migration.
- **B6 — CI audited.** `tests-check.yml` already calls `make install` →
  `uv sync --all-extras`, which pulls in the `[temporal]` extra. No edits
  needed.
- **B7 — Makefile audit.** Default decision honored: keep `make validate`
  as-is.
- **B8 — `uv.lock` refreshed and committed-state.** `uv lock` then
  `uv sync --all-extras` ran successfully; the editable `pipelex` install
  works (`pipelex==0.26.4` from `file:///Users/lchoquel/repos/Pipelex/_workflows`).
  Smoke-imported all six public symbols (`pipelex_run_pipe`,
  `pipelex_run_pipe_offloaded`, `pipelex_run_pipe_streaming`,
  plus the three `pipelex.runtime_bridge.*` paths) — all OK.
- **C1 — `activities.py` written** in the new repo. Optional-dep guard
  dropped; bare imports of `mistralai.workflows.{activity,...}`. Pipelex
  imports rewritten to `pipelex.runtime_bridge.bridge`.
- **C2 — `streaming.py` written.** Same edits; sibling import goes to
  `pipelex_mistralai_workflows.streaming_event_forwarder`.
- **C3 — `streaming_event_forwarder.py` copied verbatim** (it had no
  Mistral or pipelex.plugins imports already).
- **C4 — `dependency.py` written.** Single `pipelex_dependency()` callable
  that returns a `Pipelex` instance, designed to be passed to
  `mistralai.workflows.Depends(...)`. Booted on first resolve via
  `ensure_pipelex_booted()`. (`§0.5` is now considered locked.)
- **C5 — Layer-2 / 3 integration tests moved.** All five test files live in
  `pipelex-mistralai-workflows/tests/integration/` with imports rewritten
  (`pipelex.plugins.mistralai_workflows.*` → `pipelex.runtime_bridge.*` +
  `pipelex_mistralai_workflows.*`).
- **C6 — Test fixtures moved + conftest merged.** The new
  `tests/integration/conftest.py` keeps the scaffold's
  `check_pipelex_initialized` / `reset_pipelex_config_fixture` and adds
  the `bridge_test_library` class-scoped fixture. Test data
  (`bridge_test.mthds` + `bridge_funcs.py`) copied to
  `tests/integration/test_data/`. Domain string
  `mistralai_workflows_bridge_test` kept verbatim so the same `.mthds` file
  works in both repos. Conftest imports use the
  `from integration.test_data.bridge_funcs import ...` style backed by
  `pythonpath = ["tests"]` (see B2).

### Verified in this session

- New repo `make agent-check` → **clean** (ruff format + lint, plxt format +
  lint, pyright = 0 errors, mypy = no issues across 5 source files).
- `.env` for the new repo was added by the user to unblock pipelex boot
  during tests (Langfuse public key was missing).
- New repo `make agent-test` was kicked off in background **but had not
  finished by the time this pause was written** — see "What's blocking
  right now" below.

## What's blocking right now

Nothing — all in-repo work is done. Stream D's release / publish steps are
manual and intentional gates, not blockers.

## What to do next, in order

1. **Stream D — coordinated landing & follow-ups.**
   - **D1.** Land Stream A's PR on `pipelex` and ship the matching pipelex
     release (the one that introduces `pipelex.runtime_bridge` and the
     `[Unreleased]` migration paragraph). Same day, push
     `pipelex-mistralai-workflows==0.1.0` to PyPI pinning the just-released
     `pipelex` minimum.
   - **D2 (deferred).** Cookbook entry — defer per §0.6.
   - **D3.** Watch the open risks (version coupling, OffloadableField
     import drift, CI test parity).
   - **D4.** Update root workspace `CLAUDE.md` to add
     `pipelex-mistralai-workflows/` to the repo table.
2. **Before publishing v0.1.0**, strip the `[tool.uv.sources]` editable
   override from `pipelex-mistralai-workflows/pyproject.toml` so PyPI builds
   resolve `pipelex` from PyPI, not the local worktree. Add the override
   back at the start of the next dev cycle.

## Open questions / decisions the next session should NOT re-derive

- **§0.1, §0.3, §0.4 are locked AND implemented.** `pipelex.runtime_bridge`
  exists; new repo is `0.1.0`; editable `[tool.uv.sources]` override is in
  place and proven to work via `uv sync`.
- **§0.2 is locked AND implemented.** All split assignments are realized in
  code. The split is complete; no hidden Mistral-shaped helper remains in
  `pipelex.runtime_bridge`.
- **§0.5 is now locked.** The Mistral component / dependency wrapper is the
  single function `pipelex_dependency` in
  `pipelex_mistralai_workflows/dependency.py` — boots Pipelex, returns the
  singleton. Passed to `Depends(pipelex_dependency)`. No `LibraryCrate`
  helper added (deferred per §C4 second bullet).
- **§0.6 (cookbook entry timing).** Still deferred — do not block on it.

---

## Original execution plan (unchanged below this line)

Concrete execution plan for the migration described in
`wip/mistral-workflows-plugin-extract.md`. Read that file plus the
binding design decisions in `wip/mistral-workflows-sub-module.md` §2 and §4
before starting any task here.

**Two repos involved**

- `_workflows/` — git worktree of `pipelex` on branch
  `feature/Adapt-mistral-workflows`. Holds the code being extracted.
- `../pipelex-mistralai-workflows/` — already scaffolded from
  `pipelex-starter-python` (currently looks like the starter app, needs to be
  converted to a library).

The new repo's package directory is `pipelex_mistralai_workflows/` and the
PyPI name is `pipelex-mistralai-workflows`. The scaffold version sits at
`0.8.0` (inherited from the starter); we will reset to `0.1.0` as the first
real release of this project.

**Reference docs (consult these before writing Mistral-facing code)**

- Mistral Workflows skill (this repo): `.claude/skills/workflows/SKILL.md`.
  Especially:
  - `references/guides/workflows-plugins.mdx` — the plugin contract (most
    relevant to §0.5 and Stream C, task C4).
  - `references/guides/dependency-injection.mdx` — `Depends(...)` shape
    (relevant to C4).
  - `references/guides/streaming.mdx` + `references/guides/streaming-consumption.mdx`
    — Task API, `update_state`, event subscription (relevant to Stream C,
    task C2).
  - `references/guides/handling-large-data.mdx` — `OffloadableField` and
    the offloading interceptor (relevant to C1 and the open
    `OffloadableField` import-drift risk in §D3).
- Mistral docs: <https://docs.mistral.ai/studio-api/workflows/building-workflows/plugins>
  — official plugin authoring guide.

**Line numbers in this file are hints, not anchors.** When this doc cites
`pyproject.toml` line 88 or `mkdocs.yml` lines 310–311, those numbers
reflect the state at write-time. If unrelated PRs land first, the lines
shift. The **descriptive text** (e.g. "the
`mistralai-workflows = [...]` entry under `[project.optional-dependencies]`")
is the source of truth — grep for it, don't jump to a stale line number.

---

## 0. Pre-decisions (lock these before writing code)

Defaults below are the recommended path. Override only if there's a concrete
reason; otherwise proceed.

- [x] **0.1 — Framework-agnostic core lives at `pipelex/runtime_bridge/`**
      (decision locked).
- [x] **0.2 — Mistral-specific bits stay in the new repo, agnostic bits move
      to `pipelex.runtime_bridge`.** Split implemented as planned.
- [x] **0.3 — Reset `pipelex-mistralai-workflows` to `0.1.0`.**
- [x] **0.4 — Pin `pipelex>=0.27.0` in the new repo, plus an editable
      `[tool.uv.sources]` override for local dev.** Implemented.
      Reminder: strip the `[tool.uv.sources]` override before publishing
      `v0.1.0` so PyPI builds resolve `pipelex` from PyPI, not a relative
      path.
- [x] **0.5 — Mistral component / dependency wrapper shape.** Implemented
      as a single `pipelex_dependency()` callable in
      `pipelex_mistralai_workflows/dependency.py`. Suitable for
      `Depends(pipelex_dependency)`.
- [ ] **0.6 — Cookbook entry timing.** Defer
      `pipelex-cookbook/examples/c_advanced/mistral-workflows/` until after
      `pipelex-mistralai-workflows==0.1.0` is on PyPI (Stream D).

---

## Stream A — Refactor inside `pipelex` (this worktree)

Goal: end state where `git grep mistralai_workflows` and `git grep
mistralai-workflows` both return zero hits inside `pipelex/`, and the
framework-agnostic core lives at `pipelex.runtime_bridge.*`.

### A1. Create the new package

- [x] Create `pipelex/runtime_bridge/` with an empty `__init__.py`.

### A2. Move `bridge.py`

- [x] Move + rewrite imports + rename library-id prefix + update install
      hint + reframe docstring.

### A3. Move `execution_mode.py`

- [x] Move; docstring slightly reframed away from Mistral-specific wording.

### A4. Move `bootstrap.py` (split — keep agnostic, drop Mistral-shaped)

- [x] Move; keep `ensure_pipelex_booted`. `get_pipelex_dependency` removed
      (lives in the new repo per C4).

### A5. Split `exceptions.py`

- [x] Created `pipelex/runtime_bridge/exceptions.py` with the new base
      `PipelexRuntimeBridgeError` + `MissingPipelexTemporalExtraError` +
      `PipelexBridgeRuntimeError`. `MistralWorkflowsNotInstalledError`
      intentionally dropped.

### A6. Delete the old plugin directory

- [x] `pipelex/plugins/mistralai_workflows/` removed.

### A7. Update `pyproject.toml`

- [x] `mistralai-workflows` extra removed.
- [x] `[[tool.mypy.overrides]]` block for `mistralai.workflows.*` removed.

### A8. Move/delete tests

- [x] Layer-1 unit tests moved to `tests/unit/pipelex/runtime_bridge/`.
- [x] Layer-1 integration test moved to
      `tests/integration/pipelex/runtime_bridge/test_bridge_direct.py`
      with the conftest + test_data.
- [x] Layer-2 / layer-3 integration test files deleted from
      `_workflows/` (they live in the new repo per Stream C).
- [x] Old plugin test directories
      (`tests/{unit,integration}/pipelex/plugins/mistralai_workflows/`)
      deleted entirely.

### A9. Move docs

- [x] Both `under-the-hood/mistralai-workflows-*.md` deleted.
- [x] Four `mkdocs.yml` lines removed.
- [ ] **Optional stub.** Default decision: skip — no
      `under-the-hood/mistralai-workflows.md` redirect page added.

### A10. Update `CHANGELOG.md`

- [x] The three plugin-landing bullets removed from `[Unreleased]`.
- [x] Migration `Changed` bullet added under `[Unreleased]`.

### A11. Verify

- [x] `make cleanderived && make rtm && make agent-check` clean. (`make rtm`
      regenerates `_generated_model_sets.py` which `cleanderived` deletes —
      pyright fails without it.)
- [x] `make agent-test` green.
- [x] `git grep mistralai_workflows pipelex/ tests/ pyproject.toml` →
      remaining hits are all in `tests/integration/pipelex/runtime_bridge/`
      test data (domain string `mistralai_workflows_bridge_test`, function
      name `mistralai_workflows_bridge_echo`). Per A8's
      "minimize churn" decision, these were intentionally kept verbatim;
      no production-code reference to the old plugin namespace remains.
- [x] `git grep mistralai-workflows pipelex/ tests/ pyproject.toml` → one
      hit, a docstring comment in `test_bridge_direct.py` referring to the
      *new* package `pipelex-mistralai-workflows`. Acceptable.
- [x] `git grep mistralai-workflows CHANGELOG.md` → exactly the migration
      paragraph.
- [x] `git grep "pipelex.runtime_bridge" pipelex/ tests/` finds 8 files in
      the new layout.

### A12. (Out-of-scope reminder) Verify "make agent-check passes without optional dep"

The outstanding box from `mistral-workflows-sub-module.md` §Outstanding
("`make agent-check` passes with `mistralai-workflows` NOT installed")
becomes trivially true once A6 + A7 are done — `pipelex` no longer imports
`mistralai.workflows` anywhere. No separate verification step needed.

---

## Stream B — Adapt the `pipelex-mistralai-workflows` scaffold

### B1. Strip starter content

- [x] All starter files removed.
- [x] Empty `tests/e2e/` directory + conftest left in place (harmless).

### B2. Rewrite `pyproject.toml`

- [x] All bullets implemented (see snapshot above).
- [x] Added `pythonpath = ["tests"]` under `[tool.pytest]` after a runtime
      `ModuleNotFoundError: No module named 'integration'` was hit during
      the first `make agent-test` attempt. Project rule forbids
      `tests/__init__.py`, so the conftest uses
      `from integration.test_data.bridge_funcs import ...` and pytest's
      `pythonpath` adds `tests/` to `sys.path` at collection time.

### B3. Replace the README

- [x] Replaced.

### B4. Replace `CLAUDE.md`

- [x] Replaced.

### B5. Rewrite `CHANGELOG.md`

- [x] Replaced. Carried the three landing bullets into `[v0.1.0]` Added,
      added the dependency-helper bullet, and a Changed bullet for the
      namespace migration.

### B6. Audit `.github/workflows/`

- [x] Reviewed. `tests-check.yml` already runs `make install` →
      `uv sync --all-extras`, which installs the `[temporal]` extra. No
      edits needed. The other 7 workflows (lint, package, version,
      changelog, cla, guard-branches, github-release) are generic and
      reference the right repo.

### B7. Audit `Makefile`

- [x] Default decision honored: keep `make validate` as-is (it's a no-op
      when there are no `.mthds` in `pipelex_mistralai_workflows/`).

### B8. Refresh `uv.lock`

- [x] `uv lock` + `uv sync --all-extras` ran cleanly; the editable
      `pipelex` install resolves to the worktree path.
      `mistralai-workflows` is locked at `==3.4.0` (the floor is
      `>=3.3.0`; both 3.3.0 and 3.4.0 confirmed working once the
      `deployment_name` fixture override is in place — see C7).
      (Lock file is uncommitted in the new repo's working tree until you
      commit.)

---

## Stream C — Move plugin code into the new repo

### C1. Move `activities.py`

- [x] Moved + guard dropped + imports rewritten.

### C2. Move `streaming.py`

- [x] Moved + guard dropped + imports rewritten.

### C3. Move `streaming_event_forwarder.py`

- [x] Copied verbatim.
- [x] writer_id `"mistralai-workflows-streaming"` kept verbatim.

### C4. Add the Mistral component / dependency wrapper

- [x] `pipelex_mistralai_workflows/dependency.py` written. Single
      `pipelex_dependency()` callable shaped for
      `mistralai.workflows.Depends(...)`.
- [ ] Optional `LibraryCrate` snapshot helper — deferred. Reference
      Mistral plugin (`mistralai.workflows.plugins.mistralai`) does not
      mandate it; revisit after first user feedback.

### C5. Move integration tests (layer-2 / layer-3)

- [x] All five files moved with imports rewritten:
  - `test_activities_direct.py`
  - `test_activities_offloaded.py`
  - `test_activities_streaming.py`
  - `test_bridge_temporal_blocking.py`
  - `test_bridge_temporal_fire_and_forget.py`

### C6. Move test fixtures

- [x] `tests/integration/conftest.py` merged with the scaffold's existing
      fixtures plus the `bridge_test_library` class-scoped fixture.
- [x] `tests/integration/test_data/{bridge_test.mthds,bridge_funcs.py}`
      copied across.

### C7. Verify the new repo

- [x] `make agent-check` clean.
- [x] `make agent-test` green — all 8 tests pass (3 layer-2 activity
      tests, 2 layer-3 Temporal tests, 2 fundamentals, 1 dry-run-all).
      **Required test fixture fix**: in all 3 layer-2 test files, the
      `override_mistralai_task_queue` fixture also clears
      `mistralai_config.worker.deployment_name = None`. Without this, a
      developer `.env` with `DEPLOYMENT_NAME=...` (or any non-test value)
      causes Mistral's `get_effective_task_queue()` to route activities
      to that deployment name instead of `TEST_TASK_QUEUE`, leading to a
      silent workflow hang.
- [x] Smoke imports already validated:

      ```python
      from pipelex_mistralai_workflows.activities import pipelex_run_pipe, pipelex_run_pipe_offloaded
      from pipelex_mistralai_workflows.streaming import pipelex_run_pipe_streaming
      from pipelex_mistralai_workflows.dependency import pipelex_dependency
      from pipelex.runtime_bridge.bridge import PipelexPipeRunInput, PipelexPipeRunOutput, run_pipe_via_bridge
      from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode
      from pipelex.runtime_bridge.bootstrap import ensure_pipelex_booted
      ```

### C8. First release

- [ ] Tag `v0.1.0` in `pipelex-mistralai-workflows`.
- [ ] Push the tag and create the GitHub release.
- [ ] Publish to PyPI as `pipelex-mistralai-workflows==0.1.0`.
- [ ] Coordinate with the matching pipelex release (Stream D §D1).

---

## Stream D — Coordinated landing & follow-ups

### D1. Coordinated land

- [ ] Land Stream A's PR on `pipelex` and ship the matching pipelex release
      (containing the `pipelex.runtime_bridge` package and the migration
      paragraph in CHANGELOG).
- [ ] On the same day, push `pipelex-mistralai-workflows==0.1.0` to PyPI
      pinning `pipelex>=0.27.0` to match the freshly-released pipelex.

### D2. Cookbook entry (deferred from Phase 1.3)

- [ ] In `pipelex-cookbook/`, create
      `examples/c_advanced/mistral-workflows/`:
  - Tier-1 DIRECT-mode worker script (using `pipelex_run_pipe` from the
    new package).
  - Tier-2 typed activity exercising `library_crate_dump`.
  - README pointing back at the new repo's docs.
- [ ] Update `mistral-workflows-sub-module.md` §Status board to check off
      the deferred Phase 1.3 cookbook entry.

### D3. Watch the open risks

- [ ] **Version coupling.** Document the `pipelex.runtime_bridge` public
      surface as stable in pipelex docs. A breaking change to that surface
      is a breaking change for the plugin pkg.
- [ ] **OffloadableField import drift.** `activities.py` (now in the new
      repo) imports `OffloadableField, OffloadableModel` from
      `mistralai.workflows.core.encoding.fields_offloader`. If a Mistral
      upgrade moves the path, fix in the plugin pkg.
- [ ] **CI test parity.** Layer-2/3 tests now run only in
      `pipelex-mistralai-workflows` CI. Make sure both repos' matrices are
      green before flipping the switch (i.e. before merging Stream A's PR
      to `main` and publishing v0.1.0).

### D4. Workspace docs

- [ ] Update root workspace `CLAUDE.md`'s repository table to include
      `pipelex-mistralai-workflows/` (PyPI: `pipelex-mistralai-workflows`,
      Python package: `pipelex_mistralai_workflows`).

---

## Resume guide

If you're picking this up cold:

1. Read `wip/mistral-workflows-sub-module.md` §2 and §4 — the binding
   design decisions and gotchas. Treat as spec; don't re-derive.
2. Read `wip/mistral-workflows-plugin-extract.md` end-to-end — the
   strategy. This file (`TODOS.md`) is the execution layer.
3. §0 pre-decisions are locked except §0.6 (cookbook timing — still
   deferred). Do not re-debate.
4. Pick up from §Progress snapshot's "What to do next, in order" — the
   pending items are A11 verification + the in-flight new-repo
   `make agent-test` outcome + Stream D landing.
5. After every step: `make agent-check && make agent-test` in whichever
   repo you touched.
