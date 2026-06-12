# TODOS — Test coverage grind

Source plan: [wip/tests/missing-tests-menu.md](wip/tests/missing-tests-menu.md). This file is the working plan; when a section is done, update the menu doc's matching section with the evolved coverage percentages. **ALL SECTIONS COMPLETE (2026-06-12):** A (CLI, Checkpoint 3), B (Temporal entry points, Checkpoint 4), C (inference plumbing, Checkpoint 5), D (core runtime, Checkpoint 6), E (tools/config, Checkpoint 7). Phases C/D/E were implemented in one session via parallel fan-out subagents. Open follow-ups: the post-grind code review confirmed several pre-existing source bugs that the new tests pin as-is — captured with fix guidance and the pinning-test inventory in [wip/tests/deferred-source-bugs-pinned-by-tests.md](wip/tests/deferred-source-bugs-pinned-by-tests.md) (headline items: inverted OpenAI image-moderation mapping, GCP storage uri_format validation accepting a non-substituting format, the bundle-spec string-concept arm, the `ConceptSpec.model_validate_spec` isinstance-guard bug, mistral system-message ordering).

## Context for cold start

- **Branch:** `feature/Add-tests` in the `_tests` worktree (treat `_tests/` as repo root; do not look in `pipelex/` sibling).
- **Goal:** unit tests for pipelex-internal CLI logic. The CLI *interface* (arg parsing, `--help`, agent JSON shapes) is owned by `../conformance` — do NOT duplicate it. We test the `_core` functions and check/report logic directly.
- **Where tests go:** `tests/unit/pipelex/cli/` (existing dir, has `conftest.py` with autouse fixtures `reset_traceback_requested` and `reset_agent_cli_error_format`). Build-command tests go in `tests/unit/pipelex/cli/commands/build/`.
- **Established patterns** (read these before writing tests):
  - `tests/unit/pipelex/cli/test_doctor_cmd.py` — mocking `config_manager` via `mocker.patch.object(ConfigLoader, "project_config_dir", new_callable=mocker.PropertyMock, ...)`, real TOML files in `tmp_path`.
  - `tests/unit/pipelex/cli/test_traceback_flag_run_core.py` — driving the async `_execute_run()` with a `_run_async()` helper, mocking `get_console()`, `get_config()`, `PipelexMTHDSProtocol`.
  - `tests/unit/pipelex/cli/test_error_handlers_snapshot.py` — pinning Rich panel output with `Console(width=80, record=True, color_system=None)` + `export_text()`.
  - Booted-library fixtures: `load_empty_library` / `load_test_library` from `tests/conftest.py` (module-scoped `Pipelex.make()` via `reset_pipelex_config_fixture`).
- **Run tests locally:** `.venv/bin/pytest -x -q tests/unit/pipelex/cli/` (fine for iteration); full gate at end = `make agent-check` then `make agent-test`.
- **Coverage measurement** (to update the menu doc — must match how baseline was measured, i.e. the full non-inference suite):
  `.venv/bin/pytest -n auto -m "(dry_runnable or not inference) and not (pipelex_api or codex_disabled)" --cov=pipelex --cov-report=term | grep -E "cli/|TOTAL"`
  Cheaper per-module proxy during iteration: `.venv/bin/pytest -q tests/unit/pipelex/cli --cov=pipelex.cli --cov-report=term-missing`.
- **House rules:** TDD where it makes sense; never hardcode counts in comments/docs; `make agent-check` after code changes; tests must be offline (no inference marks needed here).
- **Pytest standards (`.claude/rules/pytest-standards.md`):** ONE TestClass per test module (so e.g. doctor tests split across several `test_doctor_*.py` files); pytest-mock (`MockerFixture`) only, never unittest.mock; strong asserts on values; parametrize multiple cases; variable names ≥3 chars.

## Phase 1 — `cli/readiness.py` (baseline 20%)

Small, self-contained, zero existing tests. New file `tests/unit/pipelex/cli/test_readiness.py`.

- [x] `_is_in_virtual_environment()`: venv (sys.prefix != base_prefix), conda env var, VIRTUAL_ENV env var, none → False (monkeypatch `sys.prefix`/env)
- [x] `_find_venv_directories()`: finds `.venv`/`venv` with `bin/python` in cwd + parents, ignores dirs without `bin/python`, empty result (monkeypatch cwd to tmp_path)
- [x] `_is_development_install()`: `.git` in parents → True, none → False, AttributeError/OSError → False
- [x] `check_readiness()`: dev+venv passes silently; production passes; dev+no-venv raises `ReadinessCheckError` with activation instructions (venvs found) vs creation instructions (none found)

## Phase 2 — `cli/error_handlers.py` (baseline 51%)

Extend `tests/unit/pipelex/cli/test_error_handlers.py` (or new `test_error_handlers_more.py`). Pattern: recorded Console, assert exit code 1 + key phrases in exported text. Untested handlers are the gateway/telemetry/signature ones.

- [x] `display_error_panel()`: basic render, no error_message, multi-line tip, links, special chars escaped
- [x] `handle_model_deck_preset_error()`: with/without user_action_detail (auto-built "Possible solutions" tip), with/without enabled_backends
- [x] `handle_validate_bundle_error()` + `_display_validation_error_details()`: blueprint errors / pipe errors / dry-run error / signature check error sections, with and without bundle_path, empty lists skip sections
- [x] `handle_signatures_not_allowed_error()`: exit 1 + `--allow-signatures` tip
- [x] `handle_telemetry_config_validation_error()`: exit 1 + migration guidance
- [x] `handle_gateway_terms_not_accepted_error()`, `handle_gateway_api_key_missing_error()`, `handle_gateway_do_not_track_conflict_error()`: exit 1 + expected guidance
- [x] `handle_remote_config_validation_error()` ("Please report this!"), `handle_remote_config_unavailable_error()` (offline guidance)
- [x] `handle_gateway_unknown_model_error()`: FRESH vs CACHED source branches

## Phase 3 — `show_cmd.py` + `which_cmd.py` (baseline 27% each)

New files `tests/unit/pipelex/cli/test_show_cmd.py`, `test_which_cmd.py`. Test the `do_*` functions directly (not the Typer wrappers — wrappers boot Pipelex; mock hub getters instead).

- [x] `do_show_config()`: loads config via config_manager, pretty-prints
- [x] `do_list_pipes()`: calls `get_pipe_library().pretty_list_pipes()`
- [x] `do_show_pipe()`: found → pretty print
- [x] `do_show_backends()`: enabled-only vs `show_all=True` (Status column), no backends → warning, routing-profile display, markup-escape path
- [x] `do_which_pipe()`: found (search path + source label, returns True), not found (returns False, tip shown), empty library_dirs, non-existent dirs marked

### CHECKPOINT 1 — small modules done

Status: **CLEARED 2026-06-12.** New files: `test_readiness.py`, `test_error_handlers_more.py`, `test_show_cmd.py`, `test_which_cmd.py`. CLI unit dir fully green; `make agent-check` clean. Coverage (unit-cli-dir proxy, lower bound vs full suite): readiness 20→97%, error_handlers 51→99%, show_cmd 27→73%, which_cmd 27→66% (remainder in both = the Typer wrappers that boot Pipelex — interface layer, conformance-owned). Decisions: tested `do_*` functions directly with hub getters mocked at the command-module namespace; SimpleNamespace for backend/routing-profile stand-ins; recorded `Console(record=True, color_system=None)` + `export_text()` for output assertions (width 300 for which_cmd to avoid path wrapping); markup-escape path triggered via a mismatched closing tag (`bad[/bold]name`) — an unclosed tag does NOT raise MarkupError.

## Phase 4 — `doctor_cmd.py` (baseline 21%, ~600 stmts — biggest payoff)

Extend `tests/unit/pipelex/cli/test_doctor_cmd.py` with new test classes (keep existing `TestDoctorLayeredResolution` untouched). The check functions return `(healthy, ..., message)` tuples — assert on those, not console output. Existing mocking pattern: ConfigLoader property mocks + real TOML files in tmp_path.

- [x] `check_config_files()`: missing files counted; pipelex.toml ValidationError; ConfigValidationError; TomlError; OSError; all-good path
- [x] `check_telemetry_config()`: file not found; TomlError; valid new format; old-format detection ("format has changed"); invalid new format
- [x] `check_backend_credentials()`: backends.toml missing; all creds valid; missing env var; placeholder value; internal backend skipped; disabled backend skipped; broad-exception path
- [x] `check_backend_files()`: no backends dir; no backends.toml; TomlError; valid file; InferenceBackendLibraryError captured per-file; has_kit_template True/False
- [x] `check_kit_template_exists()` + `replace_backend_file()`: template exists/missing/exception→False; replace happy path writes file; dry_run doesn't write; missing template → False
- [x] `check_deck_sync()`: deck dir missing → healthy; clean deck; dirty deck w/ version mismatch message; manifest missing
- [x] `gather_config_location()`: project-local vs global
- [x] `check_models()`: backend files unhealthy short-circuit; gateway disabled happy path; gateway enabled but service config missing / terms not accepted; remote fetch failure; deck validation error path
- [x] `do_doctor_cmd()` fix mode: config fix → init_cmd(focus=CONFIG); telemetry fix; deck fix → update_cmd(yes=True); backend file replace accepted/declined (mock `Confirm.ask`)

## Phase 5 — `run/_run_core.py` (baseline 32%)

Extend alongside `test_traceback_flag_run_core.py` patterns (new file `tests/unit/pipelex/cli/test_run_core.py`). Mock `PipelexMTHDSProtocol`, `get_config`, `get_console`; use tmp_path for outputs.

- [x] `_execute_run()` happy path: pipe executes, recap printed
- [x] Bundle with main_pipe used when no pipe_code; bundle without main_pipe → Exit(1); no bundle + no pipe_code → Exit(1)
- [x] Inline JSON inputs success; file inputs success (resolve_inputs_paths called); non-dict file JSON → Exit(1)
- [x] Output saving: graphs dir, main_stuff JSON/MD/HTML, working memory JSON (assert files exist in tmp_path)
- [x] CSV branches: happy flat-list save; empty `--save-csv` path → Exit(1); bad suffix → Exit(1); no main_stuff → Exit(1); non-flat output → Exit(1)
- [x] `execute_run()` wrapper: setup/teardown called; `PipeOperatorModelChoiceError` → `handle_model_choice_error`; `PipeOperatorModelAvailabilityError` → handler; `typer.Exit` passthrough

### CHECKPOINT 2 — doctor + run core done

Status: **CLEARED 2026-06-12.** Doctor tests split across one-class-per-module files: `test_doctor_config_checks.py`, `test_doctor_backend_checks.py`, `test_doctor_deck_sync.py`, `test_doctor_check_models.py`, `test_doctor_fix_mode.py`, `test_doctor_display_report.py` (display rendering + the doctor_cmd outer error guard). Run core in `test_run_core_execution.py` + `test_run_core_wrapper.py`. Coverage (unit-cli-dir proxy): doctor_cmd 21→92% (remainder ≈ setup_doctor_runtime, deliberately untested — once-per-process log.configure side effects, existing tests stub it), _run_core 32→94%. Decisions: check functions tested via explicit `config_dir=tmp_path` (resolve_config_file bypasses layering) with real TOML files; check_models decision tree tested with all collaborators mocked at the doctor module namespace (ModelManager, RemoteConfigFetcher, gateway probes); fix mode mocks `doctor_cmd.Confirm.ask` + init_cmd/update_cmd/replace_backend_file; runner mocked via `mocker.AsyncMock` on `PipelexMTHDSProtocol.execute` returning `SimpleNamespace(pipe_output=...)`; pipe_output is a SimpleNamespace with a MagicMock working_memory; render_cost_report_for_output mocked away; CSV happy path mocks flat_field_names + csv_from_list_content but uses a real ListContent for the isinstance check. All green incl. `make agent-check`.

## Phase 6 — `build/*` internals (baseline 21–41%)

New files under `tests/unit/pipelex/cli/commands/build/`. Existing reference: `test_structures_cmd_cross_package_refines.py` (calls `generate_structures_from_blueprints()` directly with tmp output dir).

- [x] `structures_cmd.py`: `_compute_relative_path_from_output_dir()` (inside/outside/equal cwd); `_build_concept_ref_to_class_info()` (skips native domain, qualified names, module paths); `generate_structures_from_blueprints()` (string concept → TextContent; explicit structure; refines native; refines custom qualified; default; `__init__.py` written; skip-existing check; quiet flag)
- [x] `_inputs_core.py`: bundle main_pipe vs explicit pipe_code vs neither → Exit(1); output path defaulting (bundle parent vs results dir); `NoInputsRequiredError` → exit 0 with message; happy path writes JSON
- [x] `_output_core.py`: same pipe/bundle resolution matrix; output path defaulting per format (json/py); happy path writes rendered output; render failure → Exit(1)
- [x] `_runner_core.py`: structures generated + classes registered; runner code generated to `run_{pipe_code}.py` default path; explicit output_path wins; no bundle → Exit(1)

## Phase 7 — Wrap-up

- [x] `make agent-check` clean
- [x] `make agent-test` green (full suite)
- [x] Run the full-suite coverage measurement (command above) and capture new per-module percentages
- [x] Update `wip/tests/missing-tests-menu.md` section A lines with evolved coverage %s (mark items done/improved)
- [x] Update this file's checkpoint statuses; changelog entry if warranted

### CHECKPOINT 3 — section A complete

Status: **CLEARED 2026-06-12 — SECTION A COMPLETE.** Full non-inference suite green with `--cov` (same marker expression as `make agent-test`, run without `--exitfirst` — strictly stronger); `make agent-check` clean; changelog [Unreleased] entry added. Final full-suite coverage (written into the menu doc): doctor_cmd 21→92, _run_core 32→94, show_cmd 27→73, which_cmd 27→66, _output_core 41→74, _runner_core 21→76, _inputs_core 21→72, structures_cmd 41→69, readiness 20→97, error_handlers 51→99; overall pipelex ~72→75%. **Bug found & fixed along the way:** pytest's default `norecursedirs` includes `build`, so everything under `tests/unit/pipelex/cli/commands/build/` was silently skipped in full runs — including the pre-existing cross-package refines regression test, which had never been running. Fixed via a `norecursedirs` override in pyproject.toml `[tool.pytest]` (defaults minus `build`). Phase 6 build-core tests mock the registry getters at the module namespace so the module-scoped Pipelex's real class/func registries are never torn down. (Section C, originally next from here, is complete — see Checkpoint 5.)

## Phase B — Temporal distributed execution (menu section B)

User-prioritized ahead of section C. Deploy-critical entry points: bugs here only surface inside a live cluster. All offline unit tests in `tests/unit/pipelex/temporal/` (existing dir, no conftest; reference style: `test_storage_payload_codec.py` with class-level `@pytest.mark.asyncio(loop_scope="class")`).

### B1 — `temporal/codec/codec_server.py` (baseline 0%)

New file `tests/unit/pipelex/temporal/test_codec_server.py`. Drive the real aiohttp app via `aiohttp.test_utils.TestClient(TestServer(app))` (no pytest-aiohttp plugin needed). Real `StoragePayloadCodec` + `InMemoryStorageProvider` for happy paths; raising stub codec (cast) for error branches.

- [x] CORS preflight (`OPTIONS /encode`, `/decode`): allowed origin → headers set; disallowed/missing origin → no CORS headers
- [x] Content-type guard: non-JSON POST → 415 (with CORS headers when origin allowed)
- [x] Malformed Payloads JSON → 400
- [x] Happy `/encode` → large payload becomes storage-ref payload (JSON parse of response proto); `/decode` of that response restores original bytes (full HTTP round-trip)
- [x] Codec raising `StorageFileNotFoundError` → 404; `OSError` → 502
- [x] Success response: content-type JSON + CORS headers on allowed origin

### B2 — `temporal/temporal_connect.py` (baseline 24%)

New file `tests/unit/pipelex/temporal/test_temporal_connect.py`. Mock at the `temporal_connect` module namespace: `TemporalClient` (class replaced, `.connect` AsyncMock), `get_config`, `get_secret`, `get_required_env`, `make_codec_from_config`, `make_data_converter`. Real `TemporalServerConfig` instances.

- [x] `connect_to_temporal_server()` api_key matrix: NONE → api_key=None/tls=False/empty metadata; ENV_VAR → `get_required_env(api_key_id)`, tls=True, `{"temporal-namespace": ns}`; SECRET_PROVIDER → `get_secret(secret_id=...)`; ENV_VAR/SECRET_PROVIDER with empty api_key_id → `TemporalConfigError`
- [x] Payload codec wiring: enabled → `make_codec_from_config()` + `make_data_converter(payload_codec=...)` passed as converter; disabled → module-level `data_converter`
- [x] `TemporalClient.connect` raising `RuntimeError` → `TemporalServerError` carrying `full_description`
- [x] `connect_to_temporal_selected_server()`: known name → connects with that config; unknown name → `TemporalConfigError`
- [x] `connect_to_temporal()`: uses `temporal_config.selected_server`

### B3 — `temporal/worker_cli.py` (baseline 0%)

New file `tests/unit/pipelex/temporal/test_worker_cli.py`. Test `configure()` directly (sync; mock `Pipelex.make`, `get_config`, `load_toml_from_path`, hub getters at `pipelex.hub`, `run_worker` AsyncMock — `asyncio.run` consumes its coroutine) plus a Typer `CliRunner` pass for arg wiring. `run_worker()` tested async with `get_task_manager` mocked.

- [x] `run_worker()`: forwards all kwargs to `get_task_manager().run_worker`; both project None and explicit project log paths
- [x] Project resolution: explicit arg skips pyproject; `project.name`; `tool.poetry.name` fallback; neither → `ValueError`
- [x] `--is-unit-testing` → `runtime_manager.set_run_mode(RunMode.UNIT_TEST)`; not set → no call
- [x] Fast-fail task-queue check: explicit `--task-queue` vs `worker_config.default_task_queue` fallback passed to `validate_task_queue_known`; validation error propagates before library load
- [x] Library load: dirs resolved → `load_libraries` with them; empty → not called; `open_library`/`set_current_library` with `worker_base`
- [x] `temporal.is_enabled` False → forced on via `model_copy(update={"is_enabled": True})` and reassigned
- [x] CliRunner arg wiring: `--task-queue/--scope/--profile/--is-unit-testing/--is-not-sandboxed` reach `run_worker` positionally correct

### CHECKPOINT 4 — Phase B (Temporal entry points) done

Status: **CLEARED 2026-06-12 — PHASE B COMPLETE.** New files: `test_codec_server.py`, `test_temporal_connect.py`, `test_worker_cli.py` in `tests/unit/pipelex/temporal/`. Full non-inference suite green with `--cov` (same marker expression as `make agent-test`, run without `--exitfirst` — strictly stronger); `make agent-check` clean; targeted temporal unit+integration dirs green; changelog [Unreleased] entry added. Final full-suite coverage (written into the menu doc): worker_cli 0→100, codec_server 0→96, temporal_connect 24→98 — the only missed lines in all three are `TYPE_CHECKING` import blocks. Decisions: codec server driven over real HTTP with `aiohttp.test_utils.TestClient(TestServer(app))` (no pytest-aiohttp plugin needed) — real `StoragePayloadCodec` + `InMemoryStorageProvider` for happy paths, a raising stub codec (cast) for the 404/502 error mapping; temporal_connect mocked entirely at its module namespace (whole `TemporalClient` class replaced so `.connect` is an AsyncMock — never touches the real SDK class), real `TemporalServerConfig` instances; worker_cli's `configure()` tested directly as a sync function (its `asyncio.run` consumes a patched `run_worker` AsyncMock's coroutine) plus Typer `CliRunner` passes for arg wiring — hub getters patched at `pipelex.hub` (they're imported inside the function), `runtime_manager.set_run_mode` patched on the CLASS (pydantic model instances reject attribute patching). Adjacent gap noted, deliberately skipped: `codec/codec_server_cli.py` (0%) is the thin arg-parse + `run_app` wrapper — interface layer, same category as the Typer wrappers excluded in section A. (Section C, originally next from here, is complete — see Checkpoint 5.)

## Phase C — Inference plumbing (menu section C)

Pure-function factories, arg-builders, and config logic around inference — none of these tests touch a provider. Tests go in the existing dirs `tests/unit/pipelex/cogt/{llm,img_gen,models}/` and `tests/unit/pipelex/plugins/{gateway,mistral}/`, plus a new `tests/unit/pipelex/cogt/model_backends/` (no `__init__.py`). Reference patterns to read first: `tests/unit/pipelex/plugins/test_transport_retry_wiring.py` (patching SDK client constructors + factory helper classmethods at the factory module's namespace), `tests/unit/pipelex/cogt/img_gen/test_img_gen_args_factory.py` (`_make_test_job` builder for real `ImgGenJob`, patching `prep_prompt_images` at the args-factory namespace), `tests/unit/pipelex/plugins/gateway/test_gateway_img_gen_worker_malformed_body.py` (`GenericResponse.model_validate({...})` to build Portkey responses with extra fields), `tests/unit/pipelex/plugins/mistral/test_mistral_worker_error_handling.py` (MagicMock-based `llm_job` builder), `tests/unit/pipelex/cogt/models/test_model_deck.py` (`_create_test_model_deck` builder for a fully-valid real `ModelDeck`). Cross-cutting gotchas: (1) the autouse module-scoped `reset_pipelex_config_fixture` boots a real Pipelex for every test module — hub getters work, but never mutate the real plugin/models registries; patch `get_models_manager`/`get_plugin_manager`/`get_model_deck` at the *consuming module's* namespace instead. (2) Both worker factories and the gateway/mistral factories import their collaborators *inside* functions (`# noqa: PLC0415` deferred imports) — those imports resolve at call time, so patch the class at its **source module** (e.g. `pipelex.plugins.openai.openai_completions_llm_worker.OpenAICompletionsLLMWorker`), not at the factory module. (3) `TYPE_CHECKING` blocks in these modules will stay uncovered — that's expected, same as Phase B. All optional SDKs (anthropic, mistralai, fal_client, huggingface_hub, google.genai, aioboto3, instructor) are installed in the venv, so every happy-path branch is reachable offline; the `MissingDependencyError` branches need `mocker.patch("importlib.util.find_spec", return_value=None)`. Per-module coverage proxy during iteration: `.venv/bin/pytest -q tests/unit/pipelex/cogt tests/unit/pipelex/plugins --cov=pipelex.cogt --cov=pipelex.plugins --cov-report=term-missing`.

### C1 — `cogt/llm/structured_output.py` (baseline 55%) + `cogt/model_backends/backend_credentials.py` (baseline 30%)

Pure functions, zero mocking — fastest wins first. New files `tests/unit/pipelex/cogt/llm/test_structured_output.py` and `tests/unit/pipelex/cogt/model_backends/test_backend_credentials.py` (new dir, no `__init__.py`). `as_instructor_mode()` imports `instructor` inside the method (installed, offline-safe). For the credentials messages, `EnvSecretsProvider()` is a real concrete class; the non-env branch just needs anything that fails `isinstance(x, EnvSecretsProvider)` — `mocker.MagicMock(spec=SecretsProviderAbstract)` works (and `make_comprehensive_error_msg` also accepts `secrets_provider=None`).

- [x] `as_instructor_mode()`: parametrize over **every** `StructureMethod` member with its expected `instructor.Mode` value (strong equality asserts on the Mode enum, e.g. `INSTRUCTOR_OPENAI_STRUCTURED_OUTPUTS` → `Mode.TOOLS_STRICT`); include a completeness guard asserting the parametrized set equals `set(StructureMethod)` so a new enum member fails the test instead of silently going untested
- [x] `make_one_variable_missing_error_msg()`: EnvSecretsProvider branch (mentions ".env file", `'{var_name}'=<your_api_key>` line) vs generic-provider branch ("secrets provider" wording); both include backend name, `enabled = false` under `\[backend]` guidance, and the Gateway/BYOK pitch
- [x] `make_comprehensive_error_msg()` env branch: missing vars only; placeholder vars only ("unresolved placeholders" + the `${VAR}` hint line); both kinds on one backend (joined with `;`); multiple backends each get an `enabled = false` line; duplicate missing vars across backends are deduped and sorted
- [x] `make_comprehensive_error_msg()` non-env branch (provider=None or non-env mock): "Provide the missing secrets" wording, missing+placeholder vars merged/sorted into one list
- [x] `BackendCredentialsReport` / `CredentialsValidationReport`: construct with real values, assert field round-trip (cheap completeness for the model definitions)

### C2 — `cogt/models/model_deck_check.py` (baseline 42%)

New file `tests/unit/pipelex/cogt/models/test_model_deck_check.py` (one class; the four check functions are structurally identical so parametrize across `(check_fn, model_type, setting_instance, deck-collection)` tuples). Build a small **real** `ModelDeck` with the `_create_test_model_deck` builder pattern from `tests/unit/pipelex/cogt/models/test_model_deck.py` (required fields: `model_deck_config`, `llm_default_temperature`, `llm_choice_defaults`, `extract_choice_default`, `img_gen_default_quality`, `img_gen_choice_default`, `search_choice_default` — copy the builder as a local helper). Patch `pipelex.cogt.models.model_deck_check.get_model_deck` (imported at module top) to return it; `suggest_model_alternatives` runs for real (pure, offline).

- [x] Setting short-circuit: `LLMSetting`/`ExtractSetting`/`SearchSetting`/`ImgGenSetting` instances return `None` without calling `get_model_deck` (assert the patched getter not called)
- [x] Found paths return `None` for all four functions x all four `ModelReferenceKind`s: preset (`$name`), alias (`@name`), waterfall (`~name`), bare handle (deck populated accordingly; handle needs an `InferenceModelSpec` with the matching `model_type` in `inference_models`)
- [x] Not-found paths raise `ModelChoiceNotFoundError` for all four functions x all four kinds; assert `model_choice == ref.raw` (sigil form preserved), `reference_kind`, `model_type`, and `available_options` equal to the right deck collection's keys (presets vs aliases vs waterfalls vs `inference_models`)
- [x] Fuzzy-suggestion integration: deck containing e.g. handle `gpt-4o-mini`, lookup `gpt-4o-mimi` → `suggestions` contains the near-miss; wrong-sigil case: name exists as alias but referenced as `$name` → `wrong_sigil_hints` non-empty (verify exact `suggest_model_alternatives` return semantics before pinning; assert membership, not full lists)
- [x] String vs `ModelReference` input both accepted (`ensure_model_reference` passthrough): one parametrized pair per kind on the LLM function is enough

### C3 — `cogt/img_gen/img_gen_args_factory.py` (baseline 58%, ~320 stmts — biggest payoff)

The existing `test_img_gen_args_factory.py` covers GPT-image paths, output compression, model-name, and the input-images guard. The gaps are the FAL/Flux/Qwen taxonomies and per-topic edge branches. New one-class-per-file modules in `tests/unit/pipelex/cogt/img_gen/`: `test_img_gen_args_aspect_ratio.py`, `test_img_gen_args_prompt_and_output.py`, `test_img_gen_args_inference_safety.py`, `test_img_gen_args_input_images.py`; put a shared `make_img_gen_job(...)` builder in a new `tests/unit/pipelex/cogt/img_gen/conftest.py` (lifted from the existing test's `_make_test_job`). Gotchas: the INFERENCE branches call `get_config().cogt.img_gen_config.get_num_inference_steps(...)` — patch `pipelex.cogt.img_gen.img_gen_args_factory.get_config` with a MagicMock whose `get_num_inference_steps` returns a known int and assert it was called with the right `model_name`/`quality`; input-image paths need `prep_prompt_images` patched at the same namespace (AsyncMock, established pattern); most per-topic `make_args_from_*` methods are classmethods testable directly without building a full job.

- [x] `make_args_from_aspect_ratio()` FLUX: each supported `AspectRatio` → expected `image_size` string (e.g. SQUARE→`square_hd`, PORTRAIT_9_16→`portrait_16_9`); LANDSCAPE_3_2 / PORTRAIT_2_3 → `ImgGenParameterError` naming Flux
- [x] `make_args_from_aspect_ratio()` FLUX_11_ULTRA: each supported ratio → `aspect_ratio` string (`"1:1"`, `"9:16"`, ...); unsupported pair raises with "Flux-1.1 Ultra" in message
- [x] `make_args_from_aspect_ratio()` QWEN_IMAGE: each supported ratio → exact `{"width", "height", "aspect_ratio"}` triple (e.g. 16:9 → 1664x928); LANDSCAPE_21_9 / PORTRAIT_9_21 raise
- [x] `make_args_from_prompt()`: POSITIVE_ONLY with a negative prompt silently drops it (only `prompt` key; optionally assert the `log.warning` via patched log); WITH_NEGATIVE emits `negative_prompt` only when negative text is set
- [x] `make_args_from_num_images()` FAL → `num_images` vs GPT_IMAGE → `n`; `make_args_from_specific()` FAL → `{"sync_mode": False}`
- [x] `make_args_from_background()`: AVAILABLE → `{"background": value}`; UNAVAILABLE + `Background.TRANSPARENT` → `ImgGenParameterError` with model name; UNAVAILABLE + OPAQUE → `{}`
- [x] `make_args_from_inference()` SDXL_LIGHTNING: steps in {1,2,4,8} pass through; invalid steps coerced to 4; steps=None → config lookup with `model_name="sdxl_lightning"` and quality defaulting to MEDIUM
- [x] `make_args_from_inference()` FLUX and QWEN_IMAGE: explicit steps win; None → config lookup (`model_name="flux"` / `"qwen_image"`); `guidance_scale` included only when truthy
- [x] `make_args_from_inference()` FLUX_11_ULTRA: `is_raw=True` → `{"raw": True}`; falsy → `{}`
- [x] `make_args_from_safety_checker()`: AVAILABLE emits `enable_safety_checker` / `safety_tolerance` independently (each only when not None); UNAVAILABLE → `{}`; OPENAI_MODERATION non-str moderation result → `{}` (check `OpenAIImgGenFactory.moderation_for_openai_image` semantics to pick the is_moderated value that returns non-str)
- [x] `make_args_from_output_format()`: SDXL png→`{"format": "png"}` / jpeg / WEBP raises "SDXL"; FLUX_1 png/jpeg under `output_format` key / WEBP raises "Flux 1"; FLUX_2 and GPT_IMAGE_LEGACY pass any `ImageFormat.value` through incl. webp
- [x] `make_args_from_input_images()` BFL_FLUX_2: key naming `input_image`, `input_image_2`, ... ; mixed `PreparedFileBase64` (data URL) and `PreparedFileHttpUrl` (raw url); more than 8 prepped images capped at 8
- [x] `make_args_from_input_images()` GPT_IMAGE: `PreparedFileHttpUrl` in prepped results → `ImgGenParameterError` ("requires base64 data URLs"); taxonomy NONE + images → error; `input_images=None`/empty → `{}` without calling `prep_prompt_images`
- [x] `make_args_from_input_fidelity()`: GPT_IMAGE_LEGACY happy path emits `input_fidelity` (real `OpenAIImgGenFactory.input_fidelity_for_openai_image`, pure); `input_fidelity=None` → `{}` even for UNAVAILABLE; full-job UNAVAILABLE error already covered by existing test — skip

### C4 — `cogt/llm/llm_worker_factory.py` (baseline 28%) + `cogt/img_gen/img_gen_worker_factory.py` (baseline 40%)

New files `tests/unit/pipelex/cogt/llm/test_llm_worker_factory.py` and `tests/unit/pipelex/cogt/img_gen/test_img_gen_worker_factory.py`. Strategy per test: real `InferenceModelSpec` (vary `sdk=`) and real `InferenceBackend(name=..., api_key="test-key", extra_config={...})`; patch `get_models_manager` and `get_plugin_manager` **at the worker-factory module namespace** — models manager mock returns the backend from `get_required_inference_backend`, plugin manager mock carries a **fresh real `PluginSdkRegistry()`** per test (never the booted Pipelex's registry — `set_sdk_instance` would leak into the module-scoped singleton). Patch each SDK client factory classmethod and worker class at their **source modules** (call-time imports pick up the patch; e.g. `pipelex.plugins.openai.openai_completions_llm_worker.OpenAICompletionsLLMWorker`, `pipelex.plugins.gateway.gateway_completions_factory.GatewayCompletionsFactory.make_portkey_openai_client_for_completions`; for fal patch `fal_client.AsyncClient`, for huggingface patch `huggingface_hub.AsyncInferenceClient`). Assert the patched worker class was called once with the right `sdk_instance`, `inference_model`, `reporting_delegate`, and (where applicable) the right completions/responses factory type with the right `is_http_url_enabled` flag.

- [x] LLM routing matrix (parametrize): `gateway_completions` → `OpenAICompletionsLLMWorker` with a `GatewayCompletionsFactory(is_http_url_enabled=False)`; `gateway_responses`; `portkey_completions`/`portkey_responses`; `openai` and `azure_openai` → `OpenAICompletionsFactory(is_http_url_enabled=True)`; `openai_responses`/`azure_openai_responses`; `anthropic`/`bedrock_anthropic` (worker receives `extra_config=backend.extra_config`); `mistral` (worker receives a `MistralFactory` instance); `bedrock_boto3`/`bedrock_aioboto3`; `google`
- [x] LLM SDK-instance caching: pre-seeded registry entry (`set_sdk_instance` before the call) → client factory **not** called and worker gets the cached instance; cold registry → client factory called once, and a second `make_llm_worker` call reuses it (client factory still called once)
- [x] LLM `MissingDependencyError` branches: `find_spec` patched to None for anthropic, mistral, bedrock (boto3/aioboto3), google — assert error message mentions the extra name; unknown sdk string → `NotImplementedError` containing the plugin
- [x] ImgGen routing matrix (parametrize): `gateway_img_gen` → `GatewayImgGenWorker` via `GatewayFactory.make_portkey_client`; `fal` → `FalAsyncClient(key=backend.api_key)`; `openai_img_gen`; `blackboxai_img_gen` → `OpenAICompletionsImgGenWorker` with `BlackboxaiCompletionsFactory(is_http_url_enabled=True)`; `openrouter_img_gen` → `OpenRouterCompletionsFactory`; `gateway_completions` → `GatewayCompletionsFactory(is_http_url_enabled=False)`; `google`
- [x] ImgGen `huggingface_img_gen`: `variant` set → `HuggingFaceFactory.make_huggingface_inference_provider(provider_str=variant)` result passed as `provider`; variant None → `provider="auto"`; token is `backend.api_key`
- [x] ImgGen `azure_rest_img_gen`: no registry interaction — `AzureImgGenWorker` (patched at its module) constructed directly with `plugin=`, `inference_model=`, `reporting_delegate=`
- [x] ImgGen `MissingDependencyError` branches (fal, google) + unknown sdk → `NotImplementedError` ("not supported for image generation")

### C5 — `plugins/gateway/gateway_completions_factory.py` (baseline 21%)

Three new files in `tests/unit/pipelex/plugins/gateway/` (one class each): `test_gateway_completions_client.py`, `test_gateway_completions_messages.py`, `test_gateway_completions_extract_output.py`. Client tests follow `test_transport_retry_wiring.py` exactly (patch `GatewayFactory.is_debug_enabled/get_endpoint/get_api_key` + `get_config` at the `gateway_completions_factory` namespace, patch `openai.AsyncOpenAI`). Message tests use the MagicMock `llm_job` pattern from the mistral worker tests and patch `prep_prompt_images`/`prep_prompt_documents` at the `gateway_completions_factory` namespace (AsyncMocks returning `PreparedFile*` instances). Extract-output tests build responses with `GenericResponse.model_validate({...})` — extra fields like `pages` become attributes, which is exactly what the `hasattr(response, "pages")` branches need; a dict **without** `pages` exercises the `choices[0].message.content` fallback.

- [x] `make_portkey_openai_client_for_completions()`: wrong `plugin.sdk` (`is_completions` False, e.g. `"gateway_responses"`) → `GatewayFactoryError`; happy path passes `base_url=endpoint`, the non-empty placeholder `api_key`, and `default_headers` built by `createHeaders` containing the portkey api key and debug flag (max_retries already pinned by `test_transport_retry_wiring.py` — don't duplicate)
- [x] `make_simple_messages()` override: system+text → system message first, user content has text part; images path → `image_url` parts with data-URL (base64) and raw URL (http), `detail` from `job_params.image_detail` defaulting to AUTO; `PreparedFileLocalPath` image → `TypeError`
- [x] `make_simple_messages()` documents: base64 doc → `image_url` part with data URL and `detail="auto"`; `PreparedFileHttpUrl`/`PreparedFileLocalPath` doc → `TypeError`; assert `prep_prompt_documents` called with `is_http_url_enabled=False`
- [x] `make_extract_output_from_response()` dispatch: model handles `mistral-document-ai-2505`/`azure-document-intelligence`/`deepseek-ocr`/`linkup-fetch` each route to the right `_make_extract_output_*` (patch the private classmethods and assert); unknown handle → `ValueError` from `GatewayExtractProtocol.make_from_model_handle`
- [x] `_extract_pages_from_choices_content()`: happy JSON-list content; no `choices`; `message` not a dict; `content` not a str; content valid JSON but not a list; malformed JSON — all the falsy paths return `None`
- [x] `_make_extract_output_from_response_azure()`: top-level `pages` (with images: `base64_str`/`mime_type`/`caption`/`bounding_box` mapped into `ExtractedImageFromPage`); fallback via choices content; neither → `GatewayExtractResponseError`; page dict failing `GatewayExtractPageAzure` validation → wrapped `GatewayExtractResponseError`
- [x] `_make_extract_output_from_response_mistral()`: no `pages` attr → error; image without `image_base64` skipped; full corner coords → `BoundingBox` built, partial coords → `bounding_box=None`; schema violation → wrapped error
- [x] `_make_extract_output_from_response_deepseek()`: happy page; `source_image_info.scaled_down=True` triggers the warning branch (and still parses); fallback-pages path; missing pages → error
- [x] `_make_extract_output_from_response_linkup_fetch()` + `_extract_content_string_from_response()`: happy fetch result (markdown/raw_html/images with `alt` empty → caption None) → single page at index 0; content missing → error; content present but invalid `GatewayFetchResultResponse` JSON → wrapped error
- [x] `make_extras()` override delegates to `GatewayFactory.make_extras` with all three args (patch and assert passthrough of the return value)

### C6 — `plugins/mistral/mistral_factory.py` (baseline 27%)

Three new files in `tests/unit/pipelex/plugins/mistral/`: `test_mistral_factory_messages.py`, `test_mistral_factory_extract_output.py`, `test_mistral_factory_document_prep.py`. The mistralai SDK models (`OCRResponse`, `OCRPageObject`, `OCRImageObject`, `UsageInfo`) are plain pydantic — construct them for real, offline. Patch `prepare_prompt_image` / `prep_prompt_images` / `prep_prompt_documents` / `prepare_file_from_uri` at the `mistral_factory` namespace (all imported at module top). `make_mistral_client` retry wiring is already pinned in `test_transport_retry_wiring.py` — don't duplicate. Quirk to pin as-is: `make_simple_messages()` appends the `SystemMessage` **after** the `UserMessage` (note it in the test docstring; if it's deemed a bug, that's a separate fix, not a test-phase change).

- [x] `make_simple_messages()`: text-only → one `UserMessage` with a `TextChunk`; with images → `ImageURLChunk`s appended (gather order preserved); with documents → `DocumentURLChunk`s; system text → `SystemMessage` present (current behavior: after the user message); no content at all → only the system message / empty list variants
- [x] `make_mistral_image_url()` / `make_mistral_document_url()`: base64 → `as_data_url()`; http → raw url; `PreparedFileLocalPath` → `TypeError`; assert `is_http_url_enabled=True` passed to the prep helpers
- [x] `make_simple_messages_openai_typed()`: system first, text part, image parts with detail mapping (`image_detail` None → AUTO), local-path image → `TypeError`
- [x] `make_nb_tokens_by_category()`: real `UsageInfo` with values and with None tokens → 0 fallback for INPUT/OUTPUT
- [x] `_clean_mistral_image_base64()`: already-JPEG (FF D8 prefix) and already-PNG returned unchanged; metadata bytes before JPEG magic stripped (build real bytes, b64-encode, assert decoded result starts with magic); same for PNG; no magic in first 32 bytes → original returned; invalid base64 input → original returned (ValueError branch)
- [x] `make_extracted_image_from_page_from_mistral_ocr_image_obj()`: missing `image_base64` → `MistralExtractResponseError`; full coords → `ImageSize` + `BoundingBox` computed (width/height = bottom-right minus top-left); partial coords → size/bbox None; `mime_type` pinned to `image/jpeg`
- [x] `make_extract_output_from_mistral_response()`: real `OCRResponse` with two pages (one with images, one without) → `ExtractOutput.pages` keyed by page index with markdown text and extracted images
- [x] `make_mistral_image_url_chunk_from_uri()`: http kept as-is; base64 → data URL; local-path result → `TypeError` (mock `prepare_file_from_uri` returns)
- [x] `make_mistral_document_url_chunk_from_uri()`: http kept; local path → `upload_file_to_mistral_for_ocr` + `files.get_signed_url_async` (AsyncMock client, assert `document_url` is the signed url); base64 first-pass → second `prepare_file_from_uri` call with both keeps False → data URL; second pass returning non-base64 → `TypeError`
- [x] `upload_file_to_mistral_for_ocr()`: real file in `tmp_path`, AsyncMock client — assert `files.upload_async` called with `file_name` + bytes content and `purpose="ocr"`, returns the uploaded id

### CHECKPOINT 5 — Phase C done

Status: **CLEARED 2026-06-12 — PHASE C COMPLETE** (implemented via parallel fan-out subagents, one per sub-phase, alongside Phases D and E in the same session). `make agent-check` clean; full non-inference suite green with `--cov` (same marker expression as `make agent-test`, no `--exitfirst`); changelog [Unreleased] entry added (one combined entry for C+D+E). Final full-suite coverage (written into the menu doc): structured_output 55→99, backend_credentials 30→100, model_deck_check 42→100, img_gen_args_factory 58→100, llm_worker_factory 28→100, img_gen_worker_factory 40→99, gateway_completions_factory 21→96, mistral_factory 27→99. Decisions: worker-factory tests use a fresh real `PluginSdkRegistry()` per test (never the booted singleton) with worker/client classes patched at their source modules; gateway extract-output tests build `GenericResponse.model_validate({...})` payloads (extra="allow" makes `pages` an attribute); img_gen args tests share a `make_img_gen_job` builder in a new img_gen conftest; mistral's system-message-AFTER-user-message quirk pinned as-is with a docstring (potential follow-up fix). Remainders deliberately skipped: TYPE_CHECKING blocks, a defensive `except` reachable only if `model_dump` throws, `make_mistral_client` retry wiring (already pinned by `test_transport_retry_wiring.py`).

## Phase D — Core runtime odds and ends (menu section D)

Fill-in section after C. All offline unit tests; each module's tests go in the unit dir mirroring its source path (`tests/unit/pipelex/observer/` is NEW — no `__init__.py`, per standards). Reference patterns: `tests/unit/pipelex/cli/commands/build/test_inputs_core.py` (module-namespace fixture mocking with `SimpleNamespace` stubs + `AsyncMock` for async collaborators), `tests/unit/pipelex/cli/test_graph_rendering.py` (graph_rendering namespace patching — note it lives under `cli/` for historical reasons and already covers `render_graph_from_spec` fully; do NOT re-test it), `tests/unit/pipelex/builder/pipe/pipe_operator/pipe_llm/test_pipe_llm.py` (spec→blueprint with `load_empty_library`). Remember `tests/conftest.py` boots a module-scoped Pipelex autouse, so `get_config()`/hub getters work in every unit module — mock them anyway where determinism or filesystem isolation matters.

### D1 — `observer/local_observer.py` (baseline 0%)

New dir `tests/unit/pipelex/observer/`, new file `test_local_observer.py` (one class, `@pytest.mark.asyncio(loop_scope="class")` — the three observe methods are async). No mocking needed for the explicit-dir path: construct `LocalObserver(storage_dir=tmp_path / "obs")` and assert real JSONL files. For the default-dir branch, patch `get_config` at the `pipelex.observer.local_observer` namespace (it's imported at module top) returning a stub whose `pipelex.observer_config.observer_dir` points inside `tmp_path` — don't let the real config's `results/observer` dir get written. Payloads go through `kajson.dumps`, so use plain str/int dicts and read lines back with `json.loads`.

- [x] Constructor: explicit `storage_dir` (str AND `Path`) creates the directory (parents included); default branch reads `get_config().pipelex.observer_config.observer_dir`
- [x] `observe_before_run` / `observe_after_successful_run` / `observe_after_failing_run` (parametrize on event type): each writes one line to `{event_type}.jsonl` containing `event_type` merged with the payload keys/values (assert exact parsed dict, not just presence)
- [x] Append semantics: two observe calls on the same event type → two JSONL lines, each independently parseable, in call order
- [x] `event_type` key collision: a payload that itself contains `event_type` — the merge order in `_write_to_jsonl` means the payload's value WINS over the event name; pin whichever behavior is current (strong assert on the resulting value)

### D2 — `core/pipes/output/output_renderer.py` (baseline 33%)

The existing `test_output_renderer.py` covers only non-Anything rendering for the three formats and predates the one-class rule (it has three classes) — leave it untouched, add NEW one-class modules alongside it in `tests/unit/pipelex/core/pipes/output/`: `test_output_renderer_collect_condition.py`, `test_output_renderer_collect_sequence.py`, `test_output_renderer_anything_formats.py`. Patch `get_required_pipe` at the `pipelex.core.pipes.output.output_renderer` namespace; build pipes as `mocker.MagicMock()` with `.type` set to exact `PipeType` string values (`"PipeCondition"`, `"PipeSequence"`, `"PipeLLM"`...) and `.output.concept.code` / `.output.concept.concept_ref` / `.output.render_stuff_spec` configured. Gotchas: Anything detection compares `concept.code == NativeConceptCode.ANYTHING`; `pipe_dependencies()` returns a `set[str]`, so with 2+ mapped pipes the `output_option_N` ordering is nondeterministic — use one mapped pipe per case or order-insensitive asserts on the option values; the `TYPE_CHECKING` import block stays uncovered by design.

- [x] `_collect_possible_outputs` PipeCondition arm: empty `pipe_dependencies()` → `[]`; one mapped pipe → `[{concept_ref, content}]` with `content` taken from the rendered dict's `"content"` key (and the `.get("content", output_dict)` fallback when the rendered dict has no `"content"` key); mapped pipe's `render_stuff_spec` raising `ValueError` (and a `PipelexError` subclass — parametrize) → `"<unable to render>"` placeholder entry
- [x] `_collect_possible_outputs` PipeSequence arm: empty `sequential_sub_pipes` → `[]`; last sub-pipe with empty `pipe_code` → `[]`; last pipe with concrete output → single rendered entry; last pipe's `render_stuff_spec` raising → `[]`; last pipe itself having Anything output → recursion into that pipe (two-level `get_required_pipe` side_effect chain, assert the leaf's outputs come back)
- [x] `_collect_possible_outputs` operator arm: a `PipeType.PIPE_LLM` (and one other operator type, parametrized) → `[]`
- [x] `render_output` Anything branches per format (parametrize JSON/PYTHON/SCHEMA): no possible outputs → `ValueError` whose message names `native.Anything`; with possible outputs → JSON has `output_option_1` with `concept`+`content` keys, PYTHON has `# Option 1: <ref>` and `output_1 = <content>` lines, SCHEMA has `schema_option_1` keys (assert parsed values, not substrings only, for the JSON-shaped ones)

### D3 — `graph/graph_rendering.py` (baseline 40%)

`render_graph_from_spec` and `_sanitize_graph_name` are already covered (`tests/unit/pipelex/cli/test_graph_rendering.py`, `tests/unit/pipelex/graph/test_graph_rendering.py`) — the gap is the bundle-level dispatch: `_dry_run_bundle`, `generate_graph_for_bundle`, `generate_view_for_bundle`. New one-class modules in `tests/unit/pipelex/graph/`: `test_graph_rendering_dry_run_bundle.py`, `test_graph_rendering_generate_graph.py`, `test_graph_rendering_generate_view.py`. Patch at the `pipelex.graph.graph_rendering` namespace: `dry_run_pipeline` (AsyncMock returning `(graph_spec_mock, "pipe_code")`), `generate_graph_outputs` (AsyncMock), `save_graph_outputs_to_dir`, `get_config` (MagicMock chain — `get_config().pipelex.pipeline_execution_config.with_execution_overrides(...)` must return a stub with `.graph_config`, and for the view path `.graph_config.reactflow_config.layout_direction` must be a real `FlowchartDirection`). Gotcha: the rename branch calls `Path.rename`, so `save_graph_outputs_to_dir` must return a path to a REAL file created in `tmp_path`. Write a real `.mthds` file in `tmp_path` for `_dry_run_bundle` (it does `read_text`).

- [x] `_dry_run_bundle` library-dirs matrix: `library_dirs=None` → `[str(parent)]`; provided list missing the parent → parent appended (original list NOT mutated); provided list already containing the resolved parent → passed through unchanged; asserts on the exact `dry_run_pipeline` kwargs (`mthds_contents` = file text, `bundle_uris` = `[str(bundle_path)]`)
- [x] `generate_graph_for_bundle` format dispatch (parametrize MERMAIDFLOW/REACTFLOW/BOTH): the `include_mermaidflow`/`include_reactflow` flags reaching `generate_graph_outputs` via the render-config `graphs_inclusion` update match the format
- [x] `generate_graph_for_bundle` rename branch: `reactflow_html` present → file renamed to sanitized `graph_name` (traversal like `../../evil.html` lands as `evil.html` in the same dir), `graph_files` dict carries the renamed str path; no `reactflow_html` key → no rename, dict passthrough
- [x] `generate_graph_for_bundle` return shape: `graph_output_dir` == str(bundle parent), `pipe_code` from dry run, `direction` `None` vs `str(direction)` when passed
- [x] `generate_view_for_bundle`: returns `graph_spec.model_dump(mode="json", by_alias=True)` result under `graphspec`; direction precedence — explicit arg wins, else `reactflow_config.layout_direction`, else `None` (parametrize the three)

### D4 — `builder/bundle_spec.py` (baseline 34%) + `builder/operations/inputs_ops.py` (baseline 20%)

Bundle spec: new one-class modules in `tests/unit/pipelex/builder/` — `test_bundle_spec_validation.py`, `test_bundle_spec_to_blueprint.py`, `test_bundle_spec_rendered_pretty.py`. Use real `PipeLLMSpec`/`PipeSequenceSpec`/`ConceptSpec` instances (spec `to_blueprint()` is hub-free; follow `test_pipe_llm.py` test-data style). Gotchas: pydantic instances reject attribute patching — to force a `ValidationError` from a pipe spec's `to_blueprint`, patch it on the CLASS (`mocker.patch.object(PipeLLMSpec, "to_blueprint", side_effect=...)`) with a real `ValidationError` captured from an intentionally invalid model construction; the string-concept arm produces `ConceptBlueprint(description=<concept KEY>, structure=<string VALUE>)` — counterintuitive, assert it exactly. Inputs ops: new `tests/unit/pipelex/builder/operations/test_inputs_ops.py`, cloning the fixture pattern of `tests/unit/pipelex/cli/commands/build/test_inputs_core.py` with `MODULE = "pipelex.builder.operations.inputs_ops"` (patch `validate_bundle` AsyncMock, `get_library_manager`, `set_current_library`, `resolve_library_dirs`, `get_required_pipe`, `render_inputs` — all top-level imports, so module-namespace patching works).

- [x] `PipelexBundleSpec` validation: invalid domain code → `ValidationError` containing "not a valid domain code"; `main_pipe` absent from `pipe` dict → `ValidationError`; `pipe` empty/None with a `main_pipe` → `ValidationError`; valid spec constructs
- [x] `to_blueprint()` concepts: `ConceptSpec` value → its blueprint (assert description/structure/refines); string value → `ConceptBlueprint(description=key, structure=value)`; `concept=None` → blueprint `concept` is None
- [x] `to_blueprint()` pipes: a `PipeSequenceSpec` main + two `PipeLLMSpec` steps fed in scrambled dict order → blueprint `pipe` dict ordered controller-first then step order (`sort_pipes_by_dependencies` pre-order); spec `to_blueprint` raising `ValidationError` → `PipelexBundleSpecBlueprintError` naming the pipe code; final `PipelexBundleBlueprint` construction failure → `PipelexBundleSpecBlueprintError` with "Failed to create pipelex bundle blueprint"
- [x] `rendered_pretty()`: recorded `Console(record=True, color_system=None)` + `export_text()` — with/without title, description, system_prompt; Concepts table renders both a `ConceptSpec` row and a string-reference row; Pipes table lists each pipe (assert key phrases: domain, main pipe, concept codes)
- [x] `build_inputs_for_pipe` mthds_contents branch: no `pipe_code` → first blueprint with `main_pipe` wins, domain-qualified via `PipeFactory.make_pipe_ref_with_domain` (assert `get_required_pipe` called with `"domain.main"`); no blueprint declares `main_pipe` → `ValueError`; explicit `pipe_code` skips the scan; `validate_bundle` called with `allow_signatures=True` (deliberate, documented behavior — pin it)
- [x] `build_inputs_for_pipe` bundle_path branch: `validate_bundle` called with `mthds_file_path=`; blueprint without `main_pipe` → `ValueError` whose message contains the bundle path; explicit `pipe_code` wins
- [x] `build_inputs_for_pipe` no-bundle branch: `open_library` + `set_current_library` + `resolve_library_dirs` called; non-empty resolved dirs → `load_libraries(library_id=..., library_dirs=...)`; empty resolved dirs → `load_libraries` NOT called; no `pipe_code` → `ValueError` "No pipe code specified"
- [x] Happy-path return shape: `{"success": True, "pipe_code": ..., "inputs": <parsed dict from render_inputs JSON>}` (strong assert on the parsed inputs values)

### D5 — `pipeline/runner.py` (baseline 65%) — targeted error/protocol surfaces only

The happy path, `PipeRouterError` wrap, and the finally-block library-restore matrix are already pinned by `tests/integration/pipelex/pipeline/` (`test_runner_library_lifecycle.py`, `test_pipeline_run_id_resubmission.py`, `test_mock_usage_direct.py`, tracing/cost tests) — do NOT re-test them. The gap is: `extra` rejection, the `except PipelexError` arms, `except ValidationError`, `start()`, and the protocol surfaces `validate()`/`models()`/`version()`. New one-class modules in `tests/unit/pipelex/pipeline/`: `test_runner_execute_error_paths.py`, `test_runner_validate_method.py`, `test_runner_protocol_surfaces.py` (models/version/start/extra). Mocking: hub getters are imported at module top → patch at `pipelex.pipeline.runner.<name>`; `pipeline_run_setup` as AsyncMock returning `(pipe_job_mock, "run-id", "lib-id")`; inject the failing pipe run via the `pipe_run=` constructor arg (no `get_pipe_run` patch needed — see `_FailingPipeRun` in the lifecycle integration test); pass an `execution_config` stub with `is_generate_graph=False` / `is_generate_usage=False` to keep the finally inert (still patch `get_report_delegate`, `get_pipeline_manager`, `get_library_manager`, `set_current_library`/`clear_current_library`, `get_telemetry_manager` at the runner namespace so the finally and telemetry run against mocks); `metadata` is imported as a module → patch `pipelex.pipeline.runner.metadata.version`.

- [x] `execute(extra={"zed": 1, "abc": 2})` → `PipelineRequestError` listing the keys sorted; nothing else needs mocking (the guard fires first)
- [x] `except PipelexError` with resolved job: `pipe_run.run` raising a `PipelexError` subclass → `PipelineExecutionError` carrying `pipe_code`/`output_name`/`run_mode`/`pipe_stack` from the pipe_job stub, `__cause__` is the original, and `get_telemetry_manager().track_event` called with `EventName.PIPELINE_COMPLETE` + `Outcome.FAILURE` properties
- [x] `except PipelexError` with `pipe_job is None`: `pipeline_run_setup` itself raising → the SAME exception instance propagates unwrapped (assert identity via `pytest.raises(...).value`), no telemetry failure event
- [x] `except ValidationError`: `pipe_run.run` raising a real pydantic `ValidationError` (capture one from an invalid mini-model construction) → `PipeExecutionError` whose message contains the model title and the formatted error
- [x] `start()` → `NotImplementedError` mentioning `execute`
- [x] `validate()`: mocked `validate_bundle` result stub — single blueprint → `blueprint` is a dict (not list), multiple → list; `pipe_structures` keyed by pipe code with each pipe's `model_dump(mode="json")`; `library_dirs` strs converted to `Path`s in the call; `allow_signatures` passthrough
- [x] `validate()` finally matrix (patch `get_current_library_id_or_none` with `side_effect` pairs): validation library != prev and prev set → `set_current_library(prev)` + `teardown(validation_id)`; prev None → `clear_current_library()` + teardown; validation library == prev → neither restore nor teardown
- [x] `models()`: `list_models` patched returning two categories of presets + per-category aliases/waterfalls → `PipelexModelDeck.models` has one `MthdsModelInfo(name, type)` per preset, aliases/waterfalls merged across categories; `category=MthdsModelCategory.LLM` → `list_models` called with `[ModelCategory.LLM]`; `category=None` → called with `None`
- [x] `version()`: patched `metadata.version` returning a version string → all three version fields + `protocol_version == MTHDS_PROTOCOL_VERSION` + `implementation == "pipelex"`; `side_effect=metadata.PackageNotFoundError` → `"unknown"` fallback (runtime must not fail)

### CHECKPOINT 6 — Phase D done

Status: **CLEARED 2026-06-12 — PHASE D COMPLETE** (same fan-out session as Phases C and E; shared gates: `make agent-check` clean, full suite green, combined changelog entry). Final full-suite coverage (written into the menu doc): local_observer 0→100, output_renderer 33→98, graph_rendering 40→100, bundle_spec 34→100, inputs_ops 20→98, pipeline/runner 65→93 (runner remainder = happy-path/`PipeRouterError`/tracer-close lines already pinned by the integration suite, by design). Decisions: runner error paths inject failing pipe runs via the `pipe_run=` constructor arg with an inert execution_config stub; bundle_spec string-concept arms reached via `model_construct` because of the source bug below; observer event-type collision pinned (payload value wins). **Source bug found, NOT fixed (test phase only): `ConceptSpec.model_validate_spec` (pipelex/builder/concept/concept_spec.py, mode="before" validator) calls `values.get(...)` without an `isinstance(values, dict)` guard — a plain string validated against the `ConceptSpec | str` union raises bare `AttributeError` instead of falling through to `str`, so a `PipelexBundleSpec` with a string concept reference cannot be constructed via normal validation despite `to_blueprint()`/`rendered_pretty()` having dedicated string arms. Fix = the same isinstance guard `ConceptBlueprint.validate_mutually_exclusive_fields` already has. → follow-up item.**

## Phase E — Tools / config (menu section E)

Fill-in section, good for a small session. All offline unit tests, no Pipelex boot, no network. Tests go in the existing dirs `tests/unit/pipelex/tools/misc/` and `tests/unit/pipelex/tools/storage/`. Reference patterns: `tests/unit/pipelex/tools/misc/test_toml_utils.py` (real TOML files written to `tmp_path` — the established house pattern from the doctor tests), `tests/unit/pipelex/tools/storage/test_s3_storage_provider.py` (the S3 *provider* tests, already mocked — NOT needed here: `storage_config.py` is pure pydantic and imports no boto3, so Phase E needs zero mocking anywhere). Pillow is a core dependency, so image tests use real in-memory images.

### E1 — `tools/misc/toml_sync.py` (baseline 0%)

Highest stakes: `sync_toml_values` rewrites config files in place (consumed by `cli/dev_cli/commands/sync_main_config_cmd.py` against `pipelex/pipelex.toml` and `.pipelex/pipelex.toml`); a bug here destroys user config. Three new files, all using real tomlkit docs / real TOML files in `tmp_path` — no mocks. Gotchas: comment preservation goes through `Item._trivia` restore in `set_nested_value`, so assert on the saved file's RAW TEXT, not the parsed doc; `[[array_of_tables]]` (tomlkit `AoT`) is not a `dict`/`Table` so `collect_leaf_key_paths` treats the whole array as one leaf (compared/synced wholesale) while inline tables (`{a = 1}`) ARE dict subclasses and recurse — pin both behaviors; `load_toml_with_tomlkit` has no existence guard, a missing source/target raises plain `FileNotFoundError`.

- [x] `test_toml_sync_nested_access.py` — `get_nested_value()`: top-level key, 2- and 3-deep dotted path, missing leaf → `(False, None)`, missing intermediate table → `(False, None)`, path traversing THROUGH a scalar (e.g. `key.sub` where `key` is an int) → `(False, None)`; works on a plain `dict` and on a tomlkit `TOMLDocument` (parametrize)
- [x] `test_toml_sync_nested_access.py` — `collect_leaf_key_paths()`: flat doc; nested `[section.sub]` tables → dotted paths; empty doc → `[]`; array value is a single leaf; `[[aot]]` array-of-tables is a single leaf (pins the wholesale-sync behavior); inline table recurses into its keys
- [x] `test_toml_sync_set_value.py` — `set_nested_value()`: existing top-level and nested keys → returns True and value changed; missing final key → False and doc untouched; missing intermediate → False; traversal through scalar → False; **never creates a key that didn't exist** (the destroy-config guard — assert doc unchanged after a False return)
- [x] `test_toml_sync_set_value.py` — trivia preservation: key with an inline comment (`timeout = 30  # seconds`) keeps `# seconds` in `tomlkit.dumps()` output after the value is replaced
- [x] `test_toml_sync_values.py` — happy path on real files in `tmp_path`: target with header comments, inline comments, and a key whose value differs from source → after sync, raw target text has the new value AND every comment/blank line preserved; `TomlSyncResult.updated_keys`/`changes` carry the right `key_path`/`old_value`/`new_value`; `updated_count`/`unchanged_count` properties
- [x] `test_toml_sync_values.py` — structure preservation: key present in source but ABSENT from target is never added; key present in target but absent from source stays untouched and lands in `unchanged_keys`
- [x] `test_toml_sync_values.py` — `dry_run=True`: result reports the would-be changes but target file bytes are identical before/after (also covers that `set_nested_value` is skipped)
- [x] `test_toml_sync_values.py` — no-op write guard: when all values already match, the file is not rewritten — write a target with deliberate formatting quirks, sync, assert raw bytes unchanged and `updated_keys == []`
- [x] `test_toml_sync_values.py` — idempotency round-trip: sync once (changes applied), sync again → second result has zero updated keys and file bytes identical between run 1 and run 2
- [x] `test_toml_sync_values.py` — nested-section sync (`[section.sub] key`) and a type-changing sync (int → string) both apply correctly

### E2 — `tools/misc/document_utils.py` (baseline 0%) + `tools/misc/image_utils.py` (baseline 52%)

Pure enum logic plus one PIL function; no mocks at all. `document_utils` is at 0% simply because nothing in the non-inference suite imports it (only the bedrock plugin does). Build images with `Image.new("RGB", (4, 4))` rather than loading assets — keep fixtures RGB, since saving RGBA to JPEG raises `OSError` in PIL. Verify output format by reopening the bytes with `Image.open` and asserting `.format`. Note: `from_mime_type` in both modules has an unreachable trailing `raise` (type-checker appeasement) — those lines will stay red, that's expected.

- [x] `test_document_utils.py` — `DocumentFormat`: parametrize all members over `is_pdf`/`is_docx`/`is_pptx` (assert exact True/False matrix), `as_file_extension`, `as_mime_type` (assert exact strings incl. the long openxmlformats ones)
- [x] `test_document_utils.py` — classmethods: `get_supported_mime_types()` exact frozenset; `is_supported_mime_type()` True for each member / False for `"image/png"` and garbage; `raise_if_unsupported_mime_type()` no-raise on valid, `ValueError` listing supported types on invalid; `from_mime_type()` round-trips every member and raises `ValueError` on unknown
- [x] `test_image_format.py` — `ImageFormat`: parametrize members over `is_transparent_compatible` (PNG True, JPEG/WEBP False), `is_png`/`is_jpeg`, `as_file_extension` (note JPEG → `"jpg"`), `as_mime_type`
- [x] `test_image_format.py` — `from_mime_type()` round-trip per member; `raise_if_unsupported_mime_type()` BOTH message branches: `"image/tiff"` → "Unsupported image MIME type", `"application/pdf"` → "Invalid image MIME type ... Expected format 'image/<subtype>'"; `get_supported_mime_types()`/`is_supported_mime_type()` exact values
- [x] `test_pil_image_to_bytes.py` — `pil_image_to_bytes()`: parametrize PNG/JPEG/WEBP with a small `Image.new("RGB", ...)` → bytes reopen via `Image.open(io.BytesIO(...))` with `.format == "PNG"/"JPEG"/"WEBP"` (plus magic-byte spot checks: `\x89PNG`, `\xff\xd8`, `RIFF`); `image_format=None` defaults to PNG; pixel content survives a PNG round-trip (lossless — assert `getpixel`)

### E3 — `tools/storage/storage_config.py` (baseline 45%)

Pure pydantic models in `tests/unit/pipelex/tools/storage/` — no boto3, no providers, no mocking (the S3/GCP SDK code lives in the provider modules, already covered by mocked tests; `lazy_validate` is invoked by `storage_provider_factory`). Gotchas: `ConfigModel` is `ConfigDict(extra="forbid", strict=True)` so construct with exact types (real ints; the literal string `"disabled"`); the `method` field alone is `Field(strict=False)` so plain strings coerce to `StorageMethod`; `StorageConfigError` raised inside the `model_validator` propagates UNWRAPPED (pydantic v2 only wraps ValueError/AssertionError) so `pytest.raises(StorageConfigError)` works directly on construction. There is an existing `tests/integration/pipelex/tools/storage/test_storage_config.py` — these unit files get distinct names. One real quirk to pin with a test: S3's `lazy_validate` requires the literal `"{hash}"` in `uri_format` while GCP's only checks for the substring `"hash"` (so GCP accepts `myhash/...` without braces) — pin current behavior and flag the asymmetry in the test docstring.

- [x] `test_storage_s3_config.py` — `StorageS3Config.lazy_validate()` matrix (parametrize): valid config passes silently; empty `uri_format`; `uri_format` missing `{hash}`; empty `bucket_name`; bucket with a dot; bucket with a slash; empty `region`; multiple faults at once → ONE `StorageConfigError` whose message contains every `- set a value for ...` line plus the docs URL
- [x] `test_storage_s3_config.py` — `signed_urls_lifespan` property: int passthrough (e.g. 3600 → 3600) and `"disabled"` → None
- [x] `test_storage_gcp_config.py` — `StorageGcpConfig.lazy_validate()` same matrix with `project_id` instead of `region`; pin that bare `"hash"` (no braces) in `uri_format` passes GCP validation (the S3/GCP asymmetry); `signed_urls_lifespan` int / `"disabled"` cases
- [x] `test_storage_provider_config.py` — `validate_storage_provider_config` model validator (parametrize all four methods): method with its matching sub-config → constructs fine; method with sub-config missing → `StorageConfigError` naming the required section (local/in_memory/s3/gcp); string method coercion (`method="local"` works despite strict mode)
- [x] `test_storage_provider_config.py` — `uri_format` property: returns the right sub-config's format for each of the four methods; error branch per method when the matching sub-config is None (build via `model_construct` to bypass the validator, since the validator otherwise makes them unreachable)
- [x] `test_storage_provider_config.py` — `storage_path` property: returns `local.local_storage_path` when local is set; `StorageConfigError` when local is None (note: it never checks `method` — pin that it works even when method is S3 as long as local config exists)
- [x] `test_storage_provider_config.py` — `StorageConfig` subclass: the two boolean flags (`is_fetch_remote_content_enabled`, `is_upload_local_content_enabled`) are required (omission → `ValidationError`) and round-trip through `model_dump`

### CHECKPOINT 7 — Phase E done

Status: **CLEARED 2026-06-12 — PHASE E COMPLETE, ALL MENU SECTIONS DONE** (same fan-out session as Phases C and D; shared gates: `make agent-check` clean, full suite green, combined changelog entry). Final full-suite coverage (written into the menu doc): toml_sync 0→98, document_utils 0→97, image_utils 52→98, storage_config 45→100; overall pipelex coverage now ~78% (was ~72% before the grind started). Decisions: toml_sync pinned the destroy-config guards on raw file text (never creates keys, comments/structure preserved, dry-run byte-identical, idempotent, no-op write guard); the S3-vs-GCP `{hash}`/bare-`hash` uri_format asymmetry pinned with cross-referenced docstrings (cosmetic follow-up: GCP's error message also lacks the `- ` prefixes and docs URL that S3's has); storage provider properties' unreachable error branches reached via `model_construct`. The test-coverage grind (menu sections A–E) is COMPLETE — remaining per-module gaps are deliberate (TYPE_CHECKING blocks, interface-layer wrappers, integration-pinned lines, live-call worker paths).
