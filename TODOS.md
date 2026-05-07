# Mistral Workflows ↔ Pipelex — Plugin Extraction TODOS

## Status

Streams A, B, C **complete and verified**. Both repos green:

- `pipelex-mistralai-workflows`: `make agent-check` clean, `make agent-test`
  passes (layer-2 Mistral activity, layer-3 Temporal, fundamentals,
  dry-run-all).
- `pipelex` (`_workflows/`): `make agent-check` clean (pyright + mypy
  across the source tree), `make agent-test` passes, all §A11
  `git grep` invariants satisfied.

Release/landing is **not** in scope for now. The dev-only
`[tool.uv.sources]` editable override in
`pipelex-mistralai-workflows/pyproject.toml` stays in place; both repos
are usable side-by-side via that override.

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
  **dev-only override**. Strip if/when publishing to PyPI.
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
  override for local dev (strip if/when publishing).
- **§0.5.** Mistral dependency wrapper is `pipelex_dependency()` — boots
  Pipelex, returns the singleton, designed for `Depends(pipelex_dependency)`.
  No `LibraryCrate` snapshot helper added (deferred, revisit after first
  user feedback).
- **§0.6.** Cookbook entry deferred.

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

## Open risks to watch

- **Version coupling.** A breaking change to the `pipelex.runtime_bridge`
  public surface is a breaking change for `pipelex-mistralai-workflows`.
- **OffloadableField import drift.** `pipelex_mistralai_workflows/activities.py`
  imports `OffloadableField, OffloadableModel` from
  `mistralai.workflows.core.encoding.fields_offloader`. If a Mistral
  upgrade moves the path, fix in the plugin pkg.
- **CI test parity.** Layer-2/3 tests now run only in
  `pipelex-mistralai-workflows` CI. Keep both repos' matrices green.

---

## Resume guide

1. Read **§Status** + **§Gotcha to remember** above. That's the whole
   in-flight context.
2. After any further code change: `make agent-check && make agent-test`
   in whichever repo you touched. Note: `make cleanderived` deletes
   `tests/integration/pipelex/fixtures/_generated_model_sets.py`; run
   `make rtm` after `cleanderived` or pyright will fail.
