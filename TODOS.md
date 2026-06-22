# Active plan — GraphSpec source paths + explicit validate graph target

> **Status: ready to start (2026-06-23).** This is a two-part Pipelex runtime graph/validation plan. Work from the Pipelex repo root (`/Users/lchoquel/repos/Pipelex/pipelex`). Start by reading the two design notes: `wip/graph/graphspec-source-map-enrichment.md` and `wip/graph/validate-explicit-graph-target.md`. Implement them in that order: source-map enrichment first, explicit graph target second.

## Cold-Start Context

Today `GraphSpec` is an execution trace for one root pipe. It has `nodes[]`, `edges[]`, `pipe_registry`, and `concept_registry`. It does not currently include the `.mthds` bundle path where each pipe or concept was declared. The path information exists elsewhere: `LibraryCrate.source_map` maps `domain.pipe_code` and `domain.ConceptCode` to source paths, `LibraryManager.get_pipe_source()` exposes pipe origins for diagnostics, and `PipeJob.library_crate` is already attached by `prepare_pipe_job()` and crosses the Temporal boundary.

Validation graph generation also has a separate root-selection constraint. The validation report graph arm currently uses `select_primary_blueprint(result.blueprints).main_pipe_ref`: first blueprint declaring `main_pipe`, else `None`. `best_effort_graph_spec(pipe_ref=None, ...)` returns `None`, so protocol/API validation succeeds without a graph when no `main_pipe` exists. CLI graph/view helpers are stricter: `dry_run_pipeline()` raises `PipelexInterpreterError("Bundle does not declare a main_pipe, cannot generate graph")` when graph output is explicitly requested and no `main_pipe` exists.

The product direction is: keep `GraphSpec` as an execution-trace artifact, but make it more useful. First, enrich existing registries with declaration source paths. Second, let callers request a graph for a specific pipe, so bundles without `main_pipe` can still validate and graph a selected pipe.

## Work Order

1. **Source-map enrichment first.** This is additive and low-risk. It uses existing `LibraryCrate.source_map` and existing free-form registry payloads. It should not change root selection or validation behavior.
2. **Explicit graph target second.** This changes validation/graph routing across direct, Temporal/API, and CLI surfaces. It benefits from the source-enriched registries once graphs can target non-`main_pipe` pipes.

## Phase 1 — Enrich GraphSpec Registries With Source Paths

Goal: when `pipe_and_concept_registry` is enabled and a `LibraryCrate.source_map` entry exists, `graph_spec.pipe_registry[pipe_ref]["source"]` and `graph_spec.concept_registry[concept_ref]["source"]` carry the source bundle path. If source is unavailable, omit the field rather than emitting `source: null`.

Implementation shape:

- In `pipelex/core/pipes/pipe_abstract.py`, add a source-aware pipe registry helper. It should start from `self.model_dump(mode="json")`, look up `library_crate.source_map.get(self.pipe_ref)`, and add `source` only when present.
- Update `_make_single_concept_data_for_registry()` and `_make_concept_data_for_registry()` to accept `library_crate: LibraryCrate | None`, look up `concept.concept_ref`, and add `source` only when present. Keep the existing `json_schema` behavior.
- In `_run_pipe_traced()`, replace `pipe_data = self.model_dump(mode="json")` and `concept_data = self._make_concept_data_for_registry()` with the source-aware helpers, passing the existing `library_crate` parameter.
- Do not add `source` to `NodeSpec`. A node is an invocation; the source path is declaration metadata, so it belongs in `pipe_registry` / `concept_registry`.
- Do not change `GraphSpec` model fields. The registries are already `dict[str, dict[str, Any]]`, and `PipeStartEvent.pipe_data` / `concept_data` already carry generic dictionaries.

Tests:

- Add focused coverage proving registry entries include `source` when a fake or real `LibraryCrate.source_map` provides entries.
- Add a direct/in-process graph test using a real `.mthds` file loaded from disk: assert the pipe registry source is the bundle path and declared concept registry source is present.
- Add or extend Temporal/event-assembled coverage so `PipeStartEvent.pipe_data` / `concept_data` with `source` survive through `GraphSpecAssembler`.
- Add a sourceless path check: raw in-memory `mthds_contents` without sources still produces a graph and omits `source`.

> **Checkpoint A — source paths in registries. DONE (2026-06-23).** Direct graph registry payloads now enrich pipes and concepts from `LibraryCrate.source_map`; event-assembled graph paths preserve `source` because `PipeStartEvent.pipe_data` / `concept_data` and `PipeEndSuccessEvent.output_concept_data` are copied unchanged by `GraphSpecAssembler`; sourceless in-memory bundle graphs still omit `source`. Edge-case decision: source enrichment uses only the executing job's active `LibraryCrate.source_map`; dependency or native entries with no source-map entry keep the previous behavior and omit `source` rather than emitting `source = null`. Verification: `CI=true .venv/bin/pytest tests/unit/pipelex/tracing/test_graphspec_assembler.py::TestGraphSpecAssembler::test_registry_source_payloads_survive_assembly tests/integration/pipelex/pipeline/test_dry_run_pipeline_graph.py::TestDryRunPipelineGraphTransport::test_graph_produced_with_tracing_disabled tests/integration/pipelex/pipeline/test_validate_graph_registry_sources.py -q` passed; `CI=true make agent-check` passed. `CI=true make agent-test` was attempted in the sandbox and reached unrelated environment failures (Temporal dev server `Operation not permitted`, restricted DNS/network HTTP tests, local HTTP server permission errors); unsandboxed rerun was rejected by approval policy because the broad suite contacts external services and starts local/networked servers.

## Phase 2 — Add Explicit Graph Target Support

Goal: callers can request graph generation for a specific pipe. The default remains unchanged: use the selected `main_pipe` when no explicit target is provided. If neither explicit target nor `main_pipe` exists, protocol/API validation should keep returning `graph_spec=None`, while CLI `--graph` / `--view` should keep failing clearly because the user explicitly requested a graph.

Implementation shape:

- Add `graph_pipe_code: str | None = None` to `pipelex/pipeline/validate_in_process.py::validate_bundles_in_process()`. Compute `graph_target_ref = graph_pipe_code or select_primary_blueprint(result.blueprints).main_pipe_ref`, then pass it to `best_effort_graph_spec()`.
- Decide how `PipelexMTHDSProtocol.validate()` exposes this. If using protocol `extra`, validate and accept only a known key such as `graph_pipe_code`; otherwise keep protocol unchanged and expose the option only on concrete API/CLI surfaces.
- Temporal path already has `DryValidateArg.pipe_code`; ensure the hosted/API dispatch layer maps the explicit graph target into it. Rename only if the surrounding API request field also uses `graph_pipe_code`; avoid churn otherwise.
- Update `pipelex/pipeline/dry_run_pipeline.py` to accept `pipe_code: str | None = None`. If provided, execute that pipe; otherwise preserve the current `main_pipe` selection and missing-main error.
- Update `pipelex/graph/graph_rendering.py` helpers (`_dry_run_bundle()`, `generate_graph_for_bundle()`, `generate_view_for_bundle()`) to accept/pass the pipe override.
- Update `pipelex/cli/agent_cli/commands/validate/bundle_cmd.py` so `validate bundle --pipe X --graph` and `--view` graph `X` instead of ignoring `--pipe` and falling back to `main_pipe`.
- Decide and document bare vs qualified target behavior. Recommended: accept both; bare targets must be unique in the loaded library; existing ambiguity errors can surface on explicit CLI graph requests and degrade on best-effort report paths.

Tests:

- Protocol/direct validation: no `main_pipe` plus explicit graph target produces non-null `graph_spec`; explicit graph target overrides declared `main_pipe`; unknown explicit target degrades to `graph_spec=None` on best-effort validation reports.
- Agent CLI: `validate bundle no_main.mthds --pipe some_pipe --view` succeeds and includes `graphspec`; `validate bundle no_main.mthds --view` still errors; `validate bundle bundle_with_main.mthds --pipe other_pipe --view` graphs `other_pipe`.
- Temporal/API path: explicit graph target maps to `DryValidateArg.pipe_code`; direct and Temporal modes agree on the target behavior.

> **Checkpoint B — explicit graph target parity.** Stop here once direct/protocol, CLI, and Temporal/API paths have consistent target selection semantics and tests pin the no-main, override, missing-target, and default-main cases. Update this checkpoint with API field decisions and exact verification.

## Non-Goals

- Do not infer a root from "the only pipe in the bundle" unless a product decision explicitly asks for that. It creates a hidden second default alongside `main_pipe`.
- Do not create a static all-pipes `GraphSpec` under the same field. That would overload an execution-trace artifact with non-execution semantics.
- Do not require `main_pipe` to validate a bundle. Current validation correctly supports concept-only files, membership-only files, and top-down partial bundles.
- Do not move declaration source onto runtime `PipeAbstract` / `Concept` models unless registry enrichment proves insufficient. The source-map already exists on `LibraryCrate`.

## Verification Guidance

Follow Pipelex repo standards: use `make agent-test`, not `make test`. For narrow iterations, run the smallest relevant pytest path through the repo's supported agent-test entrypoint if available, then run broader graph/validation coverage before handing off. Likely target areas: `tests/unit/pipelex/graph/`, `tests/integration/pipelex/pipeline/`, `tests/integration/pipelex/temporal/`, and agent CLI validate tests. If implementation touches hosted API request mapping, also update and verify the matching `../pipelex-api` surface in a separate repo change.

## Files Likely To Touch

- `pipelex/core/pipes/pipe_abstract.py`
- `pipelex/pipeline/validate_in_process.py`
- `pipelex/pipeline/runner.py`
- `pipelex/pipeline/dry_run_pipeline.py`
- `pipelex/graph/graph_rendering.py`
- `pipelex/cli/agent_cli/commands/validate/bundle_cmd.py`
- `pipelex/temporal/tprl_pipe/act_dry_validate.py` only if field naming changes
- tests under `tests/unit/pipelex/graph/`, `tests/integration/pipelex/pipeline/`, `tests/integration/pipelex/temporal/`, and agent CLI validate coverage
- hosted API validate request/dispatch mapping in `../pipelex-api` if this is exposed over the public API

## Definition Of Done

- `GraphSpec.pipe_registry` and `GraphSpec.concept_registry` include `source` when a source-map entry exists and omit it when not available.
- Source enrichment works through direct in-memory graphs and event-assembled Temporal graphs.
- Validation can graph an explicit pipe target without `main_pipe`.
- Default validation behavior stays unchanged when no explicit target is provided.
- CLI `validate bundle --pipe X --graph/--view` graphs `X`.
- Tests pin source enrichment, no-main explicit target, target-overrides-main, missing target degradation/error behavior, and direct/Temporal parity.
