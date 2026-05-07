# Mistral Workflows ↔ Pipelex — Plugin Extraction TODOS

## Status

Streams A, B, C **complete and verified**. Both repos green:

- `pipelex-mistralai-workflows`: `make agent-check` clean, `make agent-test`
  passes (8 tests: 3 layer-2 Mistral activity, 2 layer-3 Temporal, 2
  fundamentals, 1 dry-run-all).
- `pipelex` (`_workflows/`): `make agent-check` clean (pyright + mypy
  across 1708 source files), `make agent-test` passes, all 4 §A11
  `git grep` invariants satisfied.

**Stream D** (coordinated landing & PyPI publish) is the only remaining
stream. See §Stream D below.

## Gotcha to remember

Mistral's `get_effective_task_queue()` returns `worker.deployment_name`
(not `temporal.task_queue`) whenever `deployment_name` is set and doesn't
match the configured task queue. Any `DEPLOYMENT_NAME=...` in `.env`
silently routes activities to that deployment name; an in-process test
worker polling `TEST_TASK_QUEUE` then hangs forever. The
`override_mistralai_task_queue` fixture in all 3 layer-2 test files
clears `mistralai_config.worker.deployment_name = None` to make the test
environment deterministic regardless of host env vars. Leave it in place
even if Mistral relaxes the routing rule in a future release.

---

## End state delivered

### `_workflows/` (pipelex)

- New `pipelex/runtime_bridge/` package: `bridge.py`, `bootstrap.py`
  (`ensure_pipelex_booted` only — `get_pipelex_dependency` removed),
  `execution_mode.py`, `exceptions.py` (`PipelexRuntimeBridgeError` base +
  `MissingPipelexTemporalExtraError` + `PipelexBridgeRuntimeError`).
  `MistralWorkflowsNotInstalledError` deleted entirely. Library-id prefix
  is `runtime_bridge_`. Install hint reads `pip install 'pipelex[temporal]'`.
- `pipelex/plugins/mistralai_workflows/` deleted.
- `tests/{unit,integration}/pipelex/runtime_bridge/` populated with the
  layer-1 tests + `conftest.py` + `test_data/` (domain string
  `mistralai_workflows_bridge_test` and function name
  `mistralai_workflows_bridge_echo` kept verbatim across both repos).
  `tests/{unit,integration}/pipelex/plugins/mistralai_workflows/` deleted.
- `pyproject.toml`: `mistralai-workflows` extra removed; the
  `[[tool.mypy.overrides]]` block for `mistralai.workflows.*` removed.
- `docs/under-the-hood/mistralai-workflows-{plugin,recipes}.md` deleted;
  the four matching `mkdocs.yml` lines removed.
- `CHANGELOG.md` `[Unreleased]` rewritten as a single Changed bullet
  describing the migration.

### `pipelex-mistralai-workflows/`

- Starter content stripped (`hello_world.{py,mthds}`, `tests/test_pipelines/`,
  `tests/e2e/test_pipelex_mistralai_workflows.py`).
- `pyproject.toml`: `version = "0.1.0"`, slim deps
  (`pipelex>=0.27.0` + `mistralai-workflows>=3.3.0`), `[temporal]` extra
  (`pipelex[temporal]>=0.27.0`), pruned markers (`gha_disabled`,
  `dry_runnable`, `temporal`), mypy override for `mistralai.workflows.*`,
  `pythonpath = ["tests"]` under `[tool.pytest]` so the
  `from integration.test_data.bridge_funcs import ...` import resolves at
  runtime (project rule forbids `tests/__init__.py`).
- `[tool.uv.sources] pipelex = { path = "../_workflows", editable = true }` —
  **dev-only override**. Strip before publishing v0.1.0; re-add at the
  start of the next dev cycle when the next breaking change to
  `pipelex.runtime_bridge` lands.
- `README.md`, `CLAUDE.md`, `CHANGELOG.md` rewritten.
- `pipelex_mistralai_workflows/` package: `activities.py` (with
  `pipelex_run_pipe` + `pipelex_run_pipe_offloaded`), `streaming.py`
  (`pipelex_run_pipe_streaming` + `PipelexPipeRunStreamingState`),
  `streaming_event_forwarder.py` (writer_id
  `"mistralai-workflows-streaming"` kept verbatim), `dependency.py`
  (single `pipelex_dependency()` callable shaped for
  `mistralai.workflows.Depends(...)`).
- `tests/integration/`: 5 layer-2/3 test files + merged `conftest.py`
  (scaffold's `check_pipelex_initialized` + `reset_pipelex_config_fixture`
  plus `bridge_test_library` class-scoped fixture from pipelex) + copied
  `test_data/` (`bridge_test.mthds` + `bridge_funcs.py`).
- CI (`tests-check.yml`) already runs `make install` →
  `uv sync --all-extras`, which installs the `[temporal]` extra. No edits
  needed.
- `uv.lock` refreshed; `mistralai-workflows==3.4.0` resolved.

## Decisions locked (do not re-derive)

- **§0.1.** Framework-agnostic core lives at `pipelex.runtime_bridge.*`
  (the earlier `pipelex.embedding` proposal was rejected).
- **§0.2.** Split assignments: `bridge.py`, `execution_mode.py`,
  `bootstrap.py::ensure_pipelex_booted`, agnostic exceptions live in
  `pipelex.runtime_bridge`. `activities.py`, `streaming.py`,
  `streaming_event_forwarder.py`, the Mistral-shaped dependency wrapper
  live in `pipelex_mistralai_workflows`.
  `MistralWorkflowsPluginError` + `MistralWorkflowsNotInstalledError`
  deleted entirely.
- **§0.3.** New repo version is `0.1.0`.
- **§0.4.** New repo pins `pipelex>=0.27.0`; editable `[tool.uv.sources]`
  override for local dev (strip before publish, re-add on next dev cycle).
- **§0.5.** Mistral dependency wrapper is `pipelex_dependency()` — boots
  Pipelex, returns the singleton, designed for `Depends(pipelex_dependency)`.
  No `LibraryCrate` snapshot helper added (deferred, revisit after first
  user feedback).
- **§0.6.** Cookbook entry deferred until after PyPI publish.

## Reference docs (consult before touching Mistral-facing code)

- `.claude/skills/workflows/SKILL.md` and especially:
  - `references/guides/workflows-plugins.mdx` — plugin contract.
  - `references/guides/dependency-injection.mdx` — `Depends(...)` shape.
  - `references/guides/streaming.mdx` +
    `references/guides/streaming-consumption.mdx` — Task API,
    `update_state`, event subscription.
  - `references/guides/handling-large-data.mdx` — `OffloadableField` and
    the offloading interceptor (relevant to D3's import-drift risk).
- Mistral docs: <https://docs.mistral.ai/studio-api/workflows/building-workflows/plugins>

---

## Stream D — Coordinated landing & follow-ups

### D1. Coordinated land

- [ ] Strip the `[tool.uv.sources]` editable override from
      `pipelex-mistralai-workflows/pyproject.toml` so PyPI builds resolve
      `pipelex` from PyPI.
- [ ] Land Stream A's PR on `pipelex` and ship the matching pipelex
      release (the one that introduces `pipelex.runtime_bridge` and the
      `[Unreleased]` migration paragraph).
- [ ] Tag `v0.1.0` in `pipelex-mistralai-workflows`, push the tag, create
      the GitHub release, publish to PyPI as
      `pipelex-mistralai-workflows==0.1.0` pinning `pipelex>=0.27.0`
      (or whichever pipelex version actually ships).
- [ ] Re-add the `[tool.uv.sources]` override at the start of the next
      dev cycle when the next breaking change to `pipelex.runtime_bridge`
      lands.

### D2. Cookbook entry (deferred)

- [ ] In `pipelex-cookbook/`, create
      `examples/c_advanced/mistral-workflows/`:
  - Tier-1 DIRECT-mode worker script (using `pipelex_run_pipe` from the
    new package).
  - Tier-2 typed activity exercising `library_crate_dump`.
  - README pointing back at the new repo's docs.
- [ ] Update `mistral-workflows-sub-module.md` §Status board to check off
      the deferred Phase 1.3 cookbook entry.

### D3. Watch the open risks

- **Version coupling.** Document the `pipelex.runtime_bridge` public
  surface as stable in pipelex docs. A breaking change to that surface is
  a breaking change for `pipelex-mistralai-workflows`.
- **OffloadableField import drift.** `pipelex_mistralai_workflows/activities.py`
  imports `OffloadableField, OffloadableModel` from
  `mistralai.workflows.core.encoding.fields_offloader`. If a Mistral
  upgrade moves the path, fix in the plugin pkg.
- **CI test parity.** Layer-2/3 tests now run only in
  `pipelex-mistralai-workflows` CI. Make sure both repos' matrices are
  green before flipping the switch.

### D4. Workspace docs

- [ ] Update root workspace `CLAUDE.md`'s repository table to include
      `pipelex-mistralai-workflows/` (PyPI: `pipelex-mistralai-workflows`,
      Python package: `pipelex_mistralai_workflows`).

---

## Resume guide

1. Read **§Status** + **§Gotcha to remember** above. That's the whole
   in-flight context.
2. The next concrete actions are all in §Stream D. D1 is the gate;
   D2/D3/D4 follow.
3. After any further code change: `make agent-check && make agent-test`
   in whichever repo you touched. Note: `make cleanderived` deletes
   `tests/integration/pipelex/fixtures/_generated_model_sets.py`; run
   `make rtm` after `cleanderived` or pyright will fail.
