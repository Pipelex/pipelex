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
