# Keyword-only refactor — positional-subject ABUSE suspects (consolidated)

> **RESOLVED (2026-06-15).** All 59 suspects — high-confidence, med/low, the public-API pair (`Pipelex.make`/`setup`), and the "decide as a family" clusters (`pipe_controllers` `_*_controller_pipe` family, the eight `graph` `GraphTracerManager` `lookup_key` dispatch methods) — were applied as **fully keyword-only** by relocating the bare `*` to immediately after `self`/`cls` (no reordering). Sibling/override sets were flipped consistently (e.g. `StuffContent.rendered_markdown` base + all subclass overrides; `PipeController._*_controller_pipe` base + overrides). Two convention boundaries were deliberately **left untouched** as out-of-scope: the broader `PipeAbstract._live_run_pipe`/`_dry_run_pipe` `job_metadata`-first convention (not among the suspects), and `GraphTracerProtocol`/`GraphTracer` (`node_id`-first, a different class). Positional call sites — production (`plugins/*_config.py` → `get_reasoning_level_str`, `check_rules_sync_cmd.py` → `build_merged_rules`) and tests — were converted to keyword; temporal `test_worker_cli.py` mock assertions were rewritten from `.call_args.args[0]` to `.call_args.kwargs[...]`. `make agent-check` (ruff, pyright 0 errors, mypy clean, `check-keyword-only` PASSED) and `make agent-test` both green. Public-API break (`Pipelex.make`/`setup` now keyword-only after the subject) is folded into the already-breaking refactor branch; downstream impact tracked in [`downstream-consumer-breakage.md`](downstream-consumer-breakage.md).

Consolidated shortlist from the positional-subject audit ([`audit/positional-subject-audit.md`](audit/positional-subject-audit.md)). The question for every entry: *was the first arg genuinely the semantic object of the call, or was it kept positional merely to satisfy Exception 1 ("the subject may stay positional"), when the call would actually read better with that arg keyworded too?*

## How this was produced

- **Population reviewed:** 1140 of the 1806 audited functions — the 797 `SUBJECT_THEN_KEYWORDS` entries (`def f(subject, *, …)`, where the subject choice was actually made) plus 343 **primitive-typed** lone subjects (`def f(x: bool/int/str/float)`, which read opaquely at the call site). The remaining ~660 non-primitive lone subjects and the symmetric-allowlist/variadic entries were filtered out mechanically (no LLM) — a single positional param with a domain type offers no subject to abuse.
- **Method:** one **Sonnet 4.6** sub-agent per package (25 agents), each with Read+Grep, instructed to open the function body and a call site or two whenever the signature alone was ambiguous, to **default to "fine" and emit only suspects**, and to cite the rubric in `docs/contribute/keyword-only-arguments.md`. Per-package shortlists live in [`audit/findings/<package>.md`](audit/findings/).
- **Calibration was healthy:** every package came back with a short list (0–5 suspects); no agent rubber-stamped or over-flagged.

## Summary

- **Total reviewed:** 1140 entries (797 Section A + 343 primitive lone-subjects).
- **Total suspects: 59** — **31 high-confidence**, 28 medium/low.
- **Zero-suspect packages:** `base_exceptions`, `errors`, `hub`, `language`, `pipe_signature`, `tracing`.
- The suggested fix is **almost always the same**: move the `*` before the subject too (make the signature *fully* keyword-only). A handful suggest *reordering* so a different arg becomes the positional subject.

| Package | High | Med/Low | Total |
| --- | ---: | ---: | ---: |
| `temporal` | 4 | 1 | 5 |
| `pipe_controllers` | 3 | 2 | 5 |
| `builder` | 3 | 1 | 4 |
| `cli` | 3 | 1 | 4 |
| `tools` | 3 | 1 | 4 |
| `pipe_operators` | 2 | 2 | 4 |
| `plugins` | 1 | 3 | 4 |
| `system` | 1 | 3 | 4 |
| `libraries` | 1 | 3 | 4 |
| `cogt` | 2 | 1 | 3 |
| `core` | 2 | 1 | 3 |
| `pipe_run` | 2 | 1 | 3 |
| `pipelex` | 1 | 2 | 3 |
| `observer` | 2 | 0 | 2 |
| `kit` | 1 | 1 | 2 |
| `graph` | 0 | 1 | 1 |
| `pipeline` | 0 | 1 | 1 |
| `reporting` | 0 | 1 | 1 |
| `runtime_bridge` | 0 | 1 | 1 |
| **Total** | **31** | **28** | **59** |

## Cross-cutting patterns (for adjudication)

The 59 suspects collapse into a small number of recurring shapes. A near-universal tell: **the existing call sites already pass the "positional" arg by keyword**, which means the positional permission is buying nothing today — exactly the signal that Exception 1 was leaned on mechanically.

1. **Lookup-table / registry / config carried positional while the real query is keyworded.** The strongest cluster. The positional arg is a deck/map/dict you read *out of*, and the keyword arg is what you're looking up.
   - `builder` `_resolve_preset_backend(model_deck, *, model_handle, …)` · `cogt` `model_cost_per_token(costs, *, cost_category)` · `cogt` `get_reasoning_level_str(effort_to_level_map, *, effort)` · `tools` `apply_tag_style(context, *, value, …)` · `kit` `_read_agent_file(agents_dir, *, name)`.

2. **`*_for_pipe` / `*_from_response` / `*_from_uri` — the name advertises the operand, but a *different* arg is positional.** The function name itself says which arg is the object, and it isn't the positional one.
   - `builder` `build_output_for_pipe(mthds_contents, *, pipe_code, …)` · `builder` `build_runner_code_for_pipe(mthds_contents, *, pipe_code)` · `plugins` `make_extract_output_from_response(inference_model, *, response)` · `plugins` `make_mistral_document_url_chunk_from_uri(mistral_client, *, uri)` · `tools` `detect_jinja2_required_variables(template_category, *, template_source)` (+ `detect_jinja2_variable_references`).

3. **Mode flag / bare bool carried positional** — `f(True)` reveals nothing, and every call site already keywords it.
   - `cli` `build_run_output(with_memory, *, …)` · `cli` `determine_needs(reset, *, …)` · `temporal` `run_worker(is_not_sandboxed, *, …)` · `system` `update_service_terms_acceptance(accepted, …)` · `system` `update_inference_setup_completed(completed, …)` · `system` `check_is_initialized(print_warning_if_not=…)` · `core` `rendered_markdown(level=1, *, is_pretty=…)` (+ async twin).

4. **`task_queue` positional on Temporal factories** — a defaulted config option, not "the thing being made". Three parallel sites.
   - `temporal` `create_executor` · `make_temporal_pipe_router` · `make_temporal_pipe_run`.

5. **Trace/provenance context carrier positional** (`job_metadata`, `lookup_key`, `calling_pipe_code`) while the function acts on the stuffs/outputs in the keyword args.
   - `pipe_controllers` `_register_branch_outputs_with_graph_tracer`, `_register_parallel_combine_with_graph_tracer`, `sub_pipe.run_pipe(calling_pipe_code, …)` · `graph` `on_pipe_end_success(lookup_key, …)` and 7 sibling dispatch methods.

6. **Accumulator/sink dict carried positional** while the content being added is keyworded.
   - `pipe_run` `_try_add_rendered_file(files, *, filename, …)` · `_add_optional_text_file(files, *, …)`.

7. **Symmetric / directional pair arbitrarily split across the `*`** — neither operand is "the subject", so a positional+keyword split is just noise.
   - `pipe_operators` `_expects_type(expected_type, *, target_type)` · `plugins` `make_nb_tokens_by_category_from_nb(nb_input, *, nb_output)` · `libraries` `compute_fingerprint_from_content(concepts, *, pipes)` · `pipe_run` `output_multiplicity_to_apply(base, *, override)` · `pipeline` `copy_with_update(otel_context, *, trace_context, …)`.

8. **Public-API surface** — already known to be keyword-breaking from the refactor; worth a deliberate call.
   - `pipelex` `Pipelex.make(integration_mode=…, *, …)` and `Pipelex.setup(integration_mode, *, …)`.

**Note on conventions:** several med/low entries are deliberate codebase-wide conventions (e.g. `job_metadata` as the first param on the whole run-pipe family in `pipe_controllers`; the `lookup_key` dispatch discriminant across the eight `GraphTracerManager` methods). Those should be decided *as a family* — fix the base/convention or leave it, don't pick off one site.

---

## Suspects by package (ordered by confidence)

### `temporal` (4 high · 1 med/low)

**High**

- `pipelex/temporal/task_manager.py:36` — `TaskManager.run_worker` — `async def run_worker(self, is_not_sandboxed: bool, *, is_unit_testing: bool, ...)` — `is_not_sandboxed` is a boolean flag that reads opaquely positionally: `run_worker(True)` reveals nothing. It's not the semantic object the method acts on; the worker it launches is. Both real call sites already pass it as `is_not_sandboxed=...`. The `temporal_task_manager.py` override (which carries `@override` and is thus skip-exempt) would track automatically once the Protocol base is fixed. Suggested fix: make the signature fully keyword-only — `async def run_worker(self, *, is_not_sandboxed: bool, is_unit_testing: bool, ...)`.
- `pipelex/temporal/tprl/workflow_caller.py:298` — `WorkflowExecutorFactory.create_executor` — `def create_executor(cls, task_queue: str | None = None, *, workflow_execution_timeout, retry_policy, ...)` — `task_queue` is one of many configuration options for the executor being created; `create_executor` doesn't designate it as the subject (no "for this queue" semantic). All four existing call sites pass it as `task_queue=...`. Suggested fix: move `task_queue` after `*`.
- `pipelex/temporal/tprl_pipe/temporal_pipe_router.py:127` — `make_temporal_pipe_router` — `def make_temporal_pipe_router(task_queue: str | None = None, *, workflow_execution_timeout, retry_policy, ...)` — same pattern as `create_executor`: `task_queue` is a config option defaulting to `None`, not the semantic object of a "make router" call. Suggested fix: `def make_temporal_pipe_router(*, task_queue: str | None = None, ...)`.
- `pipelex/temporal/tprl_pipe/temporal_pipe_run.py:131` — `make_temporal_pipe_run` — `def make_temporal_pipe_run(task_queue: str | None = None, *, workflow_execution_timeout, retry_policy, ...)` — same pattern as `make_temporal_pipe_router`. Suggested fix: `def make_temporal_pipe_run(*, task_queue: str | None = None, ...)`.

**Medium / low**

- `pipelex/temporal/worker_cli.py:25` — `run_worker` — `async def run_worker(project: str | None = None, *, is_not_sandboxed: bool, is_unit_testing: bool, ...)` — `project` defaults to `None` and is looked up from pyproject.toml when absent; its role is closer to a context/config override than the semantic subject of "run a worker". The one real call site passes it positionally from the Typer command, but a fully keyword-only form would be equally natural. Medium confidence — `project` does describe which project's worker to run, so the positional reading is defensible.

### `pipe_controllers` (3 high · 2 med/low)

**High**

- `pipelex/pipe_controllers/parallel/pipe_parallel.py:326` — `PipeParallel._register_branch_outputs_with_graph_tracer` — `def _register_branch_outputs_with_graph_tracer(self, job_metadata: JobMetadata, *, output_stuffs: dict[str, 'Stuff']) -> None` — `job_metadata` is a trace-context carrier / lookup key, not the semantic object; the function acts on `output_stuffs`. Both call sites (210, 309) already pass `job_metadata=job_metadata`. Suggested fix: make fully keyword-only.
- `pipelex/pipe_controllers/parallel/pipe_parallel.py:369` — `PipeParallel._register_parallel_combine_with_graph_tracer` — `def _register_parallel_combine_with_graph_tracer(self, job_metadata: JobMetadata, *, combined_stuff: 'Stuff', branch_stuffs: dict[str, 'Stuff']) -> None` — same pattern: `job_metadata` is a context/trace carrier; the function acts on `combined_stuff` and `branch_stuffs`. Both call sites (203, 302) use `job_metadata=job_metadata`. Suggested fix: move `*` before `job_metadata`.
- `pipelex/pipe_controllers/sub_pipe.py:34` — `SubPipe.run_pipe` — `async def run_pipe(self, calling_pipe_code: str, *, working_memory: WorkingMemory, job_metadata: JobMetadata, sub_pipe_run_params: PipeRunParams, library_crate: 'LibraryCrate | None'=None) -> PipeOutput` — `calling_pipe_code` is caller provenance/context, not the semantic object; `self` (the SubPipe) is the object being run. Call sites (pipe_parallel.py:152, pipe_sequence.py:195, pipe_condition.py:328) already pass `calling_pipe_code=self.code`. Suggested fix: make fully keyword-only.

**Medium / low**

- `pipelex/pipe_controllers/pipe_controller.py:71` — `PipeController._live_run_controller_pipe` — `async def _live_run_controller_pipe(self, job_metadata: JobMetadata, *, ...)` — `job_metadata` positional follows the codebase-wide `_live_run_pipe(self, job_metadata, *, ...)` convention on `PipeAbstract`. The single call site uses keyword form. Medium confidence only — changing the controller without changing the base class would create inconsistency. **Decide as a family** with the base run-pipe signatures.
- `pipelex/pipe_controllers/pipe_controller.py:83` — `PipeController._dry_run_controller_pipe` — same reasoning as `_live_run_controller_pipe`; treat as a pair.

### `builder` (3 high · 1 med/low)

**High**

- `pipelex/builder/operations/models_ops.py:36` — `_resolve_preset_backend` — `def _resolve_preset_backend(model_deck: ModelDeck, *, model_handle: str, model_type: ModelType) -> InferenceModelSpec | None` — Docstring: "Resolve a preset's model handle to an InferenceModelSpec" — the thing resolved is `model_handle`; `model_deck` is a lookup registry. Call sites confirm: `_resolve_preset_backend(model_deck, model_handle=setting.model, model_type=model_type)` — the deck reads as an unlabeled blob while the real target is buried in keyword args. Suggested fix: make fully keyword-only.
- `pipelex/builder/operations/output_ops.py:14` — `build_output_for_pipe` — `async def build_output_for_pipe(mthds_contents: list[str], *, pipe_code: str, output_format: ...) -> dict[str, Any]` — the name says "for_pipe", so the pipe is the subject; `mthds_contents` is raw bundle source material (context/input). `build_output_for_pipe(some_list, pipe_code="my.pipe")` makes the caller think twice about the first list. Suggested fix: make fully keyword-only, or reorder so `pipe_code` is the positional subject.
- `pipelex/builder/operations/runner_code_ops.py:17` — `build_runner_code_for_pipe` — `async def build_runner_code_for_pipe(mthds_contents: list[str], *, pipe_code: str) -> str` — same pattern as `build_output_for_pipe`: name says "for_pipe", the pipe is the object, but `mthds_contents` was made positional. Suggested fix: make fully keyword-only, or promote `pipe_code`.

**Medium / low**

- `pipelex/builder/operations/models_ops.py:101` — `_build_presets_for_category` (+ parallels `_build_aliases_for_category` :135, `_build_waterfalls_for_category` :160) — `def _build_presets_for_category(model_deck: ModelDeck, *, category: ModelCategory, backend: str | None)` — name says "for_category"; `category` drives behavior, `model_deck` is the data source. At call sites the deck reads as an unnamed blob. Lower confidence than `_resolve_preset_backend` because the deck is a richer object with a plausible claim to being the queried subject. Suggested fix: make fully keyword-only (all three).

### `cli` (3 high · 1 med/low)

**High**

- `pipelex/cli/cli_factory.py:31` — `make_pipelex_for_cli` — `def make_pipelex_for_cli(context: ErrorContext, *, library_dirs: ..., needs_inference: bool, ...) -> Pipelex` — `context` is error-reporting metadata (an `ErrorContext` enum that shapes error messages), not the object being created. The function builds a `Pipelex`; `context` is a side-channel tag. Every call site uses `context=...`. Suggested fix: make fully keyword-only.
- `pipelex/cli/agent_cli/commands/run/_output_helpers.py:14` — `build_run_output` — `def build_run_output(with_memory: bool, *, main_stuff_json: dict, working_memory_dump: dict, compact_result: ..., extra_metadata: ...) -> dict` — `with_memory: bool` is a mode flag, not the object being assembled; `main_stuff_json` is the more central data. Both call sites pass `with_memory=with_memory`. Suggested fix: move `*` before `with_memory`.
- `pipelex/cli/commands/init/command.py:182` — `determine_needs` — `def determine_needs(reset: bool, *, check_config: bool, check_inference: bool, ...) -> tuple[bool, bool, bool, bool]` — `reset: bool` is one mode flag among several others; not more "the subject" than `check_config`/`check_inference`. The single call site passes `reset=reset`. Suggested fix: move `*` before `reset` (consistent with the other flags).

**Medium / low**

- `pipelex/cli/agent_cli/commands/init_cmd.py:173` — `_configure_backends` — `def _configure_backends(config: dict[str, Any], *, backends_toml_path: Path, template_backends_path: Path) -> list[str]` — the primary action modifies `backends_toml_path`; `config: dict` is read-only context. The call site passes `config` positionally, so there's no immediate caller-side benefit. Private helper, contained impact, and `config` as "data being acted upon" is defensible. Low confidence.

### `tools` (3 high · 1 med/low)

**High**

- `pipelex/tools/jinja2/jinja2_required_variables.py:121` — `detect_jinja2_required_variables` — `def detect_jinja2_required_variables(template_category: TemplateCategory, *, template_source: str) -> set[str]` — `template_source` is the object analyzed; `template_category` is a configuration/mode parameter. All call sites pass `template_category=` as keyword, so the positional exemption buries the real subject keyword-only. Suggested fix: swap order — `detect_jinja2_required_variables(template_source: str, *, template_category: TemplateCategory)`.
- `pipelex/tools/jinja2/jinja2_required_variables.py:255` — `detect_jinja2_variable_references` — `def detect_jinja2_variable_references(template_category: TemplateCategory, *, template_source: str) -> list[VariableReference]` — same pattern: source is the object, category is config; all call sites keyword the category. Suggested fix: swap order so `template_source` is the positional subject.
- `pipelex/tools/jinja2/jinja2_filters.py:110` — `apply_tag_style` — `def apply_tag_style(context: Context, *, value: str, tag_name: str | None=None) -> str` — `context` is a Jinja2 `Context` used only to retrieve `TAG_STYLE`; `value` is the string being wrapped. Single call site passes `context` positionally (framework-driven), but conceptually the positional arg is a lookup registry, not the acted-on object. Suggested fix: fully keyword-only. *(Caveat: confirm the Jinja2 invocation path — if a `@pass_context` filter calls it positionally, the framework owns the convention.)*

**Medium / low**

- `pipelex/tools/jinja2/jinja2_environment.py:9` — `make_jinja2_env_from_loader` — `def make_jinja2_env_from_loader(template_category: TemplateCategory, *, loader: BaseLoader, enable_async: bool=True) -> Environment` — the name says "from loader", pointing to `loader` as the operative arg; `template_category` is config. Minor — `template_category` plausibly drives env construction. Suggested fix: reorder to `loader` positional, or fully keyword-only.

### `pipe_operators` (2 high · 2 med/low)

**High**

- `pipelex/pipe_operators/img_gen/img_gen_prompt_blueprint.py:269` — `ImgGenPromptBlueprint._render_text` — `async def _render_text(self, context_provider: ContextProviderAbstract, *, template_blueprint: TemplateBlueprint, ...)` — `context_provider` is a lookup environment/registry, not the thing rendered; `template_blueprint` is the real subject. Call sites always pass `context_provider=`. Suggested fix: make fully keyword-only.
- `pipelex/pipe_operators/llm/llm_prompt_blueprint.py:350` — `LLMPromptBlueprint._unravel_text` — `async def _unravel_text(self, context_provider: ContextProviderAbstract, *, jinja2_blueprint: TemplateBlueprint, ...)` — identical to `_render_text`: `context_provider` is the resolution environment, `jinja2_blueprint` is what gets unraveled. Call sites use `context_provider=`. Suggested fix: make fully keyword-only.

**Medium / low**

- `pipelex/pipe_operators/compose/structured_content_composer.py:392` — `StructuredContentComposer._expects_type` — `def _expects_type(self, expected_type: type[Any], *, target_type: type)` — symmetric type-comparison pair (`issubclass(expected_type, target_type)`); neither arg is more "subject". Call sites pass `expected_type=` as keyword. Suggested fix: make fully keyword-only.
- `pipelex/pipe_operators/img_gen/img_gen_prompt_blueprint.py:65` — `ImgGenPromptBlueprint.make_img_gen_prompt` — `async def make_img_gen_prompt(self, context_provider: ContextProviderAbstract, *, extra_params, max_prompt_images)` — `context_provider` is a resolution environment, not what's generated (the prompt is built from `self`). Lower confidence because "context to use for building" is a defensible subject role. Suggested fix: make fully keyword-only.

### `plugins` (1 high · 3 med/low)

**High**

- `pipelex/plugins/gateway/gateway_completions_factory.py:138` — `GatewayCompletionsFactory.make_extract_output_from_response` — `def make_extract_output_from_response(cls, inference_model: InferenceModelSpec, *, response: GenericResponse) -> ExtractOutput` — name is "from_response", so `response` is the primary operand; `inference_model` is only a lookup key selecting the extraction sub-method (`GatewayExtractProtocol.make_from_model_handle`). Suggested fix: make fully keyword-only (or reorder so `response` is the subject).

**Medium / low**

- `pipelex/plugins/anthropic/anthropic_factory.py:244` — `AnthropicFactory.make_nb_tokens_by_category_from_nb` — `def make_nb_tokens_by_category_from_nb(nb_input: int, *, nb_output: int) -> NbTokensByCategoryDict` — symmetric directional pair (`nb_input`/`nb_output`); splitting across `*` is arbitrary. No external call sites found, so risk is low. Suggested fix: make fully keyword-only.
- `pipelex/plugins/mistral/mistral_factory.py:365` — `MistralFactory.make_mistral_document_url_chunk_from_uri` — `async def make_mistral_document_url_chunk_from_uri(cls, mistral_client: Mistral, *, uri: str) -> DocumentURLChunkTypedDict` — name ends "from_uri", so `uri` is the operand; `mistral_client` is a dependency (the docstring calls it "required for local file uploads"). Suggested fix: make fully keyword-only.
- `pipelex/plugins/plugin_sdk_registry.py:22` — `PluginSdkRegistry.set_sdk_instance` — `def set_sdk_instance(self, plugin: Plugin, *, sdk_instance: Any) -> Any` — registry keyed by `plugin.sdk_handle`; `plugin` acts as an index, `sdk_instance` is what's stored. "Set X instance" implies `sdk_instance` is the subject. Call sites already keyword both. Suggested fix: make fully keyword-only.

### `system` (1 high · 3 med/low)

**High**

- `pipelex/system/pipelex_service/gateway_config_merger.py:69` — `GatewayConfigMerger._apply_overrides_to_model` — `def _apply_overrides_to_model(cls, model_name: str, *, gateway_model_specs: BackendModelSpecs, local_model_config: BackendModelSpecs) -> None` — `model_name` is a string used only in log/warning messages; the real operands are the two keyword specs. The sole call site passes `model_name=model_name`. Suggested fix: make fully keyword-only.

**Medium / low**

- `pipelex/system/pipelex_service/pipelex_service_agreement.py:29` — `update_service_terms_acceptance` — `def update_service_terms_acceptance(accepted: bool, *, config_dir: Path | None=None) -> None` — bare `bool` positional; `update_service_terms_acceptance(True)` is opaque. All call sites use `accepted=...`. Suggested fix: make fully keyword-only.
- `pipelex/system/pipelex_service/pipelex_service_agreement.py:53` — `update_inference_setup_completed` — `def update_inference_setup_completed(completed: bool, *, config_dir: Path | None=None) -> None` — same pattern; always called as `completed=True`. Suggested fix: make fully keyword-only.
- `pipelex/system/configuration/config_check.py:12` — `check_is_initialized` — `def check_is_initialized(print_warning_if_not: bool=True) -> bool` — (primitive lone-subject) single `bool` with a descriptive name; `check_is_initialized(False)` would be opaque. Callers always keyword it or use the default. Low priority. Suggested fix: `def check_is_initialized(*, print_warning_if_not: bool=True)`.

### `libraries` (1 high · 3 med/low)

**High**

- `pipelex/libraries/libraries/library_crate.py:39` — `LibraryCrate.compute_fingerprint_from_content` — `def compute_fingerprint_from_content(concepts: dict[str, 'ConceptBlueprint | str'], *, pipes: dict[str, PipeBlueprintUnion]) -> str` — `concepts` and `pipes` are co-equal operands (both dict inputs to a hash); neither is the object. Call sites keyword both. Suggested fix: make fully keyword-only.

**Medium / low**

- `pipelex/libraries/concept/concept_library.py:191` — `ConceptLibrary.add_dependency_concept` — `def add_dependency_concept(self, alias: str, *, concept: Concept) -> None` — `alias` is a namespace/prefix used to build a composite key; `concept` is what's actually added. Call sites use `alias=alias`. Suggested fix: make `alias` keyword-only too, or reorder to `(self, concept, *, alias)`.
- `pipelex/libraries/pipe/pipe_library.py:97` — `PipeLibrary.add_dependency_pipe` — `def add_dependency_pipe(self, alias: str, *, pipe: PipeAbstract) -> None` — identical pattern to `add_dependency_concept`: `alias` is the namespacing key, `pipe` is the subject. Suggested fix: same.
- `pipelex/libraries/visibility_utils.py:35` — `make_visibility_checker` (+ `check_visibility_for_blueprints` :53) — `def make_visibility_checker(manifest: MethodsManifest | None, *, blueprints: list[PipelexBundleBlueprint]) -> PackageVisibilityChecker` — `manifest` is nullable config/filter (often `None`); `blueprints` is the primary data inspected. Call sites pass `manifest=manifest`. Low confidence — `manifest` could be argued as the filter subject. Suggested fix: make both keyword-only (both functions).

### `cogt` (2 high · 1 med/low)

**High**

- `pipelex/cogt/usage/costs_per_token.py:4` — `model_cost_per_token` — `def model_cost_per_token(costs: CostsByCategoryDict, *, cost_category: CostCategory) -> float` — `costs` is a dict used purely as a lookup table; the function dispatches on `cost_category` (`costs.get(cost_category) / 1_000_000`). The real subject is `cost_category`. All three call sites use `costs=...`. Suggested fix: make fully keyword-only, or reorder with `cost_category` first.
- `pipelex/cogt/llm/reasoning_config_base.py:40` — `get_reasoning_level_str` — `def get_reasoning_level_str(effort_to_level_map: EffortToLevelMap, *, effort: ReasoningEffort) -> str | None` — body is `effort_to_level_map.get(effort)`; the map is a lookup table, `effort` is the query. All four call sites pass the map positionally as `self.effort_to_level_map`, reading opaquely. Suggested fix: make fully keyword-only.

**Medium / low**

- `pipelex/cogt/model_backends/backend_credentials.py:26` — `BackendCredentialsErrorMsgFactory.make_one_variable_missing_error_msg` — `def make_one_variable_missing_error_msg(cls, secrets_provider: SecretsProviderAbstract, *, backend_name: str | None, var_name: str) -> str` — `secrets_provider` is a dispatch context (`isinstance`-branches to pick wording); `backend_name`/`var_name` are the real domain objects. Sole call site uses `secrets_provider=`. Lower confidence because the provider does control branching. Low urgency.

### `core` (2 high · 1 med/low)

**High**

- `pipelex/core/stuffs/stuff_content.py:64` — `StuffContent.rendered_markdown` — `def rendered_markdown(self, level: int=1, *, is_pretty: bool=False) -> str` — `level` and `is_pretty` are both optional rendering options; neither is the subject (`self` is). All call sites use keyword form or the no-arg default. `rendered_markdown(2)` is opaque. Suggested fix: move `*` before `level`.
- `pipelex/core/stuffs/stuff_content.py:113` — `StuffContent.rendered_markdown_async` — `async def rendered_markdown_async(self, level: int=1, *, is_pretty: bool=False) -> str` — same issue as `rendered_markdown`; parallel async signature. Suggested fix: move `*` before `level`.

**Medium / low**

- `pipelex/core/concepts/concept.py:194` — `Concept.render_concept_representation` — `def render_concept_representation(self, output_format: ConceptRepresentationFormat, *, is_multiple: bool=False) -> tuple[dict[str, Any], set[str]]` — `self` (Concept) is the real subject; `output_format` and `is_multiple` are equal-standing rendering options. All call sites keyword both. Suggested fix: move `*` before `output_format`.

### `pipe_run` (2 high · 1 med/low)

**High**

- `pipelex/pipe_run/delivery_executor.py:201` — `DeliveryExecutor._try_add_rendered_file` — `async def _try_add_rendered_file(cls, files: dict[str, ResultFile], *, filename: str, render: Awaitable[str], content_type: str) -> None` — `files` is a mutable accumulator/sink, not the object; the real subjects of the "add" are `filename`/`render`/`content_type`. Call site: `self._try_add_rendered_file(files, filename="main_stuff.json", ...)`. Suggested fix: make fully keyword-only.
- `pipelex/pipe_run/delivery_executor.py:219` — `DeliveryExecutor._add_optional_text_file` — `def _add_optional_text_file(cls, files: dict[str, ResultFile], *, filename: str, text: str | None, content_type: str) -> None` — same pattern: `files` is the accumulator carried positionally, `filename`/`text`/`content_type` are the content added. Suggested fix: make fully keyword-only.

**Medium / low**

- `pipelex/pipe_run/pipe_run_params.py:28` — `output_multiplicity_to_apply` — `def output_multiplicity_to_apply(base_multiplicity: VariableMultiplicity | None, *, override_multiplicity: VariableMultiplicity | None) -> VariableMultiplicityResolution` — two-operand priority merge; neither input is clearly "the object". Docstring examples (`output_multiplicity_to_apply(None, None)`) show opaque positional calling. Suggested fix: make fully keyword-only.

### `pipelex` (1 high · 2 med/low)

**High**

- `pipelex/pipelex.py:512` — `Pipelex.make` — `def make(cls, integration_mode: IntegrationMode = IntegrationMode.PYTHON, *, ...)` — `integration_mode` is a mode/config option, not the subject of the factory (the subject is the instance created). All call sites omit it or pass `integration_mode=...`. `Pipelex.make(IntegrationMode.CLI)` reads opaquely. **Primary public API entry point** — keyword-only is the right default. Suggested fix: `def make(cls, *, integration_mode: IntegrationMode = IntegrationMode.PYTHON, ...)`.

**Medium / low**

- `pipelex/pipelex.py:165` — `Pipelex.setup` — `def setup(self, integration_mode: IntegrationMode, *, ...)` — same logic as `make`: `integration_mode` is a mode flag, not the subject (`self` is). The sole internal call site uses `integration_mode=integration_mode`. Public API surface (though `make` is the primary entry). Suggested fix: `def setup(self, *, integration_mode: IntegrationMode, ...)`.
- `pipelex/pipelex.py:145` — `Pipelex._get_validation_error_msg` — `def _get_validation_error_msg(component_name: str, *, validation_exc: Exception) -> str` — `component_name` is a descriptive label ("routing profile library", …), behaving like context alongside `validation_exc`. Call sites: `self._get_validation_error_msg("routing profile library", validation_exc=exc)` — the bare positional string reads opaquely. Private, low call-count, but inconsistent (`validation_exc` already keyword-only). Suggested fix: make fully keyword-only.

### `observer` (2 high · 0 med/low)

**High**

- `pipelex/observer/multi_observer.py:14` — `MultiObserver.remove_observer` — `def remove_observer(self, name: str) -> None` — asymmetric with `add_observer(*, name, observer)` which is fully keyword-only; `remove_observer("some_name")` passes a bare string with no call-site context. Convention consistency + readability → `def remove_observer(self, *, name: str)`. *(Primitive lone-subject — flagged for the asymmetry, not opacity alone.)*
- `pipelex/observer/local_observer.py:22` — `LocalObserver._write_to_jsonl` — `def _write_to_jsonl(self, event_type: str, *, payload: PayloadType) -> None` — `event_type` is a routing/selector string (picks the file + injects a key), not the object written; the payload is the real subject. Call sites pass a named constant so readability is acceptable, but the positional/keyword split is inconsistent (both are equally descriptive). Suggested fix: `def _write_to_jsonl(self, *, event_type, payload)`.

### `kit` (1 high · 1 med/low)

**High**

- `pipelex/kit/single_file_agent_rules.py:12` — `_read_agent_file` — `def _read_agent_file(agents_dir: Traversable, *, name: str) -> str` — `agents_dir` is a lookup-context directory; `name` is the file read — the real object. "read [name] from [agents_dir]" has the subject keyworded and the context positional. Call site (:79): `_read_agent_file(agents_dir, name=name)`. Suggested fix: make fully keyword-only.

**Medium / low**

- `pipelex/kit/single_file_agent_rules.py:49` — `build_merged_rules` — `def build_merged_rules(kit_index: KitIndex, *, agent_set: str | None=None, file_list: list[str] | None=None) -> str` — `kit_index` is a config/registry data source + lookup table, reading more like context than subject. Lower confidence — a `KitIndex` could reasonably be "the thing being merged from". Suggested fix: make fully keyword-only.

### `graph` (0 high · 1 med/low)

**Medium / low**

- `pipelex/graph/graph_tracer_manager.py:266` — `GraphTracerManager.on_pipe_end_success` (+ siblings `on_pipe_end_error` :325, `register_execution_data` :304, `add_edge` :360, `register_controller_output` :389, `register_batch_item_extraction` :411, `register_batch_aggregation` :440, `register_parallel_combine` :469) — `lookup_key` is a registry dispatch key routing to the right `GraphTracer` via `self._get_tracer(lookup_key)`; the semantic subject is `node_id` (in the keyword args). All call sites already pass `lookup_key=` as keyword, so no opacity exists today. The case for keyword-only: `lookup_key` is a dispatch concern, not the object, and the naming asymmetry with `GraphTracerProtocol` (which takes `node_id` positionally) is mildly confusing. Low confidence — `lookup_key` as first-positional is a coherent "which tracer" discriminant. **Decide as a family** across all eight manager dispatch methods.

### `pipeline` (0 high · 1 med/low)

**Medium / low**

- `pipelex/pipeline/job_metadata.py:89` — `JobMetadata.copy_with_update` — `def copy_with_update(self, otel_context: OtelContext | None, *, trace_context: TraceContext | None = None, **updates: Any)` — `otel_context` is not the subject (`self` is); it's one of two context fields being updated, asymmetrically split from `trace_context` across `*`. Call sites pass `otel_context=...`, and the docstring justifies the asymmetry semantically (different inheritance semantics), but from a signature-readability standpoint both context args are peers. Suggested fix: make fully keyword-only.

### `reporting` (0 high · 1 med/low)

**Medium / low**

- `pipelex/reporting/reporting_manager.py:251` — `ReportingManager._emit_best_effort` — `def _emit_best_effort(event_log: EventLogProtocol, *, event: UsageReportEvent) -> None` — `event` is the object emitted; `event_log` is the target/sink (`event_log.emit(event)`). Both call sites pass `event_log=`. "emit best effort" names the action, not the receiver, so neither arg has a clear subject claim. Suggested fix: make fully keyword-only.

### `runtime_bridge` (0 high · 1 med/low)

**Medium / low**

- `pipelex/runtime_bridge/primitives/hydration.py:17` — `_validate_as_known_class` — `def _validate_as_known_class(item_class: type[StuffContent], *, raw_item: StuffContent | dict[str, Any]) -> StuffContent` — `item_class` is a type/schema used to validate, not the data acted on; `raw_item` is the actual object. "validate raw_item into item_class" → `raw_item` is arguably the subject. Call sites: `_validate_as_known_class(item_class_or_none, raw_item=raw_item)` — a type as positional subject is unusual. Suggested fix: make fully keyword-only, or reorder to `(raw_item, *, item_class)`.

---

## Zero-suspect packages

`base_exceptions` (1 reviewed), `errors` (7), `hub` (15), `language` (8), `pipe_signature` (2), `tracing` (9) — reviewed, no positional-subject abuse found.

## Suggested next step

Reserve adjudication for the **31 high-confidence** entries first — they cluster tightly into patterns 1–6 above and most already have call sites that keyword the "positional" arg, so the fix is low-risk and mechanical (`move *` / reorder). The `pipelex.make`/`setup` pair (pattern 8) is a deliberate public-API call. The med/low entries flagged "decide as a family" (`pipe_controllers` run-pipe convention, `graph` dispatch methods) should be settled at the base/convention level, not site-by-site. Point Opus at this shortlist, or hand-pick — happy to drive either.
