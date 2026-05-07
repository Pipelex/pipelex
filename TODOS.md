# Mistral Workflows ↔ Pipelex — Plugin Extraction TODOs

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

---

## 0. Pre-decisions (lock these before writing code)

Defaults below are the recommended path. Override only if there's a concrete
reason; otherwise proceed.

- [ ] **0.1 — Where the framework-agnostic core lives.** Default: `pipelex/embedding/`.
      Free package name (verified — no clash with existing modules; the
      "embedding" hits in pipelex are unrelated HTML / jinja2 string usages).
      The name communicates *embedding the Pipelex runtime into another
      host runtime*. If the vector-embedding overlap feels confusing later,
      `pipelex.runtime_bridge` is the fallback.
- [ ] **0.2 — Mistral-specific bits stay in the new repo, agnostic bits move
      to `pipelex.embedding`.** Concrete split:
  - **Move to `pipelex/embedding/`:** `bridge.py`, `execution_mode.py`,
    `bootstrap.py::ensure_pipelex_booted`, the agnostic exceptions
    (`PipelexBridgeRuntimeError`, `MissingPipelexTemporalExtraError`).
  - **Move to `pipelex_mistralai_workflows/`:** `activities.py`,
    `streaming.py`, `streaming_event_forwarder.py`,
    `bootstrap.py::get_pipelex_dependency` (Mistral-shaped — references
    `mistralai.workflows.Depends`).
  - **Delete entirely:** `MistralWorkflowsPluginError`,
    `MistralWorkflowsNotInstalledError`. Once `mistralai-workflows>=3.3.0`
    is a hard dep of the new repo, the optional-dep guards in
    `activities.py` / `streaming.py` are obsolete and the import-fail
    exception goes with them.
- [ ] **0.3 — Reset `pipelex-mistralai-workflows` to `0.1.0`.** Currently
      `0.8.0` (starter inheritance) — that version space is wrong for a
      brand-new project. First release ships as `v0.1.0`.
- [ ] **0.4 — Pin `pipelex>=NEXT` in the new repo.** `NEXT` is whatever
      pipelex version lands the `pipelex.embedding` package. Bump the
      minimum on every pipelex release that touches the embedding surface.
      Independent SemVer for the plugin pkg.
- [ ] **0.5 — Mistral component / dependency wrapper shape.** Open: read
      `mistralai.workflows.plugins.mistralai` (the reference plugin) before
      committing to a shape. Stream C task C4 below holds the placeholder.
- [ ] **0.6 — Cookbook entry timing.** Defer
      `pipelex-cookbook/examples/c_advanced/mistral-workflows/` until after
      `pipelex-mistralai-workflows==0.1.0` is on PyPI (Stream D).

---

## Stream A — Refactor inside `pipelex` (this worktree)

Goal: end state where `git grep mistralai_workflows` and `git grep
mistralai-workflows` both return zero hits inside `pipelex/`, and the
framework-agnostic core lives at `pipelex.embedding.*`.

### A1. Create the new package

- [ ] Create `pipelex/embedding/` with an empty `__init__.py` (no
      re-exports — Pipelex rule).

### A2. Move `bridge.py`

- [ ] Move `pipelex/plugins/mistralai_workflows/bridge.py` →
      `pipelex/embedding/bridge.py`.
- [ ] Rewrite imports inside `bridge.py`:
  - `from pipelex.plugins.mistralai_workflows.bootstrap import ensure_pipelex_booted`
    → `from pipelex.embedding.bootstrap import ensure_pipelex_booted`
  - `from pipelex.plugins.mistralai_workflows.exceptions import (MissingPipelexTemporalExtraError, PipelexBridgeRuntimeError)`
    → `from pipelex.embedding.exceptions import (MissingPipelexTemporalExtraError, PipelexBridgeRuntimeError)`
  - `from pipelex.plugins.mistralai_workflows.execution_mode import PipelexExecutionMode`
    → `from pipelex.embedding.execution_mode import PipelexExecutionMode`
- [ ] Rename the per-call library id prefix on line 222:
      `f"mistralai_workflows_{uuid4().hex[:8]}"` →
      `f"embedding_{uuid4().hex[:8]}"`.
- [ ] Update the install hint in `_require_pipelex_temporal_extra` (line 336):
      `"pip install 'pipelex[temporal,mistralai-workflows]'"` →
      `"pip install 'pipelex[temporal]'"`.
- [ ] Update the module docstring: drop "of the mistralai_workflows plugin",
      reframe as "framework-agnostic Pipelex embedding surface for host
      runtimes (Mistral Workflows, raw Temporal, future plugins)".

### A3. Move `execution_mode.py`

- [ ] Move `pipelex/plugins/mistralai_workflows/execution_mode.py` →
      `pipelex/embedding/execution_mode.py`. No import changes inside the
      file.

### A4. Move `bootstrap.py` (split — keep agnostic, drop Mistral-shaped)

- [ ] Move `pipelex/plugins/mistralai_workflows/bootstrap.py` →
      `pipelex/embedding/bootstrap.py`.
- [ ] Keep `ensure_pipelex_booted(...)` verbatim. Update the module
      docstring: drop "for use inside Mistral Workflows activities", reframe
      as "for use inside any host runtime that embeds Pipelex".
- [ ] **Delete** `get_pipelex_dependency()` from `pipelex/embedding/bootstrap.py`
      — it returns a callable explicitly shaped for `mistralai.workflows.Depends`
      and belongs in the new repo. Its replacement lives in
      `pipelex_mistralai_workflows/dependency.py` (Stream C, task C4).

### A5. Split `exceptions.py`

- [ ] Create `pipelex/embedding/exceptions.py` with:
  - `PipelexEmbeddingError(PipelexError)` — new base (replaces
    `MistralWorkflowsPluginError`).
  - `MissingPipelexTemporalExtraError(PipelexEmbeddingError)`.
  - `PipelexBridgeRuntimeError(PipelexEmbeddingError)`.
- [ ] **Do NOT** carry `MistralWorkflowsNotInstalledError` over — it goes
      away entirely (the new repo has `mistralai-workflows>=3.3.0` as a
      hard dep, so the optional-dep guard pattern is obsolete).

### A6. Delete the old plugin directory

- [ ] After A2–A5 are complete and tests still pass, delete the entire
      directory `pipelex/plugins/mistralai_workflows/`. This includes:
  - `__init__.py`
  - `bridge.py` (moved in A2)
  - `bootstrap.py` (moved in A4)
  - `exceptions.py` (split in A5)
  - `execution_mode.py` (moved in A3)
  - `activities.py` (deleted; lives in new repo per Stream C)
  - `streaming.py` (deleted; lives in new repo per Stream C)
  - `streaming_event_forwarder.py` (deleted; lives in new repo per Stream C)

### A7. Update `pyproject.toml`

- [ ] Remove the `mistralai-workflows = ["mistralai-workflows>=3.3.0"]`
      entry from `[project.optional-dependencies]` (currently line 88).
- [ ] Remove the entire `[[tool.mypy.overrides]]` block for
      `mistralai.workflows.*` / `mistralai.workflows` (currently lines
      154–164). Pipelex no longer imports anything from that namespace.

### A8. Move/delete tests

Layer-1 (framework-agnostic) tests follow the embedding core into pipelex.
Layer-2 / layer-3 tests (which actually instantiate Mistral
`WorkflowEnvironment` / activities) go to the new repo via Stream C.

- [ ] **Move** `tests/unit/pipelex/plugins/mistralai_workflows/` →
      `tests/unit/pipelex/embedding/`:
  - `test_input_models.py`
  - `test_execution_mode.py`
  - `test_validation.py`
  - `test_dispatch.py`
  - In each, rewrite `pipelex.plugins.mistralai_workflows.*` imports →
    `pipelex.embedding.*`.
- [ ] **Move** the layer-1 integration test:
      `tests/integration/pipelex/plugins/mistralai_workflows/test_bridge_direct.py`
      → `tests/integration/pipelex/embedding/test_bridge_direct.py`.
      Rewrite imports.
- [ ] **Move the conftest + test_data with it.** They are needed by the
      layer-1 test that stays in pipelex AND will be copied to the new repo
      (Stream C, C6) for the layer-2 / layer-3 tests:
  - `tests/integration/pipelex/plugins/mistralai_workflows/conftest.py`
    → `tests/integration/pipelex/embedding/conftest.py`. Update the import
    path inside (`from tests.integration.pipelex.plugins.mistralai_workflows.test_data.bridge_funcs`
    → `from tests.integration.pipelex.embedding.test_data.bridge_funcs`).
  - `tests/integration/pipelex/plugins/mistralai_workflows/test_data/`
    → `tests/integration/pipelex/embedding/test_data/` (`bridge_test.mthds`
    + `bridge_funcs.py`).
  - Update the `domain` in `bridge_test.mthds` if the prefix
    `mistralai_workflows_bridge_test` reads weirdly post-move; suggest
    keeping the existing domain string for the move PR to minimize churn,
    rename in a follow-up if needed. Tests reference the literal pipe
    refs so any rename must be coordinated.
- [ ] **Delete** the layer-2 / layer-3 integration tests (they move to the
      new repo via Stream C):
  - `test_activities_direct.py`
  - `test_activities_offloaded.py`
  - `test_activities_streaming.py`
  - `test_bridge_temporal_blocking.py`
  - `test_bridge_temporal_fire_and_forget.py`
- [ ] Delete the now-empty
      `tests/{unit,integration}/pipelex/plugins/mistralai_workflows/` dirs.

### A9. Move docs

- [ ] **Delete** `docs/under-the-hood/mistralai-workflows-plugin.md` and
      `docs/under-the-hood/mistralai-workflows-recipes.md`. Their content
      moves to the new repo's docs (Stream B, B3 README + future docs site).
- [ ] **Update `mkdocs.yml`** — remove four lines:
  - line 310: `- under-the-hood/mistralai-workflows-plugin.md: "Mistral Workflows Plugin"`
  - line 311: `- under-the-hood/mistralai-workflows-recipes.md: "Mistral Workflows Recipes"`
  - line 500: `- Mistral Workflows Plugin: under-the-hood/mistralai-workflows-plugin.md`
  - line 501: `- Mistral Workflows Recipes: under-the-hood/mistralai-workflows-recipes.md`
- [ ] **Optional stub.** If we want a discoverable redirect, add a single
      short page `docs/under-the-hood/mistralai-workflows.md` containing a
      one-paragraph "moved to a separate package" notice with a link to
      the new repo. Re-wire `mkdocs.yml` to reference it. Default: skip
      the stub — the CHANGELOG migration entry (A10) covers discovery.

### A10. Update `CHANGELOG.md`

The current `[Unreleased]` section has three entries documenting the plugin
landing. Replace with the migration story.

- [ ] Remove the three plugin-specific bullets from `[Unreleased]` (the
      `pipelex.plugins.mistralai_workflows` activity, the streaming
      variant, the per-step streaming additions). They will live in the
      new repo's CHANGELOG (Stream B, B5).
- [ ] Add a new `[Unreleased]` bullet:

      > **Mistral Workflows integration extracted into a dedicated package.**
      > The optional `pipelex[mistralai-workflows]` extra and the
      > `pipelex.plugins.mistralai_workflows.*` modules have been removed
      > from `pipelex`. Install the new package instead:
      > `pip install pipelex-mistralai-workflows`, and import from
      > `pipelex_mistralai_workflows.*`. The framework-agnostic embedding
      > core (boundary types, `run_pipe_via_bridge`, `PipelexExecutionMode`,
      > `ensure_pipelex_booted`) has been promoted from
      > `pipelex.plugins.mistralai_workflows.*` to `pipelex.embedding.*` so
      > any host runtime — not just Mistral Workflows — can embed Pipelex.
      > No behavior changes; activities, boundary types, and execution
      > modes are identical.

      Per project rule (CLAUDE.md "No backward compatibility"), no compat
      shim. The pipelex release that drops the extra ships together with
      `pipelex-mistralai-workflows==0.1.0`.

### A11. Verify

- [ ] `make agent-check` clean.
- [ ] `make agent-test` green.
- [ ] `git grep mistralai_workflows pipelex/ tests/ pyproject.toml` returns no hits.
- [ ] `git grep mistralai-workflows pipelex/ tests/ pyproject.toml` returns
      only the migration paragraph in `CHANGELOG.md` and the install hint
      in `_require_pipelex_temporal_extra` (now removed per A2 — verify).
- [ ] `git grep "pipelex.embedding" pipelex/ tests/` finds the new package
      paths.

### A12. (Out-of-scope reminder) Verify "make agent-check passes without optional dep"

The outstanding box from `mistral-workflows-sub-module.md` §Outstanding
("`make agent-check` passes with `mistralai-workflows` NOT installed")
becomes trivially true once A6 + A7 are done — `pipelex` no longer imports
`mistralai.workflows` anywhere. No separate verification step needed.

---

## Stream B — Adapt the `pipelex-mistralai-workflows` scaffold

Currently the repo at `../pipelex-mistralai-workflows/` is the
`pipelex-starter-python` scaffold with a `hello_world` example. Convert
to a library distribution.

### B1. Strip starter content

- [ ] Delete `pipelex_mistralai_workflows/hello_world.py`.
- [ ] Delete `pipelex_mistralai_workflows/hello_world.mthds`.
- [ ] Keep `pipelex_mistralai_workflows/__init__.py` (empty) and
      `pipelex_mistralai_workflows/py.typed`.
- [ ] Delete `tests/test_pipelines/` (starter artifact — no test pipelines
      yet) and `tests/e2e/test_pipelex_mistralai_workflows.py` (starter
      smoke test that imports `hello_world`). Layer-1+ tests come from
      Stream C.

### B2. Rewrite `pyproject.toml`

- [ ] `version = "0.1.0"` (currently `0.8.0`).
- [ ] `description = "Mistral Workflows plugin for Pipelex — invoke Pipelex pipes from inside Mistral Workflows activities."`
      (currently a placeholder).
- [ ] Uncomment `authors` and set to
      `[{ name = "Evotis S.A.S.", email = "oss@pipelex.com" }]` (matching
      pipelex).
- [ ] Update `[project.urls]`:
  - `Homepage = "https://pipelex.com"`
  - `Repository = "https://github.com/Pipelex/pipelex-mistralai-workflows"`
  - `Documentation = "https://docs.pipelex.com/"`
- [ ] Replace `dependencies = ["pipelex[mistralai,anthropic,...]>=0.26.4"]`
      with the slim library shape:

      ```toml
      dependencies = [
        "pipelex>=NEXT",                 # NEXT = the version that ships pipelex.embedding
        "mistralai-workflows>=3.3.0",
      ]
      ```

      No inference / cloud extras. This is a library, not an app.
- [ ] Add an optional extra for the Temporal layer-3 tests:

      ```toml
      [project.optional-dependencies]
      temporal = ["pipelex[temporal]>=NEXT"]
      ```
- [ ] Add the PEP 695 mypy override that pipelex used to carry — Mistral's
      source still uses PEP 695 type parameters mypy rejects under the
      project's `python_version`. Copy the block (lines 154–164 in
      pipelex's old `pyproject.toml` — moved here in Stream A task A7):

      ```toml
      [[tool.mypy.overrides]]
      follow_imports = "skip"
      ignore_errors = true
      module = ["mistralai.workflows.*", "mistralai.workflows"]
      ```
- [ ] Add `pytest-asyncio>=0.24.0`, `pytest-mock>=3.14.0` to the `dev`
      extra.
- [ ] **Pytest markers** — keep only the markers the test suite actually
      uses. Drop `inference` / `llm` / `img_gen` / `extract` / `pipelex_api`
      (the layer-2/3 tests don't call inference). Keep:
  - `gha_disabled`
  - `dry_runnable`
  - `temporal: tests that require a Temporal server` (mirror pipelex's)
- [ ] Reconsider `requires-python`. The scaffold is `>=3.12,<3.15` (because
      `mistralai-workflows` requires 3.12+). pipelex itself targets 3.10+.
      Keep `>=3.12,<3.15` here — Mistral Workflows is the binding floor.
      Confirm by checking `mistralai-workflows` PyPI metadata.

### B3. Replace the README

- [ ] Replace `README.md` (currently the starter's) with a library-style
      README. Sections:
  - Title + one-paragraph pitch ("Invoke Pipelex pipes from inside Mistral
    Workflows activities").
  - Install: `pip install pipelex-mistralai-workflows`. Optional Temporal
    layer: `pip install 'pipelex-mistralai-workflows[temporal]'`.
  - Quick start (Tier 1): import `pipelex_run_pipe`, register on a worker,
    call from a workflow.
  - Per-call library scoping (Tier 2/3) using `library_crate_dump`.
  - Streaming variant (`pipelex_run_pipe_streaming`).
  - Migration note (mirror the CHANGELOG entry from Stream A, A10).
  - Links: Pipelex docs, MTHDS standard, Mistral Workflows docs.

  Move the bulk of the deleted pipelex docs (`mistralai-workflows-plugin.md`
  + `mistralai-workflows-recipes.md`) into the README — the docs site can
  come later. Keep the README scannable; deeper recipes can become a
  `docs/` subdirectory in a follow-up.

### B4. Replace `CLAUDE.md`

- [ ] Replace with a short repo-specific CLAUDE.md:
  - Point at workspace `CLAUDE.md` for global rules.
  - Note: do NOT depend on internal `pipelex` paths (e.g. anything under
    `pipelex.pipe_run`, `pipelex.libraries`, etc.). Only depend on the
    public `pipelex.embedding.*` surface.
  - List the same `make agent-check` / `make agent-test` / `cleanderived`
    workflow used in pipelex.
  - Mirror pipelex's "No backward compatibility" rule.

### B5. Rewrite `CHANGELOG.md`

- [ ] Replace existing `[v0.8.0]` placeholder. New top-of-file:

      ```markdown
      # Changelog

      ## [Unreleased]

      ## [v0.1.0] - <release date>

      First release. Extracts the Mistral Workflows ↔ Pipelex bridge from
      `pipelex[mistralai-workflows]` into a dedicated package.

      ### Added

      - `pipelex_mistralai_workflows.activities.pipelex_run_pipe` — pre-decorated
        Mistral Workflows activity wrapping `pipelex.embedding.run_pipe_via_bridge`.
      - `pipelex_mistralai_workflows.activities.pipelex_run_pipe_offloaded` —
        offload-capable variant for payloads that exceed Temporal's per-event
        size limit.
      - `pipelex_mistralai_workflows.streaming.pipelex_run_pipe_streaming` —
        streaming activity that wraps the run in a Mistral `Task`
        (`custom_task_type="pipelex.pipe_run"`) so subscribers see
        `CustomTaskStarted` → `CustomTaskInProgress` → `CustomTaskCompleted` /
        `CustomTaskFailed` events. Emits per-step `CustomTaskInProgress`
        events for `DIRECT` execution mode.
      - `pipelex_mistralai_workflows.dependency.pipelex_dependency` — Mistral
        component / dependency wrapper around `ensure_pipelex_booted` (see
        §0.5 — final shape TBD pending a read of
        `mistralai.workflows.plugins.mistralai`).

      ### Changed

      - Migrated from `pipelex.plugins.mistralai_workflows.*` to
        `pipelex_mistralai_workflows.*`. Framework-agnostic types
        (`PipelexPipeRunInput`, `PipelexPipeRunOutput`,
        `run_pipe_via_bridge`, `PipelexExecutionMode`,
        `ensure_pipelex_booted`) now imported from `pipelex.embedding.*`.
      ```

      Carry the three original landing-narrative bullets from the old
      pipelex `[Unreleased]` (deleted in A10) into the **Added** section
      above, rewriting the import paths to the new namespaces.

### B6. Audit `.github/workflows/`

The starter shipped 8 workflows. Verify each is fit-for-purpose:

- [ ] `tests-check.yml` — the test job needs to install `pipelex[temporal]`
      via the new `[temporal]` extra so layer-3 tests run. Confirm the
      install step uses `uv sync --extra temporal` (or equivalent).
- [ ] `lint-check.yml` — should already work (calls `make` targets).
- [ ] `package-check.yml` — verifies the wheel builds; no changes.
- [ ] `version-check.yml` — verifies version bumps follow SemVer; review
      that it works for a non-app library.
- [ ] `changelog-check.yml` — verifies CHANGELOG was updated on PRs;
      confirm format expected matches B5.
- [ ] `cla.yml`, `guard-branches.yml`, `github-release.yml` — generic; keep
      as-is, confirm they reference the right repo.

If any workflow assumes starter conventions that don't apply, prune.

### B7. Audit `Makefile`

- [ ] Confirm all targets resolve in the new dep layout. Specifically:
  - `make agent-check` should work without `mistralai-workflows`-specific
    knowledge (it's a hard dep now).
  - `make validate` calls `pipelex validate --all` — works only if the
    package directory contains valid `.mthds` (currently the starter's
    `hello_world.mthds` is being deleted in B1; layer-2 tests carry their
    own `bridge_test.mthds` under `tests/integration/test_data/`). Decide
    whether `make validate` is meaningful for this repo. Default: keep the
    target; it's a no-op when there are no `.mthds` in the package.

### B8. Refresh `uv.lock`

- [ ] After B2 lands, run inside the new repo:

      ```bash
      uv lock
      uv sync --all-extras
      ```

      Commit the updated `uv.lock`.

---

## Stream C — Move plugin code into the new repo

Coordinated with the pipelex deletions in Stream A. Land Stream A's PR and
Stream C's first commit in lockstep so `git bisect` always builds.

### C1. Move `activities.py`

- [ ] Move `pipelex/plugins/mistralai_workflows/activities.py` →
      `pipelex_mistralai_workflows/activities.py`.
- [ ] **Drop the optional-dep guard.** Replace:

      ```python
      try:
          from mistralai.workflows import activity
          from mistralai.workflows.core.encoding.fields_offloader import OffloadableField, OffloadableModel
      except ImportError as exc:
          msg = (...)
          raise MistralWorkflowsNotInstalledError(msg) from exc
      ```

      with bare imports:

      ```python
      from mistralai.workflows import activity
      from mistralai.workflows.core.encoding.fields_offloader import OffloadableField, OffloadableModel
      ```
- [ ] Rewrite Pipelex imports:
  - `from pipelex.plugins.mistralai_workflows.bridge import (PipelexPipeRunInput, PipelexPipeRunOutput, run_pipe_via_bridge)`
    → `from pipelex.embedding.bridge import (PipelexPipeRunInput, PipelexPipeRunOutput, run_pipe_via_bridge)`
  - Drop the `from pipelex.plugins.mistralai_workflows.exceptions import MistralWorkflowsNotInstalledError` import (exception deleted).

### C2. Move `streaming.py`

- [ ] Move `pipelex/plugins/mistralai_workflows/streaming.py` →
      `pipelex_mistralai_workflows/streaming.py`.
- [ ] Drop the optional-dep guard (same pattern as C1).
- [ ] Rewrite imports:
  - `pipelex.plugins.mistralai_workflows.bridge` → `pipelex.embedding.bridge`
  - `pipelex.plugins.mistralai_workflows.execution_mode` → `pipelex.embedding.execution_mode`
  - `pipelex.plugins.mistralai_workflows.streaming_event_forwarder` → `pipelex_mistralai_workflows.streaming_event_forwarder`
  - Drop the `MistralWorkflowsNotInstalledError` import.

### C3. Move `streaming_event_forwarder.py`

- [ ] Move `pipelex/plugins/mistralai_workflows/streaming_event_forwarder.py`
      → `pipelex_mistralai_workflows/streaming_event_forwarder.py`. The
      file has no `mistralai.workflows` imports and no
      `pipelex.plugins.mistralai_workflows` imports — it's already
      framework-agnostic. No edits needed beyond placement.
- [ ] Optionally: keep the writer_id `"mistralai-workflows-streaming"`
      verbatim — it's a stable identifier that downstream observers may
      already key off of.

### C4. Add the Mistral component / dependency wrapper

- [ ] Create `pipelex_mistralai_workflows/dependency.py`. Before writing
      it, **read** `mistralai/workflows/plugins/mistralai` (the
      reference plugin) and mirror its dependency-component shape.
- [ ] Provide at minimum:
  - `pipelex_dependency` — a callable shaped for
    `mistralai.workflows.Depends(...)`. Body wraps
    `ensure_pipelex_booted()` (imported from `pipelex.embedding.bootstrap`)
    and returns `Pipelex.get_instance()`. This is the function previously
    living as `get_pipelex_dependency()` in
    `pipelex.plugins.mistralai_workflows.bootstrap` (deleted in Stream A,
    A4) — port it over with the Mistral-specific docstring.
- [ ] Optional: a `LibraryCrate` snapshot helper exposing
      `library_crate_dump` per-call without forcing every caller to
      hand-roll the `LibraryCrate.model_dump(...)` call. Defer if the
      reference plugin doesn't follow this pattern.

### C5. Move integration tests (layer-2 / layer-3)

For each file, move from
`_workflows/tests/integration/pipelex/plugins/mistralai_workflows/`
to `pipelex-mistralai-workflows/tests/integration/`.

- [ ] `test_activities_direct.py`
- [ ] `test_activities_offloaded.py`
- [ ] `test_activities_streaming.py`
- [ ] `test_bridge_temporal_blocking.py`
- [ ] `test_bridge_temporal_fire_and_forget.py`

For each, rewrite imports:

- `from pipelex.plugins.mistralai_workflows.bridge import ...`
  → `from pipelex.embedding.bridge import ...`
- `from pipelex.plugins.mistralai_workflows.execution_mode import ...`
  → `from pipelex.embedding.execution_mode import ...`
- `from pipelex.plugins.mistralai_workflows.activities import ...`
  → `from pipelex_mistralai_workflows.activities import ...`
- `from pipelex.plugins.mistralai_workflows.streaming import ...`
  → `from pipelex_mistralai_workflows.streaming import ...`
- `from tests.integration.pipelex.plugins.mistralai_workflows.test_data.bridge_funcs import ...`
  → `from tests.integration.test_data.bridge_funcs import ...`

### C6. Move test fixtures

- [ ] Copy
      `tests/integration/pipelex/plugins/mistralai_workflows/conftest.py` →
      `pipelex-mistralai-workflows/tests/integration/conftest.py`. The new
      conftest needs to **merge** with the existing scaffold conftest
      (which has `check_pipelex_initialized` and
      `reset_pipelex_config_fixture`). Strategy:
  - Keep the scaffold's `check_pipelex_initialized` and
    `reset_pipelex_config_fixture` (session/module-scoped Pipelex setup).
  - Add `bridge_test_library` (class-scoped) from the pipelex conftest.
  - Update its import: `from tests.integration.test_data.bridge_funcs import ...`.
- [ ] Copy
      `tests/integration/pipelex/plugins/mistralai_workflows/test_data/`
      → `pipelex-mistralai-workflows/tests/integration/test_data/`:
  - `bridge_test.mthds`
  - `bridge_funcs.py`

  Note: the same files also live in pipelex at
  `tests/integration/pipelex/embedding/test_data/` (per Stream A, A8) for
  the layer-1 bridge test. This is intentional duplication: both repos
  exercise the same fixture against different layers. If divergence
  becomes a maintenance problem later, factor into a tiny shared package;
  for v0.1.0 keep duplicated.

### C7. Verify the new repo

- [ ] In `../pipelex-mistralai-workflows/`:

      ```bash
      make install
      make agent-check
      make agent-test
      ```
- [ ] Run the layer-3 (Temporal) tests explicitly with the `temporal` extra:

      ```bash
      .venv/bin/uv sync --extra temporal --extra dev
      .venv/bin/pytest tests/integration/test_bridge_temporal_blocking.py \
                       tests/integration/test_bridge_temporal_fire_and_forget.py
      ```
- [ ] Run the streaming layer-2 test with detailed logging to verify the
      per-step `CustomTaskInProgress` event flow still asserts correctly:

      ```bash
      .venv/bin/pytest -s tests/integration/test_activities_streaming.py
      ```
- [ ] Smoke import in a fresh shell:

      ```python
      from pipelex_mistralai_workflows.activities import pipelex_run_pipe, pipelex_run_pipe_offloaded
      from pipelex_mistralai_workflows.streaming import pipelex_run_pipe_streaming
      from pipelex.embedding.bridge import PipelexPipeRunInput, PipelexPipeRunOutput, run_pipe_via_bridge
      from pipelex.embedding.execution_mode import PipelexExecutionMode
      from pipelex.embedding.bootstrap import ensure_pipelex_booted
      ```
      All six imports succeed without warnings.

### C8. First release

- [ ] Tag `v0.1.0` in `pipelex-mistralai-workflows`.
- [ ] Push the tag and create the GitHub release (use `release` skill if
      available in the new repo, else manual).
- [ ] Publish to PyPI as `pipelex-mistralai-workflows==0.1.0`.
- [ ] Coordinate timing: this PyPI release ships **together with** the
      pipelex release that drops the `[mistralai-workflows]` extra (Stream
      A, A11 / migration paragraph in CHANGELOG).

---

## Stream D — Coordinated landing & follow-ups

### D1. Coordinated land

- [ ] Land Stream A's PR on `pipelex` and ship the matching pipelex release
      (containing the `pipelex.embedding` package and the migration
      paragraph in CHANGELOG).
- [ ] On the same day, push `pipelex-mistralai-workflows==0.1.0` to PyPI
      pinning `pipelex>=NEXT` to the freshly-released pipelex version.

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

- [ ] **Version coupling.** Document the `pipelex.embedding` public surface
      as stable in pipelex docs. A breaking change to that surface is a
      breaking change for the plugin pkg.
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
3. Resolve §0 pre-decisions if not already locked. Defaults are usable.
4. Pick a stream:
   - Streams A and B are independent — run in parallel.
   - Stream C waits on both A and B.
   - Stream D waits on C.
5. After every step: `make agent-check && make agent-test` in whichever
   repo you touched.
