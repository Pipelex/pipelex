# Mistral Workflows ↔ Pipelex — Plugin Extraction TODOS

> **The current merge decision lives in [`wip/mistral-workflows-merge-readiness.md`](wip/mistral-workflows-merge-readiness.md)** — the cold-start assessment of whether `feature/Mistral-workflows-merge-4` is safe to PR into `dev`, and the recommended split. This TODOS file records the earlier plugin-extraction milestone (Streams A/B/C); work continued past it — the `runtime_bridge.primitives` lift and the `MISTRAL_NATIVE` execution mode — and the §End state below was refreshed 2026-06-03 to match the live tree. Use the readiness doc, not this file, as the merge basis.

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

- New `pipelex/runtime_bridge/` package: `bridge.py` (boundary types + `run_pipe_via_bridge` dispatch), `bootstrap.py` (`ensure_pipelex_booted` only — `get_pipelex_dependency` removed), `execution_mode.py` (`PipelexExecutionMode` — `DIRECT`, `TEMPORAL_BLOCKING`, `TEMPORAL_FIRE_AND_FORGET`, `MISTRAL_NATIVE`), `exceptions.py` (`PipelexRuntimeBridgeError` base + `MissingPipelexTemporalExtraError` + `PipelexBridgeRuntimeError` + `MissingMistralWorkflowsPluginError`), and a `primitives/` subpackage (`delivery`, `graph_assembly`, `hydration`, `pipe_classification`, `submitter_hydration`, `trace_flush`, `pipe_run_arg`) — framework-agnostic helpers lifted out of `pipelex.temporal` so both the Temporal path and the Mistral-native path share them. The old `MistralWorkflowsNotInstalledError` was deleted; the new `MissingMistralWorkflowsPluginError` is what the `MISTRAL_NATIVE` dispatch raises (via deferred import of `pipelex_mistralai_workflows`) when that package is absent. Library-id prefix is `runtime_bridge_`. Install hint reads `pip install 'pipelex[temporal]'`.
- `pipelex/temporal/tprl_pipe/*` activities (`act_assemble_graph`, `act_deliver`, `act_flush_trace_events`) rewired to thin `@activity.defn` wrappers delegating to `runtime_bridge.primitives` — behavior-neutral lift, body moved verbatim into the primitives.
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

---

# TODOS — Recap

## Summary

Two adjacent refactors landed on feature branches:

- **`temporal-primitives`** — overhauled how Pipelex maps its identity model onto Temporal's identifier and observability primitives. Fixed the activity-id collision bug, deleted the worker-singleton LRU, dropped the `wfid` parameter across protocols, switched to typed search attributes, and made the namespace bootstrap hard-fail with a `pipelex setup-temporal-namespace` CLI. Phases 1–6 shipped; only the `WorkflowExecutionError → ApplicationError` revamp remains deferred.
- **`text-then-object`** — reintroduced the removed `structuring_method = preliminary_text` capability as a build-time elaboration. Added a first-class `PipeStructure` operator, a bundle-level elaboration pass that rewrites `preliminary_text` PipeLLMs into `PipeSequence(PipeLLM(text), PipeStructure)`, and removed `structuring_method` from the runtime `PipeLLM`. All ten phases complete.

---

## `wip/temporal-primitives/`

See `00-temporal-id-primitives.md`, `01-id-and-naming-design.md`, `02-id-and-naming-plan.md`, `03-temporal-error-handling-revamp.md`.

### What landed (Phases 1–6 on `feature/Temporal-ids`)

- **Phase 1 — Foundations.** New `pipelex/temporal/tprl/observability.py` with five helpers (`build_search_attributes`, `build_search_attributes_for_child`, `build_static_summary`, `build_static_details`, `build_activity_summary`). `TemporalManager.make_top_workflow_id` simplified to `{env_prefix}{pipeline_run_id}`. `WorkflowExecutor` entry points (top-level + child variants) gained additive `search_attributes`, `static_summary`, `static_details`, `memo` kwargs.
- **Phase 2 — Activity-layer rewrite.** Deleted `_seen_activity_ids` LRU, `_MAX_SEEN_RUNS`, `_record_activity_id`, and the `is_replaying()` short-circuit from `ContentGeneratorInWorkflow`. Stopped passing `activity_id=` on every `workflow.execute_activity(...)` call (SDK now assigns deterministic integers). Dropped `wfid` from `ContentGeneratorProtocol` and both other implementations. Every dispatch now carries a `summary=build_activity_summary(...)`. The TDD gate in `test_default_activity_id_collision_bug.py` flipped green.
- **Phase 3 — Workflow-layer rewrite + protocol cleanup.** Top-level Workflow ID is now `{env_prefix}{pipeline_run_id}`. Child Workflow IDs use slash-separated paths (`{parent}/pipe-router` for the fixed-role child, `{parent}/{pipe_code}-{workflow.uuid4()[:8]}` for dynamic children). `wfid` removed from `PipeRunProtocol`, `PipeRouterProtocol`, `PipeRun`, `PipeRouter`, `DryPipeRouter`, `TemporalPipeRun`, `TemporalPipeRouter`. Search attributes and static summary/details now populate on every workflow start.
- **Phase 4 — Deployment hooks, docs, CHANGELOG.** Namespace bootstrap soft-fail check added (catches `RPCError`, warns with the registration command). New `docs/under-the-hood/temporal-deployment.md`. `[Unreleased]` CHANGELOG entry covers all breaking changes including the new pipeline-run-chain semantics.
- **Phase 5 — TypedSearchAttributes migration.** Switched from `Mapping[str, list[str]]` to `TypedSearchAttributes` everywhere. Five `SearchAttributeKey` module constants in `observability.py`. Zero `DeprecationWarning: Dictionary-based search attributes are deprecated` lines remain. Two follow-ups landed in the same window:
    - **Child-spawn unification reverted** (commit `ac8e2335`): briefly routed `wf_pipe_run.py` through `WorkflowExecutor.execute_child_workflow`, then reverted because the factory bakes config values into the recorded `StartChildWorkflowExecution` command and breaks replay determinism. Both child paths now call `workflow.execute_child_workflow(...)` directly.
    - **Session-id determinism fix** (same commit): `build_search_attributes` and `build_static_details` no longer read `get_temporal_manager().session_id` at workflow runtime. New `stamp_submitter_session_id(pipe_job)` helper stamps it onto `JobMetadata.session_id` at the submitter boundary; helpers stay pure functions of workflow input.
    - **Pre-Phase-6 cleanup**: tightened exception handling in `workflow_caller.py` (replaced `except Exception` with named SDK exceptions on all four entry points). Added `tests/integration/pipelex/temporal/test_wf_pipe_run_failure_path.py`. Discovered + fixed a latent prod bug — `WorkflowExecutionError` re-raised inside a workflow caused infinite task retry; fixed by registering it in `workflow_failure_exception_types=[WorkflowExecutionError]` on `make_worker`.
- **Phase 6 — Hard-fail worker boot + configurable attributes + CLI.** Three intertwined deliverables (latest commit `c89674f5`):
    - New `[temporal.search_attributes]` config block with master `enabled` toggle and `attributes` subset selector.
    - Worker boot now **hard-fails** on a reachable namespace when configured attributes are missing (raises `SearchAttributeRegistrationError`). Soft-fail kept only for unreachable namespaces (`RPCError`).
    - New `pipelex setup-temporal-namespace` CLI command that wraps `ensure_required_search_attributes_registered`, honors `--server <profile>`, supports `--dry-run`. Follows the `worker_cmd` deferred-import pattern so the `temporal` extra stays optional.
    - `REQUIRED_SEARCH_ATTRIBUTES` renamed to `BUILTIN_SEARCH_ATTRIBUTES` and moved to `pipelex/temporal/config_temporal.py` (under `TYPE_CHECKING`-guarded temporalio import) so the config validator can reference it without the temporal extra.

### What remains deferred

- **`03-temporal-error-handling-revamp.md` — `WorkflowExecutionError → ApplicationError`.** Currently `WorkflowExecutionError(PipelexError)` is registered in `workflow_failure_exception_types` to make Temporal treat it as a terminal failure. The cleaner final form is to make it subclass `temporalio.exceptions.ApplicationError` so the worker-side registration becomes redundant. Not done because: scope creep beyond Phase 5 cleanup, `ApplicationError.__init__` signature is incompatible with `PipelexError`, and the line between "raised inside a workflow" exceptions and the rest of the `TemporalFlowError` hierarchy needs design work. Estimated 1–2 hours. Triggers to revisit: a second-time encounter of the "I forgot to register my new exception" footgun, or a Phase 7+ holistic error-model cleanup.

---

## `wip/text-then-object/`

See `text-then-object-plan.md` and `PR-text-then-object.html`.

### What landed (all ten phases on `feature/Text-then-object`)

- **Phase 1 — Bundle-level elaboration metadata.** Added `StepRole`, `ElaborationMetadata`, and `elaboration_metadata: dict[str, ElaborationMetadata] | None = Field(default=None, exclude=True)` side-table to `PipelexBundleBlueprint`. The side-table is internal — does not leak onto the per-pipe surface or runtime `PipeAbstract`. Accessor `get_elaboration_for(pipe_code)` added.
- **Phase 2 — `PipeStructure` operator.** New `pipelex/pipe_operators/structure/` package with blueprint, factory, runtime operator. Registered in `PipeBlueprintUnion`, `PipeType.PIPE_STRUCTURE`, `CoreRegistryModels.PIPE_OPERATORS{,_FACTORY}`, `output_renderer._collect_possible_outputs`, and `mthds_schema_generator._PIPE_DEFINITION_NAMES`. New `structuring_prompt` template under `[cogt.llm_config.generic_templates]`. Validates Text-compatible input + structured output. Regenerated `derived/mthds_schema.json`.
- **Phase 3 — `PipeStructureSpec`.** Authoring-layer counterpart at `pipelex/builder/pipe/pipe_structure_spec.py`, registered in `pipe_spec_union.py` and `pipe_spec_map.py`.
- **Phase 4 — Bundle elaboration framework.** New `pipelex/core/interpreter/bundle_elaborator.py` with `BundleElaborator.elaborate()`. Fast-path short-circuit when no `preliminary_text` directive present. Recursive-elaboration guard. Post-elaboration `model_validate` re-run. `BundleElaboratorError(PipelexInterpreterError)`. Wired into `PipelexInterpreter.make_pipelex_bundle_blueprint`. Uses `TypeGuard[PipeLLMBlueprint]` so callers narrow without casts.
- **Phase 5 — `preliminary_text` elaboration.** Synthesizes step-1 (`<code>__draft_text` PipeLLM, output always literal `Text`), step-2 (`<code>__structure` PipeStructure, original output preserved with multiplicity), and replaces the original `<code>` with a `PipeSequence` wrapping both. `elaboration_metadata` populated. Image inputs naturally flow only to step-1.
- **Phase 6 — Removed `structuring_method` from runtime PipeLLM.** Field, validator, `NotImplementedError` block, and `execution_data_dict` line all gone from `PipeLLM`. Factory no longer forwards it. Authoring-time `model_validator(mode="after")` on `PipeLLMBlueprint` rejects `preliminary_text + Text output` before the elaborator runs. Added `StructuringMethod.is_preliminary_text` `@property`. `PipeLLMSpec.structuring_method` exposed as plain `Field` (not `SkipJsonSchema`) so AI builders see it in the JSON schema.
- **Phase 7 — Skipped per plan.** All trace/log/CLI/graph-viewer integration deferred to follow-up TODOs.
- **Phase 8 — Round-out tests.** Kajson round-trip for `PipeStructureBlueprint` + elaborated bundles. End-to-end interpreter test from `.mthds` source. Hand-authored `PipeSequence` wrapping `PipeStructure`. `PipeBatch` iterating `PipeStructure` over three texts. Full e2e (`preliminary_text_e2e.mthds`) parametrized over all three multiplicity forms (`RestaurantReview`, `RestaurantReview[]`, `RestaurantReview[2]`), with assertion that **exactly two LLM calls** are issued in live mode. Inline-structure variant (`HikingTripReport`, 12 fields, no Python class) covers the inline-concept path.
- **Phase 9 — Documentation & changelog.** New `docs/building-methods/pipes/pipe-operators/PipeStructure.md` and `docs/under-the-hood/build-time-elaboration.md`. Updated `PipeLLM.md` (`structuring_method` section, parameters table). Relinked dangling references to the deleted `llm-structured-generation-config.md`. `mkdocs.yml` + nav + redirects updated. `[Unreleased]` CHANGELOG entry.
- **Phase 10 — Final validation.** `make agent-check`, `make agent-test`, `make docs-check` all clean.

### Code-quality decisions worth noting

- No premature error types: `pipe_operators/structure/exceptions.py` deleted — no call site distinguished from generic `PipeRunError`/`ValidationError`.
- No speculative `try/except`: `pipe_structure.py` does not wrap `make_object` — the cogt layer wraps any underlying `ValidationError` in `LLMCompletionError`.
- `QualifiedRef.parse(...).local_code` consolidated across three call sites instead of inline `split(".")`.
- `StructuringMethod.is_preliminary_text` property added so call sites read as `method.is_preliminary_text` (project rule: never `==` against an enum value).
- `TypeGuard[PipeLLMBlueprint]` on `_is_preliminary_text_pipe` eliminates a `# type: ignore[arg-type]`.

### What remains as follow-up TODOs (out of scope for this PR)

1. **plxt schema sync.** `vscode-pipelex/crates/taplo-common/schemas/mthds_schema.json` is from before this PR — authoring `type = "PipeStructure"` directly in a `.mthds` file fails plxt validation. Regenerate via `pipelex-dev generate-mthds-schema` and ship a `pipelex-tools` release. The `preliminary_text` path is unaffected because the synthesized `PipeStructure` lives in-memory only.
2. **Synthetic-pipe marker on graph nodes + CLI listing exclusion.** When emitting `NodeSpec`, look up `bundle.elaboration_metadata` and set `tags["synthetic"] = "true"` + `tags["parent_pipe_code"] = parent`. Requires either a runtime-only field on `PipeAbstract` or a side-registry keyed by pipe code. Also hide synthetic pipes from `pipelex list`. ~2–3 file edits.
3. **Friendly synthetic-pipe rendering across logs/traces/run-reporting.** After (2), render `<parent_pipe_code> [<step_role_label>]` everywhere `self.code` appears. Touches graph_tracer, run_reporting, journal, distributed-tracing. ~5–8 file edits.
4. **`mthds-ui` graph viewer integration.** After (2), decide in the UI repo whether to nest synthetic pipes under their parent or hide them.
5. **Bundle-load benchmark in CI.** Microbenchmark library load time; alert on >5% regression. Protects future elaboration-pass additions.
6. **PipeStructure image input support.** v1 takes Text only; extend when a concrete need arises.
7. **Per-step prompt customization for `preliminary_text`.** Don't build until requested.
8. **Generic meta-pipe / build-time elaboration framework.** Promote `BundleElaborator._elaborate_preliminary_text` into a plugin registry when a SECOND elaboration directive appears.
9. **`pipelex-dev elaborate-bundle <path>`** debugging CLI to print the elaborated form without running.
10. **Revisit `StructuringMethod.DIRECT`.** Functionally identical to `None`. Delete if no second method materializes.
11. **Persist `elaboration_metadata` into MTHDS/JSON exports.** Today `Field(exclude=True)` drops it on every `model_dump`. When a cross-boundary consumer materializes (graph viewer over a serialized bundle, Temporal payload, persistent cache), flip `exclude=False`, regenerate the schema, ship a plxt bump. The regression test at `test_elaboration_metadata.py::test_bundle_round_trip_drops_elaboration_metadata` flips first.
