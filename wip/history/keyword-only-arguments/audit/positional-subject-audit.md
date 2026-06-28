# Keyword-Only Refactor — Positional-Subject Audit

Every `pipelex/` function/method where the **first true parameter (after dropping `self`/`cls`) was kept positional** — i.e. where Exception 1 of the keyword-only convention ("the subject may stay positional") is in effect. This is the population to audit for the worry: *was the first arg really the semantically obvious object of the call, or was it made positional just to satisfy the rule?*

## How this was generated

An AST pass that **reuses the keyword-only guard's own carve-out detection** (`pipelex/cli/dev_cli/commands/keyword_only_guard.py`). Anything the guard skips is excluded here too, because those were never a deliberate "subject" decision:

- dunder/operator methods (`__init__`, `__eq__`, …)
- pydantic `@field_validator` / `@model_validator` / serializers
- framework entrypoints: Typer/click commands, Temporal `@activity.defn`/`@workflow.*`, pytest fixtures, Jinja2 `@pass_context`/… filters
- `@override` implementations (the parent's call convention governs them)
- `# kw-only: ignore` escape-hatch defs

Functions with **no** positional parameter at all (fully keyword-only `def f(*, a, b)`, zero-arg, or staticmethods with only keyword-only params) are also excluded — there is no positional subject to question.

Scope: `pipelex/` source only (tests excluded, matching the refactor's locked scope).

## Summary

**Total positional-subject functions: 1806**

| Category | Count | What it is |
| --- | --- | --- |
| `SUBJECT_THEN_KEYWORDS` | 797 | Subject kept positional **and** one or more other params pushed to keyword-only (`def f(subject, *, ...)`). This is where the "which arg is the subject?" decision was actually made — the **primary review target**. |
| `LONE_SUBJECT` | 1003 | A single positional parameter and nothing else after it (`def f(subject)`, optionally `**kwargs`). No "choice" of subject was possible — only one arg exists. Lowest signal; included for completeness. A bare bool/int/str subject here is the only thing arguably worth a second look (`do_thing(True)` reads opaquely). |
| `SYMMETRIC_ALLOWLIST` | 5 | Exception 2 — the curated symmetric-tuple allowlist (multiple positionals that read better ordered, e.g. `set_env(key, value)`). |
| `MULTI_POSITIONAL` | 1 | Survives the guard with 2+ positionals or a `*args` — i.e. a variadic wrapper/closure, not a deliberate subject choice. |

### By package

| Package | SUBJECT_THEN_KEYWORDS | All categories |
| --- | --- | --- |
| `base_exceptions.py` | 0 | 8 |
| `builder` | 20 | 36 |
| `cli` | 112 | 210 |
| `cogt` | 119 | 291 |
| `core` | 95 | 213 |
| `errors` | 5 | 17 |
| `graph` | 40 | 67 |
| `hub.py` | 1 | 45 |
| `kit` | 8 | 12 |
| `language` | 5 | 21 |
| `libraries` | 28 | 74 |
| `observer` | 1 | 5 |
| `pipe_controllers` | 6 | 11 |
| `pipe_operators` | 40 | 53 |
| `pipe_run` | 18 | 27 |
| `pipe_signature` | 2 | 2 |
| `pipelex.py` | 3 | 4 |
| `pipeline` | 18 | 31 |
| `plugins` | 49 | 132 |
| `reporting` | 5 | 12 |
| `runtime_bridge` | 12 | 22 |
| `system` | 38 | 100 |
| `temporal` | 39 | 88 |
| `test_extras` | 0 | 6 |
| `tools` | 128 | 296 |
| `tracing` | 5 | 23 |

---

## Review strategy

**What this audit is asking each reviewer to decide:** for a given `def f(subject, *, ...)`, is `subject` genuinely the semantic object the function acts on (so positional reads naturally — `parse_pipe_spec(spec_data, ...)`), or was it kept positional merely to satisfy Exception 1, when the call would actually read better with that arg keyworded too?

### Model grade

**Sonnet 4.6 is sufficient for the per-line judgment.** This is a naming/API-taste classification, not a reasoning-heavy task — the vast majority of signatures are unambiguous from the `def` line alone. Opus-grade horsepower buys little here.

The real bottleneck is **not** model IQ — it is two other things:

1. **Context per line.** A signature alone settles most cases, but an ambiguous minority cannot be judged without the function body and a call site or two (e.g. `_resolve_preset_backend(model_deck, *, model_handle, model_type)` — is the deck the subject, or is this "resolve a backend *for a handle*" with the deck as a lookup table?). **Give the reviewer Read/Grep so it can open the body — do not feed it only the text line**, or even Opus will just guess.
2. **Calibration.** A cheap pass tends to either rubber-stamp everything or over-flag. Mitigate with a tight rubric (see `docs/contribute/keyword-only-arguments.md` for worked examples) and an instruction to **default to OK and emit only the suspects**, each with a one-line reason and a suggested fix.

### Triage plan (don't sweep all 1806 lines)

1. **Drop most of `LONE_SUBJECT` (1003).** With a single positional param there was no "subject" choice to abuse. The only sub-slice worth a look is **primitive-typed** lone subjects (`do_thing(True)`, `f(count: int)`), which read opaquely at the call site — filter those mechanically (grep), no LLM needed.
2. **Sonnet fan-out across packages** over the 797 `SUBJECT_THEN_KEYWORDS` (+ the primitive lone-subjects), one agent per package, each emitting only a shortlist of "this positional reads wrong" entries with reasoning + suggested fix. Parallel, cheap, consistent.
3. **Adjudicate only the shortlist** (yourself, or Opus on just the contested few dozen). Reserve the expensive judgment for the small contested set rather than spending it uniformly across ~1800 obvious cases.

---

## A. `SUBJECT_THEN_KEYWORDS` — primary review target

_Subject kept positional **and** one or more other params pushed to keyword-only (`def f(subject, *, ...)`). This is where the "which arg is the subject?" decision was actually made — the **primary review target**._

Count: 797

### `builder` (20)

- `pipelex/builder/concept/concept_spec.py:198` — `ConceptStructureSpec._raise_type_mismatch_error` — `def _raise_type_mismatch_error(self, expected_type_name: str, *, actual_type_name: str) -> None`
- `pipelex/builder/operations/inputs_ops.py:23` — `build_inputs_for_pipe` — `async def build_inputs_for_pipe(pipe_code: str | None=None, *, mthds_contents: list[str] | None=None, bundle_path: Path | None=None, library_dirs: list[Path] | None=None) -> dict[str, Any]`
- `pipelex/builder/operations/models_ops.py:28` — `_should_include` — `def _should_include(category: ModelCategory, *, categories: list[ModelCategory] | None) -> bool`
- `pipelex/builder/operations/models_ops.py:36` — `_resolve_preset_backend` — `def _resolve_preset_backend(model_deck: ModelDeck, *, model_handle: str, model_type: ModelType) -> InferenceModelSpec | None`
- `pipelex/builder/operations/models_ops.py:46` — `_filter_presets_by_backend` — `def _filter_presets_by_backend(presets_list: list[dict[str, Any]], *, presets_dict: dict[str, Any], model_deck: ModelDeck, model_type: ModelType, backend: str) -> list[dict[str, Any]]`
- `pipelex/builder/operations/models_ops.py:67` — `_filter_aliases_by_backend` — `def _filter_aliases_by_backend(aliases: dict[str, str], *, model_deck: ModelDeck, model_type: ModelType, backend: str) -> dict[str, str]`
- `pipelex/builder/operations/models_ops.py:83` — `_filter_waterfalls_by_backend` — `def _filter_waterfalls_by_backend(waterfalls: dict[str, list[str]], *, model_deck: ModelDeck, model_type: ModelType, backend: str) -> dict[str, list[str]]`
- `pipelex/builder/operations/models_ops.py:101` — `_build_presets_for_category` — `def _build_presets_for_category(model_deck: ModelDeck, *, category: ModelCategory, backend: str | None) -> list[dict[str, Any]]`
- `pipelex/builder/operations/models_ops.py:135` — `_build_aliases_for_category` — `def _build_aliases_for_category(model_deck: ModelDeck, *, category: ModelCategory, backend: str | None) -> dict[str, str]`
- `pipelex/builder/operations/models_ops.py:160` — `_build_waterfalls_for_category` — `def _build_waterfalls_for_category(model_deck: ModelDeck, *, category: ModelCategory, backend: str | None) -> dict[str, list[str]]`
- `pipelex/builder/operations/models_ops.py:185` — `list_models` — `def list_models(categories: list[ModelCategory] | None=None, *, backend: str | None=None) -> dict[str, Any]`
- `pipelex/builder/operations/output_ops.py:14` — `build_output_for_pipe` — `async def build_output_for_pipe(mthds_contents: list[str], *, pipe_code: str, output_format: ConceptRepresentationFormat=ConceptRepresentationFormat.SCHEMA) -> dict[str, Any]`
- `pipelex/builder/operations/pipe_ops.py:47` — `_normalize_sub_pipe_list` — `def _normalize_sub_pipe_list(raw_value: Any, *, field_name: str) -> list[dict[str, Any]]`
- `pipelex/builder/operations/pipe_ops.py:89` — `parse_pipe_spec` — `def parse_pipe_spec(spec_data: Any, *, pipe_type: str) -> PipeSpec`
- `pipelex/builder/operations/pipe_ops.py:191` — `add_type_specific_fields` — `def add_type_specific_fields(pipe_spec: PipeSpec, *, pipe_table: Table) -> None`
- `pipelex/builder/operations/runner_code_ops.py:17` — `build_runner_code_for_pipe` — `async def build_runner_code_for_pipe(mthds_contents: list[str], *, pipe_code: str) -> str`
- `pipelex/builder/operations/validate_ops.py:53` — `validate_bundle_file` — `async def validate_bundle_file(bundle_path: Path, *, library_dirs: list[Path] | None=None) -> dict[str, Any]`
- `pipelex/builder/operations/validate_ops.py:110` — `validate_pipe` — `async def validate_pipe(pipe_code: str, *, library_dirs: list[Path] | None=None) -> dict[str, Any]`
- `pipelex/builder/runner_code.py:65` — `_format_representation_as_python` — `def _format_representation_as_python(representation: dict[str, Any], *, is_multiple: bool=False) -> str`
- `pipelex/builder/runner_code.py:158` — `generate_runner_code` — `def generate_runner_code(pipe: PipeAbstract, *, output_multiplicity: bool=False, library_dir: str | None=None) -> str`

### `cli` (112)

- `pipelex/cli/agent_cli/commands/agent_cli_factory.py:163` — `make_pipelex_for_agent_cli` — `def make_pipelex_for_agent_cli(library_dirs: list[str] | list[Path] | None=None, *, needs_inference: bool=True, needs_model_specs: bool | None=None) -> Pipelex`
- `pipelex/cli/agent_cli/commands/agent_output.py:218` — `_assemble_error_payload` — `def _assemble_error_payload(message: str, *, error_type: str, cause: BaseException | None, extra: dict[str, Any]) -> dict[str, Any]`
- `pipelex/cli/agent_cli/commands/agent_output.py:311` — `_agent_error_json` — `def _agent_error_json(message: str, *, error_type: str, cause: BaseException | None, extra: dict[str, Any]) -> NoReturn`
- `pipelex/cli/agent_cli/commands/agent_output.py:318` — `agent_error_markdown` — `def agent_error_markdown(message: str, *, error_type: str, cause: BaseException | None=None, **extra: Any) -> NoReturn`
- `pipelex/cli/agent_cli/commands/agent_output.py:338` — `agent_error` — `def agent_error(message: str, *, error_type: str, cause: BaseException | None=None, **extra: Any) -> NoReturn`
- `pipelex/cli/agent_cli/commands/agent_output.py:382` — `agent_success_formatted` — `def agent_success_formatted(result: dict[str, Any], *, markdown_renderer: Callable[[dict[str, Any]], str], output_format: CliOutputFormat) -> None`
- `pipelex/cli/agent_cli/commands/init_cmd.py:153` — `_copy_telemetry_template` — `def _copy_telemetry_template(target_dir: Path, *, for_project: bool) -> None`
- `pipelex/cli/agent_cli/commands/init_cmd.py:173` — `_configure_backends` — `def _configure_backends(config: dict[str, Any], *, backends_toml_path: Path, template_backends_path: Path) -> list[str]`
- `pipelex/cli/agent_cli/commands/init_cmd.py:228` — `_configure_routing` — `def _configure_routing(selected_backend_keys: list[str], *, config: dict[str, Any], target_dir: Path) -> str`
- `pipelex/cli/agent_cli/commands/inputs/_inputs_core.py:13` — `inputs_core` — `async def inputs_core(pipe_code: str | None=None, *, bundle_path: Path | None=None, library_dirs: list[Path] | None=None) -> dict[str, Any]`
- `pipelex/cli/agent_cli/commands/pipe_cmd.py:74` — `_add_type_specific_fields` — `def _add_type_specific_fields(pipe_spec: PipeSpec, *, pipe_table: tomlkit.TOMLDocument | tomlkit.items.Table) -> None`
- `pipelex/cli/agent_cli/commands/plxt_passthrough.py:11` — `run_plxt` — `def run_plxt(subcommand: str, *, file_path: str) -> None`
- `pipelex/cli/agent_cli/commands/run/_output_helpers.py:14` — `build_run_output` — `def build_run_output(with_memory: bool, *, main_stuff_json: dict[str, Any], working_memory_dump: dict[str, Any], compact_result: dict[str, Any] | None, extra_metadata: dict[str, Any] | None=None) -> dict[str, Any]`
- `pipelex/cli/agent_cli/commands/run/_output_helpers.py:69` — `format_run_markdown` — `def format_run_markdown(result: dict[str, Any], *, with_memory: bool) -> str`
- `pipelex/cli/agent_cli/commands/run/_run_core.py:21` — `run_pipeline_core` — `async def run_pipeline_core(pipe_code: str, *, mthds_contents: list[str] | None=None, bundle_uris: list[str] | None=None, inputs: dict[str, Any] | None=None, dry_run: bool=False, mock_inputs: bool=False, library_dirs: list[str] | None=None, graph: bool=False, costs: bool=True, with_memory: bool=False) -> dict[str, Any]`
- `pipelex/cli/agent_cli/commands/run/_run_core_api.py:17` — `run_pipeline_core_api` — `async def run_pipeline_core_api(pipe_code: str, *, mthds_contents: list[str] | None=None, inputs: dict[str, Any] | None=None, with_memory: bool=False) -> dict[str, Any]`
- `pipelex/cli/agent_cli/commands/run/stdin_resolver.py:116` — `parse_cli_inputs` — `def parse_cli_inputs(inputs_arg: str | None, *, stdin_fallback: bool=True, auto_inputs_path: str | None=None) -> dict[str, Any] | None`
- `pipelex/cli/agent_cli/commands/validate/_validate_core.py:22` — `validate_all_core` — `async def validate_all_core(library_dirs: list[Path] | None=None, *, allow_signatures: bool=False) -> dict[str, Any]`
- `pipelex/cli/agent_cli/commands/validate/_validate_core.py:57` — `validate_bundle_core` — `async def validate_bundle_core(bundle_path: Path, *, library_dirs: list[Path] | None=None, allow_signatures: bool=False) -> dict[str, Any]`
- `pipelex/cli/agent_cli/commands/validate/_validate_core.py:97` — `validate_pipe_core` — `async def validate_pipe_core(pipe_code: str, *, library_dirs: list[Path] | None=None, allow_signatures: bool=False) -> dict[str, Any]`
- `pipelex/cli/cli_factory.py:31` — `make_pipelex_for_cli` — `def make_pipelex_for_cli(context: ErrorContext, *, library_dirs: list[str] | list[Path] | None=None, needs_inference: bool=True, temporal_enabled: bool | None=None, needs_model_specs: bool | None=None) -> Pipelex`
- `pipelex/cli/commands/build/inputs/_inputs_core.py:35` — `_generate_inputs_core` — `async def _generate_inputs_core(pipe_code: str | None=None, *, bundle_path: Path | None=None, output_path: Path | None=None, library_dir: list[str] | None=None) -> None`
- `pipelex/cli/commands/build/inputs/_inputs_core.py:116` — `execute_generate_inputs` — `def execute_generate_inputs(pipe_code: str | None, *, bundle_path: Path | None, output_path: Path | None, library_dir: list[str] | None=None, telemetry_command_label: str=f'{COMMAND} {SUB_COMMAND_INPUTS}') -> None`
- `pipelex/cli/commands/build/output/_output_core.py:35` — `_generate_output_core` — `async def _generate_output_core(pipe_code: str | None=None, *, bundle_path: Path | None=None, output_path: Path | None=None, output_format: ConceptRepresentationFormat=ConceptRepresentationFormat.JSON, library_dir: list[str] | None=None) -> None`
- `pipelex/cli/commands/build/output/_output_core.py:130` — `execute_generate_output` — `def execute_generate_output(pipe_code: str | None, *, bundle_path: Path | None, output_path: Path | None, output_format: ConceptRepresentationFormat, library_dir: list[str] | None=None, telemetry_command_label: str=f'{COMMAND} {SUB_COMMAND_OUTPUT}') -> None`
- `pipelex/cli/commands/build/runner/_runner_core.py:52` — `_prepare_runner_core` — `async def _prepare_runner_core(pipe_code: str | None=None, *, bundle_path: Path | None=None, output_path: Path | None=None, library_dirs: list[Path] | None=None) -> None`
- `pipelex/cli/commands/build/runner/_runner_core.py:175` — `execute_prepare_runner` — `def execute_prepare_runner(pipe_code: str | None, *, bundle_path: Path | None, output_path: Path | None, library_dirs: list[Path] | None=None, telemetry_command_label: str=f'{COMMAND} {SUB_COMMAND_RUNNER}') -> None`
- `pipelex/cli/commands/build/structures_cmd.py:50` — `_build_concept_ref_to_class_info` — `def _build_concept_ref_to_class_info(blueprints: list['PipelexBundleBlueprint'], *, output_directory: Path) -> dict[str, ConceptClassInfo]`
- `pipelex/cli/commands/build/structures_cmd.py:105` — `generate_structures_from_blueprints` — `def generate_structures_from_blueprints(blueprints: list['PipelexBundleBlueprint'], *, output_directory: Path, target_path: Path | None=None, skip_existing_check: bool=False, quiet: bool=False) -> list[tuple[str, str]]`
- `pipelex/cli/commands/doctor_cmd.py:291` — `replace_backend_file` — `def replace_backend_file(backend_name: str, *, dry_run: bool=False, config_dir: Path | None=None) -> bool`
- `pipelex/cli/commands/doctor_cmd.py:741` — `setup_doctor_runtime` — `def setup_doctor_runtime(log_config_overrides: Mapping[str, Any] | None=None, *, config_dir: Path | None=None) -> None`
- `pipelex/cli/commands/graph_cmd.py:38` — `_do_graph_render` — `def _do_graph_render(input_file: Path, *, out: str | None, direction: FlowchartDirection | None, mermaidflow: bool, reactflow: bool, subgraphs: bool, open_browser: bool) -> None`
- `pipelex/cli/commands/init/backends.py:31` — `update_backends_in_toml` — `def update_backends_in_toml(toml_doc: Any, *, selected_indices: list[int], backend_options: list[tuple[str, str]]) -> None`
- `pipelex/cli/commands/init/command.py:129` — `prime_remote_config_cache` — `def prime_remote_config_cache(console: Console, *, target_config_dir: Path | None=None) -> None`
- `pipelex/cli/commands/init/command.py:144` — `_check_gateway_terms_if_needed` — `def _check_gateway_terms_if_needed(console: Console, *, backends_toml_path: Path) -> None`
- `pipelex/cli/commands/init/command.py:182` — `determine_needs` — `def determine_needs(reset: bool, *, check_config: bool, check_inference: bool, check_routing: bool, check_telemetry: bool, backends_toml_path: Path, routing_profiles_toml_path: Path, telemetry_config_path: Path, target_config_dir: Path | None=None) -> tuple[bool, bool, bool, bool]`
- `pipelex/cli/commands/init/command.py:219` — `confirm_initialization` — `def confirm_initialization(console: Console, *, needs_config: bool, needs_inference: bool, needs_routing: bool, needs_telemetry: bool, check_credentials: bool, reset: bool, focus: InitFocus) -> bool`
- `pipelex/cli/commands/init/command.py:277` — `execute_initialization` — `def execute_initialization(console: Console, *, needs_config: bool, needs_inference: bool, needs_routing: bool, needs_telemetry: bool, check_credentials: bool, reset: bool, check_inference: bool, check_routing: bool, backends_toml_path: Path, telemetry_config_path: Path, is_first_time_backends_setup: bool, target_config_dir: Path | None=None, for_project: bool=False)`
- `pipelex/cli/commands/init/command.py:478` — `init_cmd` — `def init_cmd(focus: InitFocus=InitFocus.ALL, *, skip_confirmation: bool=False, local: bool=False)`
- `pipelex/cli/commands/init/config_files.py:20` — `init_config` — `def init_config(reset: bool=False, *, dry_run: bool=False, target_dir: Path | None=None) -> int`
- `pipelex/cli/commands/init/credentials.py:48` — `write_env_file` — `def write_env_file(env_path: Path, *, entries: dict[str, str]) -> None`
- `pipelex/cli/commands/init/credentials.py:104` — `prompt_credentials` — `def prompt_credentials(console: Console, *, backends_toml_path: Path) -> None`
- `pipelex/cli/commands/init/ide_extension.py:56` — `_install_extension` — `def _install_extension(ide_name: str, *, cmd: str, console: Console) -> bool`
- `pipelex/cli/commands/init/routing.py:26` — `customize_routing_profile` — `def customize_routing_profile(selected_backend_keys: list[str], *, target_config_dir: Path | None=None) -> None`
- `pipelex/cli/commands/init/ui/backends_ui.py:17` — `get_backend_options_from_toml` — `def get_backend_options_from_toml(template_path: Path, *, existing_path: Path | None=None) -> list[tuple[str, str]]`
- `pipelex/cli/commands/init/ui/backends_ui.py:61` — `get_currently_enabled_backends` — `def get_currently_enabled_backends(backends_toml_path: Path, *, backend_options: list[tuple[str, str]]) -> list[int]`
- `pipelex/cli/commands/init/ui/backends_ui.py:97` — `build_backend_selection_panel` — `def build_backend_selection_panel(backend_options: list[tuple[str, str]], *, currently_enabled: list[int] | None=None, is_first_time_setup: bool=False) -> Panel`
- `pipelex/cli/commands/init/ui/backends_ui.py:155` — `prompt_backend_select` — `def prompt_backend_select(console: Console, *, backend_options: list[tuple[str, str]], currently_enabled: list[int] | None=None, is_first_time_setup: bool=False) -> tuple[list[int], set[str]]`
- `pipelex/cli/commands/init/ui/general_ui.py:6` — `build_initialization_panel` — `def build_initialization_panel(needs_config: bool, *, needs_inference: bool, needs_routing: bool, needs_telemetry: bool, reset: bool, check_credentials: bool=False) -> Panel`
- `pipelex/cli/commands/init/ui/routing_ui.py:13` — `build_primary_backend_panel` — `def build_primary_backend_panel(backend_keys: list[str], *, backend_options: list[tuple[str, str]]) -> Panel`
- `pipelex/cli/commands/init/ui/routing_ui.py:91` — `build_fallback_order_panel` — `def build_fallback_order_panel(remaining_backends: list[str], *, backend_options: list[tuple[str, str]]) -> Panel`
- `pipelex/cli/commands/init/ui/routing_ui.py:127` — `prompt_fallback_order` — `def prompt_fallback_order(console: Console, *, remaining_backends: list[str], backend_options: list[tuple[str, str]]) -> list[str]`
- `pipelex/cli/commands/init/ui/routing_ui.py:198` — `display_routing_profile_result` — `def display_routing_profile_result(console: Console, *, profile_name: str, created: bool=False) -> None`
- `pipelex/cli/commands/login/command.py:105` — `serve_until_callback` — `def serve_until_callback(server: HTTPServer, *, result: dict[str, str | None]) -> None`
- `pipelex/cli/commands/run/_inputs_path_resolver.py:45` — `resolve_url_in_value` — `def resolve_url_in_value(value: Any, *, base_dir: Path) -> Any`
- `pipelex/cli/commands/run/_inputs_path_resolver.py:75` — `resolve_inputs_paths` — `def resolve_inputs_paths(inputs_dict: dict[str, Any], *, base_dir: Path) -> dict[str, Any]`
- `pipelex/cli/commands/run/_run_core.py:74` — `_execute_run` — `async def _execute_run(pipe_code: str | None, *, bundle_path: str | None, inputs: str | None, save_working_memory: bool, working_memory_path: str | None, save_main_stuff: bool, no_pretty_print: bool, graph: bool | None, graph_full_data: bool | None, output_dir: str, dry_run: bool, mock_usage: bool, mock_inputs: bool, library_dir: list[str] | None, costs: bool | None=None, dynamic_output_concept_ref: str | None=None, save_csv: str | None=None) -> None`
- `pipelex/cli/commands/run/_run_core.py:344` — `execute_run` — `def execute_run(pipe_code: str | None, *, bundle_path: str | None, inputs: str | None, save_working_memory: bool, working_memory_path: str | None, save_main_stuff: bool, no_pretty_print: bool, graph: bool | None, graph_full_data: bool | None, output_dir: str, dry_run: bool, mock_usage: bool, mock_inputs: bool, library_dir: list[str] | None, costs: bool | None=None, telemetry_command_label: str=COMMAND, temporal: bool | None=None, dynamic_output_concept_ref: str | None=None, save_csv: str | None=None) -> None`
- `pipelex/cli/commands/update_cmd.py:34` — `update_cmd` — `def update_cmd(local: bool=False, *, yes: bool=False, dry_run: bool=False, no_backup: bool=False) -> None`
- `pipelex/cli/commands/update_cmd.py:102` — `_print_status_table` — `def _print_status_table(report: DeckSyncReport, *, deck_dir: Path) -> None`
- `pipelex/cli/commands/update_cmd.py:138` — `_apply_updates` — `def _apply_updates(deck_dir: Path, *, report: DeckSyncReport, no_backup: bool) -> int`
- `pipelex/cli/commands/update_cmd.py:187` — `_summary_panel` — `def _summary_panel(message: str, *, style: str) -> Panel`
- `pipelex/cli/commands/validate/_validate_core.py:59` — `do_validate_all_libraries_and_dry_run` — `def do_validate_all_libraries_and_dry_run(library_dirs: list[Path] | None=None, *, allow_signatures: bool=False) -> None`
- `pipelex/cli/commands/validate/_validate_core.py:99` — `_validate_pipe_or_bundle` — `async def _validate_pipe_or_bundle(pipe_code: str | None=None, *, bundle_path: Path | None=None, library_dirs: list[Path] | None=None, allow_signatures: bool=False) -> None`
- `pipelex/cli/commands/validate/_validate_core.py:162` — `execute_validate` — `def execute_validate(pipe_code: str | None, *, bundle_path: Path | None, library_dirs: list[Path] | None, telemetry_command_label: str=COMMAND, allow_signatures: bool=False, temporal: bool | None=None) -> None`
- `pipelex/cli/commands/which_cmd.py:33` — `do_which_pipe` — `def do_which_pipe(pipe_code: str, *, library_dirs: list[Path], source_label: str) -> bool`
- `pipelex/cli/dev_cli/commands/check_config_sync_cmd.py:24` — `check_config_sync_cmd` — `def check_config_sync_cmd(show_diff: bool=True, *, leading: LeadingConfig=LeadingConfig.INSTALLED, quiet: bool=False) -> None`
- `pipelex/cli/dev_cli/commands/check_gateway_models_cmd.py:28` — `check_gateway_models_cmd` — `def check_gateway_models_cmd(show_diff: bool=True, *, quiet: bool=False) -> None`
- `pipelex/cli/dev_cli/commands/check_mthds_schema_cmd.py:21` — `check_mthds_schema_cmd` — `def check_mthds_schema_cmd(show_diff: bool=True, *, quiet: bool=False) -> None`
- `pipelex/cli/dev_cli/commands/check_rules_sync_cmd.py:40` — `check_rules_sync_cmd` — `def check_rules_sync_cmd(show_diff: bool=True, *, quiet: bool=False) -> None`
- `pipelex/cli/dev_cli/commands/check_urls_cmd.py:63` — `check_single_url_async` — `async def check_single_url_async(client: httpx.AsyncClient, *, name: str, url: str) -> URLCheckResult`
- `pipelex/cli/dev_cli/commands/check_urls_cmd.py:118` — `check_all_urls_async` — `async def check_all_urls_async(url_pairs: list[tuple[str, str]], *, request_timeout: int) -> list[URLCheckResult]`
- `pipelex/cli/dev_cli/commands/check_urls_cmd.py:145` — `check_urls_cmd` — `def check_urls_cmd(quiet: bool=False, *, timeout: int=DEFAULT_TIMEOUT) -> None`
- `pipelex/cli/dev_cli/commands/gateway_models_generator.py:126` — `generate_pure_markdown_list.sort_by_preferred` — `def sort_by_preferred(items: list[str], *, preferred: list[str]) -> list[str]`
- `pipelex/cli/dev_cli/commands/gateway_models_generator.py:165` — `generate_markdown_table.sort_by_preferred` — `def sort_by_preferred(items: set[str], *, preferred: list[str]) -> list[str]`
- `pipelex/cli/dev_cli/commands/generate_error_pages_cmd.py:16` — `generate_error_pages_cmd` — `def generate_error_pages_cmd(output: Path | None=None, *, quiet: bool=False) -> None`
- `pipelex/cli/dev_cli/commands/generate_mthds_schema_cmd.py:18` — `generate_mthds_schema_cmd` — `def generate_mthds_schema_cmd(output: Path | None=None, *, quiet: bool=False) -> None`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:214` — `_positional_or_keyword_count` — `def _positional_or_keyword_count(node: ast.FunctionDef | ast.AsyncFunctionDef, *, is_method: bool) -> int`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:232` — `_def_line_has_escape_hatch` — `def _def_line_has_escape_hatch(node: ast.FunctionDef | ast.AsyncFunctionDef, *, source_lines: list[str]) -> bool`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:240` — `_qualify` — `def _qualify(name: str, *, class_stack: tuple[str, ...], func_stack: tuple[str, ...]) -> str`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:245` — `_evaluate_def` — `def _evaluate_def(node: ast.FunctionDef | ast.AsyncFunctionDef, *, module_qname: str, relative_path: str, class_stack: tuple[str, ...], func_stack: tuple[str, ...], is_method: bool, source_lines: list[str]) -> Violation | None`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:327` — `find_violations_in_source` — `def find_violations_in_source(source: str, *, module_qname: str, relative_path: str) -> list[Violation]`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:381` — `relative_source_path` — `def relative_source_path(path: Path, *, root: Path | None=None) -> Path | None`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:407` — `collect_violations_for_files` — `def collect_violations_for_files(paths: Iterable[Path], *, root: Path | None=None) -> list[Violation]`
- `pipelex/cli/dev_cli/commands/kit_cmd.py:31` — `_sync_agent_rules` — `def _sync_agent_rules(repo_root: Path | None, *, agent_set: str | None, cleanup: bool, kit_index: KitIndex | None=None, targets_filter: list[AgentTarget] | None=None) -> None`
- `pipelex/cli/dev_cli/commands/kit_cmd.py:91` — `_cleanup_other_targets` — `def _cleanup_other_targets(repo_root: Path, *, kit_index: KitIndex, preferred_targets: list[AgentTarget]) -> None`
- `pipelex/cli/dev_cli/commands/preprocess_test_models_cmd.py:247` — `_process_collections_from_toml` — `def _process_collections_from_toml(collections_raw: Any, *, collections: dict[str, dict[str, list[str]]]) -> None`
- `pipelex/cli/dev_cli/commands/preprocess_test_models_cmd.py:292` — `_resolve_model_list` — `def _resolve_model_list(raw_list: list[str], *, collections: dict[str, list[str]], backend_models: dict[str, list[str]], all_known_models: list[str]) -> list[str]`
- `pipelex/cli/dev_cli/commands/preprocess_test_models_cmd.py:367` — `_filter_models_by_profile` — `def _filter_models_by_profile(availability: dict[str, Any], *, profile: dict[str, Any], collections: dict[str, dict[str, list[str]]]) -> dict[str, list[tuple[str, str]]]`
- `pipelex/cli/dev_cli/commands/preprocess_test_models_cmd.py:498` — `_generate_fixtures_python` — `def _generate_fixtures_python(combo_pairs: dict[str, list[tuple[str, str]]], *, profile_name: str) -> str`
- `pipelex/cli/dev_cli/commands/preprocess_test_models_cmd.py:561` — `_display_summary` — `def _display_summary(availability: dict[str, Any], *, combo_pairs: dict[str, list[tuple[str, str]]], profile_name: str, console: Console) -> None`
- `pipelex/cli/dev_cli/commands/preprocess_test_models_cmd.py:611` — `preprocess_test_models_cmd` — `def preprocess_test_models_cmd(profile: str='dev', *, generate_fixtures: bool=False, output_json: bool=False, quiet: bool=False) -> None`
- `pipelex/cli/dev_cli/commands/refresh_graph_ui_sri_cmd.py:86` — `_validate_version` — `def _validate_version(name: str, *, value: str) -> str`
- `pipelex/cli/dev_cli/commands/refresh_graph_ui_sri_cmd.py:106` — `_fetch` — `def _fetch(url: str, *, timeout: float=30.0) -> bytes`
- `pipelex/cli/dev_cli/commands/refresh_graph_ui_sri_cmd.py:148` — `refresh_graph_ui_sri_cmd` — `def refresh_graph_ui_sri_cmd(mthds_ui_version: str | None=None, *, elkjs_version: str | None=None, output_path: Path | None=None, quiet: bool=False) -> None`
- `pipelex/cli/dev_cli/commands/sync_kit_configs_cmd.py:20` — `_display_result` — `def _display_result(result: MirrorDirResult, *, quiet: bool) -> None`
- `pipelex/cli/dev_cli/commands/sync_kit_configs_cmd.py:86` — `sync_kit_configs_cmd` — `def sync_kit_configs_cmd(quiet: bool=False, *, dry_run: bool=False) -> None`
- `pipelex/cli/dev_cli/commands/sync_main_config_cmd.py:38` — `_display_sync_result` — `def _display_sync_result(result: TomlSyncResult, *, target_label: str, show_diff: bool, quiet: bool) -> None`
- `pipelex/cli/dev_cli/commands/sync_main_config_cmd.py:77` — `sync_main_config_cmd` — `def sync_main_config_cmd(target: SyncTarget=SyncTarget.ALL, *, dry_run: bool=False, quiet: bool=False, show_diff: bool=True) -> None`
- `pipelex/cli/dev_cli/commands/update_gateway_models_cmd.py:41` — `_all_references_up_to_date` — `def _all_references_up_to_date(reference_files: list[tuple[Path, Path]], *, expected_html: str, expected_plain: str) -> bool`
- `pipelex/cli/error_handlers.py:86` — `display_error_panel` — `def display_error_panel(console: Console, *, title: str, fields: list[tuple[str, str]], error_message: str | None, tip: str, links: list[tuple[str, str]]) -> None`
- `pipelex/cli/error_handlers.py:125` — `handle_model_choice_error` — `def handle_model_choice_error(exc: PipeOperatorModelChoiceError, *, context: ErrorContext) -> NoReturn`
- `pipelex/cli/error_handlers.py:156` — `handle_model_availability_error` — `def handle_model_availability_error(exc: PipeOperatorModelAvailabilityError, *, context: ErrorContext) -> NoReturn`
- `pipelex/cli/error_handlers.py:193` — `handle_model_deck_preset_error` — `def handle_model_deck_preset_error(exc: ModelDeckPresetValidatonError, *, context: ErrorContext) -> NoReturn`
- `pipelex/cli/error_handlers.py:248` — `_display_validation_error_details` — `def _display_validation_error_details(console: Console, *, exc: ValidateBundleError) -> None`
- `pipelex/cli/error_handlers.py:325` — `handle_signatures_not_allowed_error` — `def handle_signatures_not_allowed_error(exc: SignaturesNotAllowedError, *, context: ErrorContext) -> NoReturn`
- `pipelex/cli/error_handlers.py:343` — `handle_validate_bundle_error` — `def handle_validate_bundle_error(exc: ValidateBundleError, *, bundle_path: Path | None=None) -> NoReturn`
- `pipelex/cli/installed_methods.py:43` — `discover_installed_methods` — `def discover_installed_methods(include_global: bool=True, *, include_project: bool=True, extra_search_dirs: list[Path] | None=None) -> list[InstalledMethod]`
- `pipelex/cli/installed_methods.py:112` — `discover_method_at` — `def discover_method_at(method_dir: Path, *, seen_dirs: set[Path]) -> InstalledMethod | None`
- `pipelex/cli/installed_methods.py:184` — `find_method_by_full_address` — `def find_method_by_full_address(full_address: str, *, methods: list[InstalledMethod] | None=None, extra_search_dirs: list[Path] | None=None) -> InstalledMethod | None`
- `pipelex/cli/installed_methods.py:216` — `find_method_by_name` — `def find_method_by_name(method_name: str, *, methods: list[InstalledMethod] | None=None, library_dirs: list[str] | None=None) -> InstalledMethod`
- `pipelex/cli/method_resolver.py:227` — `resolve_method_target` — `def resolve_method_target(method_name: str, *, pipe_override: str | None=None, library_dirs: list[str] | None=None) -> tuple[str, list[str], InstalledMethod]`

### `cogt` (119)

- `pipelex/cogt/config_cogt.py:30` — `ImgGenConfig.get_num_inference_steps` — `def get_num_inference_steps(self, model_name: str, *, quality: Quality) -> int`
- `pipelex/cogt/config_cogt.py:96` — `LLMConfig.get_reasoning_budget` — `def get_reasoning_budget(self, prompting_target: str, *, effort: ReasoningEffort) -> int`
- `pipelex/cogt/content_generation/assignment_models.py:87` — `ObjectAssignment.make_for_class` — `def make_for_class(object_class: type[BaseModel], *, llm_assignment: LLMAssignment, nb_items: int | None=None) -> 'ObjectAssignment'`
- `pipelex/cogt/content_generation/assignment_models.py:177` — `SearchObjectAssignment.make_for_class` — `def make_for_class(output_class: type[BaseModel], *, search_assignment: SearchAssignment) -> 'SearchObjectAssignment'`
- `pipelex/cogt/content_generation/content_generator.py:44` — `_revalidate_against_object_class` — `def _revalidate_against_object_class(raw_obj: BaseModel, *, object_class: type[BaseModelTypeVar], is_mock_built: bool) -> BaseModelTypeVar`
- `pipelex/cogt/content_generation/dry_mock.py:143` — `report_dry_llm_job` — `def report_dry_llm_job(job_metadata: JobMetadata, *, llm_setting: LLMSetting, llm_prompt: LLMPrompt) -> None`
- `pipelex/cogt/content_generation/dry_mock.py:155` — `report_mock_usage_llm_job` — `def report_mock_usage_llm_job(job_metadata: JobMetadata, *, llm_setting: LLMSetting, llm_prompt: LLMPrompt) -> None`
- `pipelex/cogt/content_generation/dry_mock.py:186` — `build_mock_objects` — `def build_mock_objects(model_class: type[BaseModelTypeVar], *, count: int) -> list[BaseModelTypeVar]`
- `pipelex/cogt/content_generation/dry_mock.py:240` — `_leaf_gen_object` — `def _leaf_gen_object(object_assignment: ObjectAssignment, *, report_func: _ReportLLMJobFunc) -> BaseModel`
- `pipelex/cogt/content_generation/dry_mock.py:262` — `_leaf_gen_object_list` — `def _leaf_gen_object_list(object_assignment: ObjectAssignment, *, report_func: _ReportLLMJobFunc) -> list[BaseModel]`
- `pipelex/cogt/content_generation/dry_mock.py:343` — `_dry_image_content` — `def _dry_image_content(image_url: str, *, img_gen_assignment: ImgGenAssignment | None=None) -> ImageContent`
- `pipelex/cogt/content_generation/dry_run_factory.py:197` — `DryRunFactory._find_nested_base_model_classes` — `def _find_nested_base_model_classes(cls, object_class: type[BaseModel], *, visited: set[type[BaseModel]] | None=None) -> set[type[BaseModel]]`
- `pipelex/cogt/content_generation/dry_run_factory.py:339` — `DryRunFactory.make_dry_run_factory` — `def make_dry_run_factory(cls, object_class: type[BaseModelTypeVar], *, snake_case_field_names: set[str] | None=None, pascal_case_field_names: set[str] | None=None) -> type[ModelFactory[BaseModelTypeVar]]`
- `pipelex/cogt/content_generation/extract_generate.py:21` — `extract_gen_pages_and_store` — `async def extract_gen_pages_and_store(extract_assignment: ExtractAssignment, *, generated_content_factory: GeneratedContentFactory) -> list[PageContent]`
- `pipelex/cogt/content_generation/generated_content_factory.py:25` — `GeneratedContentFactory._build_storage_key` — `def _build_storage_key(self, primary_id: str, *, secondary_id: str, data: bytes, mime_type: str | None, image_format: ImageFormat | None) -> str`
- `pipelex/cogt/content_generation/generated_content_factory.py:68` — `GeneratedContentFactory.make_image_content` — `async def make_image_content(self, primary_id: str, *, secondary_id: str, raw_details: GeneratedImageRawDetails) -> ImageContent`
- `pipelex/cogt/content_generation/generated_content_factory.py:161` — `GeneratedContentFactory.make_page_contents` — `async def make_page_contents(self, primary_id: str, *, secondary_id: str, extract_output: ExtractOutput) -> list[PageContent]`
- `pipelex/cogt/content_generation/img_gen_generate.py:40` — `img_gen_single_image_and_store` — `async def img_gen_single_image_and_store(img_gen_assignment: ImgGenAssignment, *, generated_content_factory: GeneratedContentFactory) -> ImageContent`
- `pipelex/cogt/content_generation/img_gen_generate.py:66` — `img_gen_image_list_and_store` — `async def img_gen_image_list_and_store(img_gen_assignment: ImgGenAssignment, *, generated_content_factory: GeneratedContentFactory) -> list[ImageContent]`
- `pipelex/cogt/content_generation/render_generate.py:17` — `render_page_views_and_store` — `async def render_page_views_and_store(render_assignment: RenderPageViewsAssignment, *, generated_content_factory: GeneratedContentFactory) -> list[ImageContent]`
- `pipelex/cogt/content_generation/schema_to_model_factory.py:82` — `SchemaToModelFactory.make_from_json_schema` — `def make_from_json_schema(cls, schema: dict[str, Any], *, class_name: str) -> type[BaseModel]`
- `pipelex/cogt/content_generation/schema_to_model_factory.py:126` — `SchemaToModelFactory._collect_unsafe_extension_paths` — `def _collect_unsafe_extension_paths(cls, node: Any, *, path: str, found: list[str]) -> None`
- `pipelex/cogt/content_generation/schema_to_model_factory.py:319` — `SchemaToModelFactory._exec_and_extract_class` — `def _exec_and_extract_class(cls, source_code: str, *, class_name: str) -> type[BaseModel]`
- `pipelex/cogt/document/prompt_document_factory.py:18` — `PromptDocumentFactory.make_prompt_document` — `def make_prompt_document(cls, uri: str | None=None, *, base64_data: str | None=None, raw_bytes: bytes | None=None, mime_type: str | None=None) -> PromptDocument`
- `pipelex/cogt/document/prompt_document_utils.py:30` — `prepare_prompt_document` — `async def prepare_prompt_document(prompt_document: PromptDocument, *, is_http_url_enabled: bool) -> PreparedFile`
- `pipelex/cogt/document/prompt_document_utils.py:96` — `prep_prompt_documents` — `async def prep_prompt_documents(prompt_documents: list[PromptDocument], *, is_http_url_enabled: bool) -> list[PreparedFile]`
- `pipelex/cogt/exceptions.py:68` — `CogtError.fill_model_and_provider` — `def fill_model_and_provider(self, model_handle: str | None, *, backend_name: str | None) -> None`
- `pipelex/cogt/extract/extract_job_factory.py:9` — `ExtractJobFactory.make_extract_job` — `def make_extract_job(cls, extract_input: ExtractInput, *, job_metadata: JobMetadata, extract_job_params: ExtractJobParams | None=None, extract_job_config: ExtractJobConfig | None=None) -> ExtractJob`
- `pipelex/cogt/extract/extract_worker_factory.py:13` — `ExtractWorkerFactory.make_extract_worker` — `def make_extract_worker(cls, inference_model: InferenceModelSpec, *, reporting_delegate: ReportingProtocol | None=None) -> ExtractWorkerAbstract`
- `pipelex/cogt/file/file_preparation_utils.py:24` — `prepare_file_from_uri` — `async def prepare_file_from_uri(uri: str, *, keep_http_url: bool, keep_local_path: bool) -> PreparedFile`
- `pipelex/cogt/image/generated_image.py:61` — `GeneratedImageRawDetails.make_from_pil_image` — `def make_from_pil_image(cls, pil_image: Image.Image, *, image_format: ImageFormat) -> GeneratedImageRawDetails`
- `pipelex/cogt/image/prompt_image_factory.py:18` — `PromptImageFactory.make_prompt_image` — `def make_prompt_image(cls, uri: str | None=None, *, base64_data: str | None=None, raw_bytes: bytes | None=None) -> PromptImage`
- `pipelex/cogt/image/prompt_image_utils.py:30` — `prepare_prompt_image` — `async def prepare_prompt_image(prompt_image: PromptImage, *, is_http_url_enabled: bool) -> PreparedFile`
- `pipelex/cogt/image/prompt_image_utils.py:97` — `prep_prompt_images` — `async def prep_prompt_images(prompt_images: list[PromptImage], *, is_http_url_enabled: bool) -> list[PreparedFile]`
- `pipelex/cogt/img_gen/img_gen_args_factory.py:49` — `ImgGenArgsFactory.make_args_for_model` — `async def make_args_for_model(cls, model_rules: ImgGenModelRules, *, img_gen_job: ImgGenJob, nb_images: int, model_id: str, model_name: str) -> dict[str, Any]`
- `pipelex/cogt/img_gen/img_gen_args_factory.py:199` — `ImgGenArgsFactory.make_args_from_num_images` — `def make_args_from_num_images(cls, num_images_taxonomy: NumImagesTaxonomy, *, nb_images: int) -> dict[str, Any]`
- `pipelex/cogt/img_gen/img_gen_args_factory.py:208` — `ImgGenArgsFactory.make_args_from_prompt` — `def make_args_from_prompt(cls, prompt_taxonomy: PromptTaxonomy, *, positive_text: str, negative_text: str | None) -> dict[str, Any]`
- `pipelex/cogt/img_gen/img_gen_args_factory.py:238` — `ImgGenArgsFactory.make_args_from_model_name` — `def make_args_from_model_name(cls, model_name_taxonomy: ModelChoiceTaxonomy, *, model_id: str, model_name: str) -> dict[str, Any]`
- `pipelex/cogt/img_gen/img_gen_args_factory.py:253` — `ImgGenArgsFactory.make_args_from_background` — `def make_args_from_background(cls, background_taxonomy: BackgroundTaxonomy, *, background: Background, model_name: str) -> dict[str, Any]`
- `pipelex/cogt/img_gen/img_gen_args_factory.py:270` — `ImgGenArgsFactory.make_args_from_aspect_ratio` — `def make_args_from_aspect_ratio(cls, aspect_ratio_taxonomy: AspectRatioTaxonomy, *, aspect_ratio: AspectRatio, size: ImageSize | None, model_name: str) -> dict[str, Any]`
- `pipelex/cogt/img_gen/img_gen_args_factory.py:373` — `ImgGenArgsFactory.make_args_from_inference` — `def make_args_from_inference(cls, inference_taxonomy: InferenceTaxonomy, *, num_inference_steps: int | None, quality: Quality | None, guidance_scale: float | None, is_raw: bool | None) -> dict[str, Any]`
- `pipelex/cogt/img_gen/img_gen_args_factory.py:425` — `ImgGenArgsFactory.make_args_from_safety_checker` — `def make_args_from_safety_checker(cls, safety_checker_taxonomy: SafetyCheckerTaxonomy, *, is_moderated: bool | None, safety_tolerance: int | None) -> dict[str, Any]`
- `pipelex/cogt/img_gen/img_gen_args_factory.py:454` — `ImgGenArgsFactory.make_args_from_output_format` — `def make_args_from_output_format(cls, output_format_taxonomy: OutputFormatTaxonomy, *, output_format: ImageFormat | None) -> dict[str, Any]`
- `pipelex/cogt/img_gen/img_gen_args_factory.py:525` — `ImgGenArgsFactory.make_args_from_input_images` — `async def make_args_from_input_images(cls, input_images_taxonomy: InputImagesTaxonomy, *, input_images: list[PromptImage] | None) -> dict[str, Any]`
- `pipelex/cogt/img_gen/img_gen_args_factory.py:584` — `ImgGenArgsFactory.make_args_from_input_fidelity` — `def make_args_from_input_fidelity(cls, input_fidelity_taxonomy: InputFidelityTaxonomy, *, input_fidelity: InputFidelity | None, model_name: str) -> dict[str, Any]`
- `pipelex/cogt/img_gen/img_gen_job_factory.py:10` — `ImgGenJobFactory.make_img_gen_job_from_prompt` — `def make_img_gen_job_from_prompt(cls, img_gen_prompt: ImgGenPrompt, *, job_metadata: JobMetadata, img_gen_job_params: ImgGenJobParams | None=None, img_gen_job_config: ImgGenJobConfig | None=None) -> ImgGenJob`
- `pipelex/cogt/img_gen/img_gen_job_factory.py:32` — `ImgGenJobFactory.make_img_gen_job_from_prompt_contents` — `def make_img_gen_job_from_prompt_contents(cls, positive_text: str, *, negative_text: str | None, job_metadata: JobMetadata, img_gen_job_params: ImgGenJobParams | None=None, img_gen_job_config: ImgGenJobConfig | None=None) -> ImgGenJob`
- `pipelex/cogt/img_gen/img_gen_worker_abstract.py:81` — `ImgGenWorkerAbstract.gen_image_list` — `async def gen_image_list(self, img_gen_job: ImgGenJob, *, nb_images: int) -> list[GeneratedImageRawDetails]`
- `pipelex/cogt/img_gen/img_gen_worker_abstract.py:116` — `ImgGenWorkerAbstract._gen_image_list` — `async def _gen_image_list(self, img_gen_job: ImgGenJob, *, nb_images: int) -> list[GeneratedImageRawDetails]`
- `pipelex/cogt/img_gen/img_gen_worker_factory.py:14` — `ImgGenWorkerFactory.make_img_gen_worker` — `def make_img_gen_worker(cls, inference_model: InferenceModelSpec, *, reporting_delegate: ReportingProtocol | None=None) -> ImgGenWorkerAbstract`
- `pipelex/cogt/inference/error_classification.py:47` — `_resolve_sdk_exception_type` — `def _resolve_sdk_exception_type(exc: BaseException, *, status_code: int | None) -> str`
- `pipelex/cogt/inference/error_classification.py:249` — `_is_quota_exhaustion_mistral` — `def _is_quota_exhaustion_mistral(error_message: str, *, status_code: int) -> bool`
- `pipelex/cogt/inference/error_classification.py:261` — `_is_quota_exhaustion_aws` — `def _is_quota_exhaustion_aws(error_message: str, *, provider_error_code: str | None) -> bool`
- `pipelex/cogt/inference/error_classification.py:276` — `_is_quota_exhaustion_gateway` — `def _is_quota_exhaustion_gateway(error_message: str, *, status_code: int) -> bool`
- `pipelex/cogt/inference/error_classification.py:586` — `extract_azure_metadata_from_response` — `def extract_azure_metadata_from_response(response: Any, *, sdk_exception_type: str, message: str) -> ProviderErrorMetadata`
- `pipelex/cogt/inference/error_classification.py:597` — `_build_azure_metadata` — `def _build_azure_metadata(response: Any, *, sdk_exception_type: str, message: str) -> ProviderErrorMetadata`
- `pipelex/cogt/inference/error_classification.py:878` — `extract_local_extract_metadata` — `def extract_local_extract_metadata(exc: BaseException, *, provider: ProviderName) -> ProviderErrorMetadata`
- `pipelex/cogt/inference/error_render.py:53` — `_format_message` — `def _format_message(metadata: SDKErrorEnvelope, *, model_desc: str) -> str`
- `pipelex/cogt/inference/error_render.py:59` — `_render_detail` — `def _render_detail(metadata: SDKErrorEnvelope, *, classification: ClassificationResult) -> str`
- `pipelex/cogt/inference/error_render.py:80` — `render_inference_error` — `def render_inference_error(metadata: SDKErrorEnvelope, *, classification: ClassificationResult, family: InferenceErrorFamily, model_desc: str, model_handle: str) -> CogtError`
- `pipelex/cogt/inference/inference_manager_protocol.py:21` — `InferenceManagerProtocol.set_llm_worker_from_external_plugin` — `def set_llm_worker_from_external_plugin(self, llm_handle: str, *, llm_worker_class: type[LLMWorkerAbstract], should_warn_if_already_registered: bool=True)`
- `pipelex/cogt/inference/transport_retry.py:110` — `request_with_transport_retry` — `async def request_with_transport_retry(send_request: Callable[[], Awaitable[httpx.Response]], *, max_retries: int, retry_on_ambiguous_failure: bool=True) -> httpx.Response`
- `pipelex/cogt/llm/llm_job_factory.py:10` — `LLMJobFactory.make_llm_job` — `def make_llm_job(cls, llm_prompt: LLMPrompt, *, job_metadata: JobMetadata, llm_job_params: LLMJobParams, llm_job_config: LLMJobConfig | None=None) -> LLMJob`
- `pipelex/cogt/llm/llm_prompt_template.py:58` — `LLMPromptTemplate._make_llm_prompt` — `async def _make_llm_prompt(self, system_text: str | None=None, *, user_text: str | None=None, user_images: list[PromptImage] | None=None, is_user_images_append: bool | None=None, template_inputs: LLMPromptTemplateInputs | None=None) -> LLMPrompt`
- `pipelex/cogt/llm/llm_setting.py:95` — `LLMSettingChoices.make_completed_with_defaults` — `def make_completed_with_defaults(cls, for_text: LLMModelChoice | None=None, *, for_object: LLMModelChoice | None=None) -> Self`
- `pipelex/cogt/llm/llm_worker_abstract.py:86` — `LLMWorkerAbstract._start_otel_span_llm` — `def _start_otel_span_llm(self, llm_job: LLMJob, *, output_type: InferenceOutputType, output_class_name: str | None=None) -> Span | None`
- `pipelex/cogt/llm/llm_worker_abstract.py:231` — `LLMWorkerAbstract._end_otel_span_with_completion_text` — `def _end_otel_span_with_completion_text(self, span: Span | None, *, llm_job: LLMJob, completion_text: str) -> None`
- `pipelex/cogt/llm/llm_worker_abstract.py:262` — `LLMWorkerAbstract._end_otel_span_with_completion_object` — `def _end_otel_span_with_completion_object(self, span: Span | None, *, llm_job: LLMJob, completion_object: BaseModel) -> None`
- `pipelex/cogt/llm/llm_worker_abstract.py:294` — `LLMWorkerAbstract._end_otel_span_with_error` — `def _end_otel_span_with_error(self, span: Span | None, *, llm_job: LLMJob, error: BaseException) -> None`
- `pipelex/cogt/llm/llm_worker_abstract.py:398` — `LLMWorkerAbstract.gen_object` — `async def gen_object(self, llm_job: LLMJob, *, schema: type[BaseModelTypeVar]) -> BaseModelTypeVar`
- `pipelex/cogt/llm/llm_worker_abstract.py:436` — `LLMWorkerAbstract._gen_object` — `async def _gen_object(self, llm_job: LLMJob, *, schema: type[BaseModelTypeVar]) -> BaseModelTypeVar`
- `pipelex/cogt/llm/llm_worker_factory.py:13` — `LLMWorkerFactory.make_llm_worker` — `def make_llm_worker(inference_model: InferenceModelSpec, *, reporting_delegate: ReportingProtocol | None=None) -> LLMWorkerInternalAbstract`
- `pipelex/cogt/llm/reasoning_config_base.py:9` — `validate_effort_to_level_map` — `def validate_effort_to_level_map(effort_to_level_map: EffortToLevelMap, *, config_name: str, level_type: type[StrEnum] | None=None) -> EffortToLevelMap`
- `pipelex/cogt/llm/reasoning_config_base.py:40` — `get_reasoning_level_str` — `def get_reasoning_level_str(effort_to_level_map: EffortToLevelMap, *, effort: ReasoningEffort) -> str | None`
- `pipelex/cogt/model_backends/backend_credentials.py:26` — `BackendCredentialsErrorMsgFactory.make_one_variable_missing_error_msg` — `def make_one_variable_missing_error_msg(cls, secrets_provider: SecretsProviderAbstract, *, backend_name: str | None, var_name: str) -> str`
- `pipelex/cogt/model_backends/backend_credentials.py:78` — `BackendCredentialsErrorMsgFactory.make_comprehensive_error_msg` — `def make_comprehensive_error_msg(cls, backend_credential_reports: dict[str, BackendCredentialsReport], *, secrets_provider: SecretsProviderAbstract | None=None) -> str`
- `pipelex/cogt/model_backends/backend_factory.py:39` — `InferenceBackendFactory.make_inference_backend` — `def make_inference_backend(cls, name: str, *, blueprint: InferenceBackendBlueprint, extra_config: dict[str, Any], model_specs: dict[str, InferenceModelSpec]) -> InferenceBackend`
- `pipelex/cogt/model_backends/backend_library.py:58` — `InferenceBackendLibrary.load` — `def load(self, secrets_provider: SecretsProviderAbstract, *, backends_library_path: str, backends_dir_path: str, include_disabled: bool=False, gateway_config: GatewayConfig | None=None, lenient: bool=False)`
- `pipelex/cogt/model_backends/backend_library.py:228` — `InferenceBackendLibrary._load_gateway_model_specs` — `def _load_gateway_model_specs(self, gateway_config: GatewayConfig, *, backends_dir_path: str, substitute_vars_with_provider: Any) -> tuple[BackendModelSpecs, str]`
- `pipelex/cogt/model_backends/backend_library.py:267` — `InferenceBackendLibrary._load_local_model_specs` — `def _load_local_model_specs(self, backend_name: str, *, backends_dir_path: str, substitute_vars_with_provider: Any) -> tuple[BackendModelSpecs, str]`
- `pipelex/cogt/model_backends/backend_library.py:300` — `InferenceBackendLibrary.check_backend_credentials` — `def check_backend_credentials(self, path: str, *, include_disabled: bool=False) -> CredentialsValidationReport`
- `pipelex/cogt/model_backends/model_lists.py:17` — `ModelLister.list_models` — `async def list_models(cls, backend_name: str, *, flat: bool=False) -> None`
- `pipelex/cogt/model_backends/model_lists.py:194` — `ModelLister._display_unsupported_sdks_message` — `def _display_unsupported_sdks_message(any_listed: bool, *, unsupported_sdks: list[str], backend_name: str, models_by_sdk: dict[str, list[str]], flat: bool) -> None`
- `pipelex/cogt/model_backends/model_spec_factory.py:78` — `InferenceModelSpecFactory.make_inference_model_spec` — `def make_inference_model_spec(cls, backend_name: str, *, name: str, blueprint: InferenceModelSpecBlueprint, backend_listed_constraints: list[ListedConstraint], backend_valued_constraints: dict[ValuedConstraint, Any], extra_headers: dict[str, str] | None=None) -> InferenceModelSpec`
- `pipelex/cogt/model_routing/routing_profile.py:25` — `RoutingProfile.get_backend_match_for_model` — `def get_backend_match_for_model(self, enabled_backends: list[str], *, model_name: str) -> BackendMatchForModel | None`
- `pipelex/cogt/model_routing/routing_profile_factory.py:38` — `RoutingProfileFactory.make_routing_profile` — `def make_routing_profile(cls, name: str, *, blueprint: RoutingProfileBlueprint) -> RoutingProfile`
- `pipelex/cogt/model_routing/routing_profile_loader.py:11` — `load_active_routing_profile` — `def load_active_routing_profile(routing_profile_library_path: str, *, enabled_backends: list[str], lenient: bool=False) -> RoutingProfile`
- `pipelex/cogt/models/deck_manifest.py:155` — `write_manifest` — `def write_manifest(manifest: DeckManifest, *, deck_dir: Path) -> None`
- `pipelex/cogt/models/deck_manifest.py:179` — `_is_manifest_older` — `def _is_manifest_older(manifest_version: str, *, current_version: str) -> bool`
- `pipelex/cogt/models/model_deck.py:135` — `ModelDeck.is_model_handle_defined` — `def is_model_handle_defined(self, model_handle: str, *, model_type: ModelType) -> bool`
- `pipelex/cogt/models/model_deck.py:219` — `ModelDeck._raise_handle_not_found_error` — `def _raise_handle_not_found_error(self, ref: ModelReference, *, model_type: ModelType, presets: dict[str, LLMSetting] | dict[str, ExtractSetting] | dict[str, ImgGenSetting] | dict[str, SearchSetting]) -> NoReturn`
- `pipelex/cogt/models/model_deck.py:250` — `ModelDeck.check_llm_choice` — `def check_llm_choice(self, llm_choice: LLMModelChoice, *, is_disabled_allowed: bool=False)`
- `pipelex/cogt/models/model_deck.py:524` — `ModelDeck._validate_llm_setting` — `def _validate_llm_setting(cls, llm_setting: LLMSetting, *, inference_model: InferenceModelSpec)`
- `pipelex/cogt/models/model_deck.py:689` — `ModelDeck._is_model_available_in_backend` — `def _is_model_available_in_backend(self, model_handle: str, *, backend_name: str) -> bool | None`
- `pipelex/cogt/models/model_deck.py:715` — `ModelDeck._resolve_waterfall` — `def _resolve_waterfall(self, waterfall_name: str, *, fallback_list: list[str], model_type: ModelType) -> InferenceModelSpec | None`
- `pipelex/cogt/models/model_deck.py:774` — `ModelDeck.get_optional_inference_model` — `def get_optional_inference_model(self, model_handle: str, *, model_type: ModelType) -> InferenceModelSpec | None`
- `pipelex/cogt/models/model_deck.py:786` — `ModelDeck._get_optional_inference_model` — `def _get_optional_inference_model(self, model_handle: str, *, model_type: ModelType, _visited: frozenset[str]) -> InferenceModelSpec | None`
- `pipelex/cogt/models/model_deck.py:862` — `ModelDeck.is_handle_defined` — `def is_handle_defined(self, model_handle: str, *, model_type: ModelType) -> bool`
- `pipelex/cogt/models/model_deck.py:866` — `ModelDeck.get_required_inference_model` — `def get_required_inference_model(self, model_handle: str, *, model_type: ModelType) -> InferenceModelSpec`
- `pipelex/cogt/models/model_deck_check.py:17` — `_raise_model_choice_not_found` — `def _raise_model_choice_not_found(msg: str, *, model_deck: ModelDeck, model_type: ModelType, raw_choice: str, name: str, reference_kind: ModelReferenceKind, available_options: list[str]) -> NoReturn`
- `pipelex/cogt/models/model_manager.py:100` — `ModelManager._enforce_gateway_model_membership` — `def _enforce_gateway_model_membership(self, gateway_config: GatewayConfig | None, *, gateway_config_source: RemoteConfigSource | None) -> None`
- `pipelex/cogt/models/model_manager.py:193` — `ModelManager._resolve_terminal_candidates` — `def _resolve_terminal_candidates(cls, deck: ModelDeck, *, ref: ModelReference, model_type: ModelType) -> list[str]`
- `pipelex/cogt/models/model_manager.py:226` — `ModelManager._collect_candidates` — `def _collect_candidates(cls, ref: ModelReference, *, aliases: dict[str, str], waterfalls: dict[str, list[str]], is_fallback_enabled: bool, visited: set[tuple[ModelReferenceKind, str]]) -> list[str]`
- `pipelex/cogt/models/model_manager.py:302` — `ModelManager.build_deck` — `def build_deck(self, model_deck_blueprint: ModelDeckBlueprint, *, enabled_backends: list[str]) -> ModelDeck`
- `pipelex/cogt/models/model_manager_abstract.py:22` — `ModelManagerAbstract.setup` — `def setup(self, secrets_provider: SecretsProviderAbstract, *, gateway_config: GatewayConfig | None, gateway_config_source: RemoteConfigSource | None, needs_inference: bool=True) -> None`
- `pipelex/cogt/models/model_manager_abstract.py:33` — `ModelManagerAbstract.get_inference_model` — `def get_inference_model(self, model_handle: str, *, model_type: ModelType) -> InferenceModelSpec`
- `pipelex/cogt/models/model_suggestion.py:33` — `get_collection_keys` — `def get_collection_keys(model_deck: ModelDeck, *, model_type: ModelType, kind: ModelReferenceKind) -> list[str]`
- `pipelex/cogt/models/model_suggestion.py:75` — `suggest_model_alternatives` — `def suggest_model_alternatives(model_deck: ModelDeck, *, model_type: ModelType, name: str, kind: ModelReferenceKind) -> tuple[list[str], list[str], list[str]]`
- `pipelex/cogt/search/search_job_factory.py:8` — `SearchJobFactory.make_search_job` — `def make_search_job(cls, query: str, *, search_setting: SearchSetting, job_metadata: JobMetadata, include_domains: list[str] | None=None, exclude_domains: list[str] | None=None, from_date: str | None=None, to_date: str | None=None) -> SearchJob`
- `pipelex/cogt/search/search_worker_abstract.py:53` — `SearchWorkerAbstract.search_structured` — `async def search_structured(self, search_job: SearchJob, *, schema: type[BaseModelTypeVar]) -> dict[str, Any]`
- `pipelex/cogt/search/search_worker_abstract.py:85` — `SearchWorkerAbstract._search_structured` — `async def _search_structured(self, search_job: SearchJob, *, schema: type[BaseModelTypeVar]) -> dict[str, Any]`
- `pipelex/cogt/templating/template_preprocessor.py:91` — `_validate_at_sigil_alone_on_line` — `def _validate_at_sigil_alone_on_line(template: str, *, declared_inputs: set[str]) -> None`
- `pipelex/cogt/templating/template_preprocessor.py:145` — `validate_template_sigils` — `def validate_template_sigils(template: str, *, declared_inputs: set[str]) -> None`
- `pipelex/cogt/templating/template_preprocessor.py:176` — `preprocess_template` — `def preprocess_template(template: str, *, declared_inputs: set[str] | None=None) -> str`
- `pipelex/cogt/templating/template_rendering.py:10` — `render_template` — `async def render_template(template: str, *, category: TemplateCategory, context: dict[str, Any], templating_style: TemplatingStyle | None=None, finalize: Callable[[Any], Any] | None=None) -> str`
- `pipelex/cogt/usage/cost_registry.py:64` — `CostRegistry.generate_report` — `def generate_report(cls, pipeline_run_id: str, *, tokens_usages: Sequence[TokensUsage], unit_scale: float, cost_report_file_path: Path | None=None, print_to_console: bool=True)`
- `pipelex/cogt/usage/cost_registry.py:88` — `CostRegistry.render_report` — `def render_report(cls, aggregated: AggregatedCosts, *, pipeline_run_id: str, unit_scale: float, cost_report_file_path: Path | None=None, print_to_console: bool=True) -> None`
- `pipelex/cogt/usage/cost_registry.py:195` — `CostRegistry.save_to_csv` — `def save_to_csv(records: list[dict[str, Any]], *, file_path: Path) -> None`
- `pipelex/cogt/usage/costs_per_token.py:4` — `model_cost_per_token` — `def model_cost_per_token(costs: CostsByCategoryDict, *, cost_category: CostCategory) -> float`

### `core` (95)

- `pipelex/core/bundles/pipelex_bundle_blueprint.py:201` — `PipelexBundleBlueprint._collect_local_refs_from_concept` — `def _collect_local_refs_from_concept(self, concept_code: str, *, concept_blueprint: ConceptBlueprint | str) -> list[tuple[str, str]]`
- `pipelex/core/bundles/pipelex_bundle_blueprint.py:224` — `PipelexBundleBlueprint._collect_local_refs_from_pipe` — `def _collect_local_refs_from_pipe(self, pipe_code: str, *, pipe_blueprint: PipeBlueprintUnion) -> list[tuple[str, str]]`
- `pipelex/core/concepts/concept.py:194` — `Concept.render_concept_representation` — `def render_concept_representation(self, output_format: ConceptRepresentationFormat, *, is_multiple: bool=False) -> tuple[dict[str, Any], set[str]]`
- `pipelex/core/concepts/concept_factory.py:88` — `ConceptFactory.make` — `def make(cls, concept_code: str, *, domain_code: str, description: str, structure_class_name: str, refines: str | None=None) -> Concept`
- `pipelex/core/concepts/concept_factory.py:187` — `ConceptFactory.make_domain_and_concept_code_from_concept_ref_or_code` — `def make_domain_and_concept_code_from_concept_ref_or_code(cls, concept_ref_or_code: str, *, domain_code: str | None=None) -> DomainAndConceptCode`
- `pipelex/core/concepts/concept_factory.py:243` — `ConceptFactory.make_refine` — `def make_refine(cls, refine: str, *, domain_code: str) -> str`
- `pipelex/core/concepts/concept_factory.py:274` — `ConceptFactory._handle_structure_with_classname` — `def _handle_structure_with_classname(cls, blueprint: ConceptBlueprint, *, concept_code: str, domain_code: str) -> str`
- `pipelex/core/concepts/concept_factory.py:301` — `ConceptFactory._handle_blueprint_with_structure` — `def _handle_blueprint_with_structure(cls, blueprint: ConceptBlueprint, *, concept_code: str, domain_code: str) -> str`
- `pipelex/core/concepts/concept_factory.py:345` — `ConceptFactory._handle_basic_blueprint` — `def _handle_basic_blueprint(cls, concept_code: str, *, domain_code: str, description: str) -> StructureNameAndRefine`
- `pipelex/core/concepts/concept_factory.py:386` — `ConceptFactory._handle_refines` — `def _handle_refines(cls, blueprint: ConceptBlueprint, *, concept_code: str, domain_code: str) -> StructureNameAndRefine`
- `pipelex/core/concepts/concept_representation_generator.py:50` — `ConceptRepresentationGenerator.generate_representation` — `def generate_representation(self, concept_ref: str, *, structure_class: type[StuffContent], include_optional: bool=True) -> dict[str, Any]`
- `pipelex/core/concepts/concept_representation_generator.py:75` — `ConceptRepresentationGenerator.generate_class_representation` — `def generate_class_representation(self, content_class: type[StuffContent], *, include_optional: bool=True) -> dict[str, Any] | str`
- `pipelex/core/concepts/concept_representation_generator.py:107` — `ConceptRepresentationGenerator._generate_fields_dict` — `def _generate_fields_dict(self, content_class: type[StuffContent], *, include_optional: bool=True) -> dict[str, Any]`
- `pipelex/core/concepts/concept_representation_generator.py:135` — `ConceptRepresentationGenerator.generate_field_value` — `def generate_field_value(self, field_type: Any, *, field_name: str) -> Any`
- `pipelex/core/concepts/concept_representation_generator.py:199` — `ConceptRepresentationGenerator._generate_list_value` — `def _generate_list_value(self, args: tuple[Any, ...], *, field_name: str) -> list[Any]`
- `pipelex/core/concepts/concept_representation_generator.py:238` — `ConceptRepresentationGenerator._generate_literal_value` — `def _generate_literal_value(self, literal_args: tuple[Any, ...], *, field_name: str) -> Any`
- `pipelex/core/concepts/concept_representation_generator.py:253` — `ConceptRepresentationGenerator._generate_enum_value` — `def _generate_enum_value(self, enum_type: type[StrEnum], *, field_name: str) -> str`
- `pipelex/core/concepts/concept_representation_generator.py:293` — `ConceptRepresentationGenerator._generate_basic_value` — `def _generate_basic_value(self, actual_type: Any, *, field_name: str) -> Any`
- `pipelex/core/concepts/concept_representation_generator.py:329` — `ConceptRepresentationGenerator._format_as_python` — `def _format_as_python(self, class_name: str, *, fields: dict[str, Any]) -> str`
- `pipelex/core/concepts/concept_representation_generator.py:394` — `generate_json_representation` — `def generate_json_representation(concept_ref: str, *, structure_class: type[StuffContent]) -> dict[str, Any]`
- `pipelex/core/concepts/concept_representation_generator.py:412` — `generate_python_representation` — `def generate_python_representation(concept_ref: str, *, structure_class: type[StuffContent]) -> tuple[dict[str, Any], set[str]]`
- `pipelex/core/concepts/concept_structure_blueprint.py:188` — `ConceptStructureBlueprint._raise_type_mismatch_error` — `def _raise_type_mismatch_error(self, expected_type_name: str, *, actual_type_name: str) -> None`
- `pipelex/core/concepts/helpers.py:13` — `get_structure_class_name_from_blueprint` — `def get_structure_class_name_from_blueprint(blueprint_or_string_description: ConceptBlueprint | str, *, concept_ref_or_code: str) -> str`
- `pipelex/core/concepts/structure_generation/generator.py:144` — `StructureGenerator.validate_generated_code` — `def validate_generated_code(self, python_code: str, *, expected_class_name: str, base_class_name: str | None=None) -> type`
- `pipelex/core/concepts/structure_generation/generator.py:211` — `StructureGenerator._format_class_docstring` — `def _format_class_docstring(self, docstring: str, *, indent: str='    ') -> str`
- `pipelex/core/concepts/structure_generation/generator.py:249` — `StructureGenerator._generate_class_source_code_from_blueprint` — `def _generate_class_source_code_from_blueprint(self, class_name: str, *, structure_blueprint: dict[str, ConceptStructureBlueprint], base_class_name: str | None=None, description: str='') -> str`
- `pipelex/core/concepts/structure_generation/generator.py:311` — `StructureGenerator._generate_field_from_blueprint` — `def _generate_field_from_blueprint(self, field_name: str, *, field_blueprint: ConceptStructureBlueprint) -> str`
- `pipelex/core/concepts/structure_generation/generator.py:480` — `StructureGenerator._generate_field` — `def _generate_field(self, field_name: str, *, field_def: dict[str, Any] | str) -> str`
- `pipelex/core/concepts/structure_generation/generator.py:530` — `StructureGenerator._get_python_type` — `def _get_python_type(self, field_type: Any, *, field_def: dict[str, Any]) -> str`
- `pipelex/core/concepts/structure_generation/generator.py:614` — `StructureGenerator._validate_execution` — `def _validate_execution(self, python_code: str, *, expected_class_name: str, base_class_name: str | None=None) -> type`
- `pipelex/core/interpreter/bundle_elaborator.py:105` — `BundleElaborator._elaborate_preliminary_text` — `def _elaborate_preliminary_text(cls, pipe_code: str, *, pipe_blueprint: PipeLLMBlueprint, new_pipe_dict: dict[str, PipeBlueprintUnion], elaboration_metadata: dict[str, ElaborationMetadata], existing_codes: set[str]) -> None`
- `pipelex/core/interpreter/interpreter.py:22` — `PipelexInterpreter.make_pipelex_bundle_blueprint` — `def make_pipelex_bundle_blueprint(cls, bundle_path: Path | None=None, *, mthds_content: str | None=None) -> PipelexBundleBlueprint`
- `pipelex/core/interpreter/validation_error_categorizer.py:27` — `_categorize_input_validation_error` — `def _categorize_input_validation_error(message: str, *, domain: str | None, source: str | None, pipe_code: str | None) -> PipelexBundleBlueprintValidationErrorData | None`
- `pipelex/core/interpreter/validation_error_categorizer.py:74` — `_categorize_syntax_validation_error` — `def _categorize_syntax_validation_error(message: str, *, domain: str | None, source: str | None) -> PipelexBundleBlueprintValidationErrorData | None`
- `pipelex/core/interpreter/validation_error_categorizer.py:127` — `_categorize_concept_validation_error` — `def _categorize_concept_validation_error(loc: tuple[int | str, ...], *, message: str, domain: str | None, source: str | None) -> PipelexBundleBlueprintValidationErrorData | None`
- `pipelex/core/interpreter/validation_error_categorizer.py:172` — `categorize_blueprint_validation_error` — `def categorize_blueprint_validation_error(error: ErrorDetails, *, blueprint_dict: dict[str, Any]) -> PipelexBundleBlueprintValidationErrorData | None`
- `pipelex/core/memory/working_memory.py:146` — `WorkingMemory.set_new_main_stuff` — `def set_new_main_stuff(self, stuff: Stuff, *, name: str | None=None)`
- `pipelex/core/memory/working_memory.py:157` — `WorkingMemory.set_alias` — `def set_alias(self, alias: str, *, target: str) -> None`
- `pipelex/core/memory/working_memory.py:167` — `WorkingMemory.add_alias` — `def add_alias(self, alias: str, *, target: str) -> None`
- `pipelex/core/memory/working_memory.py:329` — `WorkingMemory._get_typed_items_from_list_content` — `def _get_typed_items_from_list_content(self, list_content: ListContent[Any], *, wanted_type: type[Any] | None) -> list[Any] | None`
- `pipelex/core/memory/working_memory.py:370` — `WorkingMemory.get_stuff_as` — `def get_stuff_as(self, name: str, *, content_type: type[StuffContentType]) -> StuffContentType`
- `pipelex/core/memory/working_memory.py:374` — `WorkingMemory.get_stuff_as_list` — `def get_stuff_as_list(self, name: str, *, item_type: type[StuffContentType]) -> ListContent[StuffContentType]`
- `pipelex/core/memory/working_memory.py:380` — `WorkingMemory.get_list_stuff_first_item_as` — `def get_list_stuff_first_item_as(self, name: str, *, item_type: type[StuffContentType]) -> StuffContentType`
- `pipelex/core/memory/working_memory_factory.py:39` — `WorkingMemoryFactory.make_from_multiple_stuffs` — `def make_from_multiple_stuffs(cls, stuff_list: list[Stuff], *, main_name: str | None=None, is_ignore_unnamed: bool=False) -> WorkingMemory`
- `pipelex/core/memory/working_memory_factory.py:68` — `WorkingMemoryFactory.make_from_pipeline_inputs` — `def make_from_pipeline_inputs(cls, pipeline_inputs: PipelineInputs, *, search_domain_codes: list[str] | None=None) -> WorkingMemory`
- `pipelex/core/memory/working_memory_factory.py:150` — `WorkingMemoryFactory.convert_stuff_spec_to_typed_named` — `def convert_stuff_spec_to_typed_named(cls, stuff_spec: StuffSpec, *, name: str) -> TypedNamedStuffSpec`
- `pipelex/core/pipes/handle_pipe_errors.py:119` — `_handle_pipe_errors` — `def _handle_pipe_errors(error: ErrorDetails, *, pipe_code: str | None) -> PipesAndConceptValidationErrorData`
- `pipelex/core/pipes/inputs/input_renderer.py:5` — `render_inputs` — `def render_inputs(the_pipe: PipeAbstract, *, indent: int=2) -> str`
- `pipelex/core/pipes/inputs/input_stuff_specs.py:26` — `TypedNamedStuffSpec.make_from_named` — `def make_from_named(cls, named: NamedStuffSpec, *, structure_class: type[StuffContent]) -> 'TypedNamedStuffSpec'`
- `pipelex/core/pipes/inputs/input_stuff_specs.py:84` — `InputStuffSpecs.add_stuff_spec` — `def add_stuff_spec(self, variable_name: str, *, concept: Concept, multiplicity: VariableMultiplicity | None=None)`
- `pipelex/core/pipes/output/output_renderer.py:16` — `_collect_possible_outputs` — `def _collect_possible_outputs(the_pipe: PipeAbstract, *, output_format: ConceptRepresentationFormat=ConceptRepresentationFormat.JSON) -> list[dict[str, Any]]`
- `pipelex/core/pipes/output/output_renderer.py:119` — `render_output` — `def render_output(the_pipe: PipeAbstract, *, indent: int=2, output_format: ConceptRepresentationFormat=ConceptRepresentationFormat.JSON) -> str`
- `pipelex/core/pipes/output/output_renderer.py:154` — `_render_json_output` — `def _render_json_output(the_pipe: PipeAbstract, *, indent: int=2) -> str`
- `pipelex/core/pipes/output/output_renderer.py:240` — `_render_schema_output` — `def _render_schema_output(the_pipe: PipeAbstract, *, indent: int=2) -> str`
- `pipelex/core/pipes/pipe_abstract.py:103` — `PipeAbstract._register_execution_data` — `def _register_execution_data(self, job_metadata: JobMetadata, *, execution_data: dict[str, Any]) -> None`
- `pipelex/core/pipes/pipe_abstract.py:316` — `PipeAbstract.validate_before_run` — `async def validate_before_run(self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None=None)`
- `pipelex/core/pipes/pipe_abstract.py:369` — `PipeAbstract._validate_before_run` — `async def _validate_before_run(self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None=None)`
- `pipelex/core/pipes/pipe_abstract.py:380` — `PipeAbstract.validate_after_run` — `async def validate_after_run(self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None=None)`
- `pipelex/core/pipes/pipe_abstract.py:393` — `PipeAbstract._validate_after_run` — `async def _validate_after_run(self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None=None)`
- `pipelex/core/pipes/pipe_abstract.py:441` — `PipeAbstract.run_pipe` — `async def run_pipe(self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None=None, library_crate: 'LibraryCrate | None'=None) -> PipeOutput`
- `pipelex/core/pipes/pipe_abstract.py:467` — `PipeAbstract._run_pipe_traced` — `async def _run_pipe_traced(self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None=None, library_crate: 'LibraryCrate | None'=None) -> PipeOutput`
- `pipelex/core/pipes/pipe_abstract.py:630` — `PipeAbstract.live_run_pipe` — `async def live_run_pipe(self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None=None, library_crate: 'LibraryCrate | None'=None) -> PipeOutput`
- `pipelex/core/pipes/pipe_abstract.py:703` — `PipeAbstract.dry_run_pipe` — `async def dry_run_pipe(self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None=None, library_crate: 'LibraryCrate | None'=None) -> PipeOutput`
- `pipelex/core/pipes/pipe_abstract.py:723` — `PipeAbstract._live_run_pipe` — `async def _live_run_pipe(self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None=None, library_crate: 'LibraryCrate | None'=None) -> PipeOutput`
- `pipelex/core/pipes/pipe_abstract.py:735` — `PipeAbstract._dry_run_pipe` — `async def _dry_run_pipe(self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None=None, library_crate: 'LibraryCrate | None'=None) -> PipeOutput`
- `pipelex/core/pipes/pipe_abstract.py:746` — `PipeAbstract._start_pipe_span` — `def _start_pipe_span(self, parent_otel_context: OtelContext, *, pipeline_run_id: str, working_memory: WorkingMemory) -> tuple[Span | None, bool]`
- `pipelex/core/pipes/pipe_abstract.py:862` — `PipeAbstract._end_pipe_span_success` — `def _end_pipe_span_success(self, span: Span | None, *, pipe_output: PipeOutput, is_root_span: bool) -> None`
- `pipelex/core/pipes/pipe_abstract.py:896` — `PipeAbstract._end_pipe_span_error` — `def _end_pipe_span_error(self, span: Span | None, *, error: Exception, is_root_span: bool=False) -> None`
- `pipelex/core/pipes/pipe_factory.py:27` — `PipeFactoryProtocol.make` — `def make(cls, pipe_category: Any, *, pipe_type: str, pipe_code: str, domain_code: str, description: str, inputs: InputStuffSpecs, output: StuffSpec, blueprint: PipeBlueprintType) -> PipeAbstractType`
- `pipelex/core/pipes/validation.py:4` — `is_variable_satisfied_by_inputs` — `def is_variable_satisfied_by_inputs(variable_path: str, *, input_names: set[str]) -> bool`
- `pipelex/core/pipes/validation.py:32` — `is_input_used_by_variables` — `def is_input_used_by_variables(input_name: str, *, variable_paths: set[str]) -> bool`
- `pipelex/core/pipes/variable_multiplicity.py:170` — `format_concept_with_multiplicity` — `def format_concept_with_multiplicity(concept_code_or_string: str, *, multiplicity: VariableMultiplicity | None) -> str`
- `pipelex/core/qualified_ref.py:136` — `QualifiedRef.from_domain_and_code` — `def from_domain_and_code(cls, domain_path: str, *, local_code: str) -> 'QualifiedRef'`
- `pipelex/core/stuffs/image_content.py:71` — `ImageContent.render_with_images` — `def render_with_images(self, registry: ImageRegistry, *, text_format: TextFormat) -> str`
- `pipelex/core/stuffs/image_field_search.py:10` — `search_for_nested_image_fields` — `def search_for_nested_image_fields(content_class: type[StuffContent], *, current_path: str='') -> list[str]`
- `pipelex/core/stuffs/list_content.py:141` — `ListContent.render_with_images` — `def render_with_images(self, registry: ImageRegistry, *, text_format: TextFormat) -> str`
- `pipelex/core/stuffs/structured_content.py:121` — `StructuredContent.render_with_images` — `def render_with_images(self, registry: ImageRegistry, *, text_format: TextFormat) -> str`
- `pipelex/core/stuffs/structured_content.py:150` — `StructuredContent._render_value_with_images` — `def _render_value_with_images(self, value: Any, *, registry: ImageRegistry, text_format: TextFormat) -> str`
- `pipelex/core/stuffs/stuff.py:100` — `Stuff.verify_content_type` — `def verify_content_type(cls, content: StuffContent, *, content_type: type[StuffContentType]) -> StuffContentType`
- `pipelex/core/stuffs/stuff_artefact.py:195` — `StuffArtefact.get` — `def get(self, key: str, *, default: Any=None) -> Any`
- `pipelex/core/stuffs/stuff_artefact.py:350` — `StuffArtefact.render_with_images` — `def render_with_images(self, registry: ImageRegistry, *, text_format: TextFormat) -> str`
- `pipelex/core/stuffs/stuff_content.py:64` — `StuffContent.rendered_markdown` — `def rendered_markdown(self, level: int=1, *, is_pretty: bool=False) -> str`
- `pipelex/core/stuffs/stuff_content.py:113` — `StuffContent.rendered_markdown_async` — `async def rendered_markdown_async(self, level: int=1, *, is_pretty: bool=False) -> str`
- `pipelex/core/stuffs/stuff_content_factory.py:12` — `StuffContentFactory.make_content_from_value` — `def make_content_from_value(cls, stuff_content_subclass: type[StuffContent], *, value: dict[str, Any] | str) -> StuffContent`
- `pipelex/core/stuffs/stuff_content_factory.py:18` — `StuffContentFactory.make_stuff_content_from_concept_required` — `def make_stuff_content_from_concept_required(cls, concept: Concept, *, value: dict[str, Any] | str) -> StuffContent`
- `pipelex/core/stuffs/stuff_content_factory.py:27` — `StuffContentFactory.make_stuff_content_from_concept_with_fallback` — `def make_stuff_content_from_concept_with_fallback(cls, concept: Concept, *, value: dict[str, Any] | str) -> StuffContent`
- `pipelex/core/stuffs/stuff_factory.py:51` — `StuffFactory.make_from_str` — `def make_from_str(cls, str_value: str, *, name: str) -> Stuff`
- `pipelex/core/stuffs/stuff_factory.py:59` — `StuffFactory.make_from_concept_ref` — `def make_from_concept_ref(cls, concept_ref: str, *, name: str, content: StuffContent) -> Stuff`
- `pipelex/core/stuffs/stuff_factory.py:69` — `StuffFactory.make_stuff` — `def make_stuff(cls, concept: Concept, *, content: StuffContent, name: str | None=None, code: str | None=None) -> Stuff`
- `pipelex/core/stuffs/stuff_factory.py:115` — `StuffFactory.combine_stuffs` — `def combine_stuffs(cls, stuff_contents: dict[str, StuffContent], *, concept: Concept, name: str | None=None) -> Stuff`
- `pipelex/core/stuffs/stuff_factory.py:136` — `StuffFactory._try_make_csv_list_stuff` — `def _try_make_csv_list_stuff(cls, concept: Concept, *, content: dict[str, Any], name: str | None, code: str | None) -> Stuff | None`
- `pipelex/core/stuffs/stuff_factory.py:227` — `StuffFactory.make_stuff_from_stuff_content_or_data` — `def make_stuff_from_stuff_content_or_data(cls, stuff_content_or_data: StuffContentOrData, *, name: str | None=None, code: str | None=None, search_domain_codes: list[str] | None=None) -> Stuff`
- `pipelex/core/stuffs/stuff_viewer.py:21` — `render_stuff_viewer` — `async def render_stuff_viewer(stuff: Stuff, *, title: str | None=None, subtitle: str | None=None) -> str`
- `pipelex/core/stuffs/stuff_viewer.py:72` — `render_stuff_content_viewer` — `async def render_stuff_content_viewer(stuff_data: str | dict[str, Any] | list[str] | list[dict[str, Any]], *, stuff_data_text: str, stuff_data_html: str, content_type: str | None=None, title: str='Stuff Content', subtitle: str | None=None) -> str`
- `pipelex/core/stuffs/text_and_images_content.py:76` — `TextAndImagesContent.render_with_images` — `def render_with_images(self, registry: ImageRegistry, *, text_format: TextFormat) -> str`

### `errors` (5)

- `pipelex/errors/error_pages_generator.py:253` — `generate_error_pages` — `def generate_error_pages(output_dir: Path, *, classes: Iterable[type[PipelexError]] | None=None) -> ErrorPagesReport`
- `pipelex/errors/error_pages_generator.py:333` — `_remove_orphans` — `def _remove_orphans(output_dir: Path, *, expected_stems: set[str], report: ErrorPagesReport) -> None`
- `pipelex/errors/error_pages_generator.py:355` — `_commit_page` — `def _commit_page(target: Path, *, new_content: str, report: ErrorPagesReport) -> None`
- `pipelex/errors/error_pages_generator.py:448` — `_subsystems_for_macro` — `def _subsystems_for_macro(macro_slug: str, *, by_subsystem: dict[str, list[type[PipelexError]]]) -> list[tuple[str, list[type[PipelexError]]]]`
- `pipelex/errors/error_pages_generator.py:473` — `render_macro_page` — `def render_macro_page(macro_heading: str, *, sections: list[tuple[str, list[type[PipelexError]]]]) -> str`

### `graph` (40)

- `pipelex/graph/graph_factory.py:45` — `generate_graph_outputs` — `async def generate_graph_outputs(graph_spec: GraphSpec, *, graph_config: GraphConfig, pipe_code: str='', title: str | None=None, direction: FlowchartDirection | None=None, include_subgraphs: bool=True) -> GraphOutputs`
- `pipelex/graph/graph_factory.py:135` — `save_graph_outputs_to_dir` — `def save_graph_outputs_to_dir(graph_outputs: GraphOutputs, *, output_dir: Path) -> dict[str, Path]`
- `pipelex/graph/graph_rendering.py:40` — `render_graph_from_spec` — `async def render_graph_from_spec(graph_spec: GraphSpec, *, graph_config: GraphConfig, include_mermaidflow: bool, include_reactflow: bool, output_dir: Path, pipe_code: str='', title: str | None=None, direction: FlowchartDirection | None=None, include_subgraphs: bool=True) -> dict[str, Path]`
- `pipelex/graph/graph_rendering.py:103` — `_dry_run_bundle` — `async def _dry_run_bundle(bundle_path: Path, *, library_dirs: list[str] | None=None) -> tuple[GraphSpec, str]`
- `pipelex/graph/graph_rendering.py:140` — `generate_graph_for_bundle` — `async def generate_graph_for_bundle(bundle_path: Path, *, graph_format: GraphFormat, library_dirs: list[str] | None=None, direction: FlowchartDirection | None=None, graph_name: str='dry_run.html') -> dict[str, Any]`
- `pipelex/graph/graph_rendering.py:215` — `generate_view_for_bundle` — `async def generate_view_for_bundle(bundle_path: Path, *, library_dirs: list[str] | None=None, direction: FlowchartDirection | None=None) -> dict[str, Any]`
- `pipelex/graph/graph_tracer.py:907` — `GraphTracer.add_selected_outcome_edge` — `def add_selected_outcome_edge(self, condition_node_id: str, *, outcome_node_id: str, outcome_value: str) -> None`
- `pipelex/graph/graph_tracer_manager.py:94` — `GraphTracerManager.open_tracer` — `def open_tracer(self, graph_id: str, *, data_inclusion: DataInclusionConfig, pipeline_ref_domain: str | None=None, pipeline_ref_main_pipe: str | None=None, event_log: 'EventLogProtocol | None'=None, workflow_id: str='direct', pipeline_run_id: str | None=None, tracer_key: str | None=None, emit_graph_events: bool=True, emit_usage_events: bool=True) -> TraceContext`
- `pipelex/graph/graph_tracer_manager.py:218` — `GraphTracerManager.on_pipe_start` — `def on_pipe_start(self, trace_context: TraceContext, *, pipe_code: str, pipe_type: str, node_kind: NodeKind, started_at: datetime, input_specs: list[IOSpec] | None=None, pipe_data: dict[str, Any] | None=None, concept_data: list[dict[str, Any]] | None=None, description: str | None=None, domain_code: str | None=None) -> tuple[str | None, TraceContext | None]`
- `pipelex/graph/graph_tracer_manager.py:266` — `GraphTracerManager.on_pipe_end_success` — `def on_pipe_end_success(self, lookup_key: str, *, node_id: str | None, ended_at: datetime, output_preview: str | None=None, metrics: dict[str, float] | None=None, output_spec: IOSpec | None=None, output_concept_data: dict[str, Any] | None=None) -> None`
- `pipelex/graph/graph_tracer_manager.py:304` — `GraphTracerManager.register_execution_data` — `def register_execution_data(self, lookup_key: str, *, node_id: str | None, execution_data: dict[str, Any]) -> None`
- `pipelex/graph/graph_tracer_manager.py:325` — `GraphTracerManager.on_pipe_end_error` — `def on_pipe_end_error(self, lookup_key: str, *, node_id: str | None, ended_at: datetime, error_type: str, error_message: str, error_stack: str | None=None) -> None`
- `pipelex/graph/graph_tracer_manager.py:360` — `GraphTracerManager.add_edge` — `def add_edge(self, lookup_key: str, *, source_node_id: str, target_node_id: str, edge_kind: EdgeKind, label: str | None=None) -> None`
- `pipelex/graph/graph_tracer_manager.py:389` — `GraphTracerManager.register_controller_output` — `def register_controller_output(self, lookup_key: str, *, node_id: str, output_spec: IOSpec) -> None`
- `pipelex/graph/graph_tracer_manager.py:411` — `GraphTracerManager.register_batch_item_extraction` — `def register_batch_item_extraction(self, lookup_key: str, *, list_stuff_code: str, item_stuff_code: str, item_index: int, batch_controller_node_id: str | None=None) -> None`
- `pipelex/graph/graph_tracer_manager.py:440` — `GraphTracerManager.register_batch_aggregation` — `def register_batch_aggregation(self, lookup_key: str, *, output_list_stuff_code: str, item_stuff_code: str, item_index: int, batch_controller_node_id: str | None=None) -> None`
- `pipelex/graph/graph_tracer_manager.py:469` — `GraphTracerManager.register_parallel_combine` — `def register_parallel_combine(self, lookup_key: str, *, combined_stuff_code: str, branch_stuff_codes: list[str], parallel_controller_node_id: str) -> None`
- `pipelex/graph/graph_tracer_protocol.py:19` — `GraphTracerProtocol.setup` — `def setup(self, graph_id: str, *, data_inclusion: DataInclusionConfig, pipeline_ref_domain: str | None=None, pipeline_ref_main_pipe: str | None=None, event_log: 'EventLogProtocol | None'=None, workflow_id: str='direct', pipeline_run_id: str | None=None, emit_graph_events: bool=True, emit_usage_events: bool=True) -> TraceContext`
- `pipelex/graph/graph_tracer_protocol.py:60` — `GraphTracerProtocol.on_pipe_start` — `def on_pipe_start(self, trace_context: TraceContext, *, pipe_code: str, pipe_type: str, node_kind: NodeKind, started_at: datetime, input_specs: list[IOSpec] | None=None, pipe_data: dict[str, Any] | None=None, concept_data: list[dict[str, Any]] | None=None, description: str | None=None, domain_code: str | None=None) -> tuple[str, TraceContext]`
- `pipelex/graph/graph_tracer_protocol.py:93` — `GraphTracerProtocol.on_pipe_end_success` — `def on_pipe_end_success(self, node_id: str, *, ended_at: datetime, output_preview: str | None=None, metrics: dict[str, float] | None=None, output_spec: IOSpec | None=None, output_concept_data: dict[str, Any] | None=None) -> None`
- `pipelex/graph/graph_tracer_protocol.py:115` — `GraphTracerProtocol.on_pipe_end_error` — `def on_pipe_end_error(self, node_id: str, *, ended_at: datetime, error_type: str, error_message: str, error_stack: str | None=None) -> None`
- `pipelex/graph/graph_tracer_protocol.py:157` — `GraphTracerProtocol.register_controller_output` — `def register_controller_output(self, node_id: str, *, output_spec: IOSpec) -> None`
- `pipelex/graph/graph_tracer_protocol.py:174` — `GraphTracerProtocol.register_batch_item_extraction` — `def register_batch_item_extraction(self, list_stuff_code: str, *, item_stuff_code: str, item_index: int, batch_controller_node_id: str | None=None) -> None`
- `pipelex/graph/graph_tracer_protocol.py:193` — `GraphTracerProtocol.register_batch_aggregation` — `def register_batch_aggregation(self, output_list_stuff_code: str, *, item_stuff_code: str, item_index: int, batch_controller_node_id: str | None=None) -> None`
- `pipelex/graph/graph_tracer_protocol.py:213` — `GraphTracerProtocol.register_parallel_combine` — `def register_parallel_combine(self, combined_stuff_code: str, *, branch_stuff_codes: list[str], parallel_controller_node_id: str) -> None`
- `pipelex/graph/graph_tracer_protocol.py:232` — `GraphTracerProtocol.register_execution_data` — `def register_execution_data(self, node_id: str, *, execution_data: dict[str, Any]) -> None`
- `pipelex/graph/graphspec.py:128` — `_truncate_string` — `def _truncate_string(value: str | None, *, max_length: int) -> str | None`
- `pipelex/graph/mermaidflow/mermaid_html.py:21` — `render_mermaid_html` — `def render_mermaid_html(mermaid_code: str, *, title: str='Pipelex Graph', theme: str='dark') -> str`
- `pipelex/graph/mermaidflow/mermaid_html.py:54` — `render_mermaid_html_async` — `async def render_mermaid_html_async(mermaid_code: str, *, title: str='Pipelex Graph', theme: str='dark') -> str`
- `pipelex/graph/mermaidflow/mermaid_html.py:86` — `render_mermaid_html_with_data_async` — `async def render_mermaid_html_with_data_async(mermaid_code: str, *, stuff_data: dict[str, str | dict[str, object] | list[str] | list[dict[str, object]] | None] | None=None, stuff_data_text: dict[str, str] | None=None, stuff_data_html: dict[str, str] | None=None, stuff_metadata: dict[str, dict[str, str]] | None=None, stuff_content_type: dict[str, str] | None=None, title: str='Pipelex Graph', theme: str='dark') -> str`
- `pipelex/graph/mermaidflow/mermaidflow_factory.py:53` — `MermaidflowFactory.make_from_graphspec` — `def make_from_graphspec(cls, graph: GraphSpec, *, graph_config: GraphConfig, direction: FlowchartDirection | None=None, show_stuff_codes: bool=False, include_subgraphs: bool=True) -> Mermaidflow`
- `pipelex/graph/mermaidflow/mermaidflow_factory.py:349` — `MermaidflowFactory._render_node` — `def _render_node(cls, node: NodeSpec, *, mermaid_id: str, indent: str='    ') -> str`
- `pipelex/graph/mermaidflow/mermaidflow_factory.py:389` — `MermaidflowFactory._render_stuff_node` — `def _render_stuff_node(cls, digest: str, *, name: str, concept: str | None, stuff_id_mapping: dict[str, str], show_stuff_codes: bool, indent: str='    ') -> str`
- `pipelex/graph/mermaidflow/mermaidflow_factory.py:427` — `MermaidflowFactory._render_dashed_edges` — `def _render_dashed_edges(cls, edges: list[EdgeSpec], *, lines: list[str], stuff_id_mapping: dict[str, str], all_stuff_info: dict[str, tuple[str, str | None]], show_stuff_codes: bool) -> None`
- `pipelex/graph/mermaidflow/mermaidflow_factory.py:487` — `MermaidflowFactory._render_subgraph_recursive` — `def _render_subgraph_recursive(cls, node_id: str, *, nodes_by_id: dict[str, NodeSpec], id_mapping: dict[str, str], children_map: dict[str, list[str]], stuff_registry: dict[str, tuple[str, str | None]], stuff_producers: dict[str, str], stuff_consumers: dict[str, list[str]], stuff_id_mapping: dict[str, str], subgraph_depths: dict[str, int], show_stuff_codes: bool, rendered_orphan_stuffs: set[str], controller_output_stuffs: dict[str, dict[str, tuple[str, str | None]]], indent_level: int=1, depth: int=0) -> list[str]`
- `pipelex/graph/mermaidflow/stuff_collector.py:18` — `_collect_stuff_field` — `def _collect_stuff_field(graph: GraphSpec, *, extractor: Callable[[IOSpec], T | None]) -> dict[str, T]`
- `pipelex/graph/reactflow/reactflow_html.py:34` — `_build_templating_context` — `def _build_templating_context(graphspec: GraphSpec, *, config: ReactFlowRenderingConfig, title: str | None) -> dict[str, object]`
- `pipelex/graph/reactflow/reactflow_html.py:51` — `generate_reactflow_html` — `def generate_reactflow_html(graphspec: GraphSpec, *, config: ReactFlowRenderingConfig, title: str | None=None) -> str`
- `pipelex/graph/reactflow/reactflow_html.py:75` — `generate_reactflow_html_async` — `async def generate_reactflow_html_async(graphspec: GraphSpec, *, config: ReactFlowRenderingConfig, title: str | None=None) -> str`
- `pipelex/graph/trace_context.py:66` — `TraceContext.copy_for_child` — `def copy_for_child(self, child_node_id: str, *, next_sequence: int) -> 'TraceContext'`

### `hub.py` (1)

- `pipelex/hub.py:121` — `PipelexHub.setup_config` — `def setup_config(self, config_cls: type[ConfigRoot], *, config_overrides: dict[str, Any] | None=None, config_dir: Path | None=None)`

### `kit` (8)

- `pipelex/kit/cursor_rules.py:34` — `_front_matter_for` — `def _front_matter_for(name: str, *, kit_index: KitIndex) -> dict[str, Any]`
- `pipelex/kit/cursor_rules.py:77` — `update_cursor_rules` — `def update_cursor_rules(repo_root: Path, *, kit_index: KitIndex, agent_set: str) -> None`
- `pipelex/kit/cursor_rules.py:113` — `remove_cursor_rules` — `def remove_cursor_rules(repo_root: Path, *, kit_index: KitIndex | None=None) -> None`
- `pipelex/kit/single_file_agent_rules.py:12` — `_read_agent_file` — `def _read_agent_file(agents_dir: Traversable, *, name: str) -> str`
- `pipelex/kit/single_file_agent_rules.py:25` — `_demote_headings` — `def _demote_headings(md_content: str, *, levels: int) -> str`
- `pipelex/kit/single_file_agent_rules.py:49` — `build_merged_rules` — `def build_merged_rules(kit_index: KitIndex, *, agent_set: str | None=None, file_list: list[str] | None=None) -> str`
- `pipelex/kit/single_file_agent_rules.py:107` — `update_single_file_agent_rules` — `def update_single_file_agent_rules(repo_root: Path, *, kit_index: KitIndex, agent_set: str, targets: dict[str, Target]) -> None`
- `pipelex/kit/single_file_agent_rules.py:145` — `remove_from_targets` — `def remove_from_targets(repo_root: Path, *, targets: dict[str, Target]) -> None`

### `language` (5)

- `pipelex/language/mthds_factory.py:52` — `MthdsFactory.convert_dicts_to_inline_tables` — `def convert_dicts_to_inline_tables(cls, value: Any, *, field_ordering: list[str] | None=None) -> Any`
- `pipelex/language/mthds_factory.py:91` — `MthdsFactory.convert_mapping_to_table` — `def convert_mapping_to_table(cls, mapping: Mapping[str, Any], *, field_ordering: list[str] | None=None) -> Any`
- `pipelex/language/mthds_schema_generator.py:89` — `_remove_from_required` — `def _remove_from_required(schema_obj: dict[str, Any], *, field_names: set[str]) -> None`
- `pipelex/language/mthds_schema_generator.py:310` — `_walk_schema` — `def _walk_schema(node: dict[str, Any] | list[Any] | Any, *, visitor: Callable[[dict[str, Any]], None]) -> None`
- `pipelex/language/toml_string_utils.py:14` — `format_toml_string` — `def format_toml_string(text: str, *, force_multiline: bool=False, length_limit_to_multiline: int=100, ensure_trailing_newline: bool=True, ensure_leading_blank_line: bool=True, prefer_literal: bool=False) -> Any`

### `libraries` (28)

- `pipelex/libraries/concept/concept_library.py:191` — `ConceptLibrary.add_dependency_concept` — `def add_dependency_concept(self, alias: str, *, concept: Concept) -> None`
- `pipelex/libraries/concept/concept_library_abstract.py:33` — `ConceptLibraryAbstract.is_compatible` — `def is_compatible(self, tested_concept: Concept, *, wanted_concept: Concept, strict: bool=False) -> bool`
- `pipelex/libraries/concept/concept_library_abstract.py:53` — `ConceptLibraryAbstract.get_required_concept_from_concept_ref_or_code` — `def get_required_concept_from_concept_ref_or_code(self, concept_ref_or_code: str, *, search_domain_codes: list[str] | None=None) -> Concept`
- `pipelex/libraries/concept_reference_validation.py:8` — `validate_concept_references_in_blueprints` — `def validate_concept_references_in_blueprints(blueprints: list[PipelexBundleBlueprint], *, already_loaded_concept_refs: set[str] | None=None) -> None`
- `pipelex/libraries/contract_match.py:24` — `_canonical_concept_spec` — `def _canonical_concept_spec(spec: str, *, domain_code: str) -> str`
- `pipelex/libraries/library_crate.py:39` — `LibraryCrate.compute_fingerprint_from_content` — `def compute_fingerprint_from_content(concepts: dict[str, 'ConceptBlueprint | str'], *, pipes: dict[str, PipeBlueprintUnion]) -> str`
- `pipelex/libraries/library_crate_factory.py:150` — `LibraryCrateFactory._reconcile_pipe_collision` — `def _reconcile_pipe_collision(cls, pipe_ref: str, *, existing: PipeDeclaration, incoming: PipeDeclaration, domain_code: str) -> PipeDeclaration`
- `pipelex/libraries/library_crate_factory.py:204` — `LibraryCrateFactory._contract_mismatch_msg` — `def _contract_mismatch_msg(pipe_ref: str, *, existing: PipeDeclaration, incoming: PipeDeclaration) -> str`
- `pipelex/libraries/library_manager.py:764` — `LibraryManager._load_mthds_files_into_library` — `def _load_mthds_files_into_library(self, library_id: str, *, valid_mthds_paths: list[Path]) -> list[PipeAbstract]`
- `pipelex/libraries/library_manager.py:839` — `LibraryManager._warn_if_mthds_version_unsatisfied` — `def _warn_if_mthds_version_unsatisfied(self, mthds_version_constraint: str, *, package_address: str) -> None`
- `pipelex/libraries/library_manager.py:860` — `LibraryManager._check_package_visibility` — `def _check_package_visibility(self, blueprints: list[PipelexBundleBlueprint], *, mthds_paths: list[Path]) -> MethodsManifest | None`
- `pipelex/libraries/library_manager.py:945` — `LibraryManager._load_dependency_packages` — `def _load_dependency_packages(self, library_id: str, *, manifest: MethodsManifest, package_root: Path) -> None`
- `pipelex/libraries/library_manager.py:981` — `LibraryManager._load_single_dependency` — `def _load_single_dependency(self, library: Library, *, resolved_dep: ResolvedDependency) -> None`
- `pipelex/libraries/library_manager.py:1142` — `LibraryManager._load_address_based_dependencies` — `def _load_address_based_dependencies(self, library_id: str, *, blueprints: list[PipelexBundleBlueprint]) -> None`
- `pipelex/libraries/library_manager.py:1193` — `LibraryManager._load_address_based_dependency` — `def _load_address_based_dependency(self, library: 'Library', *, full_address: str, extra_search_dirs: list[Path] | None=None) -> bool`
- `pipelex/libraries/library_manager.py:1357` — `LibraryManager._detect_concept_cycles.check_for_cycle` — `def check_for_cycle(concept_ref: str, *, visiting: set[str], path: list[str]) -> None`
- `pipelex/libraries/library_manager_abstract.py:84` — `LibraryManagerAbstract.load_from_crate` — `def load_from_crate(self, library_id: str, *, crate: LibraryCrate) -> list[PipeAbstract]`
- `pipelex/libraries/library_manager_abstract.py:96` — `LibraryManagerAbstract.load_from_blueprints` — `def load_from_blueprints(self, library_id: str, *, blueprints: list[PipelexBundleBlueprint]) -> list[PipeAbstract]`
- `pipelex/libraries/library_manager_abstract.py:100` — `LibraryManagerAbstract.load_concepts_only_from_blueprints` — `def load_concepts_only_from_blueprints(self, library_id: str, *, blueprints: list[PipelexBundleBlueprint]) -> list['Concept']`
- `pipelex/libraries/library_manager_abstract.py:116` — `LibraryManagerAbstract._remove_from_blueprint` — `def _remove_from_blueprint(self, library_id: str, *, blueprint: PipelexBundleBlueprint) -> None`
- `pipelex/libraries/library_manager_abstract.py:120` — `LibraryManagerAbstract._remove_from_blueprints` — `def _remove_from_blueprints(self, library_id: str, *, blueprints: list[PipelexBundleBlueprint]) -> None`
- `pipelex/libraries/library_manager_abstract.py:124` — `LibraryManagerAbstract.load_libraries` — `def load_libraries(self, library_id: str, *, library_dirs: list[Path] | None=None, library_file_paths: list[Path] | None=None) -> list[PipeAbstract]`
- `pipelex/libraries/library_manager_abstract.py:134` — `LibraryManagerAbstract.load_libraries_concepts_only` — `def load_libraries_concepts_only(self, library_id: str, *, library_dirs: list[Path] | None=None, library_file_paths: list[Path] | None=None) -> list['Concept']`
- `pipelex/libraries/library_utils.py:24` — `get_pipelex_mthds_files_from_package._find_mthds_in_traversable` — `def _find_mthds_in_traversable(traversable: Traversable, *, collected: list[Path]) -> None`
- `pipelex/libraries/pipe/pipe_library.py:97` — `PipeLibrary.add_dependency_pipe` — `def add_dependency_pipe(self, alias: str, *, pipe: PipeAbstract) -> None`
- `pipelex/libraries/pipe/pipe_library.py:137` — `PipeLibrary.pretty_list_pipes._format_concept_code` — `def _format_concept_code(concept_code: str | None, *, current_domain: str) -> str`
- `pipelex/libraries/visibility_utils.py:35` — `make_visibility_checker` — `def make_visibility_checker(manifest: MethodsManifest | None, *, blueprints: list[PipelexBundleBlueprint]) -> PackageVisibilityChecker`
- `pipelex/libraries/visibility_utils.py:53` — `check_visibility_for_blueprints` — `def check_visibility_for_blueprints(manifest: MethodsManifest | None, *, blueprints: list[PipelexBundleBlueprint]) -> list[VisibilityError]`

### `observer` (1)

- `pipelex/observer/local_observer.py:22` — `LocalObserver._write_to_jsonl` — `def _write_to_jsonl(self, event_type: str, *, payload: PayloadType) -> None`

### `pipe_controllers` (6)

- `pipelex/pipe_controllers/batch/pipe_batch.py:152` — `PipeBatch._live_run_controller_pipe._run_branch` — `async def _run_branch(item_input_stuff: 'Stuff', *, branch_output_item_code: str) -> PipeOutput`
- `pipelex/pipe_controllers/parallel/pipe_parallel.py:326` — `PipeParallel._register_branch_outputs_with_graph_tracer` — `def _register_branch_outputs_with_graph_tracer(self, job_metadata: JobMetadata, *, output_stuffs: dict[str, 'Stuff']) -> None`
- `pipelex/pipe_controllers/parallel/pipe_parallel.py:369` — `PipeParallel._register_parallel_combine_with_graph_tracer` — `def _register_parallel_combine_with_graph_tracer(self, job_metadata: JobMetadata, *, combined_stuff: 'Stuff', branch_stuffs: dict[str, 'Stuff']) -> None`
- `pipelex/pipe_controllers/pipe_controller.py:71` — `PipeController._live_run_controller_pipe` — `async def _live_run_controller_pipe(self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None=None, library_crate: 'LibraryCrate | None'=None) -> PipeOutput`
- `pipelex/pipe_controllers/pipe_controller.py:83` — `PipeController._dry_run_controller_pipe` — `async def _dry_run_controller_pipe(self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None=None, library_crate: 'LibraryCrate | None'=None) -> PipeOutput`
- `pipelex/pipe_controllers/sub_pipe.py:34` — `SubPipe.run_pipe` — `async def run_pipe(self, calling_pipe_code: str, *, working_memory: WorkingMemory, job_metadata: JobMetadata, sub_pipe_run_params: PipeRunParams, library_crate: 'LibraryCrate | None'=None) -> PipeOutput`

### `pipe_operators` (40)

- `pipelex/pipe_operators/compose/pipe_compose.py:165` — `PipeCompose._run_template_mode` — `async def _run_template_mode(self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None) -> PipeComposeOutput`
- `pipelex/pipe_operators/compose/pipe_compose.py:224` — `PipeCompose._run_construct_mode` — `async def _run_construct_mode(self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None) -> PipeComposeOutput`
- `pipelex/pipe_operators/compose/pipe_compose.py:318` — `PipeCompose._make_mock_construct_output` — `def _make_mock_construct_output(self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, output_name: str | None) -> PipeComposeOutput`
- `pipelex/pipe_operators/compose/pipe_compose_factory.py:52` — `PipeComposeFactory._make_template_mode` — `def _make_template_mode(cls, pipe_code: str, *, domain_code: str, description: str, inputs: InputStuffSpecs, output: StuffSpec, blueprint: PipeComposeBlueprint) -> PipeCompose`
- `pipelex/pipe_operators/compose/structured_content_composer.py:119` — `StructuredContentComposer._resolve_field` — `async def _resolve_field(self, field_blueprint: ConstructFieldBlueprint, *, field_name: str) -> Any`
- `pipelex/pipe_operators/compose/structured_content_composer.py:145` — `StructuredContentComposer._resolve_from_var` — `def _resolve_from_var(self, field_blueprint: ConstructFieldBlueprint, *, field_name: str) -> Any`
- `pipelex/pipe_operators/compose/structured_content_composer.py:187` — `StructuredContentComposer._convert_list_to_dict_keyed_by` — `def _convert_list_to_dict_keyed_by(self, value: Any, *, key_attr: str) -> dict[str, Any]`
- `pipelex/pipe_operators/compose/structured_content_composer.py:243` — `StructuredContentComposer._resolve_dotted_path` — `def _resolve_dotted_path(self, path: str, *, expected_type: type[Any] | None) -> Any`
- `pipelex/pipe_operators/compose/structured_content_composer.py:283` — `StructuredContentComposer._resolve_from_stuff_name` — `def _resolve_from_stuff_name(self, name: str, *, expected_type: type[Any] | None) -> StuffContent | list[dict[str, Any]] | str`
- `pipelex/pipe_operators/compose/structured_content_composer.py:298` — `StructuredContentComposer._convert_for_target_type` — `def _convert_for_target_type(self, stuff_content: StuffContent, *, expected_type: type[Any] | None) -> StuffContent | list[dict[str, Any]] | str`
- `pipelex/pipe_operators/compose/structured_content_composer.py:324` — `StructuredContentComposer._convert_text_content` — `def _convert_text_content(self, text_content: TextContent, *, expected_type: Any) -> TextContent | str`
- `pipelex/pipe_operators/compose/structured_content_composer.py:348` — `StructuredContentComposer._convert_list_content` — `def _convert_list_content(self, list_content: ListContent[StuffContent], *, expected_type: type[Any] | None) -> ListContent[StuffContent] | list[dict[str, Any]]`
- `pipelex/pipe_operators/compose/structured_content_composer.py:392` — `StructuredContentComposer._expects_type` — `def _expects_type(self, expected_type: type[Any], *, target_type: type) -> bool`
- `pipelex/pipe_operators/compose/structured_content_composer.py:410` — `StructuredContentComposer._convert_content_for_field` — `def _convert_content_for_field(self, stuff_content: StuffContent, *, expected_type: type[StuffContent]) -> StuffContent`
- `pipelex/pipe_operators/compose/structured_content_composer.py:501` — `StructuredContentComposer._convert_list_items_as_dicts` — `def _convert_list_items_as_dicts(self, items: list[StuffContent], *, expected_item_type: type[Any] | None) -> list[dict[str, Any]]`
- `pipelex/pipe_operators/compose/structured_content_composer.py:528` — `StructuredContentComposer._convert_list_items_as_objects` — `def _convert_list_items_as_objects(self, items: list[StuffContent], *, expected_item_type: type[Any] | None) -> list[StuffContent]`
- `pipelex/pipe_operators/compose/structured_content_composer.py:555` — `StructuredContentComposer._validate_item_compatibility` — `def _validate_item_compatibility(self, item: StuffContent, *, expected_type: type[Any], idx: int) -> None`
- `pipelex/pipe_operators/compose/structured_content_composer.py:599` — `StructuredContentComposer._convert_single_item_as_object` — `def _convert_single_item_as_object(self, item: StuffContent, *, expected_type: type[Any], idx: int) -> StuffContent`
- `pipelex/pipe_operators/compose/structured_content_composer.py:662` — `StructuredContentComposer._resolve_nested` — `async def _resolve_nested(self, field_blueprint: ConstructFieldBlueprint, *, field_name: str) -> StuffContent`
- `pipelex/pipe_operators/img_gen/img_gen_prompt_blueprint.py:65` — `ImgGenPromptBlueprint.make_img_gen_prompt` — `async def make_img_gen_prompt(self, context_provider: ContextProviderAbstract, *, extra_params: dict[str, Any] | None=None, max_prompt_images: int | None=None) -> ImgGenPrompt`
- `pipelex/pipe_operators/img_gen/img_gen_prompt_blueprint.py:198` — `ImgGenPromptBlueprint._extract_direct_image` — `def _extract_direct_image(self, image_ref: ImageReference, *, context_provider: ContextProviderAbstract, image_registry: ImageRegistry, image_registry_indices: dict[str, int]) -> None`
- `pipelex/pipe_operators/img_gen/img_gen_prompt_blueprint.py:224` — `ImgGenPromptBlueprint._extract_direct_list_images` — `def _extract_direct_list_images(self, image_ref: ImageReference, *, context_provider: ContextProviderAbstract, image_registry: ImageRegistry, image_registry_indices: dict[str, int]) -> None`
- `pipelex/pipe_operators/img_gen/img_gen_prompt_blueprint.py:269` — `ImgGenPromptBlueprint._render_text` — `async def _render_text(self, context_provider: ContextProviderAbstract, *, template_blueprint: TemplateBlueprint, extra_params: dict[str, Any] | None=None, image_registry: ImageRegistry | None=None) -> str`
- `pipelex/pipe_operators/llm/llm_prompt_blueprint.py:61` — `LLMPromptBlueprint.make_llm_prompt` — `async def make_llm_prompt(self, output_concept_ref: str, *, context_provider: ContextProviderAbstract, output_structure_prompt: str | None=None, extra_params: dict[str, Any] | None=None) -> LLMPrompt`
- `pipelex/pipe_operators/llm/llm_prompt_blueprint.py:279` — `LLMPromptBlueprint._extract_direct_image` — `def _extract_direct_image(self, image_ref: ImageReference, *, context_provider: ContextProviderAbstract, image_registry: ImageRegistry, image_registry_indices: dict[str, int]) -> None`
- `pipelex/pipe_operators/llm/llm_prompt_blueprint.py:305` — `LLMPromptBlueprint._extract_direct_list_images` — `def _extract_direct_list_images(self, image_ref: ImageReference, *, context_provider: ContextProviderAbstract, image_registry: ImageRegistry, image_registry_indices: dict[str, int]) -> None`
- `pipelex/pipe_operators/llm/llm_prompt_blueprint.py:350` — `LLMPromptBlueprint._unravel_text` — `async def _unravel_text(self, context_provider: ContextProviderAbstract, *, jinja2_blueprint: TemplateBlueprint, extra_params: dict[str, Any] | None=None, image_registry: ImageRegistry | None=None) -> str`
- `pipelex/pipe_operators/llm/llm_prompt_blueprint.py:382` — `LLMPromptBlueprint._extract_direct_document` — `def _extract_direct_document(self, doc_ref: DocumentReference, *, context_provider: ContextProviderAbstract, prompt_user_documents: dict[str, PromptDocument]) -> None`
- `pipelex/pipe_operators/llm/llm_prompt_blueprint.py:410` — `LLMPromptBlueprint._extract_direct_list_documents` — `def _extract_direct_list_documents(self, doc_ref: DocumentReference, *, context_provider: ContextProviderAbstract, prompt_user_documents: dict[str, PromptDocument]) -> None`
- `pipelex/pipe_operators/llm/pipe_llm.py:330` — `PipeLLM._llm_gen_object_stuff_content` — `async def _llm_gen_object_stuff_content(self, job_metadata: JobMetadata, *, pipe_run_params: PipeRunParams, is_multiple_output: bool, fixed_nb_output: int | None, output_class_name: str, llm_setting_for_object: LLMSetting, llm_prompt_for_object: LLMPrompt, content_generator: ContentGeneratorProtocol) -> StuffContent`
- `pipelex/pipe_operators/llm/pipe_llm.py:386` — `PipeLLM._format_llm_error` — `def _format_llm_error(self, exc: LLMCompletionError, *, settings: list[LLMSetting]) -> str`
- `pipelex/pipe_operators/llm/template_document_analyzer.py:31` — `TemplateDocumentAnalyzer.analyze_template_for_documents` — `def analyze_template_for_documents(cls, template_source: str, *, input_specs: dict[str, str], domain_code: str) -> list[DocumentReference]`
- `pipelex/pipe_operators/llm/template_document_analyzer.py:107` — `TemplateDocumentAnalyzer._resolve_concept` — `def _resolve_concept(cls, concept_ref_or_code: str, *, domain_code: str) -> Concept`
- `pipelex/pipe_operators/llm/template_document_analyzer.py:128` — `TemplateDocumentAnalyzer._resolve_variable_type` — `def _resolve_variable_type(cls, var_path: str, *, root_var: str, root_concept: Concept) -> tuple[bool, bool] | None`
- `pipelex/pipe_operators/pipe_operator.py:101` — `PipeOperator._live_run_operator_pipe` — `async def _live_run_operator_pipe(self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None=None) -> PipeOperatorOutputType`
- `pipelex/pipe_operators/pipe_operator.py:111` — `PipeOperator._dry_run_operator_pipe` — `async def _dry_run_operator_pipe(self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None=None) -> PipeOperatorOutputType`
- `pipelex/pipe_operators/shared/template_image_analyzer.py:34` — `TemplateImageAnalyzer.analyze_template_for_images` — `def analyze_template_for_images(cls, template_source: str, *, input_specs: dict[str, str], domain_code: str, template_category: TemplateCategory=TemplateCategory.LLM_PROMPT) -> list[ImageReference]`
- `pipelex/pipe_operators/shared/template_image_analyzer.py:137` — `TemplateImageAnalyzer.validate_unused_inputs` — `def validate_unused_inputs(cls, template_sources: list[str], *, input_specs: dict[str, str], template_category: TemplateCategory=TemplateCategory.LLM_PROMPT) -> None`
- `pipelex/pipe_operators/shared/template_image_analyzer.py:174` — `TemplateImageAnalyzer._resolve_concept` — `def _resolve_concept(cls, concept_ref_or_code: str, *, domain_code: str) -> Concept`
- `pipelex/pipe_operators/shared/template_image_analyzer.py:195` — `TemplateImageAnalyzer._resolve_variable_type` — `def _resolve_variable_type(cls, var_path: str, *, root_var: str, root_concept: Concept) -> tuple[bool, bool, bool, list[str] | None] | None`

### `pipe_run` (18)

- `pipelex/pipe_run/delivery_executor.py:40` — `DeliveryExecutor.execute` — `async def execute(self, pipe_output: PipeOutput | None, *, user_id: str, pipeline_run_id: str, delivery_assignment: DeliveryAssignment, status: DeliveryStatus, error_report: ErrorReport | None=None, request_id: str | None=None) -> None`
- `pipelex/pipe_run/delivery_executor.py:163` — `DeliveryExecutor._generate_main_stuff_files_from_raw` — `def _generate_main_stuff_files_from_raw(cls, raw_main_stuff: dict[str, Any], *, files: dict[str, ResultFile]) -> None`
- `pipelex/pipe_run/delivery_executor.py:178` — `DeliveryExecutor._generate_main_stuff_files` — `async def _generate_main_stuff_files(self, main_stuff: Stuff, *, files: dict[str, ResultFile]) -> None`
- `pipelex/pipe_run/delivery_executor.py:185` — `DeliveryExecutor._generate_graph_files` — `async def _generate_graph_files(self, graph_spec: Any, *, files: dict[str, ResultFile]) -> None`
- `pipelex/pipe_run/delivery_executor.py:201` — `DeliveryExecutor._try_add_rendered_file` — `async def _try_add_rendered_file(cls, files: dict[str, ResultFile], *, filename: str, render: Awaitable[str], content_type: str) -> None`
- `pipelex/pipe_run/delivery_executor.py:219` — `DeliveryExecutor._add_optional_text_file` — `def _add_optional_text_file(cls, files: dict[str, ResultFile], *, filename: str, text: str | None, content_type: str) -> None`
- `pipelex/pipe_run/delivery_executor.py:226` — `DeliveryExecutor._store_results` — `async def _store_results(self, pipe_output: PipeOutput, *, user_id: str, pipeline_run_id: str, storage: StorageTarget, request_id: str | None=None) -> str`
- `pipelex/pipe_run/dry_run_in_process.py:33` — `best_effort_graph_spec` — `async def best_effort_graph_spec(pipe_ref: str | None, *, library_id: str | None, log_context: str) -> GraphSpec | None`
- `pipelex/pipe_run/dry_run_in_process.py:69` — `dry_run_pipe_in_process` — `async def dry_run_pipe_in_process(pipe: PipeAbstract, *, library_id: str) -> GraphSpec`
- `pipelex/pipe_run/pipe_job_factory.py:13` — `PipeJobFactory.make_pipe_job` — `def make_pipe_job(cls, pipe: PipeAbstract, *, job_metadata: JobMetadata, pipe_run_params: PipeRunParams | None=None, working_memory: WorkingMemory | None=None, output_name: str | None=None, library_crate: LibraryCrate | None=None) -> PipeJob`
- `pipelex/pipe_run/pipe_router_protocol.py:24` — `PipeRouterProtocol._after_successful_run` — `async def _after_successful_run(self, pipe_job: PipeJob, *, pipe_output: PipeOutput) -> None`
- `pipelex/pipe_run/pipe_router_protocol.py:37` — `PipeRouterProtocol._after_failing_run` — `async def _after_failing_run(self, pipe_job: PipeJob, *, error: Exception) -> None`
- `pipelex/pipe_run/pipe_run_params.py:28` — `output_multiplicity_to_apply` — `def output_multiplicity_to_apply(base_multiplicity: VariableMultiplicity | None, *, override_multiplicity: VariableMultiplicity | None) -> VariableMultiplicityResolution`
- `pipelex/pipe_run/pipe_run_params.py:121` — `BatchParams.make_batch_params` — `def make_batch_params(cls, input_list_name: str, *, input_item_name: str) -> BatchParams`
- `pipelex/pipe_run/pipe_run_params.py:206` — `PipeRunParams.copy_by_injecting_multiplicity` — `def copy_by_injecting_multiplicity(cls, pipe_run_params: Self, *, applied_output_multiplicity: VariableMultiplicity | None) -> Self`
- `pipelex/pipe_run/pipe_run_protocol.py:20` — `PipeRunProtocol.run` — `async def run(self, pipe_job: PipeJob, *, delivery_assignment: DeliveryAssignment | None=None) -> PipeOutput`
- `pipelex/pipe_run/tracing_assembly.py:51` — `assemble_tracing` — `def assemble_tracing(pipeline_run_id: str, *, assemble_graph: bool, assemble_usage: bool, domain_code: str | None=None, main_pipe_code: str | None=None) -> TracingAssembly`
- `pipelex/pipe_run/tracing_assembly.py:142` — `assemble_tracing_on_output` — `def assemble_tracing_on_output(pipe_output: PipeOutput, *, pipeline_run_id: str, assemble_graph: bool, assemble_usage: bool, domain_code: str | None=None, main_pipe_code: str | None=None) -> None`

### `pipe_signature` (2)

- `pipelex/pipe_signature/signature_walk.py:14` — `collect_signature_refs` — `def collect_signature_refs(pipe: PipeAbstract, *, visited: set[str] | None=None) -> set[str]`
- `pipelex/pipe_signature/signature_walk.py:40` — `collect_signature_paths` — `def collect_signature_paths(pipe: PipeAbstract, *, current_path: list[str] | None=None, paths: dict[str, list[str]] | None=None) -> dict[str, list[str]]`

### `pipelex.py` (3)

- `pipelex/pipelex.py:145` — `Pipelex._get_validation_error_msg` — `def _get_validation_error_msg(component_name: str, *, validation_exc: Exception) -> str`
- `pipelex/pipelex.py:165` — `Pipelex.setup` — `def setup(self, integration_mode: IntegrationMode, *, needs_inference: bool=True, temporal_enabled: bool | None=None, needs_model_specs: bool | None=None, class_registry: ClassRegistryAbstract | None=None, secrets_provider: SecretsProviderAbstract | None=None, storage_provider: StorageProviderAbstract | None=None, models_manager: ModelManagerAbstract | None=None, inference_manager: InferenceManager | None=None, content_generator: ContentGeneratorProtocol | None=None, pipeline_manager: PipelineManagerAbstract | None=None, pipe_router: PipeRouterProtocol | None=None, reporting_delegate: ReportingProtocol | None=None, telemetry_config: TelemetryConfig | None=None, telemetry_manager: TelemetryManagerAbstract | None=None, observers: dict[str, ObserverProtocol] | None=None, library_manager: LibraryManagerAbstract | None=None, library_dirs: list[str] | list[Path] | None=None, **kwargs: Any)`
- `pipelex/pipelex.py:512` — `Pipelex.make` — `def make(cls, integration_mode: IntegrationMode=IntegrationMode.PYTHON, *, needs_inference: bool=True, temporal_enabled: bool | None=None, needs_model_specs: bool | None=None, class_registry: ClassRegistryAbstract | None=None, secrets_provider: SecretsProviderAbstract | None=None, storage_provider: StorageProviderAbstract | None=None, models_manager: ModelManagerAbstract | None=None, inference_manager: InferenceManager | None=None, content_generator: ContentGeneratorProtocol | None=None, pipeline_manager: PipelineManager | None=None, pipe_router: PipeRouterProtocol | None=None, reporting_delegate: ReportingProtocol | None=None, telemetry_config: TelemetryConfig | None=None, telemetry_manager: TelemetryManagerAbstract | None=None, observers: dict[str, ObserverProtocol] | None=None, library_dirs: list[str] | list[Path] | None=None, config_overrides: dict[str, Any] | None=None, **kwargs: Any) -> Self`

### `pipeline` (18)

- `pipelex/pipeline/bundle_validator.py:171` — `BundleValidator.validate_pipes` — `async def validate_pipes(self, pipes: list[PipeAbstract], *, library_id: str, allow_signatures: bool=False) -> dict[str, DryRunOutput]`
- `pipelex/pipeline/dry_run_pipeline.py:26` — `dry_run_pipeline` — `async def dry_run_pipeline(mthds_contents: list[str] | None=None, *, bundle_uris: list[str] | None=None, library_dirs: list[str] | None=None) -> tuple[GraphSpec, str]`
- `pipelex/pipeline/execution_seams.py:55` — `acquire_library` — `def acquire_library(library_id: str, *, library_dirs: list[str] | None=None, mthds_contents: list[str] | None=None, bundle_uris: list[str] | None=None) -> tuple[str, str | None]`
- `pipelex/pipeline/execution_seams.py:154` — `prepare_pipe_job` — `async def prepare_pipe_job(pipe: PipeAbstract, *, library_id: str, execution_config: PipelineExecutionConfig, pipe_run_mode: PipeRunMode, pipeline_run_id: str, user_id: str, inputs: PipelineInputs | WorkingMemory | None=None, search_domain_codes: list[str] | None=None, trace_context: 'TraceContext | None'=None, otel_context: OtelContext | None=None, output_name: str | None=None, output_multiplicity: VariableMultiplicity | None=None, dynamic_output_concept_ref: str | None=None, request_id: str | None=None, is_mock_usage: bool=False) -> PipeJob`
- `pipelex/pipeline/input_normalizer.py:61` — `_normalize_value` — `async def _normalize_value(value: Any, *, storage: StorageProviderAbstract) -> tuple[Any, bool]`
- `pipelex/pipeline/input_normalizer.py:96` — `_normalize_structured_content` — `async def _normalize_structured_content(structured_content: StructuredContent, *, storage: StorageProviderAbstract) -> tuple[StructuredContent, bool]`
- `pipelex/pipeline/input_normalizer.py:127` — `_normalize_list_content` — `async def _normalize_list_content(list_content: ListContent[Any], *, storage: StorageProviderAbstract) -> tuple[ListContent[Any], bool]`
- `pipelex/pipeline/input_normalizer.py:161` — `_normalize_list` — `async def _normalize_list(items: list[Any], *, storage: StorageProviderAbstract) -> tuple[list[Any], bool]`
- `pipelex/pipeline/input_normalizer.py:187` — `_normalize_url_content` — `async def _normalize_url_content(content: NormalizableContent, *, storage: StorageProviderAbstract) -> NormalizableContent`
- `pipelex/pipeline/job_metadata.py:89` — `JobMetadata.copy_with_update` — `def copy_with_update(self, otel_context: OtelContext | None, *, trace_context: TraceContext | None=None, **updates: Any) -> 'JobMetadata'`
- `pipelex/pipeline/pipeline_manager.py:35` — `PipelineManager._set_pipeline` — `def _set_pipeline(self, pipeline_run_id: str, *, pipeline: Pipeline) -> Pipeline`
- `pipelex/pipeline/pipeline_manager_abstract.py:24` — `PipelineManagerAbstract.add_new_pipeline` — `def add_new_pipeline(self, pipe_code: str | None, *, pipeline_run_id: str | None=None) -> Pipeline`
- `pipelex/pipeline/pipeline_response.py:36` — `PipelexRunResultExecute.from_pipe_output` — `def from_pipe_output(cls, pipe_output: PipeOutput, *, pipeline_run_id: str='', created_at: str='', state: RunState=RunState.COMPLETED, finished_at: str | None=None) -> PipelexRunResultExecute`
- `pipelex/pipeline/pipeline_run_setup.py:43` — `pipeline_run_setup` — `async def pipeline_run_setup(execution_config: PipelineExecutionConfig, *, library_id: str | None=None, library_dirs: list[str] | None=None, pipe_code: str | None=None, mthds_contents: list[str] | None=None, bundle_uris: list[str] | None=None, inputs: PipelineInputs | WorkingMemory | None=None, output_name: str | None=None, output_multiplicity: VariableMultiplicity | None=None, dynamic_output_concept_ref: str | None=None, pipe_run_mode: PipeRunMode | None=None, is_mock_usage: bool=False, search_domain_codes: list[str] | None=None, user_id: str | None=None, pipeline_run_id: str | None=None, request_id: str | None=None) -> tuple[PipeJob, str, str]`
- `pipelex/pipeline/validate_bundle.py:204` — `_pipes_to_dry_run` — `def _pipes_to_dry_run(loaded_pipes: list[PipeAbstract], *, dry_run_pipe_codes: list[str] | None) -> list[PipeAbstract]`
- `pipelex/pipeline/validate_bundle.py:230` — `validate_bundle` — `async def validate_bundle(mthds_file_path: Path | None=None, *, mthds_contents: list[str] | None=None, library_dirs: Sequence[Path] | None=None, allow_signatures: bool=False, dry_run_pipe_codes: list[str] | None=None) -> ValidateBundleResult`
- `pipelex/pipeline/validate_bundle.py:335` — `validate_bundles_from_directory` — `async def validate_bundles_from_directory(directory: Path, *, allow_signatures: bool=False) -> ValidateBundleResult`
- `pipelex/pipeline/validate_bundle.py:378` — `load_concepts_only` — `def load_concepts_only(mthds_file_path: Path | None=None, *, mthds_contents: list[str] | None=None, library_dirs: Sequence[Path] | None=None) -> LoadConceptsOnlyResult`

### `plugins` (49)

- `pipelex/plugins/anthropic/anthropic_factory.py:38` — `AnthropicFactory.make_anthropic_client` — `def make_anthropic_client(plugin: Plugin, *, backend: InferenceBackend) -> AsyncAnthropic | AsyncAnthropicBedrock`
- `pipelex/plugins/anthropic/anthropic_factory.py:105` — `AnthropicFactory._make_document_block_param` — `def _make_document_block_param(prepped_document: PreparedFile, *, title: str | None=None) -> DocumentBlockParam`
- `pipelex/plugins/anthropic/anthropic_factory.py:169` — `AnthropicFactory.openai_typed_user_message` — `def openai_typed_user_message(cls, user_content_txt: str, *, prepped_user_images: list[PreparedFile] | None=None, prepped_user_documents: list[tuple[PreparedFile, str | None]] | None=None) -> 'ChatCompletionMessageParam'`
- `pipelex/plugins/anthropic/anthropic_factory.py:244` — `AnthropicFactory.make_nb_tokens_by_category_from_nb` — `def make_nb_tokens_by_category_from_nb(nb_input: int, *, nb_output: int) -> NbTokensByCategoryDict`
- `pipelex/plugins/anthropic/anthropic_list.py:20` — `list_anthropic_models` — `async def list_anthropic_models(sdk: str, *, backend_name: str, backend: InferenceBackend, flat: bool, any_listed: bool) -> None`
- `pipelex/plugins/anthropic/anthropic_list.py:72` — `_display_anthropic_models_flat` — `def _display_anthropic_models_flat(models: list[ModelInfo], *, sdk: str, backend_name: str, any_listed: bool) -> None`
- `pipelex/plugins/anthropic/anthropic_list.py:89` — `_display_anthropic_models_table` — `def _display_anthropic_models_table(models: list[ModelInfo], *, sdk: str, backend_name: str) -> None`
- `pipelex/plugins/anthropic/anthropic_llm_worker.py:115` — `AnthropicLLMWorker._build_thinking_params` — `def _build_thinking_params(self, job_params: LLMJobParams, *, max_tokens: int) -> _ThinkingParams`
- `pipelex/plugins/anthropic/anthropic_llm_worker.py:145` — `AnthropicLLMWorker._build_thinking_params_for_effort` — `def _build_thinking_params_for_effort(self, thinking_mode: ThinkingMode, *, effort: ReasoningEffort, max_tokens: int) -> _ThinkingParams`
- `pipelex/plugins/anthropic/anthropic_llm_worker.py:200` — `AnthropicLLMWorker._build_thinking_params_for_budget` — `def _build_thinking_params_for_budget(self, thinking_mode: ThinkingMode, *, budget: int, max_tokens: int) -> _ThinkingParams`
- `pipelex/plugins/anthropic/anthropic_llms.py:10` — `anthropic_list_available_models` — `async def anthropic_list_available_models(plugin: Plugin, *, backend: InferenceBackend) -> list[ModelInfo]`
- `pipelex/plugins/bedrock/bedrock_client_protocol.py:9` — `BedrockClientProtocol.chat` — `async def chat(self, messages: BedrockMessageDictList, *, system_text: str | None, model: str, temperature: float, max_tokens: int | None=None) -> tuple[str, NbTokensByCategoryDict]`
- `pipelex/plugins/bedrock/bedrock_factory.py:27` — `BedrockFactory.make_bedrock_client` — `def make_bedrock_client(cls, plugin: Plugin, *, backend: InferenceBackend) -> BedrockClientProtocol`
- `pipelex/plugins/bedrock/bedrock_list.py:20` — `list_bedrock_models` — `def list_bedrock_models(sdk: str, *, backend_name: str, backend: InferenceBackend, flat: bool, any_listed: bool) -> None`
- `pipelex/plugins/bedrock/bedrock_list.py:80` — `_display_bedrock_models_flat` — `def _display_bedrock_models_flat(models: list[dict[str, Any]], *, sdk: str, backend_name: str, aws_region: str, any_listed: bool) -> None`
- `pipelex/plugins/bedrock/bedrock_list.py:99` — `_display_bedrock_models_table` — `def _display_bedrock_models_table(models: list[dict[str, Any]], *, sdk: str, aws_region: str) -> None`
- `pipelex/plugins/bedrock/bedrock_llms.py:10` — `bedrock_list_available_models` — `def bedrock_list_available_models(plugin: Plugin, *, backend: InferenceBackend) -> list[dict[str, Any]]`
- `pipelex/plugins/fal/fal_img_gen_worker.py:37` — `FalImgGenWorker._submit_and_get_result` — `async def _submit_and_get_result(self, img_gen_job: ImgGenJob, *, nb_images: int) -> Any`
- `pipelex/plugins/gateway/gateway_completions_factory.py:104` — `GatewayCompletionsFactory.make_portkey_openai_client_for_completions` — `def make_portkey_openai_client_for_completions(cls, plugin: Plugin, *, backend: InferenceBackend) -> openai.AsyncOpenAI`
- `pipelex/plugins/gateway/gateway_completions_factory.py:138` — `GatewayCompletionsFactory.make_extract_output_from_response` — `def make_extract_output_from_response(cls, inference_model: InferenceModelSpec, *, response: GenericResponse) -> ExtractOutput`
- `pipelex/plugins/gateway/gateway_extract_worker.py:191` — `GatewayExtractWorker._extract_base64_url` — `async def _extract_base64_url(self, extract_job: ExtractJob, *, base64_url: str, should_include_images: bool=False) -> ExtractOutput`
- `pipelex/plugins/gateway/gateway_factory.py:64` — `GatewayFactory.make_extras` — `def make_extras(cls, inference_model: InferenceModelSpec, *, inference_job: InferenceJobAbstract, output_desc: str) -> tuple[dict[str, str], dict[str, Any]]`
- `pipelex/plugins/gateway/gateway_responses_factory.py:26` — `GatewayResponsesFactory.make_portkey_openai_client_for_responses` — `def make_portkey_openai_client_for_responses(cls, plugin: Plugin, *, backend: InferenceBackend) -> openai.AsyncOpenAI`
- `pipelex/plugins/gateway/gateway_search_worker.py:128` — `GatewaySearchWorker._extract_usage` — `def _extract_usage(self, response: GenericResponse, *, search_job: SearchJob) -> None`
- `pipelex/plugins/gateway/gateway_search_worker.py:140` — `GatewaySearchWorker._call_relay` — `async def _call_relay(self, model: str, *, content: str) -> GenericResponse`
- `pipelex/plugins/google/google_factory.py:79` — `GoogleFactory.extract_text_from_response` — `def extract_text_from_response(cls, response: genai_types.GenerateContentResponse, *, model_desc: str) -> str`
- `pipelex/plugins/google/google_img_gen_factory.py:106` — `GoogleImgGenFactory.dimensions_for_aspect_ratio_and_size` — `def dimensions_for_aspect_ratio_and_size(cls, model: str, *, aspect_ratio: AspectRatio, size: GoogleImageSize) -> tuple[int, int]`
- `pipelex/plugins/google/google_list.py:16` — `list_google_models` — `async def list_google_models(sdk: str, *, backend_name: str, backend: InferenceBackend, flat: bool, any_listed: bool) -> None`
- `pipelex/plugins/google/google_list.py:57` — `_display_google_models_flat` — `def _display_google_models_flat(models: list[Any], *, sdk: str, backend_name: str, any_listed: bool) -> None`
- `pipelex/plugins/google/google_list.py:75` — `_display_google_models_table` — `def _display_google_models_table(models: list[Any], *, sdk: str, backend_name: str) -> None`
- `pipelex/plugins/google/google_llm_worker.py:111` — `GoogleLLMWorker._build_thinking_config` — `def _build_thinking_config(self, job_params: LLMJobParams, *, max_tokens: int | None) -> genai_types.ThinkingConfig | None`
- `pipelex/plugins/google/google_llm_worker.py:135` — `GoogleLLMWorker._build_thinking_config_for_effort` — `def _build_thinking_config_for_effort(self, thinking_mode: ThinkingMode, *, effort: ReasoningEffort, max_tokens: int | None) -> genai_types.ThinkingConfig`
- `pipelex/plugins/google/google_llm_worker.py:172` — `GoogleLLMWorker._build_thinking_config_for_budget` — `def _build_thinking_config_for_budget(self, thinking_mode: ThinkingMode, *, budget: int, max_tokens: int | None) -> genai_types.ThinkingConfig`
- `pipelex/plugins/mistral/mistral_extract_worker.py:86` — `MistralExtractWorker._extract_pages_from_document` — `async def _extract_pages_from_document(self, document_uri: str, *, extract_job_params: ExtractJobParams) -> ExtractOutput`
- `pipelex/plugins/mistral/mistral_factory.py:365` — `MistralFactory.make_mistral_document_url_chunk_from_uri` — `async def make_mistral_document_url_chunk_from_uri(cls, mistral_client: Mistral, *, uri: str) -> DocumentURLChunkTypedDict`
- `pipelex/plugins/mistral/mistral_list.py:13` — `list_mistral_models` — `def list_mistral_models(sdk: str, *, backend_name: str, flat: bool, any_listed: bool) -> None`
- `pipelex/plugins/mistral/mistral_list.py:54` — `_display_mistral_models_flat` — `def _display_mistral_models_flat(models: list[Any], *, sdk: str, backend_name: str, any_listed: bool) -> None`
- `pipelex/plugins/mistral/mistral_list.py:70` — `_display_mistral_models_table` — `def _display_mistral_models_table(models: list[Any], *, sdk: str, backend_name: str) -> None`
- `pipelex/plugins/openai/openai_client_factory.py:27` — `OpenAIClientFactory.make_openai_client` — `def make_openai_client(cls, plugin: Plugin, *, backend: InferenceBackend) -> openai.AsyncClient`
- `pipelex/plugins/openai/openai_list.py:19` — `list_openai_models` — `async def list_openai_models(sdk: str, *, backend_name: str, backend: InferenceBackend, flat: bool, any_listed: bool) -> None`
- `pipelex/plugins/openai/openai_list.py:49` — `_display_openai_models_flat` — `def _display_openai_models_flat(models: list[Model], *, sdk: str, backend_name: str, any_listed: bool) -> None`
- `pipelex/plugins/openai/openai_list.py:70` — `_display_openai_models_table` — `def _display_openai_models_table(models: list[Model], *, sdk: str, backend_name: str) -> None`
- `pipelex/plugins/openai/openai_llms.py:8` — `openai_list_available_models` — `async def openai_list_available_models(plugin: Plugin, *, backend: InferenceBackend) -> list[Model]`
- `pipelex/plugins/openai/vertexai_factory.py:47` — `VertexAIFactory._make_endpoint` — `def _make_endpoint(cls, gcp_project_id: str, *, gcp_location: str) -> str`
- `pipelex/plugins/plugin_factory_abstract.py:10` — `PluginFactoryAbstract.make_extras` — `def make_extras(self, inference_model: InferenceModelSpec, *, inference_job: InferenceJobAbstract, output_desc: str) -> tuple[dict[str, str], dict[str, Any]]`
- `pipelex/plugins/plugin_sdk_registry.py:22` — `PluginSdkRegistry.set_sdk_instance` — `def set_sdk_instance(self, plugin: Plugin, *, sdk_instance: Any) -> Any`
- `pipelex/plugins/portkey/portkey_completions_factory.py:95` — `PortkeyCompletionsFactory.make_portkey_openai_client_for_completions` — `def make_portkey_openai_client_for_completions(cls, plugin: Plugin, *, backend: InferenceBackend) -> openai.AsyncOpenAI`
- `pipelex/plugins/portkey/portkey_factory.py:40` — `PortkeyFactory.make_extras` — `def make_extras(cls, inference_model: InferenceModelSpec, *, inference_job: InferenceJobAbstract, output_desc: str) -> tuple[dict[str, str], dict[str, Any]]`
- `pipelex/plugins/portkey/portkey_responses_factory.py:26` — `PortkeyResponsesFactory.make_portkey_openai_client_for_responses` — `def make_portkey_openai_client_for_responses(cls, plugin: Plugin, *, backend: InferenceBackend) -> openai.AsyncOpenAI`

### `reporting` (5)

- `pipelex/reporting/reporting_manager.py:179` — `ReportingManager._emit_usage_event` — `def _emit_usage_event(self, inference_job: InferenceJobAbstract, *, tokens_usage: AnyTokensUsage) -> None`
- `pipelex/reporting/reporting_manager.py:229` — `ReportingManager._emit_via_registered_context` — `def _emit_via_registered_context(context: _EventLogContext, *, trace_context: TraceContext, tokens_usage: AnyTokensUsage) -> None`
- `pipelex/reporting/reporting_manager.py:251` — `ReportingManager._emit_best_effort` — `def _emit_best_effort(event_log: EventLogProtocol, *, event: UsageReportEvent) -> None`
- `pipelex/reporting/reporting_manager.py:265` — `ReportingManager._emit_usage_event_runner_fallback` — `def _emit_usage_event_runner_fallback(self, inference_job: InferenceJobAbstract, *, tokens_usage: AnyTokensUsage, trace_context: TraceContext) -> None`
- `pipelex/reporting/reporting_protocol.py:16` — `ReportingProtocol.set_event_log` — `def set_event_log(self, context_key: str, *, event_log: EventLogProtocol, workflow_id: str, pipeline_run_id: str) -> None`

### `runtime_bridge` (12)

- `pipelex/runtime_bridge/bridge.py:106` — `run_pipe_via_bridge` — `async def run_pipe_via_bridge(input_payload: PipelexPipeRunInput, *, trace_context: TraceContext | None=None) -> PipelexPipeRunOutput`
- `pipelex/runtime_bridge/bridge.py:160` — `build_pipe_job_from_input` — `def build_pipe_job_from_input(input_payload: PipelexPipeRunInput, *, library_crate: LibraryCrate | None, trace_context: TraceContext | None=None) -> PipeJob`
- `pipelex/runtime_bridge/bridge.py:240` — `_validate_input` — `def _validate_input(input_payload: PipelexPipeRunInput, *, delivery_assignment: DeliveryAssignment | None) -> None`
- `pipelex/runtime_bridge/bridge.py:270` — `_run_direct` — `async def _run_direct(pipe_job: PipeJob, *, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput`
- `pipelex/runtime_bridge/bridge.py:297` — `_run_temporal_blocking` — `async def _run_temporal_blocking(pipe_job: PipeJob, *, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput`
- `pipelex/runtime_bridge/bridge.py:330` — `_run_temporal_fire_and_forget` — `async def _run_temporal_fire_and_forget(pipe_job: PipeJob, *, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput`
- `pipelex/runtime_bridge/bridge.py:358` — `_serialize_completed_output` — `def _serialize_completed_output(pipe_output: PipeOutput, *, workflow_id: str | None) -> PipelexPipeRunOutput`
- `pipelex/runtime_bridge/bridge.py:408` — `_run_mistral_native` — `async def _run_mistral_native(pipe_job: PipeJob, *, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput`
- `pipelex/runtime_bridge/primitives/hydration.py:17` — `_validate_as_known_class` — `def _validate_as_known_class(item_class: type[StuffContent], *, raw_item: StuffContent | dict[str, Any]) -> StuffContent`
- `pipelex/runtime_bridge/primitives/hydration.py:75` — `hydrate_content` — `def hydrate_content(raw_content: list[Any] | dict[str, Any] | str, *, concept: Concept) -> StuffContent`
- `pipelex/runtime_bridge/primitives/scoped_library.py:16` — `scoped_library_for_crate` — `def scoped_library_for_crate(library_crate: LibraryCrate | None, *, library_id_prefix: str) -> Generator[str | None, None, None]`
- `pipelex/runtime_bridge/primitives/submitter_hydration.py:30` — `rehydrate_pipe_output_with_crate` — `def rehydrate_pipe_output_with_crate(pipe_output: PipeOutput, *, library_crate: 'LibraryCrate | None') -> PipeOutput`

### `system` (38)

- `pipelex/system/configuration/config_loader.py:90` — `ConfigLoader.resolve_config_file` — `def resolve_config_file(self, relative_path: str, *, config_dir: Path | None=None) -> Path`
- `pipelex/system/configuration/config_loader.py:171` — `ConfigLoader._override_files_for_dir` — `def _override_files_for_dir(cls, config_dir: Path, *, include_run_mode: bool) -> list[Path]`
- `pipelex/system/configuration/config_model.py:15` — `ConfigModel.transform_dict_str_to_enum` — `def transform_dict_str_to_enum(input_dict: dict[str, str], *, key_enum_cls: type[StrEnumType] | None=None, value_enum_cls: type[StrEnumType] | None=None) -> dict[str, StrEnumType] | dict[StrEnumType, str] | dict[StrEnumType, StrEnumType]`
- `pipelex/system/configuration/config_model.py:43` — `ConfigModel.transform_dict_of_floats_str_to_enum` — `def transform_dict_of_floats_str_to_enum(input_dict: dict[str, float], *, key_enum_cls: type[StrEnumType]) -> dict[StrEnumType, float]`
- `pipelex/system/configuration/config_model.py:61` — `ConfigModel.transform_dict_keys_str_to_enum` — `def transform_dict_keys_str_to_enum(input_dict: dict[str, Any], *, key_enum_cls: type[StrEnumType]) -> dict[StrEnumType, Any]`
- `pipelex/system/configuration/config_model.py:79` — `ConfigModel.transform_list_of_str_to_enum` — `def transform_list_of_str_to_enum(input_list: list[str], *, enum_cls: type[StrEnumType]) -> list[StrEnumType]`
- `pipelex/system/configuration/configs.py:234` — `MigrationConfig.text_in_renaming_keys` — `def text_in_renaming_keys(self, text: str, *, category: str) -> list[tuple[str, str]]`
- `pipelex/system/configuration/configs.py:240` — `MigrationConfig.text_in_renaming_values` — `def text_in_renaming_values(self, text: str, *, category: str) -> list[tuple[str, str]]`
- `pipelex/system/pipelex_service/gateway_config_merger.py:21` — `GatewayConfigMerger.merge` — `def merge(cls, gateway_model_specs: BackendModelSpecs, *, local_overrides: BackendModelSpecs) -> dict[str, Any]`
- `pipelex/system/pipelex_service/gateway_config_merger.py:69` — `GatewayConfigMerger._apply_overrides_to_model` — `def _apply_overrides_to_model(cls, model_name: str, *, gateway_model_specs: BackendModelSpecs, local_model_config: BackendModelSpecs) -> None`
- `pipelex/system/pipelex_service/pipelex_service_agreement.py:29` — `update_service_terms_acceptance` — `def update_service_terms_acceptance(accepted: bool, *, config_dir: Path | None=None) -> None`
- `pipelex/system/pipelex_service/pipelex_service_agreement.py:53` — `update_inference_setup_completed` — `def update_inference_setup_completed(completed: bool, *, config_dir: Path | None=None) -> None`
- `pipelex/system/pipelex_service/remote_config_fetcher.py:167` — `RemoteConfigFetcher._build_unavailable_error` — `def _build_unavailable_error(cls, fetch_error: RemoteConfigFetchError, *, cache_refused: bool=False) -> RemoteConfigUnavailableError`
- `pipelex/system/registries/class_registry_utils.py:21` — `ClassRegistryUtils.register_classes_in_file` — `def register_classes_in_file(cls, file_path: Path, *, base_class: type[Any] | None, is_include_imported: bool) -> None`
- `pipelex/system/registries/class_registry_utils.py:41` — `ClassRegistryUtils.register_classes_in_folder` — `def register_classes_in_folder(cls, folder_path: Path, *, base_class: type[Any] | None=None, is_recursive: bool=True, is_include_imported: bool=False, force_exclude_dirs: list[Path] | None=None) -> None`
- `pipelex/system/registries/class_registry_utils.py:77` — `ClassRegistryUtils.import_modules_in_folder` — `def import_modules_in_folder(cls, folder_path: Path, *, force_include_dirs: list[Path] | None=None, is_recursive: bool=True, base_class_names: list[str] | None=None) -> None`
- `pipelex/system/registries/func_registry.py:99` — `FuncRegistry.register_function` — `def register_function(self, func: Callable[..., Any], *, name: str | None=None) -> None`
- `pipelex/system/registries/func_registry.py:200` — `FuncRegistry.is_eligible_function` — `def is_eligible_function(self, func: Any, *, require_decorator: bool=False) -> bool`
- `pipelex/system/registries/func_registry.py:347` — `FuncRegistry.register_ineligible_function` — `def register_ineligible_function(self, func: Callable[..., Any], *, reason: str, source_file: str | None=None) -> None`
- `pipelex/system/registries/func_registry_utils.py:18` — `FuncRegistryUtils.register_pipe_funcs_from_package` — `def register_pipe_funcs_from_package(cls, package_name: str, *, package: Any) -> int`
- `pipelex/system/registries/func_registry_utils.py:75` — `FuncRegistryUtils.register_funcs_in_folder` — `def register_funcs_in_folder(cls, folder_path: Path, *, force_include_dirs: list[Path] | None=None, is_recursive: bool=True) -> None`
- `pipelex/system/telemetry/otel_factory.py:32` — `OtelFactory.make_truncated_content` — `def make_truncated_content(cls, content: str, *, max_length: int | None) -> str`
- `pipelex/system/telemetry/otel_factory.py:61` — `OtelFactory.make_inputs_json` — `def make_inputs_json(cls, working_memory: WorkingMemory, *, needed_input_names: set[str], max_length: int | None) -> str`
- `pipelex/system/telemetry/otel_factory.py:90` — `OtelFactory.make_output_json` — `def make_output_json(cls, pipe_output: PipeOutput, *, max_length: int | None) -> str`
- `pipelex/system/telemetry/otel_factory.py:133` — `OtelFactory.make_trace_names` — `def make_trace_names(cls, pipeline_run_id: str, *, pipe_code: str) -> tuple[str, str]`
- `pipelex/system/telemetry/otel_factory.py:198` — `OtelFactory.make_ai_tracer` — `def make_ai_tracer(cls, user_id: str | None, *, custom_posthog_client: 'Posthog | None', custom_redaction_config: TelemetryRedactionConfig, pipelex_posthog_client: 'Posthog | None', pipelex_gateway_redaction_config: TelemetryRedactionConfig, pipelex_distinct_id: str | None, otlp_exporters: list[OtlpExporterConfig] | None, langfuse_config: LangfuseConfig | None) -> 'tuple[OTelTracer, OTelTracerProvider]'`
- `pipelex/system/telemetry/posthog_span_exporter.py:43` — `PostHogSpanExporter._capture_event` — `def _capture_event(self, event: PostHogEvent, *, properties: dict[str, Any]) -> None`
- `pipelex/system/telemetry/posthog_span_exporter.py:99` — `PostHogSpanExporter._build_redacted_pipe_span_name` — `def _build_redacted_pipe_span_name(self, original_span_name: str, *, pipe_type: str | None) -> str`
- `pipelex/system/telemetry/posthog_span_exporter.py:127` — `PostHogSpanExporter._build_redacted_generation_span_name` — `def _build_redacted_generation_span_name(self, original_span_name: str, *, pipe_code: str | None, unit_job_id: str | None, model_name: str | None, output_class_name: str | None) -> str`
- `pipelex/system/telemetry/posthog_span_exporter.py:198` — `PostHogSpanExporter._get_base_properties` — `def _get_base_properties(self, span: ReadableSpan, *, attributes: Mapping[str, AttributeValue]) -> dict[str, Any]`
- `pipelex/system/telemetry/posthog_span_exporter.py:222` — `PostHogSpanExporter._export_generation_span` — `def _export_generation_span(self, span: ReadableSpan, *, attributes: Mapping[str, AttributeValue]) -> None`
- `pipelex/system/telemetry/posthog_span_exporter.py:288` — `PostHogSpanExporter._export_pipe_span` — `def _export_pipe_span(self, span: ReadableSpan, *, attributes: Mapping[str, AttributeValue]) -> None`
- `pipelex/system/telemetry/telemetry_factory.py:23` — `TelemetryFactory.make_telemetry_manager` — `def make_telemetry_manager(cls, secrets_provider: SecretsProviderAbstract, *, integration_mode: IntegrationMode, remote_config: RemoteConfig | None, is_pipelex_telemetry_enabled: bool=False, telemetry_config: TelemetryConfig | None=None, injected_telemetry_manager: TelemetryManagerAbstract | None=None) -> TelemetryManagerAbstract`
- `pipelex/system/telemetry/telemetry_manager.py:269` — `TelemetryManager._track_anonymous_event` — `def _track_anonymous_event(self, event_name: str, *, properties: dict[str, Any])`
- `pipelex/system/telemetry/telemetry_manager.py:277` — `TelemetryManager._track_identified_event` — `def _track_identified_event(self, event_name: str, *, properties: dict[str, Any], user_id: str)`
- `pipelex/system/telemetry/telemetry_manager.py:284` — `TelemetryManager._track_to_pipelex` — `def _track_to_pipelex(self, event_name: str, *, properties: dict[str, Any])`
- `pipelex/system/telemetry/telemetry_manager_abstract.py:97` — `TelemetryManagerAbstract.track_event` — `def track_event(self, event_name: EventName, *, properties: dict[EventProperty, Any] | None=None)`
- `pipelex/system/telemetry/telemetry_manager_abstract.py:156` — `TelemetryManagerAbstract.handle_trace_start` — `def handle_trace_start(self, trace_name: str, *, trace_name_redacted: str, trace_id: int) -> None`

### `temporal` (39)

- `pipelex/temporal/codec/codec_server.py:31` — `_set_cors_headers` — `def _set_cors_headers(response: web.Response, *, request_origin: str, cors_origins: list[str]) -> None`
- `pipelex/temporal/codec/codec_server.py:50` — `_error_response` — `def _error_response(request: web.Request, *, cors_origins: list[str], status: int, text: str) -> web.Response`
- `pipelex/temporal/codec/codec_server.py:89` — `build_codec_server` — `def build_codec_server(codec: StoragePayloadCodec, *, cors_origins: list[str]) -> web.Application`
- `pipelex/temporal/codec/storage_payload_codec.py:79` — `StoragePayloadCodec._build_storage_key` — `def _build_storage_key(self, payload: Payload, *, hash_hex: str) -> str`
- `pipelex/temporal/config_temporal.py:469` — `WorkerConfig.resolve_queue` — `def resolve_queue(self, activity_name: str, *, routing_key: str | None=None) -> str | None`
- `pipelex/temporal/config_temporal.py:508` — `WorkerConfig.resolve_dispatch` — `def resolve_dispatch(self, activity_name: str, *, routing_key: str | None=None, queue_options_by_queue: dict[str, 'QueueOptions'] | None=None, is_traced: bool=False) -> DispatchOptions`
- `pipelex/temporal/task_manager.py:15` — `TaskManager.complement_catalog` — `def complement_catalog(self, extra_catalog: dict[str, TaskPack], *, extra_workflows: list[WorkflowType], extra_activities: list[ActivityType])`
- `pipelex/temporal/task_manager.py:23` — `TaskManager.make_worker` — `def make_worker(self, temporal_client: TemporalClient, *, task_queue: str, is_not_sandboxed: bool=False, scope: WorkerScope | None=None, runtime_profile: WorkerRuntimeProfile | None=None, substitute_activities: dict[ActivityType, ActivityType] | None=None, test_workflows: WorkflowList | None=None, test_activities: ActivityList | None=None) -> Worker`
- `pipelex/temporal/task_manager.py:36` — `TaskManager.run_worker` — `async def run_worker(self, is_not_sandboxed: bool, *, is_unit_testing: bool, task_queue: str | None=None, scope_name: str | None=None, profile_name: str | None=None)`
- `pipelex/temporal/task_manager.py:48` — `TaskManager.workflows_and_activities` — `def workflows_and_activities(self, scope: WorkerScope | None=None, *, test_workflows: WorkflowList | None=None, test_activities: ActivityList | None=None, substitute_activities: dict[ActivityType, ActivityType] | None=None) -> tuple[list[WorkflowType], list[ActivityType]]`
- `pipelex/temporal/temporal_connect.py:18` — `connect_to_temporal_server` — `async def connect_to_temporal_server(server_config: TemporalServerConfig, *, name: str | None=None) -> TemporalClient`
- `pipelex/temporal/temporal_data_converter.py:64` — `BaseModelPayloadConverter._kajson_to_payload` — `def _kajson_to_payload(self, value: object, *, source_type_holder: object) -> Payload`
- `pipelex/temporal/temporal_data_converter.py:97` — `BaseModelPayloadConverter._restore_class_source` — `def _restore_class_source(self, value: BaseModel, *, class_source_code: str) -> None`
- `pipelex/temporal/temporal_manager.py:47` — `TemporalManager.connect_temporal` — `async def connect_temporal(self, temporal_client: TemporalClient | None=None, *, temporal_server_config: TemporalServerConfig | None=None, temporal_selected_server: str | None=None) -> TemporalClient`
- `pipelex/temporal/temporal_tasks.py:19` — `TemporalTasks.complement_catalog` — `def complement_catalog(self, extra_catalog: dict[str, TaskPack], *, extra_workflows: list[WorkflowType], extra_activities: list[ActivityType])`
- `pipelex/temporal/temporal_tasks.py:38` — `TemporalTasks.replace_catalog` — `def replace_catalog(self, new_catalog: dict[str, TaskPack], *, new_workflows: list[WorkflowType], new_activities: list[ActivityType])`
- `pipelex/temporal/temporal_tasks.py:68` — `TemporalTasks._register_workflow` — `def _register_workflow(cls, all_workflows: dict[str, WorkflowType], *, workflow: WorkflowType, source: str) -> None`
- `pipelex/temporal/temporal_tasks.py:79` — `TemporalTasks._register_activity` — `def _register_activity(cls, all_activities: dict[str, ActivityType], *, activity: ActivityType, source: str) -> None`
- `pipelex/temporal/temporal_tasks.py:89` — `TemporalTasks.workflows_and_activities` — `def workflows_and_activities(self, scope: WorkerScope | None=None, *, test_workflows: WorkflowList | None=None, test_activities: ActivityList | None=None, substitute_activities: dict[ActivityType, ActivityType] | None=None) -> tuple[list[WorkflowType], list[ActivityType]]`
- `pipelex/temporal/temporal_tasks.py:122` — `TemporalTasks._resolve_scope` — `def _resolve_scope(self, scope: WorkerScope, *, all_workflows: dict[str, WorkflowType], all_activities: dict[str, ActivityType]) -> tuple[set[WorkflowType], set[ActivityType]]`
- `pipelex/temporal/tprl/namespace_check.py:71` — `format_temporal_cli_command` — `def format_temporal_cli_command(missing: Sequence[str], *, namespace: str) -> str`
- `pipelex/temporal/tprl/namespace_check.py:84` — `format_tcld_cli_command` — `def format_tcld_cli_command(missing: Sequence[str], *, namespace: str) -> str`
- `pipelex/temporal/tprl/namespace_check.py:94` — `check_required_search_attributes` — `async def check_required_search_attributes(temporal_client: TemporalClient, *, namespace: str, configured_attributes: Sequence[str]) -> None`
- `pipelex/temporal/tprl/namespace_check.py:155` — `ensure_required_search_attributes_registered` — `async def ensure_required_search_attributes_registered(temporal_client: TemporalClient, *, namespace: str, configured_attributes: Sequence[str]) -> RegistrationFailure | tuple[str, ...]`
- `pipelex/temporal/tprl/observability.py:38` — `_truncate_utf8` — `def _truncate_utf8(text: str, *, max_bytes: int) -> str`
- `pipelex/temporal/tprl/observability.py:163` — `build_activity_summary` — `def build_activity_summary(method_label: str, *, job_metadata: JobMetadata, extras: Mapping[str, str] | None=None) -> str`
- `pipelex/temporal/tprl/temporal_error.py:232` — `TemporalError.from_message_exception` — `def from_message_exception(cls, exc: PipelexError, *, force_non_retryable: bool=False) -> Self`
- `pipelex/temporal/tprl/temporal_error.py:270` — `TemporalError._is_non_retryable` — `def _is_non_retryable(cls, exc: PipelexError, *, error_type: str) -> bool`
- `pipelex/temporal/tprl/workflow_caller.py:91` — `WorkflowExecutor.execute_workflow` — `async def execute_workflow(self, workflow_class: type[WorkflowClass[WorkflowInput, WorkflowOutput]], *, workflow_arg: WorkflowInput, workflow_id: str, search_attributes: TypedSearchAttributes | None=None, static_summary: str | None=None, static_details: str | None=None, memo: Mapping[str, Any] | None=None) -> WorkflowOutput`
- `pipelex/temporal/tprl/workflow_caller.py:140` — `WorkflowExecutor.start_workflow` — `async def start_workflow(self, workflow_class: type[WorkflowClass[WorkflowInput, WorkflowOutput]], *, workflow_arg: WorkflowInput, workflow_id: str, callbacks: Sequence[Callback] | None=None, search_attributes: TypedSearchAttributes | None=None, static_summary: str | None=None, static_details: str | None=None, memo: Mapping[str, Any] | None=None) -> WorkflowHandle[WorkflowClass[WorkflowInput, WorkflowOutput], WorkflowOutput]`
- `pipelex/temporal/tprl/workflow_caller.py:180` — `WorkflowExecutor.execute_child_workflow` — `async def execute_child_workflow(self, workflow_class: type[WorkflowClass[WorkflowInput, WorkflowOutput]], *, workflow_arg: WorkflowInput, workflow_id: str, child_task_queue: str | None=None, search_attributes: TypedSearchAttributes | None=None, static_summary: str | None=None, static_details: str | None=None, memo: Mapping[str, Any] | None=None) -> WorkflowOutput`
- `pipelex/temporal/tprl/workflow_caller.py:246` — `WorkflowExecutor.start_child_workflow` — `async def start_child_workflow(self, workflow_class: type[WorkflowClass[WorkflowInput, WorkflowOutput]], *, workflow_arg: WorkflowInput, workflow_id: str, child_task_queue: str | None=None, search_attributes: TypedSearchAttributes | None=None, static_summary: str | None=None, static_details: str | None=None, memo: Mapping[str, Any] | None=None) -> ChildWorkflowHandle[WorkflowClass[WorkflowInput, WorkflowOutput], WorkflowOutput]`
- `pipelex/temporal/tprl/workflow_caller.py:298` — `WorkflowExecutorFactory.create_executor` — `def create_executor(cls, task_queue: str | None=None, *, workflow_execution_timeout: timedelta | None=None, retry_policy: RetryPolicy | None=None, run_timeout: timedelta | None=None, task_timeout: timedelta | None=None, start_delay: timedelta | None=None, rpc_timeout: timedelta | None=None, temporal_client: TemporalClient | None=None, should_auto_connect_temporal: bool=False, worker_environment: TemporalWorkerEnvironment=TemporalWorkerEnvironment.EXTERNAL) -> WorkflowExecutor[WorkflowInput, WorkflowOutput]`
- `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py:51` — `_revalidate_against_object_class` — `def _revalidate_against_object_class(raw_obj: BaseModel, *, object_class: type[BaseModelTypeVar], is_mock_built: bool) -> BaseModelTypeVar`
- `pipelex/temporal/tprl_pipe/dry_validate_dispatch.py:22` — `dispatch_dry_validate` — `async def dispatch_dry_validate(arg: DryValidateArg, *, task_queue: str | None=None, should_auto_connect_temporal: bool=True) -> DryValidateResult`
- `pipelex/temporal/tprl_pipe/temporal_pipe_router.py:127` — `make_temporal_pipe_router` — `def make_temporal_pipe_router(task_queue: str | None=None, *, workflow_execution_timeout: timedelta | None=None, retry_policy: RetryPolicy | None=None, should_auto_connect_temporal: bool=True, worker_environment: TemporalWorkerEnvironment=TemporalWorkerEnvironment.EXTERNAL) -> TemporalPipeRouter`
- `pipelex/temporal/tprl_pipe/temporal_pipe_run.py:92` — `TemporalPipeRun.start` — `async def start(self, pipe_job: PipeJob, *, delivery_assignment: DeliveryAssignment | None=None) -> tuple[str, WorkflowHandle[WorkflowClass[PipeRunArg, PipeOutput], PipeOutput]]`
- `pipelex/temporal/tprl_pipe/temporal_pipe_run.py:131` — `make_temporal_pipe_run` — `def make_temporal_pipe_run(task_queue: str | None=None, *, workflow_execution_timeout: timedelta | None=None, retry_policy: RetryPolicy | None=None, should_auto_connect_temporal: bool=True, worker_environment: TemporalWorkerEnvironment=TemporalWorkerEnvironment.EXTERNAL) -> TemporalPipeRun`
- `pipelex/temporal/worker_cli.py:25` — `run_worker` — `async def run_worker(project: str | None=None, *, is_not_sandboxed: bool=False, is_unit_testing: bool=False, task_queue: str | None=None, scope_name: str | None=None, profile_name: str | None=None)`

### `tools` (128)

- `pipelex/tools/jinja2/image_renderable.py:36` — `ImageRenderable.render_with_images` — `def render_with_images(self, registry: ImageRegistry, *, text_format: TextFormat) -> str`
- `pipelex/tools/jinja2/jinja2_environment.py:9` — `make_jinja2_env_from_loader` — `def make_jinja2_env_from_loader(template_category: TemplateCategory, *, loader: BaseLoader, enable_async: bool=True) -> Environment`
- `pipelex/tools/jinja2/jinja2_environment.py:57` — `_register_filters` — `def _register_filters(jinja2_env: Environment, *, template_category: TemplateCategory, enable_async: bool) -> None`
- `pipelex/tools/jinja2/jinja2_environment.py:81` — `make_jinja2_env_without_loader` — `def make_jinja2_env_without_loader(template_category: TemplateCategory, *, enable_async: bool=True) -> Environment`
- `pipelex/tools/jinja2/jinja2_environment.py:97` — `make_jinja2_env_from_registry` — `def make_jinja2_env_from_registry(template_category: TemplateCategory, *, enable_async: bool=True) -> Environment`
- `pipelex/tools/jinja2/jinja2_filters.py:110` — `apply_tag_style` — `def apply_tag_style(context: Context, *, value: str, tag_name: str | None=None) -> str`
- `pipelex/tools/jinja2/jinja2_parsing.py:8` — `check_jinja2_parsing` — `def check_jinja2_parsing(template_source: str, *, template_category: TemplateCategory=TemplateCategory.LLM_PROMPT)`
- `pipelex/tools/jinja2/jinja2_rendering.py:24` — `_add_to_templating_context` — `def _add_to_templating_context(templating_context: dict[str, Any], *, jinja2_context_key: Jinja2ContextKey, value: Any) -> None`
- `pipelex/tools/jinja2/jinja2_rendering.py:37` — `_compile_jinja2_template` — `def _compile_jinja2_template(template_source: str, *, template_category: TemplateCategory, use_registry: bool=False, enable_async: bool=True, finalize: Callable[[Any], Any] | None=None) -> _Jinja2Template`
- `pipelex/tools/jinja2/jinja2_rendering.py:66` — `_prepare_templating_context` — `def _prepare_templating_context(templating_context: dict[str, Any], *, templating_style: TemplatingStyle | None) -> dict[str, Any]`
- `pipelex/tools/jinja2/jinja2_rendering.py:87` — `_make_type_error_msg` — `def _make_type_error_msg(template_source: str, *, templating_context: dict[str, Any], type_error: TypeError) -> str`
- `pipelex/tools/jinja2/jinja2_rendering.py:97` — `_make_non_type_error_msg` — `def _make_non_type_error_msg(template_source: str, *, error_label: str, error: Jinja2StuffError | TemplateSyntaxError | UndefinedError | Jinja2ContextError) -> str`
- `pipelex/tools/jinja2/jinja2_rendering.py:106` — `_render_template_sync` — `def _render_template_sync(template_source: str, *, template: _Jinja2Template, templating_context: dict[str, Any]) -> str`
- `pipelex/tools/jinja2/jinja2_rendering.py:127` — `_render_template_async` — `async def _render_template_async(template_source: str, *, template: _Jinja2Template, templating_context: dict[str, Any]) -> str`
- `pipelex/tools/jinja2/jinja2_rendering.py:148` — `render_jinja2_sync` — `def render_jinja2_sync(template_source: str, *, template_category: TemplateCategory, templating_context: dict[str, Any], templating_style: TemplatingStyle | None=None, use_registry: bool=False) -> str`
- `pipelex/tools/jinja2/jinja2_rendering.py:173` — `render_jinja2_async` — `async def render_jinja2_async(template_source: str, *, template_category: TemplateCategory, templating_context: dict[str, Any], templating_style: TemplatingStyle | None=None, use_registry: bool=False, finalize: Callable[[Any], Any] | None=None) -> str`
- `pipelex/tools/jinja2/jinja2_required_variables.py:66` — `_collect_full_variable_paths` — `def _collect_full_variable_paths(node: nodes.Node, *, paths: set[str], declared_names: set[str]) -> None`
- `pipelex/tools/jinja2/jinja2_required_variables.py:121` — `detect_jinja2_required_variables` — `def detect_jinja2_required_variables(template_category: TemplateCategory, *, template_source: str) -> set[str]`
- `pipelex/tools/jinja2/jinja2_required_variables.py:185` — `_collect_variable_references` — `def _collect_variable_references(node: nodes.Node, *, references: dict[str, VariableReference], declared_names: set[str]) -> None`
- `pipelex/tools/jinja2/jinja2_required_variables.py:255` — `detect_jinja2_variable_references` — `def detect_jinja2_variable_references(template_category: TemplateCategory, *, template_source: str) -> list[VariableReference]`
- `pipelex/tools/jinja2/jinja2_with_images_filter.py:78` — `_render_sequence_with_images` — `def _render_sequence_with_images(sequence: list[Any] | tuple[Any, ...], *, registry: ImageRegistry, text_format: TextFormat) -> str`
- `pipelex/tools/log/log.py:203` — `Log.set_level_for_package` — `def set_level_for_package(self, package_name: str, *, level: LogLevel)`
- `pipelex/tools/log/log.py:224` — `Log.verbose` — `def verbose(self, content: str | Any, *, title: str | None=None, inline: str | None=None)`
- `pipelex/tools/log/log.py:243` — `Log.debug` — `def debug(self, content: str | Any, *, title: str | None=None, inline: str | None=None)`
- `pipelex/tools/log/log.py:262` — `Log.dev` — `def dev(self, content: str | Any, *, title: str | None=None, inline: str | None=None)`
- `pipelex/tools/log/log.py:281` — `Log.info` — `def info(self, content: str | Any, *, title: str | None=None, inline: str | None=None)`
- `pipelex/tools/log/log.py:300` — `Log.warning` — `def warning(self, content: str | Any, *, title: str | None=None, inline: str | None=None, problem_id: str | None=None)`
- `pipelex/tools/log/log.py:323` — `Log.error` — `def error(self, content: str | Any, *, title: str | None=None, inline: str | None=None, include_exception: bool=False, problem_id: str | None=None)`
- `pipelex/tools/log/log.py:354` — `Log.critical` — `def critical(self, content: str | Any, *, title: str | None=None, inline: str | None=None, include_exception: bool=False, problem_id: str | None=None)`
- `pipelex/tools/log/log_dispatch.py:66` — `LogDispatch.dispatch` — `def dispatch(self, content: str | Any, *, severity: int, title: str | None=None, inline: str | None=None, include_exception: bool=False)`
- `pipelex/tools/log/log_dispatch.py:125` — `LogDispatch._log_message` — `def _log_message(self, message: str, *, severity: int, caller_info_str: str | None, title: str | None=None, inline: str | None=None, include_exception: bool=False)`
- `pipelex/tools/log/log_dispatch.py:160` — `LogDispatch._log_data` — `def _log_data(self, data: Any, *, severity: int, caller_info_str: str | None, title: str | None=None, include_exception: bool=False)`
- `pipelex/tools/log/log_dispatch.py:234` — `LogDispatch._log_to_console` — `def _log_to_console(self, message: str, *, severity: int)`
- `pipelex/tools/mermaid/mermaid_utils.py:64` — `print_mermaid_url` — `def print_mermaid_url(url: str, *, title: str) -> None`
- `pipelex/tools/mermaid/mermaid_utils.py:142` — `render_mermaid_html_generic` — `def render_mermaid_html_generic(mermaid_code: str, *, title: str='Mermaid Diagram', theme: str='default') -> str`
- `pipelex/tools/mermaid/mermaid_utils.py:173` — `render_mermaid_html_generic_async` — `async def render_mermaid_html_generic_async(mermaid_code: str, *, title: str='Mermaid Diagram', theme: str='default') -> str`
- `pipelex/tools/misc/async_utils.py:19` — `gather_bounded` — `async def gather_bounded(task_factories: Sequence[Callable[[], Awaitable[_T]]], *, max_concurrency: int | None) -> list[_T]`
- `pipelex/tools/misc/attribute_utils.py:12` — `AttributePolisher._truncate_string` — `def _truncate_string(cls, value: str, *, max_length: int) -> str`
- `pipelex/tools/misc/attribute_utils.py:19` — `AttributePolisher._truncate_bytes` — `def _truncate_bytes(cls, value: bytes, *, max_length: int) -> bytes`
- `pipelex/tools/misc/attribute_utils.py:65` — `AttributePolisher.apply_truncation_recursive` — `def apply_truncation_recursive(cls, obj: Any, *, name: str | None=None) -> Any`
- `pipelex/tools/misc/base64_utils.py:38` — `make_base64_url` — `def make_base64_url(base64_data: str, *, file_type: FileType) -> str`
- `pipelex/tools/misc/context_provider_abstract.py:11` — `ContextProviderAbstract.get_typed_object_or_attribute` — `def get_typed_object_or_attribute(self, name: str, *, wanted_type: type[Any] | None=None, accept_list: bool=False) -> Any`
- `pipelex/tools/misc/dict_utils.py:14` — `insert_before` — `def insert_before(dictionary: dict[K, V], *, target_key: K, new_key: K, new_value: V) -> dict[K, V]`
- `pipelex/tools/misc/dict_utils.py:51` — `apply_to_strings_recursive` — `def apply_to_strings_recursive(data: Any, *, transform_func: Callable[[str], str]) -> dict[str, Any]`
- `pipelex/tools/misc/dict_utils.py:86` — `apply_to_strings_in_list` — `def apply_to_strings_in_list(data: list[Any], *, transform_func: Callable[[str], str]) -> list[Any]`
- `pipelex/tools/misc/dict_utils.py:102` — `substitute_nested_in_context` — `def substitute_nested_in_context(context: dict[str, Any], *, extra_params: dict[str, Any] | None=None) -> dict[str, Any]`
- `pipelex/tools/misc/diff.py:97` — `_generate_diff_summary` — `def _generate_diff_summary(diff_content: str, *, left_is_newer: bool) -> str | None`
- `pipelex/tools/misc/diff.py:241` — `make_diff_dirs_pretty._collect_diffs` — `def _collect_diffs(dir_comparison: filecmp.dircmp[str], *, relative_path: str='') -> None`
- `pipelex/tools/misc/file_fetch_utils.py:7` — `fetch_file_from_url_httpx` — `async def fetch_file_from_url_httpx(url: str, *, request_timeout: int | None=None) -> bytes`
- `pipelex/tools/misc/file_utils.py:13` — `reject_bare_str_or_path` — `def reject_bare_str_or_path(value: object, *, param_name: str) -> None`
- `pipelex/tools/misc/file_utils.py:38` — `save_bytes_to_binary_file` — `def save_bytes_to_binary_file(byte_data: bytes, *, file_path: Path, create_directory: bool=False) -> Path`
- `pipelex/tools/misc/file_utils.py:59` — `save_text_to_path` — `def save_text_to_path(text: str, *, path: Path, create_directory: bool=False)`
- `pipelex/tools/misc/file_utils.py:151` — `copy_file_from_package` — `def copy_file_from_package(package_name: str, *, file_path_in_package: str, target_path: Path, overwrite: bool=True) -> None`
- `pipelex/tools/misc/file_utils.py:167` — `copy_folder_from_package` — `def copy_folder_from_package(package_name: str, *, folder_path_in_package: str, target_dir: Path, overwrite: bool=True, non_overwrite_files: list[str] | None=None) -> None`
- `pipelex/tools/misc/file_utils.py:460` — `get_incremental_directory_path` — `def get_incremental_directory_path(base_path: Path, *, base_name: str, start_at: int=1) -> Path`
- `pipelex/tools/misc/file_utils.py:486` — `get_incremental_file_path` — `def get_incremental_file_path(base_path: Path, *, base_name: str, extension: str, start_at: int=1, avoid_suffix_if_possible: bool=False) -> Path`
- `pipelex/tools/misc/file_utils.py:532` — `find_files_in_dir` — `def find_files_in_dir(dir_path: Path, *, pattern: str, is_recursive: bool=True, excluded_dirs: list[str] | None=None, force_include_dirs: list[str] | None=None) -> list[Path]`
- `pipelex/tools/misc/hash_utils.py:4` — `hash_sha256` — `def hash_sha256(data: str | bytes, *, length: int | None=None) -> str`
- `pipelex/tools/misc/image_utils.py:95` — `pil_image_to_bytes` — `def pil_image_to_bytes(pil_image: Image.Image, *, image_format: ImageFormat | None) -> bytes`
- `pipelex/tools/misc/json_utils.py:71` — `clean_json_dumps` — `def clean_json_dumps(data: Any, *, indent: int | None=None) -> str`
- `pipelex/tools/misc/json_utils.py:92` — `json_str` — `def json_str(some_object: Any, *, title: str | None=None, is_spaced: bool=False) -> str`
- `pipelex/tools/misc/json_utils.py:128` — `save_as_json_to_path` — `def save_as_json_to_path(object_to_save: Any, *, path: Path, indent: int | None=4, is_warning_enabled: bool=True, create_directory: bool=False)`
- `pipelex/tools/misc/json_utils.py:227` — `deep_update` — `def deep_update(target_dict: dict[str, Any], *, updates: Mapping[str, Any])`
- `pipelex/tools/misc/json_utils.py:315` — `purify_json` — `def purify_json(data: Any, *, indent: int | None=None, is_truncate_bytes_enabled: bool=False, is_warning_enabled: bool=True) -> tuple[dict[Any, Any] | list[Any], str]`
- `pipelex/tools/misc/json_utils.py:395` — `purify_json_list` — `def purify_json_list(data: list[Any], *, indent: int | None=None, is_truncate_bytes_enabled: bool=False) -> tuple[list[Any], str]`
- `pipelex/tools/misc/json_utils.py:453` — `purify_json_dict` — `def purify_json_dict(data: Any, *, indent: int | None=None, is_warning_enabled: bool=True) -> tuple[dict[str, Any], str]`
- `pipelex/tools/misc/json_utils.py:508` — `pure_json_str` — `def pure_json_str(data: Any, *, indent: int | None=None, is_warning_enabled: bool=True) -> str`
- `pipelex/tools/misc/markdown_utils.py:7` — `convert_to_markdown` — `def convert_to_markdown(data: Any, *, level: int=1, is_pretty: bool=False) -> str`
- `pipelex/tools/misc/pretty.py:99` — `pretty_print` — `def pretty_print(content: str | Any, *, title: TextType | None=None, subtitle: TextType | None=None, inner_title: str | None=None, border_style: StyleType | None=None, width: int | None=None, console_width: int | None=None)`
- `pipelex/tools/misc/pretty.py:120` — `pretty_print_md` — `def pretty_print_md(content: str, *, title: TextType | None=None, subtitle: TextType | None=None, inner_title: str | None=None, border_style: StyleType | None=None, width: int | None=None, console_width: int | None=None)`
- `pipelex/tools/misc/pretty.py:143` — `pretty_print_url` — `def pretty_print_url(url: str, *, title: TextType | None=None, subtitle: TextType | None=None, inner_title: str | None=None, border_style: StyleType | None=None, width: int | None=None, console_width: int | None=None)`
- `pipelex/tools/misc/pretty.py:170` — `PrettyPrinter.pretty_print` — `def pretty_print(cls, content: str | Any, *, title: TextType | None=None, subtitle: TextType | None=None, inner_title: str | None=None, border_style: StyleType | None=None, width: int | None=None, console_width: int | None=None)`
- `pipelex/tools/misc/pretty.py:198` — `PrettyPrinter.pretty_print_using_rich` — `def pretty_print_using_rich(cls, content: str | Any, *, title: TextType | None=None, subtitle: TextType | None=None, inner_title: str | None=None, border_style: StyleType | None=None, width: int | None=None, console_width: int | None=None)`
- `pipelex/tools/misc/pretty.py:222` — `PrettyPrinter.pretty_width` — `def pretty_width(cls, width: int | None=None, *, depth: int | None=None) -> int`
- `pipelex/tools/misc/pretty.py:234` — `PrettyPrinter.make_pretty_panel` — `def make_pretty_panel(cls, content: str | Any, *, title: TextType | None=None, subtitle: TextType | None=None, inner_title: str | None=None, border_style: StyleType | None=None, width: int | None=None, console_width: int | None=None) -> Panel`
- `pipelex/tools/misc/pretty.py:259` — `PrettyPrinter.wrap_in_panel` — `def wrap_in_panel(cls, pretty: PrettyPrintable, *, title: TextType | None=None, subtitle: TextType | None=None, border_style: StyleType | None=None, width: int | None=None) -> Panel`
- `pipelex/tools/misc/pretty.py:282` — `PrettyPrinter.pretty_text` — `def pretty_text(cls, pretty: PrettyPrintable, *, width: int=PRETTY_WIDTH_FOR_EXPORT) -> str`
- `pipelex/tools/misc/pretty.py:303` — `PrettyPrinter.pretty_html` — `def pretty_html(cls, pretty: PrettyPrintable, *, width: int=PRETTY_WIDTH_FOR_EXPORT) -> str`
- `pipelex/tools/misc/pretty.py:315` — `PrettyPrinter.pretty_svg` — `def pretty_svg(cls, pretty: PrettyPrintable, *, width: int=PRETTY_WIDTH_FOR_EXPORT) -> str`
- `pipelex/tools/misc/pretty.py:322` — `PrettyPrinter.make_pretty` — `def make_pretty(cls, value: Any, *, inner_title: str | None=None, depth: int=0) -> PrettyPrintable`
- `pipelex/tools/misc/pretty.py:381` — `PrettyPrinter.pretty_print_without_rich` — `def pretty_print_without_rich(cls, content: str | Any, *, title: TextType | None=None, subtitle: TextType | None=None, inner_title: str | None=None, width: int | None=None, console_width: int | None=None)`
- `pipelex/tools/misc/pretty.py:438` — `PrettyPrinter.pretty_print_url_without_rich` — `def pretty_print_url_without_rich(cls, content: str | Any, *, title: TextType | None=None, subtitle: TextType | None=None)`
- `pipelex/tools/misc/semver.py:59` — `version_satisfies` — `def version_satisfies(version: Version, *, constraint: SimpleSpec) -> bool`
- `pipelex/tools/misc/semver.py:73` — `select_minimum_version` — `def select_minimum_version(available_versions: list[Version], *, constraint: SimpleSpec) -> Version | None`
- `pipelex/tools/misc/semver.py:96` — `select_minimum_version_for_multiple_constraints` — `def select_minimum_version_for_multiple_constraints(available_versions: list[Version], *, constraints: list[SimpleSpec]) -> Version | None`
- `pipelex/tools/misc/string_utils.py:335` — `matches_wildcard_pattern` — `def matches_wildcard_pattern(text: str, *, pattern: str) -> bool`
- `pipelex/tools/misc/toml_sync.py:42` — `get_nested_value` — `def get_nested_value(doc: TOMLDocument | Table | dict[str, Any], *, key_path: str) -> tuple[bool, Any]`
- `pipelex/tools/misc/toml_sync.py:69` — `set_nested_value` — `def set_nested_value(doc: TOMLDocument | Table | dict[str, Any], *, key_path: str, value: Any) -> bool`
- `pipelex/tools/misc/toml_sync.py:120` — `collect_leaf_key_paths` — `def collect_leaf_key_paths(doc: TOMLDocument | Table | dict[str, Any], *, prefix: str='') -> list[str]`
- `pipelex/tools/misc/toml_utils.py:67` — `save_toml_to_path` — `def save_toml_to_path(data: dict[str, Any] | tomlkit.TOMLDocument, *, path: str | Path) -> None`
- `pipelex/tools/network/ssrf_guard.py:37` — `resolve_to_allowed_ips` — `async def resolve_to_allowed_ips(host: str, *, port: int, timeout: float | None=None) -> list[str]`
- `pipelex/tools/pdf/pypdfium2_renderer.py:68` — `_extract_image_from_pdf_object` — `def _extract_image_from_pdf_object(image_obj: PdfImage, *, output_format: ImageFormat | None) -> ExtractedImageFromPage`
- `pipelex/tools/pdf/pypdfium2_renderer.py:159` — `PyPdfium2Renderer._render_pdf_pages_sync` — `def _render_pdf_pages_sync(pdf_input: PdfInput, *, scale: float) -> list[Image.Image]`
- `pipelex/tools/pdf/pypdfium2_renderer.py:190` — `PyPdfium2Renderer._extract_embedded_images_from_page_sync` — `def _extract_embedded_images_from_page_sync(pdf_input: PdfInput, *, page_index: int, max_depth: int=DEFAULT_IMAGE_EXTRACTION_MAX_DEPTH, output_format: ImageFormat | None=None) -> list[ExtractedImageFromPage]`
- `pipelex/tools/pdf/pypdfium2_renderer.py:227` — `PyPdfium2Renderer._extract_embedded_images_from_pdf_sync` — `def _extract_embedded_images_from_pdf_sync(pdf_input: PdfInput, *, max_depth: int=DEFAULT_IMAGE_EXTRACTION_MAX_DEPTH, output_format: ImageFormat | None=None) -> dict[int, list[ExtractedImageFromPage]]`
- `pipelex/tools/pdf/pypdfium2_renderer.py:267` — `PyPdfium2Renderer.render_pdf_pages` — `async def render_pdf_pages(self, pdf_input: PdfInput, *, dpi: int) -> list[Image.Image]`
- `pipelex/tools/pdf/pypdfium2_renderer.py:278` — `PyPdfium2Renderer.render_pdf_pages_from_uri` — `async def render_pdf_pages_from_uri(self, pdf_uri: str, *, dpi: int) -> list[Image.Image]`
- `pipelex/tools/pdf/pypdfium2_renderer.py:287` — `PyPdfium2Renderer.extract_embedded_images_from_page` — `async def extract_embedded_images_from_page(self, pdf_input: PdfInput, *, page_index: int, max_depth: int=DEFAULT_IMAGE_EXTRACTION_MAX_DEPTH, output_format: ImageFormat | None=None) -> list[ExtractedImageFromPage]`
- `pipelex/tools/pdf/pypdfium2_renderer.py:316` — `PyPdfium2Renderer.extract_embedded_images_from_pdf` — `async def extract_embedded_images_from_pdf(self, pdf_input: PdfInput, *, max_depth: int=DEFAULT_IMAGE_EXTRACTION_MAX_DEPTH, output_format: ImageFormat | None=None) -> dict[int, list[ExtractedImageFromPage]]`
- `pipelex/tools/pdf/pypdfium2_renderer.py:342` — `PyPdfium2Renderer.extract_embedded_images_from_pdf_uri` — `async def extract_embedded_images_from_pdf_uri(self, pdf_uri: str, *, max_depth: int=DEFAULT_IMAGE_EXTRACTION_MAX_DEPTH, output_format: ImageFormat | None=None) -> dict[int, list[ExtractedImageFromPage]]`
- `pipelex/tools/secrets/secrets_provider_abstract.py:14` — `SecretsProviderAbstract.get_required_secret_specific_version` — `def get_required_secret_specific_version(self, secret_id: str, *, version_id: str) -> str`
- `pipelex/tools/secrets/secrets_provider_abstract.py:17` — `SecretsProviderAbstract.get_optional_secret_specific_version` — `def get_optional_secret_specific_version(self, secret_id: str, *, version_id: str) -> str | None`
- `pipelex/tools/secrets/secrets_provider_abstract.py:20` — `SecretsProviderAbstract.set_secret_as_env_var` — `def set_secret_as_env_var(self, secret_id: str, *, version_id: str=LATEST_SECRET_VERSION_NAME)`
- `pipelex/tools/secrets/secrets_utils.py:22` — `substitute_vars` — `def substitute_vars(content: str, *, secrets_provider: SecretsProviderAbstract, raise_on_missing_var: bool=True) -> str`
- `pipelex/tools/secrets/secrets_utils.py:92` — `_handle_fallback_pattern` — `def _handle_fallback_pattern(var_spec: str, *, secrets_provider: SecretsProviderAbstract) -> str`
- `pipelex/tools/secrets/secrets_utils.py:139` — `_get_secret` — `def _get_secret(secret_name: str, *, secrets_provider: SecretsProviderAbstract) -> str`
- `pipelex/tools/storage/gcp_storage_provider.py:134` — `GcpStorageProvider._store_sync` — `def _store_sync(self, data: bytes, *, key: str, content_type: str | None) -> None`
- `pipelex/tools/storage/storage_provider_abstract.py:97` — `StorageProviderAbstract.store` — `async def store(self, data: bytes, *, key: str, content_type: str | None=None) -> str`
- `pipelex/tools/storage/storage_provider_abstract.py:113` — `StorageProviderAbstract._store` — `async def _store(self, data: bytes, *, key: str, content_type: str | None) -> None`
- `pipelex/tools/tabular/csv_codec.py:141` — `_validate_header` — `def _validate_header(header: list[str], *, path: Path) -> None`
- `pipelex/tools/tabular/csv_codec.py:160` — `_read_table` — `def _read_table(path: Path, *, delimiter: str, encoding: str) -> tuple[list[str], list[tuple[int, list[str]]]]`
- `pipelex/tools/tabular/csv_codec.py:219` — `_row_to_dict` — `def _row_to_dict(data_row: list[str], *, header: list[str]) -> dict[str, str]`
- `pipelex/tools/tabular/csv_codec.py:224` — `read_rows` — `def read_rows(path: Path, *, delimiter: str=DEFAULT_DELIMITER, encoding: str=DEFAULT_READ_ENCODING) -> list[dict[str, str]]`
- `pipelex/tools/tabular/csv_codec.py:312` — `list_content_from_csv` — `def list_content_from_csv(path: Path, *, row_model: type[StuffContentType], delimiter: str=DEFAULT_DELIMITER, encoding: str=DEFAULT_READ_ENCODING) -> ListContent[StuffContentType]`
- `pipelex/tools/tabular/csv_codec.py:379` — `csv_from_list_content` — `def csv_from_list_content(list_content: ListContent[StuffContentType], *, row_model: type[StuffContentType], path: Path, delimiter: str=DEFAULT_DELIMITER, encoding: str=DEFAULT_ENCODING) -> None`
- `pipelex/tools/typing/class_utils.py:122` — `has_compatible_field` — `def has_compatible_field(model_cls: type[Any], *, target_type: type[Any]) -> bool`
- `pipelex/tools/typing/module_inspector.py:100` — `find_class_names_in_file` — `def find_class_names_in_file(file_path: Path, *, base_class_names: list[str] | None=None) -> list[str]`
- `pipelex/tools/typing/module_inspector.py:161` — `find_decorated_function_names_in_file` — `def find_decorated_function_names_in_file(file_path: Path, *, decorator_names: list[str]) -> list[str]`
- `pipelex/tools/typing/module_inspector.py:226` — `import_module_from_file_if_has_decorated_functions` — `def import_module_from_file_if_has_decorated_functions(file_path: Path, *, decorator_names: list[str]) -> Any | None`
- `pipelex/tools/typing/module_inspector.py:259` — `import_module_from_file_if_has_classes` — `def import_module_from_file_if_has_classes(file_path: Path, *, base_class_names: list[str] | None=None) -> Any | None`
- `pipelex/tools/typing/module_inspector.py:294` — `find_classes_in_module` — `def find_classes_in_module(module: Any, *, base_class: type[Any] | None, include_imported: bool) -> list[type[Any]]`
- `pipelex/tools/typing/pydantic_utils.py:31` — `empty_dict_factory_of` — `def empty_dict_factory_of(_key: type[K], *, _val: type[V] | None=None) -> Callable[[], dict[K, Any]]`
- `pipelex/tools/typing/pydantic_utils.py:317` — `serialize_model` — `def serialize_model(obj: Any, *, field_visibility: FieldVisibility=FieldVisibility.NO_HIDDEN_FIELDS, is_stringify_enums: bool=True) -> dict[str, Any] | list[Any] | Any`
- `pipelex/tools/typing/structure_printer.py:69` — `StructurePrinter.get_type_structure` — `def get_type_structure(self, tp: type[Any], *, seen_types: set[str] | None=None, collected_types: dict[str, type[Any]] | None=None, collected_enums: dict[str, type[Enum]] | None=None, base_class: type[Any]=BaseModel) -> list[str]`
- `pipelex/tools/typing/validation_utils.py:4` — `has_exactly_one_among_attributes_from_list` — `def has_exactly_one_among_attributes_from_list(obj: Any, *, attributes_list: list[str]) -> bool`
- `pipelex/tools/typing/validation_utils.py:23` — `has_more_than_one_among_attributes_from_list` — `def has_more_than_one_among_attributes_from_list(obj: Any, *, attributes_list: list[str]) -> bool`
- `pipelex/tools/typing/validation_utils.py:42` — `has_more_than_one_among_attributes_from_lists` — `def has_more_than_one_among_attributes_from_lists(obj: Any, *, attributes_lists: list[list[str]]) -> list[str] | None`
- `pipelex/tools/uri/uri_resolver.py:160` — `make_base64_url_from_any_uri` — `async def make_base64_url_from_any_uri(uri: str, *, storage_provider: StorageProviderAbstract | None=None) -> str`

### `tracing` (5)

- `pipelex/tracing/activity_event_log.py:80` — `ActivityEventLogCache.log_once_runner_fallback_engaged` — `def log_once_runner_fallback_engaged(cls, workflow_id: str, *, writer_id: str) -> None`
- `pipelex/tracing/dynamodb_event_log.py:99` — `DynamoDBEventLog._make_sk` — `def _make_sk(workflow_id: str, *, writer_id: str, sequence: int) -> str`
- `pipelex/tracing/event_log_factory.py:10` — `make_event_log` — `def make_event_log(tracing_config: TracingConfig, *, writer_id: str='primary') -> EventLogProtocol`
- `pipelex/tracing/graphspec_assembler.py:116` — `GraphSpecAssembler.assemble` — `def assemble(events: Sequence[TraceEvent], *, graph_id: str, pipeline_ref: PipelineRef | None=None) -> GraphSpec`
- `pipelex/tracing/ndjson_event_log.py:73` — `NdjsonEventLog._file_name_for` — `def _file_name_for(workflow_id: str, *, writer_id: str) -> str`

## B. `LONE_SUBJECT` — single positional param (low signal)

_A single positional parameter and nothing else after it (`def f(subject)`, optionally `**kwargs`). No "choice" of subject was possible — only one arg exists. Lowest signal; included for completeness. A bare bool/int/str subject here is the only thing arguably worth a second look (`do_thing(True)` reads opaquely)._

Count: 1003

### `base_exceptions.py` (8)

- `pipelex/base_exceptions.py:12` — `iter_cause_chain` — `def iter_cause_chain(exc: BaseException) -> Iterator[BaseException]`
- `pipelex/base_exceptions.py:66` — `_redact_provider_metadata_for_strict` — `def _redact_provider_metadata_for_strict(metadata_payload: dict[str, Any]) -> dict[str, Any] | None`
- `pipelex/base_exceptions.py:178` — `error_domain_to_http_status` — `def error_domain_to_http_status(error_domain: ErrorDomain | str | None) -> int`
- `pipelex/base_exceptions.py:209` — `error_domain_is_input` — `def error_domain_is_input(error_domain: ErrorDomain | str | None) -> bool`
- `pipelex/base_exceptions.py:268` — `ErrorReport.to_dict` — `def to_dict(self, disclosure_mode: DisclosureMode=DisclosureMode.VERBOSE) -> dict[str, Any]`
- `pipelex/base_exceptions.py:360` — `ErrorReport.from_dict` — `def from_dict(cls, data: dict[str, Any]) -> 'ErrorReport'`
- `pipelex/base_exceptions.py:397` — `_humanize_class_name` — `def _humanize_class_name(class_name: str) -> str`
- `pipelex/base_exceptions.py:510` — `PipelexError._enrich_error_report_from_cause` — `def _enrich_error_report_from_cause(self, report: ErrorReport) -> ErrorReport`

### `builder` (16)

- `pipelex/builder/concept/concept_spec.py:339` — `ConceptSpec._format_type_display` — `def _format_type_display(self, field_spec: ConceptStructureSpec) -> str`
- `pipelex/builder/operations/concept_ops.py:14` — `parse_concept_spec` — `def parse_concept_spec(spec_data: Any) -> ConceptSpec`
- `pipelex/builder/operations/concept_ops.py:95` — `structure_field_to_dict` — `def structure_field_to_dict(field_spec: ConceptStructureSpec) -> dict[str, Any]`
- `pipelex/builder/operations/concept_ops.py:127` — `concept_spec_to_toml` — `def concept_spec_to_toml(concept_spec: ConceptSpec) -> str`
- `pipelex/builder/operations/models_ops.py:240` — `format_models_markdown` — `def format_models_markdown(result: dict[str, Any]) -> str`
- `pipelex/builder/operations/pipe_ops.py:39` — `_normalize_sub_pipe_dict` — `def _normalize_sub_pipe_dict(data: dict[str, Any]) -> None`
- `pipelex/builder/operations/pipe_ops.py:69` — `_normalize_pipe_code_aliases` — `def _normalize_pipe_code_aliases(data: dict[str, Any]) -> None`
- `pipelex/builder/operations/pipe_ops.py:79` — `_normalize_prompt_aliases` — `def _normalize_prompt_aliases(data: dict[str, Any]) -> None`
- `pipelex/builder/operations/pipe_ops.py:303` — `pipe_spec_to_toml` — `def pipe_spec_to_toml(pipe_spec: PipeSpec) -> str`
- `pipelex/builder/operations/validate_ops.py:22` — `validate_all` — `async def validate_all(library_dirs: list[Path] | None=None) -> dict[str, Any]`
- `pipelex/builder/operations/validate_ops.py:82` — `validate_bundle_content` — `async def validate_bundle_content(mthds_contents: list[str]) -> dict[str, Any]`
- `pipelex/builder/pipe/pipe_spec.py:132` — `PipeSpec.validate_pipe_code_syntax` — `def validate_pipe_code_syntax(cls, pipe_code: str) -> str`
- `pipelex/builder/runner_code.py:48` — `_is_multiple` — `def _is_multiple(multiplicity: VariableMultiplicity | None) -> bool`
- `pipelex/builder/runner_code.py:86` — `_get_structure_class_import` — `def _get_structure_class_import(class_name: str) -> str | None`
- `pipelex/builder/runner_code.py:104` — `_collect_concept_info` — `def _collect_concept_info(concept: Concept) -> CustomClassInfo | None`
- `pipelex/builder/runner_code.py:125` — `_collect_imports_for_inputs` — `def _collect_imports_for_inputs(inputs: InputStuffSpecs) -> tuple[set[str], dict[str, CustomClassInfo]]`

### `cli` (98)

- `pipelex/cli/_cli.py:98` — `version_callback` — `def version_callback(value: bool) -> None`
- `pipelex/cli/agent_cli/_agent_cli.py:73` — `version_callback` — `def version_callback(value: bool) -> None`
- `pipelex/cli/agent_cli/commands/agent_output.py:41` — `record_setup_warning` — `def record_setup_warning(warning_payload: dict[str, Any]) -> None`
- `pipelex/cli/agent_cli/commands/agent_output.py:76` — `set_agent_cli_error_format` — `def set_agent_cli_error_format(error_format: CliOutputFormat) -> None`
- `pipelex/cli/agent_cli/commands/agent_output.py:187` — `_build_error_source` — `def _build_error_source(exc: BaseException) -> list[str]`
- `pipelex/cli/agent_cli/commands/agent_output.py:290` — `_render_error_markdown` — `def _render_error_markdown(payload: dict[str, Any]) -> str`
- `pipelex/cli/agent_cli/commands/agent_output.py:361` — `agent_success` — `def agent_success(result: dict[str, Any]) -> None`
- `pipelex/cli/agent_cli/commands/agent_output.py:410` — `extract_validation_errors` — `def extract_validation_errors(exc: ValidateBundleError) -> list[dict[str, Any]]`
- `pipelex/cli/agent_cli/commands/check_model_cmd.py:21` — `_format_check_markdown` — `def _format_check_markdown(result: dict[str, Any]) -> str`
- `pipelex/cli/agent_cli/commands/concept_cmd.py:19` — `_concept_spec_to_toml` — `def _concept_spec_to_toml(concept_spec: ConceptSpec) -> str`
- `pipelex/cli/agent_cli/commands/doctor_cmd.py:27` — `_status_icon` — `def _status_icon(healthy: bool) -> str`
- `pipelex/cli/agent_cli/commands/doctor_cmd.py:32` — `_format_doctor_markdown` — `def _format_doctor_markdown(result: dict[str, Any]) -> str`
- `pipelex/cli/agent_cli/commands/init_cmd.py:34` — `_parse_config_arg` — `def _parse_config_arg(config_arg: str | None) -> dict[str, Any]`
- `pipelex/cli/agent_cli/commands/init_cmd.py:67` — `_format_init_markdown` — `def _format_init_markdown(result: dict[str, Any]) -> str`
- `pipelex/cli/agent_cli/commands/init_cmd.py:88` — `_resolve_target_dir` — `def _resolve_target_dir(global_: bool) -> Path`
- `pipelex/cli/agent_cli/commands/init_cmd.py:110` — `_copy_inference_templates` — `def _copy_inference_templates(target_dir: Path) -> None`
- `pipelex/cli/agent_cli/commands/pipe_cmd.py:36` — `_pipe_spec_to_toml` — `def _pipe_spec_to_toml(pipe_spec: PipeSpec) -> str`
- `pipelex/cli/agent_cli/commands/run/_output_helpers.py:52` — `_render_json_payload_lines` — `def _render_json_payload_lines(result_payload: Any) -> list[str]`
- `pipelex/cli/agent_cli/commands/run/stdin_resolver.py:19` — `_extract_concept_code` — `def _extract_concept_code(concept_data: Any) -> str`
- `pipelex/cli/agent_cli/commands/run/stdin_resolver.py:37` — `_extract_stuff_entry` — `def _extract_stuff_entry(stuff_data: dict[str, Any]) -> dict[str, Any] | None`
- `pipelex/cli/agent_cli/commands/run/stdin_resolver.py:57` — `resolve_stdin_inputs` — `def resolve_stdin_inputs(stdin_data: dict[str, Any]) -> dict[str, Any]`
- `pipelex/cli/agent_cli/commands/run/stdin_resolver.py:155` — `_parse_inputs_arg` — `def _parse_inputs_arg(inputs_arg: str) -> dict[str, Any] | None`
- `pipelex/cli/agent_cli/commands/validate/_output_helpers.py:8` — `format_validate_markdown` — `def format_validate_markdown(result: dict[str, Any]) -> str`
- `pipelex/cli/commands/build/structures_cmd.py:34` — `_compute_relative_path_from_output_dir` — `def _compute_relative_path_from_output_dir(output_directory: Path) -> Path | None`
- `pipelex/cli/commands/doctor_cmd.py:109` — `check_config_files` — `def check_config_files(config_dir: Path | None=None) -> tuple[bool, int, str]`
- `pipelex/cli/commands/doctor_cmd.py:162` — `check_telemetry_config` — `def check_telemetry_config(config_dir: Path | None=None) -> tuple[bool, str]`
- `pipelex/cli/commands/doctor_cmd.py:191` — `check_backend_credentials` — `def check_backend_credentials(config_dir: Path | None=None) -> tuple[bool, dict[str, BackendCredentialsReport], str]`
- `pipelex/cli/commands/doctor_cmd.py:268` — `check_kit_template_exists` — `def check_kit_template_exists(backend_name: str) -> bool`
- `pipelex/cli/commands/doctor_cmd.py:333` — `check_backend_files` — `def check_backend_files(config_dir: Path | None=None) -> tuple[bool, dict[str, BackendFileReport], str]`
- `pipelex/cli/commands/doctor_cmd.py:706` — `check_deck_sync` — `def check_deck_sync(config_dir: Path | None=None) -> tuple[bool, DeckSyncReport, str]`
- `pipelex/cli/commands/doctor_cmd.py:796` — `check_models` — `def check_models(config_dir: Path | None=None) -> tuple[bool, str, dict[str, BackendFileReport]]`
- `pipelex/cli/commands/doctor_cmd.py:894` — `doctor_cmd` — `def doctor_cmd(fix: bool=False) -> None`
- `pipelex/cli/commands/doctor_cmd.py:918` — `do_doctor_cmd` — `def do_doctor_cmd(fix: bool=False) -> None`
- `pipelex/cli/commands/init/backends.py:49` — `get_selected_backend_keys` — `def get_selected_backend_keys(backends_toml_path: Path) -> list[str]`
- `pipelex/cli/commands/init/backends.py:76` — `disable_gateway_backend` — `def disable_gateway_backend(backends_toml_path: Path) -> None`
- `pipelex/cli/commands/init/command.py:61` — `attempt_prime_remote_config_cache` — `def attempt_prime_remote_config_cache(target_config_dir: Path | None=None) -> CachePrimingResult`
- `pipelex/cli/commands/init/command.py:427` — `_init_agreement` — `def _init_agreement(console: Console) -> None`
- `pipelex/cli/commands/init/credentials.py:23` — `read_env_file` — `def read_env_file(env_path: Path) -> dict[str, str]`
- `pipelex/cli/commands/init/credentials.py:72` — `get_required_vars_for_enabled_backends` — `def get_required_vars_for_enabled_backends(backends_toml_path: Path) -> dict[str, list[str]]`
- `pipelex/cli/commands/init/ide_extension.py:26` — `_is_extension_installed` — `def _is_extension_installed(cmd: str) -> bool`
- `pipelex/cli/commands/init/ide_extension.py:89` — `suggest_extension_install_if_needed` — `def suggest_extension_install_if_needed(console: Console) -> None`
- `pipelex/cli/commands/init/ui/gateway_ui.py:94` — `prompt_gateway_acceptance` — `def prompt_gateway_acceptance(console: Console) -> bool`
- `pipelex/cli/commands/init/ui/gateway_ui.py:114` — `display_gateway_declined_message` — `def display_gateway_declined_message(console: Console) -> None`
- `pipelex/cli/commands/init/ui/gateway_ui.py:136` — `display_gateway_accepted_message` — `def display_gateway_accepted_message(console: Console) -> None`
- `pipelex/cli/commands/login/command.py:115` — `save_api_key` — `def save_api_key(api_key: str) -> None`
- `pipelex/cli/commands/run/_inputs_path_resolver.py:19` — `is_relative_local_path` — `def is_relative_local_path(uri: str) -> bool`
- `pipelex/cli/commands/show_cmd.py:65` — `do_show_pipe` — `def do_show_pipe(pipe_code: str) -> None`
- `pipelex/cli/commands/show_cmd.py:72` — `do_show_backends` — `def do_show_backends(show_all: bool=False) -> None`
- `pipelex/cli/commands/update_cmd.py:91` — `_resolve_deck_dir` — `def _resolve_deck_dir(local: bool) -> Path`
- `pipelex/cli/commands/update_cmd.py:124` — `_action_description` — `def _action_description(status: DeckFileStatus) -> str`
- `pipelex/cli/commands/validate/_validate_core.py:47` — `_format_signatures_summary_suffix` — `def _format_signatures_summary_suffix(signature_count: int) -> str`
- `pipelex/cli/dev_cli/commands/check_keyword_only_cmd.py:29` — `_print_report` — `def _print_report(violations: list[Violation]) -> None`
- `pipelex/cli/dev_cli/commands/check_keyword_only_cmd.py:136` — `_print_violation_lines` — `def _print_violation_lines(violations: list[Violation]) -> None`
- `pipelex/cli/dev_cli/commands/gateway_models_generator.py:30` — `normalize_for_comparison` — `def normalize_for_comparison(content: str) -> str`
- `pipelex/cli/dev_cli/commands/gateway_models_generator.py:54` — `extract_reference_data` — `def extract_reference_data(model_specs: BackendModelSpecs) -> dict[str, list[dict[str, Any]]]`
- `pipelex/cli/dev_cli/commands/gateway_models_generator.py:107` — `generate_pure_markdown_list` — `def generate_pure_markdown_list(models: list[dict[str, Any]]) -> str`
- `pipelex/cli/dev_cli/commands/gateway_models_generator.py:145` — `generate_markdown_table` — `def generate_markdown_table(models: list[dict[str, Any]]) -> str`
- `pipelex/cli/dev_cli/commands/gateway_models_generator.py:222` — `generate_reference_markdown` — `def generate_reference_markdown(model_specs: BackendModelSpecs) -> str`
- `pipelex/cli/dev_cli/commands/gateway_models_generator.py:274` — `generate_reference_pure_markdown` — `def generate_reference_pure_markdown(model_specs: BackendModelSpecs) -> str`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:124` — `_attribute_tail` — `def _attribute_tail(node: ast.expr) -> tuple[str, ...]`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:137` — `_decorator_matches_carveout` — `def _decorator_matches_carveout(decorator: ast.expr) -> bool`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:165` — `_has_carveout_decorator` — `def _has_carveout_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:170` — `_iter_subscript_metadata` — `def _iter_subscript_metadata(annotation: ast.expr) -> Iterator[ast.expr]`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:179` — `_callee_name` — `def _callee_name(func: ast.expr) -> str | None`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:188` — `_annotation_has_typer_metadata` — `def _annotation_has_typer_metadata(annotation: ast.expr | None) -> bool`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:203` — `_has_typer_param_annotation` — `def _has_typer_param_annotation(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:227` — `_is_dunder` — `def _is_dunder(name: str) -> bool`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:298` — `_Collector._visit_function` — `def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:349` — `_module_qname_for` — `def _module_qname_for(path: Path) -> str`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:357` — `iter_source_files` — `def iter_source_files(root: Path) -> Iterator[Path]`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:365` — `collect_all_violations` — `def collect_all_violations(root: Path) -> list[Violation]`
- `pipelex/cli/dev_cli/commands/keyword_only_guard.py:443` — `main` — `def main(argv: list[str]) -> int`
- `pipelex/cli/dev_cli/commands/preprocess_test_models_cmd.py:42` — `_extract_models_from_backend_toml` — `def _extract_models_from_backend_toml(backend_path: Path) -> dict[str, list[str]]`
- `pipelex/cli/dev_cli/commands/preprocess_test_models_cmd.py:222` — `_load_test_profile` — `def _load_test_profile(profile_name: str) -> dict[str, Any]`
- `pipelex/cli/dev_cli/commands/refresh_graph_ui_sri_cmd.py:93` — `_validate_sri` — `def _validate_sri(value: str) -> str`
- `pipelex/cli/dev_cli/commands/refresh_graph_ui_sri_cmd.py:116` — `_sha384_sri` — `def _sha384_sri(payload: bytes) -> str`
- `pipelex/cli/dev_cli/commands/refresh_graph_ui_sri_cmd.py:122` — `_python_string_literal` — `def _python_string_literal(value: str) -> str`
- `pipelex/cli/dev_cli/commands/sync_main_config_cmd.py:30` — `_format_value` — `def _format_value(value: object) -> str`
- `pipelex/cli/dev_cli/commands/update_gateway_models_cmd.py:65` — `update_gateway_models_cmd` — `def update_gateway_models_cmd(quiet: bool=False) -> None`
- `pipelex/cli/error_handlers.py:57` — `set_traceback_requested` — `def set_traceback_requested(value: bool) -> None`
- `pipelex/cli/error_handlers.py:80` — `print_traceback_if_requested` — `def print_traceback_if_requested(console: Console) -> None`
- `pipelex/cli/error_handlers.py:370` — `handle_inference_setup_required_error` — `def handle_inference_setup_required_error(exc: InferenceSetupRequiredError) -> NoReturn`
- `pipelex/cli/error_handlers.py:396` — `handle_telemetry_config_validation_error` — `def handle_telemetry_config_validation_error(exc: TelemetryConfigValidationError) -> NoReturn`
- `pipelex/cli/error_handlers.py:426` — `handle_gateway_terms_not_accepted_error` — `def handle_gateway_terms_not_accepted_error(exc: GatewayTermsNotAcceptedError) -> NoReturn`
- `pipelex/cli/error_handlers.py:453` — `handle_gateway_api_key_missing_error` — `def handle_gateway_api_key_missing_error(exc: GatewayApiKeyMissingError) -> NoReturn`
- `pipelex/cli/error_handlers.py:483` — `handle_gateway_do_not_track_conflict_error` — `def handle_gateway_do_not_track_conflict_error(exc: GatewayDoNotTrackConflictError) -> NoReturn`
- `pipelex/cli/error_handlers.py:512` — `handle_remote_config_validation_error` — `def handle_remote_config_validation_error(exc: RemoteConfigValidationError) -> NoReturn`
- `pipelex/cli/error_handlers.py:549` — `handle_remote_config_unavailable_error` — `def handle_remote_config_unavailable_error(exc: RemoteConfigUnavailableError) -> NoReturn`
- `pipelex/cli/error_handlers.py:582` — `handle_gateway_unknown_model_error` — `def handle_gateway_unknown_model_error(exc: GatewayUnknownModelError) -> NoReturn`
- `pipelex/cli/installed_methods.py:142` — `discover_methods_from_library_dirs` — `def discover_methods_from_library_dirs(library_dirs: list[str]) -> list[InstalledMethod]`
- `pipelex/cli/method_resolver.py:22` — `_get_all_exported_pipes` — `def _get_all_exported_pipes(method: InstalledMethod) -> set[str]`
- `pipelex/cli/method_resolver.py:30` — `_find_method_by_exported_pipe` — `def _find_method_by_exported_pipe(pipe_code: str) -> InstalledMethod`
- `pipelex/cli/method_resolver.py:63` — `is_github_url` — `def is_github_url(target: str) -> bool`
- `pipelex/cli/method_resolver.py:68` — `parse_github_url` — `def parse_github_url(url: str) -> tuple[str, str | None]`
- `pipelex/cli/method_resolver.py:127` — `is_local_path` — `def is_local_path(target: str) -> bool`
- `pipelex/cli/method_resolver.py:134` — `resolve_method_from_path` — `def resolve_method_from_path(method_path: str) -> InstalledMethod`
- `pipelex/cli/method_resolver.py:168` — `resolve_method_from_url` — `def resolve_method_from_url(url: str) -> InstalledMethod`
- `pipelex/cli/method_resolver.py:294` — `resolve_pipe_from_exports` — `def resolve_pipe_from_exports(pipe_code: str) -> list[str] | None`

### `cogt` (172)

- `pipelex/cogt/config_cogt.py:89` — `LLMConfig.get_template` — `def get_template(self, template_name: str) -> str`
- `pipelex/cogt/content_generation/assignment_models.py:43` — `LLMAssignment.clone_with_new_prompt` — `def clone_with_new_prompt(self, new_prompt: LLMPrompt) -> 'LLMAssignment'`
- `pipelex/cogt/content_generation/content_generator_protocol.py:26` — `update_job_metadata` — `def update_job_metadata(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]`
- `pipelex/cogt/content_generation/content_generator_protocol.py:142` — `ContentGeneratorProtocol.make_search_sourced_answer` — `def make_search_sourced_answer(self, search_assignment: SearchAssignment) -> Coroutine[Any, Any, SearchResultContent]`
- `pipelex/cogt/content_generation/dry_mock.py:167` — `build_mock_object` — `def build_mock_object(model_class: type[BaseModelTypeVar], **field_values: Any) -> BaseModelTypeVar`
- `pipelex/cogt/content_generation/dry_mock.py:200` — `_reconstruct_object_class` — `def _reconstruct_object_class(object_assignment: ObjectAssignment) -> type[BaseModel]`
- `pipelex/cogt/content_generation/dry_mock.py:214` — `stamp_mock_main_coordination` — `def stamp_mock_main_coordination(items: Sequence[Any]) -> None`
- `pipelex/cogt/content_generation/dry_mock.py:229` — `_nb_list_items` — `def _nb_list_items(object_assignment: ObjectAssignment) -> int`
- `pipelex/cogt/content_generation/dry_mock.py:278` — `_dry_report_func` — `def _dry_report_func(cogt_run_params: CogtRunParams) -> _ReportLLMJobFunc`
- `pipelex/cogt/content_generation/dry_mock.py:293` — `dry_llm_gen_text` — `def dry_llm_gen_text(llm_assignment: LLMAssignment) -> str`
- `pipelex/cogt/content_generation/dry_mock.py:303` — `dry_llm_gen_object` — `def dry_llm_gen_object(object_assignment: ObjectAssignment) -> BaseModel`
- `pipelex/cogt/content_generation/dry_mock.py:309` — `dry_llm_gen_object_list` — `def dry_llm_gen_object_list(object_assignment: ObjectAssignment) -> list[BaseModel]`
- `pipelex/cogt/content_generation/dry_mock.py:323` — `dry_templating_gen_text` — `def dry_templating_gen_text(templating_assignment: TemplatingAssignment) -> str`
- `pipelex/cogt/content_generation/dry_mock.py:356` — `dry_img_gen_image_contents` — `def dry_img_gen_image_contents(img_gen_assignment: ImgGenAssignment) -> list[ImageContent]`
- `pipelex/cogt/content_generation/dry_mock.py:370` — `dry_extract_page_contents` — `def dry_extract_page_contents(extract_assignment: ExtractAssignment) -> list[PageContent]`
- `pipelex/cogt/content_generation/dry_mock.py:394` — `dry_render_page_views` — `def dry_render_page_views(render_assignment: RenderPageViewsAssignment) -> list[ImageContent]`
- `pipelex/cogt/content_generation/dry_mock.py:406` — `dry_search_gen_sourced_answer` — `def dry_search_gen_sourced_answer(search_assignment: SearchAssignment) -> SearchResultContent`
- `pipelex/cogt/content_generation/dry_mock.py:414` — `dry_search_gen_structured` — `def dry_search_gen_structured(search_object_assignment: SearchObjectAssignment) -> dict[str, Any]`
- `pipelex/cogt/content_generation/dry_run_factory.py:64` — `DryRunFactory.generate_dict_snake_key_pascal_value` — `def generate_dict_snake_key_pascal_value(cls, num_items: int=2) -> dict[str, str]`
- `pipelex/cogt/content_generation/dry_run_factory.py:97` — `DryRunFactory._get_examples_from_field` — `def _get_examples_from_field(cls, field_info: FieldInfo) -> list[Any] | None`
- `pipelex/cogt/content_generation/dry_run_factory.py:107` — `DryRunFactory._get_mock_format_from_field` — `def _get_mock_format_from_field(cls, field_info: FieldInfo) -> MockFormat | None`
- `pipelex/cogt/content_generation/dry_run_factory.py:133` — `DryRunFactory._detect_examples_constraints` — `def _detect_examples_constraints(cls, object_class: type[BaseModelTypeVar]) -> dict[str, list[Any]]`
- `pipelex/cogt/content_generation/dry_run_factory.py:143` — `DryRunFactory._get_literal_values_from_annotation` — `def _get_literal_values_from_annotation(cls, annotation: Any) -> tuple[Any, ...] | None`
- `pipelex/cogt/content_generation/dry_run_factory.py:168` — `DryRunFactory._detect_literal_fields` — `def _detect_literal_fields(cls, object_class: type[BaseModel]) -> dict[str, tuple[Any, ...]]`
- `pipelex/cogt/content_generation/dry_run_factory.py:188` — `DryRunFactory._make_example_picker` — `def _make_example_picker(examples: list[Any]) -> Callable[[], Any]`
- `pipelex/cogt/content_generation/dry_run_factory.py:238` — `DryRunFactory._extract_types_from_annotation` — `def _extract_types_from_annotation(cls, annotation: Any) -> list[Any]`
- `pipelex/cogt/content_generation/dry_run_factory.py:258` — `DryRunFactory._create_nested_factory` — `def _create_nested_factory(cls, nested_class: type[BaseModel]) -> type[ModelFactory[Any]]`
- `pipelex/cogt/content_generation/dry_run_factory.py:318` — `DryRunFactory._detect_format_constraints` — `def _detect_format_constraints(cls, object_class: type[BaseModelTypeVar]) -> dict[MockFormat, set[str]]`
- `pipelex/cogt/content_generation/exceptions.py:35` — `DryRunObjectFidelityError.for_object_class` — `def for_object_class(cls, object_class_name: str) -> 'DryRunObjectFidelityError'`
- `pipelex/cogt/content_generation/exceptions.py:63` — `DryRunMockBuildError.for_object_class` — `def for_object_class(cls, object_class_name: str) -> 'DryRunMockBuildError'`
- `pipelex/cogt/content_generation/extract_generate.py:10` — `extract_gen_pages` — `async def extract_gen_pages(extract_assignment: ExtractAssignment) -> ExtractOutput`
- `pipelex/cogt/content_generation/generated_content_factory.py:65` — `GeneratedContentFactory._fetch_remote_content` — `async def _fetch_remote_content(self, url: str) -> bytes`
- `pipelex/cogt/content_generation/img_gen_generate.py:11` — `img_gen_single_image` — `async def img_gen_single_image(img_gen_assignment: ImgGenAssignment) -> GeneratedImageRawDetails`
- `pipelex/cogt/content_generation/img_gen_generate.py:24` — `img_gen_image_list` — `async def img_gen_image_list(img_gen_assignment: ImgGenAssignment) -> list[GeneratedImageRawDetails]`
- `pipelex/cogt/content_generation/llm_generate.py:17` — `llm_gen_text` — `async def llm_gen_text(llm_assignment: LLMAssignment) -> str`
- `pipelex/cogt/content_generation/llm_generate.py:31` — `llm_gen_object` — `async def llm_gen_object(object_assignment: ObjectAssignment) -> BaseModel`
- `pipelex/cogt/content_generation/llm_generate.py:52` — `llm_gen_object_list` — `async def llm_gen_object_list(object_assignment: ObjectAssignment) -> list[BaseModel]`
- `pipelex/cogt/content_generation/schema_to_model_factory.py:115` — `SchemaToModelFactory._normalize_class_name` — `def _normalize_class_name(cls, title: str) -> str`
- `pipelex/cogt/content_generation/schema_to_model_factory.py:146` — `SchemaToModelFactory._reject_unsafe_schema_extensions` — `def _reject_unsafe_schema_extensions(cls, schema: dict[str, Any]) -> None`
- `pipelex/cogt/content_generation/schema_to_model_factory.py:161` — `SchemaToModelFactory._generate_source_from_schema` — `def _generate_source_from_schema(cls, schema: dict[str, Any]) -> str`
- `pipelex/cogt/content_generation/schema_to_model_factory.py:241` — `SchemaToModelFactory._exec_source_to_types` — `def _exec_source_to_types(cls, source_code: str) -> dict[str, type[Any]]`
- `pipelex/cogt/content_generation/schema_to_model_factory.py:289` — `SchemaToModelFactory.make_types_from_source` — `def make_types_from_source(cls, source_code: str) -> dict[str, type[Any]]`
- `pipelex/cogt/content_generation/search_generate.py:25` — `_make_search_worker` — `def _make_search_worker(search_assignment: SearchAssignment) -> SearchWorkerAbstract`
- `pipelex/cogt/content_generation/search_generate.py:34` — `_make_search_job` — `def _make_search_job(search_assignment: SearchAssignment) -> SearchJob`
- `pipelex/cogt/content_generation/search_generate.py:46` — `search_gen_sourced_answer` — `async def search_gen_sourced_answer(search_assignment: SearchAssignment) -> SearchResultContent`
- `pipelex/cogt/content_generation/search_generate.py:54` — `search_gen_structured` — `async def search_gen_structured(search_object_assignment: SearchObjectAssignment) -> dict[str, Any]`
- `pipelex/cogt/content_generation/templating_generate.py:6` — `templating_gen_text` — `async def templating_gen_text(templating_assignment: TemplatingAssignment) -> str`
- `pipelex/cogt/document/prompt_document.py:71` — `PromptDocumentUri.get_content_hash` — `def get_content_hash(self, length: int | None=None) -> str`
- `pipelex/cogt/document/prompt_document.py:112` — `PromptDocumentBase64.get_content_hash` — `def get_content_hash(self, length: int | None=None) -> str`
- `pipelex/cogt/document/prompt_document.py:145` — `PromptDocumentBinary.get_content_hash` — `def get_content_hash(self, length: int | None=None) -> str`
- `pipelex/cogt/document/prompt_document_utils.py:114` — `prepare_prompt_document_as_base64` — `async def prepare_prompt_document_as_base64(prompt_document: PromptDocument) -> PreparedFileBase64`
- `pipelex/cogt/exceptions.py:112` — `find_inference_error_category_in_chain` — `def find_inference_error_category_in_chain(exc: BaseException) -> InferenceErrorCategory | None`
- `pipelex/cogt/extract/extract_job.py:22` — `ExtractJob.extract_job_before_start` — `def extract_job_before_start(self, inference_model: InferenceModelSpec)`
- `pipelex/cogt/extract/extract_report.py:25` — `ExtractTokenCostReportField.report_field_for_nb_tokens_by_category` — `def report_field_for_nb_tokens_by_category(token_category: TokenCategory) -> str`
- `pipelex/cogt/extract/extract_report.py:29` — `ExtractTokenCostReportField.report_field_for_cost_by_category` — `def report_field_for_cost_by_category(token_category: CostCategory) -> str`
- `pipelex/cogt/extract/extract_worker_abstract.py:53` — `ExtractWorkerAbstract._check_can_perform_job` — `def _check_can_perform_job(self, extract_job: ExtractJob)`
- `pipelex/cogt/extract/extract_worker_abstract.py:69` — `ExtractWorkerAbstract.extract_pages` — `async def extract_pages(self, extract_job: ExtractJob) -> ExtractOutput`
- `pipelex/cogt/extract/extract_worker_abstract.py:111` — `ExtractWorkerAbstract._extract_pages` — `async def _extract_pages(self, extract_job: ExtractJob) -> ExtractOutput`
- `pipelex/cogt/image/prompt_image_utils.py:115` — `prepare_prompt_image_as_base64` — `async def prepare_prompt_image_as_base64(prompt_image: PromptImage) -> PreparedFileBase64`
- `pipelex/cogt/img_gen/img_gen_args_factory.py:231` — `ImgGenArgsFactory.make_args_from_specific` — `def make_args_from_specific(cls, specific_taxonomy: SpecificTaxonomy) -> dict[str, Any]`
- `pipelex/cogt/img_gen/img_gen_args_factory.py:509` — `ImgGenArgsFactory.make_args_from_output_compression` — `def make_args_from_output_compression(cls, output_compression_taxonomy: OutputCompressionTaxonomy) -> dict[str, Any]`
- `pipelex/cogt/img_gen/img_gen_job.py:22` — `ImgGenJob.img_gen_job_before_start` — `def img_gen_job_before_start(self, inference_model: InferenceModelSpec)`
- `pipelex/cogt/img_gen/img_gen_report.py:25` — `ImgGenTokenCostReportField.report_field_for_nb_tokens_by_category` — `def report_field_for_nb_tokens_by_category(token_category: TokenCategory) -> str`
- `pipelex/cogt/img_gen/img_gen_report.py:29` — `ImgGenTokenCostReportField.report_field_for_cost_by_category` — `def report_field_for_cost_by_category(token_category: CostCategory) -> str`
- `pipelex/cogt/img_gen/img_gen_worker_abstract.py:38` — `ImgGenWorkerAbstract._check_can_perform_job` — `def _check_can_perform_job(self, img_gen_job: ImgGenJob)`
- `pipelex/cogt/img_gen/img_gen_worker_abstract.py:42` — `ImgGenWorkerAbstract.gen_image` — `async def gen_image(self, img_gen_job: ImgGenJob) -> GeneratedImageRawDetails`
- `pipelex/cogt/img_gen/img_gen_worker_abstract.py:75` — `ImgGenWorkerAbstract._gen_image` — `async def _gen_image(self, img_gen_job: ImgGenJob) -> GeneratedImageRawDetails`
- `pipelex/cogt/inference/error_classification.py:231` — `_is_quota_exhaustion_openai` — `def _is_quota_exhaustion_openai(error_message: str) -> bool`
- `pipelex/cogt/inference/error_classification.py:237` — `_is_quota_exhaustion_anthropic` — `def _is_quota_exhaustion_anthropic(error_message: str) -> bool`
- `pipelex/cogt/inference/error_classification.py:243` — `_is_quota_exhaustion_google` — `def _is_quota_exhaustion_google(error_message: str) -> bool`
- `pipelex/cogt/inference/error_classification.py:288` — `_is_content_policy_violation` — `def _is_content_policy_violation(error_message: str) -> bool`
- `pipelex/cogt/inference/error_classification.py:294` — `_stringify_for_scan` — `def _stringify_for_scan(body: Any) -> str`
- `pipelex/cogt/inference/error_classification.py:308` — `extract_underlying_sdk_exception` — `def extract_underlying_sdk_exception(instructor_exc: Any) -> BaseException | None`
- `pipelex/cogt/inference/error_classification.py:345` — `_parse_retry_after_seconds` — `def _parse_retry_after_seconds(value: Any) -> float | None`
- `pipelex/cogt/inference/error_classification.py:370` — `_provider_error_code_from_body` — `def _provider_error_code_from_body(body: Any) -> str | None`
- `pipelex/cogt/inference/error_classification.py:383` — `extract_openai_metadata` — `def extract_openai_metadata(exc: BaseException) -> ProviderErrorMetadata`
- `pipelex/cogt/inference/error_classification.py:430` — `extract_anthropic_metadata` — `def extract_anthropic_metadata(exc: BaseException) -> ProviderErrorMetadata`
- `pipelex/cogt/inference/error_classification.py:465` — `_provider_error_code_from_flat_body` — `def _provider_error_code_from_flat_body(body: Any) -> str | None`
- `pipelex/cogt/inference/error_classification.py:481` — `_parse_response_text_body` — `def _parse_response_text_body(response: Any) -> tuple[Any | None, str | None]`
- `pipelex/cogt/inference/error_classification.py:510` — `_google_provider_error_code_from_details` — `def _google_provider_error_code_from_details(details: Any) -> str | None`
- `pipelex/cogt/inference/error_classification.py:533` — `extract_google_metadata` — `def extract_google_metadata(exc: BaseException) -> ProviderErrorMetadata`
- `pipelex/cogt/inference/error_classification.py:570` — `extract_azure_metadata` — `def extract_azure_metadata(exc: BaseException) -> ProviderErrorMetadata`
- `pipelex/cogt/inference/error_classification.py:623` — `extract_fal_metadata` — `def extract_fal_metadata(exc: BaseException) -> ProviderErrorMetadata`
- `pipelex/cogt/inference/error_classification.py:662` — `extract_huggingface_metadata` — `def extract_huggingface_metadata(exc: BaseException) -> ProviderErrorMetadata`
- `pipelex/cogt/inference/error_classification.py:695` — `extract_gateway_metadata` — `def extract_gateway_metadata(exc: BaseException) -> ProviderErrorMetadata`
- `pipelex/cogt/inference/error_classification.py:729` — `extract_mistral_metadata` — `def extract_mistral_metadata(exc: BaseException) -> ProviderErrorMetadata`
- `pipelex/cogt/inference/error_classification.py:796` — `extract_bedrock_metadata` — `def extract_bedrock_metadata(exc: BaseException) -> ProviderErrorMetadata`
- `pipelex/cogt/inference/error_classification.py:843` — `extract_linkup_metadata` — `def extract_linkup_metadata(exc: BaseException) -> ProviderErrorMetadata`
- `pipelex/cogt/inference/error_classify.py:73` — `_classify_statusless` — `def _classify_statusless(metadata: SDKErrorEnvelope) -> ClassificationResult`
- `pipelex/cogt/inference/error_classify.py:97` — `classify_inference_error` — `def classify_inference_error(metadata: SDKErrorEnvelope) -> ClassificationResult`
- `pipelex/cogt/inference/inference_constants.py:11` — `InferenceOutputType.is_text` — `def is_text(cls, output_desc: str) -> bool`
- `pipelex/cogt/inference/inference_manager.py:53` — `InferenceManager._setup_one_internal_llm_worker` — `def _setup_one_internal_llm_worker(self, llm_handle: str) -> LLMWorkerInternalAbstract`
- `pipelex/cogt/inference/inference_manager.py:88` — `InferenceManager._setup_one_img_gen_worker` — `def _setup_one_img_gen_worker(self, img_gen_handle: str) -> ImgGenWorkerAbstract`
- `pipelex/cogt/inference/inference_manager.py:109` — `InferenceManager._setup_one_extract_worker` — `def _setup_one_extract_worker(self, extract_handle: str) -> ExtractWorkerAbstract`
- `pipelex/cogt/inference/inference_manager_protocol.py:19` — `InferenceManagerProtocol.get_llm_worker` — `def get_llm_worker(self, llm_handle: str) -> LLMWorkerAbstract`
- `pipelex/cogt/inference/inference_manager_protocol.py:33` — `InferenceManagerProtocol.get_img_gen_worker` — `def get_img_gen_worker(self, img_gen_handle: str) -> ImgGenWorkerAbstract`
- `pipelex/cogt/inference/inference_manager_protocol.py:39` — `InferenceManagerProtocol.get_extract_worker` — `def get_extract_worker(self, extract_handle: str) -> ExtractWorkerAbstract`
- `pipelex/cogt/inference/transport_retry.py:49` — `_parse_retry_after` — `def _parse_retry_after(raw_value: str | None) -> float | None`
- `pipelex/cogt/inference/transport_retry.py:69` — `_transport_retry_wait` — `def _transport_retry_wait(retry_state: RetryCallState) -> float`
- `pipelex/cogt/inference/transport_retry.py:81` — `_make_retry_predicate` — `def _make_retry_predicate(retry_on_ambiguous_failure: bool) -> Callable[[BaseException], bool]`
- `pipelex/cogt/inference/transport_retry.py:91` — `_make_retry_predicate.should_retry` — `def should_retry(exc: BaseException) -> bool`
- `pipelex/cogt/llm/instructor_retry.py:7` — `make_instructor_schema_retrying` — `def make_instructor_schema_retrying(max_attempts: int) -> AsyncRetrying`
- `pipelex/cogt/llm/llm_job.py:28` — `LLMJob.llm_job_before_start` — `def llm_job_before_start(self, inference_model: InferenceModelSpec)`
- `pipelex/cogt/llm/llm_prompt.py:54` — `LLMPrompt.desc` — `def desc(self, truncate_text_length: int | None=None) -> str`
- `pipelex/cogt/llm/llm_prompt_template_inputs.py:50` — `LLMPromptTemplateInputs.complemented_by` — `def complemented_by(self, additional_template_inputs: LLMPromptTemplateInputs | None) -> LLMPromptTemplateInputs`
- `pipelex/cogt/llm/llm_prompt_template_inputs.py:56` — `LLMPromptTemplateInputs.complemented_by_dict` — `def complemented_by_dict(self, additional_inputs_dict: LLMPromptTemplateInputsDict | None) -> LLMPromptTemplateInputs`
- `pipelex/cogt/llm/llm_report.py:25` — `LLMTokenCostReportField.report_field_for_nb_tokens_by_category` — `def report_field_for_nb_tokens_by_category(token_category: TokenCategory) -> str`
- `pipelex/cogt/llm/llm_report.py:29` — `LLMTokenCostReportField.report_field_for_cost_by_category` — `def report_field_for_cost_by_category(token_category: CostCategory) -> str`
- `pipelex/cogt/llm/llm_utils.py:7` — `dump_prompt` — `def dump_prompt(llm_prompt: LLMPrompt) -> None`
- `pipelex/cogt/llm/llm_utils.py:22` — `dump_response_from_text_gen` — `def dump_response_from_text_gen(response: Any) -> None`
- `pipelex/cogt/llm/llm_utils.py:30` — `dump_response_from_structured_gen` — `def dump_response_from_structured_gen(response: Any) -> None`
- `pipelex/cogt/llm/llm_utils.py:34` — `dump_error` — `def dump_error(error: Exception) -> None`
- `pipelex/cogt/llm/llm_worker_abstract.py:317` — `LLMWorkerAbstract._before_job` — `async def _before_job(self, llm_job: LLMJob)`
- `pipelex/cogt/llm/llm_worker_abstract.py:357` — `LLMWorkerAbstract._check_can_perform_job` — `def _check_can_perform_job(self, llm_job: LLMJob)`
- `pipelex/cogt/llm/llm_worker_abstract.py:361` — `LLMWorkerAbstract.gen_text` — `async def gen_text(self, llm_job: LLMJob) -> str`
- `pipelex/cogt/llm/llm_worker_abstract.py:392` — `LLMWorkerAbstract._gen_text` — `async def _gen_text(self, llm_job: LLMJob) -> str`
- `pipelex/cogt/llm/llm_worker_internal_abstract.py:88` — `LLMWorkerInternalAbstract._apply_constraints` — `def _apply_constraints(self, llm_job: LLMJob) -> LLMJobParams | None`
- `pipelex/cogt/llm/llm_worker_internal_abstract.py:152` — `LLMWorkerInternalAbstract._validate_no_reasoning_for_structured_gen` — `def _validate_no_reasoning_for_structured_gen(self, job_params: LLMJobParams)`
- `pipelex/cogt/llm/llm_worker_internal_abstract.py:157` — `LLMWorkerInternalAbstract._check_vision_support` — `def _check_vision_support(self, llm_job: LLMJob)`
- `pipelex/cogt/llm/llm_worker_internal_abstract.py:169` — `LLMWorkerInternalAbstract._check_document_support` — `def _check_document_support(self, llm_job: LLMJob)`
- `pipelex/cogt/model_backends/backend.py:27` — `PipelexBackend.is_gateway_backend` — `def is_gateway_backend(cls, backend_name: str) -> bool`
- `pipelex/cogt/model_backends/backend.py:54` — `InferenceBackend.get_model_spec` — `def get_model_spec(self, model_name: str) -> InferenceModelSpec | None`
- `pipelex/cogt/model_backends/backend.py:58` — `InferenceBackend.get_extra_config` — `def get_extra_config(self, key: str) -> Any | None`
- `pipelex/cogt/model_backends/backend_library.py:392` — `InferenceBackendLibrary.get_inference_backend` — `def get_inference_backend(self, backend_name: str) -> InferenceBackend | None`
- `pipelex/cogt/models/deck_manifest.py:77` — `DeckSyncReport.files_with_status` — `def files_with_status(self, status: DeckFileStatus) -> list[str]`
- `pipelex/cogt/models/deck_manifest.py:81` — `compute_sha256` — `def compute_sha256(data: bytes) -> str`
- `pipelex/cogt/models/deck_manifest.py:85` — `compute_file_sha256` — `def compute_file_sha256(path: Path) -> str`
- `pipelex/cogt/models/deck_manifest.py:98` — `_is_managed_deck_filename` — `def _is_managed_deck_filename(filename: str) -> bool`
- `pipelex/cogt/models/deck_manifest.py:119` — `list_managed_installed_files` — `def list_managed_installed_files(deck_dir: Path) -> dict[str, str]`
- `pipelex/cogt/models/deck_manifest.py:133` — `manifest_path` — `def manifest_path(deck_dir: Path) -> Path`
- `pipelex/cogt/models/deck_manifest.py:137` — `read_manifest` — `def read_manifest(deck_dir: Path) -> DeckManifest | None`
- `pipelex/cogt/models/deck_manifest.py:163` — `is_deck_stale_fast` — `def is_deck_stale_fast(deck_dir: Path) -> bool`
- `pipelex/cogt/models/deck_manifest.py:193` — `_try_parse_version` — `def _try_parse_version(version: str) -> tuple[int, ...] | None`
- `pipelex/cogt/models/deck_manifest.py:206` — `status_rich_label` — `def status_rich_label(status: DeckFileStatus) -> str`
- `pipelex/cogt/models/deck_manifest.py:221` — `suggest_x_custom_filename` — `def suggest_x_custom_filename(numbered_filename: str) -> str`
- `pipelex/cogt/models/deck_manifest.py:233` — `compute_deck_sync_report` — `def compute_deck_sync_report(deck_dir: Path) -> DeckSyncReport`
- `pipelex/cogt/models/model_deck.py:123` — `ModelDeck.get_aliases_and_waterfalls_for_type` — `def get_aliases_and_waterfalls_for_type(self, model_type: ModelType) -> tuple[dict[str, str], dict[str, list[str]]]`
- `pipelex/cogt/models/model_deck.py:163` — `ModelDeck._warn_if_ambiguous_llm` — `def _warn_if_ambiguous_llm(self, name: str) -> None`
- `pipelex/cogt/models/model_deck.py:177` — `ModelDeck._warn_if_ambiguous_extract` — `def _warn_if_ambiguous_extract(self, name: str) -> None`
- `pipelex/cogt/models/model_deck.py:191` — `ModelDeck._warn_if_ambiguous_img_gen` — `def _warn_if_ambiguous_img_gen(self, name: str) -> None`
- `pipelex/cogt/models/model_deck.py:205` — `ModelDeck._warn_if_ambiguous_search` — `def _warn_if_ambiguous_search(self, name: str) -> None`
- `pipelex/cogt/models/model_deck.py:309` — `ModelDeck.get_llm_setting` — `def get_llm_setting(self, llm_choice: LLMModelChoice) -> LLMSetting`
- `pipelex/cogt/models/model_deck.py:362` — `ModelDeck.get_extract_setting` — `def get_extract_setting(self, extract_choice: ExtractModelChoice) -> ExtractSetting`
- `pipelex/cogt/models/model_deck.py:411` — `ModelDeck.get_search_setting` — `def get_search_setting(self, search_choice: SearchModelChoice) -> SearchSetting`
- `pipelex/cogt/models/model_deck.py:460` — `ModelDeck.get_img_gen_setting` — `def get_img_gen_setting(self, img_gen_choice: ImgGenModelChoice) -> ImgGenSetting`
- `pipelex/cogt/models/model_deck.py:510` — `ModelDeck.final_validate` — `def final_validate(cls, deck: Self)`
- `pipelex/cogt/models/model_deck_check.py:41` — `check_llm_choice_with_deck` — `def check_llm_choice_with_deck(llm_choice: LLMModelChoice) -> None`
- `pipelex/cogt/models/model_deck_check.py:103` — `check_extract_choice_with_deck` — `def check_extract_choice_with_deck(extract_choice: ExtractModelChoice) -> None`
- `pipelex/cogt/models/model_deck_check.py:165` — `check_search_choice_with_deck` — `def check_search_choice_with_deck(search_choice: SearchModelChoice) -> None`
- `pipelex/cogt/models/model_deck_check.py:227` — `check_img_gen_choice_with_deck` — `def check_img_gen_choice_with_deck(img_gen_choice: ImgGenModelChoice) -> None`
- `pipelex/cogt/models/model_deck_loader.py:12` — `load_model_deck_blueprint` — `def load_model_deck_blueprint(model_deck_paths: list[str]) -> ModelDeckBlueprint`
- `pipelex/cogt/models/model_manager.py:44` — `ModelManager.get_model_deck_paths` — `def get_model_deck_paths(cls, deck_dir_path: str) -> list[str]`
- `pipelex/cogt/models/model_manager.py:143` — `ModelManager._collect_deck_referenced_handles` — `def _collect_deck_referenced_handles(cls, deck: ModelDeck) -> list[tuple[str, ModelType]]`
- `pipelex/cogt/models/model_manager.py:178` — `ModelManager._extract_choice_handle` — `def _extract_choice_handle(cls, choice: LLMSetting | ExtractSetting | ImgGenSetting | SearchSetting | ModelReference | str | None) -> str | None`
- `pipelex/cogt/models/model_manager_abstract.py:41` — `ModelManagerAbstract.get_required_inference_backend` — `def get_required_inference_backend(self, backend_name: str) -> InferenceBackend`
- `pipelex/cogt/models/model_reference.py:63` — `ModelReference.parse` — `def parse(cls, value: str) -> 'ModelReference'`
- `pipelex/cogt/models/model_reference.py:165` — `ensure_model_reference` — `def ensure_model_reference(value: str | ModelReference) -> ModelReference`
- `pipelex/cogt/models/model_reference.py:175` — `parse_model_reference` — `def parse_model_reference(value: Any) -> ModelReference | Any`
- `pipelex/cogt/search/search_job.py:33` — `SearchJob.search_job_before_start` — `def search_job_before_start(self, inference_model: InferenceModelSpec)`
- `pipelex/cogt/search/search_report.py:25` — `SearchTokenCostReportField.report_field_for_nb_tokens_by_category` — `def report_field_for_nb_tokens_by_category(token_category: TokenCategory) -> str`
- `pipelex/cogt/search/search_report.py:29` — `SearchTokenCostReportField.report_field_for_cost_by_category` — `def report_field_for_cost_by_category(token_category: CostCategory) -> str`
- `pipelex/cogt/search/search_worker_abstract.py:31` — `SearchWorkerAbstract.search_sourced_answer` — `async def search_sourced_answer(self, search_job: SearchJob) -> SearchResultContent`
- `pipelex/cogt/search/search_worker_abstract.py:78` — `SearchWorkerAbstract._search_sourced_answer` — `async def _search_sourced_answer(self, search_job: SearchJob) -> SearchResultContent`
- `pipelex/cogt/search/search_worker_factory.py:9` — `SearchWorkerFactory.make_search_worker` — `def make_search_worker(cls, inference_model: InferenceModelSpec) -> SearchWorkerAbstract`
- `pipelex/cogt/templating/template_preprocessor.py:73` — `_replace_at_sigil` — `def _replace_at_sigil(match: Match[str]) -> str`
- `pipelex/cogt/templating/template_preprocessor.py:86` — `_replace_dollar_sigil` — `def _replace_dollar_sigil(match: Match[str]) -> str`
- `pipelex/cogt/templating/template_preprocessor.py:139` — `_normalize_and_escape` — `def _normalize_and_escape(template: str) -> str`
- `pipelex/cogt/templating/template_preprocessor.py:158` — `rewrite_template_sigils` — `def rewrite_template_sigils(template: str) -> str`
- `pipelex/cogt/usage/cost_registry.py:218` — `CostRegistry.aggregate_costs` — `def aggregate_costs(cls, tokens_usages: Sequence[TokensUsage]) -> AggregatedCosts`
- `pipelex/cogt/usage/cost_registry.py:283` — `CostRegistry.build_cost_summary` — `def build_cost_summary(cls, tokens_usages: Sequence[TokensUsage]) -> dict[str, Any] | None`
- `pipelex/cogt/usage/cost_registry.py:314` — `CostRegistry.compute_cost_report` — `def compute_cost_report(cls, tokens_usage: TokensUsage) -> TokenCostReport`
- `pipelex/cogt/usage/cost_registry.py:360` — `CostRegistry.complete_cost_report` — `def complete_cost_report(cls, tokens_usage: TokensUsage) -> TokenCostReport`

### `core` (118)

- `pipelex/core/bundles/pipe_sorter.py:7` — `sort_pipes_by_dependencies` — `def sort_pipes_by_dependencies(pipes: dict[str, PipeBlueprintUnion]) -> list[tuple[str, PipeBlueprintUnion]]`
- `pipelex/core/bundles/pipe_sorter.py:48` — `sort_pipes_by_dependencies.visit` — `def visit(pipe_code: str) -> None`
- `pipelex/core/bundles/pipelex_bundle_blueprint.py:143` — `PipelexBundleBlueprint.get_elaboration_for` — `def get_elaboration_for(self, pipe_code: str) -> ElaborationMetadata | None`
- `pipelex/core/concepts/concept.py:86` — `Concept.sentence_from_concept` — `def sentence_from_concept(cls, concept: 'Concept') -> str`
- `pipelex/core/concepts/concept.py:90` — `Concept.is_native_concept` — `def is_native_concept(cls, concept: 'Concept') -> bool`
- `pipelex/core/concepts/concept.py:167` — `Concept.is_valid_structure_class` — `def is_valid_structure_class(cls, structure_class_name: str) -> bool`
- `pipelex/core/concepts/concept.py:227` — `Concept._render_schema_representation` — `def _render_schema_representation(self, is_multiple: bool=False) -> tuple[dict[str, Any], set[str]]`
- `pipelex/core/concepts/concept_factory.py:98` — `ConceptFactory.make_native_concept` — `def make_native_concept(cls, native_concept_code: NativeConceptCode) -> Concept`
- `pipelex/core/concepts/concept_representation_generator.py:183` — `ConceptRepresentationGenerator._unwrap_optional` — `def _unwrap_optional(self, field_type: Any) -> Any`
- `pipelex/core/concepts/concept_representation_generator.py:227` — `ConceptRepresentationGenerator._generate_dict_value` — `def _generate_dict_value(self, field_name: str) -> dict[str, str]`
- `pipelex/core/concepts/concept_representation_generator.py:266` — `ConceptRepresentationGenerator._generate_basemodel_representation` — `def _generate_basemodel_representation(self, model_class: type[BaseModel]) -> dict[str, Any] | str`
- `pipelex/core/concepts/concept_representation_generator.py:347` — `ConceptRepresentationGenerator._format_python_value` — `def _format_python_value(self, value: Any) -> str`
- `pipelex/core/concepts/helpers.py:52` — `strip_multiplicity_from_concept_ref_or_code` — `def strip_multiplicity_from_concept_ref_or_code(concept_ref_or_code: str) -> str`
- `pipelex/core/concepts/helpers.py:66` — `normalize_structure_blueprint` — `def normalize_structure_blueprint(structure_dict: dict[str, str | ConceptStructureBlueprint]) -> dict[str, ConceptStructureBlueprint]`
- `pipelex/core/concepts/helpers.py:111` — `extract_concept_code_from_concept_ref_or_code` — `def extract_concept_code_from_concept_ref_or_code(concept_ref_or_code: str) -> str`
- `pipelex/core/concepts/native/concept_native.py:77` — `NativeConceptCode.is_native_structure_class` — `def is_native_structure_class(cls, class_name: str) -> bool`
- `pipelex/core/concepts/native/concept_native.py:89` — `NativeConceptCode.get_native_structure_class` — `def get_native_structure_class(cls, class_name: str) -> type | None`
- `pipelex/core/concepts/native/concept_native.py:107` — `NativeConceptCode.is_text_concept` — `def is_text_concept(cls, concept_code: str) -> bool`
- `pipelex/core/concepts/native/concept_native.py:132` — `NativeConceptCode.is_dynamic_concept` — `def is_dynamic_concept(cls, concept_code: str) -> bool`
- `pipelex/core/concepts/native/concept_native.py:165` — `NativeConceptCode.is_native_concept_ref_or_code` — `def is_native_concept_ref_or_code(cls, concept_ref_or_code: str) -> bool`
- `pipelex/core/concepts/native/concept_native.py:176` — `NativeConceptCode.is_valid_native_concept_ref` — `def is_valid_native_concept_ref(cls, concept_ref: str) -> bool`
- `pipelex/core/concepts/native/concept_native.py:195` — `NativeConceptCode.validate_native_concept_ref_or_code` — `def validate_native_concept_ref_or_code(cls, concept_ref_or_code: str) -> None`
- `pipelex/core/concepts/native/concept_native.py:201` — `NativeConceptCode.get_validated_native_concept_ref` — `def get_validated_native_concept_ref(cls, concept_ref_or_code: str) -> str`
- `pipelex/core/concepts/structure_generation/exceptions.py:16` — `SyntaxErrorData.from_syntax_error` — `def from_syntax_error(cls, syntax_error: SyntaxError) -> 'SyntaxErrorData'`
- `pipelex/core/concepts/structure_generation/generator.py:173` — `StructureGenerator._escape_string_for_python` — `def _escape_string_for_python(self, value: str) -> str`
- `pipelex/core/concepts/structure_generation/generator.py:205` — `StructureGenerator._format_default_value` — `def _format_default_value(self, value: Any) -> str`
- `pipelex/core/concepts/structure_generation/generator.py:227` — `StructureGenerator._format_field_description` — `def _format_field_description(self, description: str) -> str`
- `pipelex/core/concepts/structure_generation/generator.py:351` — `StructureGenerator._get_python_type_from_blueprint` — `def _get_python_type_from_blueprint(self, field_blueprint: ConceptStructureBlueprint) -> str`
- `pipelex/core/concepts/structure_generation/generator.py:424` — `StructureGenerator._resolve_concept_ref_to_type` — `def _resolve_concept_ref_to_type(self, concept_ref: str | None) -> str`
- `pipelex/core/concepts/validation.py:6` — `is_concept_code_valid` — `def is_concept_code_valid(concept_code: str) -> bool`
- `pipelex/core/concepts/validation.py:10` — `validate_concept_code` — `def validate_concept_code(concept_code: str) -> None`
- `pipelex/core/concepts/validation.py:16` — `is_concept_ref_valid` — `def is_concept_ref_valid(concept_ref: str) -> bool`
- `pipelex/core/concepts/validation.py:32` — `validate_concept_ref` — `def validate_concept_ref(concept_ref: str) -> None`
- `pipelex/core/concepts/validation.py:42` — `is_concept_ref_or_code_valid` — `def is_concept_ref_or_code_valid(concept_ref_or_code: str) -> bool`
- `pipelex/core/concepts/validation.py:59` — `validate_concept_ref_or_code` — `def validate_concept_ref_or_code(concept_ref_or_code: str) -> None`
- `pipelex/core/domains/domain.py:12` — `SpecialDomain.is_native` — `def is_native(cls, domain_code: str) -> bool`
- `pipelex/core/domains/domain_factory.py:11` — `DomainFactory.make_from_blueprint` — `def make_from_blueprint(cls, blueprint: DomainBlueprint) -> Domain`
- `pipelex/core/domains/validation.py:8` — `is_domain_code_valid` — `def is_domain_code_valid(code: Any) -> bool`
- `pipelex/core/domains/validation.py:26` — `validate_domain_code` — `def validate_domain_code(code: str) -> None`
- `pipelex/core/interpreter/bundle_elaborator.py:26` — `_is_preliminary_text_pipe` — `def _is_preliminary_text_pipe(pipe_blueprint: PipeBlueprintUnion) -> TypeGuard[PipeLLMBlueprint]`
- `pipelex/core/interpreter/bundle_elaborator.py:48` — `BundleElaborator.elaborate` — `def elaborate(cls, bundle: PipelexBundleBlueprint) -> PipelexBundleBlueprint`
- `pipelex/core/interpreter/helpers.py:8` — `is_pipelex_file` — `def is_pipelex_file(file_path: Path) -> bool`
- `pipelex/core/interpreter/helpers.py:28` — `ValidationErrorScope.is_pipe_scope` — `def is_pipe_scope(cls, scope: str) -> bool`
- `pipelex/core/interpreter/helpers.py:46` — `get_error_scope` — `def get_error_scope(loc: tuple[int | str, ...]) -> ValidationErrorScope`
- `pipelex/core/interpreter/validation_error_categorizer.py:17` — `_extract_variable_names_from_message` — `def _extract_variable_names_from_message(message: str) -> list[str] | None`
- `pipelex/core/interpreter/validation_error_categorizer.py:113` — `_is_pydantic_internal_loc_element` — `def _is_pydantic_internal_loc_element(element: str) -> bool`
- `pipelex/core/memory/working_memory.py:67` — `WorkingMemory.get_optional_stuff` — `def get_optional_stuff(self, name: str) -> Stuff | None`
- `pipelex/core/memory/working_memory.py:80` — `WorkingMemory.get_stuff` — `def get_stuff(self, name: str) -> Stuff`
- `pipelex/core/memory/working_memory.py:96` — `WorkingMemory.get_stuffs` — `def get_stuffs(self, names: set[str]) -> list[Stuff]`
- `pipelex/core/memory/working_memory.py:102` — `WorkingMemory.get_existing_stuffs` — `def get_existing_stuffs(self, names: set[str]) -> list[Stuff]`
- `pipelex/core/memory/working_memory.py:109` — `WorkingMemory.is_stuff_code_used` — `def is_stuff_code_used(self, stuff_code: str) -> bool`
- `pipelex/core/memory/working_memory.py:112` — `WorkingMemory.remove_stuff` — `def remove_stuff(self, name: str)`
- `pipelex/core/memory/working_memory.py:122` — `WorkingMemory.is_stuff_exists` — `def is_stuff_exists(self, name: str) -> bool`
- `pipelex/core/memory/working_memory.py:174` — `WorkingMemory.remove_alias` — `def remove_alias(self, alias: str) -> None`
- `pipelex/core/memory/working_memory.py:183` — `WorkingMemory.get_aliases_for` — `def get_aliases_for(self, target: str) -> list[str]`
- `pipelex/core/memory/working_memory.py:384` — `WorkingMemory.get_stuff_as_text` — `def get_stuff_as_text(self, name: str) -> TextContent`
- `pipelex/core/memory/working_memory.py:388` — `WorkingMemory.get_stuff_as_str` — `def get_stuff_as_str(self, name: str) -> str`
- `pipelex/core/memory/working_memory.py:392` — `WorkingMemory.get_stuff_as_image` — `def get_stuff_as_image(self, name: str) -> ImageContent`
- `pipelex/core/memory/working_memory.py:396` — `WorkingMemory.get_stuff_as_text_and_image` — `def get_stuff_as_text_and_image(self, name: str) -> TextAndImagesContent`
- `pipelex/core/memory/working_memory.py:400` — `WorkingMemory.get_stuff_as_document` — `def get_stuff_as_document(self, name: str) -> DocumentContent`
- `pipelex/core/memory/working_memory.py:404` — `WorkingMemory.get_stuff_as_number` — `def get_stuff_as_number(self, name: str) -> NumberContent`
- `pipelex/core/memory/working_memory.py:408` — `WorkingMemory.get_stuff_as_html` — `def get_stuff_as_html(self, name: str) -> HtmlContent`
- `pipelex/core/memory/working_memory.py:412` — `WorkingMemory.get_stuff_as_mermaid` — `def get_stuff_as_mermaid(self, name: str) -> MermaidContent`
- `pipelex/core/memory/working_memory.py:420` — `WorkingMemory.main_stuff_as` — `def main_stuff_as(self, content_type: type[StuffContentType]) -> StuffContentType`
- `pipelex/core/memory/working_memory.py:424` — `WorkingMemory.main_stuff_as_list` — `def main_stuff_as_list(self, item_type: type[StuffContentType]) -> ListContent[StuffContentType]`
- `pipelex/core/memory/working_memory.py:430` — `WorkingMemory.main_list_stuff_first_item_as` — `def main_list_stuff_first_item_as(self, item_type: type[StuffContentType]) -> StuffContentType`
- `pipelex/core/memory/working_memory_factory.py:31` — `WorkingMemoryFactory.make_from_single_stuff` — `def make_from_single_stuff(cls, stuff: Stuff) -> WorkingMemory`
- `pipelex/core/memory/working_memory_factory.py:96` — `WorkingMemoryFactory.convert_to_working_memory_format` — `def convert_to_working_memory_format(cls, needed_inputs_spec: InputStuffSpecs) -> list[TypedNamedStuffSpec]`
- `pipelex/core/memory/working_memory_factory.py:174` — `WorkingMemoryFactory.make_mock_content` — `def make_mock_content(cls, typed_named_stuff_spec: TypedNamedStuffSpec) -> StuffContent`
- `pipelex/core/memory/working_memory_factory.py:196` — `WorkingMemoryFactory._get_mockable_class` — `def _get_mockable_class(cls, structure_class: type[StuffContent]) -> type[StuffContent]`
- `pipelex/core/memory/working_memory_factory.py:216` — `WorkingMemoryFactory.make_mock_stuff` — `def make_mock_stuff(cls, typed_named_stuff_spec: TypedNamedStuffSpec) -> Stuff`
- `pipelex/core/memory/working_memory_factory.py:251` — `WorkingMemoryFactory.make_mock_inputs` — `def make_mock_inputs(cls, needed_inputs: list[TypedNamedStuffSpec]) -> 'WorkingMemory'`
- `pipelex/core/pipes/handle_pipe_errors.py:18` — `_extract_wrapped_pipe_validation_error` — `def _extract_wrapped_pipe_validation_error(error: ErrorDetails) -> PipeValidationError | None`
- `pipelex/core/pipes/handle_pipe_errors.py:46` — `categorize_pipe_validation_error` — `def categorize_pipe_validation_error(validation_error: ValidationError) -> list[PipesAndConceptValidationErrorData]`
- `pipelex/core/pipes/handle_pipe_errors.py:173` — `categorize_pipe_validation_with_libraries_error` — `def categorize_pipe_validation_with_libraries_error(pipe_error: PipeValidationError) -> PipesAndConceptValidationErrorData`
- `pipelex/core/pipes/handle_pipe_errors.py:202` — `categorize_pipe_factory_error` — `def categorize_pipe_factory_error(factory_error: PipeFactoryError) -> PipeFactoryErrorData`
- `pipelex/core/pipes/inputs/input_stuff_specs.py:67` — `InputStuffSpecs.set_default_domain` — `def set_default_domain(self, domain_code: str)`
- `pipelex/core/pipes/inputs/input_stuff_specs.py:74` — `InputStuffSpecs.get_required_stuff_spec` — `def get_required_stuff_spec(self, variable_name: str) -> StuffSpec`
- `pipelex/core/pipes/inputs/input_stuff_specs.py:81` — `InputStuffSpecs.is_variable_existing` — `def is_variable_existing(self, variable_name: str) -> bool`
- `pipelex/core/pipes/inputs/input_stuff_specs.py:136` — `InputStuffSpecs.format_for_display` — `def format_for_display(self, indent: int=6) -> str`
- `pipelex/core/pipes/inputs/input_stuff_specs.py:153` — `InputStuffSpecs.render_inputs` — `def render_inputs(self, indent: int=2) -> str`
- `pipelex/core/pipes/output/output_renderer.py:191` — `_render_python_output` — `def _render_python_output(the_pipe: PipeAbstract) -> str`
- `pipelex/core/pipes/pipe_abstract.py:121` — `PipeAbstract._make_single_concept_data_for_registry` — `def _make_single_concept_data_for_registry(self, concept: Concept) -> dict[str, Any]`
- `pipelex/core/pipes/pipe_abstract.py:415` — `PipeAbstract.needed_inputs` — `def needed_inputs(self, visited_pipes: set[str] | None=None) -> InputStuffSpecs`
- `pipelex/core/pipes/pipe_abstract.py:427` — `PipeAbstract._format_pipe_run_info` — `def _format_pipe_run_info(self, pipe_run_params: PipeRunParams) -> str`
- `pipelex/core/pipes/pipe_blueprint.py:36` — `PipeCategory.is_controller_by_str` — `def is_controller_by_str(cls, category_str: str) -> bool`
- `pipelex/core/pipes/pipe_output.py:35` — `PipeOutput.prepare_for_temporal` — `def prepare_for_temporal(self, library_crate: LibraryCrate | None=None) -> 'PipeOutput'`
- `pipelex/core/pipes/pipe_output.py:66` — `PipeOutput.main_stuff_as_list` — `def main_stuff_as_list(self, item_type: type[StuffContentType]) -> ListContent[StuffContentType]`
- `pipelex/core/pipes/pipe_output.py:72` — `PipeOutput.main_stuff_as_items` — `def main_stuff_as_items(self, item_type: type[StuffContentType]) -> list[StuffContentType]`
- `pipelex/core/pipes/pipe_output.py:78` — `PipeOutput.main_stuff_as` — `def main_stuff_as(self, content_type: type[StuffContentType]) -> StuffContentType`
- `pipelex/core/pipes/stuff_spec/stuff_spec.py:28` — `StuffSpec.render_stuff_spec` — `def render_stuff_spec(self, output_format: ConceptRepresentationFormat) -> dict[str, Any]`
- `pipelex/core/pipes/validation.py:56` — `is_valid_input_name` — `def is_valid_input_name(input_name: str) -> bool`
- `pipelex/core/pipes/validation.py:106` — `validate_input_name` — `def validate_input_name(input_name: str) -> None`
- `pipelex/core/pipes/validation.py:126` — `is_pipe_code_valid` — `def is_pipe_code_valid(pipe_code: str) -> bool`
- `pipelex/core/pipes/variable_multiplicity.py:58` — `parse_concept_with_multiplicity` — `def parse_concept_with_multiplicity(concept_ref_or_code: str) -> MultiplicityParseResult`
- `pipelex/core/qualified_ref.py:41` — `QualifiedRef.parse` — `def parse(cls, raw: str) -> 'QualifiedRef'`
- `pipelex/core/qualified_ref.py:71` — `QualifiedRef.parse_stripping_cross_package` — `def parse_stripping_cross_package(cls, raw: str) -> 'QualifiedRef'`
- `pipelex/core/qualified_ref.py:82` — `QualifiedRef.parse_concept_ref` — `def parse_concept_ref(cls, raw: str) -> 'QualifiedRef'`
- `pipelex/core/qualified_ref.py:109` — `QualifiedRef.parse_pipe_ref` — `def parse_pipe_ref(cls, raw: str) -> 'QualifiedRef'`
- `pipelex/core/qualified_ref.py:148` — `QualifiedRef.is_local_to` — `def is_local_to(self, domain: str) -> bool`
- `pipelex/core/qualified_ref.py:161` — `QualifiedRef.is_external_to` — `def is_external_to(self, domain: str) -> bool`
- `pipelex/core/qualified_ref.py:175` — `QualifiedRef.is_address_based_alias` — `def is_address_based_alias(alias: str) -> bool`
- `pipelex/core/qualified_ref.py:190` — `QualifiedRef.has_cross_package_prefix` — `def has_cross_package_prefix(raw: str) -> bool`
- `pipelex/core/qualified_ref.py:204` — `QualifiedRef.split_cross_package_ref` — `def split_cross_package_ref(raw: str) -> CrossPackageRef`
- `pipelex/core/stuffs/image_field_search.py:130` — `check_generic_container_for_images` — `def check_generic_container_for_images(container_type: Any) -> bool`
- `pipelex/core/stuffs/list_content.py:21` — `ListContent.get_items` — `def get_items(self, item_type: type[StuffContent]) -> list[StuffContent]`
- `pipelex/core/stuffs/structured_content.py:44` — `StructuredContent._render_value_html` — `def _render_value_html(self, value: Any) -> str`
- `pipelex/core/stuffs/stuff.py:38` — `Stuff.make_stuff_name` — `def make_stuff_name(cls, concept: Concept) -> str`
- `pipelex/core/stuffs/stuff.py:95` — `Stuff.content_as` — `def content_as(self, content_type: type[StuffContentType]) -> StuffContentType`
- `pipelex/core/stuffs/stuff.py:170` — `Stuff.as_list_of_fixed_content_type` — `def as_list_of_fixed_content_type(self, item_type: type[StuffContentType]) -> ListContent[StuffContentType]`
- `pipelex/core/stuffs/stuff.py:250` — `Stuff.pretty_print_stuff` — `def pretty_print_stuff(self, title: str | None=None) -> None`
- `pipelex/core/stuffs/stuff_artefact.py:334` — `StuffArtefact.rendered_for_template_async` — `async def rendered_for_template_async(self, text_format: TextFormat) -> str`
- `pipelex/core/stuffs/stuff_content.py:79` — `StuffContent.rendered_for_prompt` — `def rendered_for_prompt(self, text_format: TextFormat=TextFormat.PLAIN) -> str`
- `pipelex/core/stuffs/stuff_content.py:95` — `StuffContent.rendered_for_template_async` — `async def rendered_for_template_async(self, text_format: TextFormat=TextFormat.PLAIN) -> str`
- `pipelex/core/stuffs/stuff_content.py:135` — `StuffContent.pretty_print_content` — `def pretty_print_content(self, title: str | None=None) -> None`
- `pipelex/core/stuffs/stuff_factory.py:47` — `StuffFactory.make_stuff_name` — `def make_stuff_name(cls, concept: Concept) -> str`
- `pipelex/core/stuffs/stuff_factory.py:91` — `StuffFactory.make_from_blueprint` — `def make_from_blueprint(cls, blueprint: StuffBlueprint) -> 'Stuff'`
- `pipelex/core/stuffs/stuff_viewer.py:118` — `_get_html_tab_label` — `def _get_html_tab_label(content_type: str | None) -> str`

### `errors` (12)

- `pipelex/errors/error_pages_generator.py:106` — `_is_production_subclass` — `def _is_production_subclass(cls: type[PipelexError]) -> bool`
- `pipelex/errors/error_pages_generator.py:195` — `page_slug` — `def page_slug(cls: type[PipelexError]) -> str`
- `pipelex/errors/error_pages_generator.py:200` — `render_error_page` — `def render_error_page(cls: type[PipelexError]) -> str`
- `pipelex/errors/error_pages_generator.py:423` — `_subsystem_key` — `def _subsystem_key(cls: type[PipelexError]) -> str`
- `pipelex/errors/error_pages_generator.py:435` — `_humanize_subsystem` — `def _humanize_subsystem(key: str) -> str`
- `pipelex/errors/error_pages_generator.py:440` — `_group_by_subsystem` — `def _group_by_subsystem(classes: Iterable[type[PipelexError]]) -> dict[str, list[type[PipelexError]]]`
- `pipelex/errors/error_pages_generator.py:505` — `render_index_page` — `def render_index_page(by_subsystem: dict[str, list[type[PipelexError]]]) -> str`
- `pipelex/errors/error_pages_generator.py:550` — `has_authored_marker` — `def has_authored_marker(content: str) -> bool`
- `pipelex/errors/error_pages_generator.py:560` — `_resolve_class_level_domain` — `def _resolve_class_level_domain(cls: type[PipelexError]) -> str`
- `pipelex/errors/error_pages_generator.py:570` — `_resolve_class_level_user_action` — `def _resolve_class_level_user_action(cls: type[PipelexError]) -> str | None`
- `pipelex/errors/error_pages_generator.py:581` — `_parent_link` — `def _parent_link(cls: type[PipelexError]) -> str`
- `pipelex/errors/error_pages_generator.py:589` — `_short_docstring` — `def _short_docstring(cls: type[PipelexError]) -> str | None`

### `graph` (27)

- `pipelex/graph/graph_analysis.py:87` — `GraphAnalysis.from_graphspec` — `def from_graphspec(cls, graph: GraphSpec) -> 'GraphAnalysis'`
- `pipelex/graph/graph_analysis.py:169` — `GraphAnalysis.get_children` — `def get_children(self, node_id: str) -> list[str]`
- `pipelex/graph/graph_analysis.py:180` — `GraphAnalysis.is_controller` — `def is_controller(self, node_id: str) -> bool`
- `pipelex/graph/graph_analysis.py:191` — `GraphAnalysis.is_root` — `def is_root(self, node_id: str) -> bool`
- `pipelex/graph/graph_analysis.py:202` — `GraphAnalysis.get_stuff_info` — `def get_stuff_info(self, digest: str) -> StuffInfo | None`
- `pipelex/graph/graph_analysis.py:213` — `GraphAnalysis.get_producer` — `def get_producer(self, digest: str) -> str | None`
- `pipelex/graph/graph_analysis.py:224` — `GraphAnalysis.get_consumers` — `def get_consumers(self, digest: str) -> list[str]`
- `pipelex/graph/graph_rendering.py:19` — `_sanitize_graph_name` — `def _sanitize_graph_name(graph_name: str) -> str`
- `pipelex/graph/graph_tracer.py:164` — `GraphTracer._emit_event` — `def _emit_event(self, event: TraceEvent) -> None`
- `pipelex/graph/graph_tracer_manager.py:58` — `GraphTracerManager.get_instance_tracer` — `def get_instance_tracer(cls, lookup_key: str) -> GraphTracerProtocol | None`
- `pipelex/graph/graph_tracer_manager.py:79` — `GraphTracerManager._get_tracer` — `def _get_tracer(self, graph_id: str) -> GraphTracer | None`
- `pipelex/graph/graph_tracer_manager.py:174` — `GraphTracerManager.close_tracer` — `def close_tracer(self, tracer_key: str) -> GraphSpec | None`
- `pipelex/graph/graph_tracer_manager.py:188` — `GraphTracerManager.get_tracer` — `def get_tracer(self, graph_id: str) -> GraphTracer | None`
- `pipelex/graph/mermaidflow/mermaidflow_factory.py:333` — `MermaidflowFactory._get_node_label` — `def _get_node_label(cls, node: NodeSpec) -> str`
- `pipelex/graph/mermaidflow/mermaidflow_utils.py:9` — `make_stuff_id` — `def make_stuff_id(digest: str) -> str`
- `pipelex/graph/mermaidflow/stuff_collector.py:63` — `collect_stuff_data` — `def collect_stuff_data(graph: GraphSpec) -> dict[str, Any]`
- `pipelex/graph/mermaidflow/stuff_collector.py:76` — `collect_stuff_data_text` — `def collect_stuff_data_text(graph: GraphSpec) -> dict[str, str]`
- `pipelex/graph/mermaidflow/stuff_collector.py:89` — `collect_stuff_data_html` — `def collect_stuff_data_html(graph: GraphSpec) -> dict[str, str]`
- `pipelex/graph/mermaidflow/stuff_collector.py:102` — `collect_stuff_content_type` — `def collect_stuff_content_type(graph: GraphSpec) -> dict[str, str]`
- `pipelex/graph/mermaidflow/stuff_collector.py:117` — `collect_stuff_metadata` — `def collect_stuff_metadata(graph: GraphSpec) -> dict[str, dict[str, str]]`
- `pipelex/graph/mermaidflow/stuff_collector.py:127` — `collect_stuff_metadata.extract_metadata` — `def extract_metadata(io_spec: IOSpec) -> dict[str, str]`
- `pipelex/graph/reactflow/reactflow_html.py:20` — `_build_viewer_config` — `def _build_viewer_config(config: ReactFlowRenderingConfig) -> dict[str, object]`
- `pipelex/graph/validation.py:10` — `validate_graphspec` — `def validate_graphspec(graph: GraphSpec) -> None`
- `pipelex/graph/validation.py:32` — `_validate_unique_node_ids` — `def _validate_unique_node_ids(graph: GraphSpec) -> None`
- `pipelex/graph/validation.py:42` — `_validate_unique_edge_ids` — `def _validate_unique_edge_ids(graph: GraphSpec) -> None`
- `pipelex/graph/validation.py:52` — `_validate_edge_references` — `def _validate_edge_references(graph: GraphSpec) -> None`
- `pipelex/graph/validation.py:65` — `_validate_failed_nodes_have_errors` — `def _validate_failed_nodes_have_errors(graph: GraphSpec) -> None`

### `hub.py` (44)

- `pipelex/hub.py:112` — `PipelexHub.set_instance` — `def set_instance(cls, pipelex_hub: 'PipelexHub') -> None`
- `pipelex/hub.py:137` — `PipelexHub.set_config` — `def set_config(self, config: ConfigRoot)`
- `pipelex/hub.py:148` — `PipelexHub.set_console_print_target` — `def set_console_print_target(self, target: ConsoleTarget)`
- `pipelex/hub.py:158` — `PipelexHub.set_console` — `def set_console(self, console: Console)`
- `pipelex/hub.py:161` — `PipelexHub.set_secrets_provider` — `def set_secrets_provider(self, secrets_provider: SecretsProviderAbstract)`
- `pipelex/hub.py:164` — `PipelexHub.set_storage_provider` — `def set_storage_provider(self, storage_provider: StorageProviderAbstract | None)`
- `pipelex/hub.py:167` — `PipelexHub.set_class_registry` — `def set_class_registry(self, class_registry: ClassRegistryAbstract)`
- `pipelex/hub.py:170` — `PipelexHub.set_telemetry_manager` — `def set_telemetry_manager(self, telemetry_manager: TelemetryManagerAbstract)`
- `pipelex/hub.py:175` — `PipelexHub.set_models_manager` — `def set_models_manager(self, models_manager: ModelManagerAbstract)`
- `pipelex/hub.py:178` — `PipelexHub.set_plugin_manager` — `def set_plugin_manager(self, plugin_manager: PluginManager)`
- `pipelex/hub.py:181` — `PipelexHub.set_inference_manager` — `def set_inference_manager(self, inference_manager: InferenceManagerProtocol)`
- `pipelex/hub.py:184` — `PipelexHub.set_report_delegate` — `def set_report_delegate(self, reporting_delegate: ReportingProtocol)`
- `pipelex/hub.py:187` — `PipelexHub.set_content_generator` — `def set_content_generator(self, content_generator: ContentGeneratorProtocol)`
- `pipelex/hub.py:190` — `PipelexHub.set_dry_run_forced` — `def set_dry_run_forced(self, is_forced: bool) -> None`
- `pipelex/hub.py:198` — `PipelexHub.set_domain_library` — `def set_domain_library(self, domain_library: DomainLibraryAbstract)`
- `pipelex/hub.py:201` — `PipelexHub.set_concept_library` — `def set_concept_library(self, concept_library: ConceptLibraryAbstract)`
- `pipelex/hub.py:204` — `PipelexHub.set_pipe_library` — `def set_pipe_library(self, pipe_library: PipeLibraryAbstract)`
- `pipelex/hub.py:207` — `PipelexHub.set_pipe_router` — `def set_pipe_router(self, pipe_router: 'PipeRouterProtocol')`
- `pipelex/hub.py:210` — `PipelexHub.set_pipe_run` — `def set_pipe_run(self, pipe_run: 'PipeRunProtocol') -> None`
- `pipelex/hub.py:213` — `PipelexHub.set_pipeline_manager` — `def set_pipeline_manager(self, pipeline_manager: PipelineManagerAbstract)`
- `pipelex/hub.py:216` — `PipelexHub.set_observer` — `def set_observer(self, observer: ObserverProtocol)`
- `pipelex/hub.py:357` — `PipelexHub.set_library_manager` — `def set_library_manager(self, library_manager: LibraryManagerAbstract)`
- `pipelex/hub.py:360` — `PipelexHub.set_default_library_dirs` — `def set_default_library_dirs(self, library_dirs: list[Path] | None) -> None`
- `pipelex/hub.py:378` — `PipelexHub.set_func_registry` — `def set_func_registry(self, func_registry: FuncRegistry)`
- `pipelex/hub.py:389` — `set_pipelex_hub` — `def set_pipelex_hub(pipelex_hub: PipelexHub)`
- `pipelex/hub.py:455` — `get_llm_worker` — `def get_llm_worker(llm_handle: str) -> LLMWorkerAbstract`
- `pipelex/hub.py:461` — `get_img_gen_worker` — `def get_img_gen_worker(img_gen_handle: str) -> ImgGenWorkerAbstract`
- `pipelex/hub.py:467` — `get_extract_worker` — `def get_extract_worker(extract_handle: str) -> ExtractWorkerAbstract`
- `pipelex/hub.py:481` — `scoped_content_generator` — `def scoped_content_generator(content_generator: ContentGeneratorProtocol) -> Generator[None, None, None]`
- `pipelex/hub.py:515` — `get_secret` — `def get_secret(secret_id: str) -> str`
- `pipelex/hub.py:525` — `set_current_library` — `def set_current_library(library_id: str) -> None`
- `pipelex/hub.py:561` — `scoped_current_library` — `def scoped_current_library(library_id: str) -> Generator[None, None, None]`
- `pipelex/hub.py:578` — `resolve_library_dirs` — `def resolve_library_dirs(library_dirs: Sequence[str | Path] | None=None) -> tuple[list[Path], str]`
- `pipelex/hub.py:612` — `get_required_domain` — `def get_required_domain(domain_code: str) -> Domain`
- `pipelex/hub.py:616` — `get_optional_domain` — `def get_optional_domain(domain_code: str) -> Domain | None`
- `pipelex/hub.py:628` — `get_required_pipe` — `def get_required_pipe(pipe_code: str) -> PipeAbstract`
- `pipelex/hub.py:632` — `get_optional_pipe` — `def get_optional_pipe(pipe_code: str) -> PipeAbstract | None`
- `pipelex/hub.py:636` — `get_pipe_source` — `def get_pipe_source(pipe_code: str) -> Path | None`
- `pipelex/hub.py:652` — `get_required_concept` — `def get_required_concept(concept_ref: str) -> Concept`
- `pipelex/hub.py:659` — `set_pipe_router` — `def set_pipe_router(pipe_router: 'PipeRouterProtocol') -> None`
- `pipelex/hub.py:678` — `scoped_pipe_router` — `def scoped_pipe_router(pipe_router: 'PipeRouterProtocol') -> Generator[None, None, None]`
- `pipelex/hub.py:712` — `scoped_event_log` — `def scoped_event_log(event_log: 'EventLogProtocol') -> Generator[None, None, None]`
- `pipelex/hub.py:751` — `get_pipeline` — `def get_pipeline(pipeline_run_id: str) -> Pipeline`
- `pipelex/hub.py:763` — `get_native_concept` — `def get_native_concept(native_concept: NativeConceptCode) -> Concept`

### `kit` (3)

- `pipelex/kit/cursor_rules.py:20` — `_iter_agent_files` — `def _iter_agent_files(agents_dir: Traversable) -> Iterable[tuple[str, str]]`
- `pipelex/kit/cursor_rules.py:55` — `_is_pipelex_managed` — `def _is_pipelex_managed(mdc_path: Path) -> bool`
- `pipelex/kit/single_file_agent_rules.py:39` — `_demote_headings.demote_match` — `def demote_match(match: re.Match[str]) -> str`

### `language` (16)

- `pipelex/language/mthds_factory.py:36` — `MthdsFactory.format_tomlkit_string` — `def format_tomlkit_string(cls, text: str) -> Any`
- `pipelex/language/mthds_factory.py:163` — `MthdsFactory.add_spaces_to_inline_tables` — `def add_spaces_to_inline_tables(cls, toml_string: str) -> str`
- `pipelex/language/mthds_factory.py:171` — `MthdsFactory.add_spaces_to_inline_tables.find_and_replace_inline_tables` — `def find_and_replace_inline_tables(text: str) -> str`
- `pipelex/language/mthds_factory.py:228` — `MthdsFactory.make_template_table` — `def make_template_table(cls, template_value: Mapping[str, Any]) -> Any`
- `pipelex/language/mthds_factory.py:238` — `MthdsFactory.make_construct_table` — `def make_construct_table(cls, construct_value: Mapping[str, Any]) -> Any`
- `pipelex/language/mthds_factory.py:250` — `MthdsFactory.make_table_obj_for_pipe` — `def make_table_obj_for_pipe(cls, section_value: Mapping[str, Any]) -> Any`
- `pipelex/language/mthds_factory.py:267` — `MthdsFactory.make_table_obj_for_concept` — `def make_table_obj_for_concept(cls, section_value: Mapping[str, Any]) -> Any`
- `pipelex/language/mthds_factory.py:324` — `MthdsFactory.dict_to_mthds_styled_toml` — `def dict_to_mthds_styled_toml(cls, data: Mapping[str, Any]) -> str`
- `pipelex/language/mthds_factory.py:358` — `MthdsFactory.make_mthds_content` — `def make_mthds_content(cls, blueprint: PipelexBundleBlueprint) -> str`
- `pipelex/language/mthds_schema_generator.py:57` — `_remove_internal_fields` — `def _remove_internal_fields(schema: dict[str, Any]) -> dict[str, Any]`
- `pipelex/language/mthds_schema_generator.py:98` — `_promote_schema_required_fields` — `def _promote_schema_required_fields(schema: dict[str, Any]) -> dict[str, Any]`
- `pipelex/language/mthds_schema_generator.py:125` — `_require_type_on_pipe_definitions` — `def _require_type_on_pipe_definitions(schema: dict[str, Any]) -> dict[str, Any]`
- `pipelex/language/mthds_schema_generator.py:152` — `_convert_to_draft4` — `def _convert_to_draft4(schema: dict[str, Any]) -> dict[str, Any]`
- `pipelex/language/mthds_schema_generator.py:173` — `_draft4_visitor` — `def _draft4_visitor(node: dict[str, Any]) -> None`
- `pipelex/language/mthds_schema_generator.py:198` — `_patch_construct_schema` — `def _patch_construct_schema(schema: dict[str, Any]) -> dict[str, Any]`
- `pipelex/language/mthds_schema_generator.py:287` — `_add_taplo_metadata` — `def _add_taplo_metadata(schema: dict[str, Any]) -> dict[str, Any]`

### `libraries` (46)

- `pipelex/libraries/concept/concept_library.py:27` — `ConceptLibrary.set_concept_resolver` — `def set_concept_resolver(self, resolver: Callable[[str], Concept | None]) -> None`
- `pipelex/libraries/concept/concept_library.py:107` — `ConceptLibrary.get_optional_concept` — `def get_optional_concept(self, concept_ref: str) -> Concept | None`
- `pipelex/libraries/concept/concept_library.py:204` — `ConceptLibrary.is_concept_exists` — `def is_concept_exists(self, concept_ref: str) -> bool`
- `pipelex/libraries/concept/concept_library_abstract.py:9` — `ConceptLibraryAbstract.add_new_concept` — `def add_new_concept(self, concept: Concept) -> None`
- `pipelex/libraries/concept/concept_library_abstract.py:13` — `ConceptLibraryAbstract.add_concepts` — `def add_concepts(self, concepts: list[Concept]) -> None`
- `pipelex/libraries/concept/concept_library_abstract.py:17` — `ConceptLibraryAbstract.remove_concepts_by_concept_refs` — `def remove_concepts_by_concept_refs(self, concept_refs: list[str]) -> None`
- `pipelex/libraries/concept/concept_library_abstract.py:21` — `ConceptLibraryAbstract.list_concepts_by_domain` — `def list_concepts_by_domain(self, domain_code: str) -> list[Concept]`
- `pipelex/libraries/concept/concept_library_abstract.py:29` — `ConceptLibraryAbstract.get_required_concept` — `def get_required_concept(self, concept_ref: str) -> Concept`
- `pipelex/libraries/concept/concept_library_abstract.py:49` — `ConceptLibraryAbstract.get_native_concept` — `def get_native_concept(self, native_concept: NativeConceptCode) -> Concept`
- `pipelex/libraries/domain/domain_library.py:33` — `DomainLibrary.add_domain` — `def add_domain(self, domain: Domain)`
- `pipelex/libraries/domain/domain_library.py:59` — `DomainLibrary.add_domains` — `def add_domains(self, domains: list[Domain])`
- `pipelex/libraries/domain/domain_library.py:63` — `DomainLibrary.remove_domain_by_code` — `def remove_domain_by_code(self, domain_code: str) -> None`
- `pipelex/libraries/domain/domain_library_abstract.py:8` — `DomainLibraryAbstract.get_domain` — `def get_domain(self, domain_code: str) -> Domain | None`
- `pipelex/libraries/domain/domain_library_abstract.py:12` — `DomainLibraryAbstract.get_required_domain` — `def get_required_domain(self, domain_code: str) -> Domain`
- `pipelex/libraries/library.py:44` — `Library.set_class_registry` — `def set_class_registry(self, class_registry: ClassRegistry) -> None`
- `pipelex/libraries/library.py:56` — `Library.get_dependency_library` — `def get_dependency_library(self, alias: str) -> 'Library | None'`
- `pipelex/libraries/library.py:67` — `Library.resolve_concept` — `def resolve_concept(self, concept_ref: str) -> 'Concept | None'`
- `pipelex/libraries/library.py:148` — `Library._has_unresolved_cross_package_deps` — `def _has_unresolved_cross_package_deps(self, pipe: PipeController) -> bool`
- `pipelex/libraries/library_crate_factory.py:33` — `LibraryCrateFactory.make_from_blueprints` — `def make_from_blueprints(cls, blueprints: list[PipelexBundleBlueprint]) -> LibraryCrate`
- `pipelex/libraries/library_crate_factory.py:199` — `LibraryCrateFactory._declaration_sort_key` — `def _declaration_sort_key(declaration: PipeDeclaration) -> tuple[str, str]`
- `pipelex/libraries/library_manager.py:62` — `_find_methods_dirs_from_blueprints` — `def _find_methods_dirs_from_blueprints(blueprints: list[PipelexBundleBlueprint]) -> list[Path]`
- `pipelex/libraries/library_manager.py:116` — `LibraryManager._pop_and_teardown_library` — `def _pop_and_teardown_library(self, library_id: str) -> bool`
- `pipelex/libraries/library_manager.py:621` — `LibraryManager._load_concepts_from_blueprints` — `def _load_concepts_from_blueprints(self, blueprints: list[PipelexBundleBlueprint]) -> list['Concept']`
- `pipelex/libraries/library_manager.py:670` — `LibraryManager._load_concepts_from_crate` — `def _load_concepts_from_crate(self, concepts: dict[str, ConceptBlueprint | str]) -> list['Concept']`
- `pipelex/libraries/library_manager.py:700` — `LibraryManager._topological_load_concepts` — `def _topological_load_concepts(self, ref_to_entry: 'Mapping[str, tuple[str, str, ConceptBlueprint | str]]') -> list['Concept']`
- `pipelex/libraries/library_manager.py:916` — `LibraryManager._find_package_root` — `def _find_package_root(self, mthds_paths: list[Path]) -> Path | None`
- `pipelex/libraries/library_manager.py:1237` — `LibraryManager._remove_pipes_from_blueprint` — `def _remove_pipes_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> None`
- `pipelex/libraries/library_manager.py:1245` — `LibraryManager._remove_concepts_from_blueprint` — `def _remove_concepts_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> None`
- `pipelex/libraries/library_manager.py:1264` — `LibraryManager._rebuild_models_with_forward_refs` — `def _rebuild_models_with_forward_refs(self, concepts: list['Concept']) -> None`
- `pipelex/libraries/library_manager.py:1295` — `LibraryManager._detect_concept_cycles` — `def _detect_concept_cycles(self, concepts: list['Concept']) -> None`
- `pipelex/libraries/library_manager.py:1316` — `LibraryManager._detect_concept_cycles.get_referenced_concepts` — `def get_referenced_concepts(concept: 'Concept') -> list[str]`
- `pipelex/libraries/library_manager.py:1323` — `LibraryManager._detect_concept_cycles.get_referenced_concepts.extract_type_names` — `def extract_type_names(annotation: type) -> list[str]`
- `pipelex/libraries/library_manager_abstract.py:22` — `LibraryManagerAbstract.teardown` — `def teardown(self, library_id: str | None=None) -> None`
- `pipelex/libraries/library_manager_abstract.py:30` — `LibraryManagerAbstract.open_library` — `def open_library(self, library_id: str | None=None) -> tuple[str, 'Library']`
- `pipelex/libraries/library_manager_abstract.py:34` — `LibraryManagerAbstract.open_fresh_library` — `def open_fresh_library(self, library_id: str) -> 'Library'`
- `pipelex/libraries/library_manager_abstract.py:45` — `LibraryManagerAbstract.get_library` — `def get_library(self, library_id: str) -> 'Library'`
- `pipelex/libraries/library_manager_abstract.py:52` — `LibraryManagerAbstract.get_library_class_registry` — `def get_library_class_registry(self, library_id: str) -> ClassRegistry | None`
- `pipelex/libraries/library_manager_abstract.py:59` — `LibraryManagerAbstract.get_pipe_source` — `def get_pipe_source(self, pipe_code: str) -> Path | None`
- `pipelex/libraries/library_manager_abstract.py:71` — `LibraryManagerAbstract.get_crate` — `def get_crate(self, library_id: str) -> LibraryCrate | None`
- `pipelex/libraries/library_utils.py:65` — `get_pipelex_mthds_files_from_dirs` — `def get_pipelex_mthds_files_from_dirs(dirs: set[Path]) -> list[Path]`
- `pipelex/libraries/pipe/pipe_library_abstract.py:21` — `PipeLibraryAbstract.get_required_pipe` — `def get_required_pipe(self, pipe_code: str) -> PipeAbstract`
- `pipelex/libraries/pipe/pipe_library_abstract.py:25` — `PipeLibraryAbstract.get_optional_pipe` — `def get_optional_pipe(self, pipe_code: str) -> PipeAbstract | None`
- `pipelex/libraries/pipe/pipe_library_abstract.py:36` — `PipeLibraryAbstract.remove_pipes_by_refs` — `def remove_pipes_by_refs(self, pipe_refs: list[str]) -> None`
- `pipelex/libraries/pipe/pipe_library_abstract.py:44` — `PipeLibraryAbstract.add_new_pipe` — `def add_new_pipe(self, pipe: PipeAbstract) -> None`
- `pipelex/libraries/pipe/pipe_library_abstract.py:48` — `PipeLibraryAbstract.add_pipes` — `def add_pipes(self, pipes: list[PipeAbstract]) -> None`
- `pipelex/libraries/visibility_utils.py:14` — `_blueprint_to_metadata` — `def _blueprint_to_metadata(blueprint: PipelexBundleBlueprint) -> BundleMetadata`

### `observer` (4)

- `pipelex/observer/multi_observer.py:14` — `MultiObserver.remove_observer` — `def remove_observer(self, name: str) -> None`
- `pipelex/observer/observer_protocol.py:18` — `ObserverProtocol.observe_before_run` — `async def observe_before_run(self, payload: PayloadType) -> None`
- `pipelex/observer/observer_protocol.py:25` — `ObserverProtocol.observe_after_successful_run` — `async def observe_after_successful_run(self, payload: PayloadType) -> None`
- `pipelex/observer/observer_protocol.py:32` — `ObserverProtocol.observe_after_failing_run` — `async def observe_after_failing_run(self, payload: PayloadType) -> None`

### `pipe_controllers` (5)

- `pipelex/pipe_controllers/batch/pipe_batch.py:35` — `resolve_batch_max_concurrency` — `def resolve_batch_max_concurrency(max_concurrency_setting: int | str) -> int | None`
- `pipelex/pipe_controllers/condition/pipe_condition.py:197` — `PipeCondition._evaluate_expression` — `async def _evaluate_expression(self, working_memory: WorkingMemory) -> str`
- `pipelex/pipe_controllers/condition/special_outcome.py:15` — `SpecialOutcome.is_continue` — `def is_continue(cls, outcome: str) -> bool`
- `pipelex/pipe_controllers/condition/special_outcome.py:30` — `SpecialOutcome.is_fail` — `def is_fail(cls, outcome: str) -> bool`
- `pipelex/pipe_controllers/sub_pipe_factory.py:13` — `SubPipeFactory.make_from_blueprint` — `def make_from_blueprint(cls, blueprint: SubPipeBlueprint) -> SubPipe`

### `pipe_operators` (13)

- `pipelex/pipe_operators/compose/construct_blueprint.py:108` — `ConstructFieldBlueprint.make_from_raw` — `def make_from_raw(cls, raw: Any) -> ConstructFieldBlueprint`
- `pipelex/pipe_operators/compose/construct_blueprint.py:294` — `ConstructBlueprint.make_from_raw` — `def make_from_raw(cls, raw: dict[str, Any]) -> ConstructBlueprint`
- `pipelex/pipe_operators/compose/structured_content_composer.py:78` — `StructuredContentComposer._build_field_type_summary` — `def _build_field_type_summary(self, field_values: dict[str, Any]) -> str`
- `pipelex/pipe_operators/compose/structured_content_composer.py:377` — `StructuredContentComposer._get_field_expected_type` — `def _get_field_expected_type(self, field_name: str) -> type[Any] | None`
- `pipelex/pipe_operators/compose/structured_content_composer.py:451` — `StructuredContentComposer._expects_list_content_type` — `def _expects_list_content_type(self, expected_type: type[Any]) -> bool`
- `pipelex/pipe_operators/compose/structured_content_composer.py:474` — `StructuredContentComposer._expects_list_type` — `def _expects_list_type(self, expected_type: type[Any]) -> bool`
- `pipelex/pipe_operators/compose/structured_content_composer.py:486` — `StructuredContentComposer._get_list_item_type` — `def _get_list_item_type(self, expected_type: type[Any]) -> type[Any] | None`
- `pipelex/pipe_operators/compose/structured_content_composer.py:624` — `StructuredContentComposer._resolve_template` — `async def _resolve_template(self, field_blueprint: ConstructFieldBlueprint) -> str`
- `pipelex/pipe_operators/compose/structured_content_composer.py:691` — `StructuredContentComposer._get_nested_field_class` — `def _get_nested_field_class(self, field_name: str) -> type[StuffContent]`
- `pipelex/pipe_operators/llm/helpers.py:12` — `get_output_structure_prompt` — `async def get_output_structure_prompt(concept_ref: str) -> str | None`
- `pipelex/pipe_operators/llm/pipe_llm.py:141` — `PipeLLM.resolve_dynamic_output_stuff_spec` — `def resolve_dynamic_output_stuff_spec(self, pipe_run_params: PipeRunParams) -> StuffSpec`
- `pipelex/pipe_operators/llm/pipe_llm.py:383` — `PipeLLM._format_error_location` — `def _format_error_location(self, pipe_run_params: PipeRunParams) -> str`
- `pipelex/pipe_operators/structure/pipe_structure.py:204` — `PipeStructure._format_error_location` — `def _format_error_location(self, pipe_run_params: PipeRunParams) -> str`

### `pipe_run` (9)

- `pipelex/pipe_run/delivery_executor.py:77` — `DeliveryExecutor.generate_result_files` — `async def generate_result_files(self, pipe_output: PipeOutput) -> dict[str, ResultFile]`
- `pipelex/pipe_run/delivery_executor.py:121` — `DeliveryExecutor._get_raw_main_stuff_dict` — `def _get_raw_main_stuff_dict(cls, working_memory_raw: dict[str, Any]) -> dict[str, Any] | None`
- `pipelex/pipe_run/delivery_executor.py:132` — `DeliveryExecutor.try_local_hydrate_stuff` — `def try_local_hydrate_stuff(cls, stuff_raw: dict[str, Any]) -> Stuff | None`
- `pipelex/pipe_run/pipe_router_protocol.py:14` — `PipeRouterProtocol._before_run` — `async def _before_run(self, pipe_job: PipeJob) -> None`
- `pipelex/pipe_run/pipe_router_protocol.py:50` — `PipeRouterProtocol.run` — `async def run(self, pipe_job: PipeJob) -> PipeOutput`
- `pipelex/pipe_run/pipe_router_protocol.py:81` — `PipeRouterProtocol._run_pipe_job` — `async def _run_pipe_job(self, pipe_job: PipeJob) -> PipeOutput`
- `pipelex/pipe_run/pipe_run_params.py:229` — `PipeRunParams.push_pipe_to_stack` — `def push_pipe_to_stack(self, pipe_code: str) -> None`
- `pipelex/pipe_run/pipe_run_params.py:239` — `PipeRunParams.pop_pipe_from_stack` — `def pop_pipe_from_stack(self, pipe_code: str) -> None`
- `pipelex/pipe_run/pipe_run_params.py:249` — `PipeRunParams.push_pipe_layer` — `def push_pipe_layer(self, pipe_code: str) -> None`

### `pipelex.py` (1)

- `pipelex/pipelex.py:140` — `Pipelex._get_config_file_not_found_error_msg` — `def _get_config_file_not_found_error_msg(component_name: str) -> str`

### `pipeline` (13)

- `pipelex/pipeline/blueprint_selection.py:26` — `select_primary_blueprint` — `def select_primary_blueprint(blueprints: Sequence[PipelexBundleBlueprint]) -> PrimaryBlueprintSelection`
- `pipelex/pipeline/bundle_validator.py:270` — `BundleValidator._signature_pre_pass` — `def _signature_pre_pass(cls, pipes: list[PipeAbstract]) -> None`
- `pipelex/pipeline/execution_seams.py:132` — `load_libraries_and_activate` — `def load_libraries_and_activate(library_dirs: Sequence[str | Path] | None=None) -> str`
- `pipelex/pipeline/input_normalizer.py:32` — `normalize_data_urls_to_storage` — `async def normalize_data_urls_to_storage(working_memory: WorkingMemory) -> WorkingMemory`
- `pipelex/pipeline/pipe_io_contracts.py:63` — `build_pipe_io_contracts` — `def build_pipe_io_contracts(pipes: Sequence[PipeAbstract]) -> dict[str, PipeIOContract]`
- `pipelex/pipeline/pipeline_factory.py:9` — `PipelineFactory.make_pipeline` — `def make_pipeline(cls, pipeline_run_id: str | None=None) -> Pipeline`
- `pipelex/pipeline/pipeline_manager_abstract.py:16` — `PipelineManagerAbstract.get_optional_pipeline` — `def get_optional_pipeline(self, pipeline_run_id: str) -> Pipeline | None`
- `pipelex/pipeline/pipeline_manager_abstract.py:20` — `PipelineManagerAbstract.get_pipeline` — `def get_pipeline(self, pipeline_run_id: str) -> Pipeline`
- `pipelex/pipeline/pipeline_manager_abstract.py:28` — `PipelineManagerAbstract.remove_pipeline` — `def remove_pipeline(self, pipeline_run_id: str) -> None`
- `pipelex/pipeline/validate_bundle.py:68` — `build_validated_pipes` — `def build_validated_pipes(dry_run_result: dict[str, DryRunOutput]) -> list[ValidatedPipeEntry]`
- `pipelex/pipeline/validate_bundle.py:79` — `build_pending_signatures` — `def build_pending_signatures(pipes_by_ref: dict[str, PipeAbstract]) -> list[str]`
- `pipelex/pipeline/validate_bundle.py:95` — `_translate_to_validate_bundle_error` — `def _translate_to_validate_bundle_error(category: Literal['pipe', 'concept']) -> Generator[None, None, None]`
- `pipelex/pipeline/validate_bundle.py:463` — `load_concepts_only_from_directory` — `def load_concepts_only_from_directory(directory: Path) -> LoadConceptsOnlyResult`

### `plugins` (83)

- `pipelex/plugins/anthropic/anthropic_config.py:26` — `AnthropicConfig.get_reasoning_level` — `def get_reasoning_level(self, effort: ReasoningEffort) -> AnthropicEffortLevel | None`
- `pipelex/plugins/anthropic/anthropic_factory.py:78` — `AnthropicFactory._make_image_block_param` — `def _make_image_block_param(prepped_image: PreparedFile) -> ImageBlockParam`
- `pipelex/plugins/anthropic/anthropic_factory.py:137` — `AnthropicFactory.make_user_message` — `async def make_user_message(cls, llm_job: LLMJob) -> MessageParam`
- `pipelex/plugins/anthropic/anthropic_factory.py:199` — `AnthropicFactory.make_simple_messages` — `async def make_simple_messages(cls, llm_job: LLMJob) -> 'list["ChatCompletionMessageParam"]'`
- `pipelex/plugins/anthropic/anthropic_factory.py:236` — `AnthropicFactory.make_nb_tokens_by_category` — `def make_nb_tokens_by_category(usage: Usage) -> NbTokensByCategoryDict`
- `pipelex/plugins/anthropic/anthropic_factory.py:252` — `AnthropicFactory.calculate_safe_max_tokens_for_timeout` — `def calculate_safe_max_tokens_for_timeout(timeout_seconds: int) -> int`
- `pipelex/plugins/azure_rest/azure_img_gen_worker.py:65` — `AzureImgGenWorker._raise_categorized_azure_status_error` — `def _raise_categorized_azure_status_error(self, exc: httpx.HTTPStatusError) -> None`
- `pipelex/plugins/bedrock/bedrock_factory.py:62` — `BedrockFactory.make_simple_message` — `def make_simple_message(cls, llm_job: LLMJob) -> BedrockMessage`
- `pipelex/plugins/bedrock/bedrock_llm_worker.py:46` — `BedrockLLMWorker._validate_no_reasoning_params` — `def _validate_no_reasoning_params(self, job_params: LLMJobParams) -> None`
- `pipelex/plugins/docling/docling_extract_worker.py:63` — `DoclingExtractWorker._extract_from_source` — `async def _extract_from_source(self, source_uri: str) -> ExtractOutput`
- `pipelex/plugins/docling/docling_factory.py:17` — `DoclingFactory.make_extract_output_from_docling_document` — `def make_extract_output_from_docling_document(cls, doc: 'DoclingDocument') -> ExtractOutput`
- `pipelex/plugins/fal/fal_factory.py:13` — `FalFactory.make_generated_image` — `def make_generated_image(cls, fal_result: dict[str, Any]) -> GeneratedImageRawDetails`
- `pipelex/plugins/fal/fal_factory.py:29` — `FalFactory.make_generated_image_list` — `def make_generated_image_list(cls, fal_result: dict[str, Any]) -> list[GeneratedImageRawDetails]`
- `pipelex/plugins/fal/fal_poller.py:19` — `FalPoller._is_transient_http` — `def _is_transient_http(self, exc: BaseException) -> bool`
- `pipelex/plugins/fal/fal_poller.py:25` — `FalPoller.poll_queue_until_complete` — `async def poll_queue_until_complete(self, response_dict: dict[str, Any]) -> dict[str, Any]`
- `pipelex/plugins/gateway/gateway_completions_factory.py:156` — `GatewayCompletionsFactory._extract_pages_from_choices_content` — `def _extract_pages_from_choices_content(cls, response: GenericResponse) -> list[dict[str, Any]] | None`
- `pipelex/plugins/gateway/gateway_completions_factory.py:187` — `GatewayCompletionsFactory._make_extract_output_from_response_azure` — `def _make_extract_output_from_response_azure(cls, response: GenericResponse) -> ExtractOutput`
- `pipelex/plugins/gateway/gateway_completions_factory.py:226` — `GatewayCompletionsFactory._make_extract_output_from_response_mistral` — `def _make_extract_output_from_response_mistral(cls, response: GenericResponse) -> ExtractOutput`
- `pipelex/plugins/gateway/gateway_completions_factory.py:276` — `GatewayCompletionsFactory._make_extract_output_from_response_deepseek` — `def _make_extract_output_from_response_deepseek(cls, response: GenericResponse) -> ExtractOutput`
- `pipelex/plugins/gateway/gateway_completions_factory.py:311` — `GatewayCompletionsFactory._make_extract_output_from_response_linkup_fetch` — `def _make_extract_output_from_response_linkup_fetch(cls, response: GenericResponse) -> ExtractOutput`
- `pipelex/plugins/gateway/gateway_completions_factory.py:345` — `GatewayCompletionsFactory._extract_content_string_from_response` — `def _extract_content_string_from_response(cls, response: GenericResponse) -> str | None`
- `pipelex/plugins/gateway/gateway_constants.py:9` — `GatewayOpenAISdkVariant.is_completions` — `def is_completions(cls, sdk: str) -> bool`
- `pipelex/plugins/gateway/gateway_constants.py:21` — `GatewayOpenAISdkVariant.is_responses` — `def is_responses(cls, sdk: str) -> bool`
- `pipelex/plugins/gateway/gateway_deck.py:9` — `GatewayDeck.get_config_id` — `def get_config_id(cls, headers: dict[str, str]) -> str`
- `pipelex/plugins/gateway/gateway_extract_worker.py:94` — `GatewayExtractWorker._extract_document` — `async def _extract_document(self, extract_job: ExtractJob) -> ExtractOutput`
- `pipelex/plugins/gateway/gateway_extract_worker.py:128` — `GatewayExtractWorker._extract_web_fetch` — `async def _extract_web_fetch(self, extract_job: ExtractJob) -> ExtractOutput`
- `pipelex/plugins/gateway/gateway_factory.py:32` — `GatewayFactory.is_debug_enabled` — `def is_debug_enabled(cls, backend: InferenceBackend) -> bool`
- `pipelex/plugins/gateway/gateway_factory.py:37` — `GatewayFactory.get_endpoint` — `def get_endpoint(cls, backend: InferenceBackend) -> str`
- `pipelex/plugins/gateway/gateway_factory.py:41` — `GatewayFactory.get_api_key` — `def get_api_key(cls, backend: InferenceBackend) -> str`
- `pipelex/plugins/gateway/gateway_factory.py:48` — `GatewayFactory.make_portkey_client` — `def make_portkey_client(cls, backend: InferenceBackend) -> AsyncPortkey`
- `pipelex/plugins/gateway/gateway_protocols.py:13` — `GatewayExtractProtocol.make_from_model_handle` — `def make_from_model_handle(cls, model_handle: str) -> GatewayExtractProtocol`
- `pipelex/plugins/gateway/gateway_search_worker.py:178` — `GatewaySearchWorker._extract_content` — `def _extract_content(self, response: GenericResponse) -> str`
- `pipelex/plugins/google/google_config.py:32` — `GoogleConfig.get_reasoning_level` — `def get_reasoning_level(self, effort: ReasoningEffort) -> genai_types.ThinkingLevel | None`
- `pipelex/plugins/google/google_factory.py:21` — `GoogleFactory.make_google_client` — `def make_google_client(cls, backend: InferenceBackend) -> GoogleGenAiClient`
- `pipelex/plugins/google/google_factory.py:31` — `GoogleFactory.prepare_image_part` — `async def prepare_image_part(cls, prompt_image: PromptImage) -> genai_types.Part`
- `pipelex/plugins/google/google_factory.py:42` — `GoogleFactory.prepare_document_part` — `async def prepare_document_part(cls, prompt_document: PromptDocument) -> genai_types.Part`
- `pipelex/plugins/google/google_factory.py:53` — `GoogleFactory.prepare_user_contents` — `async def prepare_user_contents(cls, llm_prompt: LLMPrompt) -> genai_types.ContentListUnion`
- `pipelex/plugins/google/google_factory.py:139` — `GoogleFactory.extract_token_usage` — `def extract_token_usage(cls, usage_metadata: genai_types.GenerateContentResponseUsageMetadata | None) -> NbTokensByCategoryDict`
- `pipelex/plugins/google/google_img_gen_factory.py:82` — `GoogleImgGenFactory.aspect_ratio_literal` — `def aspect_ratio_literal(cls, aspect_ratio: AspectRatio) -> GoogleAspectRatioType`
- `pipelex/plugins/huggingface/huggingface_factory.py:6` — `HuggingFaceFactory.make_huggingface_inference_provider` — `def make_huggingface_inference_provider(cls, provider_str: str) -> PROVIDER_OR_POLICY_T`
- `pipelex/plugins/huggingface/huggingface_img_gen_worker.py:37` — `HuggingFaceImgGenWorker._generate_single_image` — `async def _generate_single_image(self, img_gen_job: ImgGenJob) -> Image.Image`
- `pipelex/plugins/linkup/linkup_search_worker.py:42` — `LinkupSearchWorker._parse_date` — `def _parse_date(self, date_str: str | None) -> date | None`
- `pipelex/plugins/mistral/mistral_config.py:29` — `MistralConfig.get_reasoning_level` — `def get_reasoning_level(self, effort: ReasoningEffort) -> MistralPromptMode | None`
- `pipelex/plugins/mistral/mistral_extract_worker.py:62` — `MistralExtractWorker._extract_page_from_image` — `async def _extract_page_from_image(self, image_uri: str) -> ExtractOutput`
- `pipelex/plugins/mistral/mistral_factory.py:50` — `MistralFactory.make_mistral_client` — `def make_mistral_client(cls, backend: InferenceBackend) -> Mistral`
- `pipelex/plugins/mistral/mistral_factory.py:73` — `MistralFactory.make_simple_messages` — `async def make_simple_messages(self, llm_job: LLMJob) -> list[Messages]`
- `pipelex/plugins/mistral/mistral_factory.py:93` — `MistralFactory.make_mistral_image_url` — `async def make_mistral_image_url(self, prompt_image: PromptImage) -> ImageURLChunk`
- `pipelex/plugins/mistral/mistral_factory.py:114` — `MistralFactory.make_mistral_document_url` — `async def make_mistral_document_url(self, prompt_document: PromptDocument) -> DocumentURLChunk`
- `pipelex/plugins/mistral/mistral_factory.py:136` — `MistralFactory.make_simple_messages_openai_typed` — `async def make_simple_messages_openai_typed(self, llm_job: LLMJob) -> 'list["ChatCompletionMessageParam"]'`
- `pipelex/plugins/mistral/mistral_factory.py:189` — `MistralFactory.make_nb_tokens_by_category` — `def make_nb_tokens_by_category(self, usage: UsageInfo) -> NbTokensByCategoryDict`
- `pipelex/plugins/mistral/mistral_factory.py:197` — `MistralFactory.make_extract_output_from_mistral_response` — `async def make_extract_output_from_mistral_response(cls, mistral_extract_response: mistralai.OCRResponse) -> ExtractOutput`
- `pipelex/plugins/mistral/mistral_factory.py:222` — `MistralFactory._clean_mistral_image_base64` — `def _clean_mistral_image_base64(cls, base64_str: str) -> str`
- `pipelex/plugins/mistral/mistral_factory.py:278` — `MistralFactory.make_extracted_image_from_page_from_mistral_ocr_image_obj` — `def make_extracted_image_from_page_from_mistral_ocr_image_obj(cls, mistral_ocr_image_obj: mistralai.OCRImageObject) -> ExtractedImageFromPage`
- `pipelex/plugins/mistral/mistral_factory.py:326` — `MistralFactory.make_mistral_image_url_chunk_from_uri` — `async def make_mistral_image_url_chunk_from_uri(cls, uri: str) -> ImageURLChunkTypedDict`
- `pipelex/plugins/mistral/mistral_llm_worker.py:68` — `MistralLLMWorker._resolve_prompt_mode` — `def _resolve_prompt_mode(self, job_params: LLMJobParams) -> 'OptionalNullable[MistralPromptMode]'`
- `pipelex/plugins/openai/openai_completions_factory.py:27` — `OpenAICompletionsFactory.make_simple_messages` — `async def make_simple_messages(self, llm_job: LLMJob) -> 'list["ChatCompletionMessageParam"]'`
- `pipelex/plugins/openai/openai_completions_factory.py:94` — `OpenAICompletionsFactory._get_document_filename` — `def _get_document_filename(prompt_document: PromptDocument) -> str`
- `pipelex/plugins/openai/openai_completions_factory.py:99` — `OpenAICompletionsFactory.make_nb_tokens_by_category` — `def make_nb_tokens_by_category(self, usage: 'CompletionUsage') -> NbTokensByCategoryDict`
- `pipelex/plugins/openai/openai_completions_img_gen_worker.py:177` — `OpenAICompletionsImgGenWorker._build_messages_with_images` — `async def _build_messages_with_images(self, img_gen_job: ImgGenJob) -> 'list[ChatCompletionMessageParam]'`
- `pipelex/plugins/openai/openai_completions_llm_worker.py:87` — `OpenAICompletionsLLMWorker._resolve_reasoning_effort` — `def _resolve_reasoning_effort(self, job_params: LLMJobParams) -> ChatCompletionReasoningEffort | None`
- `pipelex/plugins/openai/openai_config.py:32` — `OpenAIConfig.get_reasoning_level` — `def get_reasoning_level(self, effort: ReasoningEffort) -> 'ChatCompletionReasoningEffort | None'`
- `pipelex/plugins/openai/openai_func.py:12` — `create_pydantic_model_from_function` — `def create_pydantic_model_from_function(func: Callable[..., Any]) -> type[BaseModel]`
- `pipelex/plugins/openai/openai_func.py:33` — `create_openai_schema_from_function` — `def create_openai_schema_from_function(func: Callable[..., Any]) -> dict[str, Any]`
- `pipelex/plugins/openai/openai_func.py:63` — `list_openai_tools` — `def list_openai_tools(openai_message: ChatCompletionMessage) -> list[str]`
- `pipelex/plugins/openai/openai_img_gen_factory.py:121` — `OpenAIImgGenFactory.moderation_for_openai_image` — `def moderation_for_openai_image(cls, is_moderated: bool | None) -> OpenAIImageModerationType`
- `pipelex/plugins/openai/openai_img_gen_factory.py:130` — `OpenAIImgGenFactory.input_fidelity_for_openai_image` — `def input_fidelity_for_openai_image(cls, input_fidelity: InputFidelity) -> OpenAIImageInputFidelityType`
- `pipelex/plugins/openai/openai_img_gen_factory.py:138` — `OpenAIImgGenFactory._size_to_string` — `def _size_to_string(size: ImageSize) -> str`
- `pipelex/plugins/openai/openai_img_gen_worker.py:186` — `OpenAIImgGenWorker._convert_image_data_urls_for_openai_sdk` — `def _convert_image_data_urls_for_openai_sdk(image_arg: Any) -> list[tuple[str, bytes, str]]`
- `pipelex/plugins/openai/openai_img_gen_worker.py:209` — `OpenAIImgGenWorker._get_requested_size` — `def _get_requested_size(args_dict: dict[str, Any]) -> str | None`
- `pipelex/plugins/openai/openai_responses_factory.py:36` — `OpenAIResponsesFactory.make_input_items` — `async def make_input_items(self, llm_job: LLMJob) -> list[ResponseInputItemParam]`
- `pipelex/plugins/openai/openai_responses_factory.py:93` — `OpenAIResponsesFactory._get_document_filename` — `def _get_document_filename(prompt_document: PromptDocument) -> str`
- `pipelex/plugins/openai/openai_responses_factory.py:98` — `OpenAIResponsesFactory.make_nb_tokens_by_category` — `def make_nb_tokens_by_category(self, usage: ResponseUsage) -> NbTokensByCategoryDict`
- `pipelex/plugins/openai/openai_responses_llm_worker.py:90` — `OpenAIResponsesLLMWorker._resolve_reasoning` — `def _resolve_reasoning(self, job_params: LLMJobParams) -> Reasoning | None`
- `pipelex/plugins/openai/vertexai_factory.py:20` — `VertexAIFactory.make_endpoint_and_api_key` — `def make_endpoint_and_api_key(cls, extra_config: dict[str, Any]) -> tuple[str, str]`
- `pipelex/plugins/openai/vertexai_factory.py:51` — `VertexAIFactory._make_api_key` — `def _make_api_key(cls, gcp_credentials_file_path: str) -> str`
- `pipelex/plugins/plugin.py:19` — `Plugin.make_for_inference_model` — `def make_for_inference_model(cls, inference_model: InferenceModelSpec) -> 'Plugin'`
- `pipelex/plugins/plugin_sdk_registry.py:19` — `PluginSdkRegistry.get_sdk_instance` — `def get_sdk_instance(self, plugin: Plugin) -> Any | None`
- `pipelex/plugins/portkey/portkey_constants.py:17` — `PortkeyOpenAISdkVariant.is_completions` — `def is_completions(cls, sdk: str) -> bool`
- `pipelex/plugins/portkey/portkey_constants.py:29` — `PortkeyOpenAISdkVariant.is_responses` — `def is_responses(cls, sdk: str) -> bool`
- `pipelex/plugins/portkey/portkey_factory.py:24` — `PortkeyFactory.is_debug_enabled` — `def is_debug_enabled(cls, backend: InferenceBackend) -> bool`
- `pipelex/plugins/portkey/portkey_factory.py:29` — `PortkeyFactory.get_endpoint` — `def get_endpoint(cls, backend: InferenceBackend) -> str`
- `pipelex/plugins/portkey/portkey_factory.py:33` — `PortkeyFactory.get_api_key` — `def get_api_key(cls, backend: InferenceBackend) -> str`
- `pipelex/plugins/pypdfium2/pypdfium2_worker.py:38` — `Pypdfium2Worker._resolve_pdf_uri` — `async def _resolve_pdf_uri(self, pdf_uri: str) -> PdfInput`

### `reporting` (7)

- `pipelex/reporting/cost_report_renderer.py:86` — `render_cost_report_for_output` — `def render_cost_report_for_output(pipe_output: PipeOutput) -> None`
- `pipelex/reporting/reporting_manager.py:143` — `ReportingManager._report_llm_job` — `def _report_llm_job(self, llm_job: LLMJob)`
- `pipelex/reporting/reporting_manager.py:152` — `ReportingManager._report_img_gen_job` — `def _report_img_gen_job(self, img_gen_job: ImgGenJob)`
- `pipelex/reporting/reporting_manager.py:161` — `ReportingManager._report_extract_job` — `def _report_extract_job(self, extract_job: ExtractJob)`
- `pipelex/reporting/reporting_manager.py:170` — `ReportingManager._report_search_job` — `def _report_search_job(self, search_job: SearchJob)`
- `pipelex/reporting/reporting_protocol.py:10` — `ReportingProtocol.report_inference_job` — `def report_inference_job(self, inference_job: InferenceJobAbstract)`
- `pipelex/reporting/reporting_protocol.py:25` — `ReportingProtocol.clear_event_log` — `def clear_event_log(self, context_key: str) -> None`

### `runtime_bridge` (10)

- `pipelex/runtime_bridge/bootstrap.py:24` — `ensure_pipelex_booted` — `def ensure_pipelex_booted(config_overrides: dict[str, Any] | None=None) -> None`
- `pipelex/runtime_bridge/bridge.py:225` — `serialize_pipe_output` — `def serialize_pipe_output(pipe_output: PipeOutput) -> dict[str, Any]`
- `pipelex/runtime_bridge/bridge.py:250` — `_decode_library_crate` — `def _decode_library_crate(library_crate_dump: dict[str, Any] | None) -> LibraryCrate | None`
- `pipelex/runtime_bridge/bridge.py:260` — `_decode_delivery_assignment` — `def _decode_delivery_assignment(delivery_assignment_dump: dict[str, Any] | None) -> DeliveryAssignment | None`
- `pipelex/runtime_bridge/bridge.py:383` — `_resolve_main_stuff_root_key` — `def _resolve_main_stuff_root_key(pipe_output: PipeOutput) -> str | None`
- `pipelex/runtime_bridge/primitives/hydration.py:39` — `_hydrate_list_item` — `def _hydrate_list_item(raw_item: dict[str, Any] | str | StuffContent) -> StuffContent`
- `pipelex/runtime_bridge/primitives/hydration.py:109` — `hydrate_working_memory` — `def hydrate_working_memory(working_memory_raw: dict[str, Any]) -> WorkingMemory`
- `pipelex/runtime_bridge/primitives/pipe_classification.py:17` — `is_controller_pipe` — `def is_controller_pipe(pipe: PipeAbstract) -> bool`
- `pipelex/runtime_bridge/primitives/pipe_classification.py:29` — `is_leaf_pipe` — `def is_leaf_pipe(pipe: PipeAbstract) -> bool`
- `pipelex/runtime_bridge/primitives/trace_flush.py:14` — `flush_trace_events_to_backend` — `async def flush_trace_events_to_backend(events: list[TraceEvent]) -> None`

### `system` (61)

- `pipelex/system/configuration/config_check.py:12` — `check_is_initialized` — `def check_is_initialized(print_warning_if_not: bool=True) -> bool`
- `pipelex/system/configuration/config_loader.py:32` — `ConfigLoader.find_project_root` — `def find_project_root(start_dir: Path) -> Path | None`
- `pipelex/system/configuration/configs.py:83` — `PromptingConfig.get_prompting_style` — `def get_prompting_style(self, prompting_target: PromptingTarget | None=None) -> TemplatingStyle | None`
- `pipelex/system/environment.py:21` — `get_required_env` — `def get_required_env(key: str) -> str`
- `pipelex/system/environment.py:29` — `get_optional_env` — `def get_optional_env(key: str) -> str | None`
- `pipelex/system/environment.py:33` — `is_env_var_set` — `def is_env_var_set(key: str) -> bool`
- `pipelex/system/environment.py:37` — `all_env_vars_are_set` — `def all_env_vars_are_set(keys: list[str]) -> bool`
- `pipelex/system/environment.py:41` — `any_env_var_is_placeholder` — `def any_env_var_is_placeholder(keys: list[str]) -> bool`
- `pipelex/system/environment.py:53` — `is_env_var_truthy` — `def is_env_var_truthy(key: str) -> bool`
- `pipelex/system/pipelex_service/pipelex_details.py:22` — `PipelexDetails.make_distinct_id` — `def make_distinct_id(cls, gateway_api_key: str) -> str`
- `pipelex/system/pipelex_service/pipelex_service_config.py:24` — `load_pipelex_service_config_if_exists` — `def load_pipelex_service_config_if_exists(config_dir: Path) -> PipelexServiceConfig | None`
- `pipelex/system/pipelex_service/pipelex_service_config.py:45` — `is_pipelex_gateway_enabled` — `def is_pipelex_gateway_enabled(backends_file_path: Path | None=None) -> bool`
- `pipelex/system/pipelex_service/remote_config_cache.py:99` — `RemoteConfigCache.store` — `def store(cls, remote_config_payload: dict[str, Any]) -> None`
- `pipelex/system/pipelex_service/remote_config_fetcher.py:79` — `RemoteConfigFetcher._log_retry_attempt` — `def _log_retry_attempt(cls, retry_state: RetryCallState) -> None`
- `pipelex/system/pipelex_service/remote_config_fetcher.py:85` — `RemoteConfigFetcher._fetch_remote_config_with_retry` — `def _fetch_remote_config_with_retry(cls, url: str) -> httpx.Response`
- `pipelex/system/pipelex_service/remote_config_fetcher.py:107` — `RemoteConfigFetcher._fetch_remote_config_with_retry._fetch_with_retry` — `def _fetch_with_retry(url: str) -> httpx.Response`
- `pipelex/system/pipelex_service/remote_config_fetcher.py:133` — `RemoteConfigFetcher._fetch_fresh` — `def _fetch_fresh(cls, url: str) -> tuple[dict[str, Any], RemoteConfig]`
- `pipelex/system/pipelex_service/remote_config_fetcher.py:201` — `RemoteConfigFetcher.fetch_remote_config` — `def fetch_remote_config(cls, require_fresh: bool=False) -> RemoteConfigResult`
- `pipelex/system/registries/class_registry_utils.py:135` — `ClassRegistryUtils.auto_register_all_subclasses` — `def auto_register_all_subclasses(cls, base_class: type[Any]) -> int`
- `pipelex/system/registries/func_registry.py:22` — `pipe_func` — `def pipe_func(name: str | None=None) -> Callable[[T], T]`
- `pipelex/system/registries/func_registry.py:48` — `pipe_func.decorator` — `def decorator(func: T) -> T`
- `pipelex/system/registries/func_registry.py:88` — `FuncRegistry.log` — `def log(self, message: str) -> None`
- `pipelex/system/registries/func_registry.py:91` — `FuncRegistry.set_logger` — `def set_logger(self, logger: logging.Logger) -> None`
- `pipelex/system/registries/func_registry.py:116` — `FuncRegistry.unregister_function` — `def unregister_function(self, func: Callable[..., Any]) -> None`
- `pipelex/system/registries/func_registry.py:125` — `FuncRegistry.unregister_function_by_name` — `def unregister_function_by_name(self, name: str) -> None`
- `pipelex/system/registries/func_registry.py:132` — `FuncRegistry.register_functions_dict` — `def register_functions_dict(self, functions: dict[str, Callable[..., Any]]) -> None`
- `pipelex/system/registries/func_registry.py:137` — `FuncRegistry.register_functions` — `def register_functions(self, functions: list[Callable[..., Any]]) -> None`
- `pipelex/system/registries/func_registry.py:142` — `FuncRegistry.get_function` — `def get_function(self, name: str) -> Callable[..., Any] | None`
- `pipelex/system/registries/func_registry.py:146` — `FuncRegistry.get_required_function` — `def get_required_function(self, name: str) -> Callable[..., Any]`
- `pipelex/system/registries/func_registry.py:167` — `FuncRegistry.get_required_function_with_signature` — `def get_required_function_with_signature(self, name: str) -> Callable[..., object]`
- `pipelex/system/registries/func_registry.py:183` — `FuncRegistry.has_function` — `def has_function(self, name: str) -> bool`
- `pipelex/system/registries/func_registry.py:187` — `FuncRegistry.is_marked_pipe_func` — `def is_marked_pipe_func(self, func: Any) -> bool`
- `pipelex/system/registries/func_registry.py:273` — `FuncRegistry.check_function_eligibility` — `def check_function_eligibility(self, func: Any) -> str | None`
- `pipelex/system/registries/func_registry.py:368` — `FuncRegistry.get_ineligible_function_info` — `def get_ineligible_function_info(self, name: str) -> IneligibleFunctionInfo | None`
- `pipelex/system/registries/func_registry_utils.py:113` — `FuncRegistryUtils._register_funcs_in_file` — `def _register_funcs_in_file(cls, file_path: Path) -> None`
- `pipelex/system/registries/func_registry_utils.py:176` — `FuncRegistryUtils._find_functions_in_module` — `def _find_functions_in_module(cls, module: Any) -> list[Callable[..., Any]]`
- `pipelex/system/registries/func_registry_utils.py:211` — `FuncRegistryUtils._get_function_registration_name` — `def _get_function_registration_name(cls, func: Callable[..., Any]) -> str`
- `pipelex/system/registries/singleton.py:21` — `MetaSingleton.clear_subclass_instances` — `def clear_subclass_instances(cls, base_cls: type[Any]) -> None`
- `pipelex/system/registries/singleton.py:28` — `MetaSingleton.get_subclass_instance` — `def get_subclass_instance(cls, base_cls: type[T]) -> T | None`
- `pipelex/system/runtime.py:100` — `RuntimeManager.set_run_mode` — `def set_run_mode(self, run_mode: RunMode)`
- `pipelex/system/runtime.py:103` — `RuntimeManager.set_worker_mode` — `def set_worker_mode(self, worker_mode: WorkerMode)`
- `pipelex/system/telemetry/exception_capture.py:56` — `DualClientExceptionCapture._thread_exception_handler` — `def _thread_exception_handler(self, args: threading.ExceptHookArgs) -> None`
- `pipelex/system/telemetry/exception_capture.py:62` — `DualClientExceptionCapture._capture_exception` — `def _capture_exception(self, exc_info: tuple[type[BaseException], BaseException | None, TracebackType | None]) -> None`
- `pipelex/system/telemetry/otel_constants.py:93` — `make_otel_gen_ai_output_type` — `def make_otel_gen_ai_output_type(output_type: str) -> otel_gen_ai_attributes.GenAiOutputTypeValues`
- `pipelex/system/telemetry/otel_factory.py:48` — `OtelFactory.stringify_json` — `def stringify_json(cls, json_conent: JsonContent) -> str`
- `pipelex/system/telemetry/otel_factory.py:118` — `OtelFactory.make_trace_id` — `def make_trace_id(cls, pipeline_run_id: str) -> int`
- `pipelex/system/telemetry/otel_factory.py:151` — `OtelFactory._is_unresolved_placeholder` — `def _is_unresolved_placeholder(cls, value: str | None) -> bool`
- `pipelex/system/telemetry/otel_factory.py:156` — `OtelFactory.make_langfuse_exporter` — `def make_langfuse_exporter(cls, langfuse_config: LangfuseConfig) -> 'OTLPSpanExporter'`
- `pipelex/system/telemetry/posthog_span_exporter.py:64` — `PostHogSpanExporter._truncate_content` — `def _truncate_content(self, content: str) -> str`
- `pipelex/system/telemetry/posthog_span_exporter.py:80` — `PostHogSpanExporter._apply_content_redaction` — `def _apply_content_redaction(self, properties: dict[str, Any]) -> None`
- `pipelex/system/telemetry/posthog_span_exporter.py:172` — `PostHogSpanExporter._get_redacted_pipe_code` — `def _get_redacted_pipe_code(self, pipe_code: str | None) -> str | None`
- `pipelex/system/telemetry/posthog_span_exporter.py:185` — `PostHogSpanExporter._get_redacted_output_class_name` — `def _get_redacted_output_class_name(self, output_class_name: str | None) -> str | None`
- `pipelex/system/telemetry/posthog_span_exporter.py:337` — `PostHogSpanExporter._do_export` — `def _do_export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult`
- `pipelex/system/telemetry/telemetry_config.py:182` — `TelemetryConfig.is_custom_telemetry_allowed_for_mode` — `def is_custom_telemetry_allowed_for_mode(self, mode: str) -> bool`
- `pipelex/system/telemetry/telemetry_config.py:214` — `TelemetryRedactionConfig.make_from_posthog_config` — `def make_from_posthog_config(cls, posthog_config: PostHogConfig | None) -> Self`
- `pipelex/system/telemetry/telemetry_config.py:239` — `load_telemetry_config` — `def load_telemetry_config(secrets_provider: SecretsProviderAbstract) -> TelemetryConfig`
- `pipelex/system/telemetry/telemetry_manager.py:155` — `TelemetryManager._wrap_capture_exception` — `def _wrap_capture_exception(self, client: Posthog) -> None`
- `pipelex/system/telemetry/telemetry_manager.py:163` — `TelemetryManager._wrap_capture_exception.sanitized_capture_exception` — `def sanitized_capture_exception(exception: ExceptionArg | None=None, **kwargs: Unpack[OptionalCaptureArgs]) -> Any`
- `pipelex/system/telemetry/telemetry_manager_abstract.py:89` — `TelemetryManagerAbstract.setup` — `def setup(self, integration_mode: IntegrationMode)`
- `pipelex/system/telemetry/telemetry_manager_abstract.py:106` — `TelemetryManagerAbstract.is_custom_portkey_logging_enabled` — `def is_custom_portkey_logging_enabled(self, is_debug_configured: bool) -> bool`
- `pipelex/system/telemetry/telemetry_manager_abstract.py:114` — `TelemetryManagerAbstract.is_pipelex_gateway_portkey_logging_enabled` — `def is_pipelex_gateway_portkey_logging_enabled(self, is_debug_configured: bool) -> bool`

### `temporal` (48)

- `pipelex/temporal/codec/codec_server.py:39` — `_make_cors_handler` — `def _make_cors_handler(cors_origins: list[str]) -> Callable[[web.Request], Awaitable[web.Response]]`
- `pipelex/temporal/codec/codec_server.py:42` — `_make_cors_handler.cors_options` — `async def cors_options(request: web.Request) -> web.Response`
- `pipelex/temporal/codec/storage_payload_codec.py:49` — `StoragePayloadCodec._extract_job_routing` — `def _extract_job_routing(payload: Payload) -> tuple[str, str] | None`
- `pipelex/temporal/codec/storage_payload_codec.py:75` — `StoragePayloadCodec._sanitize_path_segment` — `def _sanitize_path_segment(segment: str) -> str`
- `pipelex/temporal/config_temporal.py:192` — `RetryPolicyConfigBase.make_retry_policy` — `def make_retry_policy(self, merged_non_retryable_types: list[str]) -> 'RetryPolicy'`
- `pipelex/temporal/config_temporal.py:445` — `WorkerConfig.all_non_retryable_error_types` — `def all_non_retryable_error_types(self, queue_options_by_queue: dict[str, 'QueueOptions']) -> set[str]`
- `pipelex/temporal/config_temporal.py:731` — `Temporal.validate_task_queue_known` — `def validate_task_queue_known(self, task_queue: str) -> None`
- `pipelex/temporal/log_temporal.py:64` — `_RequestIdLog.verbose` — `def verbose(self, content: Union[str, Any]) -> None`
- `pipelex/temporal/log_temporal.py:67` — `_RequestIdLog.debug` — `def debug(self, content: Union[str, Any]) -> None`
- `pipelex/temporal/log_temporal.py:70` — `_RequestIdLog.dev` — `def dev(self, content: Union[str, Any]) -> None`
- `pipelex/temporal/log_temporal.py:73` — `_RequestIdLog.info` — `def info(self, content: Union[str, Any]) -> None`
- `pipelex/temporal/log_temporal.py:76` — `_RequestIdLog.warning` — `def warning(self, content: Union[str, Any]) -> None`
- `pipelex/temporal/log_temporal.py:79` — `_RequestIdLog.error` — `def error(self, content: Union[str, Any]) -> None`
- `pipelex/temporal/log_temporal.py:82` — `_RequestIdLog.critical` — `def critical(self, content: Union[str, Any]) -> None`
- `pipelex/temporal/sandbox_manager.py:9` — `SandboxManager.set_sandbox_callable` — `def set_sandbox_callable(self, sandbox_callable: Callable[[], bool])`
- `pipelex/temporal/temporal_connect.py:83` — `connect_to_temporal_selected_server` — `async def connect_to_temporal_selected_server(selected_server_config: str) -> TemporalClient`
- `pipelex/temporal/temporal_data_converter.py:57` — `BaseModelPayloadConverter._is_kajson_wire_value` — `def _is_kajson_wire_value(cls, value: object) -> bool`
- `pipelex/temporal/temporal_data_converter.py:79` — `BaseModelPayloadConverter._first_kajson_list_element` — `def _first_kajson_list_element(cls, value: object) -> object | None`
- `pipelex/temporal/temporal_data_converter.py:101` — `BaseModelPayloadConverter._kajson_deserialize_from_payload` — `def _kajson_deserialize_from_payload(self, payload: Payload) -> Any`
- `pipelex/temporal/temporal_data_converter.py:133` — `BaseModelPayloadConverter._is_kajson_type` — `def _is_kajson_type(cls, type_hint: Any) -> bool`
- `pipelex/temporal/temporal_data_converter.py:145` — `BaseModelPayloadConverter._unwrap_optional_kajson_type` — `def _unwrap_optional_kajson_type(cls, type_hint: type[Any] | None) -> bool`
- `pipelex/temporal/temporal_data_converter.py:200` — `make_data_converter` — `def make_data_converter(payload_codec: PayloadCodec | None=None) -> DataConverter`
- `pipelex/temporal/temporal_hub.py:20` — `TemporalHub.set_task_manager` — `def set_task_manager(self, task_manager: TaskManager)`
- `pipelex/temporal/temporal_manager.py:37` — `TemporalManager.setup` — `def setup(cls, session_id: str) -> None`
- `pipelex/temporal/temporal_manager.py:86` — `TemporalManager.get_temporal_client` — `async def get_temporal_client(self, should_auto_connect: bool) -> TemporalClient`
- `pipelex/temporal/temporal_manager.py:95` — `TemporalManager.make_top_workflow_id` — `def make_top_workflow_id(self, pipeline_run_id: str) -> str`
- `pipelex/temporal/temporal_manager.py:115` — `get_temporal_client` — `async def get_temporal_client(should_auto_connect: bool) -> TemporalClient`
- `pipelex/temporal/temporal_task_manager.py:236` — `TemporalTaskManager._resolve_scope_by_name` — `def _resolve_scope_by_name(scope_name: str | None) -> WorkerScope`
- `pipelex/temporal/temporal_task_manager.py:245` — `TemporalTaskManager._resolve_runtime_profile_by_name` — `def _resolve_runtime_profile_by_name(profile_name: str | None) -> WorkerRuntimeProfile`
- `pipelex/temporal/test_extras/wf_test_structured_output_cross_process.py:65` — `_assert_invoice_round_trip` — `def _assert_invoice_round_trip(invoice: FixtureInvoice) -> None`
- `pipelex/temporal/test_extras/wf_test_structured_output_cross_process.py:101` — `_assert_invoice_list_round_trip` — `def _assert_invoice_list_round_trip(invoices: list[FixtureInvoice]) -> None`
- `pipelex/temporal/test_helpers/temporal_pytest_plugins.py:11` — `pytest_addoption` — `def pytest_addoption(parser: Parser)`
- `pipelex/temporal/tprl/activity_error_boundary.py:25` — `convert_pipelex_errors` — `def convert_pipelex_errors(func: Callable[_ActivityParams, Awaitable[_ActivityReturn]]) -> Callable[_ActivityParams, Awaitable[_ActivityReturn]]`
- `pipelex/temporal/tprl/conditional_worker.py:17` — `with_conditional_worker` — `def with_conditional_worker(execute_workflow: FuncExecuteWorkflow) -> FuncExecuteWorkflow`
- `pipelex/temporal/tprl/observability.py:64` — `stamp_submitter_session_id` — `def stamp_submitter_session_id(pipe_job: PipeJob) -> PipeJob`
- `pipelex/temporal/tprl/observability.py:85` — `build_search_attributes` — `def build_search_attributes(pipe_job: PipeJob) -> TypedSearchAttributes`
- `pipelex/temporal/tprl/observability.py:124` — `build_static_summary` — `def build_static_summary(pipe: PipeAbstract) -> str`
- `pipelex/temporal/tprl/observability.py:137` — `build_static_details` — `def build_static_details(pipe_job: PipeJob) -> str`
- `pipelex/temporal/tprl/temporal_error.py:25` — `error_report_dict_from_details` — `def error_report_dict_from_details(details: Sequence[Any]) -> dict[str, Any] | None`
- `pipelex/temporal/tprl/temporal_error.py:41` — `_find_error_report_dict` — `def _find_error_report_dict(exc: BaseException) -> dict[str, Any] | None`
- `pipelex/temporal/tprl/temporal_error.py:64` — `_message_from_exc` — `def _message_from_exc(exc: BaseException) -> str`
- `pipelex/temporal/tprl/temporal_error.py:85` — `recover_error_report` — `def recover_error_report(exc: BaseException) -> ErrorReport`
- `pipelex/temporal/tprl/temporal_error.py:168` — `TemporalError._log_critical` — `def _log_critical(cls, message: str) -> None`
- `pipelex/temporal/tprl/temporal_error.py:181` — `TemporalError._log_error` — `def _log_error(cls, message: str) -> None`
- `pipelex/temporal/tprl/temporal_error.py:192` — `TemporalError._error_type_in_name_list` — `def _error_type_in_name_list(cls, error_type: str | None) -> bool`
- `pipelex/temporal/tprl/temporal_error.py:205` — `TemporalError.from_app_error` — `def from_app_error(cls, exc: ApplicationError) -> Self`
- `pipelex/temporal/tprl/workflow_caller.py:86` — `WorkflowExecutor.make_workflow_id` — `def make_workflow_id(self, pipeline_run_id: str) -> str`
- `pipelex/temporal/tprl_pipe/wf_pipe_router.py:25` — `_carries_temporal_failure` — `def _carries_temporal_failure(exc: BaseException) -> bool`

### `test_extras` (6)

- `pipelex/test_extras/shared_pytest_plugins.py:69` — `pytest_addoption` — `def pytest_addoption(parser: Parser)`
- `pipelex/test_extras/shared_pytest_plugins.py:93` — `pytest_configure` — `def pytest_configure(config: Config) -> None`
- `pipelex/test_extras/shared_pytest_plugins.py:151` — `_setup_env_var_placeholders` — `def _setup_env_var_placeholders(env_var_keys: list[str]) -> None`
- `pipelex/test_extras/shared_pytest_plugins.py:174` — `_cleanup_placeholder_env_vars` — `def _cleanup_placeholder_env_vars(env_var_keys: list[str]) -> None`
- `pipelex/test_extras/shared_pytest_plugins.py:230` — `needs_inference_in_pipelex` — `def needs_inference_in_pipelex(request: FixtureRequest) -> bool`
- `pipelex/test_extras/shared_pytest_plugins.py:256` — `is_inference_disabled_in_pipelex` — `def is_inference_disabled_in_pipelex(request: FixtureRequest) -> bool`

### `tools` (165)

- `pipelex/tools/aws/aws_config.py:37` — `AwsConfig.get_aws_access_keys_with_method` — `def get_aws_access_keys_with_method(self, api_key_method: AwsKeyMethod) -> tuple[str, str, str]`
- `pipelex/tools/jinja2/image_registry.py:27` — `ImageRegistry.register_image` — `def register_image(self, image: Any) -> int`
- `pipelex/tools/jinja2/image_registry.py:48` — `ImageRegistry.get_image_placeholder` — `def get_image_placeholder(self, image: Any) -> str | None`
- `pipelex/tools/jinja2/image_registry.py:74` — `ImageRegistry.make_finalize.finalize` — `def finalize(value: Any) -> Any`
- `pipelex/tools/jinja2/jinja2_filters.py:139` — `escape_script_tag` — `def escape_script_tag(value: Any) -> Any`
- `pipelex/tools/jinja2/jinja2_required_variables.py:32` — `_build_full_path` — `def _build_full_path(node: nodes.Node) -> str | None`
- `pipelex/tools/jinja2/jinja2_required_variables.py:50` — `_collect_declarations_from_body` — `def _collect_declarations_from_body(body: list[nodes.Node]) -> set[str]`
- `pipelex/tools/jinja2/jinja2_required_variables.py:163` — `_extract_filters_and_variable` — `def _extract_filters_and_variable(node: nodes.Node) -> tuple[list[str], nodes.Node | None]`
- `pipelex/tools/jinja2/jinja2_template_loader.py:117` — `TemplateLoader.load` — `def load(cls, name: str) -> None`
- `pipelex/tools/jinja2/jinja2_template_loader.py:157` — `TemplateLoader.reload` — `def reload(cls, name: str | None=None) -> None`
- `pipelex/tools/jinja2/jinja2_template_loader.py:173` — `TemplateLoader.is_loaded` — `def is_loaded(cls, name: str) -> bool`
- `pipelex/tools/jinja2/jinja2_template_registry.py:47` — `TemplateRegistry.get` — `def get(cls, key: str) -> str`
- `pipelex/tools/jinja2/jinja2_template_registry.py:77` — `TemplateRegistry.is_registered` — `def is_registered(cls, key: str) -> bool`
- `pipelex/tools/jinja2/text_format_renderable.py:32` — `TextFormatRenderable.rendered_for_template_async` — `async def rendered_for_template_async(self, text_format: TextFormat) -> str`
- `pipelex/tools/log/log.py:28` — `Log.set_log_mode` — `def set_log_mode(self, mode: LogMode)`
- `pipelex/tools/log/log.py:73` — `Log.configure_if_unset` — `def configure_if_unset(self, log_config: LogConfig) -> bool`
- `pipelex/tools/log/log.py:92` — `Log.configure` — `def configure(self, log_config: LogConfig)`
- `pipelex/tools/log/log.py:131` — `Log.set_poor_log_formatter` — `def set_poor_log_formatter(self, formatter: logging.Formatter)`
- `pipelex/tools/log/log.py:143` — `Log._should_ignore` — `def _should_ignore(self, problem_id: str | None=None) -> bool`
- `pipelex/tools/log/log.py:170` — `Log.set_level_by_int` — `def set_level_by_int(self, level_int: int)`
- `pipelex/tools/log/log.py:179` — `Log.set_level_by_name` — `def set_level_by_name(self, level_name: str)`
- `pipelex/tools/log/log.py:194` — `Log.set_level` — `def set_level(self, level: LogLevel)`
- `pipelex/tools/log/log.py:214` — `Log.set_levels_for_packages` — `def set_levels_for_packages(self, package_log_levels: dict[str, LogLevel])`
- `pipelex/tools/log/log_config.py:41` — `CallerInfoTemplate.for_template_key` — `def for_template_key(cls, key: CallerInfoTemplate) -> str`
- `pipelex/tools/log/log_config.py:71` — `RichLogConfig.make_rich_handler` — `def make_rich_handler(self, target: ConsoleTarget) -> RichHandler`
- `pipelex/tools/log/log_dispatch.py:23` — `LogDispatch.set_log_mode` — `def set_log_mode(self, mode: LogMode)`
- `pipelex/tools/log/log_dispatch.py:46` — `LogDispatch.configure` — `def configure(self, log_config: LogConfig)`
- `pipelex/tools/log/log_formatter.py:10` — `emoji_for_channel` — `def emoji_for_channel(channel_name: str) -> str | None`
- `pipelex/tools/log/log_levels.py:47` — `LogLevel.from_int` — `def from_int(logging_level: int) -> 'LogLevel'`
- `pipelex/tools/mermaid/mermaid_utils.py:32` — `encode_pako_from_bytes` — `def encode_pako_from_bytes(state_bytes: bytes) -> str`
- `pipelex/tools/mermaid/mermaid_utils.py:39` — `encode_pako_from_string` — `def encode_pako_from_string(state: str) -> str`
- `pipelex/tools/mermaid/mermaid_utils.py:45` — `make_mermaid_url` — `def make_mermaid_url(mermaid_code: str) -> str`
- `pipelex/tools/mermaid/mermaid_utils.py:80` — `clean_str_for_mermaid_node_title` — `def clean_str_for_mermaid_node_title(text: str) -> str`
- `pipelex/tools/mermaid/mermaid_utils.py:97` — `sanitize_mermaid_id` — `def sanitize_mermaid_id(node_id: str) -> str`
- `pipelex/tools/mermaid/mermaid_utils.py:114` — `escape_mermaid_label` — `def escape_mermaid_label(label: str) -> str`
- `pipelex/tools/misc/async_utils.py:8` — `_invoke` — `async def _invoke(factory: Callable[[], Awaitable[_T]]) -> _T`
- `pipelex/tools/misc/attribute_utils.py:26` — `AttributePolisher.should_truncate` — `def should_truncate(cls, value: Any) -> bool`
- `pipelex/tools/misc/attribute_utils.py:39` — `AttributePolisher.get_truncated_value` — `def get_truncated_value(cls, value: Any) -> Any`
- `pipelex/tools/misc/attribute_utils.py:53` — `AttributePolisher._looks_like_base64` — `def _looks_like_base64(cls, value: str) -> bool`
- `pipelex/tools/misc/base64_utils.py:9` — `load_binary_as_base64` — `async def load_binary_as_base64(path: Path) -> str`
- `pipelex/tools/misc/base64_utils.py:15` — `make_base64_url_from_path` — `async def make_base64_url_from_path(path: Path) -> str`
- `pipelex/tools/misc/base64_utils.py:23` — `make_base64_url_from_http_url` — `async def make_base64_url_from_http_url(url: str) -> str`
- `pipelex/tools/misc/base64_utils.py:31` — `make_base64_url_from_bytes` — `def make_base64_url_from_bytes(raw_bytes: bytes) -> str`
- `pipelex/tools/misc/base64_utils.py:47` — `is_prefixed_base64_url` — `def is_prefixed_base64_url(possibly_base64_url: str) -> bool`
- `pipelex/tools/misc/base64_utils.py:51` — `strip_base64_str_if_needed` — `def strip_base64_str_if_needed(base64_str: str) -> str`
- `pipelex/tools/misc/base64_utils.py:59` — `extract_base64_str_from_base64_url_if_possible` — `def extract_base64_str_from_base64_url_if_possible(possibly_base64_url: str) -> tuple[str, str] | None`
- `pipelex/tools/misc/dict_utils.py:173` — `extract_vars_from_strings_recursive` — `def extract_vars_from_strings_recursive(data: Any) -> set[str]`
- `pipelex/tools/misc/dict_utils.py:194` — `extract_vars_from_strings_recursive.extract_from_string` — `def extract_from_string(text: str) -> None`
- `pipelex/tools/misc/dict_utils.py:221` — `extract_vars_from_strings_recursive.traverse` — `def traverse(value: Any) -> None`
- `pipelex/tools/misc/diff.py:44` — `has_diff_dirs._filter_excluded_files` — `def _filter_excluded_files(file_list: list[str]) -> list[str]`
- `pipelex/tools/misc/diff.py:47` — `has_diff_dirs._has_diff` — `def _has_diff(dir_comparison: filecmp.dircmp[str]) -> bool`
- `pipelex/tools/misc/diff.py:238` — `make_diff_dirs_pretty._filter_excluded_files` — `def _filter_excluded_files(file_list: list[str]) -> list[str]`
- `pipelex/tools/misc/document_utils.py:59` — `DocumentFormat.is_supported_mime_type` — `def is_supported_mime_type(cls, mime_type: str) -> bool`
- `pipelex/tools/misc/document_utils.py:64` — `DocumentFormat.raise_if_unsupported_mime_type` — `def raise_if_unsupported_mime_type(cls, mime_type: str) -> None`
- `pipelex/tools/misc/document_utils.py:79` — `DocumentFormat.from_mime_type` — `def from_mime_type(cls, mime_type: str) -> 'DocumentFormat'`
- `pipelex/tools/misc/exceptions.py:36` — `TomlError.from_tomli_error` — `def from_tomli_error(cls, exc: tomli.TOMLDecodeError) -> Self`
- `pipelex/tools/misc/file_utils.py:82` — `load_text_from_path` — `def load_text_from_path(path: Path) -> str`
- `pipelex/tools/misc/file_utils.py:101` — `failable_load_text_from_path` — `def failable_load_text_from_path(path: Path) -> str | None`
- `pipelex/tools/misc/file_utils.py:119` — `load_binary` — `def load_binary(path: Path) -> bytes`
- `pipelex/tools/misc/file_utils.py:123` — `load_binary_async` — `async def load_binary_async(path: Path) -> bytes`
- `pipelex/tools/misc/file_utils.py:217` — `remove_file` — `def remove_file(file_path: Path)`
- `pipelex/tools/misc/file_utils.py:234` — `remove_folder` — `def remove_folder(folder_path: Path) -> None`
- `pipelex/tools/misc/file_utils.py:273` — `_reraise_walk_error` — `def _reraise_walk_error(walk_error: OSError) -> None`
- `pipelex/tools/misc/file_utils.py:406` — `ensure_directory_exists` — `def ensure_directory_exists(directory_path: Path) -> None`
- `pipelex/tools/misc/file_utils.py:416` — `ensure_path` — `def ensure_path(path: Path) -> bool`
- `pipelex/tools/misc/file_utils.py:435` — `ensure_directory_for_file_path` — `def ensure_directory_for_file_path(file_path: Path) -> None`
- `pipelex/tools/misc/file_utils.py:444` — `path_exists` — `def path_exists(path_str: str | Path) -> bool`
- `pipelex/tools/misc/filetype_utils.py:38` — `detect_file_type_from_path` — `def detect_file_type_from_path(path: Path) -> FileType`
- `pipelex/tools/misc/filetype_utils.py:60` — `detect_file_type_from_bytes` — `def detect_file_type_from_bytes(raw_bytes: bytes) -> FileType`
- `pipelex/tools/misc/filetype_utils.py:82` — `detect_file_type_from_base64` — `def detect_file_type_from_base64(base64_data: str | bytes) -> FileType`
- `pipelex/tools/misc/filetype_utils.py:115` — `mime_type_to_extension` — `def mime_type_to_extension(mime_type: str) -> str`
- `pipelex/tools/misc/hash_utils.py:24` — `hash_md5_to_int` — `def hash_md5_to_int(string: str) -> int`
- `pipelex/tools/misc/http_utils.py:24` — `validate_url_resource_exists` — `def validate_url_resource_exists(url: str) -> None`
- `pipelex/tools/misc/http_utils.py:50` — `_validate_http_url` — `def _validate_http_url(url: str) -> None`
- `pipelex/tools/misc/http_utils.py:80` — `_validate_local_path` — `def _validate_local_path(url: str) -> None`
- `pipelex/tools/misc/image_utils.py:58` — `ImageFormat.from_mime_type` — `def from_mime_type(cls, mime_type: str) -> 'ImageFormat'`
- `pipelex/tools/misc/image_utils.py:72` — `ImageFormat.is_supported_mime_type` — `def is_supported_mime_type(cls, mime_type: str) -> bool`
- `pipelex/tools/misc/image_utils.py:77` — `ImageFormat.raise_if_unsupported_mime_type` — `def raise_if_unsupported_mime_type(cls, mime_type: str) -> None`
- `pipelex/tools/misc/json_utils.py:23` — `clean_json_content` — `def clean_json_content(content: Any) -> Any`
- `pipelex/tools/misc/json_utils.py:156` — `load_json_from_path` — `def load_json_from_path(path: Path) -> JsonContent`
- `pipelex/tools/misc/json_utils.py:177` — `load_json_dict_from_path` — `def load_json_dict_from_path(path: Path) -> dict[str, Any]`
- `pipelex/tools/misc/json_utils.py:202` — `load_json_list_from_path` — `def load_json_list_from_path(path: Path) -> list[Any]`
- `pipelex/tools/misc/json_utils.py:262` — `remove_none_values` — `def remove_none_values(json_content: JsonContent | Any) -> JsonContent | Any`
- `pipelex/tools/misc/json_utils.py:307` — `remove_none_values_from_dict` — `def remove_none_values_from_dict(data: Mapping[str, Any]) -> dict[str, Any]`
- `pipelex/tools/misc/placeholder.py:4` — `make_placeholder_value` — `def make_placeholder_value(key: str) -> str`
- `pipelex/tools/misc/placeholder.py:17` — `value_is_placeholder` — `def value_is_placeholder(value: str | None) -> bool`
- `pipelex/tools/misc/semver.py:18` — `parse_version` — `def parse_version(version_str: str) -> Version`
- `pipelex/tools/misc/semver.py:40` — `parse_constraint` — `def parse_constraint(constraint_str: str) -> SimpleSpec`
- `pipelex/tools/misc/semver.py:119` — `parse_version_tag` — `def parse_version_tag(tag: str) -> Version | None`
- `pipelex/tools/misc/string_utils.py:6` — `has_text` — `def has_text(text: str) -> bool`
- `pipelex/tools/misc/string_utils.py:22` — `is_none_or_has_text` — `def is_none_or_has_text(text: str | None) -> bool`
- `pipelex/tools/misc/string_utils.py:39` — `can_inject_text` — `def can_inject_text(value: Any | None) -> bool`
- `pipelex/tools/misc/string_utils.py:63` — `is_not_none_and_has_text` — `def is_not_none_and_has_text(text: str | None) -> bool`
- `pipelex/tools/misc/string_utils.py:80` — `camel_to_snake_case` — `def camel_to_snake_case(name: str) -> str`
- `pipelex/tools/misc/string_utils.py:101` — `pascal_case_to_snake_case` — `def pascal_case_to_snake_case(name: str) -> str`
- `pipelex/tools/misc/string_utils.py:121` — `pascal_case_to_kebab` — `def pascal_case_to_kebab(name: str) -> str`
- `pipelex/tools/misc/string_utils.py:158` — `pascal_case_to_sentence` — `def pascal_case_to_sentence(name: str) -> str`
- `pipelex/tools/misc/string_utils.py:199` — `snake_to_pascal_case` — `def snake_to_pascal_case(snake_str: str) -> str`
- `pipelex/tools/misc/string_utils.py:220` — `snake_to_capitalize_first_letter` — `def snake_to_capitalize_first_letter(snake_str: str) -> str`
- `pipelex/tools/misc/string_utils.py:242` — `snake_to_title_case` — `def snake_to_title_case(snake_str: str) -> str`
- `pipelex/tools/misc/string_utils.py:262` — `is_snake_case` — `def is_snake_case(word: str) -> bool`
- `pipelex/tools/misc/string_utils.py:266` — `is_pascal_case` — `def is_pascal_case(word: str) -> bool`
- `pipelex/tools/misc/string_utils.py:270` — `normalize_to_ascii` — `def normalize_to_ascii(text: str) -> str`
- `pipelex/tools/misc/string_utils.py:309` — `get_root_from_dotted_path` — `def get_root_from_dotted_path(dotted_path: str) -> str`
- `pipelex/tools/misc/tenacity_utils.py:6` — `log_retry` — `def log_retry(retry_state: RetryCallState) -> None`
- `pipelex/tools/misc/toml_utils.py:17` — `load_toml_from_content` — `def load_toml_from_content(content: str) -> dict[str, Any]`
- `pipelex/tools/misc/toml_utils.py:25` — `load_toml_from_path` — `def load_toml_from_path(path: str | Path) -> dict[str, Any]`
- `pipelex/tools/misc/toml_utils.py:46` — `load_toml_from_path_if_exists` — `def load_toml_from_path_if_exists(path: str | Path) -> dict[str, Any] | None`
- `pipelex/tools/misc/toml_utils.py:53` — `load_toml_with_tomlkit` — `def load_toml_with_tomlkit(path: str | Path) -> tomlkit.TOMLDocument`
- `pipelex/tools/misc/toml_utils.py:79` — `load_toml_from_path_and_merge_with_overrides` — `def load_toml_from_path_and_merge_with_overrides(paths: Sequence[str | Path]) -> dict[str, Any]`
- `pipelex/tools/network/host_rules.py:19` — `is_disallowed_ip` — `def is_disallowed_ip(host: str) -> bool`
- `pipelex/tools/network/host_rules.py:43` — `is_disallowed_host` — `def is_disallowed_host(host: str) -> bool`
- `pipelex/tools/pdf/pypdfium2_renderer.py:41` — `_resolve_pdf_uri_to_input` — `async def _resolve_pdf_uri_to_input(pdf_uri: str) -> PdfInput`
- `pipelex/tools/pdf/pypdfium2_renderer.py:178` — `PyPdfium2Renderer._extract_text_from_pdf_pages_sync` — `def _extract_text_from_pdf_pages_sync(pdf_input: PdfInput) -> list[str]`
- `pipelex/tools/pdf/pypdfium2_renderer.py:273` — `PyPdfium2Renderer.extract_text_from_pdf_pages` — `async def extract_text_from_pdf_pages(self, pdf_input: PdfInput) -> list[str]`
- `pipelex/tools/pdf/pypdfium2_renderer.py:282` — `PyPdfium2Renderer.extract_text_from_pdf_pages_from_uri` — `async def extract_text_from_pdf_pages_from_uri(self, pdf_uri: str) -> list[str]`
- `pipelex/tools/secrets/secrets_provider_abstract.py:8` — `SecretsProviderAbstract.get_required_secret` — `def get_required_secret(self, secret_id: str) -> str`
- `pipelex/tools/secrets/secrets_provider_abstract.py:11` — `SecretsProviderAbstract.get_optional_secret` — `def get_optional_secret(self, secret_id: str) -> str | None`
- `pipelex/tools/secrets/secrets_provider_abstract.py:22` — `SecretsProviderAbstract.get_secret` — `def get_secret(self, secret_id: str) -> str`
- `pipelex/tools/secrets/secrets_utils.py:51` — `substitute_vars.replace_var` — `def replace_var(match: re.Match[str]) -> str`
- `pipelex/tools/secrets/secrets_utils.py:130` — `_get_env_var` — `def _get_env_var(var_name: str) -> str`
- `pipelex/tools/storage/gcp_storage_provider.py:84` — `GcpStorageProvider._load_with_metadata_sync` — `def _load_with_metadata_sync(self, key: str) -> StoredData`
- `pipelex/tools/storage/gcp_storage_provider.py:170` — `GcpStorageProvider._make_public_url` — `def _make_public_url(self, key: str) -> str`
- `pipelex/tools/storage/gcp_storage_provider.py:181` — `GcpStorageProvider._generate_signed_url_sync` — `def _generate_signed_url_sync(self, key: str) -> str | None`
- `pipelex/tools/storage/local_storage_provider.py:26` — `LocalStorageProvider._validate_key` — `def _validate_key(self, key: str) -> Path`
- `pipelex/tools/storage/s3_storage_provider.py:176` — `S3StorageProvider._make_public_url` — `def _make_public_url(self, key: str) -> str`
- `pipelex/tools/storage/storage_provider_abstract.py:28` — `StorageProviderAbstract._strip_scheme` — `def _strip_scheme(self, uri: str) -> str`
- `pipelex/tools/storage/storage_provider_abstract.py:45` — `StorageProviderAbstract._add_scheme` — `def _add_scheme(self, key: str) -> str`
- `pipelex/tools/storage/storage_provider_abstract.py:62` — `StorageProviderAbstract.load` — `async def load(self, uri: str) -> bytes`
- `pipelex/tools/storage/storage_provider_abstract.py:74` — `StorageProviderAbstract.load_with_metadata` — `async def load_with_metadata(self, uri: str) -> StoredData`
- `pipelex/tools/storage/storage_provider_abstract.py:87` — `StorageProviderAbstract._load_with_metadata` — `async def _load_with_metadata(self, key: str) -> StoredData`
- `pipelex/tools/storage/storage_provider_abstract.py:123` — `StorageProviderAbstract.public_url` — `async def public_url(self, uri: str) -> str | None`
- `pipelex/tools/storage/storage_provider_factory.py:14` — `make_storage_provider_from_config` — `def make_storage_provider_from_config(storage_provider_config: StorageProviderConfig) -> StorageProviderAbstract`
- `pipelex/tools/tabular/csv_codec.py:60` — `_is_flat_annotation` — `def _is_flat_annotation(annotation: Any) -> bool`
- `pipelex/tools/tabular/csv_codec.py:86` — `_annotation_allows_none` — `def _annotation_allows_none(annotation: Any) -> bool`
- `pipelex/tools/tabular/csv_codec.py:93` — `flat_field_names` — `def flat_field_names(row_model: type[StuffContent]) -> list[str]`
- `pipelex/tools/tabular/csv_codec.py:120` — `_assert_single_char_delimiter` — `def _assert_single_char_delimiter(delimiter: str) -> None`
- `pipelex/tools/tabular/csv_codec.py:275` — `is_tabular_path` — `def is_tabular_path(path: Path) -> bool`
- `pipelex/tools/tabular/csv_codec.py:287` — `assert_supported_table_suffix` — `def assert_supported_table_suffix(path: Path) -> None`
- `pipelex/tools/tabular/csv_codec.py:407` — `_validation_error_label` — `def _validation_error_label(error: 'ErrorDetails') -> str`
- `pipelex/tools/tabular/csv_codec.py:419` — `_to_cell` — `def _to_cell(value: Any) -> str`
- `pipelex/tools/typing/class_utils.py:14` — `normalize_property_for_comparison` — `def normalize_property_for_comparison(prop: dict[str, Any]) -> dict[str, Any]`
- `pipelex/tools/typing/class_utils.py:46` — `normalize_properties_for_comparison` — `def normalize_properties_for_comparison(properties: dict[str, Any]) -> dict[str, Any]`
- `pipelex/tools/typing/class_utils.py:129` — `has_compatible_field._is_compatible` — `def _is_compatible(type_param: Any) -> bool`
- `pipelex/tools/typing/module_inspector.py:11` — `import_module_from_file` — `def import_module_from_file(file_path: Path) -> Any`
- `pipelex/tools/typing/module_inspector.py:58` — `convert_file_path_to_module_path` — `def convert_file_path_to_module_path(file_path: Path) -> str`
- `pipelex/tools/typing/pydantic_utils.py:24` — `empty_list_factory_of` — `def empty_list_factory_of(_: type[T]) -> Callable[[], list[T]]`
- `pipelex/tools/typing/pydantic_utils.py:62` — `analyze_pydantic_validation_error` — `def analyze_pydantic_validation_error(exc: ValidationError) -> PydanticValidationErrorAnalysis`
- `pipelex/tools/typing/pydantic_utils.py:145` — `format_pydantic_validation_error` — `def format_pydantic_validation_error(exc: ValidationError) -> str`
- `pipelex/tools/typing/pydantic_utils.py:158` — `_serialize_input_value` — `def _serialize_input_value(value: Any) -> Any`
- `pipelex/tools/typing/pydantic_utils.py:180` — `_serialize_context` — `def _serialize_context(ctx: dict[str, Any]) -> dict[str, Any]`
- `pipelex/tools/typing/pydantic_utils.py:196` — `format_pydantic_validation_error_for_agent` — `def format_pydantic_validation_error_for_agent(exc: ValidationError) -> tuple[str, dict[str, Any]]`
- `pipelex/tools/typing/pydantic_utils.py:277` — `convert_strenum_to_str` — `def convert_strenum_to_str(obj: dict[str, Any] | list[Any] | StrEnum | Any) -> dict[str, Any] | list[Any] | str | Any`
- `pipelex/tools/typing/pydantic_utils.py:305` — `clean_model_to_dict` — `def clean_model_to_dict(obj: BaseModel) -> dict[str, Any]`
- `pipelex/tools/typing/pydantic_utils.py:409` — `_truncated_rich_repr_from_items` — `def _truncated_rich_repr_from_items(rich_repr_items: RichReprResult) -> RichReprResult`
- `pipelex/tools/typing/pydantic_utils.py:431` — `make_truncated_wrapper` — `def make_truncated_wrapper(model: BaseModel) -> Any`
- `pipelex/tools/typing/pydantic_utils.py:440` — `make_truncated_wrapper.rich_repr_method` — `def rich_repr_method(_self: Any) -> RichReprResult`
- `pipelex/tools/typing/structure_printer.py:32` — `StructurePrinter.pretty_type` — `def pretty_type(self, tp: object) -> str`
- `pipelex/tools/typing/structure_printer.py:95` — `StructurePrinter.get_type_structure.format_type` — `def format_type(tp: Any) -> str`
- `pipelex/tools/typing/structure_printer.py:137` — `StructurePrinter.get_type_structure.collect_types` — `def collect_types(tp: type[Any]) -> None`
- `pipelex/tools/uri/uri_resolver.py:23` — `extract_filename_from_uri` — `def extract_filename_from_uri(uri: str) -> str | None`
- `pipelex/tools/uri/uri_resolver.py:45` — `describe_uri` — `def describe_uri(uri: str) -> str`
- `pipelex/tools/uri/uri_resolver.py:58` — `resolve_uri` — `def resolve_uri(uri: str) -> ResolvedUri`
- `pipelex/tools/uri/uri_resolver.py:118` — `_resolve_file_uri` — `def _resolve_file_uri(uri: str) -> ResolvedLocalPath`
- `pipelex/tools/uri/uri_resolver.py:135` — `_resolve_base64_data_url` — `def _resolve_base64_data_url(uri: str) -> ResolvedBase64DataUrl`

### `tracing` (18)

- `pipelex/tracing/activity_event_log.py:44` — `ActivityEventLogCache.get_or_create` — `def get_or_create(cls, tracing_config: TracingConfig) -> EventLogProtocol | None`
- `pipelex/tracing/dynamodb_event_log.py:95` — `DynamoDBEventLog._make_pk` — `def _make_pk(pipeline_run_id: str) -> str`
- `pipelex/tracing/dynamodb_event_log.py:102` — `DynamoDBEventLog._key_condition` — `def _key_condition(self, pipeline_run_id: str) -> Any`
- `pipelex/tracing/event_log_protocol.py:54` — `EventLogProtocol.emit` — `def emit(self, event: TraceEvent) -> None`
- `pipelex/tracing/event_log_protocol.py:63` — `EventLogProtocol.read_events` — `def read_events(self, pipeline_run_id: str) -> list[TraceEvent]`
- `pipelex/tracing/event_log_protocol.py:79` — `EventLogProtocol.cleanup` — `def cleanup(self, pipeline_run_id: str) -> None`
- `pipelex/tracing/graphspec_assembler.py:163` — `_AssemblerState.pass_one` — `def pass_one(self, events: Sequence[TraceEvent]) -> None`
- `pipelex/tracing/graphspec_assembler.py:220` — `_AssemblerState._track_earliest_timestamp` — `def _track_earliest_timestamp(self, event: TraceEvent) -> None`
- `pipelex/tracing/graphspec_assembler.py:224` — `_AssemblerState._handle_pipe_start` — `def _handle_pipe_start(self, event: PipeStartEvent) -> None`
- `pipelex/tracing/graphspec_assembler.py:248` — `_AssemblerState._handle_pipe_end_success` — `def _handle_pipe_end_success(self, event: PipeEndSuccessEvent) -> None`
- `pipelex/tracing/graphspec_assembler.py:276` — `_AssemblerState._handle_pipe_end_error` — `def _handle_pipe_end_error(self, event: PipeEndErrorEvent) -> None`
- `pipelex/tracing/graphspec_assembler.py:286` — `_AssemblerState._handle_edge_event` — `def _handle_edge_event(self, event: EdgeEvent) -> None`
- `pipelex/tracing/graphspec_assembler.py:304` — `_AssemblerState._handle_controller_output` — `def _handle_controller_output(self, event: ControllerOutputEvent) -> None`
- `pipelex/tracing/graphspec_assembler.py:314` — `_AssemblerState._handle_execution_data` — `def _handle_execution_data(self, event: ExecutionDataEvent) -> None`
- `pipelex/tracing/graphspec_assembler.py:321` — `_AssemblerState._handle_batch_item` — `def _handle_batch_item(self, event: BatchItemEvent) -> None`
- `pipelex/tracing/graphspec_assembler.py:327` — `_AssemblerState._handle_batch_aggregate` — `def _handle_batch_aggregate(self, event: BatchAggregateEvent) -> None`
- `pipelex/tracing/graphspec_assembler.py:333` — `_AssemblerState._handle_parallel_combine` — `def _handle_parallel_combine(self, event: ParallelCombineEvent) -> None`
- `pipelex/tracing/usage_aggregator.py:13` — `UsageAggregator.aggregate` — `def aggregate(events: Sequence[TraceEvent]) -> list[AnyTokensUsage]`

## C. `SYMMETRIC_ALLOWLIST` — Exception 2

_Exception 2 — the curated symmetric-tuple allowlist (multiple positionals that read better ordered, e.g. `set_env(key, value)`)._

Count: 5

- `pipelex/kit/single_file_agent_rules.py:86` — `unified_diff` — `def unified_diff(before: str, after: str, path: str) -> str`
- `pipelex/system/environment.py:49` — `set_env` — `def set_env(key: str, value: str) -> None`
- `pipelex/tools/misc/diff.py:79` — `diff_files` — `def diff_files(path1: str | Path, path2: str | Path) -> str`
- `pipelex/tools/misc/diff.py:356` — `diff_dirs` — `def diff_dirs(dir1: str | Path, dir2: str | Path) -> None`
- `pipelex/tools/typing/class_utils.py:69` — `are_classes_equivalent` — `def are_classes_equivalent(class_1: type[Any], class_2: type[Any]) -> bool`

## D. `MULTI_POSITIONAL` — variadic wrapper

_Survives the guard with 2+ positionals or a `*args` — i.e. a variadic wrapper/closure, not a deliberate subject choice._

Count: 1

- `pipelex/temporal/tprl/conditional_worker.py:36` — `with_conditional_worker.wrapper` — `async def wrapper(self: WorkflowExecutor[WorkflowInput, WorkflowOutput], *args: Any, **kwargs: Any) -> Any`

